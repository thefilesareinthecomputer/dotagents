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


class RemoteControl(unittest.TestCase):
    """SPEC.md invariant 7: the column reads config files and an injected
    process list, so these never depend on what runs on the test machine."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="harness-probe-rc-"))
        self.home = self.tmp
        sys.path.insert(0, str(SCRIPT.parent))
        import harness_probe
        self.hp = harness_probe

    def tearDown(self):
        import shutil
        sys.path.remove(str(SCRIPT.parent))
        shutil.rmtree(self.tmp, ignore_errors=True)

    def row(self, name):
        return next(r for r in self.hp.ROWS if r.harness == name)

    def remote(self, name, procs=(), env=None):
        return self.hp.remote_of(self.row(name), self.home, list(procs), env or {})

    def write(self, rel, text):
        p = self.home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def test_claude_code_needs_both_the_setting_and_the_env(self):
        self.assertTrue(self.remote("claude-code").startswith("ON"))
        self.write(".claude/settings.json", json.dumps({"disableRemoteControl": True}))
        self.assertIn("DISABLE_TELEMETRY", self.remote("claude-code"))
        self.write(".claude/settings.json", json.dumps({"disableRemoteControl": True, "env": {"DISABLE_TELEMETRY": "1"}}))
        self.assertEqual(self.remote("claude-code"), "off")

    def test_codex_needs_the_daemon_off_analytics_off_and_no_daemon_process(self):
        self.write(".codex/config.toml", "[features]\ndaemon_auto_start = false\n\n[analytics]\nenabled = false\n")
        self.assertEqual(self.remote("codex"), "off")
        self.assertIn("daemon running", self.remote("codex", procs=["/x/bin/codex app-server --listen unix:// --managed-daemon"]))
        self.write(".codex/config.toml", "[analytics]\nenabled = false\n")
        self.assertIn("daemon_auto_start", self.remote("codex"))

    def test_codex_reads_the_toml_structure_not_a_line_pattern(self):
        # The key under another table, a comment, or a dotted form must not pass as off.
        self.write(".codex/config.toml", "[profiles.x]\ndaemon_auto_start = false\n[analytics]\nenabled = false\n")
        self.assertIn("daemon_auto_start", self.remote("codex"))
        self.write(".codex/config.toml", "# daemon_auto_start = false\n[analytics]\nenabled = false\n")
        self.assertIn("daemon_auto_start", self.remote("codex"))
        self.write(".codex/config.toml", "features.daemon_auto_start = false\nanalytics.enabled = false\n")
        self.assertEqual(self.remote("codex"), "off")

    def test_goose_last_key_wins_and_the_env_overrides(self):
        self.write(".config/goose/config.yaml", "GOOSE_TELEMETRY_ENABLED: false\nGOOSE_TELEMETRY_ENABLED: true\n")
        self.assertTrue(self.remote("goose").startswith("ON"))
        self.assertEqual(self.remote("goose", env={"GOOSE_TELEMETRY_ENABLED": "false"}), "off")

    def test_copilot_matches_exact_tokens(self):
        self.assertTrue(self.remote("copilot", procs=["copilot --no-remote-export --remote -p hi"]).startswith("ON"))
        self.assertIn("per session", self.remote("copilot", procs=["copilot --remote-thing -p hi"]))

    def test_antigravity_launch_agent_is_judged_by_content_in_either_folder(self):
        self.write("Library/LaunchAgents/com.example.unrelated.plist", "<string>/usr/local/bin/agy</string>")
        self.assertIn("launch agent", self.remote("antigravity"))
        (self.home / "Library/LaunchAgents/com.example.unrelated.plist").unlink()
        self.write("Library/LaunchAgents/com.agy.lookalike.plist", "<string>/usr/local/bin/other</string>")
        self.assertTrue(self.remote("antigravity").startswith("off"))
        self.assertTrue(self.remote("antigravity", procs=["/x/bin/not-agy remote-control start"]).startswith("off"))

    def test_malformed_json_sections_do_not_crash(self):
        self.write(".claude/settings.json", json.dumps({"disableRemoteControl": True, "env": "oops"}))
        self.assertIn("DISABLE_TELEMETRY", self.remote("claude-code"))
        self.write(".cursor/cli-config.json", json.dumps({"privacyCache": "oops"}))
        self.assertTrue(self.remote("cursor").startswith("ON"))

    def test_cursor_is_on_when_a_cloud_worker_runs_or_ghost_mode_is_off(self):
        self.write(".cursor/cli-config.json", json.dumps({"privacyCache": {"ghostMode": True}}))
        self.assertEqual(self.remote("cursor"), "off")
        self.assertIn("worker", self.remote("cursor", procs=["cursor-agent worker --pool x"]))
        self.write(".cursor/cli-config.json", json.dumps({"privacyCache": {"ghostMode": False}}))
        self.assertTrue(self.remote("cursor").startswith("ON"))

    def test_copilot_has_only_a_per_session_switch(self):
        self.assertIn("per session", self.remote("copilot"))
        self.assertTrue(self.remote("copilot", procs=["copilot --remote -p hi"]).startswith("ON"))
        self.assertIn("per session", self.remote("copilot", procs=["copilot --no-remote-export -p hi"]))

    def test_goose_pi_and_antigravity(self):
        self.write(".config/goose/config.yaml", "GOOSE_MODEL: x\nGOOSE_TELEMETRY_ENABLED: false\n")
        self.assertEqual(self.remote("goose"), "off")
        self.assertIn("serve", self.remote("goose", procs=["goose serve --port 1"]))
        self.assertTrue(self.remote("pi").startswith("ON"))
        self.assertEqual(self.remote("pi", env={"PI_TELEMETRY": "0"}), "off")
        self.assertTrue(self.remote("antigravity").startswith("off"))
        self.assertTrue(self.remote("antigravity", procs=["agy remote-control start"]).startswith("ON"))
        self.write("Library/LaunchAgents/com.google.antigravity.remote.plist", "<string>/opt/agy</string>")
        self.assertIn("launch agent", self.remote("antigravity"))

    def test_the_column_reaches_the_json_and_the_table(self):
        env = {"PATH": str(self.tmp), "HOME": str(self.home)}
        r = subprocess.run([sys.executable, str(SCRIPT), "--json"], text=True, capture_output=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(all("remote_control" in row for row in json.loads(r.stdout)))
        r = subprocess.run([sys.executable, str(SCRIPT)], text=True, capture_output=True, env=env, timeout=60)
        self.assertIn("remote control", r.stdout.splitlines()[0])


if __name__ == "__main__":
    unittest.main()
