"""Planner: turn a goal into an ordered, bounded list of tool steps.

Plans are data. The planner never executes anything; it emits a Plan the
executor walks, so a plan can be inspected, edited, or refused before any
tool runs.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from relay.config import Config
from relay.errors import RelayError
from relay.llm.client import LLMClient
from relay.tools.registry import get_registry


@dataclass(frozen=True)
class Step:
    name: str
    tool: str
    args: dict
    rationale: str = ""

    def describe(self) -> str:
        return f"{self.name} -> {self.tool}({', '.join(self.args)})"


@dataclass
class Plan:
    goal: str
    steps: list[Step] = field(default_factory=list)

    def append(self, step: Step) -> None:
        self.steps.append(step)

    def tool_names(self) -> set[str]:
        return {s.tool for s in self.steps}

    def describe(self) -> list[str]:
        return [s.describe() for s in self.steps]


_KEYWORD_ROUTES: list[tuple[tuple[str, ...], str]] = [
    (("fetch", "download", "url", "page", "scrape"), "web"),
    (("query", "table", "rows", "database", "sql"), "sql"),
    (("list", "read", "file", "grep", "log"), "shell"),
]


def route_keyword(fragment: str) -> str:
    """Cheap-first routing: keyword table before any model call."""
    lowered = fragment.lower()
    for keywords, tool_name in _KEYWORD_ROUTES:
        if any(k in lowered for k in keywords):
            return tool_name
    return "shell"


class Planner:
    def __init__(self, config: Config, client: LLMClient) -> None:
        self.config = config
        self.client = client

    def plan(self, goal: str) -> Plan:
        """Split the goal into fragments, route each, cap at max_steps."""
        if not goal.strip():
            raise RelayError("empty goal")
        fragments = self._split_goal(goal)
        available = get_registry().filtered(
            self.config.tool_allowlist).names()
        plan = Plan(goal=goal)
        for i, fragment in enumerate(fragments[: self.config.max_steps]):
            tool_name = route_keyword(fragment)
            if tool_name not in available:
                tool_name = available[0] if available else "shell"
            plan.append(Step(
                name=f"step-{i + 1}",
                tool=tool_name,
                args=self._args_for(tool_name, fragment),
                rationale=fragment.strip()))
        return plan

    def _split_goal(self, goal: str) -> list[str]:
        parts = [p for chunk in goal.split(" then ")
                 for p in chunk.split(" and ")]
        return [p.strip() for p in parts if p.strip()]

    def _args_for(self, tool_name: str, fragment: str) -> dict:
        if tool_name == "web":
            words = [w for w in fragment.split() if w.startswith("http")]
            return {"url": words[0] if words else "https://example.com"}
        if tool_name == "sql":
            return {"sql": "SELECT key, body FROM records LIMIT 10"}
        return {"command": f"grep -r {fragment.split()[-1]} ."}

    def replan_after_failure(self, plan: Plan, failed: Step,
                             error: str) -> Plan:
        """Drop the failed step, keep the rest; one retry step if retryable."""
        remaining = [s for s in plan.steps if s.name != failed.name]
        revised = Plan(goal=plan.goal, steps=remaining)
        if "timeout" in error.lower():
            revised.append(Step(
                name=f"{failed.name}-retry", tool=failed.tool,
                args=failed.args, rationale=f"retry after: {error[:80]}"))
        return revised
