from pkg.numeric import clamp


def test_clamp_inside_range():
    assert clamp(5, 0, 10) == 5
