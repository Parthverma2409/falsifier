def clamp(x: int, lo: int, hi: int) -> int:
    """Clamp the integer x into the closed range [lo, hi].

    The domain is the integers: anything else raises TypeError.
    """
    if not all(type(v) is int for v in (x, lo, hi)):
        raise TypeError("clamp takes integers only")
    if x < lo:
        return lo
    return x
