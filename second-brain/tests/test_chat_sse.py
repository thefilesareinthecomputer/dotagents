"""chat.sse encoder tests. STORY-000035 (M4).

Frames are checked through the same discipline ui/kb-graph-hud.js's
parseSse applies: split on the blank line, one event: and one data: line
per frame.
"""

import inspect
import json
import urllib.parse

from second_brain import chat


def _parse(frame: bytes) -> tuple[str, str]:
    text = frame.decode()
    assert text.endswith("\n\n"), "frame must end with a blank line"
    event_line, data_line = text[:-2].split("\n")
    assert event_line.startswith("event: ")
    assert data_line.startswith("data: ")
    return event_line[7:], data_line[6:]


def test_json_events_carry_their_exact_field_sets():
    cases = {
        "iteration_start": {"iteration": 1},
        "tool_call": {"tool": "read_file", "args": {"filename": "a.md"}},
        "tool_executing": {"tool": "read_file", "args": {}, "started": 1.0},
        "tool_done": {"tool": "read_file", "elapsed_ms": 12, "executed": True},
        "tool_result": {"tool": "read_file", "result": "text", "info": {}},
        "kb_file": {"path": "KNOWLEDGE-BASE/a.md", "score": 0.9},
        "heartbeat": {"phase": "tools", "iteration": 1, "label": "Working"},
        "token_usage": {"used": 120, "total": 200000, "phase": "turn"},
        "done": {},
    }
    for event, payload in cases.items():
        name, data = _parse(chat.sse(event, payload))
        assert name == event
        assert json.loads(data) == payload


def test_thinking_and_token_percent_encoded():
    raw = "two\nlines & 100% special chars"
    for event in ("thinking", "token"):
        name, data = _parse(chat.sse(event, raw))
        assert name == event
        assert "\n" not in data
        assert urllib.parse.unquote(data) == raw


def test_error_is_plain_single_line_text():
    _, data = _parse(chat.sse("error", "boom\nsecond line"))
    assert data == "boom second line"


def test_kb_file_requires_path_and_score():
    _, data = _parse(chat.sse("kb_file", {"path": "LEARNING/x.md", "score": 1.0}))
    assert set(json.loads(data)) == {"path", "score"}


def test_kb_context_is_never_emitted():
    source = inspect.getsource(chat)
    assert 'sse("kb_context"' not in source
    assert "sse('kb_context'" not in source


def test_multiple_frames_split_cleanly_on_blank_lines():
    stream = chat.sse("iteration_start", {"iteration": 0}) + \
        chat.sse("token", "hello world") + chat.sse("done", {})
    frames = [f for f in stream.decode().split("\n\n") if f]
    assert len(frames) == 3
