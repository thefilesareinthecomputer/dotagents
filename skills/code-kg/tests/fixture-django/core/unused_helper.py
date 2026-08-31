"""Genuinely dead module. Imported by nothing, no framework convention name."""


def format_slug(value):
    return value.strip().lower().replace(" ", "-")


def chunk(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]
