from pkg.numeric import clamp


def test_clamp_upper_bound():
    assert clamp(15, 0, 10) == 10
