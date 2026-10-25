def parse_port(address):
    """Return the port of a "host:port" address. IPv6 hosts are written in brackets."""
    return int(address.rsplit(":", 1)[1])
