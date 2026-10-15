#!/usr/bin/env python3
"""The decision hook: a local decision model beside Claude Code's own guards.

PreToolUse asks one choice question about the tool call on Ollama's /v1/systemone
and can answer "ask" or nothing. UserPromptSubmit embeds the prompt and can add
one line of context or nothing. Every other path, including every failure,
exits 0 with no output. Stdlib only; loopback only.

    decide.py --event pre-tool-use | user-prompt-submit | session-start   (hook entries, read stdin)
    decide.py doctor
    decide.py report [--days N]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import ipaddress
import json
import math
import os
import platform
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REFS = HERE.parent / "references"
MAX_FIELD = 2000          # characters kept per string field of the tool input
MAX_STATE = 56 * 1024     # the endpoint caps text plus schema at 64 KiB; the question takes the rest
MAX_RESPONSE = 1 << 20
WATCHED_TOOLS = re.compile(r"^(Bash|Write|Edit|MultiEdit|NotebookEdit|mcp__.*)$")
MODE_VALUES = ("off", "shadow", "active")
PERMISSION_MODES = ("default", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions")
RUNNER_RE = re.compile(r"^\s*(\d+)\s+.*\bollama runner\b.*--model\s+(\S+)")
SESSION_RE = re.compile(r"[^A-Za-z0-9_-]")


class HookError(Exception):
    def __init__(self, outcome: str, msg: str):
        super().__init__(msg)
        self.outcome = outcome


# ------------------------------------------------------------------ the one rule

def hook_output(event: str, escalate: bool, reason: str) -> dict | None:
    """The only things this hook can say on PreToolUse: nothing, or ask."""
    if event != "PreToolUse" or not escalate:
        return None
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "ask",
                                   "permissionDecisionReason": reason}}


def context_output(line: str) -> dict:
    """The only thing this hook can say on UserPromptSubmit: one line of context."""
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": line}}


# ------------------------------------------------------------------ config and state

def default_config() -> dict:
    modes = {"PreToolUse": {m: "shadow" for m in PERMISSION_MODES},
             "UserPromptSubmit": {m: "off" for m in PERMISSION_MODES}}   # routing missed its Phase 0 gate; opt in
    modes["PreToolUse"]["bypassPermissions"] = "off"   # there an ask would become an allow
    # `judgment`: features (deterministic call features and one logistic score, no model, the
    # default), systemone (the decision model on /v1/systemone), or both (features first, the
    # model only when the features do not flag).
    return {"base_url": "http://127.0.0.1:11434", "model": "tev1:0.8b", "embed_model": "embeddinggemma",
            "judgment": "features",
            "keep_alive": "10m", "client_timeout_s": 1.5, "warm_timeout_s": 15, "escalation_cap": 5,
            "budget_path": str(Path.home() / ".config" / "local-models" / "budget.json"), "modes": modes}


def config_path() -> Path:
    return Path(os.environ.get("DECISION_HOOK_CONFIG") or Path.home() / ".config" / "decision-hook" / "config.json")


def state_dir() -> Path:
    return Path(os.environ.get("DECISION_HOOK_STATE") or Path.home() / ".local" / "state" / "decision-hook")


def index_path() -> Path:
    return Path(os.environ.get("DECISION_HOOK_INDEX") or REFS / "routing-index.json")


def load_config() -> dict:
    cfg = default_config()
    try:
        user = json.loads(config_path().read_text())
    except (OSError, ValueError):
        return cfg
    if isinstance(user, dict):
        modes = user.pop("modes", None)
        cfg.update(user)
        if isinstance(modes, dict):
            for event, table in modes.items():
                if isinstance(table, dict):
                    cfg["modes"].setdefault(event, {}).update(table)
    return cfg


def resolve_mode(cfg: dict, event: str, permission_mode: str) -> str:
    if event == "PreToolUse" and permission_mode == "bypassPermissions":
        return "off"   # there an ask becomes an allow, so no config can switch this on
    value = ((cfg.get("modes") or {}).get(event) or {}).get(permission_mode)
    return value if value in MODE_VALUES else "off"


def ensure_state() -> Path:
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(d, 0o700)
    return d


def log_record(record: dict) -> None:
    path = ensure_state() / "decisions.jsonl"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, separators=(",", ":")) + "\n")


def session_count(session_id: str, bump: bool = False) -> int:
    d = ensure_state() / "sessions"
    d.mkdir(exist_ok=True, mode=0o700)
    path = d / (SESSION_RE.sub("_", session_id)[:120] or "none")
    try:
        count = int(path.read_text().strip() or 0)
    except (OSError, ValueError):
        count = 0
    if bump:
        count += 1
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(str(count))
    return count


# ------------------------------------------------------------------ state building

def cut(value, limit: int):
    if isinstance(value, str):
        return value[:limit]
    if isinstance(value, dict):
        return {str(k)[:200]: cut(v, limit) for k, v in list(value.items())[:200]}
    if isinstance(value, list):
        return [cut(v, limit) for v in value[:200]]
    return value


def build_state(payload: dict) -> dict:
    tool_input = payload.get("tool_input")
    limit = MAX_FIELD
    while True:
        state = {"tool_name": str(payload.get("tool_name", ""))[:200],
                 "tool_input": cut(tool_input if isinstance(tool_input, dict) else {}, limit),
                 "cwd": str(payload.get("cwd", ""))[:1000],
                 "permission_mode": str(payload.get("permission_mode", ""))[:40]}
        if len(json.dumps(state)) <= MAX_STATE or limit <= 16:
            return state
        limit //= 2


# ------------------------------------------------------------------ probabilities

def platt(p: float, params: dict) -> float:
    p = min(max(float(p), 1e-6), 1 - 1e-6)
    z = float(params.get("a", 1.0)) * math.log(p / (1 - p)) + float(params.get("b", 0.0))
    return 1.0 / (1.0 + math.exp(-z))


def parse_probabilities(reply: object, name: str) -> dict:
    answer = (reply.get("answers") or {}).get(name) if isinstance(reply, dict) else None
    probs = answer.get("probabilities") if isinstance(answer, dict) else None
    if not isinstance(probs, dict) or not probs:
        raise HookError("error", "reply holds no probabilities")
    out = {}
    for k, v in probs.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise HookError("error", "a probability is not a number")
        out[str(k)] = float(v)
    return out


def decide_risk(probs: dict, question: dict) -> tuple[str, float] | None:
    """The option with the highest calibrated probability over its own threshold, or None."""
    best = None
    for option, threshold in (question.get("thresholds") or {}).items():
        if option == "none":
            continue
        p = round(platt(probs.get(option, 0.0), (question.get("platt") or {}).get(option) or {}), 4)
        if p >= float(threshold) and (best is None or p > best[1]):
            best = (option, p)
    return best


# ------------------------------------------------------------------ routing

def cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def route(vector, index: dict) -> tuple[str | None, float]:
    best_sim, best = -1.0, None
    for ex in index.get("exemplars") or []:
        sim = cosine(vector, ex.get("vector") or [])
        if sim > best_sim:
            best_sim, best = sim, ex
    if best is None or best_sim < float(index.get("threshold", 1.0)) or not best.get("should_trigger"):
        return None, round(best_sim, 4)
    return str(best.get("skill")), round(best_sim, 4)


# ------------------------------------------------------------------ memory

def parse_runner_rss(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        m = RUNNER_RE.match(line)
        if m:
            out[m.group(2)] = int(m.group(1)) * 1024
    return out


def runner_rss() -> dict:
    try:
        text = subprocess.run(["ps", "-axo", "rss,command"], capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    return parse_runner_rss(text)


def loaded_bytes(ps_models: list, rss: dict) -> int:
    """What the loaded models occupy: resident size for the MLX runner, whose /api/ps size is not a
    memory reading (it reported 8 GB for a 0.7 GB runner on 2026-10-09); the larger reading otherwise."""
    total = 0
    for m in ps_models:
        name = str(m.get("name") or m.get("model") or "")
        size = int(m.get("size") or 0)
        res = rss.get(name) or rss.get(name.split(":")[0]) or 0
        total += res if m.get("runner") == "mlx" and res else max(size, res)
    return total


def free_memory_bytes() -> int | None:
    try:
        if platform.system() == "Darwin":
            def sysctl(name):
                return int(subprocess.run(["sysctl", "-n", name], capture_output=True, text=True,
                                          timeout=2, check=True).stdout.strip())
            return sysctl("hw.memsize") * sysctl("kern.memorystatus_level") // 100
        if platform.system() == "Linux":
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return None


def total_memory_bytes() -> int:
    try:
        if platform.system() == "Darwin":
            return int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=2).stdout)
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (OSError, ValueError, subprocess.SubprocessError):
        return 16 << 30


def load_budget(cfg: dict) -> dict:
    budget = {"max_total_gb": round(total_memory_bytes() * 0.35 / (1 << 30), 2), "reserve_gb": 4.0}
    try:
        user = json.loads(Path(str(cfg.get("budget_path"))).expanduser().read_text())
        if isinstance(user, dict):
            budget.update({k: float(v) for k, v in user.items() if k in ("max_total_gb", "reserve_gb")})
    except (OSError, ValueError, TypeError):
        pass
    return budget


def over_budget(budget: dict, loaded: int, estimate: int, free: int | None) -> str | None:
    cap = float(budget.get("max_total_gb", 0)) * (1 << 30)
    if loaded + estimate > cap:
        return f"over the memory budget cap: {(loaded + estimate) / (1 << 30):.1f} GB would exceed {cap / (1 << 30):.1f} GB"
    if free is not None and estimate > free - float(budget.get("reserve_gb", 0)) * (1 << 30):
        return f"not enough free memory: {free / (1 << 30):.1f} GB free against a {budget.get('reserve_gb')} GB reserve"
    return None


# ------------------------------------------------------------------ http

def is_loopback(url: str) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").strip("[]").split("%", 1)[0]
    if host == "localhost":
        try:
            infos = socket.getaddrinfo(host, None)
        except OSError:
            return False
        return bool(infos) and all(ipaddress.ip_address(i[4][0]).is_loopback for i in infos)
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


class Client:
    def __init__(self, base_url: str, deadline: float):
        if not is_loopback(base_url):
            raise HookError("error", "the endpoint is not on loopback")
        self.base = base_url.rstrip("/")
        self.deadline = deadline
        self.opener = urllib.request.build_opener(NoRedirect(), urllib.request.ProxyHandler({}))

    def call(self, method: str, path: str, body: dict | None = None):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise HookError("timeout", "client budget spent before " + path)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", "Accept": "application/json"})
        try:
            with self.opener.open(req, timeout=remaining) as resp:
                raw = resp.read(MAX_RESPONSE + 1)
        except urllib.error.HTTPError as e:
            raise HookError("error", f"HTTP {e.code} from {path}")
        except urllib.error.URLError as e:
            if isinstance(e.reason, (TimeoutError, socket.timeout)):
                raise HookError("timeout", f"no answer from {path} within the budget")
            raise HookError("error", f"cannot reach {path}: {type(e.reason).__name__}")
        except (TimeoutError, socket.timeout):
            raise HookError("timeout", f"no answer from {path} within the budget")
        except OSError as e:
            raise HookError("error", f"connection failed on {path}: {type(e).__name__}")
        if len(raw) > MAX_RESPONSE:
            raise HookError("error", "reply too large")
        try:
            return json.loads(raw)
        except ValueError:
            raise HookError("error", f"reply from {path} is not JSON")


def unload(client: "Client", model: str) -> None:
    """Ask Ollama to drop a model now. Operator tooling calls this when it finishes so a model never
    outlives the command that loaded it; the hook itself keeps its model warm on purpose."""
    try:
        client.call("POST", "/api/generate", {"model": model, "keep_alive": 0})
    except HookError:
        pass


def same_model(a: str, b: str) -> bool:
    norm = lambda s: s if ":" in s else s + ":latest"  # noqa: E731
    return norm(a) == norm(b)


def loaded_models(client: Client) -> list:
    reply = client.call("GET", "/api/ps")
    models = reply.get("models") if isinstance(reply, dict) else None
    return [m for m in (models or []) if isinstance(m, dict)]


def check_slot(client: Client, cfg: dict, model: str, loaded: list) -> None:
    """Skip when another model holds the slot; on a cold load, obey the shared memory budget."""
    names = [str(m.get("name") or m.get("model") or "") for m in loaded]
    if any(same_model(n, model) for n in names):
        return
    if names:
        raise HookError("skipped", "another model loaded: " + ", ".join(names))
    estimate = 1 << 30
    try:
        tags = client.call("GET", "/api/tags")
        for m in (tags.get("models") or []) if isinstance(tags, dict) else []:
            if same_model(str(m.get("name") or ""), model) and m.get("size"):
                estimate = int(int(m["size"]) * 1.25)
    except HookError:
        pass
    reason = over_budget(load_budget(cfg), loaded_bytes(loaded, runner_rss()), estimate, free_memory_bytes())
    if reason:
        raise HookError("skipped", "memory budget: " + reason)


# ------------------------------------------------------------------ events

def load_question() -> dict:
    return json.loads((REFS / "risk.json").read_text())


def features_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("features", HERE / "features.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


JUDGMENTS = ("features", "systemone", "both")


def scrubbed(state: dict) -> dict:
    """The state as it is logged: secrets by shape and the station term list masked. The model gets the raw state;
    the log on disk never holds a value the labeler would have to scrub later."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("scrub", HERE / "scrub.py")
        scrub = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scrub)
        return scrub.scrub_value(state, scrub.load_terms(), {})
    except Exception:  # noqa: BLE001 - a scrub failure must not become a stalled call; log the shape only
        return {"tool_name": state.get("tool_name"), "cwd": state.get("cwd"), "permission_mode": state.get("permission_mode"),
                "tool_input": "<not logged: scrub unavailable>"}


