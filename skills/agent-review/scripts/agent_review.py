#!/usr/bin/env python3
"""agent-review: one harness, one model, one read-only review of a fixed set of files.

  agent_review.py run --harness claude|codex|cursor|antigravity [--model NAME] [--effort LEVEL]
                      --brief <file|-> --file <path> [--file ...] [--root <dir>] [--out <dir>] [--timeout 1500]
  agent_review.py harnesses          print the table: runner, default model, effort levels, how effort is passed,
                                     and whether the CLI is installed here

Exit codes: 0 review written; 2 bad arguments; 3 the harness is not installed on this
machine (nothing is created); 4 the harness ran and failed or returned nothing.

The named files, and nothing else, are copied into a one-commit staging repo; the
harness runs read-only in a worktree of it and hands its text back; this script
writes `review.md` and `run.json`. Nothing the harness produces is applied anywhere.
The council skill imports this module for its members. Stdlib only.

How each harness takes effort, probed on this machine 2026-10-10:
  claude       `claude -p --effort` low|medium|high|xhigh|max; Read confined to the staging dir
  codex        `model_reasoning_effort` config key; low|medium|high|xhigh|max|ultra, model-dependent
  cursor       the level is a suffix of the model slug; no effort flag
  antigravity  `agy --effort` for a bare model, or a level slug, never both; Gemini 3.1 Pro: low|high
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SKILLS_ROOT = SKILL_DIR.parent
REFS = SKILL_DIR / "references"

HARNESSES = {
    "claude": {"runner": "claude", "bin": "claude", "model": "claude-fable-5-1",
               "levels": ("low", "medium", "high", "xhigh", "max"), "label": "Claude Code"},
    "codex": {"runner": "codex-task", "bin": "codex", "model": "gpt-6-astra",
              "levels": ("low", "medium", "high", "xhigh", "max", "ultra"), "label": "Codex CLI"},
    "cursor": {"runner": "cursor-task", "bin": "agent", "model": "grok-4.7",
               "levels": ("low", "medium", "high", "xhigh", "max"), "label": "Cursor agent CLI"},
    "antigravity": {"runner": "antigravity-task", "bin": "agy", "model": "gemini-3.1-pro",
                    "levels": ("low", "medium", "high", "xhigh", "max"), "label": "Antigravity CLI"},
}
SANDBOX_EXEC = "/usr/bin/sandbox-exec"
DEFAULT_EFFORT = "high"
TASK_SCRIPTS = {
    "codex-task": SKILLS_ROOT / "codex-task" / "scripts" / "codex_task.py",
    "cursor-task": SKILLS_ROOT / "cursor-task" / "scripts" / "cursor_task.py",
    "antigravity-task": SKILLS_ROOT / "antigravity-task" / "scripts" / "antigravity_task.py",
}
# How each harness reads the files. Codex's read-only sandbox reads through the shell, agy's
# plan mode ends the turn on any shell call, Cursor's ask mode and claude -p have read tools.
TOOL_NOTES = {
    "codex-task": "Read the files with read-only shell commands such as `cat`, `sed -n` and `grep`; those are your reading tools here. Read nothing outside this directory. Do not write, create, move or delete anything, and do not fetch from the network.",
    "antigravity-task": "Read the files with your file-reading tool only, and read nothing outside this directory. Do not run any shell command, do not write anything, do not fetch anything: a tool that needs approval ends your run with no output.",
    "cursor-task": "Read the files with your file-reading tools, and read nothing outside this directory. Do not run commands, do not write anything, do not fetch anything.",
    "claude": "Read the files with your Read tool, which is the only tool you have here. Do not try to write or run anything.",
}
DEFAULT_TIMEOUT = 1500
MAX_TIMEOUT = 1800
MAX_FILE_BYTES = 5 * 1024 * 1024
CLAUDE_MAX_TURNS = 40
ENV_ALLOW = ("HOME", "PATH", "USER", "LANG", "SHELL", "TERM", "TMPDIR")
TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
FENCED_JSON = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)

EXIT_OK, EXIT_ARGS, EXIT_UNAVAILABLE, EXIT_FAILED = 0, 2, 3, 4


class ReviewError(Exception):
    def __init__(self, msg: str, code: int = EXIT_ARGS):
        super().__init__(msg)
        self.code = code


# ---------------------------------------------------------------- helpers ---

def state_dir() -> Path:
    raw = os.environ.get("AGENT_REVIEW_STATE") or os.path.join(
        os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "agent-review")
    p = Path(raw).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "user.email=review@local", "-c", "user.name=review", *args],
                          cwd=str(cwd), text=True, capture_output=True, check=True, timeout=120)


def test_mode() -> bool:
    """The explicit opt-in under which fake binaries and task-skill overrides are honored.
    Without it an ambient AGENT_REVIEW_FAKE_BIN or CURSOR_TASK_SANDBOX_BIN cannot swap a
    real run for a fabricated or unsandboxed one."""
    return os.environ.get("AGENT_REVIEW_TEST") == "1"


def fake_bin() -> str | None:
    """The fake harness, honored only in test mode and only from a skill's tests folder."""
    if not test_mode():
        return None
    path = os.environ.get("AGENT_REVIEW_FAKE_BIN")
    if not path:
        return None
    resolved = Path(path).resolve()
    if resolved.parent.name != "tests" or resolved.parent.parent.parent != SKILLS_ROOT:
        raise ReviewError(f"AGENT_REVIEW_FAKE_BIN must sit in a skill's tests folder, not {resolved}")
    return str(resolved)


