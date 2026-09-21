#!/usr/bin/env python3
"""codex-task: delegate one bounded task to the local Codex CLI, with writes
confined to an explicit file allowlist.

Three commands:
  run    --repo <root> --allow <path> [--allow ...] --brief <file|->
  apply  --run <id>
  clean  [--run <id> | --all | --older-than-days N]

The real repo is never Codex's working directory. `run` checks out a detached
git worktree under the state dir, runs Codex there with a locked flag set,
then harvests a patch restricted to the allowlist. `apply` re-filters by the
recorded allowlist and applies to the real tree. Stdlib only.
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
import threading
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
BRIEF_TEMPLATE = SKILL_DIR / "references" / "brief.md"
RESULT_SCHEMA = SKILL_DIR / "references" / "result.schema.json"

DEFAULT_MODEL = "gpt-6-astra"
DEFAULT_EFFORT = "high"
DEFAULT_TIMEOUT = 900
MAX_TIMEOUT = 1800
PRUNE_DAYS = 7
TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
# Must start alphanumeric, so '.', '..' and a leading '-' are all excluded.
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

EXIT_OK, EXIT_ARGS, EXIT_OUT_OF_SCOPE, EXIT_CODEX_ERROR, EXIT_TIMEOUT = 0, 2, 3, 4, 5

FORBIDDEN_ARGV = ("--dangerously-", "danger-full-access", "network_access=true")

# Codex is passed shell_environment_policy.include_only, but at 0.155.1 it does
# not apply it: a live probe saw the full parent environment reach the sandboxed
# shell, including another harness's session token and an ssh-agent socket. The
# scrub therefore happens here, where the process boundary enforces it instead
# of Codex's cooperation. Keep the two lists identical.
ENV_ALLOW = ("HOME", "PATH", "USER", "LANG", "SHELL", "TMPDIR")


class TaskError(Exception):
    def __init__(self, msg: str, code: int = EXIT_ARGS):
        super().__init__(msg)
        self.code = code


# ---------------------------------------------------------------- helpers ---

def die(msg: str, code: int = EXIT_ARGS) -> None:
    print(f"codex-task: {msg}", file=sys.stderr)
    sys.exit(code)


def git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), text=True,
                          capture_output=True, check=check, timeout=120)


def codex_bin() -> str:
    return os.environ.get("CODEX_TASK_BIN") or "codex"


def state_dir() -> Path:
    raw = os.environ.get("CODEX_TASK_STATE") or os.path.join(
        os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
        "codex-task")
    p = Path(raw).expanduser().resolve()
    banned = [Path("/tmp").resolve()]
    if os.environ.get("TMPDIR"):
        banned.append(Path(os.environ["TMPDIR"]).resolve())
    for b in banned:
        if p == b or b in p.parents:
            raise TaskError(f"state dir {p} is under {b}; /tmp and $TMPDIR are writable "
                            "to Codex, so the state dir must live elsewhere")
    p.mkdir(parents=True, exist_ok=True)
    return p


def isolated_home(sdir: Path) -> tuple[Path, list[str]]:
    """A private CODEX_HOME so a run never writes trust, memories or state into
    ~/.codex. Auth is a symlink to the real auth.json so no second login is
    needed. Returns (home, warnings)."""
    real = Path(os.environ.get("CODEX_TASK_REAL_HOME") or os.path.expanduser("~/.codex"))
    home = sdir / "home"
    home.mkdir(parents=True, exist_ok=True)
    link = home / "auth.json"
    warnings: list[str] = []
    if link.exists() and not link.is_symlink():
        # A token refresh replaced the symlink with a real file. Keep the real
        # home authoritative: drop the copy and relink.
        warnings.append("isolated home held a real auth.json (token refresh replaced the "
                        "symlink); relinked to the real one")
        link.unlink()
    if not link.is_symlink():
        if link.exists():
            link.unlink()
        if not (real / "auth.json").exists():
            raise TaskError(f"no auth at {real / 'auth.json'}; run `codex login` first")
        link.symlink_to(real / "auth.json")
    return home, warnings


def repo_root(path: str) -> Path:
    try:
        out = git(["rev-parse", "--show-toplevel"], Path(path).resolve()).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise TaskError(f"{path} is not inside a git repository")
    return Path(out).resolve()


def validate_allow(root: Path, raw_paths: list[str]) -> list[str]:
    """Return normalized repo-relative posix paths, or raise."""
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
        # No symlink anywhere on the existing part of the path.
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
    joined = " ".join(argv)
    for bad in FORBIDDEN_ARGV:
        if bad in joined:
            raise TaskError(f"refusing to spawn Codex with {bad!r} in argv")


def build_argv(ws: Path, model: str, effort: str, last_msg: Path) -> list[str]:
    if not TOKEN_RE.match(model) or not TOKEN_RE.match(effort):
        raise TaskError("model and effort must be plain tokens")
    argv = [
        codex_bin(), "exec", "--json", "--ephemeral", "--ignore-user-config",
        "-s", "workspace-write", "-C", str(ws),
        "-m", model,
        "-c", f'model_reasoning_effort="{effort}"',
        "-c", 'approval_policy="never"',
        "-c", "sandbox_workspace_write.network_access=false",
        "-c", "sandbox_workspace_write.exclude_slash_tmp=true",
        "-c", "sandbox_workspace_write.exclude_tmpdir_env_var=true",
        "-c", 'shell_environment_policy.inherit="core"',
        "-c", 'shell_environment_policy.include_only=["HOME","PATH","USER","LANG","SHELL","TMPDIR"]',
        "-c", "analytics.enabled=false",
        "-c", "features.memories=false",
        "-o", str(last_msg),
        "--output-schema", str(RESULT_SCHEMA),
        "-",
    ]
    check_argv(argv)
    return argv


def render_brief(task: str, allow: list[str], repo_name: str) -> str:
    tpl = BRIEF_TEMPLATE.read_text(encoding="utf-8")
    allow_block = "\n".join(f"- {p}" for p in allow)
    return (tpl.replace("{{TASK}}", task.strip())
               .replace("{{ALLOWLIST}}", allow_block)
               .replace("{{REPO_NAME}}", repo_name))


def child_env(home: Path) -> dict[str, str]:
    """The environment Codex is spawned with: ENV_ALLOW plus CODEX_HOME.

    Everything else is dropped, so a variable the session happens to carry -
    another agent's token, an ssh-agent socket, a cloud credential - never
    reaches Codex or the shell it runs commands in.
    """
    env = {k: os.environ[k] for k in ENV_ALLOW if k in os.environ}
    env["CODEX_HOME"] = str(home)
    # Test hook only: the fake Codex binary is configured through FAKE_CODEX_*,
    # which is never set outside the suite. CODEX_TASK_BIN already gates that path.
    env.update({k: v for k, v in os.environ.items() if k.startswith("FAKE_CODEX_")})
    return env


def _raise_interrupt(signum, frame):
    raise KeyboardInterrupt(f"signal {signum}")


def spawn_codex(argv: list[str], prompt: str, run_dir: Path, timeout: int,
                home: Path) -> tuple[int, str]:
    """Run Codex, streaming JSONL to events.jsonl. Returns (rc, reason)."""
    events = run_dir / "events.jsonl"
    stderr = run_dir / "stderr.log"
    env = child_env(home)
    ws = run_dir / "ws"
    with events.open("wb") as out, stderr.open("wb") as err:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=out, stderr=err,
                                cwd=str(ws), start_new_session=True, env=env)

        def feed() -> None:
            # On a thread so a Codex that never drains stdin cannot block the
            # deadline loop; closing stdin is what prevents the documented hang.
            try:
                proc.stdin.write(prompt.encode("utf-8"))
            except (BrokenPipeError, OSError):
                pass
            finally:
                try:
                    proc.stdin.close()
                except OSError:
                    pass

        threading.Thread(target=feed, daemon=True).start()
        # SIGTERM's default action ends this process without unwinding, so the
        # finally below never runs. Turn both signals into an exception.
        prior = {}
        for sig in (signal.SIGTERM, signal.SIGINT):
            prior[sig] = signal.getsignal(sig)
            signal.signal(sig, _raise_interrupt)
        deadline = time.monotonic() + timeout
        # start_new_session=True detaches Codex from this process group, so
        # without the finally it survives anything that kills the parent -
        # including the Bash-tool timeout SKILL.md tells the operator to set.
        # It would keep editing the worktree and spending with nothing left to
        # harvest it or stop it.
        try:
            while proc.poll() is None:
                if time.monotonic() > deadline:
                    _kill_group(proc)
                    return proc.returncode if proc.returncode is not None else -9, "timeout"
                time.sleep(0.2)
        finally:
            for sig, handler in prior.items():
                signal.signal(sig, handler)
            if proc.poll() is None:
                _kill_group(proc)
    return proc.returncode, "exited"


def _kill_group(proc: subprocess.Popen) -> None:
    for sig, wait in ((signal.SIGTERM, 5.0), (signal.SIGKILL, 5.0)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        end = time.monotonic() + wait
        while proc.poll() is None and time.monotonic() < end:
            time.sleep(0.1)
        if proc.poll() is not None:
            return


def parse_events(run_dir: Path) -> dict:
    messages, errors, usage = [], [], None
    path = run_dir / "events.jsonl"
    if not path.exists():
        return {"messages": [], "errors": ["no events emitted"], "usage": None}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = ev.get("type")
        item = ev.get("item") or {}
        if t == "item.completed" and item.get("type") == "agent_message":
            messages.append(item.get("text", ""))
        elif t == "item.completed" and item.get("type") == "error":
            errors.append(item.get("message") or json.dumps(item))
        elif t == "error":
            errors.append(ev.get("message") or json.dumps(ev))
        elif t == "turn.completed":
            usage = ev.get("usage")
    return {"messages": messages, "errors": errors, "usage": usage}


def symlink_entries(ws: Path, base: str, paths: list[str]) -> list[str]:
    """Of `paths`, those whose post-image mode is 120000 (a symlink)."""
    if not paths:
        return []
    out = git(["diff", "--no-renames", "--raw", "-z", base, "--", *paths], ws).stdout
    # -z raw format: ":<srcmode> <dstmode> <srcsha> <dstsha> <status>\0<path>\0"
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


def harvest(ws: Path, allow: list[str], run_dir: Path, base: str) -> tuple[list[str], list[str]]:
    """Diff the worktree against the base commit; write allowed.patch; return
    (in_scope, out_of_scope). Diffing against base rather than the index means
    anything Codex staged or committed is still seen."""
    git(["add", "-A", "-N", "--", "."], ws)  # intent-to-add so new files diff
    names = git(["diff", "--no-renames", "--name-only", "-z", base, "--"], ws).stdout.split("\0")
    changed = sorted(n for n in names if n)
    in_scope = [n for n in changed if n in allow]
    out_scope = [n for n in changed if n not in allow]
    # The allowlist filters names; it says nothing about modes. Codex can keep
    # an allowed name and turn it into a symlink, which `apply` would then put
    # in the real tree pointing anywhere. Treat a mode change to 120000 as out
    # of scope so it is reported and dropped rather than applied.
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
            git(["diff", "--no-renames", "--binary", base, "--", *out_scope], ws).stdout,
            encoding="utf-8")
    return in_scope, out_scope


def dirty_paths(root: Path, paths: list[str]) -> list[str]:
    if not paths:
        return []
    out = git(["status", "--porcelain", "--", *paths], root).stdout
    return sorted({ln[3:].strip() for ln in out.splitlines() if ln.strip()})


# --------------------------------------------------------------- commands ---

def cmd_run(a: argparse.Namespace) -> int:
    root = repo_root(a.repo)
    allow = validate_allow(root, a.allow)
    timeout = int(a.timeout)
    if not 30 <= timeout <= MAX_TIMEOUT:
        raise TaskError(f"--timeout must be between 30 and {MAX_TIMEOUT} seconds")
    task = sys.stdin.read() if a.brief == "-" else Path(a.brief).read_text(encoding="utf-8")
    if not task.strip():
        raise TaskError("brief is empty")
    base = git(["rev-parse", "--verify", f"{a.base}^{{commit}}"], root).stdout.strip()

    sdir = state_dir()
    home, warnings = isolated_home(sdir)
    prune(sdir, PRUNE_DAYS)
    run_id = _dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
    run_dir = sdir / run_id
    ws = run_dir / "ws"
    run_dir.mkdir(parents=True)
    git(["worktree", "add", "--detach", str(ws), base], root)

    last_msg = run_dir / "last_message.txt"
    argv = build_argv(ws, a.model, a.effort, last_msg)
    prompt = render_brief(task, allow, root.name)
    (run_dir / "brief.md").write_text(prompt, encoding="utf-8")
    (run_dir / "argv.json").write_text(json.dumps(argv, indent=1), encoding="utf-8")

    started = time.time()
    rc, reason = spawn_codex(argv, prompt, run_dir, timeout, home)
    elapsed = round(time.time() - started, 1)
    ev = parse_events(run_dir)
    if (home / "auth.json").exists() and not (home / "auth.json").is_symlink():
        warnings.append("Codex replaced the auth symlink in the isolated home during this run; "
                        "the next run relinks, but check `codex login status` if auth fails")
    in_scope, out_scope = harvest(ws, allow, run_dir, base)

    result = None
    if last_msg.exists():
        try:
            result = json.loads(last_msg.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            result = {"raw": last_msg.read_text(encoding="utf-8", errors="replace")[:4000]}

    if reason == "timeout":
        code = EXIT_TIMEOUT
    elif rc != 0 or ev["errors"]:
        code = EXIT_CODEX_ERROR
    elif out_scope:
        code = EXIT_OUT_OF_SCOPE
    else:
        code = EXIT_OK

    report = {
        "run_id": run_id, "run_dir": str(run_dir), "repo": str(root), "base": base,
        "model": a.model, "effort": a.effort, "timeout_s": timeout, "elapsed_s": elapsed,
        "allowlist": allow, "changed_in_scope": in_scope, "changed_out_of_scope": out_scope,
        "dirty_allowed_files_in_repo": dirty_paths(root, allow),
        "codex_home": str(home), "warnings": warnings,
        "codex_rc": rc, "exit_reason": reason, "codex_errors": ev["errors"],
        "usage": ev["usage"], "result": result,
        "last_agent_message": (ev["messages"][-1] if ev["messages"] else None),
        "patch": str(run_dir / "allowed.patch"), "exit_code": code,
    }
    (run_dir / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")

    print(f"run {run_id}  exit {code}  {elapsed}s  model {a.model}")
    print(f"  in scope : {', '.join(in_scope) or '(none)'}")
    if out_scope:
        print(f"  DROPPED  : {', '.join(out_scope)}")
    if ev["errors"]:
        print(f"  errors   : {ev['errors'][0][:200]}")
    for w in warnings:
        print(f"  warning  : {w}")
    if result and isinstance(result, dict) and result.get("summary"):
        print(f"  summary  : {str(result['summary'])[:300]}")
    print(f"  patch    : {run_dir / 'allowed.patch'}")
    print(f"  report   : {run_dir / 'report.json'}")
    return code


def load_report(run_id: str) -> tuple[Path, dict]:
    # TOKEN_RE admits '.' and '..', which resolve to the state dir and its
    # parent. `clean --run ..` deleted the parent outright, so the run id is
    # confined to a direct child by name, not just by character class.
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
    allow = validate_allow(root, rpt["allowlist"])  # re-check against the tree as it is now
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
    includes = [f"--include={p}" for p in allow]  # re-filter: only the recorded allowlist lands
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
        if d.name == "home" or not d.is_dir():
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
    ap = argparse.ArgumentParser(prog="codex_task.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run Codex on a task in an isolated worktree")
    r.add_argument("--repo", required=True, help="any path inside the target repo")
    r.add_argument("--allow", action="append", required=True, help="repo-relative file Codex may change; repeatable")
    r.add_argument("--brief", required=True, help="file holding the task text, or - for stdin")
    r.add_argument("--model", default=DEFAULT_MODEL)
    r.add_argument("--effort", default=DEFAULT_EFFORT)
    r.add_argument("--timeout", default=DEFAULT_TIMEOUT, help=f"seconds, max {MAX_TIMEOUT}")
    r.add_argument("--base", default="HEAD", help="commit the worktree starts from")
    r.set_defaults(fn=cmd_run)

    p = sub.add_parser("apply", help="apply a run's allowed patch to the real repo")
    p.add_argument("--run", required=True)
    p.add_argument("--force-base", action="store_true", help="apply even if HEAD moved since the run")
    p.add_argument("--force", action="store_true", help="apply even if allowed files are dirty")
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
        die(f"{' '.join(e.cmd)} failed:\n{(e.stderr or '').strip()}", EXIT_CODEX_ERROR)
    return EXIT_ARGS


if __name__ == "__main__":
    sys.exit(main())
