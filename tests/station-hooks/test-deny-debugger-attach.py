#!/usr/bin/env python3
"""Tests for the deny_debugger_attach.py PreToolUse hook.
Target: the repo's hooks/deny_debugger_attach.py by default; HOOK_UNDER_TEST points the run
at a station copy such as ~/.claude/hooks/deny_debugger_attach.py.
Run: python3 tests/station-hooks/test-deny-debugger-attach.py   (or via unittest discover)

Contract: a shell command whose program is lldb, gdb, debugserver or DevToolsSecurity exits 2
with the reason on stderr; a command that only mentions them exits 0. Fails open.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

TARGET = Path(os.environ.get("HOOK_UNDER_TEST") or Path(__file__).resolve().parents[2] / "hooks" / "deny_debugger_attach.py")


def run(command: str, tool: str = "Bash") -> subprocess.CompletedProcess:
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "session_id": "t",
               "tool_input": {"command": command}}
    return subprocess.run([sys.executable, str(TARGET)], input=json.dumps(payload),
                          capture_output=True, text=True, timeout=10)


class DebuggerCase(unittest.TestCase):
    BLOCKED = [
        'timeout 180 lldb --batch -p 75541 -o "command script import /tmp/scan.py" -o scan',
        "lldb -p 1234",
        "lldb --attach-name Python",
        "/usr/bin/lldb -p 1",
        "sudo lldb -p 1",
        "env FOO=1 lldb",
        "nohup gdb -p 99 &",
        "git status && gdb ./a.out",
        "cd /tmp; debugserver localhost:1234 --attach=99",
        "DevToolsSecurity -enable",
        "DevToolsSecurity -status",
        "X=1 timeout -s KILL 30 lldb",
        "xcrun lldb --version",
        "cat <<EOF | lldb -p 1\nscript\nEOF",
        "(gdb -p 1)",
        "cat <<<X\nlldb -p 1\nX",  # a here-string has no body to leave out
        "echo 1 | xargs lldb -p",
        "arch -arm64 lldb",
    ]
    ALLOWED = [
        "grep -n lldb file.py",
        "echo gdb",
        "which lldb",
        "ls /usr/bin/lldb",
        "git commit -m 'never run lldb on a live process'",
        "python3 -m unittest",
        "rg 'lldb|gdb' src",
        # quoted text and here-documents that hold a separator or start a line with the word
        'git commit -m "fix\n\ngdb was mentioned on its own line"',
        'grep -n "a; lldb -p 1" notes.md',
        'echo "(gdb) prompt text"',
        "python3 script.py <<EOF\nlldb is named on a here-document line\nEOF",
        "python3 - <<'PY'\ncommands = ['lldb -p 1']\nPY",
    ]

    def test_debugger_programs_are_blocked(self):
        for cmd in self.BLOCKED:
            with self.subTest(cmd=cmd):
                p = run(cmd)
                self.assertEqual(p.returncode, 2, p.stderr)
                self.assertIn("Blocked:", p.stderr)
                self.assertIn("`!`", p.stderr)

    def test_mentions_pass(self):
        for cmd in self.ALLOWED:
            with self.subTest(cmd=cmd):
                p = run(cmd)
                self.assertEqual(p.returncode, 0, p.stderr)

    def test_a_large_command_is_fast(self):
        """Unclosed here-document openings once made the scan quadratic: 64 KB took six seconds."""
        import time
        for cmd in ("cat <<A\n" * 3500, "x = y << z\n" * 2800, "echo ok\n" * 40000):
            with self.subTest(size=len(cmd)):
                started = time.monotonic()
                self.assertEqual(run(cmd).returncode, 0)
                self.assertLess(time.monotonic() - started, 2)

    def test_a_missing_sibling_module_allows_the_command(self):
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            alone = Path(folder) / TARGET.name
            shutil.copy(TARGET, alone)
            payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "lldb -p 1"}}
            p = subprocess.run([sys.executable, str(alone)], input=json.dumps(payload),
                               capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 0)
        self.assertIn("command allowed", p.stderr)

    def test_other_tools_pass(self):
        self.assertEqual(run("lldb -p 1", tool="Read").returncode, 0)

    def test_fails_open_on_bad_input(self):
        p = subprocess.run([sys.executable, str(TARGET)], input="not json",
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 0)


if __name__ == "__main__":
    unittest.main()
