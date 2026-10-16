#!/usr/bin/env python3
"""support-local: hand one information goal to a goal-bound Haiku worker that
drives the local models, and check what comes back.

    support_local.py brief --goal TEXT --corpus PATH|INDEX|VAULT [--complete TEXT] [--out-of-scope TEXT]
                           [--budget-turns 30] [--budget-calls 20]
    support_local.py run --goal TEXT --corpus PATH [...brief options] [--model ID]   # headless worker via `claude -p`
    support_local.py verify --answer FILE|- [--corpus PATH]                         # schema and reference check
    support_local.py doctor

Stdlib only. The worker's model is asserted on every headless run; a mismatch is a refusal.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EXIT_OK = 0
EXIT_ARGS = 2
EXIT_REFUSED = 3
EXIT_WORKER = 4
EXIT_SCHEMA = 6

HERE = Path(__file__).resolve().parent
REFS = HERE.parent / "references"
AGENT = HERE.parent.parent.parent / "agents" / "support-local.md"
REQUIRED_MODEL_PREFIX = "claude-haiku-5-5"
TYPES = {"string": (str,), "number": (int, float), "boolean": (bool,), "array": (list,), "object": (dict,)}
REF_RE = re.compile(r"^(?P<path>[^:#]+?)(?::(?P<line>\d+)(?:-(?P<end>\d+))?)?$")
VAULT_REF_RE = re.compile(r"^vault:[A-Za-z0-9._-]+#\S+$")
MAX_GOAL = 2000
MAX_RESULT = 4 << 20
MIN_QUOTE = 8   # a shorter quote matches too easily to count as evidence


class TaskError(Exception):
    def __init__(self, msg: str, code: int = EXIT_ARGS):
        super().__init__(msg)
        self.code = code


def state_dir() -> Path:
    d = Path(os.environ.get("SUPPORT_LOCAL_STATE") or Path.home() / ".local" / "state" / "support-local")
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ brief

def agent_model() -> str:
    """The model pinned in the agent definition's frontmatter; the headless run uses the same one."""
    try:
        fm = AGENT.read_text(encoding="utf-8").split("---")[1]
    except (OSError, IndexError):
        return REQUIRED_MODEL_PREFIX
    m = re.search(r"^model:\s*(\S+)", fm, re.M)
    return m.group(1) if m else REQUIRED_MODEL_PREFIX


def agent_effort() -> str | None:
    """The effort pinned in the agent definition's frontmatter. A subagent gets it from the definition; a headless
    run gets the body with the frontmatter stripped, so the runner has to pass it as --effort itself."""
    try:
        fm = AGENT.read_text(encoding="utf-8").split("---")[1]
    except (OSError, IndexError):
        return None
    m = re.search(r"^effort:\s*(low|medium|high|xhigh|max)\s*$", fm, re.M)
    return m.group(1) if m else None


# The default is the local-first brief: on the 72-run goal matrix of 2026-10-09 it scored 22/24 against 18/24 for the
# full and terse briefs, at the lowest cost, and it was the only one that abstained on absent goals.
VARIANTS = {"default": "brief-template.md", "local-first": "brief-template.md", "full": "brief-full.md", "terse": "brief-terse.md"}


def build_brief(goal: str, corpus: str, complete: str, out_of_scope: str, budget_turns: int, budget_calls: int,
                variant: str = "default") -> str:
    goal = " ".join(goal.split())
    if not goal:
        raise TaskError("--goal is empty")
    if len(goal) > MAX_GOAL:
        raise TaskError(f"--goal is longer than {MAX_GOAL} characters; a goal is one sentence, the detail goes in --complete")
    if not corpus.strip():
        raise TaskError("--corpus is empty; name a path, an index or a vault")
    if budget_turns < 1 or budget_calls < 1:
        raise TaskError("budgets must be at least 1")
    if variant not in VARIANTS:
        raise TaskError(f"unknown brief variant {variant!r}; one of {', '.join(VARIANTS)}")
    template = (REFS / VARIANTS[variant]).read_text(encoding="utf-8")
    return template.format(goal=goal, corpus=corpus.strip(),
                           complete=complete.strip() or "Every part of the goal answered, each claim with a reference.",
                           out_of_scope=out_of_scope.strip() or "Anything outside the named corpus.",
                           budget_turns=budget_turns, budget_calls=budget_calls)


