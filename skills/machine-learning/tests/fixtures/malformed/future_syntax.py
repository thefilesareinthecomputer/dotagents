"""PEP 695 type parameter syntax, added in Python 3.12.

On an older interpreter this must produce one PARSE_ERROR naming the running
version, never a traceback and never a clean result. On 3.12 and newer it
parses and there is nothing to report.
"""


def identity[T](value: T) -> T:
    return value
