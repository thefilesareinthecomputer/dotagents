#!/usr/bin/env python3
"""Hand one bounded task from a Claude Code session to a local model or a
self-run OpenAI-compatible gateway, keep the result on disk, print a capsule.

Commands: run, search, list, use, doctor. Stdlib only. SKILL.md is the
operator interface; tasks/SPEC-MODEL-TASK.md records the design.
"""

from __future__ import annotations

import argparse
import fcntl
import ipaddress
import json
import math
import os
import platform
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

EXIT_OK = 0
EXIT_ARGS = 2
EXIT_REFUSED = 3
EXIT_BACKEND = 4
EXIT_TIMEOUT = 5
EXIT_SCHEMA = 6
EXIT_INTERRUPTED = 130

REFS = Path(__file__).resolve().parent.parent / "references"
MAX_TIMEOUT = 1800
MAX_RESPONSE = 8 * 1024 * 1024
MAX_BRIEF = 64 * 1024
CAPSULE_LINES = 20
PRUNE_DAYS = 7
TRUNCATION_MARGIN = 64
KEEP_ALIVE = "1m"   # the longest a model outlives a run that died before it could unload
EVIDENCE_KEY = "evidence"
MIN_QUOTE = 4
NOT_ABSENT = "A short or empty list means nothing more relevant was among the matches, not that the target is absent."
TYPES = {"string": (str,), "number": (int, float), "boolean": (bool,), "array": (list,), "object": (dict,)}
MODEL_RE = re.compile(r"[A-Za-z0-9._:/@+-]{1,200}")
RUN_RE = re.compile(r"\d{8}-\d{6}-[0-9a-f]{6}")
MARKER_RE = re.compile(r"([1-9][0-9]{0,9})\.[0-9a-f]{8}", re.ASCII)

DEFAULT_CONFIG = {
    "default": "ollama",
    "backends": {
        "ollama": {"base_url": "http://127.0.0.1:11434", "api": "ollama",
                   "locality": "local", "default_model": "qwen3.5:4b"},
    },
}


class TaskError(Exception):
    def __init__(self, msg: str, code: int = EXIT_ARGS):
        super().__init__(msg)
        self.code = code


# ------------------------------------------------------------------ paths

def config_path() -> Path:
    return Path(os.environ.get("LOCAL_MODEL_TASK_CONFIG") or Path.home() / ".config" / "local-model-task" / "backends.json")


def state_dir() -> Path:
    return Path(os.environ.get("LOCAL_MODEL_TASK_STATE") or Path.home() / ".local" / "state" / "local-model-task")


def lock_path() -> Path:
    """One lock for every local run on the machine; LOCAL_MODEL_TASK_STATE does not move it."""
    return Path.home() / ".local" / "state" / "local-model-task" / "locks" / "local.lock"


def app_env(name: str) -> str | None:
    """A variable as the Ollama macOS app sees it (launchctl), or None when unset or unknown."""
    if platform.system() != "Darwin":
        return None
    try:
        out = subprocess.run(["/bin/launchctl", "getenv", name], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


# ------------------------------------------------------------------ locality

def host_is_loopback_literal(host: str) -> bool:
    host = host.strip("[]").split("%", 1)[0]
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def is_loopback_host(host: str) -> bool:
    """True when every address the host names is loopback."""
    if not host:
        return False
    if host != "localhost":
        return host_is_loopback_literal(host)
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    return bool(infos) and all(host_is_loopback_literal(info[4][0]) for info in infos)


def is_cloud_model(model: str) -> bool:
    """Ollama tags ending in cloud are served from Ollama's public API, never locally."""
    return re.search(r"(?i)[:-]cloud(?=$|@)", model) is not None


def is_ollama_public(host: str) -> bool:
    host = host.lower().rstrip(".")
    return host == "ollama.com" or host.endswith(".ollama.com")


def url_port(url: str) -> int:
    parts = urllib.parse.urlsplit(url)
    return parts.port or (443 if parts.scheme == "https" else 80)


def validate_backend(name: str, b: object) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", name):
        raise TaskError(f"backend name {name!r} must be letters, digits, '-' or '_'")
    if not isinstance(b, dict):
        raise TaskError(f"backend {name}: must be an object")
    for key in ("base_url", "api", "locality", "default_model"):
        if not isinstance(b.get(key), str) or not b[key]:
            raise TaskError(f"backend {name}: '{key}' is required")
    if b["api"] not in ("ollama", "openai"):
        raise TaskError(f"backend {name}: api must be 'ollama' or 'openai'")
    if b["locality"] not in ("local", "private", "hosted"):
        raise TaskError(f"backend {name}: locality must be 'local', 'private' or 'hosted'")
    env = b.get("api_key_env")
    if env is not None and not (isinstance(env, str) and re.fullmatch(r"[A-Z_][A-Z0-9_]*", env)):
        raise TaskError(f"backend {name}: api_key_env must name an environment variable, never hold a key")
    parts = urllib.parse.urlsplit(b["base_url"])
    host = parts.hostname or ""
    if parts.scheme not in ("http", "https") or not host:
        raise TaskError(f"backend {name}: base_url must be an http or https URL")
    if is_ollama_public(host):
        raise TaskError(f"backend {name}: {host} is Ollama's public API, which is refused", EXIT_REFUSED)
    if parts.username or parts.password:
        raise TaskError(f"backend {name}: base_url must not carry credentials")
    loopback = is_loopback_host(host)
    if b["locality"] == "local" and not loopback:
        raise TaskError(f"backend {name}: locality is local but {host} is not loopback", EXIT_REFUSED)
    if not loopback and parts.scheme != "https":
        raise TaskError(f"backend {name}: only loopback addresses may use plain http")


def load_config() -> dict:
    path = config_path()
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        cfg = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise TaskError(f"cannot read {path}: {e}")
    if not isinstance(cfg, dict) or not isinstance(cfg.get("backends"), dict) or not cfg["backends"]:
        raise TaskError(f"{path}: needs a non-empty 'backends' object")
    for name, b in cfg["backends"].items():
        validate_backend(name, b)
    if cfg.get("default") not in cfg["backends"]:
        raise TaskError(f"{path}: default backend {cfg.get('default')!r} is not defined")
    return cfg


def save_config(cfg: dict) -> None:
    path = config_path()
    if not path.parent.exists():
        path.parent.mkdir(parents=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".backends-")
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, (json.dumps(cfg, indent=2) + "\n").encode())
    finally:
        os.close(fd)
    os.replace(tmp, path)


