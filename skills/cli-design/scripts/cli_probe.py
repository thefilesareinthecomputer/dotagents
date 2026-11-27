#!/usr/bin/env python3
"""Probe a command-line program from the outside and report where it breaks
the conventions in references/standard.md.

    cli_probe.py [options] -- COMMAND [ARGS...]

The probe runs COMMAND only with `--help`, `-h`, `--version` and one unknown
flag, each with stdin closed and a time limit. It runs nothing else unless
asked: `--sub NAME` adds `COMMAND NAME --help`, `--no-args` runs COMMAND exactly as given after `--`,
and `--json-args ARGS` runs COMMAND with ARGS and checks the output parses.

Exit status: 0 no failures, 1 at least one failure (or a warning with
--strict), 2 the probe itself was called wrongly.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import procguard  # noqa: E402

UNKNOWN_FLAG = "--cli-probe-unknown-flag"
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
SGR = re.compile(r"\x1b\[[0-9;]*m")
TRACE_MARKS = (
    "Traceback (most recent call last)",
    "panic: ",
    "goroutine 1 [",
    "    at Object.<anonymous>",
    "Unhandled exception",
    "stack backtrace:",
)
SLOW_HELP_SECONDS = 1.0

PASS, WARN, FAIL, SKIP = "pass", "warn", "fail", "skip"
HUNG = object()  # call_on_terminal's result when the program outlived its limit


class Run:
    """One finished call of the target."""

    def __init__(self, argv, code, out, err, seconds, timed_out):
        self.argv = argv
        self.code = code
        self.out = out
        self.err = err
        self.seconds = seconds
        self.timed_out = timed_out


def call(argv, timeout, env=None):
    started = time.monotonic()
    try:
        proc = procguard.run(
            argv, timeout=timeout, capture_output=True, text=True,
            errors="replace", stdin=subprocess.DEVNULL, env=env,
        )
    except subprocess.TimeoutExpired:
        return Run(argv, None, "", "", time.monotonic() - started, True)
    except (FileNotFoundError, PermissionError) as exc:
        raise SystemExit2("cannot run %s: %s" % (argv[0], exc))
    return Run(argv, proc.returncode, proc.stdout or "", proc.stderr or "",
               time.monotonic() - started, False)


def call_on_terminal(argv, timeout, env):
    """Run argv with stdout and stderr on a pseudo-terminal and return what it
    wrote, or None where no pseudo-terminal is available."""
    try:
        import pty
        import select
    except ImportError:
        return None
    try:
        master, slave = pty.openpty()
    except OSError:
        return None
    chunks = []
    try:
        proc = procguard.popen(argv, timeout=timeout, stdin=subprocess.DEVNULL,
                               stdout=slave, stderr=slave, env=env)
    except (FileNotFoundError, PermissionError):
        os.close(master)
        os.close(slave)
        return None
    os.close(slave)
    started = time.monotonic()
    deadline = started + timeout + 5
    hung = False
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master], [], [], 0.2)
            if ready:
                try:
                    data = os.read(master, 65536)
                except OSError:
                    break
                if not data:
                    break
                chunks.append(data)
            elif proc.poll() is not None:
                break
    finally:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            hung = True
            procguard.stop(proc.pid)
        # The watchdog ends a child that outlives the limit and exits 124 itself.
        if proc.returncode == procguard.EXIT_TIMEOUT and time.monotonic() - started >= timeout:
            hung = True
        procguard.release(proc)
        os.close(master)
    if hung:
        return HUNG
    return b"".join(chunks).decode("utf-8", "replace")


class SystemExit2(Exception):
    pass


class Report:
    def __init__(self):
        self.results = []

    def add(self, check, status, detail, rule):
        self.results.append({"check": check, "status": status, "detail": detail, "rule": rule})

    def count(self, status):
        return sum(1 for r in self.results if r["status"] == status)


def first_line(text):
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:120]
    return ""


def check_help(report, run, label, flag):
    """Checks shared by `--help`, `-h` and each subcommand's help."""
    name = "%s %s" % (label, flag) if label else flag
    if run.timed_out:
        report.add("no-hang", FAIL, "`%s` did not return with stdin closed" % name, "robustness")
        return False
    ok = True
    if run.code != 0:
        report.add("help-exit", FAIL, "`%s` exited %s, expected 0" % (name, run.code), "help")
        ok = False
    if not run.out.strip():
        where = "stderr" if run.err.strip() else "nowhere"
        report.add("help-stream", FAIL,
                   "`%s` wrote its help to %s; requested help belongs on stdout" % (name, where), "streams")
        ok = False
    if ANSI.search(run.out) or ANSI.search(run.err):
        report.add("plain-when-piped", FAIL,
                   "`%s` wrote terminal escape codes while not on a terminal" % name, "color")
        ok = False
    return ok