def cmd_brief(a: argparse.Namespace) -> int:
    sys.stdout.write(build_brief(a.goal, a.corpus, a.complete, a.out_of_scope, a.budget_turns, a.budget_calls, a.variant))
    return EXIT_OK


# ------------------------------------------------------------------ verify

def check_schema(obj: object, schema: dict) -> list[str]:
    if not isinstance(obj, dict):
        return ["the answer is not a JSON object"]
    problems = []
    for key, typ in schema.items():
        if key not in obj:
            problems.append(f"missing key '{key}'")
            continue
        value = obj[key]
        if not isinstance(value, TYPES[typ]) or (typ == "number" and isinstance(value, bool)):
            problems.append(f"'{key}' should be {typ}")
    return problems


def corpus_root(corpus: str, root: str | None) -> Path | None:
    """The directory evidence references resolve against: `--corpus-root` when given, else the corpus itself when it
    is a directory. An index or vault corpus with no root has none, and then no file reference can be verified."""
    if root:
        return Path(root).expanduser()
    p = Path(corpus).expanduser()
    return p if p.is_dir() else None


def resolve(ref: object, corpus: Path | None) -> tuple[Path | None, int | None, int | None, str]:
    """Where a reference points, as (path, line, end, why): a path the script can read inside the corpus, or
    (None, None, None, reason). A vault reference is only resolvable by the vault, so it stays unverified here."""
    if not isinstance(ref, str) or not ref.strip():
        return None, None, None, "no reference"
    ref = ref.strip()
    if VAULT_REF_RE.match(ref):
        return None, None, None, "vault reference; only the vault can confirm it"
    m = REF_RE.match(ref)
    if not m:
        return None, None, None, "unrecognized reference shape"
    path = Path(m.group("path")).expanduser()
    if corpus is None:
        return None, None, None, "no corpus root to resolve against; pass --corpus-root for an index or vault corpus"
    if not path.is_absolute():
        path = corpus / path
    try:
        path.resolve().relative_to(corpus.resolve())
    except ValueError:
        return None, None, None, "outside the corpus"
    if not path.is_file():
        return None, None, None, "file not found"
    if m.group("line") is None:
        return path, None, None, "file exists"
    line = int(m.group("line"))
    end = int(m.group("end")) if m.group("end") else line
    if end < line:
        return None, None, None, "line range runs backwards"
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            total = sum(1 for _ in f)
    except OSError:
        return None, None, None, "file unreadable"
    if end > total:
        return None, None, None, f"line {end} is past the end of the file"
    return path, line, end, "line exists" if end == line else "line range exists"


def _norm(text: str) -> str:
    """Whitespace removed, so a quote the worker re-spaced still matches the line it came from."""
    return "".join(text.split())


def quote_found(path: Path, line: int | None, end: int | None, quote: object) -> tuple[bool, str]:
    """Does the quoted text sit at the cited line (or range), whitespace aside, or anywhere in the file for a
    file-level reference? A line existing is not evidence; the text the worker relied on has to be there."""
    if not isinstance(quote, str) or not quote.strip():
        return False, "no quote to check against the cited line" if line else "no quote to check against the file"
    q = _norm(quote)
    if len(q) < MIN_QUOTE:
        return False, f"quote shorter than {MIN_QUOTE} characters"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False, "file unreadable"
    if line is None:
        return (True, "quote found in the file") if q in _norm(text) else (False, "quote not found in the file")
    span = text.splitlines()[line - 1:end]
    if q in _norm("\n".join(span)):
        return True, "quote found at the cited line"
    return False, "quote not found at the cited line"