# ------------------------------------------------------------------ listeners and memory

def parse_netstat(text: str, port: int) -> list[str]:
    """Hosts listening on `port` in macOS `netstat -an -p tcp` output."""
    hosts = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[0].startswith("tcp") and parts[-1] == "LISTEN":
            host, _, p = parts[3].rpartition(".")
            if p == str(port):
                hosts.append(host)
    return hosts


def parse_ss(text: str, port: int) -> list[str]:
    """Hosts listening on `port` in Linux `ss -ltnH` output."""
    hosts = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0] == "LISTEN":
            host, _, p = parts[3].rpartition(":")
            if p == str(port):
                hosts.append(host.strip("[]").split("%", 1)[0])
    return hosts


def listening_hosts(port: int) -> list[str] | None:
    """Every address listening on `port`, or None when it cannot be read."""
    try:
        if platform.system() == "Darwin":
            out = subprocess.run(["netstat", "-an", "-p", "tcp"], capture_output=True, text=True, timeout=15)
            return parse_netstat(out.stdout, port) if out.returncode == 0 else None
        if platform.system() == "Linux" and shutil.which("ss"):
            out = subprocess.run(["ss", "-ltnH"], capture_output=True, text=True, timeout=15)
            return parse_ss(out.stdout, port) if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def exposed_hosts(hosts: list[str]) -> list[str]:
    return [h for h in hosts if not host_is_loopback_literal(h)]


def check_listener(port: int) -> list[str]:
    hosts = listening_hosts(port)
    if hosts is None:
        raise TaskError(f"cannot read the listening sockets to confirm port {port} is loopback-only", EXIT_REFUSED)
    exposed = exposed_hosts(hosts)
    if exposed:
        raise TaskError(f"the server on port {port} also listens on {', '.join(sorted(set(exposed)))}; "
                        f"bind it to 127.0.0.1 only", EXIT_REFUSED)
    return hosts


def free_memory_bytes() -> int | None:
    try:
        if platform.system() == "Darwin":
            def sysctl(name):
                return int(subprocess.run(["sysctl", "-n", name], capture_output=True, text=True,
                                          timeout=10, check=True).stdout.strip())
            return sysctl("hw.memsize") * sysctl("kern.memorystatus_level") // 100
        if platform.system() == "Linux":
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return None


def check_memory(min_gb: float) -> None:
    if min_gb <= 0:
        return
    free = free_memory_bytes()
    if free is None:
        raise TaskError("cannot measure free memory; pass --min-free-gb 0 to skip the check")
    if free < min_gb * (1 << 30):
        raise TaskError(f"only {free / (1 << 30):.1f} GB of memory is free and a local run needs "
                        f"{min_gb:g} GB (--min-free-gb)")


# ------------------------------------------------------------------ helpers

def check_schema(obj: object, schema: dict) -> list[str]:
    if not isinstance(obj, dict):
        return ["the reply is not a JSON object"]
    problems = []
    for key, typ in schema.items():
        if key not in obj:
            problems.append(f"missing key '{key}'")
            continue
        value = obj[key]
        ok = isinstance(value, TYPES[typ]) and not (typ == "number" and isinstance(value, bool))
        if not ok:
            problems.append(f"'{key}' should be {typ}")
    return problems


def load_schema(path: str) -> dict:
    try:
        schema = json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        raise TaskError(f"cannot read schema {path}: {e}")
    if not isinstance(schema, dict) or not schema or any(t not in TYPES for t in schema.values()):
        raise TaskError(f"schema {path} must map keys to one of: {', '.join(TYPES)}")
    if EVIDENCE_KEY in schema:
        raise TaskError(f"schema {path} may not define '{EVIDENCE_KEY}', which the script reserves")
    return schema


def _norm(text: str) -> str:
    return " ".join(text.split())


def locate_quote(quote, sources: list[tuple[str, str]]) -> str | None:
    """Where an evidence quote appears verbatim, whitespace aside: 'path:line', 'path', or None."""
    if not isinstance(quote, str) or len(_norm(quote)) < MIN_QUOTE:
        return None
    q = _norm(quote)
    for path, text in sources:
        for number, line in enumerate(text.splitlines(), 1):
            if q in _norm(line):
                return f"{path}:{number}"
    for path, text in sources:
        if q in _norm(text):
            return path
    return None


