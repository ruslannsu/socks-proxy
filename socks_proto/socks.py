
class SocksProtocolInterpreter:
    def __init__(self) -> None:
        self._address_type = {'IPv4': 1, 'DNS': 2, 'IPv6':3}
        self._aut_methods = {'noauth': 0, 'GSSAPI': 1, 'UP': 2}
        self._commands = {'connect': 1}
        self.socks_ver = 5

    def interpretate_authentication_start_request(self, request) -> dict:
        bytes_list = list(request)
        interpreted_request = {}

        interpreted_request['socks_version'] = bytes_list[0]
        
        interpreted_request['socks_auth_methods_count'] = bytes_list[1]

        method_counter = 0
        for method in bytes_list[2:]:
            method_counter += 1
            interpreted_request[f'auth_method{method_counter}'] = method

        return interpreted_request

    def interpretate_client_request(self, request) -> dict:
        bytes_list = list(request)
        interpreted_request = {}

        interpreted_request['socks_version'] = bytes_list[0]
        interpreted_request['command'] = bytes_list[1]
        interpreted_request['address_type'] = bytes_list[3]

        address = bytes_list[4:8]
        interpreted_request['address'] = '.'.join([str(x) for x in address])
        interpreted_request['port'] = 443

        return interpreted_request







        
        
    