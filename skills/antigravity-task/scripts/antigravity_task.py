#!/usr/bin/env python3
"""antigravity-task: delegate one bounded task to the local Antigravity CLI (agy),
with writes confined to an explicit file allowlist.

Three commands:
  run    --repo <root> [--allow <path> ...] [--read-only] --brief <file|->
  apply  --run <id>
  clean  [--run <id> | --all | --older-than-days N]

The real repo is never the agent's working directory. `run` checks out a detached
git worktree under the state dir, runs agy there inside a macOS sandbox-exec
profile that denies every file write outside the worktree, agy's own state folder
and the system temp tree, then harvests a patch restricted to the allowlist.
`apply` re-filters by the recorded allowlist and applies to the real tree.
Stdlib only.

Read-only runs use agy's plan mode and return the answer as text. Write runs use
accept-edits mode; headless agy auto-denies its write tool unless the user's own
settings hold a permissions.allow rule, so a write run that produced no change and
no output is reported as such rather than as success.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
BRIEF_TEMPLATE = SKILL_DIR / "references" / "brief.md"

DEFAULT_MODEL = "gemini-3.1-pro"
DEFAULT_EFFORT = "high"
DEFAULT_TIMEOUT = 900
MAX_TIMEOUT = 1800
PRUNE_DAYS = 7
MAX_PROMPT_BYTES = 200_000
TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
EFFORTS = ("low", "medium", "high", "xhigh", "max")

EXIT_OK, EXIT_ARGS, EXIT_OUT_OF_SCOPE, EXIT_AGENT_ERROR, EXIT_TIMEOUT = 0, 2, 3, 4, 5

FORBIDDEN_ARGV = ("--dangerously-", "--remote-control", "--continue", "--conversation")
ENV_ALLOW = ("HOME", "PATH", "USER", "LANG", "SHELL")
FENCED_JSON = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)


class TaskError(Exception):
    def __init__(self, msg: str, code: int = EXIT_ARGS):
        super().__init__(msg)
        self.code = code


# ---------------------------------------------------------------- helpers ---

def die(msg: str, code: int = EXIT_ARGS) -> None:
    print(f"antigravity-task: {msg}", file=sys.stderr)
    sys.exit(code)


def git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), text=True,
                          capture_output=True, check=check, timeout=120)


def test_override(name: str) -> str | None:
    """An ANTIGRAVITY_TASK_* override of a binary or a home is honored only under the
    explicit test opt-in, so a stray export cannot swap the sandbox or the agent out from
    under a real run."""
    if os.environ.get("ANTIGRAVITY_TASK_TEST") == "1":
        return os.environ.get(name) or None
    return None


def agent_bin() -> str:
    return test_override("ANTIGRAVITY_TASK_BIN") or "agy"


def sandbox_bin() -> str:
    path = test_override("ANTIGRAVITY_TASK_SANDBOX_BIN") or "/usr/bin/sandbox-exec"
    if not (Path(path).exists() or shutil.which(path)):
        raise TaskError(f"no OS sandbox at {path}; antigravity-task runs only where sandbox-exec exists")
    return path


def agent_state_home() -> Path:
    """agy keeps auth, settings and conversations under ~/.gemini and has no override for
    it, so the real folder is allowed in the sandbox; the env var exists for the tests."""
    return Path(test_override("ANTIGRAVITY_TASK_AGENT_HOME") or os.path.expanduser("~/.gemini")).resolve()


def user_temp_root() -> Path:
    """The per-user temp tree the sandbox allows: the parent of this user's Darwin temp
    folder (T, C and 0), read from getconf rather than $TMPDIR so a caller that passes no
    TMPDIR cannot turn this into /private/tmp. Anything else is a refusal."""
    try:
        out = subprocess.run(["/usr/bin/getconf", "DARWIN_USER_TEMP_DIR"], capture_output=True, text=True, timeout=10)
        raw = out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        raw = ""
    tmp = Path(raw).resolve() if raw else None
    if not tmp or not str(tmp).startswith("/private/var/folders/") or tmp.name != "T":
        raise TaskError("could not find this user's Darwin temp folder under /private/var/folders; refusing to guess")
    return tmp.parent


def state_dir() -> Path:
    raw = os.environ.get("ANTIGRAVITY_TASK_STATE") or os.path.join(
        os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "antigravity-task")
    p = Path(raw).expanduser().resolve()
    banned = [Path("/tmp").resolve(), user_temp_root()]
    if os.environ.get("TMPDIR"):
        banned.append(Path(os.environ["TMPDIR"]).resolve())
    for b in banned:
        if p == b or b in p.parents:
            raise TaskError(f"state dir {p} is under {b}; the temp tree is writable inside "
                            "the sandbox, so the state dir must live elsewhere")
    p.mkdir(parents=True, exist_ok=True)
    return p


def repo_root(path: str) -> Path:
    try:
        out = git(["rev-parse", "--show-toplevel"], Path(path).resolve()).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise TaskError(f"{path} is not inside a git repository")
    return Path(out).resolve()


def validate_allow(root: Path, raw_paths: list[str]) -> list[str]:
    if not raw_paths:
        raise TaskError("at least one --allow path is required")
    out: list[str] = []
    for raw in raw_paths:
        if not raw or raw.strip() != raw:
            raise TaskError(f"bad allow path {raw!r}")
        p = Path(raw)
        if p.is_absolute():
            try:
                rel = p.resolve(strict=False).relative_to(root)
            except ValueError:
                raise TaskError(f"allow path {raw} is outside the repo")
        else:
            rel = Path(os.path.normpath(raw))
        parts = rel.parts
        if not parts or parts[0] in ("..", ".", "") or ".." in parts:
            raise TaskError(f"allow path {raw} escapes or names the repo root")
        if parts[0] == ".git":
            raise TaskError(f"allow path {raw} is under .git/")
        if any(ch in rel.as_posix() for ch in "*?[]"):
            raise TaskError(f"allow path {raw} contains glob characters")
        cur = root
        for part in parts:
            cur = cur / part
            if cur.is_symlink():
                raise TaskError(f"allow path {raw} crosses a symlink at {cur.relative_to(root)}")
            if not cur.exists():
                break
        if cur.exists() and cur.is_dir():
            raise TaskError(f"allow path {raw} is a directory; name files")
        posix = rel.as_posix()
        if posix not in out:
            out.append(posix)
    return out


def check_argv(argv: list[str]) -> None:
    """The flags, not the brief: the prompt is the last element and may quote a flag name."""
    joined = " ".join(argv[:-1])
    for bad in FORBIDDEN_ARGV:
        if bad in joined:
            raise TaskError(f"refusing to spawn agy with {bad!r} in argv")


SB_PATH_BAD = re.compile(r'[\x00-\x1f"()\\]')


def _sb_path(p: Path) -> str:
    """A path literal for a Seatbelt profile; a quote, paren, backslash or control
    character could end the s-expression and inject a rule, so it is refused."""
    s = str(p.resolve())
    if SB_PATH_BAD.search(s):
        raise TaskError(f"a sandbox path holds a character the profile cannot carry safely: {s!r}")
    return s


def write_profile(run_dir: Path, ws: Path, tmp: Path, read_only: bool = False) -> Path:
    """Deny every file write; allow the worktree (not in a read-only run), agy's state
    folder, the run's temp folder, this user's temp tree and the terminal devices; then
    deny agy's settings file, since a later rule wins and a steered run must not change
    the CLI's permissions for the next one. Reads and network stay open."""
    home = agent_state_home()
    allowed = ([] if read_only else [ws]) + [home, tmp, user_temp_root()]
    lines = ["(version 1)", "(allow default)", "(deny file-write*)"]
    for p in allowed:
        lines.append(f'(allow file-write* (subpath "{_sb_path(p)}"))')
    lines.append('(allow file-write* (literal "/dev/null") (literal "/dev/tty") (regex #"^/dev/ttys[0-9]+$"))')
    # Everything under the state folder that agy or Gemini loads later as config or
    # instructions; an allow-list of what the CLI needs waits on a canary (tasks/todo.md).
    for name in ("antigravity-cli/settings.json", "settings.json", "GEMINI.md", "extensions"):
        lines.append(f'(deny file-write* (subpath "{_sb_path(home / name)}"))')
    profile = run_dir / "sandbox.sb"
    profile.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return profile