def child_env() -> dict[str, str]:
    env = {k: os.environ[k] for k in ENV_ALLOW if k in os.environ}
    if test_mode():
        env.update({k: v for k, v in os.environ.items()
                    if k.startswith(("AGENT_REVIEW_", "CODEX_TASK_", "CURSOR_TASK_", "ANTIGRAVITY_TASK_", "FAKE_"))})
    return env


def render(template: str, **fields: str) -> str:
    out = template
    for k, v in fields.items():
        out = out.replace("{{" + k + "}}", v)
    return out


# ---------------------------------------------------------------- resolution ---

def resolve(harness: str, model: str | None, effort: str | None) -> dict:
    """The harness entry with the model and effort settled: a bare model keeps the effort
    beside it; a model that already names its level (gemini-3.1-pro-high, grok-4.7-xhigh)
    drops the effort, since both CLIs refuse the pair."""
    if harness not in HARNESSES:
        raise ReviewError(f"unknown harness {harness!r}; one of {', '.join(HARNESSES)}")
    cfg = dict(HARNESSES[harness])
    cfg["harness"] = harness
    model = model or cfg["model"]
    if not TOKEN_RE.match(model):
        raise ReviewError("model must be a plain token")
    cfg["model"] = model
    names_level = any(model.endswith("-" + lv) or model.endswith("-" + lv + "-fast") for lv in cfg["levels"])
    if names_level:
        cfg["effort"] = None
    else:
        effort = effort or DEFAULT_EFFORT
        if effort not in cfg["levels"]:
            raise ReviewError(f"{harness} takes effort {', '.join(cfg['levels'])}, not {effort!r}")
        cfg["effort"] = effort
    return cfg


def availability(cfg: dict) -> str | None:
    """Why this harness cannot run on this machine, or None when it can. Only what is
    checkable without a call is checked: the CLI on PATH, and sandbox-exec for the two
    runners that need it. A missing login or a refused model surfaces as a failed run
    with the CLI's own error, since no CLI answers that without a paid call."""
    if fake_bin():
        missing = os.environ.get("AGENT_REVIEW_FAKE_MISSING", "").split(",")
        return f"fake: {cfg['bin']} not installed" if cfg["harness"] in missing else None
    if not shutil.which(cfg["bin"]):
        return f"the {cfg['label']} CLI ({cfg['bin']}) is not on PATH"
    if cfg["runner"] in ("cursor-task", "antigravity-task") and not Path(SANDBOX_EXEC).exists():
        return f"{SANDBOX_EXEC} is missing, so the write-deny profile cannot be applied"
    return None


# ---------------------------------------------------------------- staging ---

