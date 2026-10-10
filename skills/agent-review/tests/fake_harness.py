#!/usr/bin/env python3
"""Fake harness for the agent-review test suite. Invoked as
`fake_harness.py <harness> <brief-path> <stage-dir> <model> <effort>`, prints one JSON
object: {text, usage, model, exit_code, error}.

AGENT_REVIEW_FAKE_RESPONSES is a JSON object keyed by harness: {"text": ..., "fail": bool}.
AGENT_REVIEW_FAKE_RECORD, if set, receives one JSON line per call with the argv and cwd.
"""

import json
import os
import sys
from pathlib import Path


def main():
    harness, brief_path, stage, model, effort = sys.argv[1:6]
    spec = json.loads(os.environ.get("AGENT_REVIEW_FAKE_RESPONSES", "{}")).get(harness, {})
    if os.environ.get("AGENT_REVIEW_FAKE_RECORD"):
        with Path(os.environ["AGENT_REVIEW_FAKE_RECORD"]).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"harness": harness, "brief": brief_path, "stage": stage, "model": model,
                                 "effort": effort, "cwd": os.getcwd(),
                                 "brief_text": Path(brief_path).read_text(encoding="utf-8")}) + "\n")
    if spec.get("fail"):
        print(json.dumps({"text": None, "usage": None, "model": model, "exit_code": 4, "error": "fake failure"}))
        return 0
    text = spec.get("text", f"Review from {harness} on {model}: the files say so.")
    print(json.dumps({"text": text, "usage": {"input_tokens": 100, "output_tokens": 20}, "model": model,
                      "exit_code": 0, "error": None}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