def verify_evidence(obj: dict, schema: dict, sources: list[tuple[str, str]]) -> dict:
    quotes = obj.pop(EVIDENCE_KEY, None)
    quotes = quotes if isinstance(quotes, dict) else {}
    out = {}
    for key in schema:
        quote = quotes.get(key)
        location = locate_quote(quote, sources)
        out[key] = {"quote": quote if isinstance(quote, str) else None, "location": location,
                    "supported": location is not None}
    return out


def size_ctx(prompt_chars: int, max_ctx: int, output_tokens: int = 2048) -> int:
    """Context window for a prompt: a generous token estimate plus the reply budget, in 1K steps."""
    estimate = math.ceil(prompt_chars / 3) + output_tokens
    ctx = max(4096, math.ceil(estimate / 1024) * 1024)
    if ctx > max_ctx:
        raise TaskError(f"the prompt needs about {ctx} tokens of context, over --max-ctx {max_ctx}; send less input")
    return ctx


def is_truncated(prompt_eval_count, num_ctx: int) -> bool:
    return isinstance(prompt_eval_count, int) and prompt_eval_count >= num_ctx - TRUNCATION_MARGIN


def parse_match(line: str):
    """One `path NUL line:text` record from rg or grep run with --null."""
    path, sep, rest = line.rstrip("\n").partition("\x00")
    m = re.match(r"^(\d+):(.*)$", rest) if sep else None
    if not m or not path:
        return None
    path = path[2:] if path.startswith("./") else path
    return path, int(m.group(1)), m.group(2)[:300]


def filter_hits(raw: object, n_matches: int) -> tuple[list[dict], int]:
    raw = raw if isinstance(raw, list) else []
    kept, seen = [], set()
    for hit in raw:
        hid = hit.get("id") if isinstance(hit, dict) else None
        if isinstance(hid, int) and not isinstance(hid, bool) and 1 <= hid <= n_matches and hid not in seen:
            seen.add(hid)
            reason = hit.get("reason") if isinstance(hit.get("reason"), str) else ""
            kept.append({"id": hid, "reason": reason.strip()[:200]})
    return kept, len(raw) - len(kept)


def strip_fences(text: str) -> str:
    m = re.match(r"^\s*```[A-Za-z]*\s*\n(.*?)\n?```\s*$", text, re.S)
    return (m.group(1) if m else text).strip()


def redact(text: str, secret: str | None) -> str:
    return text.replace(secret, "[redacted]") if secret else text


def check_timeout(value: int) -> int:
    if not 1 <= value <= MAX_TIMEOUT:
        raise TaskError(f"--timeout must be between 1 and {MAX_TIMEOUT} seconds")
    return value


def check_model(model: str) -> str:
    if not MODEL_RE.fullmatch(model):
        raise TaskError(f"model name {model!r} has characters a model name does not use")
    if is_cloud_model(model):
        raise TaskError(f"{model} is an Ollama cloud model, served from Ollama's public API; refused", EXIT_REFUSED)
    return model


def render(template: str, **values: str) -> str:
    text = (REFS / template).read_text()
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


# ------------------------------------------------------------------ backend calls

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, f"redirect to {newurl} refused", headers, fp)


def request_json(method: str, url: str, body: dict | None, headers: dict, timeout: int, secret: str | None):
    handlers = [NoRedirect()]
    if is_loopback_host(urllib.parse.urlsplit(url).hostname or ""):
        handlers.append(urllib.request.ProxyHandler({}))
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", "Accept": "application/json", **headers})
    try:
        with urllib.request.build_opener(*handlers).open(req, timeout=timeout) as resp:
            raw = resp.read(MAX_RESPONSE + 1)
    except urllib.error.HTTPError as e:
        try:
            detail = e.read(500).decode("utf-8", "replace").strip()
        except (OSError, AttributeError):
            detail = ""
        raise TaskError(redact(f"backend returned HTTP {e.code}: {detail or e.reason}", secret), EXIT_BACKEND)
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            raise TaskError(f"backend did not answer within {timeout} s", EXIT_TIMEOUT)
        raise TaskError(redact(f"cannot reach backend: {e.reason}", secret), EXIT_BACKEND)
    except TimeoutError:
        raise TaskError(f"backend did not answer within {timeout} s", EXIT_TIMEOUT)
    except ValueError:
        # http.client rejects a malformed header with the header value in the message; never echo it
        raise TaskError("the request could not be built; check the backend URL and key for stray characters")
    except OSError as e:
        raise TaskError(redact(f"backend connection failed: {e}", secret), EXIT_BACKEND)
    if len(raw) > MAX_RESPONSE:
        raise TaskError("backend reply is larger than 8 MB", EXIT_BACKEND)
    try:
        return json.loads(raw)
    except ValueError:
        raise TaskError("backend reply is not JSON", EXIT_BACKEND)


def backend_key(b: dict) -> str | None:
    env = b.get("api_key_env")
    if not env:
        return None
    key = os.environ.get(env)
    if not key:
        raise TaskError(f"{env} is not set; this backend reads its key from that variable")
    if key != key.strip() or any(ord(c) < 0x21 or ord(c) == 0x7F for c in key):
        raise TaskError(f"{env} holds whitespace or control characters; fix the variable")
    return key


