from socket import socket

class SocketConnection:
    def __init__(self, sock: socket, type, status) -> None:
        self._sock = sock
        self._type = type
        self._status = status
        self._handle_info: str | None = None
        self._sock_pair: None | SocketConnection = None
        
        self._sock_meta: None | SocketConnection = None
        self._upstream_port: None | int = None
        
        self._buffer = b''
        


    
    def buffer_update(self, buffer):
        self._buffer += buffer

    @property
    def buffer(self):
        return self._buffer
    
    @buffer.setter
    def buffer(self, buffer):
        self._buffer = buffer
    
    def clear_buffer(self):
        self._buffer = b''

    @property
    def sock(self):
        return self._sock
    
    @property
    def type(self):
        return self._type
    
    @property
    def status(self):
        return self._status
    
    @status.setter
    def status(self, status: str):
        self._status = status
    
    @property
    def socket_pair(self):
        return self._sock_pair
    
    @socket_pair.setter
    def socket_pair(self, sock) -> None:
        self._sock_pair = sock

    @property
    def handle_info(self):
        return self._handle_info

    @handle_info.setter
    def handle_info(self, handle: str):
        self._handle_info = handle    
    
    @property
    def upstream_port(self):
        return self._upstream_port

    @upstream_port.setter
    def upstream_port(self, port):
        self._upstream_port = port

    