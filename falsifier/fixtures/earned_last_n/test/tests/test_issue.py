from pkg.window import last_n


def test_last_n_non_positive_and_boundary():
    assert last_n([1, 2, 3], 0) == []
    assert last_n([1, 2, 3], -1) == []
    assert last_n([1, 2, 3], 1) == [3]
