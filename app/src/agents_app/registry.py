"""Mission-control activity registry. SPEC-GROUP-CHAT-V1 G8 (STORY-000079).

In-process and observational only: the claude lane reports the stream-json
events it already parses, this module folds them into one row per live
turn - state, current tool, transient subagents (detected by the
parent_tool_use_id field the 2026-08-27 spike confirmed on assistant/user
events originating inside an Agent/Task subagent) - and GET /agents
serves the snapshot. Rows die with their turn; a restart clears the lot.
"""

import time

# key -> row; key is (conversation_id, actor) where actor is the seat id
# ("main" for the two-party agent), suffixed ":prep" for a G10 prep turn.
_rows: dict[tuple[str, str], dict] = {}

_SUBAGENT_TOOLS = {"Agent", "Task"}


def begin(conversation_id: str, actor: str, name: str, cwd: str,
          model: str, prep: bool = False) -> None:
    _rows[(conversation_id, actor)] = {
        "conversation_id": conversation_id,
        "actor": actor,
        "name": name,
        "cwd": cwd,
        "model": model,
        "prep": prep,
        "state": "starting",
        "tool": "",
        "started": time.time(),
        "kb_file": "",
        "tokens": 0,
        "subagents": {},  # tool_use id -> {state, tool, started}
    }


def event(conversation_id: str, actor: str, raw: dict) -> None:
    """Fold one stream-json event into the actor's row. Unknown keys or
    a missing row are ignored - observation must never break a turn."""
    row = _rows.get((conversation_id, actor))
    if row is None:
        return
    kind = raw.get("type")
    parent = raw.get("parent_tool_use_id")
    if parent:
        sub = row["subagents"].setdefault(
            parent, {"state": "working", "tool": "", "started": time.time()})
        _fold(sub, raw, kind)
        return
    _fold(row, raw, kind)
    if kind == "user":
        # a tool_result for a subagent's spawning tool_use ends that row
        for block in (raw.get("message") or {}).get("content", []):
            if isinstance(block, dict) and block.get("type") == "tool_result":
                row["subagents"].pop(block.get("tool_use_id"), None)
    if kind == "result":
        usage = raw.get("usage") or {}
        row["tokens"] = sum(usage.get(k, 0) for k in
                            ("input_tokens", "output_tokens"))
        row["state"] = "idle"


def _fold(row: dict, raw: dict, kind: str | None) -> None:
    if kind == "system":
        if row["state"] == "starting":
            row["state"] = "thinking"
    elif kind == "stream_event":
        inner = (raw.get("event") or {})
        if inner.get("type") == "content_block_delta":
            row["state"] = "generating"
    elif kind == "assistant":
        tools = [block for block in
                 (raw.get("message") or {}).get("content", [])
                 if isinstance(block, dict) and block.get("type") == "tool_use"]
        if tools:
            row["state"] = "tools"
            row["tool"] = tools[-1].get("name", "tool")
        else:
            row["state"] = "generating"
    elif kind == "user":
        row["tool"] = ""
        row["state"] = "thinking"


def kb(conversation_id: str, actor: str, path: str) -> None:
    row = _rows.get((conversation_id, actor))
    if row is not None:
        row["kb_file"] = path


def end(conversation_id: str, actor: str) -> None:
    _rows.pop((conversation_id, actor), None)


def snapshot() -> list[dict]:
    """Rows for GET /agents, oldest first, subagents as nested lists."""
    out = []
    for row in sorted(_rows.values(), key=lambda r: r["started"]):
        item = {k: v for k, v in row.items() if k != "subagents"}
        item["subagents"] = [
            {"id": sid, **sub} for sid, sub in row["subagents"].items()]
        out.append(item)
    return out
