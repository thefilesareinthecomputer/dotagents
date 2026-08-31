"""Run reports: one RunResult rendered as text, markdown, or a dict tree.

Rendering lives apart from the executor so formats can grow without
touching the run loop, and so tests can assert on structure rather than
string-matching terminal output.
"""
from __future__ import annotations

from relay.executor import RunResult, StepResult


def _step_rows(steps: list[StepResult]) -> list[dict]:
    return [{
        "name": r.step.name,
        "tool": r.step.tool,
        "ok": r.ok,
        "elapsed_s": round(r.elapsed_s, 3),
        "output_head": r.output[:120],
    } for r in steps]


def as_tree(result: RunResult) -> dict:
    """The structured form every other renderer builds from."""
    return {
        "goal": result.goal,
        "stopped": result.stopped_reason,
        "counts": {"completed": len(result.completed),
                   "failed": len(result.failed)},
        "completed": _step_rows(result.completed),
        "failed": _step_rows(result.failed),
    }


def as_text(result: RunResult) -> str:
    tree = as_tree(result)
    lines = [f"goal: {tree['goal']}",
             f"stopped: {tree['stopped']}"
             f" ({tree['counts']['completed']} ok,"
             f" {tree['counts']['failed']} failed)"]
    for row in tree["completed"]:
        lines.append(f"  ok   {row['name']:<12} {row['tool']:<10}"
                     f" {row['elapsed_s']}s")
    for row in tree["failed"]:
        lines.append(f"  FAIL {row['name']:<12} {row['tool']:<10}"
                     f" {row['output_head']}")
    return "\n".join(lines)


def as_markdown(result: RunResult) -> str:
    tree = as_tree(result)
    lines = [f"## Run: {tree['goal']}", "",
             f"Stopped: `{tree['stopped']}` -"
             f" {tree['counts']['completed']} completed,"
             f" {tree['counts']['failed']} failed", "",
             "| step | tool | ok | elapsed |",
             "|---|---|---|---|"]
    for row in tree["completed"] + tree["failed"]:
        lines.append(f"| {row['name']} | {row['tool']} |"
                     f" {'yes' if row['ok'] else 'NO'} |"
                     f" {row['elapsed_s']}s |")
    failed = tree["failed"]
    if failed:
        lines += ["", "### Failures", ""]
        for row in failed:
            lines.append(f"- **{row['name']}**: {row['output_head']}")
    return "\n".join(lines)


def failure_digest(results: list[RunResult], limit: int = 5) -> list[str]:
    """The most recent distinct failure messages across several runs."""
    seen: set[str] = set()
    digest: list[str] = []
    for result in reversed(results):
        for row in _step_rows(result.failed):
            key = row["output_head"]
            if key not in seen:
                seen.add(key)
                digest.append(f"{result.goal[:40]}: {key}")
            if len(digest) >= limit:
                return digest
    return digest