def accept(claim: dict, corpus: Path | None) -> dict:
    """A claim is verified only when its reference resolves inside the corpus and its quote is at that reference;
    otherwise it is kept and marked unsupported, with the reason."""
    path, line, end, why = resolve(claim.get("ref"), corpus)
    if path is None:
        claim["verified"], claim["check"] = False, why
        return claim
    claim["verified"], claim["check"] = quote_found(path, line, end, claim.get("quote"))
    return claim


def verify_answer(obj: object, corpus: Path | None) -> dict:
    schema = json.loads((REFS / "answer.schema.json").read_text(encoding="utf-8"))
    problems = check_schema(obj, schema)
    if problems:
        raise TaskError("answer fails the schema: " + "; ".join(problems), EXIT_SCHEMA)
    evidence = []
    for claim in obj["evidence"]:
        if not isinstance(claim, dict):
            evidence.append({"claim": str(claim)[:300], "ref": None, "verified": False, "check": "claim is not an object"})
            continue
        quote = claim.get("quote")
        evidence.append(accept({"claim": str(claim.get("claim", ""))[:1000], "ref": claim.get("ref"),
                                "quote": quote[:500] if isinstance(quote, str) else None}, corpus))
    obj["evidence"] = evidence
    obj["verified_count"] = sum(1 for c in evidence if c["verified"])
    obj["unsupported_count"] = len(evidence) - obj["verified_count"]
    if obj["answerable"] and obj["verified_count"] == 0:
        # an answer nothing supports is not an answer; the worker's claims stay in the record as unsupported
        obj["answerable"] = False
        obj["downgraded"] = "answerable set to false: no claim verified"
    return obj


def capsule(obj: dict) -> str:
    lines = [f"answerable: {obj['answerable']}; evidence {obj['verified_count']} verified, {obj['unsupported_count']} unsupported; "
             f"local calls {obj['local_calls']}; stop: {obj['stop_reason']}",
             f"coverage: {obj['coverage'][:400]}",
             f"answer: {obj['answer'][:1200]}"]
    for c in obj["evidence"]:
        mark = "ok " if c["verified"] else "?? "
        lines.append(f"  {mark}{c['claim'][:160]}  [{c.get('ref')}; {c['check']}]")
    return "\n".join(lines)


def read_answer(src: str) -> object:
    text = sys.stdin.read(MAX_RESULT) if src == "-" else Path(src).read_text(encoding="utf-8")
    return parse_json_object(text)


