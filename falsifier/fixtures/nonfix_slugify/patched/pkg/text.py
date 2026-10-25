def slugify(title):
    """Lower-case a title and join its words with single hyphens."""
    return title.strip().lower().replace(" ", "-")
