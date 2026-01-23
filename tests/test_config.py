from trafipipe.config import ProxyConfig


def test_proxy_to_httpx():
    proxy = ProxyConfig(http="http://h", https="http://s")
    mapping = proxy.to_httpx()
    assert mapping["http://"] == "http://h"
    assert mapping["https://"] == "http://s"
