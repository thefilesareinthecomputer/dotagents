"""Tool registry: decorator-based registration and name routing.

This is deliberate dynamic dispatch - the call path from executor to a tool
function exists only in this table at runtime, which is exactly the pattern
static reachability cannot see. The fixture keeps it because real agent
codebases are full of it.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Callable

from relay.errors import ToolFailed, ToolNotFound


@dataclass
class ToolSpec:
    name: str
    description: str
    fn: Callable[..., str]
    timeout_s: int = 30
    tags: tuple[str, ...] = ()
    calls: int = field(default=0, compare=False)

    def signature(self) -> str:
        return f"{self.name}{inspect.signature(self.fn)}"


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"duplicate tool name: {spec.name}")
        self._tools[spec.name] = spec

    def names(self) -> list[str]:
        return sorted(self._tools)

    def describe_all(self) -> list[dict]:
        return [{"name": s.name, "description": s.description,
                 "signature": s.signature(), "tags": list(s.tags)}
                for _, s in sorted(self._tools.items())]

    def filtered(self, allowlist: tuple[str, ...]) -> "ToolRegistry":
        """A view holding only allowlisted tools; empty allowlist means all."""
        if not allowlist:
            return self
        view = ToolRegistry()
        for name in allowlist:
            if name in self._tools:
                view._tools[name] = self._tools[name]
        return view

    def dispatch(self, name: str, **kwargs) -> str:
        """Route a step to its tool by name. The runtime edge lives here."""
        spec = self._tools.get(name)
        if spec is None:
            raise ToolNotFound(name, self.names())
        try:
            spec.calls += 1
            return spec.fn(**kwargs)
        except ToolFailed:
            raise
        except Exception as exc:  # noqa: BLE001 - tool boundary
            raise ToolFailed(name, str(exc), retryable=False) from exc


_REGISTRY = ToolRegistry()


def get_registry() -> ToolRegistry:
    return _REGISTRY


def tool(name: str, description: str, timeout_s: int = 30,
         tags: tuple[str, ...] = ()) -> Callable:
    """Class-free registration: decorate a function and it is routable."""

    def wrap(fn: Callable[..., str]) -> Callable[..., str]:
        _REGISTRY.register(ToolSpec(
            name=name, description=description, fn=fn,
            timeout_s=timeout_s, tags=tags))
        return fn

    return wrap
