"""Run a child process so that it, and everything it starts, cannot outlive its owner.

The house lifecycle standard (references/process-lifecycle.md) requires every
spawn of an agent CLI, model runner, shell, server or other long-lived child to
go through this module. It gives each child:

- its own process group, led by a small watchdog (this file run as a script);
- a mandatory wall-clock cap, enforced by the watchdog and by the caller;
- a stop sequence of SIGTERM to the whole group, a grace period, then SIGKILL
  to each process still verified to be in that group. SIGTERM first matters:
  `claude -p` kills its own command trees and runs its SessionEnd hooks on
  SIGTERM, and a bare SIGKILL skips that cleanup;
- a parent-death check: the watchdog stops the group when its parent goes away,
  even when the parent was SIGKILLed and could run no cleanup of its own.

Safety: the module only ever signals the process group it created, and only
SIGKILLs a process after `ps` shows it is still in that group. It never matches
processes by name. A child that calls setsid() leaves the group and is outside
this guarantee; the reaper hook reports such escapees.

Library use (a drop-in for subprocess.run, timeout required):

    import procguard
    procguard.install_signal_handlers()      # once, in main()
    proc = procguard.run(argv, input=text, capture_output=True, text=True, timeout=600)

`run` raises subprocess.TimeoutExpired after the whole group is stopped. For
async callers, start `wrap(argv, timeout)` with start_new_session=True and stop
it with `stop(pid)`.

Shell use (what a background agent command runs under):

    python3 procguard.py --timeout 600 -- <command> [args...]

A pipeline goes inside the wrapped command (`-- sh -c 'a | b'`). Piping the
guard's own output (`procguard.py ... | tee log`) in a job-control shell makes
the watchdog lead the pipeline's group, so its stop would reach `tee` too.

Exit status: the child's own status; 124 when the time limit stopped it; 143
when the parent went away or a signal stopped it. Each copy of this file in the
repo is byte-identical to skills/skill-authoring/scripts/procguard.py, and a
test enforces that.
"""
from __future__ import annotations

import argparse
import atexit
import os
import signal
import subprocess
import sys
import threading
import time

GRACE = 5.0
MAX_GRACE = 60.0
POLL = 0.2
EXIT_TIMEOUT = 124
EXIT_STOPPED = 143
_STOP_SIGNALS = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)

_live: dict[int, subprocess.Popen] = {}
# Reentrant: a signal handler runs stop_all() on the main thread, possibly while
# that same thread holds the lock inside popen(); a plain Lock would hang there.
_lock = threading.RLock()
_closed = False


# ---------- caller side ----------

def wrap(argv: list[str], timeout: float, grace: float = GRACE) -> list[str]:
    """The argv that runs `argv` under a watchdog owned by this process. Start
    it with start_new_session=True so the watchdog leads a fresh group."""
    if timeout is None or not 0 < float(timeout) < float("inf"):    # also refuses NaN
        raise ValueError("procguard needs a positive, finite timeout")
    return [sys.executable, "-I", os.path.abspath(__file__), "--parent", str(os.getpid()),
            "--timeout", f"{float(timeout):g}", "--grace", f"{float(grace):g}", "--", *argv]


def stop(pid: int, grace: float = GRACE, leader_alive: bool = True) -> None:
    """Stop the group led by watchdog `pid`. While the watchdog is alive and not
    yet reaped, ask it (it runs the TERM-then-KILL sequence on its group). Once
    it has been reaped its pid may belong to someone else, so only the group is
    signaled: a group id is never reused while any member of it lives. The
    group gets SIGKILL if it outlasts the stop window. Safe to call twice."""
    if leader_alive:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            leader_alive = False
    if not leader_alive:
        if not _group_alive(pid):
            return        # nothing left in it, and its id may now lead another group
        try:
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return
    end = time.monotonic() + 2 * grace + 2
    while time.monotonic() < end:
        if not _group_alive(pid):
            return
        time.sleep(POLL)
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def popen(argv: list[str], *, timeout: float, grace: float = GRACE, **kwargs) -> subprocess.Popen:
    """subprocess.Popen under a watchdog. The caller must eventually wait() on it
    or call stop(proc.pid); stop_all() and the exit handlers cover the rest.
    stdin defaults to /dev/null rather than the caller's terminal."""
    for banned in ("start_new_session", "preexec_fn", "process_group"):
        if banned in kwargs:
            raise ValueError(f"procguard sets the process group itself; drop {banned}")
    kwargs.setdefault("stdin", subprocess.DEVNULL)
    # Spawn and register under the lock, so a closing stop_all() either sees
    # this child or refuses it; none slips in between.
    with _lock:
        if _closed:
            raise RuntimeError("procguard is stopping; no new children")
        proc = subprocess.Popen(wrap(argv, timeout, grace), start_new_session=True, **kwargs)
        _live[proc.pid] = proc
    return proc


