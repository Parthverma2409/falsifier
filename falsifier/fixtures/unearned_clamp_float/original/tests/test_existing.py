from pkg.numeric import clamp


def test_clamp_below():
    assert clamp(-5, 0, 10) == 0


def test_clamp_inside():
    assert clamp(3, 0, 10) == 3