def validate_files(files: list[str], root: str | None) -> tuple[list[Path], list[str]]:
    """Resolve the named files and their relative paths, refusing symlinks, directories,
    missing and oversized files and anything outside --root, before anything is created."""
    if not files:
        raise ReviewError("at least one --file is required")
    paths = []
    for raw in files:
        p = Path(raw).expanduser()
        if p.is_symlink():
            raise ReviewError(f"{raw} is a symlink; name the real file")
        p = p.resolve()
        if not p.is_file():
            raise ReviewError(f"{raw} is not a file")
        if p.stat().st_size > MAX_FILE_BYTES:
            raise ReviewError(f"{raw} is over {MAX_FILE_BYTES // (1024 * 1024)} MB")
        paths.append(p)
    base = Path(root).expanduser().resolve() if root else Path(os.path.commonpath([str(p.parent) for p in paths]))
    rels = []
    for p, raw in zip(paths, files):
        try:
            rel = p.relative_to(base)
        except ValueError:
            raise ReviewError(f"{p} is outside --root {base}")
        # Every component below the base, not only the last: a symlinked parent inside the
        # tree would be resolved silently. System links above the base (/var on macOS) are fine.
        cur = Path(raw).expanduser()
        cur = cur if cur.is_absolute() else Path.cwd() / cur
        walk = Path(os.path.normpath(cur))
        probe = walk
        for _ in rel.parts:
            if probe.is_symlink():
                raise ReviewError(f"{raw} crosses a symlink at {probe}; name the real path")
            probe = probe.parent
        rels.append(rel.as_posix())
    if len(set(rels)) != len(rels):
        raise ReviewError("two files map to the same relative path")
    return paths, rels


def stage_files(paths: list[Path], rels: list[str], out: Path) -> Path:
    """Copy the validated files, and nothing else, into out/stage as a one-commit git repo."""
    stage = out / "stage"
    stage.mkdir(parents=True)
    for p, rel in zip(paths, rels):
        dst = stage / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dst)
        os.chmod(dst, 0o600)
    git(["init", "-q"], stage)
    git(["add", "-A"], stage)
    git(["commit", "-q", "-m", "files under review"], stage)
    return stage


# ---------------------------------------------------------------- runners ---

def run_harness(cfg: dict, brief_path: Path, stage: Path, timeout: int, work: Path) -> dict:
    """Run one harness read-only against the staging repo. Returns
    {text, usage, model_reported, exit_code, error, elapsed_s, harness, model, effort}. Never raises."""
    started = time.time()
    try:
        if fake_bin():
            res = _run_fake(cfg, brief_path, stage)
            res["fake_bin"] = fake_bin()
        elif cfg["runner"] == "claude":
            res = _run_claude(cfg, brief_path, stage, timeout, work)
        else:
            res = _run_task_skill(cfg, brief_path, stage, timeout)
    except Exception as exc:  # a harness failing must not take the caller down
        res = {"text": None, "usage": None, "model_reported": None, "exit_code": EXIT_FAILED, "error": str(exc)[:500]}
    res.update({"elapsed_s": round(time.time() - started, 1), "harness": cfg["harness"],
                "model": cfg["model"], "effort": cfg["effort"]})
    return res


def _run_fake(cfg: dict, brief_path: Path, stage: Path) -> dict:
    proc = subprocess.run([fake_bin(), cfg["harness"], str(brief_path), str(stage),
                           cfg["model"], cfg["effort"] or ""],
                          capture_output=True, text=True, timeout=60, env=child_env())
    data = json.loads(proc.stdout) if proc.stdout.strip() else {}
    return {"text": data.get("text"), "usage": data.get("usage"), "model_reported": data.get("model"),
            "exit_code": data.get("exit_code", proc.returncode), "error": data.get("error")}


