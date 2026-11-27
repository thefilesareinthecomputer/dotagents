#!/usr/bin/env python3
"""A small program that follows the conventions the probe checks."""
import argparse
import json
import os
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="good",
        description="List the tides for a harbor.",
        epilog="examples:\n  good list --json\n  good list --harbor north",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version="good 1.2.0")
    sub = parser.add_subparsers(dest="cmd")
    lst = sub.add_parser("list", help="list tides", description="List tides.",
                         epilog="example:\n  good list --json",
                         formatter_class=argparse.RawDescriptionHelpFormatter)
    lst.add_argument("--json", action="store_true")
    lst.add_argument("--harbor", default="north")
    args = parser.parse_args()
    if args.cmd is None:
        parser.print_usage(sys.stderr)
        sys.stderr.write("good: name a command; try `good --help`\n")
        return 2
    rows = [{"harbor": args.harbor, "high": "06:12"}, {"harbor": args.harbor, "high": "18:40"}]
    if args.json:
        json.dump(rows, sys.stdout)
        sys.stdout.write("\n")
        return 0
    color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    for row in rows:
        text = "%s  %s" % (row["harbor"], row["high"])
        sys.stdout.write(("\x1b[1m%s\x1b[0m\n" % text) if color else text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
