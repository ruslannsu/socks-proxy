from socket import AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR, SO_ERROR, socket, INADDR_ANY
from select import EPOLLIN, EPOLLHUP, EPOLLOUT, EPOLLERR, EPOLLRDHUP, epoll
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

        self._sockets[self._dns_socket.fileno()] = SocketConnection(sock=self._dns_socket, type=SocketTypes.DNS_SOCKET, status=SocketStatus.DATA_WAIT)
        self._domains = {}
        
        self._epoll.register(self._server_socket.fileno(), EPOLLIN)

        


    def _create_upstream_connection_ip(self, ip: str, port: int, pair: SocketConnection):
        upstream_socket = socket(AF_INET, SOCK_STREAM)
        #self._server_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        upstream_socket.setblocking(False)
        self._epoll.register(upstream_socket.fileno(), EPOLLIN | EPOLLOUT | EPOLLHUP | EPOLLERR | EPOLLRDHUP)
        self._sockets[upstream_socket.fileno()] = SocketConnection(sock=upstream_socket, type=SocketTypes.UPSTREAM_SOCKET, status=SocketStatus.CONNECTION_WAIT)
        self._sockets[upstream_socket.fileno()].socket_pair = pair
        pair._sock_pair = self._sockets[upstream_socket.fileno()]

        try:
            upstream_socket.connect((ip, port))
        except ConnectionRefusedError:
            raise ConnectionRefusedError
        except Exception as e:
            pass
        
    def _close_connection(self, fd: int) -> None:
        if fd not in self._sockets:
            return
        
        try:
            sock_conn = self._sockets[fd]
            desc = sock_conn.sock.fileno()
            self._epoll.unregister(desc)
            sock_conn.sock.close()
        except:
            pass
            
        try:
            self._epoll.unregister(fd)
        except:
            pass
            
        sock_conn = self._sockets[fd]
        try:
            sock_conn.sock.close()
        except:
            pass
            
        try:
            del self._sockets[fd]
        except KeyError:
            pass
        
    def _handle_proxy(self, fd: int):
        socket_conn = self._sockets[fd]

        socket = self._sockets[fd].sock
        socket_status = self._sockets[fd].status
        socket_type = self._sockets[fd].type
        socket_pair = self._sockets[fd].socket_pair
        
        if socket_type == SocketTypes.CLIENT_SOCKET  and socket_status == SocketStatus.SOCKET_ACCEPTED:
            try:
                data = socket.recv(10000)
                if (len(data)) == 0:
                    print('bb')
                    self._close_connection(fd)
                    return
                request = self._socks_proto.interpretate_authentication_start_request(request=data)
                if request[SocksMeta.SOCKS_VERSION] != 5:
                    raise ValueError
                
                #TODO еще пачка проверок

                response = []
                response.append(5)
                response.append(0)
                socket.send(bytes(response))
                self._sockets[fd].status = SocketStatus.COMMAND_WAIT
                return
            except (BrokenPipeError, ConnectionResetError):
                self._close_connection(fd)

        if socket_type == SocketTypes.DNS_SOCKET and socket_status == SocketStatus.DATA_WAIT:
            data, _addr = socket.recvfrom(2000)
            
            _, ips, domain_name = self._dns_proto.parse_dns_response(data)
            ip = ips[0]
            client_socket_conn = self._domains[domain_name]
            _port = client_socket_conn.upstream_port
            #self._close_connection(fd)

            self._create_upstream_connection_ip(pair=client_socket_conn, ip=ip, port=_port) 
            
        if socket_type == SocketTypes.CLIENT_SOCKET  and socket_status == SocketStatus.COMMAND_WAIT:
            try:
                data = socket.recv(10240)
                if (len(data)) == 0:
                    print('gg')
                    self._close_connection(fd)
                    return
            
                request = self._socks_proto.interpretate_client_request(data)
                if request[SocksMeta.SOCKS_VERSION] != 5:
                    raise ValueError
                
                if request[SocksMeta.ADDRESS_TYPE] == self._socks_proto._address_type['DNS']:
                    dns_sock = self._dns_socket
                    request[SocksMeta.ADDRESS] = request[SocksMeta.ADDRESS][2:-1]
                    socket_conn.upstream_port = request[SocksMeta.PORT]
                    self._domains[request[SocksMeta.ADDRESS]] = socket_conn
                    
                    self._dns_proto.send_dns_query(sock=dns_sock, hostname=request[SocksMeta.ADDRESS])
                    

                if request[SocksMeta.ADDRESS_TYPE] == self._socks_proto._address_type['IPv4']:
                    ip = request[SocksMeta.ADDRESS]
                    port = request[SocksMeta.PORT]
                    self._create_upstream_connection_ip(ip=ip, port=port, pair=socket_conn)
                # self._sockets[fd].status = 'socks'
                return   
            except (BrokenPipeError, ConnectionResetError, OSError):
                self._close_connection(fd)
           

        if socket_type == SocketTypes.UPSTREAM_SOCKET and socket_status == SocketStatus.CONNECTION_WAIT:
            try:
                if socket.getsockopt(SOL_SOCKET, SO_ERROR) == 0:
                    self._sockets[fd].status = SocketStatus.SOCKS
                    response = bytes([5, 0, 0, 1, 127, 0, 0, 0, 31, 154])

                    client_socket_conn = socket_conn.socket_pair
                    client_socket_conn.sock.send(response) #type: ignore
                    client_socket_conn.status = SocketStatus.SOCKS #type: ignore
            except (BrokenPipeError, OSError):
                self._close_connection(fd)
                
        if socket_type == SocketTypes.CLIENT_SOCKET  and socket_status == SocketStatus.SOCKS:
            try:
                buf = socket.recv(10000)
                socket_conn.socket_pair.sock.send(buf) #type: ignore 
            except (BrokenPipeError, ConnectionResetError, OSError):
                self._close_connection(fd)
                
        if socket_type == SocketTypes.UPSTREAM_SOCKET and socket_status == SocketStatus.SOCKS:
            #TODO: сохранять buf в структуру 
            try:
                buf = socket.recv(10000)
                socket_conn.socket_pair.sock.send(buf) #type: ignore
            except BlockingIOError:
                pass
            except (BrokenPipeError, ConnectionResetError, OSError):
                self._close_connection(fd)   
            
    def _handle_event(self, fd: int, event: int) -> None:
        if event & (EPOLLHUP | EPOLLERR | EPOLLRDHUP):
            self._close_connection(fd)
            return
       
        if event & EPOLLIN:
            if fd == self._server_socket_fd:
                client_socket, addr = self._server_socket.accept()
                self._sockets[client_socket.fileno()] = SocketConnection(sock=client_socket, type=SocketTypes.CLIENT_SOCKET , status=SocketStatus.SOCKET_ACCEPTED)
                client_socket.setblocking(False)
                self._epoll.register(client_socket.fileno(), EPOLLIN | EPOLLHUP | EPOLLERR | EPOLLRDHUP)    
                return
            
            if fd not in self._sockets:
                return
            
            self._handle_proxy(fd=fd)
            return
        
        if event & EPOLLOUT:
            self._epoll.modify(fd, EPOLLIN | EPOLLHUP | EPOLLERR | EPOLLRDHUP)
            self._handle_proxy(fd=fd)
            

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._server_socket.close()

    
    def run(self) -> None:
        self._server_socket.listen(100)
        i = 0
        while True:
            i += 1
            print(i)
            events = self._epoll.poll(timeout=-1)
            for fd, event in events:
                self._handle_event(fd, event)
            
           


                


    