def build_argv(profile: Path, model: str, effort: str | None, read_only: bool, prompt: str) -> list[str]:
    """agy takes either a bare model with --effort or a slug that ends in the level, never
    both, and a bare model without --effort is refused (probed 2026-10-10). A level
    suffix on the model therefore switches --effort off."""
    if not TOKEN_RE.match(model):
        raise TaskError("model must be a plain token")
    if any(model.endswith("-" + lv) for lv in EFFORTS):
        effort = None
    else:
        effort = effort or DEFAULT_EFFORT
    if effort is not None and effort not in EFFORTS:
        raise TaskError(f"--effort must be one of {', '.join(EFFORTS)}")
    if len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
        raise TaskError(f"brief is over {MAX_PROMPT_BYTES} bytes; the prompt travels on argv")
    argv = [sandbox_bin(), "-f", str(profile), agent_bin(),
            "--output-format", "json", "--model", model, "--print-timeout", "0",
            "--mode", "plan" if read_only else "accept-edits"]
    if effort:
        argv += ["--effort", effort]
    # --disable-slash-commands is deliberately absent: at 1.1.22 it also disables --mode.
    argv += ["-p", prompt]
    check_argv(argv)
    return argv


def render_brief(task: str, allow: list[str], repo_name: str, read_only: bool) -> str:
    tpl = BRIEF_TEMPLATE.read_text(encoding="utf-8")
    allow_block = "\n".join(f"- {p}" for p in allow) if not read_only else "- (none: this is a read-only run; answer in your final message)"
    return (tpl.replace("{{TASK}}", task.strip())
               .replace("{{ALLOWLIST}}", allow_block)
               .replace("{{REPO_NAME}}", repo_name))


