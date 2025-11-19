import struct
from socket import socket, AF_INET, SOCK_DGRAM
import dns.message
import dns.rdatatype

class DNSProtocol:
    def _create_dns_query(self, hostname, query_id=None):
        
        query = dns.message.make_query(hostname, dns.rdatatype.A)
        
        if query_id is not None:
            query.id = query_id
        
        query_data = query.to_wire()
        return query_data
    

    def create_dns_sock(self) -> socket:
        sock = socket(AF_INET, SOCK_DGRAM)
        sock.setblocking(False)
        return sock

        
    def send_dns_query(self, sock: socket, hostname: str):
        query_id = 12345  
        dns_query = self._create_dns_query(hostname, query_id)
        
        dns_server = ('8.8.8.8', 53)
        sock.sendto(dns_query, dns_server)

    def parse_dns_response(self, data):
        try:
            response = dns.message.from_wire(data) 
            ips = []
            for answer in response.answer:
                if answer.rdtype == dns.rdatatype.A:
                    for item in answer:
                        ips.append(item.address)
            
            return response.id, ips
            
        except Exception as e:
            print(f"DNS parse error: {e}")
            return 0, []    