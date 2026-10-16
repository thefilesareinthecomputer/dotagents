"""Shared body of the four fake CLIs in this folder (claude, codex, agent, agy). Each
records its argv, stdin, cwd and environment as one JSON line to AGENT_REVIEW_FAKE_RECORD
and prints the real CLI's output shape, with the text from AGENT_REVIEW_FAKE_RESPONSES
keyed by CLI name ({"text": ..., "fail": bool}). No model, no network."""

import json
import os
import sys
from pathlib import Path


AGY_MODELS = ["gemini-4-argon-medium", "gemini-4-argon-high", "gemini-4-argon-low", "gemini-3.8-flash-high",
              "gemini-3.8-flash-medium", "gemini-3.8-flash-low", "claude-opus-5-5-high"]


def main(name: str) -> int:
    stdin = sys.stdin.read() if not sys.stdin.isatty() else ""
    spec = json.loads(os.environ.get("AGENT_REVIEW_FAKE_RESPONSES", "{}")).get(name, {})
    if name == "agy" and sys.argv[1:] == ["models"]:
        # the real CLI: a progress line, then one `<slug>\t<label>` per line, every slug naming its level
        print("Fetching available models...")
        for slug in spec.get("models", AGY_MODELS):
            print(f"{slug}\t{slug.replace('-', ' ').title()}")
        return 0
    if name == "agy" and "--model" in sys.argv and sys.argv[sys.argv.index("--model") + 1] not in spec.get("models", AGY_MODELS):
        # the real CLI since 1.3.x: a slug it does not list is refused up front, the message in `error` and on stderr
        wanted = sys.argv[sys.argv.index("--model") + 1]
        msg = f'invalid model selection (--model "{wanted}"): unknown model'
        print(f"error: {msg}", file=sys.stderr)
        print(json.dumps({"conversation_id": "", "status": "ERROR", "response": "", "error": msg, "duration_seconds": 0,
                          "num_turns": 0, "usage": {"input_tokens": 0, "output_tokens": 0}}))
        return 1
    # Probe the write boundary the way a steered CLI would: a write outside the cwd and the
    # temp tree, into the user's home, must be refused by the OS when a profile is applied.
    probe = Path(os.path.expanduser("~")) / f".agent-review-fake-probe-{os.getpid()}"
    try:
        probe.write_text("x")
        write_outside = "allowed"
    except PermissionError:
        write_outside = "denied"
    finally:
        probe.unlink(missing_ok=True)
    if spec.get("write_config"):
        # the real Cursor CLI rewrites its config at startup through a temp file and a rename
        target = Path(spec["write_config"])
        tmp = target.with_name(target.name + ".fake.tmp")
        tmp.write_text('{"permissions": {"allow": ["Shell(rm)"]}, "version": 2}\n')
        os.replace(tmp, target)
    if os.environ.get("AGENT_REVIEW_FAKE_RECORD"):
        with Path(os.environ["AGENT_REVIEW_FAKE_RECORD"]).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"cli": name, "argv": sys.argv[1:], "stdin": stdin, "cwd": os.getcwd(),
                                 "env": sorted(os.environ), "sandboxed": write_outside == "denied",
                                 "write_outside": write_outside}) + "\n")
    text = spec.get("text", f"Review from {name}: the files say so.")
    fail = spec.get("fail")
    if name == "claude":
        model = spec.get("model") or sys.argv[sys.argv.index("--model") + 1]
        print(json.dumps({"type": "result", "subtype": "error" if fail else "success", "is_error": bool(fail),
                          "result": "fake failure" if fail else text, "num_turns": 1,
                          "usage": {"input_tokens": 100, "output_tokens": 20}, "modelUsage": {model: {}}}))
    elif name == "codex":
        print(json.dumps({"type": "thread.started", "thread_id": "t"}))
        if fail:
            print(json.dumps({"type": "error", "message": "fake failure"}))
            return 1
        print(json.dumps({"type": "item.completed", "item": {"id": "i0", "type": "agent_message", "text": text}}))
        print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 20}}))
    elif name == "agent":
        print(json.dumps({"type": "result", "subtype": "error" if fail else "success", "is_error": bool(fail),
                          "result": "fake failure" if fail else text, "usage": {"inputTokens": 100, "outputTokens": 20}}))
    elif name == "agy":
        # on failure the real CLI leaves `response` empty and puts the message in `error`
        print(json.dumps({"status": "ERROR" if fail else "SUCCESS", "response": "" if fail else text,
                          "error": "fake failure" if fail else None,
                          "num_turns": 1, "usage": {"input_tokens": 100, "output_tokens": 20}}))
    return 0
