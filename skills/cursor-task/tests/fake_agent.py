#!/usr/bin/env python3
"""Fake Cursor `agent` binary for the cursor-task test suite. Never touches the network.

Behavior is selected by FAKE_AGENT_MODE:
  clean       edit only allowed files
  edit        edit one allowed file and one disallowed file, add a new allowed file
  sleep       sleep for FAKE_AGENT_SLEEP seconds (default 60), never finish
  error       print an error envelope and exit 1
  child-sleep spawn a child that sleeps, then sleep (tests process-group kill)
  commit      like `edit`, then stage and commit inside the worktree
  pathspec    create a file whose name is git pathspec magic
  symlink     swap an allowed file for a symlink out of the repo
  readonly    write nothing, answer in the result text

FAKE_AGENT_ARGV, if set, receives the argv, the environment and the cwd as JSON.
FAKE_AGENT_ORPHAN, if set, starts a sleeping child tagged with its value that outlives
the fake (tests the process-group kill after a normal exit).
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


def envelope(text, is_error=False):
    sys.stdout.write(json.dumps({"type": "result", "subtype": "error" if is_error else "success",
                                 "is_error": is_error, "duration_ms": 12, "result": text,
                                 "session_id": "fake-session",
                                 "usage": {"inputTokens": 10, "outputTokens": 5, "cacheReadTokens": 0,
                                           "cacheWriteTokens": 0}}))
    sys.stdout.flush()


def main():
    mode = os.environ.get("FAKE_AGENT_MODE", "clean")
    if os.environ.get("FAKE_AGENT_ARGV"):
        Path(os.environ["FAKE_AGENT_ARGV"]).write_text(
            json.dumps({"argv": sys.argv, "env": dict(os.environ), "cwd": os.getcwd()}))
    ws = Path(arg_after("--workspace") or ".")
    if os.environ.get("FAKE_AGENT_WRITE_CONFIG"):
        # The real CLI rewrites its config at startup through a temp file and a rename.
        target = Path(os.environ["FAKE_AGENT_WRITE_CONFIG"])
        tmp = target.with_name(target.name + ".fake.tmp")
        tmp.write_text('{"permissions": {"allow": ["Shell(rm)"]}, "version": 2}\n')
        os.replace(tmp, target)
    if os.environ.get("FAKE_AGENT_ORPHAN"):
        subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", os.environ["FAKE_AGENT_ORPHAN"]])

    if mode == "sleep":
        time.sleep(float(os.environ.get("FAKE_AGENT_SLEEP", "60")))
        return 0
    if mode == "child-sleep":
        subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        time.sleep(120)
        return 0
    if mode == "error":
        envelope("fake failure", is_error=True)
        return 1
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
        # Point the worktree's gitdir at the real repository, then edit an allowed file.
        real = (ws / ".git").read_text().split("gitdir: ", 1)[1].strip()
        main_git = str(Path(real).parent.parent)  # <repo>/.git/worktrees/<name> -> <repo>/.git
        (ws / ".git").write_text(f"gitdir: {main_git}\n")
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
        subprocess.run(["git", "-c", "user.email=f@f", "-c", "user.name=f", "commit", "-qm", "sneaky"],
                       cwd=ws, check=True)
    result = {"summary": "fake edit", "files_changed": ["src/allowed.py", "src/new_allowed.py"],
              "notes": "", "blocked_on": ""}
    envelope("I made the change.\n\n```json\n" + json.dumps(result) + "\n```")
    return 0


if __name__ == "__main__":
    sys.exit(main())
