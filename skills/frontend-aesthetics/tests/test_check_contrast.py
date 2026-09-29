#!/usr/bin/env python3
"""Test contrast arithmetic and the CLI contract with stdlib unittest.

    python3 -B -m unittest discover -s skills/frontend-aesthetics/tests
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_contrast.py"
SPEC = importlib.util.spec_from_file_location("check_contrast", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
contrast = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contrast)

INVALID_COLORS = (
    "", "#12", "#12345", "#1234567", "#ggg", "abc", "123456",
    "#abcd", "#11223344", "black", "white", "transparent",
    "var(--color)", "linear-gradient(#000, #fff)", "rgb(0, 0, 0)",
    " #abc", "#abc ", "#abc\n",
)


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


def check(foreground: str, background: str, minimum: str,
          *extra: str) -> subprocess.CompletedProcess[str]:
    return run("--foreground", foreground, "--background", background,
               "--minimum", minimum, *extra)


class TestContrastMath(unittest.TestCase):
    def test_black_white(self) -> None:
        self.assertEqual(contrast.contrast_ratio("#000000", "#ffffff"), 21.0)

    def test_identical_colors(self) -> None:
        for color in ("#000", "#fff", "#abc", "#647b7d"):
            with self.subTest(color=color):
                self.assertEqual(contrast.contrast_ratio(color, color), 1.0)

    def test_normalization(self) -> None:
        for value, expected in (("#abc", "#aabbcc"), ("#AbC", "#aabbcc"),
                                ("#A1B2C3", "#a1b2c3")):
            with self.subTest(value=value):
                self.assertEqual(contrast.parse_color(value), expected)

    def test_swapped_pair(self) -> None:
        self.assertEqual(contrast.contrast_ratio("#123", "#abc"),
                         contrast.contrast_ratio("#abc", "#123"))

    def test_luminance_weights(self) -> None:
        for color, expected in (("#f00", 0.2126), ("#0f0", 0.7152), ("#00f", 0.0722)):
            with self.subTest(color=color):
                self.assertAlmostEqual(contrast.relative_luminance(color), expected)

    def test_linearization_boundary(self) -> None:
        self.assertAlmostEqual(contrast.relative_luminance("#0a0a0a"),
                               (10 / 255) / 12.92)
        self.assertAlmostEqual(contrast.relative_luminance("#0b0b0b"),
                               ((11 / 255 + 0.055) / 1.055) ** 2.4)

    def test_invalid_colors(self) -> None:
        for color in INVALID_COLORS:
            with self.subTest(color=color), self.assertRaises(ValueError):
                contrast.parse_color(color)


class TestContrastCLI(unittest.TestCase):
    def assert_invalid(self, proc: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(len(proc.stderr.splitlines()), 1)
        self.assertTrue(proc.stderr.startswith("error: "))
        self.assertNotIn("parse_color", proc.stderr)

    def test_text_pass(self) -> None:
        proc = check("#ABC", "#000", "4.5")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, "")
        self.assertEqual(proc.stdout,
                         "#aabbcc on #000000: 10.69:1 (minimum 4.5) PASS\n")

    def test_json_schema_and_types(self) -> None:
        for foreground, background, minimum, expected_passes in (
            ("#000", "#FFF", "4.5", True),
            ("#ABC", "#aabbcc", "4.5", False),
        ):
            with self.subTest(foreground=foreground):
                proc = check(foreground, background, minimum, "--json")
                self.assertEqual(proc.returncode, 0 if expected_passes else 1)
                self.assertEqual(proc.stderr, "")
                data = json.loads(proc.stdout)
                self.assertEqual(set(data),
                                 {"foreground", "background", "ratio", "minimum", "passes"})
                for key in ("foreground", "background"):
                    self.assertIs(type(data[key]), str)
                    self.assertRegex(data[key], r"^#[0-9a-f]{6}$")
                self.assertEqual(data["foreground"], contrast.parse_color(foreground))
                self.assertEqual(data["background"], contrast.parse_color(background))
                for key in ("ratio", "minimum"):
                    self.assertIn(type(data[key]), (int, float))
                self.assertEqual(data["ratio"], 21.0 if expected_passes else 1.0)
                self.assertEqual(data["minimum"], 4.5)
                self.assertIs(type(data["passes"]), bool)
                self.assertIs(data["passes"], expected_passes)

    def test_threshold_equality_passes(self) -> None:
        for foreground, background in (("#000", "#fff"), ("#abc", "#abc"),
                                      ("#123", "#abc")):
            ratio = contrast.contrast_ratio(foreground, background)
            with self.subTest(ratio=ratio):
                proc = check(foreground, background, repr(ratio), "--json")
                self.assertEqual(proc.returncode, 0)
                self.assertIs(json.loads(proc.stdout)["passes"], True)

    def test_rounding_cannot_pass_a_failure(self) -> None:
        # Found by searching RGB channels 100 through 129 against white.
        ratio = contrast.contrast_ratio("#647b7d", "#fff")
        self.assertAlmostEqual(ratio, 4.4956498875818385, places=14)
        self.assertLess(ratio, 4.5)
        self.assertEqual(f"{ratio:.2f}", "4.50")
        proc = check("#647b7d", "#fff", "4.5")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stderr, "")
        self.assertEqual(proc.stdout,
                         "#647b7d on #ffffff: 4.50:1 (minimum 4.5) FAIL\n")
        proc = check("#647b7d", "#fff", "4.5", "--json")
        self.assertEqual(proc.returncode, 1)
        data = json.loads(proc.stdout)
        self.assertEqual(data["ratio"], ratio)
        self.assertIs(data["passes"], False)

    def test_invalid_colors_exit_two(self) -> None:
        for color in INVALID_COLORS:
            for pair in ((color, "#fff"), ("#000", color)):
                with self.subTest(pair=pair):
                    self.assert_invalid(check(*pair, "4.5"))

    def test_invalid_minimums_exit_two(self) -> None:
        for minimum in ("nan", "inf", "-inf", "0.5", "22", "1e999", "bad", ""):
            with self.subTest(minimum=minimum):
                self.assert_invalid(check("#000", "#fff", minimum))

    def test_argument_errors_are_one_line(self) -> None:
        valid = ["--foreground", "#000", "--background", "#fff", "--minimum", "4.5"]
        for start in (0, 2, 4):
            with self.subTest(missing=valid[start]):
                self.assert_invalid(run(*(valid[:start] + valid[start + 2:])))
        self.assert_invalid(run(*valid, "--unknown\noption"))
        self.assert_invalid(run(*valid, "--foreground"))


if __name__ == "__main__":
    unittest.main()