def probe(command, timeout, subs, no_args, json_args):
    report = Report()
    env = dict(os.environ)
    env.pop("NO_COLOR", None)
    env.pop("FORCE_COLOR", None)
    env.pop("CLICOLOR_FORCE", None)

    # --help
    run = call(command + ["--help"], timeout, env)
    help_text = run.out
    help_returned = not run.timed_out
    if check_help(report, run, "", "--help"):
        report.add("help", PASS, "`--help` exits 0 and writes plain text to stdout", "help")
    if not run.timed_out:
        if re.search(r"(?im)^\s*examples?\b", help_text) or "example" in help_text.lower():
            report.add("help-examples", PASS, "help shows an example", "help")
        elif help_text.strip():
            report.add("help-examples", WARN, "help shows no example; lead with one or two", "help")
        if run.seconds > SLOW_HELP_SECONDS:
            report.add("help-speed", WARN,
                       "`--help` took %.1f s; help should not load the whole program" % run.seconds, "robustness")

    # -h
    run = call(command + ["-h"], timeout, env)
    if run.timed_out:
        report.add("no-hang", FAIL, "`-h` did not return with stdin closed", "robustness")
    elif run.code == 0 and run.out.strip():
        report.add("help-short", PASS, "`-h` shows help", "help")
    else:
        report.add("help-short", WARN, "`-h` does not show help (exit %s)" % run.code, "help")

    # --version
    run = call(command + ["--version"], timeout, env)
    if run.timed_out:
        report.add("no-hang", FAIL, "`--version` did not return with stdin closed", "robustness")
    elif run.code == 0 and re.search(r"\d", first_line(run.out)):
        report.add("version", PASS, "`--version` prints `%s`" % first_line(run.out), "help")
    elif run.code == 0 and re.search(r"\d", first_line(run.err)):
        report.add("version", WARN, "`--version` writes to stderr; it belongs on stdout", "streams")
    else:
        report.add("version", WARN, "`--version` does not print a version (exit %s)" % run.code, "help")

    # unknown flag
    run = call(command + [UNKNOWN_FLAG], timeout, env)
    if run.timed_out:
        report.add("no-hang", FAIL, "an unknown flag did not return with stdin closed", "robustness")
    else:
        if run.code == 0:
            report.add("usage-exit", FAIL, "an unknown flag exited 0; a usage error must exit nonzero", "exit-codes")
        else:
            note = "" if run.code == 2 else " (2 is the common code for a usage error)"
            report.add("usage-exit", PASS, "an unknown flag exits %s%s" % (run.code, note), "exit-codes")
        if run.out.strip():
            report.add("usage-stream", FAIL,
                       "an unknown flag wrote to stdout; errors belong on stderr so pipes stay clean", "streams")
        elif not run.err.strip():
            report.add("usage-stream", FAIL, "an unknown flag produced no message", "errors")
        else:
            report.add("usage-stream", PASS, "the usage error goes to stderr and stdout stays empty", "streams")
        both = run.out + run.err
        if any(mark in both for mark in TRACE_MARKS):
            report.add("usage-trace", FAIL, "a usage error shows a raw stack trace", "errors")
        elif both.strip():
            lowered = both.lower()
            if UNKNOWN_FLAG in both or "usage" in lowered or "help" in lowered:
                report.add("usage-hint", PASS, "the usage error names the flag or points to help", "errors")
            else:
                report.add("usage-hint", WARN,
                           "the usage error does not name the flag or point to `--help`", "errors")

    # NO_COLOR on a terminal
    colored_env = dict(env)
    colored_env["NO_COLOR"] = "1"
    colored_env.setdefault("TERM", "xterm-256color")
    shown = call_on_terminal(command + ["--help"], timeout, colored_env) if help_returned else None
    if not help_returned:
        report.add("no-color", SKIP, "`--help` did not return; NO_COLOR not checked", "color")
    elif shown is HUNG:
        report.add("no-color", SKIP, "`--help` did not return on a terminal; NO_COLOR not checked", "color")
        report.add("no-hang", FAIL, "`--help` did not return when run on a terminal", "robustness")
    elif shown is None:
        report.add("no-color", SKIP, "no pseudo-terminal here; NO_COLOR not checked", "color")
    elif SGR.search(shown):
        report.add("no-color", FAIL, "color is written on a terminal even with NO_COLOR set", "color")
    else:
        report.add("no-color", PASS, "NO_COLOR is respected on a terminal", "color")

    # subcommands
    for sub in subs:
        run = call(command + [sub, "--help"], timeout, env)
        if check_help(report, run, sub, "--help"):
            report.add("sub-help", PASS, "`%s --help` exits 0 and writes plain text to stdout" % sub, "help")

    # bare call, opt-in
    if no_args:
        run = call(command, timeout, env)
        if run.timed_out:
            report.add("no-args", FAIL,
                       "a bare call did not return with stdin closed; it may be waiting for input", "interactivity")
        elif any(mark in run.out + run.err for mark in TRACE_MARKS):
            report.add("no-args", FAIL, "a bare call shows a raw stack trace", "errors")
        elif not (run.out + run.err).strip():
            report.add("no-args", WARN, "a bare call prints nothing; show short help or a next step", "help")
        else:
            report.add("no-args", PASS, "a bare call returns and says something (exit %s)" % run.code, "help")

    # machine output, opt-in
    if json_args is not None:
        run = call(command + json_args, timeout, env)
        shown_args = " ".join(json_args)
        if run.timed_out:
            report.add("json", FAIL, "`%s` did not return with stdin closed" % shown_args, "robustness")
        elif ANSI.search(run.out):
            report.add("json", FAIL, "`%s` wrote terminal escape codes into its output" % shown_args, "machine-output")
        elif not parses_as_json(run.out):
            report.add("json", FAIL,
                       "`%s` stdout is neither one JSON value nor JSON Lines" % shown_args, "machine-output")
        else:
            report.add("json", PASS, "`%s` stdout parses as JSON" % shown_args, "machine-output")
    return report


