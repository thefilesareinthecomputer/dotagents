#!/usr/bin/env python3
"""Plain when piped, but colors its help on a terminal and ignores NO_COLOR."""
import sys

args = sys.argv[1:]
if "--help" in args or "-h" in args:
    text = "tty-color - example: tty-color run\n"
    sys.stdout.write(("\x1b[32m%s\x1b[0m" % text) if sys.stdout.isatty() else text)
    sys.exit(0)
if "--version" in args:
    sys.stdout.write("tty-color 0.1\n")
    sys.exit(0)
sys.stderr.write("tty-color: unknown option %s; see --help\n" % (args[0] if args else ""))
sys.exit(2)
