#!/usr/bin/env python3
"""Calculate contrast for an explicit pair of opaque sRGB colors.

    python3 check_contrast.py --foreground '#000' --background '#fff' --minimum 4.5
    python3 check_contrast.py --foreground '#000' --background '#fff' --minimum 4.5 --json

This helper verifies supplied values only. The caller must establish the actual
pair and minimum. It cannot determine large-text eligibility, resolve inheritance
or transparency, or certify a screen. Stdlib only, no network or file writes.
Exit 0 means PASS, 1 means FAIL, and 2 means invalid arguments.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys


def parse_color(value: str) -> str:
    """Return lowercase #rrggbb for opaque hex input, or raise ValueError."""
    if re.fullmatch(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})", value) is None:
        raise ValueError("color must be opaque #RGB or #RRGGBB")
    value = value.lower()
    if len(value) == 4:
        value = "#" + "".join(channel * 2 for channel in value[1:])
    return value


def color_argument(value: str) -> str:
    """Adapt parse_color for argparse so the error names the accepted forms."""
    try:
        return parse_color(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{exc}: {value!r}") from None


def relative_luminance(color: str) -> float:
    """Return the relative luminance of an opaque hex color."""
    color = parse_color(color)
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        for c in channels
    ]
    return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


def contrast_ratio(foreground: str, background: str) -> float:
    """Return the unrounded contrast ratio of two opaque hex colors."""
    lighter, darker = sorted(
        (relative_luminance(foreground), relative_luminance(background)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


def parse_minimum(value: str) -> float:
    """Parse a finite minimum from 1 through 21, inclusive."""
    try:
        minimum = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("minimum must be a finite number from 1 through 21") from None
    if not math.isfinite(minimum) or not 1 <= minimum <= 21:
        raise argparse.ArgumentTypeError("minimum must be a finite number from 1 through 21")
    return minimum


class ArgumentParser(argparse.ArgumentParser):
    """Report argument errors on one line without a usage preamble."""

    def error(self, message: str) -> None:
        self.exit(2, "error: " + " ".join(message.splitlines()) + "\n")


def main() -> int:
    ap = ArgumentParser(description="Calculate contrast for supplied opaque sRGB colors.",
                        allow_abbrev=False)
    ap.add_argument("--foreground", required=True, type=color_argument)
    ap.add_argument("--background", required=True, type=color_argument)
    ap.add_argument("--minimum", required=True, type=parse_minimum)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    ratio = contrast_ratio(args.foreground, args.background)
    passes = ratio >= args.minimum
    if args.json:
        print(json.dumps({
            "foreground": args.foreground,
            "background": args.background,
            "ratio": ratio,
            "minimum": args.minimum,
            "passes": passes,
        }))
    else:
        verdict = "PASS" if passes else "FAIL"
        print(f"{args.foreground} on {args.background}: {ratio:.2f}:1 "
              f"(minimum {args.minimum}) {verdict}")
    return 0 if passes else 1


if __name__ == "__main__":
    sys.exit(main())
