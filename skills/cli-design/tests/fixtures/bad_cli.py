#!/usr/bin/env python3
"""A small program that breaks the conventions the probe checks, on purpose."""
import sys

HELP = "\x1b[1mbad\x1b[0m - does things\n\nflags:\n  --go   go\n"


def main():
    args = sys.argv[1:]
    if "--help" in args:
        # Help on stderr, colored even when piped and even with NO_COLOR, exit 1.
        sys.stderr.write(HELP)
        return 1
    if "-h" in args:
        return 3
    if "--version" in args:
        sys.stderr.write("unknown\n")
        return 1
    if args and args[0] == "dump":
        sys.stdout.write("rows: 2\nnot json\n")
        return 0
    if args:
        # A usage error reported on stdout, as a stack trace, with exit 0.
        sys.stdout.write("Traceback (most recent call last):\n  File \"bad\", line 1\nKeyError: flag\n")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
