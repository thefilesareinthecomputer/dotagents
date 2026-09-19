#!/usr/bin/env python3
"""Tests for the cmon_nudge.py SessionStart/UserPromptSubmit hook.
Target: ~/.claude/hooks/cmon_nudge.py (seeded from SPEC-CLAUDE-CODE.md §8).
Run: python3 tests/station-hooks/test-cmon-nudge.py   (or via unittest discover)

Contract: advisory only, exit 0 on every path. SessionStart always injects the
heads-up. UserPromptSubmit injects a nudge only when the previous main-thread
reply exceeds the threshold, counting words outside fenced code. Fails open.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path.home() / ".claude" / "hooks" / "cmon_nudge.py"
SEED = Path(__file__).resolve().parent.parent.parent / "specs" / "claude-code" / "hooks" / "cmon_nudge.py"
TARGET = HOOK if HOOK.is_file() else SEED


def row(kind: str, content, sidechain: bool = False) -> str:
    return json.dumps({"type": kind, "isSidechain": sidechain,
                       "message": {"role": kind, "content": content}})


def user(text: str, **kw) -> str:
    return row("user", text, **kw)


def tool_result() -> str:
    return row("user", [{"type": "tool_result", "content": "ok"}])


def assistant(text: str, **kw) -> str:
    return row("assistant", [{"type": "text", "text": text}], **kw)


def words(n: int) -> str:
    return " ".join(f"w{i}" for i in range(n))


class NudgeCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.transcript = Path(self.tmp.name) / "t.jsonl"

    def write(self, *lines: str) -> None:
        self.transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def run_hook(self, event: str, env: dict | None = None, path: str | None = None) -> tuple[int, dict | None]:
        payload = {"hook_event_name": event,
                   "transcript_path": path if path is not None else str(self.transcript)}
        full_env = {**os.environ, **(env or {})}
        p = subprocess.run([sys.executable, str(TARGET)], input=json.dumps(payload),
                           capture_output=True, text=True, env=full_env)
        self.assertEqual(p.returncode, 0, p.stderr)
        out = p.stdout.strip()
        return p.returncode, (json.loads(out) if out else None)

    def context(self, out: dict | None) -> str:
        self.assertIsNotNone(out, "expected a nudge, got silence")
        return out["hookSpecificOutput"]["additionalContext"]


class TestSessionStart(NudgeCase):
    def test_heads_up_names_the_threshold_and_the_skill(self) -> None:
        _code, out = self.run_hook("SessionStart")
        ctx = self.context(out)
        self.assertIn("150 words", ctx)
        self.assertIn("/cmon", ctx)
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SessionStart")

    def test_threshold_override_is_reflected(self) -> None:
        _code, out = self.run_hook("SessionStart", env={"CMON_WORDS": "80"})
        self.assertIn("80 words", self.context(out))


class TestUserPromptSubmit(NudgeCase):
    def test_short_reply_is_silent(self) -> None:
        self.write(user("hi"), assistant(words(40)))
        _code, out = self.run_hook("UserPromptSubmit")
        self.assertIsNone(out)

    def test_long_reply_nudges_with_the_count(self) -> None:
        self.write(user("hi"), assistant(words(200)))
        _code, out = self.run_hook("UserPromptSubmit")
        ctx = self.context(out)
        self.assertIn("200 words", ctx)
        self.assertIn("cmon", ctx)

    def test_fenced_code_is_not_counted(self) -> None:
        body = words(40) + "\n```\n" + words(300) + "\n```\n"
        self.write(user("hi"), assistant(body))
        _code, out = self.run_hook("UserPromptSubmit")
        self.assertIsNone(out)

    def test_a_turn_split_by_tool_calls_is_summed(self) -> None:
        self.write(user("hi"), assistant(words(90)), tool_result(), assistant(words(90)))
        _code, out = self.run_hook("UserPromptSubmit")
        self.assertIn("180 words", self.context(out))

    def test_only_the_last_turn_counts(self) -> None:
        self.write(user("a"), assistant(words(400)), user("b"), assistant(words(20)))
        _code, out = self.run_hook("UserPromptSubmit")
        self.assertIsNone(out)

    def test_current_prompt_already_appended_does_not_hide_the_reply(self) -> None:
        self.write(user("a"), assistant(words(200)), user("b"))
        _code, out = self.run_hook("UserPromptSubmit")
        self.assertIn("200 words", self.context(out))

    def test_sidechain_rows_are_ignored(self) -> None:
        self.write(user("a"), assistant(words(20)), assistant(words(500), sidechain=True))
        _code, out = self.run_hook("UserPromptSubmit")
        self.assertIsNone(out)

    def test_threshold_override(self) -> None:
        self.write(user("a"), assistant(words(60)))
        _code, out = self.run_hook("UserPromptSubmit", env={"CMON_WORDS": "50"})
        self.assertIn("limit 50", self.context(out))


class TestFailsOpen(NudgeCase):
    def test_missing_transcript_is_silent(self) -> None:
        _code, out = self.run_hook("UserPromptSubmit", path=str(self.transcript / "nope"))
        self.assertIsNone(out)

    def test_malformed_lines_are_skipped(self) -> None:
        self.write("{not json", user("a"), assistant(words(200)), "also not json")
        _code, out = self.run_hook("UserPromptSubmit")
        self.assertIn("200 words", self.context(out))

    def test_unknown_event_is_silent(self) -> None:
        self.write(user("a"), assistant(words(200)))
        _code, out = self.run_hook("PreToolUse")
        self.assertIsNone(out)

    def test_garbage_stdin_exits_zero(self) -> None:
        p = subprocess.run([sys.executable, str(TARGET)], input="nope", capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