def parse_json_object(text: str) -> object:
    """The worker's final message, which should be one JSON object; tolerate a fenced block or stray prose around it."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    obj = None
    try:
        obj = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                obj = json.loads(text[start:end + 1])
            except ValueError:
                pass
    if isinstance(obj, dict):
        return obj
    raise TaskError("the answer is not a JSON object", EXIT_SCHEMA)


def cmd_verify(a: argparse.Namespace) -> int:
    obj = verify_answer(read_answer(a.answer), corpus_root(a.corpus or "", a.corpus_root) if (a.corpus or a.corpus_root) else None)
    print(capsule(obj))
    return EXIT_OK


# ------------------------------------------------------------------ headless run

def agent_body() -> str:
    try:
        parts = AGENT.read_text(encoding="utf-8").split("---", 2)
        return parts[2].strip() if len(parts) == 3 else ""
    except OSError:
        return ""


# The local tools the worker may run through Bash, as permission-rule prefixes. Any other shell command is
# unmatched, which a headless run cannot approve, so it is denied and the worker reports `blocked`.
LOCAL_TOOLS = ("skills/local-model-task/scripts/local_model_task.py", "skills/code-kg/scripts/code_kg.py",
               "skills/obsidian-kg/scripts/obsidian_kg.py")


def allowed_tools() -> str:
    rules = ["Read", "Grep", "Glob"]
    for rel in LOCAL_TOOLS:
        for root in ("~/.agents", str(Path.home() / ".agents")):
            rules.append(f"Bash(python3 {root}/{rel}:*)")
    return ",".join(rules)


# The station's memory gate. A headless worker cannot answer the "ask" the gate returns at warn, so the runner seats
# the worker (the gate then denies load-adding calls outright, with a prefix the worker's fallback rule recognizes)
# and asks the gate itself before spending anything: critical refuses the run, warn is passed on to the worker.
SEAT = "support-local"
GATE_PREFIX = "brain-gate: memory-pressure"
GATE_HOOKS = (Path.home() / ".claude" / "hooks" / "memory_pressure_gate.py", HERE.parent.parent.parent / "hooks" / "memory_pressure_gate.py")


def gate_check() -> str | None:
    """Ask the station's memory gate as a prompt would. Exit 2 is critical: refuse before a worker is spent. A warning
    on stdout is returned so the brief can tell the worker that its local calls may be denied. No gate installed, or a
    gate that cannot read the kernel, means no gate."""
    hook = next((h for h in GATE_HOOKS if h.is_file()), None)
    if hook is None:
        return None
    try:
        p = subprocess.run([sys.executable, str(hook)], input=json.dumps({"hook_event_name": "UserPromptSubmit"}),
                           capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode == 2:
        raise TaskError("memory pressure is critical on this machine; refusing to start a worker: " + p.stderr.strip()[:300], EXIT_REFUSED)
    try:
        return (json.loads(p.stdout).get("systemMessage") or None) if p.stdout.strip() else None
    except ValueError:
        return None


def run_worker(brief: str, model: str, max_turns: int, timeout: int, effort: str | None = None,
               autocompact: str | None = None) -> dict:
    """One headless worker run. Always returns a result dict: the harness's own when it produced one, or a
    synthetic one with `died` set when the process timed out, crashed or printed no JSON, so a dead worker is a
    recorded outcome and never a vanished one. The worker is seated for the memory gate and runs in an empty
    directory of its own, so no project rules file or session memory reaches it; the user-level hooks still do."""
    claude = shutil.which("claude")
    if not claude:
        raise TaskError("the claude CLI is not on PATH", EXIT_WORKER)
    cmd = [claude, "-p", "--model", model, "--output-format", "json", "--max-turns", str(max_turns),
           "--allowedTools", allowed_tools(), "--append-system-prompt", agent_body()]
    if effort:
        cmd += ["--effort", effort]
    if autocompact:
        cmd += ["--autocompact", autocompact]
    cmd.append(brief)
    env = {**os.environ, "AGENTS_APP_SEAT": SEAT}
    (state_dir() / "cwd").mkdir(exist_ok=True, mode=0o700)
    cwd = tempfile.mkdtemp(prefix="worker-", dir=state_dir() / "cwd")
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    except subprocess.TimeoutExpired as e:
        tail = (e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""))[-500:]
        return {"died": "timeout", "subtype": f"killed after {timeout} s", "result": tail, "is_error": True, "modelUsage": {}}
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
    lines = [ln for ln in p.stdout.splitlines() if ln.strip().startswith("{")]
    if not lines:
        return {"died": "no_json", "subtype": f"exit {p.returncode}", "result": (p.stdout + "\n" + p.stderr).strip()[-500:],
                "is_error": True, "modelUsage": {}}
    try:
        return json.loads(lines[-1])
    except ValueError:
        return {"died": "bad_json", "subtype": "result line is not JSON", "result": lines[-1][-500:], "is_error": True, "modelUsage": {}}


def salvage(goal: str, result: dict, text: str) -> dict:
    """The answer object for a worker that ended without one: nothing claimed, everything stated."""
    subtype = str(result.get("subtype") or "")
    if result.get("died") == "timeout":
        reason = "timeout"
    elif "max_turns" in subtype or "max-turns" in subtype:
        reason = "budget"
    else:
        reason = "error"
    return {"goal": goal, "answer": "", "answerable": False, "evidence": [],
            "coverage": f"worker ended without a JSON answer ({subtype or result.get('died') or 'unknown'}); last text: {text[-400:]!r}",
            "local_calls": 0, "stop_reason": reason}


def assert_model(result: dict, model: str) -> str:
    used = list((result.get("modelUsage") or {}).keys())
    if not used:
        raise TaskError("the worker result names no model; refusing to trust it", EXIT_REFUSED)
    for name in used:
        if not name.startswith(REQUIRED_MODEL_PREFIX):
            raise TaskError(f"the worker ran on {name}, which is not {REQUIRED_MODEL_PREFIX}; refusing (asked for {model})", EXIT_REFUSED)
    return used[0]


def peak_context(usage: dict) -> int | None:
    """The largest single-request context the worker reached, from the harness's per-iteration usage."""
    peaks = []
    for it in usage.get("iterations") or []:
        if isinstance(it, dict):
            peaks.append((it.get("input_tokens") or 0) + (it.get("cache_read_input_tokens") or 0) + (it.get("cache_creation_input_tokens") or 0))
    return max(peaks) if peaks else None


