#!/usr/bin/env python3
"""Lock down the legacy slop_check.py CLI with stdlib-only tests.

    python3 -B -m unittest discover -s skills/frontend-aesthetics/tests

Cases follow the implemented patterns and limits, including silent long-line
skips and the lack of JSON output when no UI targets are found.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "slop_check.py"
SUFFIXES = (
    ".astro", ".css", ".html", ".js", ".jsx", ".scss", ".svelte", ".ts",
    ".tsx", ".vue",
)
CLEAN = "<p>Account settings</p>\n"
FAIL_INPUT = "<p>Lorem ipsum</p>\n"
WARN_INPUT = "a { color: #fff; }\n"


def run(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *[str(arg) for arg in args]],
        capture_output=True,
        text=True,
        timeout=30,
    )


def write(root: Path, name: str, content: str | bytes) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    return path


# Each tuple names a rule, its severity, a match, and a legitimate near miss.
# Unicode escapes keep the dash-rule examples out of the source's typography.
RULE_CASES = (
    ("em-dash", "FAIL", "<p>Save\u2014then close</p>", "<p>Save - then close</p>"),
    ("em-dash", "FAIL", "<p>1\u20132 items</p>", "<p>1-2 items</p>"),
    ("banned-palette", "FAIL", "a { color: #F5F1EA; }", "a { color: #f5f1eb; }"),
    ("pure-black-white", "WARN", WARN_INPUT, "a { color: #fafafa; }"),
    ("banned-font", "WARN", "font-family: Instrument_Serif;", "font-family: Georgia;"),
    ("default-font", "WARN", "fontFamily: 'Inter'", "fontFamily: 'Interstate'"),
    ("lucide-icons", "WARN", "import { Check } from 'lucide-react';",
     "import { Check } from './lucide-react';"),
    ("handrolled-icon", "WARN", '<svg><path d="M0 0" /></svg>',
     '<svg aria-hidden="false"><path d="M0 0" /></svg>'),
    ("emoji", "FAIL", "<p>Sunny \u2600</p>", "<p>Sunny</p>"),
    ("h-screen", "FAIL", '<main class="h-screen">', '<main class="min-h-[100dvh]">'),
    ("scroll-listener", "FAIL", "addEventListener('scroll', update);",
     "addEventListener('resize', update);"),
    ("animate-layout-prop", "WARN", "transition: width 200ms;",
     "transition: transform 200ms;"),
    ("flex-percent-math", "WARN", '<div class="w-[calc(50%-1rem)]">',
     '<div class="w-[calc(20rem-1rem)]">'),
    ("custom-cursor", "WARN", "cursor: url(pointer.cur), auto;", "cursor: pointer;"),
    ("gradient-text", "WARN", "background-clip: text;", "background-clip: padding-box;"),
    ("placeholder-comment", "FAIL", "// implement handler", "// Handler validates input."),
    ("lorem-ipsum", "FAIL", FAIL_INPUT, "<p>The word lorem appears in the sample.</p>"),
    ("stock-name", "FAIL", "<p>Acme Inc</p>", "<p>Acmeology</p>"),
    ("filler-verb", "WARN", "<p>Seamlessly</p>", "<p>Seamlessness</p>"),
    ("scroll-cue", "FAIL", "<p>Scroll down</p>", "<p>Scroll position</p>"),
    ("performative-craft", "WARN", "<p>Field notes</p>", "<p>Field notebook</p>"),
    ("fake-precision", "WARN", "<p>99.9% available</p>", "<p>99.8% available</p>"),
    ("hero-version-label", "WARN", "<span>v2.4</span>", "<span>v2.4 release notes</span>"),
    ("section-number-eyebrow", "WARN", "<h2>01 / INDEX</h2>", "<h2>10 / INDEX</h2>"),
    ("placeholder-as-label", "WARN", '<input placeholder="Email">',
     '<input id="email" placeholder="Email">'),
    ("middot-spam", "WARN", "<p>A · B · C</p>", "<p>A · B</p>"),
    ("eyebrow-budget", "FAIL",
     '<section><p class="uppercase tracking-wide">A</p></section>\n'
     '<section><p class="uppercase tracking-wide">B</p></section>\n<section />',
     '<section><p class="uppercase tracking-wide">A</p></section>\n'
     '<section><p class="uppercase tracking-wide">B</p></section>\n<section />\n<section />'),
    ("radius-scale", "WARN",
     "a{border-radius: 3px}\nb{border-radius: 4px}\nc{border-radius: 8px}",
     "a{border-radius: 0}\nb{border-radius: 4px}\nc{border-radius: 8px}\n"
     "d{border-radius: 50%}\ne{border-radius: 999px}\nf{border-radius: 9999px}"),
)


class TestRuleContract(unittest.TestCase):
    def test_each_rule_matches_and_stays_quiet_on_near_miss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for rule, severity, match, near_miss in RULE_CASES:
                for label, content in (("match", match), ("near miss", near_miss)):
                    with self.subTest(rule=rule, case=label, content=content):
                        path = write(Path(tmp), "case.tsx", content)
                        proc = run("--json", path)
                        report = json.loads(proc.stdout)
                        expected = [(rule, severity, 1)] if label == "match" else []
                        self.assertEqual(
                            [(f["rule"], f["severity"], f["line"]) for f in report["findings"]],
                            expected,
                        )
                        self.assertEqual(report["files"], 1)
                        self.assertEqual(proc.returncode, int(label == "match" and severity == "FAIL"))
                        self.assertEqual(proc.stderr, "")


class TestCLIContract(unittest.TestCase):
    def test_json_keys_types_and_file_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = [write(root, "issues.tsx", FAIL_INPUT + WARN_INPUT),
                     write(root, "clean.tsx", CLEAN)]
            proc = run("--json", *paths)
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(proc.stderr, "")
            report = json.loads(proc.stdout)
            self.assertEqual(set(report), {"findings", "files"})
            self.assertIs(type(report["files"]), int)
            self.assertEqual(report["files"], len(paths))
            self.assertIs(type(report["findings"]), list)
            self.assertEqual(len(report["findings"]), 2)
            fields = {"path": str, "line": int, "severity": str, "rule": str, "message": str}
            for finding in report["findings"]:
                with self.subTest(finding=finding):
                    self.assertEqual(set(finding), set(fields))
                    for key, expected_type in fields.items():
                        self.assertIs(type(finding[key]), expected_type)
                    self.assertIn(finding["severity"], {"FAIL", "WARN"})
                    self.assertEqual(finding["path"], str(paths[0]))

    def test_exit_codes_in_text_and_json_modes(self) -> None:
        cases = (
            ("fail", FAIL_INPUT, (), 1),
            ("mixed", FAIL_INPUT + WARN_INPUT, (), 1),
            ("warn", WARN_INPUT, (), 0),
            ("warn-only", FAIL_INPUT, ("--warn-only",), 0),
            ("clean", CLEAN, (), 0),
        )
        with tempfile.TemporaryDirectory() as tmp:
            for label, content, flags, expected in cases:
                for mode in ((), ("--json",)):
                    with self.subTest(case=label, mode=mode):
                        path = write(Path(tmp), "case.tsx", content)
                        proc = run(*mode, *flags, path)
                        self.assertEqual(proc.returncode, expected)
                        self.assertEqual(proc.stderr, "")
                        if label == "warn-only":
                            self.assertIn("FAIL", proc.stdout)

    def test_missing_paths_is_an_argparse_error(self) -> None:
        proc = run()
        self.assertEqual((proc.returncode, proc.stdout), (2, ""))
        self.assertIn("usage:", proc.stderr)

    def test_no_targets_prints_only_stderr_even_with_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write(Path(tmp), "readme.md", FAIL_INPUT)
            for flags in ((), ("--json",), ("--warn-only",), ("--json", "--warn-only")):
                with self.subTest(flags=flags):
                    proc = run(*flags, tmp)
                    self.assertEqual(proc.returncode, 0)
                    self.assertEqual(proc.stdout, "")
                    self.assertEqual(
                        proc.stderr,
                        "no UI files found (looked for: " + " ".join(SUFFIXES) + ")\n",
                    )

    def test_text_finding_layout_sorting_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            last = write(root, "z.tsx", CLEAN + FAIL_INPUT + WARN_INPUT)
            first = write(root, "a.tsx", WARN_INPUT)
            findings = json.loads(run("--json", last, first).stdout)["findings"]
            expected = [
                f'{f["path"]}:{f["line"]}: {f["severity"]}: {f["rule"]}: {f["message"]}'
                for f in sorted(findings, key=lambda f: (f["path"], f["line"]))
            ]
            proc = run(last, first)
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(proc.stdout.splitlines(), expected + ["", "1 fail, 2 warn, 2 file(s)"])

    def test_clean_text_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp), "clean.tsx", CLEAN)
            proc = run(path)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout, "\n0 fail, 0 warn, 1 file(s)\n"
                             "clean \u2014 but a clean lint is a floor, not a ceiling. "
                             "The judgment checks in SKILL.md still apply.\n")
            self.assertEqual(json.loads(run("--json", path).stdout), {"findings": [], "files": 1})


class TestTraversalContract(unittest.TestCase):
    def test_multiple_inputs_preserve_positional_order_in_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            last = write(root, "z.tsx", FAIL_INPUT)
            first = write(root, "a.tsx", FAIL_INPUT)
            report = json.loads(run("--json", last, first).stdout)
            self.assertEqual(report["files"], 2)
            self.assertEqual([f["path"] for f in report["findings"]], [str(last), str(first)])

    def test_directory_recursion_is_sorted_and_filters_suffixes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = [write(root, "z.tsx", FAIL_INPUT), write(root, "a/nested.tsx", FAIL_INPUT)]
            for suffix in reversed(SUFFIXES):
                paths.append(write(root, "m/component" + suffix, FAIL_INPUT))
            for suffix in (".md", ".txt", ".json", ".py", ".TSX", ""):
                write(root, "ignored" + suffix, FAIL_INPUT)
            report = json.loads(run("--json", root).stdout)
            self.assertEqual(report["files"], len(paths))
            self.assertEqual([f["path"] for f in report["findings"]], [str(p) for p in sorted(paths)])

    def test_generated_directories_are_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = write(root, "app.tsx", CLEAN)
            for directory in ("node_modules", ".git", "dist", "build", ".next"):
                with self.subTest(directory=directory):
                    path = write(root, "nested/" + directory + "/deep/issue.tsx", FAIL_INPUT)
                    report = json.loads(run("--json", root).stdout)
                    self.assertEqual(report, {"findings": [], "files": 1})
                    # An explicit file path is still scanned, even in an excluded directory.
                    explicit = json.loads(run("--json", clean, path).stdout)
                    self.assertEqual(explicit["files"], 2)
                    self.assertEqual([f["path"] for f in explicit["findings"]], [str(path)])

    def test_symlinked_file_is_skipped_in_directory_but_scanned_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = write(root, "outside.tsx", FAIL_INPUT)
            write(root, "scan/clean.tsx", CLEAN)
            link = root / "scan" / "linked.tsx"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"File symlinks are unavailable: {exc}")
            self.assertEqual(json.loads(run("--json", root / "scan").stdout),
                             {"findings": [], "files": 1})
            report = json.loads(run("--json", link).stdout)
            self.assertEqual(report["files"], 1)
            self.assertEqual([f["path"] for f in report["findings"]], [str(link)])

    def test_explicit_unsupported_suffix_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ignored = write(root, "ignored.txt", FAIL_INPUT)
            clean = write(root, "clean.tsx", CLEAN)
            self.assertEqual(json.loads(run("--json", ignored, clean).stdout),
                             {"findings": [], "files": 1})
            proc = run("--json", ignored)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout, "")
            self.assertTrue(proc.stderr.startswith("no UI files found (looked for: "))


class TestBoundsAndSafety(unittest.TestCase):
    def test_file_size_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for size, expected in ((1_000_000, []), (1_000_001, [("skipped-large", "WARN", 0)])):
                with self.subTest(rule="skipped-large", size=size):
                    line = b"x" * 1_999 + b"\n"
                    body = line * (size // len(line))
                    path = write(Path(tmp), "large.tsx", body + b"x" * (size - len(body)))
                    proc = run("--json", path)
                    report = json.loads(proc.stdout)
                    self.assertEqual(proc.returncode, 0)
                    self.assertEqual(report["files"], 1)
                    self.assertEqual(
                        [(f["rule"], f["severity"], f["line"]) for f in report["findings"]], expected,
                    )

    def test_unreadable_and_readable_targets(self) -> None:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("Root can read files regardless of their permission bits")
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp), "permissions.tsx", CLEAN)
            original_mode = path.stat().st_mode
            try:
                for mode, expected in ((0, ["unreadable"]), (original_mode, [])):
                    with self.subTest(rule="unreadable", mode=mode):
                        try:
                            path.chmod(mode)
                        except OSError as exc:
                            self.skipTest(f"File permissions cannot be changed: {exc}")
                        if mode == 0:
                            try:
                                path.read_bytes()
                            except PermissionError:
                                pass
                            else:
                                self.skipTest("The platform still permits reading a mode-0 file")
                        proc = run("--json", path)
                        report = json.loads(proc.stdout)
                        self.assertEqual(proc.returncode, 0)
                        self.assertEqual(report["files"], 1)
                        self.assertEqual([f["rule"] for f in report["findings"]], expected)
                        if expected:
                            finding = report["findings"][0]
                            self.assertEqual((finding["path"], finding["line"], finding["severity"]),
                                             (str(path), 0, "WARN"))
                            self.assertTrue(finding["message"].startswith("Could not read: "))
            finally:
                path.chmod(original_mode)

    def test_line_length_boundary_is_silent_above_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for size, expected in ((2_000, ["lorem-ipsum"]), (2_001, [])):
                with self.subTest(size=size):
                    content = "Lorem ipsum" + " " * (size - len("Lorem ipsum"))
                    path = write(Path(tmp), "long.tsx", content + "\n")
                    proc = run("--json", path)
                    report = json.loads(proc.stdout)
                    self.assertEqual(proc.returncode, int(bool(expected)))
                    self.assertEqual(report["files"], 1)
                    self.assertEqual([f["rule"] for f in report["findings"]], expected)
                    self.assertEqual(proc.stderr, "")

    def test_invalid_utf8_is_replaced_and_scan_continues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp), "invalid.tsx", b"\xff\xfe\n<p>Lorem ipsum</p>\n")
            proc = run("--json", path)
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(proc.stderr, "")
            report = json.loads(proc.stdout)
            self.assertEqual(report["files"], 1)
            self.assertEqual([(f["rule"], f["line"]) for f in report["findings"]], [("lorem-ipsum", 2)])

    def test_filename_newline_is_escaped_in_text_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                path = write(Path(tmp), "line\nbreak.tsx", FAIL_INPUT)
            except (OSError, ValueError) as exc:
                self.skipTest(f"The filesystem refuses a filename containing a newline: {exc}")
            proc = run(path)
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(proc.stderr, "")
            lines = proc.stdout.splitlines()
            escaped = str(path).replace("\n", "\\n")
            self.assertEqual(len(lines), 3)
            self.assertTrue(lines[0].startswith(f"{escaped}:1: FAIL: lorem-ipsum: "))
            self.assertEqual(lines[1:], ["", "1 fail, 0 warn, 1 file(s)"])
            self.assertNotIn(str(path), proc.stdout)

    def test_repeated_output_is_identical_and_targets_are_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = [write(root, "z.tsx", FAIL_INPUT + WARN_INPUT),
                     write(root, "nested/a.css", b"\xff\n.x{border-radius: 4px}\r\n")]
            original = {path: path.read_bytes() for path in paths}
            for flags in ((), ("--json",)):
                with self.subTest(flags=flags):
                    first = run(*flags, root)
                    second = run(*flags, root)
                    self.assertEqual(first.returncode, 1)
                    self.assertEqual(second.returncode, first.returncode)
                    self.assertEqual(first.stdout.encode("utf-8"), second.stdout.encode("utf-8"))
                    self.assertEqual(first.stderr, "")
                    self.assertEqual(second.stderr, "")
                    self.assertEqual({path: path.read_bytes() for path in paths}, original)


if __name__ == "__main__":
    unittest.main()