def pre_tool_use(payload: dict, cfg: dict) -> dict | None:
    tool = str(payload.get("tool_name", ""))
    mode = resolve_mode(cfg, "PreToolUse", str(payload.get("permission_mode", "")))
    if mode == "off" or not WATCHED_TOOLS.match(tool):
        return None
    session = str(payload.get("session_id", ""))
    judgment = str(cfg.get("judgment") or "features")
    if judgment not in JUDGMENTS:
        judgment = "features"
    start = time.monotonic()   # the clock starts before the state is built, so the latency is the hook's whole cost
    state = build_state(payload)
    record = {"ts": now(), "event": "PreToolUse", "session_id": session, "tool_use_id": payload.get("tool_use_id"),
              "permission_mode": payload.get("permission_mode"), "mode": mode, "tool_name": tool, "judgment": judgment,
              "model": cfg["model"] if judgment != "features" else None, "state": scrubbed(state), "outcome": "none",
              "reason": "", "flag": None, "category": None, "score": None, "features": None, "probs": None, "latency_ms": None}
    output = None
    try:
        hit = None   # (flag, probability or score, description)
        if judgment in ("features", "both"):
            # features are read from the raw input, before the cut and the scrub, so a long or
            # masked command is judged on what will run
            fe = features_module()
            verdict = fe.judge(tool, payload.get("tool_input"), str(payload.get("cwd", "")), fe.load_weights())
            record["score"], record["features"] = verdict["score"], verdict["features"]
            if verdict["flag"]:
                hit = (verdict["category"] or "risk", verdict["score"], "features: " + ", ".join(verdict["features"][:4]))
        if hit is None and judgment in ("systemone", "both"):
            question = load_question()
            client = Client(cfg["base_url"], start + float(cfg["client_timeout_s"]))
            check_slot(client, cfg, cfg["model"], loaded_models(client))
            reply = client.call("POST", "/v1/systemone",
                                {"model": cfg["model"], "state": state, "keep_alive": cfg["keep_alive"],
                                 "questions": {question["name"]: question["question"]}})
            record["probs"] = parse_probabilities(reply, question["name"])
            model_hit = decide_risk(record["probs"], question)
            if model_hit:
                hit = (model_hit[0], model_hit[1], describe(model_hit[0], question))
        if hit:
            record["flag"], record["category"] = hit[0], hit[0]
            if session_count(session) >= int(cfg["escalation_cap"]):
                record["outcome"] = "capped"
            else:
                record["outcome"] = "ask"
                session_count(session, bump=True)
                output = hook_output("PreToolUse", True, f"decision-hook: {hit[0]} (p={hit[1]:.2f}) - {hit[2]}; review this call")
    except HookError as e:
        record["outcome"], record["reason"] = e.outcome, str(e)
    record["latency_ms"] = round((time.monotonic() - start) * 1000)
    log_record(record)
    return output if mode == "active" else None