def attempt(goal: str, corpus: str, brief: str, model: str, budget_turns: int, timeout: int, effort: str | None,
            autocompact: str | None) -> tuple[dict, dict, bool]:
    """One attempt: (answer object, raw result, salvaged). A model mismatch is still a refusal."""
    result = run_worker(brief, model, budget_turns, timeout, effort, autocompact)
    if result.get("died"):
        return salvage(goal, result, str(result.get("result") or "")), result, True
    assert_model(result, model)
    text = str(result.get("result") or "")
    try:
        return parse_json_object(text), result, False
    except TaskError:
        return salvage(goal, result, text), result, True


def run_goal(goal: str, corpus: str, complete: str, out_of_scope: str, budget_turns: int, budget_calls: int, model: str | None,
             timeout: int, variant: str = "default", effort: str | None = None, autocompact: str | None = None,
             retries: int = 1, root: str | None = None) -> tuple[dict, dict]:
    """Run the worker on one goal and return (verified answer, run record). Shared by `run` and the goal evals.

    A worker that dies, times out or returns no JSON is salvaged into an `answerable: false` answer with the reason in
    `coverage`, then retried at most `retries` times with half the turn budget and the prior coverage in the brief.
    Every attempt's tokens and cost are summed into the record; nothing vanishes."""
    model = model or agent_model()
    effort = effort or agent_effort()
    started = now()
    warning = gate_check()   # critical refuses here, before anything is spent
    corpus_path = corpus_root(corpus, root)
    if corpus_path is not None and Path(corpus).expanduser().is_dir():
        corpus = str(corpus_path.resolve())   # the worker runs in its own empty directory, so a relative corpus would not resolve
    attempts: list[dict] = []
    prior = ""
    obj = result = None
    salvaged = False
    turns = budget_turns
    for n in range(1, retries + 2):
        brief = build_brief(goal, corpus, complete, out_of_scope, turns, budget_calls, variant)
        if warning:
            brief += (f"\n\n## Station state\n\nThe station's memory gate is at warn ({warning[:300]}). A local-model call may be denied "
                      f"with a reason starting `{GATE_PREFIX}`; that is the machine declining to load a model, and your definition's "
                      f"fallback rule applies: continue with Grep, Glob and Read and name the gate in `coverage`.\n")
        if prior:
            brief += f"\n\n## Prior attempt\n\nA previous worker on this goal ended early. Its coverage: {prior}\nStart from what it covered; do not repeat the same failing call.\n"
        obj, result, salvaged = attempt(goal, corpus, brief, model, turns, timeout, effort, autocompact)
        usage = result.get("usage") or {}
        attempts.append({"n": n, "turns_budget": turns, "turns": result.get("num_turns"), "salvaged": salvaged,
                         "stop_reason": obj.get("stop_reason"), "detail": str(result.get("subtype") or "")[:200],
                         "output_tokens": usage.get("output_tokens"),
                         "cache_read": usage.get("cache_read_input_tokens"), "cache_write": usage.get("cache_creation_input_tokens"),
                         "input_tokens": usage.get("input_tokens"), "harness_cost_usd": result.get("total_cost_usd"),
                         "per_model": {name: {k: u.get(k) for k in ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "costUSD")}
                                       for name, u in (result.get("modelUsage") or {}).items() if isinstance(u, dict)}})
        # a dead worker is retried; so is one that ran out of budget with nothing to show and no verdict. A parsed
        # `answerable: false` is a verdict, whatever stopped the worker, and is not run again
        retryable = salvaged or (obj.get("answerable") is not False and obj.get("stop_reason") in ("budget", "error", "timeout")
                                 and not obj.get("evidence"))
        if not retryable or n > retries:
            break
        prior = str(obj.get("coverage") or "")[:1500]
        turns = max(5, turns // 2)
    obj = verify_answer(obj, corpus_path)
    usage = result.get("usage") or {}
    used = next((m for a in attempts for m in a["per_model"]), model)
    per_model: dict = {}
    for a in attempts:
        for name, u in a["per_model"].items():
            slot = per_model.setdefault(name, {"inputTokens": 0, "outputTokens": 0, "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0, "costUSD": 0.0})
            for k in slot:
                slot[k] += (u.get(k) or 0)

    def total(key):
        return sum((a.get(key) or 0) for a in attempts)

    turns_total = total("turns")
    record = {"ts": started, "goal": obj["goal"], "corpus": corpus, "model": used, "variant": variant, "effort": effort,
              "autocompact": autocompact, "budget_turns": budget_turns, "budget_calls": budget_calls,
              "attempts": len(attempts), "salvaged": salvaged, "attempt_log": attempts,
              "harness_cost_usd": total("harness_cost_usd"), "list_cost_usd": list_cost(per_model),
              "turns": turns_total, "wall_ms": result.get("duration_ms"),
              "input_tokens": total("input_tokens"), "output_tokens": total("output_tokens"),
              "cache_read": total("cache_read"), "cache_write": total("cache_write"),
              "peak_context_tokens": peak_context(usage),
              "mean_context_tokens": round((total("cache_read") + total("cache_write") + total("input_tokens")) / max(1, turns_total)),
              "per_model": per_model, "answerable": obj["answerable"],
              "verified": obj["verified_count"], "unsupported": obj["unsupported_count"], "local_calls": obj["local_calls"],
              "stop_reason": obj["stop_reason"]}
    return obj, record


def cmd_run(a: argparse.Namespace) -> int:
    obj, record = run_goal(a.goal, a.corpus, a.complete, a.out_of_scope, a.budget_turns, a.budget_calls, a.model, a.timeout,
                           a.variant, a.effort, a.autocompact, a.retries, a.corpus_root)
    out = state_dir() / "runs.jsonl"
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, separators=(",", ":")) + "\n")
    used = record["model"]
    print(f"worker {used}: {record['turns']} turns over {record['attempts']} attempt(s); tokens in {record['input_tokens'] or 0} / "
          f"out {record['output_tokens'] or 0} / cache read {record['cache_read'] or 0} / cache write {record['cache_write'] or 0}; "
          f"mean context per turn {record['mean_context_tokens']}; harness estimate ${record['harness_cost_usd'] or 0:.4f}; "
          f"list price ${record['list_cost_usd']:.4f}"
          + (" (harness called the model unrecognized, so its estimate is a fallback)" if used.startswith(REQUIRED_MODEL_PREFIX) else ""))
    print(capsule(obj))
    if record["salvaged"]:
        print(f"support-local: the worker ended without an answer on every attempt ({obj['stop_reason']}); the record above is what it covered",
              file=sys.stderr)
        return EXIT_WORKER
    return EXIT_OK


# Published list prices per million tokens (input, output); cache write is 1.25x input and cache read 0.1x input.
# Haiku 5.5 from platform.claude.com on 2026-10-09 (the under-100K-context tier). Add rows as they are verified.
LIST_PRICES = {"claude-haiku-5-5": (0.10, 0.50)}


def list_cost(per_model: dict) -> float:
    total = 0.0
    for name, u in per_model.items():
        prices = next((p for prefix, p in LIST_PRICES.items() if name.startswith(prefix)), None)
        if prices is None:
            total += float(u.get("costUSD") or 0.0)     # trust the harness where it knows the model
            continue
        inp, out = prices
        total += ((u.get("inputTokens") or 0) * inp + (u.get("outputTokens") or 0) * out
                  + (u.get("cacheCreationInputTokens") or 0) * inp * 1.25 + (u.get("cacheReadInputTokens") or 0) * inp * 0.1) / 1e6
    return round(total, 6)


# ------------------------------------------------------------------ doctor

def cmd_doctor(a: argparse.Namespace) -> int:
    failures = 0

    def say(ok: bool, msg: str) -> None:
        nonlocal failures
        failures += 0 if ok else 1
        print(f"{'ok  ' if ok else 'FAIL'} {msg}")

    say(AGENT.exists(), f"agent definition {AGENT}")
    model = agent_model()
    say(model.startswith(REQUIRED_MODEL_PREFIX), f"agent pins model {model} ({REQUIRED_MODEL_PREFIX} or newer is required)")
    linked = Path.home() / ".claude" / "agents" / "support-local.md"
    say(linked.exists(), f"agent linked into {linked} (run sync-skills.sh, then restart the session)" if not linked.exists()
        else f"agent linked at {linked}")
    say(shutil.which("claude") is not None, "claude CLI on PATH for headless runs")
    lmt = HERE.parent.parent / "local-model-task" / "scripts" / "local_model_task.py"
    say(lmt.exists(), f"local-model-task at {lmt}")
    if lmt.exists():
        try:
            p = subprocess.run([sys.executable, str(lmt), "doctor"], capture_output=True, text=True, timeout=60)
            say(p.returncode == 0, "local-model-task doctor " + ("passes" if p.returncode == 0 else "fails; run it directly"))
        except (OSError, subprocess.SubprocessError) as e:
            say(False, f"local-model-task doctor could not run: {type(e).__name__}")
    budget = Path.home() / ".config" / "local-models" / "budget.json"
    print(f"{'ok  ' if budget.exists() else 'warn'} memory budget file {budget}{'' if budget.exists() else ' is absent; built-in defaults apply'}")
    say(True, f"state {state_dir()}")
    return EXIT_OK if failures == 0 else 1


# ------------------------------------------------------------------ entry

def add_brief_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--goal", required=True)
    p.add_argument("--corpus", required=True, help="a path, a code-kg or obsidian-kg index name, or vault:<name>")
    p.add_argument("--corpus-root", default=None, help="the directory evidence references resolve against when --corpus is an index name; a path corpus is its own root")
    p.add_argument("--complete", default="", help="what a complete answer contains")
    p.add_argument("--out-of-scope", default="")
    p.add_argument("--budget-turns", type=int, default=30)
    p.add_argument("--budget-calls", type=int, default=20)
    p.add_argument("--variant", default="default", choices=sorted(VARIANTS), help="brief template variant")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("brief")
    add_brief_args(b)
    b.set_defaults(fn=cmd_brief)
    r = sub.add_parser("run")
    add_brief_args(r)
    r.add_argument("--model", default=None, help="defaults to the agent definition's pin")
    r.add_argument("--timeout", type=int, default=1200)
    r.add_argument("--effort", default=None, choices=["low", "medium", "high", "max"], help="worker effort; the definition's high applies when omitted")
    r.add_argument("--autocompact", default=None, help="claude -p --autocompact value: auto, or a token count")
    r.add_argument("--retries", type=int, default=1, help="retries after a worker dies or ends with no evidence; each gets half the turns and the prior coverage")
    r.set_defaults(fn=cmd_run)
    v = sub.add_parser("verify")
    v.add_argument("--answer", required=True, help="a file, or - for stdin")
    v.add_argument("--corpus", default=None)
    v.add_argument("--corpus-root", default=None)
    v.set_defaults(fn=cmd_verify)
    d = sub.add_parser("doctor")
    d.set_defaults(fn=cmd_doctor)
    a = p.parse_args(argv)
    try:
        return a.fn(a)
    except TaskError as e:
        print(f"support-local: {e}", file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
