"""Prompt templates kept as code, not config, so diffs review like logic."""
from __future__ import annotations

_SYSTEM_TEMPLATE = """You are relay, a workflow executor.
Model: {model}
Rules:
- Act only through the provided tools.
- Report failure honestly; never invent output.
- Stop when the goal is met or the budget is gone.
"""

_STEP_TEMPLATE = """Goal: {goal}
Current step: {step}

Context so far:
{context}

Respond with the outcome of this step only.
"""

_SUMMARY_TEMPLATE = """Summarize the run of goal {goal!r} in three sentences.
Steps completed: {completed}
Steps failed: {failed}
"""


def render_system_prompt(model: str) -> str:
    return _SYSTEM_TEMPLATE.format(model=model)


def render_step_prompt(goal: str, step: str, context: str) -> str:
    clipped = context if len(context) < 4000 else context[-4000:]
    return _STEP_TEMPLATE.format(goal=goal, step=step, context=clipped)


def render_summary_prompt(goal: str, completed: int, failed: int) -> str:
    return _SUMMARY_TEMPLATE.format(
        goal=goal, completed=completed, failed=failed)


def context_block(entries: list[str], budget_chars: int = 6000) -> str:
    """Newest-last context assembly that trims oldest-first when over."""
    kept: list[str] = []
    total = 0
    for entry in reversed(entries):
        if total + len(entry) > budget_chars:
            break
        kept.append(entry)
        total += len(entry)
    return "\n".join(reversed(kept))
