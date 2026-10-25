from pkg.text import slugify


def test_slugify_trailing_space():
    assert slugify("Hello World ") == "hello-world"
