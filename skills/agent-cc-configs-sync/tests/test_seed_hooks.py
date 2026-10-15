#!/usr/bin/env python3
"""Tests for scripts/seed_hooks.py: the effect oracle, idempotence, hand-added
entries surviving, retirement, first-run adoption, the Codex refusal and the
duplicate-basename check. Stdlib unittest, temp home and temp repo copies.
Run: python3 -m unittest discover -s skills/agent-cc-configs-sync/tests -v
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SCRIPT = HERE.parent / "scripts" / "seed_hooks.py"
ORACLE = json.loads((HERE / "fixtures" / "claude-code-hooks-2026-10-13.json").read_text())["hooks"]

spec = importlib.util.spec_from_file_location("seed_hooks", SCRIPT)
sh = importlib.util.module_from_spec(spec)
sys.modules["seed_hooks"] = sh
spec.loader.exec_module(sh)
hi = sh.load_input_module(REPO)


def run(*args, repo=REPO):
    return subprocess.run([sys.executable, str(SCRIPT), *args, "--repo", str(repo)],
                          text=True, capture_output=True)


def copy_repo(dst: Path) -> Path:
    for rel in ("hooks", "specs/claude-code/hooks"):
        shutil.copytree(REPO / rel, dst / rel, ignore=shutil.ignore_patterns("__pycache__", "tests"))
    shutil.copy2(REPO / "specs/claude-code/settings.json", dst / "specs/claude-code/settings.json")
    return dst


class Render(unittest.TestCase):
    def test_claude_code_equals_the_oracle_in_effect(self):
        entries, _ = sh.load_seeds(REPO, "claude-code")
        rendered, skips, managed = sh.render(entries, "claude-code", hi)
        self.assertEqual(sh.tuples(rendered, hi), sh.tuples(ORACLE, hi))
        self.assertEqual(skips, [])
        self.assertEqual(len(managed), 22)

    def test_codex_wires_nothing_until_tested(self):
        entries, _ = sh.load_seeds(REPO, "codex")
        rendered, skips, managed = sh.render(entries, "codex", hi)
        self.assertEqual(rendered, {})
        self.assertEqual(managed, [])
        self.assertTrue(all("not tested against codex" in s for s in skips))
        self.assertEqual(len(skips), 16)

    def test_partial_projection_and_source_skip(self):
        entries = [
            {"script": "x.sh", "_harnesses": ["codex"], "_folder": REPO,
             "bindings": [{"event": "PreToolUse", "matcher": ["file-read", "shell"]},
                          {"event": "SessionStart", "sources": ["startup", "resume"]},
                          {"event": "SessionStart", "sources": ["compact"]},
                          {"event": "Notification"}]},
        ]
        rendered, skips, managed = sh.render(entries, "codex", hi)
        self.assertEqual(rendered, {
            "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "bash ~/.codex/hooks/x.sh"}]}],
            "SessionStart": [{"matcher": "startup", "hooks": [{"type": "command", "command": "bash ~/.codex/hooks/x.sh"}]}],
        })
        self.assertEqual(managed, ["bash ~/.codex/hooks/x.sh"])
        self.assertEqual(len(skips), 4)
        self.assertIn("file-read has no codex tool; written for Bash", skips[0])
        self.assertIn("source resume not captured for codex; written for startup", skips[1])
        self.assertIn("source compact not captured for codex; binding skipped", skips[2])
        self.assertIn("no Notification event", skips[3])

    def test_binding_with_no_mappable_class_is_skipped(self):
        entries = [{"script": "x.sh", "_harnesses": ["codex"], "_folder": REPO,
                    "bindings": [{"event": "PreToolUse", "matcher": ["search"]}]}]
        rendered, skips, _ = sh.render(entries, "codex", hi)
        self.assertEqual(rendered, {})
        self.assertIn("binding skipped", skips[0])


class Station(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="seed-hooks-"))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.settings = self.home / ".claude" / "settings.json"
        self.hooks = self.home / ".claude" / "hooks"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cc(self, cmd):
        return run(cmd, "--harness", "claude-code", "--home", str(self.home))

    def test_apply_then_clean(self):
        r = self.cc("apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        doc = json.loads(self.settings.read_text())
        self.assertEqual(sh.tuples(doc["hooks"], hi), sh.tuples(ORACLE, hi))
        self.assertTrue((self.hooks / "guard-rm.sh").is_file())
        self.assertTrue((self.hooks / "_require.sh").is_file())
        self.assertTrue((self.hooks / "cmon_nudge.py").is_file())
        self.assertFalse((self.hooks / "manifest.json").exists())
        ledger = json.loads((self.hooks / sh.LEDGER_NAME).read_text())
        self.assertEqual(len(ledger["entries"]), 26)
        self.assertEqual(sh.ledger_tuples(ledger, hi), sh.tuples(ORACLE, hi))
        r = self.cc("plan")
        self.assertIn("clean: nothing to apply", r.stdout)
        r = self.cc("apply")
        self.assertNotIn("applied", r.stdout)

    def test_hand_added_entry_and_other_keys_survive(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(json.dumps({"model": "opus", "hooks": {"PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "bash ~/.claude/hooks/mine.sh"}]}]}}))
        r = self.cc("plan")
        self.assertIn("kept_unmanaged PreToolUse Bash bash ~/.claude/hooks/mine.sh", r.stdout)
        r = self.cc("apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        doc = json.loads(self.settings.read_text())
        self.assertEqual(doc["model"], "opus")
        cmds = [h["command"] for g in doc["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertIn("bash ~/.claude/hooks/mine.sh", cmds)
        self.assertEqual(sh.tuples(doc["hooks"], hi) - sh.tuples(ORACLE, hi),
                         {("PreToolUse", frozenset({"Bash"}), "bash ~/.claude/hooks/mine.sh", None)})

    def test_first_run_adopts_by_path_and_fixes_the_timeout(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(json.dumps({"hooks": {"PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": f"bash {self.home}/.claude/hooks/guard-rm.sh",
                                           "timeout": 99}]}]}}))
        r = self.cc("apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        doc = json.loads(self.settings.read_text())
        guard = [(h["command"], h.get("timeout")) for g in doc["hooks"]["PreToolUse"]
                 for h in g["hooks"] if h["command"].endswith("guard-rm.sh")]
        self.assertEqual(guard, [("bash ~/.claude/hooks/guard-rm.sh", 10)])

    def test_retired_entry_is_reported_then_removed(self):
        self.cc("apply")
        ledger = json.loads((self.hooks / sh.LEDGER_NAME).read_text())
        old = "python3 ~/.claude/hooks/old_gate.py"
        ledger["entries"].append(["PreToolUse", "Bash", old, None])
        ledger["files"].append("old_gate.py")
        (self.hooks / sh.LEDGER_NAME).write_text(json.dumps(ledger))
        (self.hooks / "old_gate.py").write_text("print()\n")
        doc = json.loads(self.settings.read_text())
        doc["hooks"]["PreToolUse"].append({"matcher": "Bash", "hooks": [{"type": "command", "command": old}]})
        self.settings.write_text(json.dumps(doc))
        r = self.cc("plan")
        self.assertIn(f"retired  PreToolUse Bash {old}", r.stdout)
        self.assertIn("retired  old_gate.py", r.stdout)
        r = self.cc("apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        doc = json.loads(self.settings.read_text())
        self.assertNotIn(old, [h["command"] for g in doc["hooks"]["PreToolUse"] for h in g["hooks"]])
        self.assertTrue((self.hooks / "old_gate.py").exists(), "files are reported, never deleted")

    def test_hand_wired_manifest_script_on_another_matcher_survives(self):
        self.settings.parent.mkdir(parents=True)
        mine = {"matcher": "mcp__.*", "hooks": [{"type": "command", "command": "bash ~/.claude/hooks/guard-rm.sh"}]}
        self.settings.write_text(json.dumps({"hooks": {"PreToolUse": [mine]}}))
        r = self.cc("plan")
        self.assertIn("kept_unmanaged PreToolUse mcp__.* bash ~/.claude/hooks/guard-rm.sh", r.stdout)
        self.assertNotIn("retired", r.stdout)
        self.cc("apply")
        doc = json.loads(self.settings.read_text())
        self.assertIn(mine, doc["hooks"]["PreToolUse"])
        r = self.cc("plan")
        self.assertIn("clean: nothing to apply", r.stdout)

    def test_symlinked_destination_is_refused(self):
        self.hooks.mkdir(parents=True)
        (self.hooks / "guard-rm.sh").symlink_to(self.tmp / "elsewhere")
        r = self.cc("apply")
        self.assertEqual(r.returncode, 1)
        self.assertIn("symlink", r.stderr)
        self.assertFalse(self.settings.exists())

    def test_codex_with_nothing_tested_wires_nothing(self):
        r = run("plan", "--harness", "codex", "--home", str(self.home))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("0 managed commands", r.stdout)
        self.assertIn("nothing to wire", r.stdout)
        self.assertNotIn("copy ", r.stdout)
        self.assertNotIn("no capture fixture", r.stdout)
        r = run("apply", "--harness", "codex", "--home", str(self.home))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.home / ".codex").exists())

    def test_codex_apply_refuses_without_its_fixture(self):
        tmp = Path(tempfile.mkdtemp(prefix="seed-hooks-nofix-"))
        try:
            repo = copy_repo(tmp / "repo")
            (repo / "hooks" / "tests" / "fixtures").mkdir(parents=True)
            r = run("apply", "--harness", "codex", "--home", str(self.home), repo=repo)
            self.assertEqual(r.returncode, 3)
            self.assertIn("capture fixture", r.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_codex_features_off_is_reported(self):
        (self.home / ".codex").mkdir()
        (self.home / ".codex" / "config.toml").write_text("[features]\nhooks = false\n")
        r = run("plan", "--harness", "codex", "--home", str(self.home))
        self.assertIn("hooks = false", r.stdout)


class RepoChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="seed-hooks-repo-"))
        self.repo = copy_repo(self.tmp / "repo")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_rules_and_readme_files_are_never_seeded(self):
        # The folder-rules files and any other markdown beside the hooks are
        # documentation for agents editing the repo, never station files.
        for name in ("AGENTS.md", "CLAUDE.md", "README.md"):
            (self.repo / "hooks" / name).write_text("# rules\n")
            (self.repo / "specs/claude-code/hooks" / name).write_text("# rules\n")
        _, files = sh.load_seeds(self.repo, "claude-code")
        names = {f.name for f in files}
        self.assertFalse(names & {"AGENTS.md", "CLAUDE.md", "README.md"}, names)
        self.assertNotIn(sh.LEDGER_NAME, names)
        self.assertIn("_require.sh", names)
        self.assertIn("reject-words.toml", names)

    def test_live_repo_seeds_no_markdown(self):
        _, files = sh.load_seeds(REPO, "claude-code")
        self.assertEqual([f.name for f in files if f.suffix == ".md"], [])

    def test_duplicate_basename_is_refused(self):
        shutil.copy2(self.repo / "hooks" / "_require.sh", self.repo / "specs/claude-code/hooks/_require.sh")
        r = run("render", "--harness", "claude-code", repo=self.repo)
        self.assertEqual(r.returncode, 1)
        self.assertIn("duplicate basename _require.sh", r.stderr)

    def test_script_name_with_a_path_is_refused(self):
        (self.repo / "x").mkdir()
        (self.repo / "x" / "evil.sh").write_text("exit 0\n")
        m = self.repo / "hooks" / "manifest.json"
        data = json.loads(m.read_text())
        data["entries"][0]["script"] = "../x/evil.sh"
        m.write_text(json.dumps(data))
        r = run("render", "--harness", "claude-code", repo=self.repo)
        self.assertEqual(r.returncode, 1)
        self.assertIn("not a plain filename", r.stderr)

    def test_missing_script_is_refused(self):
        m = self.repo / "hooks" / "manifest.json"
        data = json.loads(m.read_text())
        data["entries"][0]["script"] = "ghost.sh"
        m.write_text(json.dumps(data))
        r = run("render", "--harness", "claude-code", repo=self.repo)
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing script ghost.sh", r.stderr)

    def test_seed_regenerates_once_then_no_op(self):
        seed = self.repo / "specs/claude-code/settings.json"
        doc = json.loads(seed.read_text())
        doc["hooks"] = {}
        seed.write_text(json.dumps(doc))
        r = run("seed", "--harness", "claude-code", repo=self.repo)
        self.assertIn("regenerated", r.stdout)
        doc = json.loads(seed.read_text())
        self.assertEqual(sh.tuples(doc["hooks"], hi), sh.tuples(ORACLE, hi))
        r = run("seed", "--harness", "claude-code", repo=self.repo)
        self.assertIn("already matches", r.stdout)
        r = run("seed", "--harness", "codex", repo=self.repo)
        self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main()