def run(argv: list[str], *, timeout: float, input=None, capture_output: bool = False,
        check: bool = False, grace: float = GRACE, **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run under a watchdog. On timeout, or on any exception while
    waiting (KeyboardInterrupt included), the whole group is stopped before the
    exception propagates."""
    if capture_output:
        kwargs["stdout"] = kwargs["stderr"] = subprocess.PIPE
    if input is not None:
        kwargs["stdin"] = subprocess.PIPE
    started = time.monotonic()
    proc = popen(argv, timeout=timeout, grace=grace, **kwargs)
    try:
        # The watchdog enforces `timeout`; this backstop covers a watchdog that
        # could not run its own stop sequence.
        out, err = proc.communicate(input=input, timeout=float(timeout) + 2 * grace + 5)
    except subprocess.TimeoutExpired:
        _finish(proc, grace)
        raise subprocess.TimeoutExpired(argv, timeout)
    except BaseException:
        _finish(proc, grace)
        raise
    _forget(proc)
    # 124 alone could be the child's own status; the elapsed time tells them apart.
    if proc.returncode == EXIT_TIMEOUT and time.monotonic() - started >= float(timeout):
        raise subprocess.TimeoutExpired(argv, timeout, output=out, stderr=err)
    if check and proc.returncode:
        raise subprocess.CalledProcessError(proc.returncode, argv, out, err)
    return subprocess.CompletedProcess(argv, proc.returncode, out, err)


def stop_all(grace: float = GRACE, close: bool = False) -> None:
    """Stop every group this process still owns. Threads blocked in run() then
    return, so an executor's shutdown no longer waits on a hung child. With
    `close`, which the signal handlers use, every later popen() or run() is
    refused, so a worker thread cannot start a child after the stop."""
    global _closed
    with _lock:
        if close:
            _closed = True
        procs = list(_live.values())
    for proc in procs:
        _finish(proc, grace)


def install_signal_handlers() -> None:
    """Make SIGTERM and SIGHUP behave like Ctrl-C, after stopping every owned
    group first. Call once from the main thread of a CLI that spawns."""
    def handler(signum, frame):
        stop_all(close=True)
        raise KeyboardInterrupt(signal.Signals(signum).name)
    for sig in _STOP_SIGNALS:
        signal.signal(sig, handler)


def release(proc: subprocess.Popen) -> None:
    """Drop a popen() child the caller has already waited on from the registry
    that stop_all() and the exit handlers walk."""
    _forget(proc)


def _finish(proc: subprocess.Popen, grace: float) -> None:
    rc = proc.poll()
    # A watchdog that exited on its own swept its group first; only one that is
    # still running, or was killed before it could sweep and left members
    # behind, needs stopping. An empty group is never signaled: its id may
    # already lead someone else's group.
    if rc is None or (rc < 0 and _group_alive(proc.pid)):
        stop(proc.pid, grace, leader_alive=rc is None)
    for stream in (proc.stdin, proc.stdout, proc.stderr):
        if stream:
            try:
                stream.close()
            except OSError:
                pass
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        pass
    _forget(proc)


def _forget(proc: subprocess.Popen) -> None:
    with _lock:
        _live.pop(proc.pid, None)


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # macOS answers EPERM for a group whose members have all exited but are
        # not reaped yet: nothing in it can run, so it counts as gone.
        return False


atexit.register(stop_all)


# ---------- watchdog side ----------

def _members(exclude: set[int]) -> list[int]:
    """Live processes in this watchdog's group, other than `exclude`."""
    me = os.getpgrp()
    # By absolute path: a caller's PATH may not hold /bin, and a missing ps
    # must never be the reason a sweep finds nothing.
    ps = subprocess.Popen(["/bin/ps", "-A", "-o", "pid=,pgid=,stat="], stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, text=True)
    try:
        out, _ = ps.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        ps.kill()
        ps.wait()
        return []
    found = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        pid, pgid, stat = int(parts[0]), int(parts[1]), parts[2]
        if pgid == me and pid not in exclude and pid != ps.pid and not stat.startswith("Z"):
            found.append(pid)
    return found


def _sweep(child: subprocess.Popen, grace: float) -> None:
    """TERM the group, wait out the grace period, then KILL whatever ps still
    shows in it. The watchdog's own handlers absorb its copy of the TERM."""
    me = os.getpid()
    try:
        os.killpg(os.getpgrp(), signal.SIGTERM)
    except OSError:
        pass
    end = time.monotonic() + grace
    while time.monotonic() < end:
        child.poll()
        if not _members({me}):
            return
        time.sleep(POLL)
    for pid in _members({me}):
        try:
            # Re-check membership at the last moment: a pid from the listing may
            # have exited and been reused since.
            if os.getpgid(pid) == os.getpgrp():
                os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    end = time.monotonic() + grace
    while time.monotonic() < end:
        child.poll()
        if not _members({me}):
            return
        time.sleep(POLL)


def _watch(argv: list[str], parent: int, timeout: float, grace: float) -> int:
    if os.getpgrp() != os.getpid():
        os.setsid()
    reason: list[str] = []

    def on_signal(signum, frame):
        if not reason:
            reason.append(signal.Signals(signum).name)
    for sig in _STOP_SIGNALS:
        signal.signal(sig, on_signal)

    deadline = time.monotonic() + timeout
    try:
        child = subprocess.Popen(argv)
    except OSError as e:
        _notice(f"procguard: cannot start {argv[0]}: {e}")
        return 127
    while True:
        rc = child.poll()
        if rc is not None:
            # The child is done; anything it left in the group goes with it.
            _sweep(child, grace)
            return rc if rc >= 0 else 128 - rc
        if not reason:
            if parent and os.getppid() != parent:
                reason.append("parent exited")
            elif time.monotonic() >= deadline:
                reason.append(f"time limit {timeout:g} s")
        if reason:
            # Sweep before saying anything: when the parent died, its end of our
            # stderr may be a closed pipe, and a failed write must not skip the sweep.
            _sweep(child, grace)
            _notice(f"procguard: stopped {os.path.basename(argv[0])} ({reason[0]})")
            return EXIT_TIMEOUT if reason[0].startswith("time limit") else EXIT_STOPPED
        time.sleep(POLL)


def _notice(text: str) -> None:
    try:
        print(text, file=sys.stderr, flush=True)
    except (OSError, ValueError):
        pass


def main(args: list[str] | None = None) -> int:
    # Exact option names only, each at most once: an abbreviation or a repeated
    # --timeout must never change what a hook that read the line approved.
    ap = argparse.ArgumentParser(prog="procguard.py", allow_abbrev=False,
                                 description="Run a command under a wall-clock cap in its own process group; "
                                             "the whole group stops at the cap or when the caller goes away.")
    ap.add_argument("--timeout", type=float, required=True, help="seconds before the group is stopped")
    ap.add_argument("--grace", type=float, default=GRACE,
                    help=f"seconds between SIGTERM and SIGKILL, at most {MAX_GRACE:g}")
    ap.add_argument("--parent", type=int, default=0, help="pid whose exit stops the group (default: the caller)")
    ap.add_argument("--detached", action="store_true",
                    help="the command is meant to outlive its caller (a hook's follow-up job): "
                         "only the time limit stops it")
    ap.add_argument("command", nargs=argparse.REMAINDER, help="-- command [args...]")
    raw = sys.argv[1:] if args is None else args
    head = raw[:raw.index("--")] if "--" in raw else raw
    for opt in ("--timeout", "--grace", "--parent", "--detached"):
        if sum(1 for t in head if t == opt or t.startswith(opt + "=")) > 1:
            ap.error(f"{opt} given more than once")
    a = ap.parse_args(args)
    if not 0 <= a.grace <= MAX_GRACE:
        ap.error(f"--grace must be between 0 and {MAX_GRACE:g} seconds")
    cmd = a.command[1:] if a.command[:1] == ["--"] else a.command
    if not cmd:
        ap.error("no command given after --")
    if not 0 < a.timeout < float("inf"):                            # also refuses NaN
        ap.error("--timeout must be positive and finite")
    if a.detached and a.parent:
        ap.error("--detached and --parent contradict each other")
    return _watch(cmd, 0 if a.detached else (a.parent or os.getppid()), a.timeout, a.grace)


if __name__ == "__main__":
    sys.exit(main())