def describe(option: str, question: dict) -> str:
    return (question.get("question", {}).get("criteria") or {}).get(option) or option


def user_prompt_submit(payload: dict, cfg: dict) -> dict | None:
    prompt = str(payload.get("prompt", "")).strip()
    mode = resolve_mode(cfg, "UserPromptSubmit", str(payload.get("permission_mode", "")))
    if mode == "off" or not prompt:
        return None
    record = {"ts": now(), "event": "UserPromptSubmit", "session_id": payload.get("session_id"),
              "permission_mode": payload.get("permission_mode"), "mode": mode, "model": cfg["embed_model"],
              "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "prompt_chars": len(prompt),
              "outcome": "none", "reason": "", "skill": None, "similarity": None, "latency_ms": None}
    start = time.monotonic()
    output = None
    try:
        try:
            index = json.loads(index_path().read_text())
        except (OSError, ValueError):
            raise HookError("error", "routing index missing or unreadable; run build_index.py")
        client = Client(cfg["base_url"], start + float(cfg["client_timeout_s"]))
        loaded = loaded_models(client)
        others = [str(m.get("name") or "") for m in loaded if not same_model(str(m.get("name") or ""), cfg["embed_model"])]
        if others:
            raise HookError("skipped", "another model loaded: " + ", ".join(others))
        reply = client.call("POST", "/api/embed", {"model": cfg["embed_model"], "input": prompt[:4000],
                                                   "keep_alive": cfg["keep_alive"]})
        vectors = reply.get("embeddings") if isinstance(reply, dict) else None
        if not vectors or not isinstance(vectors[0], list):
            raise HookError("error", "embed reply holds no vector")
        skill, sim = route(vectors[0], index)
        record["similarity"] = sim
        if skill:
            record["outcome"], record["skill"] = "suggest", skill
            output = context_output(f"Suggested skill: {skill} (similarity {sim:.2f}); ignore if it does not fit.")
    except HookError as e:
        record["outcome"], record["reason"] = e.outcome, str(e)
    record["latency_ms"] = round((time.monotonic() - start) * 1000)
    log_record(record)
    return output if mode == "active" else None


