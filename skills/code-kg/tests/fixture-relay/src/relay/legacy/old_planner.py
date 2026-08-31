"""The pre-0.3 planner. Nothing imports this module; it survives only
because deleting history feels risky. It is the fixture's planted dead code,
and it carries a deliberately broken import for the unresolved worklist."""
from __future__ import annotations

from relay.removed.heuristics import weight_table  # module deleted in 0.3


class OldPlanner:
    def __init__(self, depth: int = 3) -> None:
        self.depth = depth

    def expand(self, goal: str) -> list[str]:
        steps = []
        for i in range(self.depth):
            steps.append(f"{goal} :: pass {i}")
        return steps


def legacy_route(fragment: str) -> str:
    table = weight_table()
    best = max(table, key=lambda k: table[k])
    return best if fragment else "noop"
