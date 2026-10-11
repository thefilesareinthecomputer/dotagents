"""Mission-control registry tests. STORY-000079 (SPEC-GROUP-CHAT-V1 G8)."""

import pytest

from second_brain import registry


@pytest.fixture(autouse=True)
def clean_registry():
    registry._rows.clear()
    yield
    registry._rows.clear()


def _tool_use(name, tool_id="t1"):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": name, "id": tool_id, "input": {}}]}}


def test_turn_lifecycle_states():
    registry.begin("c1", "main", "Main", "/repo", "sonnet")
    assert registry.snapshot()[0]["state"] == "starting"

    registry.event("c1", "main", {"type": "system", "subtype": "init"})
    assert registry.snapshot()[0]["state"] == "thinking"

    registry.event("c1", "main", _tool_use("Read"))
    row = registry.snapshot()[0]
    assert row["state"] == "tools" and row["tool"] == "Read"

    registry.event("c1", "main", {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "t1"}]}})
    row = registry.snapshot()[0]
    assert row["state"] == "thinking" and row["tool"] == ""

    registry.event("c1", "main", {"type": "result", "usage":
                                  {"input_tokens": 10, "output_tokens": 5}})
    row = registry.snapshot()[0]
    assert row["state"] == "idle" and row["tokens"] == 15

    registry.end("c1", "main")
    assert registry.snapshot() == []


def test_subagent_rows_from_parent_tool_use_id():
    """The 2026-08-27 spike: subagent events carry parent_tool_use_id
    pointing at the spawning Agent tool_use; its tool_result ends them."""
    registry.begin("c1", "scribe", "Scribe", "/arch", "")
    registry.event("c1", "scribe", _tool_use("Agent", "toolu_9"))
    registry.event("c1", "scribe",
                   {"type": "assistant", "parent_tool_use_id": "toolu_9",
                    "message": {"content": [
                        {"type": "tool_use", "name": "Grep", "id": "g1",
                         "input": {}}]}})
    row = registry.snapshot()[0]
    assert len(row["subagents"]) == 1
    sub = row["subagents"][0]
    assert sub["id"] == "toolu_9"
    assert sub["state"] == "tools" and sub["tool"] == "Grep"

    registry.event("c1", "scribe", {"type": "user", "message":
                   {"content": [{"type": "tool_result",
                                 "tool_use_id": "toolu_9"}]}})
    assert registry.snapshot()[0]["subagents"] == []


def test_prep_rows_are_flagged_and_independent():
    registry.begin("c1", "scout", "Scout", "/s", "", prep=False)
    registry.begin("c1", "scout:prep", "Scout", "/s", "", prep=True)
    rows = registry.snapshot()
    assert len(rows) == 2
    assert {r["prep"] for r in rows} == {True, False}
    registry.end("c1", "scout:prep")
    assert len(registry.snapshot()) == 1


def test_unknown_actor_events_are_ignored():
    registry.event("cx", "ghost", {"type": "result"})  # no crash, no row
    assert registry.snapshot() == []