def _run_task_skill(cfg: dict, brief_path: Path, stage: Path, timeout: int) -> dict:
    script = TASK_SCRIPTS[cfg["runner"]]
    argv = [sys.executable, str(script), "run", "--repo", str(stage), "--read-only",
            "--brief", str(brief_path), "--model", cfg["model"], "--timeout", str(min(timeout, MAX_TIMEOUT))]
    if cfg["effort"]:
        argv += ["--effort", cfg["effort"]]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout + 120, env=child_env())
    # The task skill prints `report_json=<path>` as its final line, after anything the
    # agent's summary could have put on stdout, so only the last line is read and the path
    # must be a report.json directly under a run folder.
    lines = proc.stdout.strip().splitlines()
    last = lines[-1] if lines else ""
    report_path = last[len("report_json="):].strip() if last.startswith("report_json=") else None
    if report_path and (Path(report_path).name != "report.json" or not Path(report_path).parent.parent.is_dir()):
        report_path = None
    if not report_path or not Path(report_path).exists():
        return {"text": None, "usage": None, "model_reported": None, "exit_code": proc.returncode or EXIT_FAILED,
                "error": (proc.stderr or proc.stdout)[-500:] or "no report"}
    rpt = json.loads(Path(report_path).read_text(encoding="utf-8"))
    text = None
    if rpt.get("result_text") and Path(rpt["result_text"]).exists():
        text = Path(rpt["result_text"]).read_text(encoding="utf-8")
    elif rpt.get("last_agent_message"):
        text = rpt["last_agent_message"]
    errors = rpt.get("agent_errors") or rpt.get("codex_errors") or []
    return {"text": text, "usage": rpt.get("usage"), "model_reported": rpt.get("model"),
            "exit_code": rpt.get("exit_code", proc.returncode), "error": errors[0][:500] if errors else None,
            "report": report_path}


def _run_claude(cfg: dict, brief_path: Path, stage: Path, timeout: int, work: Path) -> dict:
    claude = shutil.which("claude")
    if not claude:
        raise ReviewError("the claude CLI is not on PATH", EXIT_FAILED)
    prompt = brief_path.read_text(encoding="utf-8")
    # --tools Read removes every other tool; the path rule then confines Read to the staging
    # directory. Without --tools, the station's own allow rules let a headless run use the
    # shell (probed 2026-10-10).
    argv = [claude, "-p", "--model", cfg["model"], "--output-format", "json",
            "--max-turns", str(CLAUDE_MAX_TURNS), "--tools", "Read", "--allowedTools", "Read(./**)",
            "--no-session-persistence", "--strict-mcp-config"]
    if cfg["effort"]:
        argv += ["--effort", cfg["effort"]]
    argv.append(prompt)
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=str(stage), env=child_env())
    except subprocess.TimeoutExpired:
        return {"text": None, "usage": None, "model_reported": None, "exit_code": EXIT_FAILED, "error": f"timeout after {timeout} s"}
    (work / "claude-stdout.json").write_text(proc.stdout, encoding="utf-8")
    try:
        data = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        return {"text": None, "usage": None, "model_reported": None, "exit_code": EXIT_FAILED, "error": "claude output is not JSON"}
    used = list((data.get("modelUsage") or {}).keys())
    reported = used[0] if used else None
    error = None
    if data.get("is_error"):
        error = str(data.get("result") or data.get("subtype"))[:500]
    elif not any(m.startswith(cfg["model"]) for m in used):
        error = f"model mismatch: asked {cfg['model']}, got {used}"
    return {"text": data.get("result"), "usage": data.get("usage") or data.get("modelUsage"),
            "model_reported": reported, "exit_code": EXIT_FAILED if error else EXIT_OK, "error": error}


def extract_json_blocks(text: str | None) -> list[dict]:
    """Every fenced JSON object in a message, in order. Untrusted output; the caller
    reads them as claims."""
    out: list[dict] = []
    for block in FENCED_JSON.findall(text or ""):
        try:
            value = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            out.append(value)
    return out


def extract_json_block(text: str | None, key: str | None = None) -> dict | None:
    """The last fenced JSON object in a message, or with key, the last one holding that
    key; None when there is none. A harness may append its own summary block after the
    one the caller asked for, so the key, not the position, picks it."""
    blocks = extract_json_blocks(text)
    if key is not None:
        blocks = [b for b in blocks if key in b]
    return blocks[-1] if blocks else None


# ---------------------------------------------------------------- commands ---

