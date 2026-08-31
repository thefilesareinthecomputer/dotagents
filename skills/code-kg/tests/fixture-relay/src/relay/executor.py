"""Executor: walk a Plan step by step, recording everything to memory.

The executor owns the run loop and nothing else: routing lives in the tool
registry, judgment lives in the planner, persistence lives in the store.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from relay.audit import AuditLog
from relay.config import Config
from relay.errors import BudgetExceeded, ToolFailed
from relay.llm.client import LLMClient
from relay.llm.prompts import context_block
from relay.memory.recall import recall
from relay.memory.store import MemoryStore
from relay.planner import Plan, Planner, Step
from relay.telemetry import Telemetry
from relay.tools.registry import get_registry


@dataclass
class StepResult:
    step: Step
    ok: bool
    output: str
    elapsed_s: float


@dataclass
class RunResult:
    goal: str
    completed: list[StepResult] = field(default_factory=list)
    failed: list[StepResult] = field(default_factory=list)
    stopped_reason: str = "done"

    def summary(self) -> dict:
        return {
            "goal": self.goal,
            "completed": len(self.completed),
            "failed": len(self.failed),
            "stopped": self.stopped_reason,
        }


class Executor:
    def __init__(self, config: Config, store: MemoryStore,
                 telemetry: Telemetry | None = None) -> None:
        self.config = config
        self.store = store
        self.telemetry = telemetry or Telemetry(config.log_level)
        self.client = LLMClient(config)
        self.planner = Planner(config, self.client)
        self.audit = AuditLog(config.memory_path + ".audit.jsonl")

    def run(self, goal: str) -> RunResult:
        plan = self.planner.plan(goal)
        self.telemetry.event("plan.created", steps=len(plan.steps))
        result = RunResult(goal=goal)
        registry = get_registry().filtered(self.config.tool_allowlist)
        for step in list(plan.steps):
            outcome = self._run_step(registry, goal, step)
            if outcome.ok:
                result.completed.append(outcome)
                continue
            result.failed.append(outcome)
            if "budget" in outcome.output:
                result.stopped_reason = "budget"
                break
            plan = self.planner.replan_after_failure(
                plan, step, outcome.output)
        self._persist(result)
        return result

    def _run_step(self, registry, goal: str, step: Step) -> StepResult:
        started = time.monotonic()
        memories = recall(self.store, step.rationale or goal)
        context = context_block([m.body for m in memories])
        try:
            self.client.complete_step(goal, step.name, context)
            output = registry.dispatch(step.tool, **step.args)
            ok = True
        except ToolFailed as exc:
            output, ok = str(exc), False
        except BudgetExceeded as exc:
            output, ok = f"budget: {exc}", False
        elapsed = time.monotonic() - started
        self.telemetry.event("step.finished", step=step.name, ok=ok,
                             elapsed_s=round(elapsed, 3))
        return StepResult(step=step, ok=ok, output=output, elapsed_s=elapsed)

    def _persist(self, result: RunResult) -> None:
        self.store.append(
            key=f"run:{result.goal[:60]}",
            body="\n".join(
                f"{r.step.name}: {'ok' if r.ok else 'FAIL'} {r.output[:200]}"
                for r in result.completed + result.failed),
            kind="run",
            meta=result.summary())
        self.audit.append("run", result.summary())