def model_entries(b: dict, key: str | None, timeout: int = 5) -> list[dict]:
    """The backend's model list as dicts with at least a 'name'."""
    base = b["base_url"].rstrip("/")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    if b["api"] == "ollama":
        data = request_json("GET", base + "/api/tags", None, headers, timeout, key)
        return [m for m in data.get("models", []) if isinstance(m, dict) and m.get("name")]
    data = request_json("GET", base + "/models", None, headers, timeout, key)
    return [{"name": m["id"]} for m in data.get("data", []) if isinstance(m, dict) and m.get("id")]


def remote_of(entry: dict) -> str | None:
    """Where an Ollama model is actually served, when that is not this machine."""
    return entry.get("remote_host") or entry.get("remote_model") or None


def find_entry(entries: list[dict], model: str) -> dict | None:
    names = {model, model + ":latest"} if ":" not in model else {model}
    return next((e for e in entries if e["name"] in names), None)


def refuse_remote(entry: dict | None, model: str) -> None:
    remote = remote_of(entry) if entry else None
    if remote:
        raise TaskError(f"{model} is served from {remote}, Ollama's public API, not this machine; refused",
                        EXIT_REFUSED)


def check_ollama_model(b: dict, model: str, key: str | None) -> None:
    """Refuse a model Ollama serves from elsewhere, whatever its name, and one that is not installed."""
    entry = find_entry(model_entries(b, key), model)
    if entry is None:
        raise TaskError(f"{model} is not installed in Ollama; run `ollama pull {model}`")
    refuse_remote(entry, model)


def check_ollama_behind_openai(b: dict, model: str, key: str | None) -> None:
    """An openai-api backend on loopback may be Ollama's /v1 route; ask its /api/tags where the model lives."""
    parts = urllib.parse.urlsplit(b["base_url"])
    probe = {"base_url": f"{parts.scheme}://{parts.netloc}", "api": "ollama"}
    try:
        entries = model_entries(probe, key)
    except TaskError:
        return  # not an Ollama server
    refuse_remote(find_entry(entries, model), model)


def call_model(b: dict, model: str, prompt: str, key: str | None, opts: argparse.Namespace,
               want_json: bool, temperature: float | None, num_ctx: int | None) -> dict:
    base = b["base_url"].rstrip("/")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    messages = [{"role": "user", "content": prompt}]
    if b["api"] == "ollama":
        options = {"num_ctx": num_ctx, "num_predict": opts.max_output_tokens}
        if temperature is not None:
            options["temperature"] = temperature
        body = {"model": model, "messages": messages, "stream": False, "think": bool(opts.think),
                "keep_alive": KEEP_ALIVE, "options": options}
        if want_json:
            body["format"] = "json"
        data = request_json("POST", base + "/api/chat", body, headers, opts.timeout, key)
        text = (data.get("message") or {}).get("content") or ""
        prompt_tokens, output_tokens = data.get("prompt_eval_count"), data.get("eval_count")
        if is_truncated(prompt_tokens, num_ctx):
            raise TaskError(f"the prompt reached {prompt_tokens} tokens against a {num_ctx}-token window, so the "
                            f"backend cut part of it; send less input or raise --max-ctx", EXIT_BACKEND)
    else:
        body = {"model": model, "messages": messages, "stream": False, "max_tokens": opts.max_output_tokens}
        if temperature is not None:
            body["temperature"] = temperature
        if want_json:
            body["response_format"] = {"type": "json_object"}
        data = request_json("POST", base + "/chat/completions", body, headers, opts.timeout, key)
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise TaskError("backend reply has no choices[0].message.content", EXIT_BACKEND)
        usage = data.get("usage") or {}
        prompt_tokens, output_tokens = usage.get("prompt_tokens"), usage.get("completion_tokens")
    if not text.strip():
        raise TaskError("the model returned an empty reply", EXIT_BACKEND)
    return {"text": text, "prompt_tokens": prompt_tokens, "output_tokens": output_tokens}


# ------------------------------------------------------------------ runs

def new_run_dir() -> Path:
    root = state_dir()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    cutoff = time.time() - PRUNE_DAYS * 86400
    for old in root.iterdir():
        if (RUN_RE.fullmatch(old.name) and old.is_dir() and not old.is_symlink()
                and old.stat().st_mtime < cutoff):
            shutil.rmtree(old, ignore_errors=True)
    run = root / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"
    run.mkdir(mode=0o700)
    return run


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class LocalLock:
    """One request at a time to a local backend; waits up to the run's timeout.

    A waiting run leaves a marker named for its pid in waiting/, so the run that
    holds the lock can tell whether anyone is queued behind it.
    """

    def __init__(self, active: bool, timeout: int):
        self.active, self.timeout, self.fd = active, timeout, None
        self.waiting = lock_path().parent / "waiting"

    def __enter__(self):
        if not self.active:
            return self
        path = lock_path()
        self.waiting.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path.parent, 0o700)
        marker = self.waiting / f"{os.getpid()}.{secrets.token_hex(4)}"
        deadline = time.monotonic() + self.timeout
        try:
            marker.touch(mode=0o600)
            self.fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
            while True:
                try:
                    fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return self
                except BlockingIOError:
                    if time.monotonic() > deadline:
                        os.close(self.fd)
                        self.fd = None
                        raise TaskError("another local run held the model past --timeout", EXIT_TIMEOUT)
                    time.sleep(0.25)
        finally:
            marker.unlink(missing_ok=True)

    def others_waiting(self) -> int:
        """Live runs queued behind this one. Only marker-shaped files count; a marker whose process
        is gone, or older than any run can wait, is removed; anything else is left alone."""
        if not self.waiting.is_dir() or self.waiting.is_symlink():
            return 0
        count, stale_before = 0, time.time() - (MAX_TIMEOUT + 60)
        for marker in self.waiting.iterdir():
            m = MARKER_RE.fullmatch(marker.name)
            if not m or not marker.is_file() or marker.is_symlink():
                continue
            try:
                if marker.stat().st_mtime >= stale_before and pid_alive(int(m.group(1))):
                    count += 1
                else:
                    marker.unlink(missing_ok=True)
            except OSError:
                continue
        return count

    def __exit__(self, *exc):
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)


