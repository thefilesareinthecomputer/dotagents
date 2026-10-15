#!/usr/bin/env python3
"""Tests for scripts/harness_probe.py: fake binaries on a temp PATH and a temp
HOME, so the suite passes with no harness installed and never reaches the
network. Run: python3 -m unittest discover -s skills/agent-cc-configs-sync/tests -v
"""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "harness_probe.py"

FAKES = {
    "claude": 'echo "9.1.0 (Claude Code)"',
    "codex": 'echo "codex-cli 0.9.1"',
    "cursor-agent": 'echo "2099.01.02-abc1234"',
    "copilot": 'case "$1" in skill) printf "Personal skills:\\n  skill-authoring - house rules\\n";; *) echo "GitHub Copilot CLI 1.2.3.";; esac',
    "goose": 'case "$1" in skills) printf "Name | Description\\nskill-authoring | house rules\\n";; *) echo " 1.60.0";; esac',
    "pi": 'echo "1.2.0"',
    "agy": 'echo "1.4.0"',
}


def write_fake(bin_dir: Path, name: str, body: str) -> None:
    p = bin_dir / name
    p.write_text("#!/bin/sh\n" + body + "\n")
    p.chmod(p.stat().st_mode | stat.S_IXUSR)


class Probe(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="harness-probe-"))
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.home = self.tmp / "home"
        self.home.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_probe(self, *args):
        env = {"PATH": str(self.bin), "HOME": str(self.home)}
        return subprocess.run([sys.executable, str(SCRIPT), *args],
                              text=True, capture_output=True, env=env, timeout=60)

    def rows(self, *args):
        r = self.run_probe("--json", *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return {row["harness"]: row for row in json.loads(r.stdout)}

    def test_nothing_installed_is_a_row_not_an_error(self):
        rows = self.rows()
        self.assertEqual(len(rows), 7)
        for row in rows.values():
            self.assertEqual(row["version"], "not installed")
            self.assertEqual(row["config_home_present"], False)

    def test_versions_are_parsed_from_each_binary_shape(self):
        for name, body in FAKES.items():
            write_fake(self.bin, name, body)
        rows = self.rows()
        self.assertEqual(rows["claude-code"]["version"], "9.1.0")
        self.assertEqual(rows["codex"]["version"], "0.9.1")
        self.assertEqual(rows["cursor"]["version"], "2099.01.02-abc1234")
        self.assertEqual(rows["copilot"]["version"], "1.2.3")
        self.assertEqual(rows["goose"]["version"], "1.60.0")
        self.assertEqual(rows["pi"]["version"], "1.2.0")
        self.assertEqual(rows["antigravity"]["version"], "1.4.0")

    def test_canaries_report_discovery_per_kind(self):
        for name, body in FAKES.items():
            write_fake(self.bin, name, body)
        skills = self.home / ".claude" / "skills"
        skills.mkdir(parents=True)
        (skills / "skill-authoring").symlink_to(self.tmp)
        (self.home / ".gemini" / "config").mkdir(parents=True)
        rows = self.rows()
        self.assertEqual(rows["copilot"]["canary"], "lists skill-authoring")
        self.assertEqual(rows["goose"]["canary"], "lists skill-authoring")
        self.assertEqual(rows["claude-code"]["canary"], "symlink present")
        self.assertEqual(rows["antigravity"]["canary"], "skills.json absent")
        for h in ("codex", "cursor", "pi"):
            self.assertEqual(rows[h]["canary"], "no listing")
        (self.home / ".gemini" / "config" / "skills.json").write_text("{}")
        self.assertEqual(self.rows()["antigravity"]["canary"], "skills.json present")

    def test_listing_without_the_skill_is_reported(self):
        write_fake(self.bin, "copilot", 'echo "Personal skills:"')
        self.assertEqual(self.rows()["copilot"]["canary"], "does not list skill-authoring")
        self.assertEqual(self.rows("--skill", "code-kg")["copilot"]["canary"], "does not list code-kg")

    def test_listing_matches_whole_names_on_stdout_only(self):
        # A rejected skill named on stderr, or a longer name sharing the
        # prefix, is not a hit.
        write_fake(self.bin, "copilot", 'echo "skill-authoring-extra - other"; echo "skill-authoring: rejected" >&2')
        self.assertEqual(self.rows()["copilot"]["canary"], "does not list skill-authoring")

    def test_failed_listing_is_reported_not_counted(self):
        write_fake(self.bin, "copilot", 'case "$1" in skill) echo "skill-authoring"; exit 1;; *) echo "GitHub Copilot CLI 1.2.3.";; esac')
        self.assertEqual(self.rows()["copilot"]["canary"], "listing failed")

    def test_skill_argument_is_validated(self):
        r = self.run_probe("--skill", "")
        self.assertNotEqual(r.returncode, 0)
        r = self.run_probe("--skill", "Bad Name")
        self.assertNotEqual(r.returncode, 0)

    def test_text_table_shows_config_homes_with_a_tilde(self):
        r = self.run_probe()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(str(self.home), r.stdout)
        self.assertIn("~/.config/goose", r.stdout)

    def test_config_homes_derive_from_home(self):
        (self.home / ".config" / "goose").mkdir(parents=True)
        (self.home / ".pi" / "agent").mkdir(parents=True)
        rows = self.rows()
        self.assertTrue(rows["goose"]["config_home_present"])
        self.assertTrue(rows["pi"]["config_home_present"])
        self.assertFalse(rows["codex"]["config_home_present"])
        self.assertTrue(rows["goose"]["config_home"].startswith(str(self.home)))

    def test_text_table_has_one_line_per_harness(self):
        write_fake(self.bin, "pi", FAKES["pi"])
        r = self.run_probe()
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = [l for l in r.stdout.splitlines() if l.strip()]
        self.assertEqual(len(lines), 8)  # header plus seven rows
        self.assertIn("pi", r.stdout)
        self.assertIn("1.2.0", r.stdout)


if __name__ == "__main__":
    unittest.main()
