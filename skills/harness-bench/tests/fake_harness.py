#!/usr/bin/env python3
"""Fake harness for the harness-bench tests: argv is <model> <brief>, behavior comes from
FAKE_HARNESS_MODE, and it reaches its "model" through OLLAMA_HOST like a real harness.

  solve        copy FAKE_HARNESS_SOLUTION over the working directory
  oos          write README.md (out of scope), then solve
  trap-revert  change app/config.py, wait, restore it, then solve
  symlink      replace FAKE_HARNESS_SYMLINK with a link to /etc/hosts
  escape       try a write under FAKE_HARNESS_REAL_HOME, a read of FAKE_HARNESS_READ and a
               direct connection to FAKE_HARNESS_DIRECT_PORT; report each as ok or denied
  orphan       start a sleeping child tagged FAKE_HARNESS_ORPHAN, then solve
FAKE_HARNESS_ANSWER, if set, becomes the final text.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def call_model(model):
    body = {"model": model, "stream": True, "tools": [{"type": "function", "function": {"name": "shell"}}],
            "messages": [{"role": "system", "content": "fake system prompt"}, {"role": "user", "content": "go"}]}
    req = urllib.request.Request(f"http://{os.environ['OLLAMA_HOST']}/v1/chat/completions",
                                 data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


def attempt(fn):
    try:
        fn()
        return "ok"
    except OSError:
        return "denied"


def main():
    model = sys.argv[1]
    mode = os.environ.get("FAKE_HARNESS_MODE", "solve")
    report = {"turns": 1, "tool_calls": 1, "final": ""}
    call_model(model)
    if mode == "oos":
        Path("README.md").write_text("changed\n")
    if mode == "trap-revert":
        p = Path("app/config.py")
        old = p.read_text()
        p.write_text("TIMEOUT = 30\n")
        time.sleep(2.0)  # several watcher polls even on a loaded machine
        p.write_text(old)
    if mode == "symlink":
        target = Path(os.environ["FAKE_HARNESS_SYMLINK"])
        target.unlink()
        target.symlink_to("/etc/hosts")
    if mode == "escape":
        report["final"] = json.dumps({
            "write_home": attempt(lambda: Path(os.environ["FAKE_HARNESS_REAL_HOME"], ".harness-bench-escape").write_text("x")),
            "read_home": attempt(lambda: Path(os.environ["FAKE_HARNESS_READ"]).read_bytes()),
            "direct": attempt(lambda: socket.create_connection(("127.0.0.1", int(os.environ["FAKE_HARNESS_DIRECT_PORT"])),
                                                              timeout=2).close()),
        })
    if mode == "orphan":
        subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", os.environ["FAKE_HARNESS_ORPHAN"]])
    sol = os.environ.get("FAKE_HARNESS_SOLUTION")
    if mode in ("solve", "oos", "trap-revert", "orphan") and sol:
        shutil.copytree(sol, ".", dirs_exist_ok=True)
    if os.environ.get("FAKE_HARNESS_ANSWER"):
        report["final"] = os.environ["FAKE_HARNESS_ANSWER"]
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