def parses_as_json(text):
    if not text.strip():
        return False
    try:
        json.loads(text)
        return True
    except ValueError:
        pass
    lines = [line for line in text.splitlines() if line.strip()]
    try:
        for line in lines:
            json.loads(line)
    except ValueError:
        return False
    return True


def render(report, command, stream):
    width = max(len(r["check"]) for r in report.results) if report.results else 0
    for r in report.results:
        stream.write("%-4s  %-*s  %s\n" % (r["status"].upper(), width, r["check"], r["detail"]))
    stream.write("\n%s: %d failed, %d warned, %d passed, %d skipped\n" % (
        " ".join(command), report.count(FAIL), report.count(WARN), report.count(PASS), report.count(SKIP)))


def build_parser():
    parser = argparse.ArgumentParser(
        prog="cli_probe.py",
        description="Probe a command-line program from the outside and report where it breaks common conventions.",
        epilog=(
            "examples:\n"
            "  cli_probe.py -- mytool\n"
            "  cli_probe.py --sub init --sub run -- python3 mytool.py\n"
            "  cli_probe.py --json --json-args 'list --json' -- mytool\n"
            "\n"
            "Only --help, -h, --version and one unknown flag are run unless --sub,\n"
            "--no-args or --json-args ask for more. Exit 0: no failures. Exit 1: a\n"
            "failure, or a warning with --strict. Exit 2: bad arguments to the probe."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version="cli_probe 1")
    parser.add_argument("--json", action="store_true", help="write the report as JSON to stdout")
    parser.add_argument("--strict", action="store_true", help="exit 1 on a warning as well as a failure")
    parser.add_argument("--timeout", type=float, default=10.0, metavar="SECONDS",
                        help="time limit for each call of the target (default 10)")
    parser.add_argument("--sub", action="append", default=[], metavar="NAME",
                        help="also check `COMMAND NAME --help`; repeat for more")
    parser.add_argument("--no-args", action="store_true",
                        help="also run COMMAND exactly as given after `--` (that call must be safe)")
    parser.add_argument("--json-args", metavar="ARGS",
                        help="also run COMMAND with ARGS and require JSON or JSON Lines on stdout")
    parser.add_argument("command", nargs=argparse.REMAINDER, metavar="-- COMMAND [ARGS...]",
                        help="the program to probe, after `--`")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("name the program to probe after `--`, for example: cli_probe.py -- mytool")
    if shutil.which(command[0]) is None:
        sys.stderr.write("cli_probe.py: cannot find `%s`; give a program on PATH or a path to one\n" % command[0])
        return 2
    if args.timeout <= 0:
        parser.error("--timeout must be greater than 0")
    json_args = None
    if args.json_args is not None:
        try:
            json_args = shlex.split(args.json_args)
        except ValueError as exc:
            parser.error("--json-args: %s" % exc)
    procguard.install_signal_handlers()
    try:
        report = probe(command, args.timeout, args.sub, args.no_args, json_args)
    except SystemExit2 as exc:
        sys.stderr.write("cli_probe.py: %s\n" % exc)
        return 2
    if args.json:
        json.dump({
            "command": command,
            "results": report.results,
            "summary": {s: report.count(s) for s in (FAIL, WARN, PASS, SKIP)},
        }, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        render(report, command, sys.stdout)
    if report.count(FAIL) or (args.strict and report.count(WARN)):
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.stderr.write("cli_probe.py: interrupted\n")
        sys.exit(130)
    except BrokenPipeError:
        sys.exit(141)
