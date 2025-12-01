from enum import Enum, auto

class SocketTypes(Enum):
    UPSTREAM_SOCKET = auto()
    CLIENT_SOCKET = auto()
    DNS_SOCKET = auto()

