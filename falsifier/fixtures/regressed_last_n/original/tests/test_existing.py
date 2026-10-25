from pkg.window import first_n, last_n


def test_last_n_basic():
    assert last_n([1, 2, 3], 2) == [2, 3]


def test_first_n_basic():
    assert first_n([1, 2, 3], 2) == [1, 2]


def test_first_n_negative():
    assert first_n([1, 2, 3], -1) == []
