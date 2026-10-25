from pkg.net import parse_port


def test_parse_port_bracketed_ipv6():
    assert parse_port("[::1]:8080") == 8080