def session_start(payload: dict, cfg: dict) -> None:
    """Warm the decision model once per session so the first PreToolUse call is not a cold load."""
    record = {"ts": now(), "event": "SessionStart", "session_id": payload.get("session_id"), "model": cfg["model"],
              "outcome": "warm", "reason": "", "latency_ms": None}
    start = time.monotonic()
    try:
        client = Client(cfg["base_url"], start + float(cfg["warm_timeout_s"]))
        check_slot(client, cfg, cfg["model"], loaded_models(client))
        question = load_question()
        client.call("POST", "/v1/systemone", {"model": cfg["model"], "state": "warm-up", "keep_alive": cfg["keep_alive"],
                                              "questions": {question["name"]: question["question"]}})
    except HookError as e:
        record["outcome"], record["reason"] = e.outcome, str(e)
    record["latency_ms"] = round((time.monotonic() - start) * 1000)
    log_record(record)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ operator commands

def cmd_report(days: int) -> int:
    path = state_dir() / "decisions.jsonl"
    if not path.exists():
        print("no decisions logged yet")
        return 0
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat(timespec="seconds")
    groups: dict = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if str(r.get("ts", "")) < since:
            continue
        key = (str(r.get("ts", ""))[:10], str(r.get("event")), str(r.get("permission_mode")), str(r.get("mode")))
        g = groups.setdefault(key, {"n": 0, "outcomes": {}, "flags": {}, "skills": {}, "lat": []})
        g["n"] += 1
        g["outcomes"][r.get("outcome")] = g["outcomes"].get(r.get("outcome"), 0) + 1
        if r.get("flag"):
            g["flags"][r["flag"]] = g["flags"].get(r["flag"], 0) + 1
        if r.get("skill"):
            g["skills"][r["skill"]] = g["skills"].get(r["skill"], 0) + 1
        if isinstance(r.get("latency_ms"), (int, float)):
            g["lat"].append(r["latency_ms"])
    print(f"{'day':10s} {'event':17s} {'perm mode':18s} {'mode':7s} {'n':>5s} {'p95 ms':>7s}  outcomes / flags / skills")
    for key in sorted(groups):
        g = groups[key]
        lat = sorted(g["lat"])
        p95 = lat[max(0, int(0.95 * len(lat)) - 1)] if lat else 0
        parts = [", ".join(f"{k}={v}" for k, v in sorted(g["outcomes"].items()))]
        if g["flags"]:
            parts.append("flags " + ", ".join(f"{k}={v}" for k, v in sorted(g["flags"].items())))
        if g["skills"]:
            parts.append("skills " + ", ".join(f"{k}={v}" for k, v in sorted(g["skills"].items())))
        print(f"{key[0]:10s} {key[1]:17s} {key[2]:18s} {key[3]:7s} {g['n']:5d} {p95:7.0f}  " + " / ".join(parts))
    return 0


