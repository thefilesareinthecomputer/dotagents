"""Configuration: one frozen object read once at startup.

Sources, in precedence order: explicit kwargs, environment variables with the
RELAY_ prefix, then defaults. Nothing else in the codebase reads os.environ.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace

from relay.errors import ConfigError

_ENV_PREFIX = "RELAY_"

_DEFAULTS = {
    "model": "claude-sonnet-5",
    "max_steps": "12",
    "token_budget": "120000",
    "memory_path": "relay-memory.db",
    "server_port": "8420",
    "log_level": "info",
}

_VALID_LOG_LEVELS = ("debug", "info", "warning", "error")


@dataclass(frozen=True)
class Config:
    model: str
    max_steps: int
    token_budget: int
    memory_path: str
    server_port: int
    log_level: str
    tool_allowlist: tuple[str, ...] = field(default_factory=tuple)

    def with_overrides(self, **kwargs) -> "Config":
        """A copy with the given fields replaced; validation re-runs."""
        merged = replace(self, **kwargs)
        _validate(merged)
        return merged

    def describe(self) -> dict:
        """A redaction-safe summary for logs and the /config endpoint."""
        return {
            "model": self.model,
            "max_steps": self.max_steps,
            "token_budget": self.token_budget,
            "server_port": self.server_port,
            "log_level": self.log_level,
            "tools": list(self.tool_allowlist) or "all",
        }


def _read_env(name: str) -> str | None:
    return os.environ.get(_ENV_PREFIX + name.upper())


def _int_field(name: str, raw: str, minimum: int, maximum: int) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(name, f"not an integer: {raw!r}") from exc
    if not minimum <= value <= maximum:
        raise ConfigError(
            name, f"{value} outside allowed range {minimum}..{maximum}")
    return value


def _validate(cfg: Config) -> None:
    if not cfg.model:
        raise ConfigError("model", "must be non-empty")
    if cfg.log_level not in _VALID_LOG_LEVELS:
        raise ConfigError(
            "log_level",
            f"{cfg.log_level!r} not one of {', '.join(_VALID_LOG_LEVELS)}")
    if cfg.memory_path.startswith("~"):
        raise ConfigError("memory_path", "expand the home directory first")


def load_config(**overrides) -> Config:
    """Build the Config from defaults, environment, then overrides."""
    raw: dict[str, str] = {}
    for key, default in _DEFAULTS.items():
        raw[key] = _read_env(key) or default
    allow = _read_env("tool_allowlist") or ""
    cfg = Config(
        model=str(overrides.get("model", raw["model"])),
        max_steps=_int_field(
            "max_steps",
            str(overrides.get("max_steps", raw["max_steps"])), 1, 64),
        token_budget=_int_field(
            "token_budget",
            str(overrides.get("token_budget", raw["token_budget"])),
            1000, 2_000_000),
        memory_path=str(overrides.get("memory_path", raw["memory_path"])),
        server_port=_int_field(
            "server_port",
            str(overrides.get("server_port", raw["server_port"])),
            1024, 65535),
        log_level=str(overrides.get("log_level", raw["log_level"])).lower(),
        tool_allowlist=tuple(t for t in allow.split(",") if t.strip()),
    )
    _validate(cfg)
    return cfg
