def last_n(items, n):
    """Return the last n items of a list. A non-positive n returns an empty list."""
    if n == 0:
        return []
    return items[-n:]


def first_n(items, n):
    """Return the first n items of a list."""
    return items[: max(n, 0)]
