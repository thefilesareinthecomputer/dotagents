#!/usr/bin/env python3
"""Fake panel member for the council test suite, in the agent-review fake-harness shape:
`fake_member.py <harness> <brief-path> <stage-dir> <model> <effort>`, printing one JSON
object {text, usage, model, exit_code, error}.

AGENT_REVIEW_FAKE_RESPONSES is a JSON object keyed by harness: {"stage1": text, "stage2":
"<labels in rank order, e.g. CAB>" | "invalid" | null, "chair": text, "fail": bool}.
The stage is read from the brief's first heading. A stage-2 ranking is built from the
labels the brief shows, so the fake never knows who wrote what.
"""

import json
import os
import re
import sys
from pathlib import Path


def main():
    harness, brief_path, stage, model, effort = sys.argv[1:6]
    brief_path = Path(brief_path)
    spec = json.loads(os.environ.get("AGENT_REVIEW_FAKE_RESPONSES", "{}")).get(harness, {})
    brief = brief_path.read_text(encoding="utf-8")
    if os.environ.get("AGENT_REVIEW_FAKE_RECORD"):
        with Path(os.environ["AGENT_REVIEW_FAKE_RECORD"]).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"member": harness, "brief": str(brief_path), "stage": stage, "model": model,
                                 "effort": effort, "cwd": os.getcwd()}) + "\n")
    if spec.get("fail"):
        print(json.dumps({"text": None, "usage": None, "model": model, "exit_code": 4, "error": "fake failure"}))
        return 0
    usage = {"input_tokens": 100, "output_tokens": 20}
    if brief.startswith("# Chair"):
        text = spec.get("chair", f"Synthesis by {harness}.")
    elif brief.startswith("# Blind review"):
        labels = re.findall(r"^## Response ([A-J])$", brief, re.M)
        order = spec.get("stage2")
        if order == "invalid":
            text = "I rank them: B, A.\n\n```json\n{\"ranking\": [\"Z\"]}\n```"
        elif order is None:
            text = "No ranking block here."
        else:
            ranking = [c for c in order if c in labels] + [c for c in labels if c not in order]
            # A task skill's own summary block follows the ranking, as the real CLIs do.
            text = ("Review paragraphs.\n\n```json\n" + json.dumps({"ranking": ranking, "rationale": {c: f"because {c}" for c in labels},
                                                                 "errors_found": "none", "disagreements": "none"}) + "\n```\n\n"
                    "```json\n{\"summary\": \"ranked\", \"files_changed\": [], \"notes\": \"\", \"blocked_on\": \"\"}\n```")
    else:
        text = spec.get("stage1", f"Answer from {harness}: the files say so.")
    print(json.dumps({"text": text, "usage": usage, "model": model, "exit_code": 0, "error": None}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
