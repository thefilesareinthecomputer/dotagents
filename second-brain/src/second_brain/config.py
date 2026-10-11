"""Configuration: env vars over ~/.brain/config over defaults.

The config file is `key = value` lines written by `brain config`.
Each accessor reads env and file at call time so per-invocation
overrides always win, and a malformed stored value falls back to its
default instead of crashing.
"""

import os
from pathlib import Path

# src/second_brain/config.py -> repo root; valid because uv installs the
# project editable during development.
_REPO_ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(path: Path | None = None) -> None:
    """Read KEY=VALUE lines from <repo>/.env into os.environ.

    Already-set environment variables win; the file is a convenience for
    settings such as OLLAMA_URL, never an override.
    """
    try:
        text = (path or _REPO_ROOT / ".env").read_text()
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


load_dotenv()


def brain_home() -> Path:
    """SECOND_BRAIN_HOME, default ~/.brain (pid, logs, user config)."""
    return Path(os.environ.get("SECOND_BRAIN_HOME", Path.home() / ".brain"))


def config_file() -> Path:
    return brain_home() / "config"


def load_file() -> dict[str, str]:
    """Parse ~/.brain/config; absent or unreadable means empty."""
    values: dict[str, str] = {}
    try:
        text = config_file().read_text()
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def _get(env_var: str, file_key: str, default: str) -> str:
    value = os.environ.get(env_var)
    if value is not None:
        return value
    return load_file().get(file_key) or default


def vault_path() -> Path:
    """SECOND_BRAIN_VAULT, then `vault` in config, default <repo>/vault."""
    return Path(_get("SECOND_BRAIN_VAULT", "vault", str(_REPO_ROOT / "vault")))


def data_path() -> Path:
    """SECOND_BRAIN_DATA, then `data` in config, default <repo>/data."""
    return Path(_get("SECOND_BRAIN_DATA", "data", str(_REPO_ROOT / "data")))


def host() -> str:
    """SECOND_BRAIN_HOST, then `host`, default 127.0.0.1 (single-user local)."""
    return _get("SECOND_BRAIN_HOST", "host", "127.0.0.1")


def port() -> int:
    """SECOND_BRAIN_PORT, then `port`, default 8765."""
    try:
        return int(_get("SECOND_BRAIN_PORT", "port", "8765"))
    except ValueError:
        return 8765


def ollama_url() -> str:
    """OLLAMA_URL, then `ollama_url`, default http://localhost:11434."""
    return _get("OLLAMA_URL", "ollama_url", "http://localhost:11434")


def ollama_keep_alive() -> str:
    """OLLAMA_KEEP_ALIVE, then `ollama_keep_alive`, default 5m: how long
    the daemon keeps a model in memory after a reply. "0" unloads right
    away (coolest, but every turn pays the model load); "-1" pins it."""
    return _get("OLLAMA_KEEP_ALIVE", "ollama_keep_alive", "5m")


def harness() -> str:
    """SECOND_BRAIN_HARNESS, then `harness` in config, default claude.
    Which terminal agent harness drives the chat lane (claude | codex |
    opencode | cursor | copilot | gemini | none)."""
    return _get("SECOND_BRAIN_HARNESS", "harness", "claude")


def preferred_name() -> str:
    """`name` in config; what the chat agent calls the user."""
    return load_file().get("name", "")


def model_default() -> str:
    """`model` in config; set, it picks the lane AND the model (the
    `brain model` surface); empty means the harness/key ladder decides."""
    return load_file().get("model", "")


def claude_model() -> str:
    """SECOND_BRAIN_CLAUDE_MODEL, then `claude_model`: passed to the claude
    CLI as --model (a tier alias, a full model id, or whatever an
    ollama-backed claude install understands). Default sonnet - the chat
    UI's turns should be fast unless the user picks a heavier tier."""
    return _get("SECOND_BRAIN_CLAUDE_MODEL", "claude_model", "sonnet")


