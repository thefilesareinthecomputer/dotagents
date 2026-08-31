"""Parsing model output: fenced blocks, tool calls, and honest failure.

Model text is untrusted input. Every parser here returns a value or a
ParseFailure - never an exception - because a malformed completion is an
ordinary outcome, not a crash.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

_FENCE_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
_TOOL_CALL_RE = re.compile(
    r"^\s*CALL\s+([a-z_][\w-]*)\s*\((.*)\)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class ParseFailure:
    reason: str
    excerpt: str

    def describe(self) -> str:
        return f"{self.reason}: {self.excerpt[:120]!r}"


@dataclass(frozen=True)
class ToolCall:
    tool: str
    args: dict


def extract_fences(text: str, language: str = "") -> list[str]:
    """All fenced blocks, optionally filtered by info string."""
    blocks = []
    for info, body in _FENCE_RE.findall(text):
        if not language or info == language:
            blocks.append(body.rstrip("\n"))
    return blocks


def extract_json_block(text: str) -> dict | ParseFailure:
    """The first json fence that parses to an object; failure says why."""
    fences = extract_fences(text, "json") or extract_fences(text)
    if not fences:
        return ParseFailure("no fenced block found", text)
    last_error = ""
    for fence in fences:
        try:
            value = json.loads(fence)
        except json.JSONDecodeError as exc:
            last_error = str(exc)
            continue
        if isinstance(value, dict):
            return value
        last_error = f"parsed {type(value).__name__}, wanted object"
    return ParseFailure(f"no fence parsed: {last_error}", fences[0])


def parse_tool_call(text: str) -> ToolCall | ParseFailure:
    """CALL tool(k=v, ...) lines, the fixture's toy tool-call syntax."""
    m = _TOOL_CALL_RE.search(text)
    if m is None:
        return ParseFailure("no CALL line", text)
    tool_name, raw_args = m.group(1), m.group(2).strip()
    args: dict = {}
    if raw_args:
        for pair in _split_args(raw_args):
            if "=" not in pair:
                return ParseFailure("argument without =", pair)
            key, _, value = pair.partition("=")
            args[key.strip()] = _coerce(value.strip())
    return ToolCall(tool=tool_name, args=args)


def _split_args(raw: str) -> list[str]:
    parts, depth, current = [], 0, []
    for ch in raw:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def _coerce(value: str):
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value.strip("'\"")
