from pkg.text import slugify


def test_slugify_simple():
    assert slugify("Hello World") == "hello-world"


def test_slugify_single_word():
    assert slugify("Hello") == "hello"
