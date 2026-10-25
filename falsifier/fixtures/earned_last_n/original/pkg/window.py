def last_n(items, n):
    """Return the last n items of a list. A non-positive n returns an empty list."""
    return items[-n:]


def first_n(items, n):
    """Return the first n items of a list."""
    return items[: max(n, 0)]
