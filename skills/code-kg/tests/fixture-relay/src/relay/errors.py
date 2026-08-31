"""Exception hierarchy for relay.

Every error raised by relay code subclasses RelayError so callers can catch
one type at the boundary and let genuine bugs (KeyError, TypeError) surface.
"""


class RelayError(Exception):
    """Base class for every error relay raises deliberately."""


class ConfigError(RelayError):
    """A configuration value is missing or malformed."""

    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"config field {field!r}: {reason}")


class ToolNotFound(RelayError):
    """A plan step names a tool the registry does not hold."""

    def __init__(self, tool_name: str, known: list[str]) -> None:
        self.tool_name = tool_name
        self.known = known
        super().__init__(
            f"unknown tool {tool_name!r}; registered: {', '.join(known)}")


class ToolFailed(RelayError):
    """A tool ran and reported failure; carries the tool's own message."""

    def __init__(self, tool_name: str, message: str, retryable: bool) -> None:
        self.tool_name = tool_name
        self.message = message
        self.retryable = retryable
        super().__init__(f"tool {tool_name!r} failed: {message}")


class BudgetExceeded(RelayError):
    """The token or step budget ran out before the plan completed."""

    def __init__(self, budget_kind: str, limit: int, spent: int) -> None:
        self.budget_kind = budget_kind
        self.limit = limit
        self.spent = spent
        super().__init__(
            f"{budget_kind} budget exceeded: {spent} of {limit}")


class MemoryCorrupt(RelayError):
    """The memory store failed an integrity check and needs a rebuild."""


def wrap_unknown(exc: Exception) -> RelayError:
    """Normalize a foreign exception at the boundary without losing it."""
    if isinstance(exc, RelayError):
        return exc
    wrapped = RelayError(f"unexpected {type(exc).__name__}: {exc}")
    wrapped.__cause__ = exc
    return wrapped
