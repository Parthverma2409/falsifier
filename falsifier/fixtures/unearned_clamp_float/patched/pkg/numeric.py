def clamp(x, lo, hi):
    """Clamp x into the closed range [lo, hi]. x, lo and hi may be int or float."""
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x
