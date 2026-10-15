#!/usr/bin/env python3
"""Tests for hooks/_input.py against the captured fixtures.
Run: python3 -m unittest discover -s hooks/tests -p 'test_*.py' -v
"""
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "_input.py"
spec = importlib.util.spec_from_file_location("hook_input", SRC)
hi = importlib.util.module_from_spec(spec)
sys.modules["hook_input"] = hi
spec.loader.exec_module(hi)

FIXTURES = {p.stem: json.loads(p.read_text()) for p in (HERE / "fixtures").glob("*.json")}


class ClaudeCodeFixture(unittest.TestCase):
    fx = FIXTURES["claude-code"]
    env = {k: "1" for k in fx["env_keys"]}

    def events(self):
        for payload in self.fx["events"]:
            yield payload, hi.parse_event(payload, environ=self.env)

    def test_harness_detected_from_environment(self):
        for _, ev in self.events():
            self.assertEqual(ev.harness, "claude-code")

    def test_every_captured_event_name_is_known(self):
        for payload, _ in self.events():
            self.assertIn(payload["hook_event_name"], hi.EVENTS["claude-code"])

    def test_tool_classes(self):
        seen = {}
        for _, ev in self.events():
            if ev.tool_name:
                seen[ev.tool_name] = ev.tool_class
        self.assertEqual(seen, {"Bash": "shell", "Write": "file-write", "Read": "file-read", "Edit": "file-write"})

    def test_shell_command_and_paths(self):
        for _, ev in self.events():
            if ev.tool_class == "shell":
                self.assertTrue(ev.command)
                self.assertEqual(ev.paths, [])
            elif ev.tool_class in ("file-write", "file-read"):
                self.assertEqual(ev.command, "")
                self.assertEqual(ev.paths, ["/work/cc-ws/note.txt"])

    def test_write_and_edit_texts(self):
        texts = {(ev.event, ev.tool_name): (ev.new_text, ev.old_text) for _, ev in self.events() if ev.tool_name}
        self.assertEqual(texts[("PreToolUse", "Write")], ("hello", ""))
        self.assertEqual(texts[("PreToolUse", "Edit")], ("hello world", "hello"))
        self.assertEqual(texts[("PreToolUse", "Read")], ("", ""))

    def test_session_start_source(self):
        starts = [ev for _, ev in self.events() if ev.event == "SessionStart"]
        self.assertEqual([s.source for s in starts], ["startup"])
        self.assertIn("startup", hi.SESSION_SOURCES["claude-code"])


class Tables(unittest.TestCase):
    def test_tool_class_patterns(self):
        cases = {"MultiEdit": "file-write", "NotebookEdit": "file-write", "Grep": "search", "Glob": "search",
                 "Agent": "agent", "Workflow": "agent", "mcp__playwright__browser_click": "mcp",
                 "WebSearch": "other", "": "other"}
        for name, cls in cases.items():
            self.assertEqual(hi.tool_class("claude-code", name), cls, name)

    def test_expand_matcher_keeps_class_order_and_reports_unmapped(self):
        m, unmapped = hi.expand_matcher("claude-code", ["file-read", "file-write", "shell", "search"])
        self.assertEqual(m, "Read|Write|Edit|MultiEdit|NotebookEdit|Update|Create|Bash|Grep|Glob")
        self.assertEqual(unmapped, [])
        m, unmapped = hi.expand_matcher("codex", ["file-read", "shell"])
        self.assertEqual(m, "Bash")
        self.assertEqual(unmapped, ["file-read"])

    def test_matcher_set_ignores_order(self):
        self.assertEqual(hi.matcher_set("Read|Edit|Write"), hi.matcher_set("Write|Read|Edit"))
        self.assertEqual(hi.matcher_set(None), frozenset())

    def test_multi_edit_paths_and_texts(self):
        ev = hi.parse_event({"hook_event_name": "PreToolUse", "tool_name": "MultiEdit",
                             "tool_input": {"file_path": "/a.md", "edits": [
                                 {"old_string": "x", "new_string": "y"}, {"old_string": "p", "new_string": "q"}]}},
                            harness="claude-code")
        self.assertEqual(ev.paths, ["/a.md"])
        self.assertEqual((ev.new_text, ev.old_text), ("y\nq", "x\np"))

    def test_unknown_harness_and_bad_payload(self):
        self.assertEqual(hi.detect_harness({}), "unknown")
        self.assertEqual(hi.detect_harness({"CODEX_HOME": "/x"}), "codex")
        ev = hi.read_event(io.StringIO("not json"), harness="claude-code")
        self.assertEqual((ev.harness, ev.event, ev.tool_class), ("claude-code", "", ""))

    def test_codex_tables(self):
        self.assertEqual(hi.SESSION_SOURCES["codex"], ["startup"])
        self.assertNotIn("file-read", hi.TOOL_CLASSES["codex"])
        self.assertEqual(hi.tool_class("codex", "apply_patch"), "file-write")

    def test_parse_apply_patch(self):
        paths, new, old = hi.parse_apply_patch(
            "*** Begin Patch\n*** Update File: a/b.py\n@@\n-x = 1\n+x = 2\n*** Delete File: c.txt\n*** End Patch")
        self.assertEqual(paths, ["a/b.py", "c.txt"])
        self.assertEqual((new, old), ("x = 2", "x = 1"))
        self.assertEqual(hi.parse_apply_patch(""), ([], "", ""))


