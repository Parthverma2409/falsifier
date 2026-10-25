from pkg.numeric import clamp


def test_clamp_upper_bound():
    assert clamp(15, 0, 10) == 10
    assert clamp(11, 0, 10) == 10
    assert clamp(10, 0, 10) == 10
    assert clamp(9, 0, 10) == 9
