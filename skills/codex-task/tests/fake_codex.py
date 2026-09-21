#!/usr/bin/env python3
"""Fake `codex` binary for the codex-task test suite. Never touches the network.

Behavior is selected by FAKE_CODEX_MODE:
  edit        edit one allowed file and one disallowed file, add a new allowed file
  clean       edit only allowed files
  sleep       sleep for FAKE_CODEX_SLEEP seconds (default 60), never finish
  error       emit an error item and exit 1
  noread      never read stdin, then behave like `clean`
  child-sleep spawn a child that sleeps, then sleep (tests process-group kill)
  commit      like `edit`, then stage and commit inside the worktree
  bigprompt   never read stdin and sleep (tests a stdin write that cannot drain)

FAKE_CODEX_ARGV, if set, receives the argv and the inherited environment as
JSON - the environment is what the scrub test reads.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def arg_after(flag):
    argv = sys.argv
    return argv[argv.index(flag) + 1] if flag in argv else None


def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main():
    mode = os.environ.get("FAKE_CODEX_MODE", "clean")
    if os.environ.get("FAKE_CODEX_ARGV"):
        Path(os.environ["FAKE_CODEX_ARGV"]).write_text(
            json.dumps({"argv": sys.argv, "codex_home": os.environ.get("CODEX_HOME"),
                        "env": dict(os.environ)}))
    ws = Path(arg_after("-C") or ".")
    last = arg_after("-o")

    if mode == "bigprompt":
        time.sleep(float(os.environ.get("FAKE_CODEX_SLEEP", "120")))
        return 0
    if mode != "noread":
        _ = sys.stdin.read()  # consume the brief

    emit({"type": "thread.started", "thread_id": "fake"})
    emit({"type": "turn.started"})

    if mode == "sleep":
        time.sleep(float(os.environ.get("FAKE_CODEX_SLEEP", "60")))
        return 0
    if mode == "child-sleep":
        subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        time.sleep(120)
        return 0
    if mode == "error":
        emit({"type": "item.completed", "item": {"type": "error", "message": "fake failure"}})
        return 1

    if mode == "pathspec":
        # A filename that is git pathspec magic. Harvest feeds changed names
        # back to `git diff` as pathspecs, where a leading ':' is not a name.
        (ws / ":(exclude)sneaky.txt").write_text("out of scope\n")
        (ws / "src" / "allowed.py").write_text("def f():\n    return 2\n")
        return 0

    if mode == "symlink":
        # Keep an allowed NAME but change its MODE to a symlink pointing out
        # of the repo. The allowlist filters names, not modes.
        target = ws / "src" / "allowed.py"
        target.unlink()
        target.symlink_to("/etc/hosts")
        return 0

    (ws / "src" / "allowed.py").write_text("def f():\n    return 2\n")
    (ws / "src" / "new_allowed.py").write_text("NEW = True\n")
    if mode in ("edit", "commit"):
        (ws / "src" / "other.py").write_text("TOUCHED = True\n")
        (ws / "README.md").write_text("changed\n")
    if mode == "commit":
        subprocess.run(["git", "add", "-A"], cwd=ws, check=True)
        subprocess.run(["git", "-c", "user.email=f@f", "-c", "user.name=f", "commit", "-qm", "sneaky"],
                       cwd=ws, check=True)

    result = {"summary": "fake edit", "files_changed": ["src/allowed.py", "src/new_allowed.py"],
              "notes": "", "blocked_on": ""}
    emit({"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(result)}})
    emit({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}})
    if last:
        Path(last).write_text(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
