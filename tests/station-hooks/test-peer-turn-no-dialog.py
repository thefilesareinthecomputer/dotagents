#!/usr/bin/env python3
"""Tests for the peer_turn_no_dialog.py PreToolUse hook.
Target: the repo's specs/claude-code/hooks/peer_turn_no_dialog.py by default; HOOK_UNDER_TEST
points the run at a station copy such as ~/.claude/hooks/peer_turn_no_dialog.py.
Run: python3 tests/station-hooks/test-peer-turn-no-dialog.py   (or via unittest discover)

Contract: a dialog tool is denied when the turn was started by anything but the user (the
latest main-thread row with an origin is not `human`), and allowed otherwise. Fails open.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TARGET = Path(os.environ.get("HOOK_UNDER_TEST") or Path(__file__).resolve().parents[2] / "specs" / "claude-code" / "hooks" / "peer_turn_no_dialog.py")


def row(content, origin: dict | None = None, sidechain: bool = False, meta: bool = False) -> str:
    r = {"type": "user", "isSidechain": sidechain, "message": {"role": "user", "content": content}}
    if origin is not None:
        r["origin"] = origin
    if meta:
        r["isMeta"] = True
    return json.dumps(r)


def human(text: str) -> str:
    return row(text, {"kind": "human"})


def peer(text: str = "hello") -> str:
    return row("Another Claude session sent a message:\n<cross-session-message from=\"uds:x\">\n"
               + text + "\n</cross-session-message>", {"kind": "peer", "name": "other"}, meta=True)


def task() -> str:
    return row("<task-notification>\n<task-id>b1</task-id>\n</task-notification>",
               {"kind": "task-notification"})


def tool_result() -> str:
    return row([{"type": "tool_result", "content": "ok"}])


def assistant(text: str = "ok") -> str:
    return json.dumps({"type": "assistant", "message": {"role": "assistant",
                                                        "content": [{"type": "text", "text": text}]}})


class DialogCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.transcript = Path(self.tmp.name) / "t.jsonl"

    def write(self, *lines: str) -> None:
        self.transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def run_hook(self, payload: dict | None = None) -> tuple[int, dict | None]:
        payload = payload or {"hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion",
                              "tool_input": {}, "transcript_path": str(self.transcript)}
        p = subprocess.run([sys.executable, str(TARGET)], input=json.dumps(payload),
                           capture_output=True, text=True, timeout=10)
        out = json.loads(p.stdout) if p.stdout.strip() else None
        return p.returncode, out

    def assertDenied(self) -> None:
        code, out = self.run_hook()
        self.assertEqual(code, 0)
        self.assertIsNotNone(out)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def assertAllowed(self) -> None:
        code, out = self.run_hook()
        self.assertEqual(code, 0)
        self.assertIsNone(out)

    def test_peer_started_turn_is_denied(self):
        self.write(human("earlier"), assistant(), peer(), assistant("reading"), tool_result())
        self.assertDenied()

    def test_task_notification_turn_is_denied(self):
        self.write(human("earlier"), assistant(), task(), tool_result())
        self.assertDenied()

    def test_human_turn_is_allowed(self):
        self.write(peer(), assistant(), human("pick one for me"), assistant(), tool_result())
        self.assertAllowed()

    def test_skill_load_and_interrupt_rows_do_not_change_the_origin(self):
        self.write(peer(), row("Base directory for this skill: /x", meta=True),
                   row([{"type": "text", "text": "[Request interrupted by user for tool use]"}]))
        self.assertDenied()

    def test_sidechain_rows_are_ignored(self):
        self.write(human("go"), assistant(), row("sub prompt", {"kind": "peer"}, sidechain=True))
        self.assertAllowed()

    def test_row_without_origin_judged_by_its_opening(self):
        self.write(human("go"), row("<task-notification>\n<task-id>x</task-id>"))
        self.assertDenied()

    def test_reason_names_the_cause_and_the_alternative(self):
        self.write(peer())
        _, out = self.run_hook()
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("another session's message", reason)
        self.assertIn("SendMessage", reason)

    def test_fails_open(self):
        self.assertEqual(self.run_hook({"hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion",
                                        "transcript_path": str(self.transcript)}), (0, None))
        self.assertEqual(self.run_hook({"hook_event_name": "PreToolUse"}), (0, None))
        self.write("not json", "{", peer())
        self.assertDenied()
        p = subprocess.run([sys.executable, str(TARGET)], input="garbage",
                           capture_output=True, text=True, timeout=10)
        self.assertEqual((p.returncode, p.stdout), (0, ""))

    def test_large_transcript_is_fast(self):
        import time
        lines = [human("x" * 200), assistant("y" * 200)] * 20000 + [peer()]
        self.write(*lines)
        start = time.monotonic()
        self.assertDenied()
        self.assertLess(time.monotonic() - start, 3.0)


if __name__ == "__main__":
    unittest.main()
