from socket import AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR, SO_ERROR, socket, INADDR_ANY, SHUT_WR, SHUT_RD
from select import EPOLLIN, EPOLLHUP, EPOLLOUT, EPOLLERR, EPOLLRDHUP, epoll
import errno
import time
from socks_proto.socks import SocksProtocolInterpreter
from proxy.socket_connection import SocketConnection
from dns_proto.dns_protocol import DNSProtocol
from proxy.states import SocketTypes, SocketStatus
from socks_proto.socks import SocksMeta


class ProxyServer:
    def __init__(self, port: int) -> None:
        self._address = ('127.0.0.2', port)
        self._socks_proto = SocksProtocolInterpreter()
        
        self._server_socket = socket(AF_INET, SOCK_STREAM)
        self._server_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        self._server_socket.setblocking(False)
        self._server_socket.bind(self._address)
        self._server_socket_fd = self._server_socket.fileno()
        self._dns_proto = DNSProtocol()
        self._epoll = epoll()
        self._sockets: dict[int, SocketConnection] = {}

        self._dns_socket = self._dns_proto.create_dns_sock()
        self._epoll.register(self._dns_socket.fileno(), EPOLLIN)

        self._sockets[self._dns_socket.fileno()] = SocketConnection(
            sock=self._dns_socket, 
            type=SocketTypes.DNS_SOCKET, 
            status=SocketStatus.DATA_WAIT
        )
        self._domains = {}
        
        self._epoll.register(self._server_socket.fileno(), EPOLLIN)

    def _create_upstream_connection_ip(self, ip: str, port: int, pair: SocketConnection) -> None:
        upstream_socket = socket(AF_INET, SOCK_STREAM)
        upstream_socket.setblocking(False)
        
        try:
            self._epoll.register(upstream_socket.fileno(), EPOLLIN | EPOLLOUT | EPOLLHUP | EPOLLERR | EPOLLRDHUP)
        except FileExistsError:
            upstream_socket.close()
            return
            
        upstream_conn = SocketConnection(
            sock=upstream_socket, 
            type=SocketTypes.UPSTREAM_SOCKET, 
            status=SocketStatus.CONNECTION_WAIT
        )
        upstream_conn.socket_pair = pair
        pair.socket_pair = upstream_conn
        
        self._sockets[upstream_socket.fileno()] = upstream_conn

        try:
            upstream_socket.connect((ip, port))
        except BlockingIOError:
            pass
        except (ConnectionRefusedError, OSError) as e:
            self._close_connection(upstream_socket.fileno())
            if pair and pair.sock:
                self._close_connection(pair.sock.fileno())
            return

    def _handle_half_close(self, fd: int, socket_conn: SocketConnection) -> None:
        if not socket_conn.socket_pair:
            return
            
        pair_fd = socket_conn.socket_pair.sock.fileno()
        if pair_fd not in self._sockets:
            return
            
        pair_conn = self._sockets[pair_fd]
        
        if socket_conn.status in [SocketStatus.SOCKS, SocketStatus.HALF_CLOSED_REMOTE]:
            socket_conn.status = SocketStatus.HALF_CLOSED_REMOTE
            
            if not pair_conn.buffer or len(pair_conn.buffer) == 0:
                try:
                    pair_conn.sock.shutdown(SHUT_WR)
                    pair_conn.status = SocketStatus.HALF_CLOSED_LOCAL
                except OSError:
                    pass
                
                if pair_fd in self._sockets:
                    self._epoll.modify(pair_fd, EPOLLIN | EPOLLHUP | EPOLLERR | EPOLLRDHUP)

    def _close_pair_connections(self, fd: int) -> None:
        if fd not in self._sockets:
            return
            
        sock_conn = self._sockets[fd]
        
        if sock_conn.socket_pair and sock_conn.socket_pair.sock:
            pair_fd = sock_conn.socket_pair.sock.fileno()
            if pair_fd in self._sockets:
                self._close_connection_impl(pair_fd)
        
        sock_conn.socket_pair = None

    def _close_connection_impl(self, fd: int) -> None:
        if fd not in self._sockets:
            return
            
        sock_conn = self._sockets[fd]
        
        try:
            self._epoll.unregister(fd)
        except (OSError, FileNotFoundError):
            pass
        
        try:
            if sock_conn.sock:
                sock_conn.sock.close()
        except OSError:
            pass
        
        try:
            del self._sockets[fd]
        except KeyError:
            pass
        
    def _close_connection(self, fd: int) -> None:
        if fd not in self._sockets:
            return
        
        self._close_pair_connections(fd)
        self._close_connection_impl(fd)

    def _handle_proxy(self, fd: int, event: int) -> None:
        if fd not in self._sockets:
            return
            
        socket_conn = self._sockets[fd]
        sock = socket_conn.sock
        socket_status = socket_conn.status
        socket_type = socket_conn.type
        
        try:
            if event & EPOLLRDHUP:
                self._handle_half_close(fd, socket_conn)
                
            if socket_type == SocketTypes.CLIENT_SOCKET and socket_status == SocketStatus.SOCKET_ACCEPTED:
                try:
                    data = sock.recv(10000)
                    if len(data) == 0:
                        self._close_connection(fd)
                        return
                        
                    request = self._socks_proto.interpretate_authentication_start_request(request=data)
                    if request[SocksMeta.SOCKS_VERSION] != 5:
                        raise ValueError
                    
                    response = bytes([5, 0])
                    sock.send(response)
                    socket_conn.status = SocketStatus.COMMAND_WAIT
                    return
                    
                except BlockingIOError:
                    return
                except (BrokenPipeError, ConnectionResetError, OSError):
                    self._close_connection(fd)
                    return

            if socket_type == SocketTypes.DNS_SOCKET and socket_status == SocketStatus.DATA_WAIT:
                try:
                    data, _addr = sock.recvfrom(2000)
                    _, ips, domain_name = self._dns_proto.parse_dns_response(data)
                            
                    ip = ips[0]
                    
                    if domain_name not in self._domains:
                        return
                    
                    client_list = self._domains[domain_name]

                    for conn in client_list:
                        _port = conn.upstream_port
                       
                        self._create_upstream_connection_ip(
                            pair=conn, 
                            ip=ip, 
                            port=_port
                        )
                    del self._domains[domain_name]

                except (OSError, KeyError):
                    pass
                return

            if socket_type == SocketTypes.CLIENT_SOCKET and socket_status == SocketStatus.COMMAND_WAIT:
                try:
                    data = sock.recv(10240)
                    if len(data) == 0:
                        self._close_connection(fd)
                        return
                    
                    request = self._socks_proto.interpretate_client_request(data)
                    if request[SocksMeta.SOCKS_VERSION] != 5:
                        raise ValueError
                    
                    if request[SocksMeta.ADDRESS_TYPE] == self._socks_proto._address_type['DNS']:
                        request[SocksMeta.ADDRESS] = request[SocksMeta.ADDRESS][2:-1]
                        socket_conn.upstream_port = request[SocksMeta.PORT]
                        
                        addr = request[SocksMeta.ADDRESS] 
                        if addr in self._domains:
                            self._domains[addr].append(socket_conn)
                        else:
                            self._domains[addr] = []
                            self._domains[addr].append(socket_conn)
                            
                                                    
                        self._dns_proto.send_dns_query(
                            sock=self._dns_socket, 
                            hostname=request[SocksMeta.ADDRESS]
                        )
                        
                        socket_conn.status = SocketStatus.DNS_WAIT
                        
                    elif request[SocksMeta.ADDRESS_TYPE] == self._socks_proto._address_type['IPv4']:
                        ip = request[SocksMeta.ADDRESS]
                        port = request[SocksMeta.PORT]
                        self._create_upstream_connection_ip(
                            ip=ip, 
                            port=port, 
                            pair=socket_conn
                        )
                        
                except (BrokenPipeError, ConnectionResetError, OSError, ValueError):
                    self._close_connection(fd)
                return

            if socket_type == SocketTypes.UPSTREAM_SOCKET and socket_status == SocketStatus.CONNECTION_WAIT:
                try:
                    err = sock.getsockopt(SOL_SOCKET, SO_ERROR)
                    if err == 0:
                        socket_conn.status = SocketStatus.SOCKS
                        
                        response = bytes([5, 0, 0, 1, 127, 0, 0, 0, 31, 154])
                        
                        if socket_conn.socket_pair and socket_conn.socket_pair.sock:
                            client_socket_conn = socket_conn.socket_pair
                            client_socket_conn.sock.send(response)
                            client_socket_conn.status = SocketStatus.SOCKS
                            
                            self._epoll.modify(fd, EPOLLIN | EPOLLHUP | EPOLLERR | EPOLLRDHUP)
                            self._epoll.modify(
                                client_socket_conn.sock.fileno(), 
                                EPOLLIN | EPOLLHUP | EPOLLERR | EPOLLRDHUP
                            )
                    else:
                        self._close_connection(fd)
                        if socket_conn.socket_pair:
                            self._close_connection(socket_conn.socket_pair.sock.fileno())
                            
                except (BrokenPipeError, OSError, AttributeError):
                    self._close_connection(fd)
                return

            if socket_status in [SocketStatus.SOCKS, SocketStatus.HALF_CLOSED_REMOTE, SocketStatus.HALF_CLOSED_LOCAL]:
                if event & EPOLLIN:
                    try:
                        data = sock.recv(8192)
                        if len(data) == 0:
                            if socket_status in [SocketStatus.HALF_CLOSED_LOCAL, SocketStatus.HALF_CLOSED_REMOTE]:
                                self._close_connection(fd)
                            else:
                                try:
                                    sock.shutdown(SHUT_WR)
                                    socket_conn.status = SocketStatus.HALF_CLOSED_LOCAL
                                    self._epoll.modify(fd, EPOLLIN | EPOLLHUP | EPOLLERR | EPOLLRDHUP)
                                except OSError:
                                    self._close_connection(fd)
                            return
                            
                        if socket_conn.socket_pair and socket_conn.socket_pair.sock:
                            socket_conn.socket_pair.buffer_update(data)
                            
                            pair_fd = socket_conn.socket_pair.sock.fileno()
                            if pair_fd in self._sockets:
                                self._epoll.modify(
                                    pair_fd, 
                                    EPOLLIN | EPOLLOUT | EPOLLHUP | EPOLLERR | EPOLLRDHUP
                                )
                                
                    except BlockingIOError:
                        pass
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        self._close_connection(fd)
                
                if event & EPOLLOUT:
                    try:
                        if socket_conn.buffer and len(socket_conn.buffer) > 0:
                            sent = sock.send(socket_conn.buffer)
                            if sent > 0:
                                socket_conn.buffer = socket_conn.buffer[sent:]
                                
                            if len(socket_conn.buffer) == 0:
                                if socket_status == SocketStatus.HALF_CLOSED_LOCAL:
                                    self._close_connection(fd)
                                else:
                                    self._epoll.modify(
                                        fd, 
                                        EPOLLIN | EPOLLHUP | EPOLLERR | EPOLLRDHUP
                                    )
                                
                    except BlockingIOError:
                        pass
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        self._close_connection(fd)
                        
        except Exception as e:
            print(f"Error in handle_proxy: {e}")
            self._close_connection(fd)

    def _handle_event(self, fd: int, event: int) -> None:
        try:
            if event & EPOLLERR:
                self._close_connection(fd)
                return
            
            if fd == self._server_socket_fd and (event & EPOLLIN):
                try:
                    client_socket, addr = self._server_socket.accept()
                    client_socket.setblocking(False)
                    client_fd = client_socket.fileno()
                    
                    self._sockets[client_fd] = SocketConnection(
                        sock=client_socket, 
                        type=SocketTypes.CLIENT_SOCKET, 
                        status=SocketStatus.SOCKET_ACCEPTED
                    )
                    
                    self._epoll.register(
                        client_fd, 
                        EPOLLIN | EPOLLHUP | EPOLLERR | EPOLLRDHUP
                    )
                    
                except (OSError, BlockingIOError):
                    pass
                return
            
            if fd in self._sockets:
                if event & (EPOLLHUP | EPOLLRDHUP):
                    self._handle_proxy(fd=fd, event=event)
                elif (event & EPOLLOUT) or (event & EPOLLIN):
                    self._handle_proxy(fd=fd, event=event)
        
        except Exception as e:
            print(f"Error in handle_event: {e}")
            if fd in self._sockets:
                self._close_connection(fd)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        for fd in list(self._sockets.keys()):
            self._close_connection_impl(fd)
        
        try:
            self._server_socket.close()
        except:
            pass
    
    def run(self) -> None:
        self._server_socket.listen(100)
        while True:
            try:
                events = self._epoll.poll(timeout=1)
                for fd, event in events:
                    self._handle_event(fd, event)
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error in main loop: {e}")
                time.sleep(0.1)