def unload_ollama(b: dict, model: str, key: str | None) -> bool:
    """Ask Ollama to drop the model from memory now; best effort, since KEEP_ALIVE bounds it anyway."""
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        request_json("POST", b["base_url"].rstrip("/") + "/api/generate",
                     {"model": model, "keep_alive": 0}, headers, 10, key)
        return True
    except TaskError:
        return False


def settle(lock: LocalLock, b: dict, model: str, key: str | None, report: dict) -> None:
    """After a run that reached a local Ollama model: unload it unless another local run is waiting.
    Never raises, since it runs in a finally block; a remote Ollama is never told to unload."""
    if b["api"] != "ollama" or b["locality"] != "local":
        return
    try:
        waiting = lock.others_waiting() if lock.active else 0
        report["unloaded"] = False if waiting else unload_ollama(b, model, key)
        if waiting:
            report["left_loaded_for"] = waiting
    except Exception as e:  # noqa: BLE001 - the run's own result matters more than this cleanup
        report["unloaded"] = False
        report["unload_error"] = str(e)[:200]


def resolve(cfg: dict, a: argparse.Namespace) -> tuple[str, dict, str, str | None]:
    name = a.backend or cfg["default"]
    if name not in cfg["backends"]:
        raise TaskError(f"no backend named {name!r}; known: {', '.join(cfg['backends'])}")
    b = cfg["backends"][name]
    model = check_model(a.model or b["default_model"])
    if b["locality"] == "hosted" and not a.allow_hosted:
        raise TaskError(f"backend {name} is run by a third party; pass --allow-hosted only after the user agrees "
                        f"to send this material there", EXIT_REFUSED)
    key = backend_key(b)
    return name, b, model, key


def preflight(b: dict, model: str, key: str | None, min_free_gb: float) -> None:
    host = urllib.parse.urlsplit(b["base_url"]).hostname or ""
    if is_loopback_host(host):
        check_listener(url_port(b["base_url"]))
    if b["locality"] == "local":
        check_memory(min_free_gb)
    if b["api"] == "ollama":
        check_ollama_model(b, model, key)
    elif is_loopback_host(host):
        check_ollama_behind_openai(b, model, key)


def read_brief(src: str) -> str:
    text = sys.stdin.read(MAX_BRIEF + 1) if src == "-" else _read_text(Path(src), "brief")
    if len(text) > MAX_BRIEF:
        raise TaskError("the brief is over 64 KB; put material in --input files instead")
    if not text.strip():
        raise TaskError("the brief is empty")
    return text.strip()


def _read_text(path: Path, label: str) -> str:
    if not path.is_file():
        raise TaskError(f"{label} {path} is not a regular file")
    data = path.read_bytes()
    if b"\x00" in data[:8192]:
        raise TaskError(f"{label} {path} looks binary")
    return data.decode("utf-8", "replace")


def read_inputs(paths: list[str], max_kb: int) -> list[tuple[str, str]]:
    out, total = [], 0
    for raw in paths:
        p = Path(raw)
        if p.is_file():
            total += p.stat().st_size
            if total > max_kb * 1024:
                raise TaskError(f"inputs add up to more than --max-input-kb {max_kb}")
        out.append((raw, _read_text(p, "input")))
    return out


def report_line(name: str, b: dict, model: str, result: dict | None, elapsed: float) -> str:
    parts = [f"backend {name} ({b['locality']})", f"model {model}"]
    if result:
        if result.get("prompt_tokens") is not None:
            parts.append(f"{result['prompt_tokens']} prompt tokens")
        if result.get("output_tokens") is not None:
            parts.append(f"{result['output_tokens']} output tokens")
    parts.append(f"{elapsed:.1f} s")
    return ", ".join(parts)


def display_path(location: str) -> str:
    """A location relative to the working directory when it sits under it, as given otherwise."""
    path, sep, line = location.rpartition(":") if re.search(r":\d+$", location) else (location, "", "")
    try:
        rel = os.path.relpath(path)
    except ValueError:
        rel = path
    return (path if rel.startswith("..") else rel) + sep + line


def head(text: str) -> str:
    lines = text.rstrip("\n").splitlines()
    shown = "\n".join(lines[:CAPSULE_LINES])
    return shown + (f"\n... ({len(lines) - CAPSULE_LINES} more lines)" if len(lines) > CAPSULE_LINES else "")


def write(run: Path, name: str, text: str) -> None:
    (run / name).write_text(text if text.endswith("\n") else text + "\n")


def finish(run: Path, report: dict, code: int, error: str | None = None) -> None:
    report.update(exit_code=code, error=error)
    write(run, "report.json", json.dumps(report, indent=2))


