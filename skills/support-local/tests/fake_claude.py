#!/usr/bin/env python3
"""A stand-in for the claude CLI: prints one result JSON the way `claude -p --output-format json` does.

FAKE_CLAUDE_MODEL sets the model it claims to have used; FAKE_CLAUDE_RESULT overrides the result text;
FAKE_CLAUDE_ARGS, when set, receives the argv it was called with (appended, one JSON line per call).
FAKE_CLAUDE_MODE picks a failure: "max_turns" (an error result with no JSON answer), "crash" (exit 1, no JSON),
"hang" (sleep past any timeout). FAKE_CLAUDE_FAIL_FIRST, a counter file path, makes only the first call fail in that mode.
"""

import json
import os
import sys
import time

if os.environ.get("FAKE_CLAUDE_ARGS"):
    with open(os.environ["FAKE_CLAUDE_ARGS"], "a") as f:
        f.write(json.dumps(sys.argv[1:]) + "\n")
if os.environ.get("FAKE_CLAUDE_ENV"):
    # the working directory and the seat variable the runner gave this worker, one JSON line per call
    with open(os.environ["FAKE_CLAUDE_ENV"], "a") as f:
        f.write(json.dumps({"cwd": os.getcwd(), "seat": os.environ.get("AGENTS_APP_SEAT"),
                            "entries": sorted(os.listdir(os.getcwd()))}) + "\n")
model = os.environ.get("FAKE_CLAUDE_MODEL", "claude-haiku-5-5")
mode = os.environ.get("FAKE_CLAUDE_MODE", "")
counter = os.environ.get("FAKE_CLAUDE_FAIL_FIRST")
if counter and mode:
    seen = 0
    if os.path.exists(counter):
        seen = int(open(counter).read() or 0)
    open(counter, "w").write(str(seen + 1))
    if seen > 0:
        mode = ""
if mode == "hang":
    time.sleep(60)
if mode == "crash":
    print("fatal: something broke", file=sys.stderr)
    sys.exit(1)
if mode == "max_turns":
    print(json.dumps({"type": "result", "subtype": "error_max_turns", "is_error": True, "num_turns": 15, "duration_ms": 9000,
                      "result": "I searched the hooks folder and found guard-private.sh but ran out of turns before verifying lines.",
                      "total_cost_usd": 0.02, "usage": {"input_tokens": 20, "output_tokens": 900, "cache_read_input_tokens": 3000,
                                                        "cache_creation_input_tokens": 500},
                      "modelUsage": {model: {"inputTokens": 20, "outputTokens": 900, "cacheReadInputTokens": 3000,
                                             "cacheCreationInputTokens": 500, "costUSD": 0.02}}}))
    sys.exit(0)
answer = os.environ.get("FAKE_CLAUDE_RESULT") or json.dumps({
    "goal": "where is the exit code table", "answer": "In the script header.", "answerable": True,
    "evidence": [{"claim": "EXIT_OK is defined", "ref": "a.py:1", "quote": "EXIT_OK = 0", "verified": True},
                 {"claim": "a claim with a bad line", "ref": "a.py:999", "quote": "EXIT_OK = 0", "verified": True}],
    "coverage": "searched a.py", "local_calls": 2, "stop_reason": "answered"})
print("[some warning line the CLI may print]")
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": answer, "num_turns": 3, "duration_ms": 4200,
                  "total_cost_usd": 0.0123, "usage": {"input_tokens": 1200, "output_tokens": 300, "cache_read_input_tokens": 500,
                                                      "cache_creation_input_tokens": 2000,
                                                      "iterations": [{"input_tokens": 2, "cache_read_input_tokens": 400, "cache_creation_input_tokens": 100},
                                                                     {"input_tokens": 5, "cache_read_input_tokens": 1600, "cache_creation_input_tokens": 95}]},
                  "modelUsage": {model: {"inputTokens": 1200, "outputTokens": 300, "cacheReadInputTokens": 500,
                                         "cacheCreationInputTokens": 2000, "costUSD": 0.0123}}}))