def child_env(tmp: Path) -> dict[str, str]:
    env = {k: os.environ[k] for k in ENV_ALLOW if k in os.environ}
    env["TMPDIR"] = str(tmp)
    # Test hook only: the fake binaries are configured through FAKE_AGY_* and FAKE_SANDBOX_*,
    # forwarded only under the same opt-in that lets them run at all.
    if os.environ.get("ANTIGRAVITY_TASK_TEST") == "1":
        env.update({k: v for k, v in os.environ.items() if k.startswith(("FAKE_AGY_", "FAKE_SANDBOX_"))})
    return env


def _raise_interrupt(signum, frame):
    raise KeyboardInterrupt(f"signal {signum}")


def spawn_agent(argv: list[str], run_dir: Path, timeout: int, env: dict[str, str]) -> tuple[int, str]:
    out_path = run_dir / "output.json"
    err_path = run_dir / "stderr.log"
    ws = run_dir / "ws"
    with out_path.open("wb") as out, err_path.open("wb") as err:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                cwd=str(ws), start_new_session=True, env=env)
        prior = {}
        for sig in (signal.SIGTERM, signal.SIGINT):
            prior[sig] = signal.getsignal(sig)
            signal.signal(sig, _raise_interrupt)
        # Both clocks: the monotonic clock stops while a Mac sleeps, so a run that spans a
        # sleep would outlive its timeout on monotonic time alone (seen 2026-10-10).
        deadline = time.monotonic() + timeout
        wall_deadline = time.time() + timeout
        try:
            while proc.poll() is None:
                if time.monotonic() > deadline or time.time() > wall_deadline:
                    _kill_group(proc)
                    return proc.returncode if proc.returncode is not None else -9, "timeout"
                time.sleep(0.2)
        finally:
            for sig, handler in prior.items():
                signal.signal(sig, handler)
            # Every exit, a normal one included: a child the agent started outlives it
            # in the same group and would keep running in the worktree.
            _kill_group(proc)
    return proc.returncode, "exited"


def _kill_group(proc: subprocess.Popen) -> None:
    """TERM then KILL the agent's whole process group, waiting on the group rather
    than the leader, since members outlive a leader that has already exited. macOS
    answers EPERM for a group whose remaining members have exited but are not yet
    reaped, which means nothing in it can run any more, so it counts as gone."""
    for sig, wait in ((signal.SIGTERM, 5.0), (signal.SIGKILL, 5.0)):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        end = time.monotonic() + wait
        while time.monotonic() < end:
            proc.poll()
            try:
                os.killpg(proc.pid, 0)
            except (ProcessLookupError, PermissionError):
                return
            time.sleep(0.1)


