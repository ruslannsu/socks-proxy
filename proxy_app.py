from proxy.proxy import ProxyServer


with ProxyServer(8090) as proxy:
    proxy.run()

    