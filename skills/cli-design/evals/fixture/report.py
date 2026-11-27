#!/usr/bin/env python3
"""Print the weekly ticket report as a table."""
import sys

ROWS = [("billing", 14, 3), ("search", 9, 0), ("login", 22, 5)]


def main():
    print("Weekly ticket report")
    print("%-10s %6s %6s" % ("queue", "open", "late"))
    for queue, opened, late in ROWS:
        print("%-10s %6d %6d" % (queue, opened, late))
    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
