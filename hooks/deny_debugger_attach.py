#!/usr/bin/env python3
"""PreToolUse hook on the shell: refuse an agent's debugger or developer-tools command.

Attaching a debugger to a running process pauses it, can end it, and on macOS raises the
system's developer-tools permission prompt over whatever the user is doing. This refuses,
from an agent, any simple command whose program is one of:

  lldb, gdb, debugserver   a debugger, attached or not
  DevToolsSecurity         the macOS switch for developer-tools access

A command that only mentions these words (a grep, an echo, a path argument, a commit
message, a here-document) passes: the program is read after unwrapping `sudo`, `env`,
`xcrun`, `arch`, `xargs`, `timeout`, `nice`, `nohup`, `time`, `command`, `exec` and leading
VAR=value assignments, in each simple command. Commands are cut at shell control tokens by
the git-bypass guard's tokenizer, which keeps quoted text whole, and here-document bodies
are left out. The user runs the same commands from their own terminal, where no PreToolUse
hook exists; that is the whole escape hatch. A `bash -c` string, a here-document fed to a
shell, a `<<` inside quotes, backticks, an alias or a variable is not seen: this guards the honest case. A
command longer than MAX_COMMAND characters is not read at all.

Exit 2 with the reason on stderr to refuse; exit 0 otherwise, including on any error of
its own, a missing sibling module among them.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

PROGRAMS = {"lldb", "gdb", "debugserver", "devtoolssecurity"}
WRAPPERS = {"sudo", "env", "xcrun", "arch", "xargs", "nice", "nohup", "time", "command", "exec",
            "caffeinate", "!", "{"}
FLAGGED = ("sudo", "env", "nice", "caffeinate", "arch", "xargs")  # wrappers whose own flags come next
TAKES_ARG = {"timeout": 1, "gtimeout": 1}
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# The opening of a here-document: `<<WORD`, `<<-WORD`, `<<'WORD'`. Never `<<<`, a here-string.
HEREDOC = re.compile(r"(?<!<)<<(?!<)-?[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
MAX_COMMAND = 32_000  # an agent's debugger command is short; a longer command passes unread

REASON = (
    "Blocked: {program} attaches to processes or changes developer-tools access. It can "
    "freeze or kill the process it touches and raises a system permission prompt over "
    "whatever the user is doing. Do not run it, and do not reach the same result another "
    "way. If it is truly needed, say why in your reply and let the user run it themselves "
    "with `!`."
)


def sibling(name: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def without_heredocs(command: str) -> str:
    """The command with every here-document body and closing word left out. One pass over the
    lines: an opening line is kept, and the lines after it are skipped up to its closing word."""
    kept: list[str] = []
    closing = ""
    for line in command.split("\n"):
        if closing:
            if line.strip() == closing:
                closing = ""
            continue
        kept.append(line)
        opening = HEREDOC.search(line)
        if opening:
            closing = opening.group(2)
    return "\n".join(kept)


def program_of(words: list[str]) -> str:
    i = 0
    while i < len(words):
        w = words[i]
        base = w.rsplit("/", 1)[-1].lower()
        if ASSIGNMENT.match(w) or base in WRAPPERS:
            i += 1
            while i < len(words) and base in FLAGGED and words[i].startswith("-"):
                i += 1
            continue
        if base in TAKES_ARG:
            i += 1
            while i < len(words) and words[i].startswith("-"):
                i += 2 if words[i] in ("-s", "-k") else 1  # these two take a value
            i += TAKES_ARG[base]
            continue
        return base
    return ""


def offending(command: str, segments) -> str:
    if len(command) > MAX_COMMAND:
        return ""
    for words in segments(without_heredocs(command)):
        prog = program_of(words)
        if prog in PROGRAMS:
            return prog
    return ""


def main() -> int:
    ev = sibling("_input").read_event()
    if ev.tool_class != "shell" or not ev.command:
        return 0
    # The git-bypass guard's quote-aware split into simple commands.
    prog = offending(ev.command, sibling("guard_git_bypass").segments)
    if not prog:
        return 0
    print(REASON.format(program=prog), file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:                                  # never brick the shell on a bug here
        print(f"deny_debugger_attach error, command allowed: {type(exc).__name__}", file=sys.stderr)
        sys.exit(0)
