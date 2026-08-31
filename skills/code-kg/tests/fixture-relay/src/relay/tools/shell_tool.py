"""Shell tool: allowlisted commands only, no shell string interpretation."""
from __future__ import annotations

import shlex
import subprocess

from relay.errors import ToolFailed
from relay.tools.registry import tool

_ALLOWED_BINARIES = ("ls", "cat", "grep", "wc", "head", "tail", "git")
_OUTPUT_CAP = 20_000


def _check_command(argv: list[str]) -> None:
    if not argv:
        raise ToolFailed("shell", "empty command", retryable=False)
    if argv[0] not in _ALLOWED_BINARIES:
        raise ToolFailed(
            "shell", f"binary {argv[0]!r} not allowlisted", retryable=False)


def _clip(text: str) -> str:
    if len(text) <= _OUTPUT_CAP:
        return text
    return text[:_OUTPUT_CAP] + f"\n[TRUNCATED at {_OUTPUT_CAP} chars]"


@tool("shell", "Run one allowlisted read-only command", timeout_s=20,
      tags=("local", "read"))
def run_shell(command: str, cwd: str = ".") -> str:
    argv = shlex.split(command)
    _check_command(argv)
    try:
        proc = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired as exc:
        raise ToolFailed("shell", "timed out", retryable=True) from exc
    if proc.returncode != 0:
        raise ToolFailed(
            "shell", _clip(proc.stderr) or f"exit {proc.returncode}",
            retryable=False)
    return _clip(proc.stdout)
