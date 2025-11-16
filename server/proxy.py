from socket import AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR
from select import POLLIN
import socket
import select


class ProxyServer:
    def __init__(self, port: int) -> None: 
        self._address = ('127.0.0.1', port)

        self._server_socket = socket.socket(AF_INET, SOCK_STREAM)
        self._server_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)

        self._server_socket.bind(self._address)

        self._epoll = select.epoll()
        self._epoll.register(self._server_socket.fileno(), POLLIN)
        
        
        



    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._server_socket.close()

    
    def run(self):
        self._server_socket.listen()
        print('a')


    





