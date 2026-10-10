#!/usr/bin/env python3
"""Fake `sandbox-exec` for the test suite: records the profile it was handed to
FAKE_SANDBOX_RECORD, then runs the wrapped command unconfined. The real profile is
tested separately against the real sandbox-exec where it exists."""

import os
import subprocess
import sys
from pathlib import Path


def main():
    argv = sys.argv[1:]
    if len(argv) < 3 or argv[0] != "-f":
        print("fake sandbox-exec: expected -f <profile> <cmd> ...", file=sys.stderr)
        return 64
    profile = Path(argv[1])
    if os.environ.get("FAKE_SANDBOX_RECORD"):
        Path(os.environ["FAKE_SANDBOX_RECORD"]).write_text(profile.read_text())
    return subprocess.call(argv[2:])


if __name__ == "__main__":
    sys.exit(main())