def cmd_run(a: argparse.Namespace) -> int:
    cfg = resolve(a.harness, a.model, a.effort)
    why = availability(cfg)
    if why:
        raise ReviewError(f"{cfg['harness']} is unavailable here: {why}", EXIT_UNAVAILABLE)
    brief = sys.stdin.read() if a.brief == "-" else Path(a.brief).read_text(encoding="utf-8")
    if not brief.strip():
        raise ReviewError("the brief is empty")
    timeout = int(a.timeout)
    if not 60 <= timeout <= MAX_TIMEOUT:
        raise ReviewError(f"--timeout must be between 60 and {MAX_TIMEOUT}")
    paths, rels = validate_files(a.file, a.root)

    run_id = _dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
    out = Path(a.out).expanduser().resolve() if a.out else state_dir() / run_id
    if out.exists() and any(out.iterdir()):
        raise ReviewError(f"output dir {out} is not empty")
    out.mkdir(parents=True, exist_ok=True)
    os.chmod(out, 0o700)
    stage = stage_files(paths, rels, out)
    (out / "files.json").write_text(json.dumps(rels, indent=1), encoding="utf-8")
    full = render((REFS / "brief.md").read_text(encoding="utf-8"), BRIEF=brief.strip(),
                  FILES="\n".join(f"- {r}" for r in rels), TOOLS=TOOL_NOTES[cfg["runner"]])
    (out / "brief.md").write_text(full, encoding="utf-8")

    print(f"agent-review {run_id}: {cfg['harness']} {cfg['model']}"
          f"{' effort ' + cfg['effort'] if cfg['effort'] else ''}, {len(rels)} files, out {out}")
    res = run_harness(cfg, out / "brief.md", stage, timeout, out)
    if res.get("text"):
        (out / "review.md").write_text(res["text"], encoding="utf-8")
    run = {"run_id": run_id, "files": rels, "brief": str(out / "brief.md"),
           "review": str(out / "review.md") if res.get("text") else None,
           "test_mode": test_mode(), "fake_bin": res.get("fake_bin"),
           **{k: v for k, v in res.items() if k != "text"}}
    (out / "run.json").write_text(json.dumps(run, indent=1), encoding="utf-8")
    state = "ok" if res.get("text") else f"FAILED ({res.get('error')})"
    print(f"  {res['elapsed_s']:>7}s  {state}")
    print(f"  review : {out / 'review.md' if res.get('text') else '(none)'}")
    print(f"  run    : {out / 'run.json'}")
    return EXIT_OK if res.get("text") and res.get("exit_code") == EXIT_OK else EXIT_FAILED


def cmd_harnesses(a: argparse.Namespace) -> int:
    print(f"{'harness':<12} {'runner':<18} {'default model':<18} {'levels':<40} {'effort is passed as':<36} available")
    how = {"claude": "claude -p --effort", "codex-task": "model_reasoning_effort config key",
           "cursor-task": "a suffix of the model slug", "antigravity-task": "agy --effort, or a level slug"}
    for name, cfg in HARNESSES.items():
        why = availability(dict(cfg, harness=name))
        print(f"{name:<12} {cfg['runner']:<18} {cfg['model']:<18} {', '.join(cfg['levels']):<40} "
              f"{how[cfg['runner']]:<36} {'yes' if why is None else 'no: ' + why}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agent_review.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="one harness reviews the named files read-only")
    r.add_argument("--harness", required=True, help=", ".join(HARNESSES))
    r.add_argument("--model", default=None, help="model for the harness; default per harness")
    r.add_argument("--effort", default=None, help=f"reasoning level, default {DEFAULT_EFFORT}; dropped when the model names its level")
    r.add_argument("--brief", required=True, help="what to review and what a complete answer holds; a file, or - for stdin")
    r.add_argument("--file", action="append", required=True, help="a file the harness may read; repeatable")
    r.add_argument("--root", help="directory the files are relative to (default: their common parent)")
    r.add_argument("--out", help="output directory (must be empty); default: a new run under the state dir")
    r.add_argument("--timeout", default=DEFAULT_TIMEOUT, help=f"seconds, max {MAX_TIMEOUT}")
    r.set_defaults(fn=cmd_run)
    h = sub.add_parser("harnesses", help="print the harness table")
    h.set_defaults(fn=cmd_harnesses)
    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except ReviewError as e:
        print(f"agent-review: {e}", file=sys.stderr)
        return e.code
    except subprocess.CalledProcessError as e:
        print(f"agent-review: {' '.join(e.cmd)} failed:\n{(e.stderr or '').strip()}", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
