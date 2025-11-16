from socket import AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR
from select import EPOLLIN
import socket
import select


class ProxyServer:
    def __init__(self, port: int) -> None: 
        self._address = ('127.0.0.1', port)

        self._server_socket = socket.socket(AF_INET, SOCK_STREAM)
        self._server_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        self._server_socket.setblocking(False)
        self._server_socket.bind(self._address)
        self._server_socket_fd = self._server_socket.fileno()

        self._epoll = select.epoll()
        self._epoll.register(self._server_socket.fileno(), EPOLLIN)

    
    def _handle_event(self, fd: int, event: int):
        if event & EPOLLIN:
            if fd == self._server_socket_fd:
                client_socket = self._server_socket.accept()
            

        
        


    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._server_socket.close()

    
    def run(self) -> None:
        self._server_socket.listen(2)
        
        while True:
            events = self._epoll.poll(timeout=-1)
            for fd, event in events:
                self._handle_event(fd, event)

                


    