def claude_effort() -> str:
    """SECOND_BRAIN_CLAUDE_EFFORT, then `claude_effort`: passed to the
    claude CLI as --effort (low|medium|high|xhigh|max). Default medium -
    same speed rationale as claude_model."""
    return _get("SECOND_BRAIN_CLAUDE_EFFORT", "claude_effort", "medium")


def save_file(values: dict[str, str]) -> None:
    """Rewrite ~/.brain/config from a key dict (the shape load_file
    returns); callers merge before saving so unrelated keys survive."""
    brain_home().mkdir(parents=True, exist_ok=True)
    lines = ["# second-brain config; `brain config` rewrites this file"]
    lines += [f"{key} = {value}" for key, value in values.items()]
    config_file().write_text("\n".join(lines) + "\n")


def seats_roster() -> list[dict]:
    """Named group-chat seats from ~/.brain/seats.json (SPEC-GROUP-CHAT-V1
    G1): the global seat store, a JSON list of {name, cwd, harness?,
    model?, effort?, readonly?, rules_source_writable?}. Absent or
    malformed reads as an empty roster.

    Entries pass through whole, so both permission flags reach the
    spawner: `readonly` seats a directory with the file tools and the
    shell denied at spawn, and `rules_source_writable` admits the shared
    skills repo as a writable seat in its own repo
    (chat.assert_seat_root decides what either flag admits).

    HUMAN-ONLY, for the same reason as seat_roots: the user edits
    `rules_source_writable` in the roster file by hand. No `brain config
    set` key, no `brain seat add` word, and no endpoint writes it.
    """
    import json
    try:
        data = json.loads((brain_home() / "seats.json").read_text())
        return [entry for entry in data if isinstance(entry, dict)
                and entry.get("name") and entry.get("cwd")]
    except Exception:
        return []


def save_seats_roster(entries: list[dict]) -> None:
    """Write the roster back (brain seat add/remove). Entries are trusted
    to be pre-validated dicts; the file is the whole roster every time."""
    import json
    brain_home().mkdir(parents=True, exist_ok=True)
    (brain_home() / "seats.json").write_text(json.dumps(entries, indent=1))


def seat_roots() -> list[Path]:
    """Directories a group-chat seat may be rooted in (`seat_roots` in
    ~/.brain/config, comma-separated).

    HUMAN-ONLY by design: nothing that decides the limits of an agent's
    own authority may be writable by an agent, so this key is absent
    from the `brain config set` allowlist. `brain config roots` routes
    the user to the file. Security review 2026-08-29.

    Absent, it derives from the roster: the parent of every seated repo
    plus this repo's own parent. A working roster therefore keeps
    working, and a genuinely new location is a deliberate human edit.
    """
    raw = load_file().get("seat_roots", "")
    listed = [Path(part.strip()).expanduser().resolve()
              for part in raw.split(",") if part.strip()]
    if listed:
        return listed
    home = Path.home().resolve()
    derived = {_REPO_ROOT.parent}
    for entry in seats_roster():
        try:
            seated = Path(entry["cwd"]).expanduser().resolve()
        except (OSError, KeyError):
            continue
        # The parent is the useful root (siblings of a worker repo are
        # the natural place for the next one) - except when that parent
        # is the home directory itself, where it would permit nearly
        # anywhere. A seat living directly in home roots only itself.
        derived.add(seated if seated.parent == home else seated.parent)
    derived.discard(home)
    return sorted(derived)


def seat_root_allowed(path: Path) -> bool:
    """True when path sits inside a permitted root (or is one).

    This repo is always permitted: it is the app's own home and the
    default cwd for a seat invited without one, so seating here grants
    nothing the main agent does not already have."""
    try:
        resolved = Path(path).expanduser().resolve()
    except OSError:
        return False
    if resolved == _REPO_ROOT:
        return True
    for root in seat_roots():
        if resolved == root or root in resolved.parents:
            return True
    return False


def ignored_folders(kind: str) -> list[str]:
    """`gitignored` / `agentignored` / `claudeignored` comma lists."""
    raw = load_file().get(kind, "")
    return [part.strip() for part in raw.split(",") if part.strip()]
