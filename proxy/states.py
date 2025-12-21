from enum import Enum, auto

class SocketTypes(Enum):
    UPSTREAM_SOCKET = auto()
    CLIENT_SOCKET = auto()
    DNS_SOCKET = auto()

class SocketStatus(Enum):
    SOCKET_ACCEPTED = auto()
    COMMAND_WAIT = auto()
    CONNECTION_WAIT = auto()
    SOCKS = auto()
    DATA_WAIT = auto()
    DNS_WAIT = auto()
    HALF_CLOSED_LOCAL = auto()   
    HALF_CLOSED_REMOTE = auto()