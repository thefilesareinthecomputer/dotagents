"""LLM client: a provider-shaped facade with retries and a hard token budget.

The fixture ships no network code; `_transport` is a seam a real deployment
replaces. Everything above the seam - retry classification, budget
accounting, prompt assembly - is the code under test.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from relay.config import Config
from relay.errors import BudgetExceeded, wrap_unknown
from relay.llm.parsing import ToolCall, parse_tool_call
from relay.llm.prompts import render_system_prompt, render_step_prompt


@dataclass
class RetryPolicy:
    """When to retry a transport failure, and how long to wait."""

    max_attempts: int = 3
    base_delay_s: float = 0.5
    multiplier: float = 2.0
    retryable_markers: tuple[str, ...] = ("overloaded", "timeout", "529")

    def delay_for(self, attempt: int) -> float:
        return self.base_delay_s * (self.multiplier ** (attempt - 1))

    def should_retry(self, attempt: int, error_text: str) -> bool:
        if attempt >= self.max_attempts:
            return False
        lowered = error_text.lower()
        return any(marker in lowered for marker in self.retryable_markers)


class TokenBudget:
    """Counts tokens spent across a run; refuses to go negative."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.spent = 0

    def charge(self, tokens: int) -> None:
        if self.spent + tokens > self.limit:
            raise BudgetExceeded("token", self.limit, self.spent + tokens)
        self.spent += tokens

    def remaining(self) -> int:
        return max(0, self.limit - self.spent)

    def estimate(self, text: str) -> int:
        """Chars/4 is deliberately crude and deliberately consistent."""
        return max(1, len(text) // 4)


class LLMClient:
    """Assembles prompts, enforces the budget, retries the transport."""

    def __init__(self, config: Config,
                 retry: RetryPolicy | None = None) -> None:
        self.config = config
        self.retry = retry or RetryPolicy()
        self.budget = TokenBudget(config.token_budget)
        self._call_log: list[dict] = []

    def complete_step(self, goal: str, step_name: str, context: str) -> str:
        """One completion for one plan step, budget-charged both directions."""
        system = render_system_prompt(self.config.model)
        prompt = render_step_prompt(goal, step_name, context)
        self.budget.charge(self.budget.estimate(system + prompt))
        text = self._call_with_retry(system, prompt)
        self.budget.charge(self.budget.estimate(text))
        return text

    def _call_with_retry(self, system: str, prompt: str) -> str:
        attempt = 0
        while True:
            attempt += 1
            started = time.monotonic()
            try:
                text = self._transport(system, prompt)
                self._record(attempt, started, ok=True)
                return text
            except Exception as exc:  # noqa: BLE001 - boundary
                self._record(attempt, started, ok=False)
                if not self.retry.should_retry(attempt, str(exc)):
                    raise wrap_unknown(exc) from exc
                time.sleep(self.retry.delay_for(attempt))

    def _transport(self, system: str, prompt: str) -> str:
        """The seam. The fixture answers deterministically for tests."""
        return f"[stub:{self.config.model}] {prompt[:80]}"

    def _record(self, attempt: int, started: float, ok: bool) -> None:
        self._call_log.append({
            "attempt": attempt,
            "elapsed_s": round(time.monotonic() - started, 4),
            "ok": ok,
        })

    def parse_tool_request(self, completion: str) -> ToolCall | None:
        """The tool call a completion asked for, if it asked for one."""
        parsed = parse_tool_call(completion)
        return parsed if isinstance(parsed, ToolCall) else None

    def call_stats(self) -> dict:
        calls = len(self._call_log)
        failures = sum(1 for c in self._call_log if not c["ok"])
        return {"calls": calls, "failures": failures,
                "tokens_spent": self.budget.spent,
                "tokens_remaining": self.budget.remaining()}