def cmd_run(a: argparse.Namespace) -> int:
    a.timeout = check_timeout(a.timeout)
    cfg = load_config()
    name, b, model, key = resolve(cfg, a)
    brief = read_brief(a.brief)
    schema = load_schema(a.schema) if a.schema else None
    inputs = read_inputs(a.input or [], a.max_input_kb)
    preflight(b, model, key, a.min_free_gb)
    files = "\n\n".join(f"--- file: {p} ---\n{t.rstrip()}\n--- end of file: {p} ---" for p, t in inputs) or "(none)"
    if schema:
        shape = ("Reply with one JSON object and nothing else. Required keys: "
                 + ", ".join(f"{k} ({t})" for k, t in schema.items()) + ". "
                 + f'Also include the key "{EVIDENCE_KEY}": an object mapping each of those keys to one exact '
                 + "phrase copied from the input files that supports its value.")
    else:
        shape = "Answer in plain text, concisely. Say plainly when the files do not hold what the task asks for."
    prompt = render("ask.md", TASK=brief, FILES=files, SHAPE=shape)
    num_ctx = (a.num_ctx or size_ctx(len(prompt), a.max_ctx, a.max_output_tokens)) if b["api"] == "ollama" else None

    run = new_run_dir()
    write(run, "brief.md", prompt)
    report = {"run_id": run.name, "mode": "run", "backend": name, "api": b["api"], "locality": b["locality"],
              "model": model, "num_ctx": num_ctx, "inputs": [p for p, _ in inputs], "schema": a.schema,
              "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    temperature = 0 if schema and a.temperature is None else a.temperature
    start = time.monotonic()
    try:
        with LocalLock(b["locality"] == "local", a.timeout) as lock:
            try:
                result = call_model(b, model, prompt, key, a, bool(schema), temperature, num_ctx)
            finally:
                settle(lock, b, model, key, report)
        report.update(prompt_tokens=result["prompt_tokens"], output_tokens=result["output_tokens"])
        if schema:
            try:
                obj = json.loads(strip_fences(result["text"]))
            except ValueError:
                obj = None
            problems = check_schema(obj, schema)
            if problems:
                write(run, "raw_output.md", result["text"])
                raise TaskError("the reply failed --schema: " + "; ".join(problems), EXIT_SCHEMA)
            evidence = verify_evidence(obj, schema, inputs or [("brief", brief)])
            supported = sum(1 for e in evidence.values() if e["supported"])
            report.update(evidence_supported=supported, evidence_fields=len(schema))
            write(run, "evidence.json", json.dumps(evidence, indent=2))
            write(run, "result.json", json.dumps(obj, indent=2))
            out_name = "result.json"
            body = "\n".join(
                f"{k}: {json.dumps(obj[k])[:120]}  "
                + (f"[{display_path(evidence[k]['location'])}] {json.dumps(evidence[k]['quote'][:100])}"
                   if evidence[k]["supported"] else "[unsupported: no quote found in the inputs]")
                for k in schema)
            body += (f"\n{supported} of {len(schema)} fields quote a line found in the inputs. A quote shows where to "
                     f"look, not that the value is right: check that each quoted line supports its value, and read "
                     f"the input for unsupported fields.")
        else:
            body, out_name = result["text"].strip(), "output.md"
            write(run, out_name, body)
    except TaskError as e:
        report["elapsed_s"] = round(time.monotonic() - start, 2)
        finish(run, report, e.code, str(e))
        e.args = (f"{e} (run {run})",)
        raise
    except KeyboardInterrupt:
        report["elapsed_s"] = round(time.monotonic() - start, 2)
        finish(run, report, EXIT_INTERRUPTED, "interrupted")
        print(f"local-model-task: interrupted; report.json records whether the model was unloaded (run {run})",
              file=sys.stderr)
        raise
    elapsed = time.monotonic() - start
    report["elapsed_s"] = round(elapsed, 2)
    finish(run, report, EXIT_OK)
    print(f"local-model-task run {run.name}: exit 0")
    print(report_line(name, b, model, result, elapsed))
    print("---")
    print(head(body))
    print("---")
    print(f"full {'result' if schema else 'output'}: {run / out_name}")
    return EXIT_OK


def is_hidden(path: str) -> bool:
    """Any path component that starts with a dot: .env, .npmrc, .git and the like."""
    return any(part.startswith(".") and part not in (".", "..") for part in Path(path).parts)


def collect_matches(patterns: list[str], root: Path, max_matches: int, max_bytes: int, timeout: int):
    """Matches under root, never from hidden files, which both engines are held to here."""
    rg = shutil.which("rg")
    pat_args = [arg for p in patterns for arg in ("-e", p)]
    if rg:
        argv, engine = [rg, "--no-config", "--null", "--line-number", "--no-heading", "--with-filename",
                        "--color", "never", *pat_args, "--", "."], "rg"
    else:
        argv, engine = [shutil.which("grep") or "grep", "-rnIE", "--null", "--exclude-dir=.git",
                        "--exclude-dir=node_modules", *pat_args, "--", "."], "grep"
    matches, size, capped = [], 0, False
    deadline = time.monotonic() + timeout
    proc = subprocess.Popen(argv, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, errors="replace")
    try:
        for line in proc.stdout:
            m = parse_match(line)
            if not m or is_hidden(m[0]):
                continue
            if len(matches) >= max_matches or size + len(line) > max_bytes or time.monotonic() > deadline:
                capped = True
                break
            matches.append(m)
            size += len(line)
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
    return matches, capped, engine


def cmd_search(a: argparse.Namespace) -> int:
    a.timeout = check_timeout(a.timeout)
    cfg = load_config()
    name, b, model, key = resolve(cfg, a)
    root = Path(a.path)
    if not root.is_dir():
        raise TaskError(f"--path {a.path} is not a directory")
    if any(not p or "\n" in p for p in a.pattern):
        raise TaskError("each --pattern must be a non-empty single line")
    preflight(b, model, key, a.min_free_gb)
    matches, capped, engine = collect_matches(a.pattern, root, a.max_matches, a.max_bytes, a.timeout)
    run = new_run_dir()
    report = {"run_id": run.name, "mode": "search", "backend": name, "api": b["api"], "locality": b["locality"],
              "model": model, "question": a.question, "patterns": a.pattern, "path": str(root.resolve()),
              "engine": engine, "matches_sent": len(matches), "matches_capped": capped,
              "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if not matches:
        finish(run, report, EXIT_OK)
        print(f"local-model-task search {run.name}: exit 0")
        print(f"No matches for these patterns under {root}; nothing was sent to the model.")
        return EXIT_OK
    listing = "\n".join(f"[{i}] {p}:{n}: {t}" for i, (p, n, t) in enumerate(matches, 1))
    prompt = render("search.md", QUESTION=a.question, MATCHES=listing, TOP=str(a.top))
    num_ctx = (a.num_ctx or size_ctx(len(prompt), a.max_ctx, a.max_output_tokens)) if b["api"] == "ollama" else None
    report["num_ctx"] = num_ctx
    write(run, "brief.md", prompt)
    start = time.monotonic()
    try:
        with LocalLock(b["locality"] == "local", a.timeout) as lock:
            try:
                result = call_model(b, model, prompt, key, a, True, 0, num_ctx)
            finally:
                settle(lock, b, model, key, report)
        report.update(prompt_tokens=result["prompt_tokens"], output_tokens=result["output_tokens"])
        try:
            obj = json.loads(strip_fences(result["text"]))
        except ValueError:
            obj = None
        if not isinstance(obj, dict) or not isinstance(obj.get("hits"), list):
            write(run, "raw_output.md", result["text"])
            raise TaskError('the reply is not a JSON object with a "hits" list', EXIT_SCHEMA)
        kept, dropped = filter_hits(obj["hits"], len(matches))
        if obj.get("answers_question") is False:
            kept, dropped = [], len(obj["hits"])
        kept = kept[:a.top]
        hits = [{"rank": r, "file": matches[h["id"] - 1][0], "line": matches[h["id"] - 1][1],
                 "text": matches[h["id"] - 1][2], "reason": h["reason"]} for r, h in enumerate(kept, 1)]
        report.update(hits_kept=len(hits), hits_dropped=dropped)
        write(run, "result.json", json.dumps({"question": a.question, "hits": hits}, indent=2))
    except TaskError as e:
        report["elapsed_s"] = round(time.monotonic() - start, 2)
        finish(run, report, e.code, str(e))
        e.args = (f"{e} (run {run})",)
        raise
    except KeyboardInterrupt:
        report["elapsed_s"] = round(time.monotonic() - start, 2)
        finish(run, report, EXIT_INTERRUPTED, "interrupted")
        print(f"local-model-task: interrupted; report.json records whether the model was unloaded (run {run})",
              file=sys.stderr)
        raise
    elapsed = time.monotonic() - start
    report["elapsed_s"] = round(elapsed, 2)
    finish(run, report, EXIT_OK)
    print(f"local-model-task search {run.name}: exit 0")
    print(report_line(name, b, model, result, elapsed)
          + f", {len(matches)} matches sent{' (capped by --max-matches or --max-bytes)' if capped else ''}"
          + f", {len(hits)} kept, {dropped} dropped")
    for h in hits:
        print(f"{h['rank']}. {h['file']}:{h['line']} - {h['reason']}")
    print(("No hits. " if not hits else "") + NOT_ABSENT)
    print(f"full result: {run / 'result.json'}")
    return EXIT_OK


def cmd_list(a: argparse.Namespace) -> int:
    cfg = load_config()
    for name, b in cfg["backends"].items():
        marker = "  (default backend)" if name == cfg["default"] else ""
        print(f"{name}: api {b['api']}, locality {b['locality']}, default model {b['default_model']}{marker}")
        if b["locality"] == "hosted" and not a.allow_hosted:
            print("  skipped: hosted backend; pass --allow-hosted to contact it")
            continue
        try:
            host = urllib.parse.urlsplit(b["base_url"]).hostname or ""
            if is_loopback_host(host):
                check_listener(url_port(b["base_url"]))
            for entry in model_entries(b, backend_key(b)):
                model = entry["name"]
                remote = remote_of(entry)
                status = (f"refused: served from {remote}" if remote
                          else "refused: Ollama cloud model" if is_cloud_model(model) else b["locality"])
                print(f"  {model}  {status}")
        except TaskError as e:
            print(f"  unavailable: {e}")
    return EXIT_OK


def cmd_use(a: argparse.Namespace) -> int:
    if "/" not in a.target:
        raise TaskError("use takes <backend>/<model>, for example ollama/qwen3.5:4b")
    name, model = a.target.split("/", 1)
    cfg = load_config()
    if name not in cfg["backends"]:
        raise TaskError(f"no backend named {name!r}; known: {', '.join(cfg['backends'])}")
    check_model(model)
    cfg["default"] = name
    cfg["backends"][name]["default_model"] = model
    save_config(cfg)
    print(f"default is now {name}/{model} ({config_path()})")
    return EXIT_OK


def cmd_doctor(a: argparse.Namespace) -> int:
    failures = 0

    def say(ok: bool, msg: str) -> None:
        nonlocal failures
        failures += 0 if ok else 1
        print(f"{'ok  ' if ok else 'FAIL'} {msg}")

    def warn(msg: str) -> None:
        print(f"warn {msg}")

    for where, value in (("shell", os.environ.get("OLLAMA_HOST")), ("Ollama app", app_env("OLLAMA_HOST"))):
        if value is None:
            say(True, f"{where}: OLLAMA_HOST is not set; the listener check below confirms the binding")
        else:
            host = urllib.parse.urlsplit(value if "://" in value else "//" + value).hostname or ""
            say(host_is_loopback_literal(host), f"{where}: OLLAMA_HOST={value} must name a loopback address")
    if platform.system() == "Darwin":
        for name, default in (("OLLAMA_MAX_LOADED_MODELS", "3"), ("OLLAMA_NUM_PARALLEL", "1")):
            value = app_env(name)
            if (value or default) == "1":
                say(True, f"Ollama app: {name}={value or 'unset (default 1)'}, so one at a time")
            else:
                warn(f"Ollama app: {name}={value or f'unset (default {default})'}, so more than one can run at "
                     f"once; `launchctl setenv {name} 1` and restart Ollama, then rerun after every reboot")
    try:
        cfg = load_config()
        say(True, f"config {'at ' + str(config_path()) if config_path().exists() else 'is the built-in default'}")
    except TaskError as e:
        say(False, str(e))
        return 1
    for name, b in cfg["backends"].items():
        if b["locality"] == "hosted" and not a.allow_hosted:
            print(f"skip {name}: hosted backend; pass --allow-hosted to contact it")
            continue
        host = urllib.parse.urlsplit(b["base_url"]).hostname or ""
        try:
            if is_loopback_host(host):
                hosts = check_listener(url_port(b["base_url"]))
                say(True, f"{name}: port {url_port(b['base_url'])} listens on "
                          f"{', '.join(sorted(set(hosts))) or 'nothing yet'} only")
            models = model_entries(b, backend_key(b))
            say(True, f"{name}: answers with {len(models)} models")
        except TaskError as e:
            say(False, f"{name}: {e}")
    return 0 if failures == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="local_model_task.py", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--backend")
        p.add_argument("--model")
        p.add_argument("--timeout", type=int, default=300, help=f"seconds, 1-{MAX_TIMEOUT}")
        p.add_argument("--min-free-gb", type=float, default=4.0, help="free memory a local run needs; 0 skips")
        p.add_argument("--max-ctx", type=int, default=32768, help="largest context window to request")
        p.add_argument("--num-ctx", type=int, help="exact context window, overriding the estimate")
        p.add_argument("--max-output-tokens", type=int, default=2048)
        p.add_argument("--think", action="store_true", help="let a thinking model reason first")
        p.add_argument("--allow-hosted", action="store_true", help="permit a hosted backend; ask the user first")

    r = sub.add_parser("run", help="send a brief and input files, get text or JSON back")
    r.add_argument("--brief", required=True, help="file holding the task, or - for stdin")
    r.add_argument("--input", action="append", help="file to include as data; repeatable")
    r.add_argument("--schema", help="JSON file mapping required keys to string/number/boolean/array/object")
    r.add_argument("--max-input-kb", type=int, default=80)
    r.add_argument("--temperature", type=float)
    common(r)
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("search", help="grep, then have the model rank the matches")
    s.add_argument("--question", required=True)
    s.add_argument("--pattern", action="append", required=True, help="regex both rg and grep -E accept; repeatable")
    s.add_argument("--path", required=True)
    s.add_argument("--max-matches", type=int, default=400)
    s.add_argument("--max-bytes", type=int, default=64 * 1024)
    s.add_argument("--top", type=int, default=10)
    common(s)
    s.set_defaults(func=cmd_search)

    lp = sub.add_parser("list", help="backends and their models")
    lp.add_argument("--allow-hosted", action="store_true", help="also contact hosted backends")
    lp.set_defaults(func=cmd_list)
    u = sub.add_parser("use", help="set the default backend and model")
    u.add_argument("target", help="<backend>/<model>")
    u.set_defaults(func=cmd_use)
    dp = sub.add_parser("doctor", help="check loopback binding, config and reachability")
    dp.add_argument("--allow-hosted", action="store_true", help="also contact hosted backends")
    dp.set_defaults(func=cmd_doctor)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except TaskError as e:
        print(f"local-model-task: {e}", file=sys.stderr)
        return e.code
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED


def _interrupt(signum, frame):
    raise KeyboardInterrupt


if __name__ == "__main__":
    # A Bash-tool timeout sends SIGTERM; turn it into an exception so the unload in settle() still runs.
    signal.signal(signal.SIGTERM, _interrupt)
    sys.exit(main())
