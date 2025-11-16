from socket import AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR, socket
from select import EPOLLIN, epoll
import time


class ProxyServer:
    def __init__(self, port: int) -> None: 
        self._address = ('127.0.0.2', port)

        self._server_socket = socket(AF_INET, SOCK_STREAM)
        self._server_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        self._server_socket.setblocking(False)
        self._server_socket.bind(self._address)
        self._server_socket_fd = self._server_socket.fileno()

        self._epoll = epoll()
        self._epoll.register(self._server_socket.fileno(), EPOLLIN)

        self._client_sockets: dict[int, socket] = {}

    
    def _handle_event(self, fd: int, event: int) -> None:
        if event & EPOLLIN:
            if fd == self._server_socket_fd:
                client_socket, addr = self._server_socket.accept()
                self._client_sockets[client_socket.fileno()] = client_socket
                client_socket.setblocking(False)
                self._epoll.register(client_socket.fileno(), EPOLLIN)    
                return


            bytes = self._client_sockets[fd].recv(1024)
            if (len(bytes) == 0):
                self._client_sockets[fd].close()
                self._client_sockets.pop(fd)


            
            
        
        


    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._server_socket.close()

    
    def run(self) -> None:
        self._server_socket.listen(1)
        
        while True:
            events = self._epoll.poll(timeout=-1)
            print(len(events))
            for fd, event in events:
                self._handle_event(fd, event)


                


    





