from pkg.window import last_n


def test_last_n_zero():
    assert last_n([1, 2, 3], 0) == []