def cmd_doctor() -> int:
    failures = 0

    def say(ok: bool, msg: str) -> None:
        nonlocal failures
        failures += 0 if ok else 1
        print(f"{'ok  ' if ok else 'FAIL'} {msg}")

    cfg = load_config()
    say(True, f"config {'at ' + str(config_path()) if config_path().exists() else 'is the built-in default'}")
    judgment = str(cfg.get("judgment") or "features")
    say(judgment in JUDGMENTS, f"judgment {judgment}" + (" (deterministic call features, no model on the hot path)" if judgment == "features" else ""))
    for event, table in cfg["modes"].items():
        active = [m for m, v in table.items() if v == "active"]
        print(f"     {event}: " + ", ".join(f"{m}={v}" for m, v in table.items()))
        if active:
            print(f"warn {event} is active in: {', '.join(active)}")
    say(is_loopback(cfg["base_url"]), f"endpoint {cfg['base_url']} is on loopback")
    try:
        client = Client(cfg["base_url"], time.monotonic() + 5)
        tags = client.call("GET", "/api/tags")
        names = [str(m.get("name") or "") for m in (tags.get("models") or [])]
        for key in ("model", "embed_model"):
            say(any(same_model(n, cfg[key]) for n in names), f"{key} {cfg[key]} is pulled")
        loaded = loaded_models(client)
        rss = runner_rss()
        budget = load_budget(cfg)
        say(True, f"loaded now: {', '.join(str(m.get('name')) for m in loaded) or 'nothing'}; "
                  f"{loaded_bytes(loaded, rss) / (1 << 30):.2f} GB resident against a {budget['max_total_gb']} GB cap, "
                  f"{budget['reserve_gb']} GB reserve")
        try:
            ping = client.call("POST", "/v1/systemone", {"model": cfg["model"], "state": "doctor", "keep_alive": cfg["keep_alive"],
                                                        "questions": {"q": {"type": "noul", "instructions": "Is this a test?"}}})
            say("answers" in ping, "/v1/systemone answers")
            if not loaded:
                unload(client, cfg["model"])   # doctor loaded it for the ping; a check leaves no model behind
        except HookError as e:
            say(False, f"/v1/systemone: {e}")
    except HookError as e:
        say(False, str(e))
    idx = index_path()
    routing_on = any(v != "off" for v in cfg["modes"].get("UserPromptSubmit", {}).values())
    if idx.exists():
        try:
            index = json.loads(idx.read_text())
            age = (time.time() - idx.stat().st_mtime) / 86400
            say(True, f"routing index: {len(index.get('exemplars') or [])} exemplars, threshold {index.get('threshold')}, {age:.0f} days old")
        except ValueError:
            say(False, "routing index is not JSON")
    elif routing_on:
        say(False, f"routing index missing at {idx}; run build_index.py")
    else:
        print(f"     routing is off; no index at {idx} (build_index.py creates one if routing is ever enabled)")
    if platform.system() == "Darwin":
        for name in ("OLLAMA_MAX_LOADED_MODELS", "OLLAMA_NUM_PARALLEL", "OLLAMA_KEEP_ALIVE"):
            try:
                value = subprocess.run(["/bin/launchctl", "getenv", name], capture_output=True, text=True, timeout=5).stdout.strip()
            except (OSError, subprocess.SubprocessError):
                value = ""
            print(f"     Ollama app: {name}={value or 'unset'}")
    say(True, f"state {state_dir()}")
    return 0 if failures == 0 else 1