def parse_output(run_dir: Path) -> dict:
    """agy's JSON envelope: status, response, error, usage, duration_seconds, conversation_id."""
    path = run_dir / "output.json"
    raw = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    stderr_tail = ""
    err_path = run_dir / "stderr.log"
    if err_path.exists():
        stderr_tail = err_path.read_text(encoding="utf-8", errors="replace")[-600:]
    if not raw.strip():
        return {"text": None, "usage": None, "errors": ["no output emitted" + (f": {stderr_tail.strip()[:300]}" if stderr_tail.strip() else "")],
                "conversation_id": None, "duration_s": None}
    try:
        env = json.loads(raw)
    except json.JSONDecodeError:
        env = None
        for line in reversed(raw.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    env = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
        if env is None:
            return {"text": None, "usage": None, "errors": [f"unparseable output: {raw[:200]!r}"],
                    "conversation_id": None, "duration_s": None}
    errors = []
    if env.get("status") not in (None, "SUCCESS") or env.get("error"):
        errors.append(str(env.get("error") or env.get("status"))[:500])
    text = env.get("response") or None
    if not text and not errors and stderr_tail.strip():
        # agy exits SUCCESS with an empty response when a tool was auto-denied headless.
        errors.append(f"empty response: {stderr_tail.strip()[:300]}")
    return {"text": text, "usage": env.get("usage"), "errors": errors,
            "conversation_id": env.get("conversation_id"), "duration_s": env.get("duration_seconds")}


def extract_result(text: str | None) -> dict | None:
    if not text:
        return None
    for block in reversed(FENCED_JSON.findall(text)):
        try:
            value = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {"raw": text[:4000]}


def symlink_entries(ws: Path, base: str, paths: list[str]) -> list[str]:
    if not paths:
        return []
    out = git(["diff", "--no-renames", "--raw", "-z", base, "--", *paths], ws).stdout
    fields = out.split("\0")
    found = []
    for i in range(0, len(fields) - 1, 2):
        meta, path = fields[i], fields[i + 1]
        if not meta.startswith(":"):
            continue
        parts = meta[1:].split()
        if len(parts) >= 2 and parts[1] == "120000":
            found.append(path)
    return sorted(set(found))


def gitdir_pointer(ws: Path) -> bytes:
    """The worktree's `.git` file, which tells git where the real gitdir is. An agent with
    write access to the worktree could point it at the user's own repository, so harvest
    refuses when it changed since the worktree was made. A deleted or replaced pointer
    reads as changed."""
    try:
        return (ws / ".git").read_bytes()
    except OSError:
        return b""


def harvest(ws: Path, allow: list[str], run_dir: Path, base: str, pointer: bytes) -> tuple[list[str], list[str]]:
    if gitdir_pointer(ws) != pointer:
        raise TaskError("the worktree's .git pointer changed during the run; nothing harvested", EXIT_AGENT_ERROR)
    git(["add", "-A", "-N", "--", "."], ws)
    names = git(["diff", "--no-renames", "--name-only", "-z", base, "--"], ws).stdout.split("\0")
    changed = sorted(n for n in names if n)
    in_scope = [n for n in changed if n in allow]
    out_scope = [n for n in changed if n not in allow]
    linked = symlink_entries(ws, base, in_scope)
    if linked:
        in_scope = [n for n in in_scope if n not in linked]
        out_scope = sorted(out_scope + linked)
    patch = ""
    if in_scope:
        patch = git(["diff", "--no-renames", "--binary", base, "--", *in_scope], ws).stdout
    (run_dir / "allowed.patch").write_text(patch, encoding="utf-8")
    if out_scope:
        (run_dir / "dropped.patch").write_text(
            git(["diff", "--no-renames", "--binary", base, "--", *out_scope], ws).stdout, encoding="utf-8")
    return in_scope, out_scope


def dirty_paths(root: Path, paths: list[str]) -> list[str]:
    if not paths:
        return []
    out = git(["status", "--porcelain", "--", *paths], root).stdout
    return sorted({ln[3:].strip() for ln in out.splitlines() if ln.strip()})


def permissions_configured() -> bool:
    """Whether agy's settings hold any permissions block. Headless write runs need an
    allow rule there; the check reads key names only and never prints the file."""
    settings = agent_state_home() / "antigravity-cli" / "settings.json"
    try:
        data = json.loads(settings.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and "permissions" in data


# --------------------------------------------------------------- commands ---

def cmd_run(a: argparse.Namespace) -> int:
    root = repo_root(a.repo)
    allow = validate_allow(root, a.allow) if a.allow else []
    if not allow and not a.read_only:
        raise TaskError("at least one --allow path is required unless --read-only")
    timeout = int(a.timeout)
    if not 30 <= timeout <= MAX_TIMEOUT:
        raise TaskError(f"--timeout must be between 30 and {MAX_TIMEOUT} seconds")
    task = sys.stdin.read() if a.brief == "-" else Path(a.brief).read_text(encoding="utf-8")
    if not task.strip():
        raise TaskError("brief is empty")
    base = git(["rev-parse", "--verify", f"{a.base}^{{commit}}"], root).stdout.strip()
    sandbox_bin()
    warnings: list[str] = []
    if not a.read_only and not permissions_configured():
        warnings.append("agy settings hold no permissions block; headless write tools are auto-denied, "
                        "so expect an empty result unless an allow rule exists")

    sdir = state_dir()
    prune(sdir, PRUNE_DAYS)
    run_id = _dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
    run_dir = sdir / run_id
    ws = run_dir / "ws"
    tmp = run_dir / "tmp"
    run_dir.mkdir(parents=True)
    tmp.mkdir()
    git(["worktree", "add", "--detach", str(ws), base], root)
    pointer = gitdir_pointer(ws)

    prompt = render_brief(task, allow, root.name, a.read_only)
    profile = write_profile(run_dir, ws, tmp, a.read_only)
    argv = build_argv(profile, a.model, a.effort, a.read_only, prompt)
    (run_dir / "brief.md").write_text(prompt, encoding="utf-8")
    (run_dir / "argv.json").write_text(json.dumps(argv[:-1] + ["<brief>"], indent=1), encoding="utf-8")

    started = time.time()
    rc, reason = spawn_agent(argv, run_dir, timeout, child_env(tmp))
    elapsed = round(time.time() - started, 1)
    out = parse_output(run_dir)
    try:
        in_scope, out_scope = harvest(ws, allow, run_dir, base, pointer)
    except TaskError as exc:
        in_scope, out_scope = [], []
        out["errors"].append(str(exc))
        (run_dir / "allowed.patch").write_text("", encoding="utf-8")
    result = extract_result(out["text"])
    if out["text"]:
        (run_dir / "result.md").write_text(out["text"], encoding="utf-8")

    if reason == "timeout":
        code = EXIT_TIMEOUT
    elif rc != 0 or out["errors"]:
        code = EXIT_AGENT_ERROR
    elif out_scope:
        code = EXIT_OUT_OF_SCOPE
    else:
        code = EXIT_OK

    report = {
        "run_id": run_id, "run_dir": str(run_dir), "repo": str(root), "base": base,
        "model": a.model, "effort": a.effort, "read_only": a.read_only, "timeout_s": timeout, "elapsed_s": elapsed,
        "allowlist": allow, "changed_in_scope": in_scope, "changed_out_of_scope": out_scope,
        "dirty_allowed_files_in_repo": dirty_paths(root, allow),
        "sandbox_profile": str(profile), "sandbox_bin": argv[0], "agent_bin": argv[3],
        "warnings": warnings, "agent_rc": rc, "exit_reason": reason,
        "agent_errors": out["errors"], "usage": out["usage"], "conversation_id": out["conversation_id"],
        "agent_duration_s": out["duration_s"], "result": result,
        "result_text": str(run_dir / "result.md") if out["text"] else None,
        "patch": str(run_dir / "allowed.patch"), "exit_code": code,
    }
    (run_dir / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")

    print(f"run {run_id}  exit {code}  {elapsed}s  model {a.model}{'  read-only' if a.read_only else ''}")
    print(f"  in scope : {', '.join(in_scope) or '(none)'}")
    if out_scope:
        print(f"  DROPPED  : {', '.join(out_scope)}")
    if out["errors"]:
        print(f"  errors   : {out['errors'][0][:200]}")
    for w in warnings:
        print(f"  warning  : {w}")
    if result and isinstance(result, dict) and result.get("summary"):
        print(f"  summary  : {str(result['summary'])[:300]}")
    print(f"  patch    : {run_dir / 'allowed.patch'}")
    print(f"  report   : {run_dir / 'report.json'}")
    print(f"report_json={run_dir / 'report.json'}")  # the machine-readable line callers anchor on
    return code


def load_report(run_id: str) -> tuple[Path, dict]:
    if not RUN_ID_RE.match(run_id):
        raise TaskError("bad run id")
    sdir = state_dir()
    run_dir = sdir / run_id
    if run_dir.resolve().parent != sdir.resolve():
        raise TaskError(f"run id {run_id!r} does not name a run directory")
    rpt = run_dir / "report.json"
    if not rpt.exists():
        raise TaskError(f"no report at {rpt}")
    return run_dir, json.loads(rpt.read_text(encoding="utf-8"))


def cmd_apply(a: argparse.Namespace) -> int:
    run_dir, rpt = load_report(a.run)
    root = Path(rpt["repo"])
    if repo_root(str(root)) != root:
        raise TaskError("recorded repo root no longer resolves")
    if not rpt["allowlist"]:
        print("nothing to apply: the run was read-only")
        return EXIT_OK
    allow = validate_allow(root, rpt["allowlist"])
    patch = run_dir / "allowed.patch"
    if not patch.exists() or not patch.read_text(encoding="utf-8").strip():
        print("nothing to apply: allowed.patch is empty")
        return EXIT_OK
    head = git(["rev-parse", "HEAD"], root).stdout.strip()
    if head != rpt["base"] and not a.force_base:
        raise TaskError(f"HEAD moved since the run (base {rpt['base'][:10]}, now {head[:10]}); "
                        "review and pass --force-base to apply anyway")
    dirty = dirty_paths(root, allow)
    if dirty and not a.force:
        raise TaskError(f"allowed files have uncommitted changes: {', '.join(dirty)}; "
                        "commit or stash them, or pass --force")
    includes = [f"--include={p}" for p in allow]
    try:
        git(["apply", "--check", *includes, str(patch)], root)
    except subprocess.CalledProcessError as e:
        raise TaskError(f"patch does not apply cleanly:\n{e.stderr.strip()}")
    git(["apply", *includes, str(patch)], root)
    applied = git(["status", "--porcelain", "--", *allow], root).stdout.strip()
    print(f"applied run {a.run} to {root}")
    print(applied or "  (no working-tree change reported)")
    return EXIT_OK


def prune(sdir: Path, days: int) -> int:
    cutoff = time.time() - days * 86400
    n = 0
    for d in sdir.iterdir():
        if not d.is_dir():
            continue
        if TOKEN_RE.match(d.name) and (d / "report.json").exists() and d.stat().st_mtime < cutoff:
            remove_run(d)
            n += 1
    return n


def remove_run(run_dir: Path) -> None:
    ws = run_dir / "ws"
    rpt = run_dir / "report.json"
    if ws.exists() and rpt.exists():
        try:
            root = json.loads(rpt.read_text(encoding="utf-8"))["repo"]
            git(["worktree", "remove", "--force", str(ws)], Path(root), check=False)
            git(["worktree", "prune"], Path(root), check=False)
        except (OSError, ValueError, KeyError):
            pass
    shutil.rmtree(run_dir, ignore_errors=True)


def cmd_clean(a: argparse.Namespace) -> int:
    sdir = state_dir()
    if a.run:
        run_dir, _ = load_report(a.run)
        remove_run(run_dir)
        print(f"removed {run_dir}")
    elif a.all:
        n = prune(sdir, 0)
        print(f"removed {n} run(s)")
    else:
        n = prune(sdir, int(a.older_than_days))
        print(f"removed {n} run(s) older than {a.older_than_days} day(s)")
    return EXIT_OK


# ------------------------------------------------------------------- main ---

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="antigravity_task.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run agy on a task in an isolated, sandboxed worktree")
    r.add_argument("--repo", required=True, help="any path inside the target repo")
    r.add_argument("--allow", action="append", help="repo-relative file agy may change; repeatable")
    r.add_argument("--brief", required=True, help="file holding the task text, or - for stdin")
    r.add_argument("--model", default=DEFAULT_MODEL, help="a model from `agy models`, bare or with its level suffix")
    r.add_argument("--effort", default=None, help=f"level for a bare model (default {DEFAULT_EFFORT}): {', '.join(EFFORTS)}; ignored when the model names its level")
    r.add_argument("--read-only", action="store_true",
                   help="run in agy's plan mode: no edits; the answer lands in result.md")
    r.add_argument("--timeout", default=DEFAULT_TIMEOUT, help=f"seconds, max {MAX_TIMEOUT}")
    r.add_argument("--base", default="HEAD", help="commit the worktree starts from")
    r.set_defaults(fn=cmd_run)

    p = sub.add_parser("apply", help="apply a run's allowed patch to the real repo")
    p.add_argument("--run", required=True)
    p.add_argument("--force-base", action="store_true")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_apply)

    c = sub.add_parser("clean", help="remove run directories and their worktrees")
    c.add_argument("--run")
    c.add_argument("--all", action="store_true")
    c.add_argument("--older-than-days", default=PRUNE_DAYS)
    c.set_defaults(fn=cmd_clean)

    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except TaskError as e:
        die(str(e), e.code)
    except subprocess.CalledProcessError as e:
        die(f"{' '.join(e.cmd)} failed:\n{(e.stderr or '').strip()}", EXIT_AGENT_ERROR)
    return EXIT_ARGS


if __name__ == "__main__":
    sys.exit(main())
