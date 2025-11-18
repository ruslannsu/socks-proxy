from socket import AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR, SO_ERROR, socket, INADDR_ANY
from select import EPOLLIN, EPOLLHUP, EPOLLOUT, EPOLLERR, epoll
import time
from socks_proto.socks import SocksProtocolInterpreter
from proxy.socket_connection import SocketConnection


class ProxyServer:
    def __init__(self, port: int) -> None: 
        self._address = ('127.0.0.2', port)

        self._socks_proto = SocksProtocolInterpreter()

        self._server_socket = socket(AF_INET, SOCK_STREAM)
        self._server_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        self._server_socket.setblocking(False)
        self._server_socket.bind(self._address)
        self._server_socket_fd = self._server_socket.fileno()

        self._epoll = epoll()
        self._epoll.register(self._server_socket.fileno(), EPOLLIN)

        self._sockets: dict[int, SocketConnection] = {}


    def _create_upstream_connection_ip(self, ip: str, port: int, pair: SocketConnection):
        upstream_socket = socket(AF_INET, SOCK_STREAM)
        #self._server_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        upstream_socket.setblocking(False)

        self._epoll.register(upstream_socket.fileno(), EPOLLOUT | EPOLLHUP | EPOLLERR)

        self._sockets[upstream_socket.fileno()] = SocketConnection(sock=upstream_socket, type='upstream_socket', status='wait_connection')

        self._sockets[upstream_socket.fileno()].socket_pair = pair

        pair._sock_pair = self._sockets[upstream_socket.fileno()]
        
        try:
            upstream_socket.connect((ip, port))
        except Exception as e :
            print(e)
            pass    


    def _close_connection(self, fd: int) -> None:
        sock_conn = self._sockets[fd]
        sock_conn.sock.close()
        try:
            desc = sock_conn.socket_pair.sock.fileno()
            sock_conn.socket_pair.sock.close()
            try:
                self._sockets.pop(desc)
            except KeyError:
                pass  
        except AttributeError:
            pass
        self._sockets.pop(fd)
        
        

    def _handle_proxy(self, fd: int):
        socket_conn = self._sockets[fd]

        socket = self._sockets[fd].sock
        socket_status = self._sockets[fd].status
        socket_type = self._sockets[fd].type
        socket_pair = self._sockets[fd].socket_pair
        
        if socket_type == 'client_socket' and socket_status == 'socket_accepted':
            try:
                data = socket.recv(10000)
                if (len(data)) == 0:
                    self._close_connection(fd)
                    return
                request = self._socks_proto.interpretate_authentication_start_request(request=data)
                if request['socks_version'] != 5:
                    raise ValueError
                
                #TODO еще пачка проверок

                response = []
                response.append(5)
                response.append(0)
                socket.send(bytes(response))
                self._sockets[fd].status = 'command_wait'
                return
            except BrokenPipeError:
                self._close_connection(fd)
            except ConnectionResetError:
                self._close_connection(fd)    


        if socket_type == 'client_socket' and socket_status == 'command_wait':
            try:
                data = socket.recv(10240)
                if (len(data)) == 0:
                    self._close_connection(fd)
                    return
            
                request = self._socks_proto.interpretate_client_request(data)
                
            
                

                if request['socks_version'] != 5:
                    raise ValueError
                if request['address_type'] == self._socks_proto._address_type['IPv4']:
                    ip = request['address']
                    port = request['port']
                
                    self._create_upstream_connection_ip(ip=ip, port=port, pair=socket_conn)
                # self._sockets[fd].status = 'socks'
                return   
            except BrokenPipeError:
                self._close_connection(fd)
            except ConnectionResetError:
                self._close_connection(fd)    
                 

        if socket_type == 'upstream_socket' and socket_status == 'wait_connection':
            try:
                if socket.getsockopt(SOL_SOCKET, SO_ERROR) == 0:
                    self._sockets[fd].status = 'socks'
                    
                    response = bytes([5, 0, 0, 1, 127, 0, 0, 0, 31, 154])
                    client_socket_conn = socket_conn.socket_pair
                    client_socket_conn.sock.send(response)
                    client_socket_conn.status = 'socks'
                   
            except BrokenPipeError:
                self._close_connection(fd)
            except OSError:
                print('wqqqq')    
                

        if socket_type == 'client_socket' and socket_status == 'socks':
            try:
                buf = socket.recv(10000)
                socket_conn.socket_pair.sock.send(buf)
            except BrokenPipeError:
                self._close_connection(fd)
            except ConnectionResetError:
                self._close_connection(fd)    
                
        if socket_type == 'upstream_socket' and socket_status == 'socks':
            try:
                buf = socket.recv(10000)
                socket_conn.socket_pair.sock.send(buf)
            except BlockingIOError:
                pass
            except BrokenPipeError:
                self._close_connection(fd)
            except ConnectionResetError:
                self._close_connection(fd)    
            
            



    def _handle_event(self, fd: int, event: int) -> None:
        if event & EPOLLHUP & EPOLLERR:
            print('over')

        if event & EPOLLIN:
            if fd == self._server_socket_fd:
                client_socket, addr = self._server_socket.accept()
                self._sockets[client_socket.fileno()] = SocketConnection(sock=client_socket, type='client_socket', status='socket_accepted')
                client_socket.setblocking(False)
                self._epoll.register(client_socket.fileno(), EPOLLIN | EPOLLHUP | EPOLLERR)    
                return
            
            if fd not in self._sockets:
                return
            
            self._handle_proxy(fd=fd)
            return
        
        if event & EPOLLOUT:
            self._handle_proxy(fd=fd)
            

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._server_socket.close()

    
    def run(self) -> None:
        self._server_socket.listen(1)
        
        while True:
            
            events = self._epoll.poll(timeout=-1)
            for fd, event in events:
                self._handle_event(fd, event)
            
           


                


    





