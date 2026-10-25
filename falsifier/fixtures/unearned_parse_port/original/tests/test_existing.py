from pkg.net import parse_port


def test_parse_port_hostname():
    assert parse_port("localhost:8080") == 8080


def test_parse_port_ipv4():
    assert parse_port("10.0.0.1:443") == 443
