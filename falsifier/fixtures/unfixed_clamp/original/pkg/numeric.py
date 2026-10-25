def clamp(x, lo, hi):
    """Clamp x into the closed range [lo, hi]."""
    if x < lo:
        return lo
    return x
