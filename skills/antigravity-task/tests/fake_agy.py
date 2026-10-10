#!/usr/bin/env python3
"""Fake `agy` binary for the antigravity-task test suite. Never touches the network.

Behavior is selected by FAKE_AGY_MODE:
  clean       edit only allowed files
  edit        edit one allowed file and one disallowed file, add a new allowed file
  sleep       sleep for FAKE_AGY_SLEEP seconds (default 60), never finish
  error       print an ERROR envelope and exit 1
  denied      exit 0 with SUCCESS and an empty response, the headless auto-deny shape
  child-sleep spawn a child that sleeps, then sleep
  commit      like `edit`, then stage and commit inside the worktree
  pathspec    create a file whose name is git pathspec magic
  symlink     swap an allowed file for a symlink out of the repo
  readonly    write nothing, answer in the response

FAKE_AGY_ARGV, if set, receives the argv, the environment and the cwd as JSON.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def envelope(response, status="SUCCESS", error=None):
    out = {"conversation_id": "fake-conv", "status": status, "response": response,
           "duration_seconds": 0.5, "num_turns": 1,
           "usage": {"input_tokens": 10, "output_tokens": 5, "thinking_tokens": 1, "cache_read_tokens": 0, "total_tokens": 16}}
    if error:
        out["error"] = error
    sys.stdout.write(json.dumps(out))
    sys.stdout.flush()


def main():
    mode = os.environ.get("FAKE_AGY_MODE", "clean")
    if os.environ.get("FAKE_AGY_ARGV"):
        Path(os.environ["FAKE_AGY_ARGV"]).write_text(
            json.dumps({"argv": sys.argv, "env": dict(os.environ), "cwd": os.getcwd()}))
    ws = Path(os.getcwd())

    if mode == "sleep":
        time.sleep(float(os.environ.get("FAKE_AGY_SLEEP", "60")))
        return 0
    if mode == "child-sleep":
        subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        time.sleep(120)
        return 0
    if mode == "error":
        envelope("", status="ERROR", error="fake failure")
        return 1
    if mode == "denied":
        print("jetski: no output produced - a tool required the write_file permission", file=sys.stderr)
        envelope("")
        return 0
    if mode == "readonly":
        envelope("The answer is 42.\n\n```json\n{\"summary\": \"answered\", \"files_changed\": [], \"notes\": \"\", \"blocked_on\": \"\"}\n```")
        return 0
    if mode == "pathspec":
        (ws / ":(exclude)sneaky.txt").write_text("out of scope\n")
        (ws / "src" / "allowed.py").write_text("def f():\n    return 2\n")
        envelope("done")
        return 0
    if mode == "symlink":
        target = ws / "src" / "allowed.py"
        target.unlink()
        target.symlink_to("/etc/hosts")
        envelope("done")
        return 0
    if mode == "gitdir":
        real = (ws / ".git").read_text().split("gitdir: ", 1)[1].strip()
        (ws / ".git").write_text(f"gitdir: {Path(real).parent.parent}\n")
        (ws / "src" / "allowed.py").write_text("def f():\n    return 2\n")
        envelope("done")
        return 0

    (ws / "src" / "allowed.py").write_text("def f():\n    return 2\n")
    (ws / "src" / "new_allowed.py").write_text("NEW = True\n")
    if mode in ("edit", "commit"):
        (ws / "src" / "other.py").write_text("TOUCHED = True\n")
        (ws / "README.md").write_text("changed\n")
    if mode == "commit":
        subprocess.run(["git", "add", "-A"], cwd=ws, check=True)
        subprocess.run(["git", "-c", "user.email=f@f", "-c", "user.name=f", "commit", "-qm", "sneaky"], cwd=ws, check=True)
    result = {"summary": "fake edit", "files_changed": ["src/allowed.py", "src/new_allowed.py"], "notes": "", "blocked_on": ""}
    envelope("I made the change.\n\n```json\n" + json.dumps(result) + "\n```")
    return 0


if __name__ == "__main__":
    sys.exit(main())