# ------------------------------------------------------------------ entry

def read_payload() -> dict | None:
    try:
        raw = sys.stdin.read(4 << 20)
        payload = json.loads(raw)
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def run_hook(event: str) -> int:
    payload = read_payload()
    if payload is None:
        return 0
    try:
        cfg = load_config()
        if event == "pre-tool-use":
            output = pre_tool_use(payload, cfg)
        elif event == "user-prompt-submit":
            output = user_prompt_submit(payload, cfg)
        else:
            session_start(payload, cfg)
            output = None
        if output is not None:
            sys.stdout.write(json.dumps(output))
            sys.stdout.flush()
    except Exception as e:  # noqa: BLE001 - a hook defect must never become a stalled or blocked call
        try:
            log_record({"ts": now(), "event": event, "outcome": "error", "reason": f"hook defect: {type(e).__name__}"})
        except Exception:  # noqa: BLE001
            pass
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", nargs="?", choices=["doctor", "report"])
    parser.add_argument("--event", choices=["pre-tool-use", "user-prompt-submit", "session-start"])
    parser.add_argument("--days", type=int, default=14)
    a = parser.parse_args(argv)
    if a.command == "doctor":
        return cmd_doctor()
    if a.command == "report":
        return cmd_report(a.days)
    if not a.event:
        parser.error("pass --event or a command")
    return run_hook(a.event)


if __name__ == "__main__":
    sys.exit(main())