class CodexFixture(unittest.TestCase):
    fx = FIXTURES["codex"]

    def events(self):
        for payload in self.fx["events"]:
            yield payload, hi.parse_event(payload, environ={})

    def test_harness_detected_from_payload_with_empty_environment(self):
        self.assertEqual(self.fx["env_keys"], [])
        for _, ev in self.events():
            self.assertEqual(ev.harness, "codex")

    def test_every_captured_event_name_is_known(self):
        for payload, _ in self.events():
            self.assertIn(payload["hook_event_name"], hi.EVENTS["codex"])

    def test_tool_classes(self):
        seen = {ev.tool_name: ev.tool_class for _, ev in self.events() if ev.tool_name}
        self.assertEqual(seen, {"Bash": "shell", "apply_patch": "file-write"})

    def test_shell_events_keep_command_and_no_paths(self):
        shells = [ev for _, ev in self.events() if ev.tool_class == "shell"]
        self.assertEqual([s.command for s in shells][:2], ["ls -la", "ls -la"])
        self.assertTrue(all(s.paths == [] for s in shells))

    def test_apply_patch_is_an_edit_not_a_command(self):
        edits = [ev for _, ev in self.events() if ev.tool_class == "file-write" and ev.event == "PreToolUse"]
        self.assertEqual([e.command for e in edits], ["", ""])
        self.assertEqual([e.paths for e in edits], [["/work/codex-ws/note2.txt"]] * 2)
        self.assertEqual([(e.new_text, e.old_text) for e in edits], [("hello", ""), ("hello world", "hello")])

    def test_session_start_source(self):
        starts = [ev for _, ev in self.events() if ev.event == "SessionStart"]
        self.assertEqual([s.source for s in starts], ["startup"])

    def test_inherited_claude_environment_does_not_hide_codex(self):
        claude_env = {"CLAUDECODE": "1", "CLAUDE_PROJECT_DIR": "/x"}
        for payload in self.fx["events"]:
            self.assertEqual(hi.parse_event(payload, environ=claude_env).harness, "codex", payload["hook_event_name"])
        for payload in FIXTURES["claude-code"]["events"]:
            self.assertEqual(hi.parse_event(payload, environ=claude_env).harness, "claude-code")

    def test_hook_harness_variable_overrides(self):
        self.assertEqual(hi.detect_harness({"HOOK_HARNESS": "codex", "CLAUDECODE": "1"}, {"prompt_id": "x"}), "codex")
        self.assertEqual(hi.detect_harness({"HOOK_HARNESS": "nonsense"}, {"prompt_id": "x"}), "claude-code")

    def test_patch_headers_are_trimmed_and_split_on_newline_only(self):
        paths, _, _ = hi.parse_apply_patch("*** Begin Patch\n  *** Update File: secret.env  \n+x\n*** End Patch")
        self.assertEqual(paths, ["secret.env"])
        line_sep = chr(0x2028)  # splitlines() would break here; Codex splits on newline only
        paths, _, _ = hi.parse_apply_patch("*** Update File: ok.txt" + line_sep + ".env\r\n+x")
        self.assertEqual(paths, ["ok.txt" + line_sep + ".env"])
        # A body line starting with + is never a header. A line that is a header
        # once trimmed is reported even when it could be hunk context, because a
        # guard that sees one path too many denies, and one too few allows.
        paths, _, _ = hi.parse_apply_patch("*** Update File: a\n+*** Update File: evil\n *** Delete File: z")
        self.assertEqual(paths, ["a", "z"])

    def test_relative_patch_paths_resolve_against_cwd(self):
        ev = hi.parse_event({"hook_event_name": "PreToolUse", "tool_name": "apply_patch", "turn_id": "t",
                             "cwd": "/w/repo", "tool_input": {"command": "*** Update File: ../private/b.txt\n+x"}})
        self.assertEqual(ev.paths, ["/w/private/b.txt"])
        ev = hi.parse_event({"hook_event_name": "PreToolUse", "tool_name": "apply_patch", "turn_id": "t",
                             "cwd": "/w/repo", "tool_input": {}})
        self.assertEqual((ev.tool_class, ev.paths), ("file-write", []))

    def test_claude_code_payload_is_not_mistaken_for_codex(self):
        cc = FIXTURES["claude-code"]["events"][2]
        self.assertEqual(hi.detect_harness({}, cc), "claude-code")


if __name__ == "__main__":
    unittest.main()
