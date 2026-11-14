#!/usr/bin/env python3
"""PreToolUse hook on the shell: refuse an agent's bypass of the station's git hooks.

The station's commit and push check (`sanitize gate`, behind the global core.hooksPath)
is only worth having if an agent cannot step around it. This refuses, from an agent:

  git commit --no-verify (or an unambiguous abbreviation such as --no-verif), or a
                                        short-flag cluster holding n (`-n`, `-an`)
  git push --no-verify                  (for push, -n is a dry run and passes)
  git -c core.hooksPath=... or include.path=..., and the --config-env= form, on any git command
  GIT_CONFIG_*, HOME or XDG_CONFIG_HOME set on, or exported before, a git commit,
                                        push or merge (each one drops the global hooks path)
  git config ... core.hooksPath         a write; `--get`, `--list` and `get` reads pass
  hooks/git/install.sh --uninstall or --force

The command is tokenized with quotes respected and cut at shell control tokens (`;`, `&&`,
`||`, `|`, `&`, `(`, `)`, `;;`, newline), so a separator inside a quoted commit message
splits nothing. Each simple command is read after unwrapping `(`, `{`, `!`, shell
keywords, env (including `env -i` and `env -u NAME`), command, exec, sudo, nice, time,
nohup and xargs and leading VAR=value assignments, so a command that only mentions these
strings (a grep, an echo, `sanitize copy --no-verify`) passes. The user runs the same commands from their own
terminal, where no PreToolUse hook exists; that is the whole escape hatch, and it needs
no state file. Not a sandbox: an alias, a variable, `bash -c`, `$(...)`, backticks and
a relative `install.sh` call from inside `hooks/git/` are not seen.

Exit 2 with the reason on stderr to refuse; exit 0 otherwise, including on any error
of its own.
"""
from __future__ import annotations

import importlib.util
import re
import shlex
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("_input", Path(__file__).with_name("_input.py"))
_input = importlib.util.module_from_spec(_spec)
sys.modules["_input"] = _input
_spec.loader.exec_module(_input)

# Fallback splitter for a command with unbalanced quotes, which the tokenizer refuses.
SEPARATORS = re.compile(r"&&|\|\||;|\||\n|(?<![&>])&(?![&>])")  # no \s* around it: that is quadratic on long whitespace
# Shell control tokens that end one simple command. Redirections (`2>&1`, `&>`) come out of
# the tokenizer as their own tokens and are not separators.
SEPARATOR_TOKENS = {";", ";;", ";&", ";;&", "&", "&&", "||", "|", "|&", "(", ")", "\n"}
ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=")
WRAPPERS = {"env", "command", "exec", "sudo", "nice", "time", "nohup", "xargs", "rtk", "proxy",
            "if", "then", "else", "elif", "do", "while", "until", "!", "{", "("}
# What `env -i` (or a bare `env -`) removes that matters here.
ENV_CLEARED = {"HOME", "XDG_CONFIG_HOME"}


def config_override(name: str) -> bool:
    """A variable that, set or removed on a hooked git command, makes git skip the global
    hooks path: any GIT_CONFIG* name, or HOME and XDG_CONFIG_HOME exactly."""
    return name.startswith("GIT_CONFIG") or name in ENV_CLEARED
NO_VERIFY = "--no-verify"
NO_VERIFY_MIN = len("--no-veri")      # shorter prefixes are ambiguous with --no-verbose
# wrapper flags that take the next word as their value
WRAPPER_ARGS = {"-u", "-g", "-n", "-C", "-I", "-L", "-P", "-s", "-E", "-S", "-a", "-d"}
GIT_GLOBAL_ARGS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--exec-path"}
HOOKED = {"commit", "push", "merge"}
# git commit options whose value is the next word, so "-m -n" is a message, not a flag
COMMIT_VALUE_OPTS = {"-m", "-F", "-C", "-c", "-t", "--message", "--file", "--author", "--date",
                     "--template", "--reuse-message", "--reedit-message", "--fixup", "--squash",
                     "--cleanup", "--trailer", "--pathspec-from-file"}
COMMIT_VALUE_SHORT = set("mFCct")
COMMIT_OPTIONAL_SHORT = set("uS")     # an attached optional value follows (-uno, -S<keyid>)
CONFIG_READS = {"--get", "--get-all", "--get-regexp", "--get-urlmatch", "-l", "--list", "get", "list"}
HOOKS_KEY = "core.hookspath"


def overrides_hooks(key: str) -> bool:
    """A -c key that sets the hooks path directly or pulls in a file that could."""
    k = key.lower()
    return k == HOOKS_KEY or k == "include.path" or (k.startswith("includeif.") and k.endswith(".path"))


def is_no_verify(arg: str) -> bool:
    return arg == NO_VERIFY or (len(arg) >= NO_VERIFY_MIN and NO_VERIFY.startswith(arg))

REASON = ("Blocked: agents do not bypass the station's git hooks ({what}). The hooks run the content "
          "check every commit and push passes. If it flagged something, fix the content; if you think it "
          "is wrong, stop and ask the user, who can run the same command from their own terminal.")


def words_of(segment: str) -> list[str]:
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def segments(command: str) -> list[list[str]]:
    """The command's simple commands as word lists. The tokenizer keeps quoted text whole,
    so a `;`, `|` or `&` inside a commit message never splits a command; a newline still
    separates commands."""
    try:
        lex = shlex.shlex(command or "", posix=True, punctuation_chars=";&|()<>\n")
        lex.whitespace_split = True
        lex.whitespace = lex.whitespace.replace("\n", "")
        tokens = list(lex)
    except ValueError:
        return [words_of(s) for s in SEPARATORS.split(command or "")]
    out: list[list[str]] = []
    current: list[str] = []
    for tok in tokens:
        if tok in SEPARATOR_TOKENS:
            if current:
                out.append(current)
            current = []
        else:
            current.append(tok)
    if current:
        out.append(current)
    return out


def unwrap(words: list[str]) -> tuple[list[str], set[str]]:
    """(the command's own words, the names assigned in front of it)."""
    assigned: set[str] = set()
    i = 0
    while i < len(words):
        w = words[i]
        stripped = w.lstrip("({!")
        if stripped != w:
            if not stripped:
                i += 1
                continue
            words = words[:i] + [stripped] + words[i + 1:]
            w = stripped
        m = ASSIGNMENT.match(w)
        if m:
            assigned.add(m.group(1))
            i += 1
            continue
        if Path(w).name in WRAPPERS:
            is_env = Path(w).name == "env"
            i += 1
            while i < len(words) and words[i].startswith("-"):
                flag = words[i]
                if is_env:
                    # env -i / env - clears the environment; env -u NAME removes one name
                    if flag in ("-i", "--ignore-environment", "-"):
                        assigned |= ENV_CLEARED
                    elif flag in ("-u", "--unset") and i + 1 < len(words):
                        assigned.add(words[i + 1])
                        i += 2
                        continue
                    elif flag.startswith("--unset="):
                        assigned.add(flag.split("=", 1)[1])
                    elif flag.startswith("-u") and len(flag) > 2:
                        assigned.add(flag[2:])
                i += 2 if flag in WRAPPER_ARGS else 1
            continue
        break
    return words[i:], assigned


def git_call(words: list[str]) -> tuple[str | None, list[str], list[str]]:
    """(subcommand, its arguments, the config keys set with -c / --config-env)."""
    keys: list[str] = []
    i = 1
    while i < len(words) and words[i].startswith("-"):
        w = words[i]
        if w in ("-c", "--config-env") and i + 1 < len(words):
            keys.append(words[i + 1].split("=", 1)[0])
            i += 2
            continue
        if w.startswith("--config-env="):
            keys.append(w.split("=", 1)[1].split("=", 1)[0])
        elif w in GIT_GLOBAL_ARGS and i + 1 < len(words):
            i += 2
            continue
        i += 1
    if i >= len(words):
        return None, [], keys
    return words[i], words[i + 1:], keys


def commit_bypasses(args: list[str]) -> bool:
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            return False
        if is_no_verify(a):
            return True
        if a in COMMIT_VALUE_OPTS:
            i += 2
            continue
        if a.startswith("-") and not a.startswith("--") and len(a) > 1:
            for ch in a[1:]:
                if ch == "n":
                    return True
                if ch in COMMIT_OPTIONAL_SHORT:
                    break               # the rest of the cluster is its attached value
                if ch in COMMIT_VALUE_SHORT:
                    if a.endswith(ch):
                        i += 1          # the value is the next word
                    break
        i += 1
    return False


def config_writes_hooks_path(args: list[str]) -> bool:
    if any(a in CONFIG_READS for a in args):
        return False
    return any(a.lower() == HOOKS_KEY or a.lower().startswith(HOOKS_KEY + "=") for a in args)


def bypass(command: str) -> str | None:
    """A description of the bypass this command attempts, or None."""
    exported: set[str] = set()
    for words in segments(command):
        if words and words[0] in ("export", "declare", "typeset"):
            exported |= {m.group(1) for w in words[1:] if (m := ASSIGNMENT.match(w))}
            continue
        words, assigned = unwrap(words)
        if any(w.endswith("hooks/git/install.sh") for w in words) and \
                any(a in ("--uninstall", "--force") for a in words):
            return "removing or replacing the station hooks path"
        if not words or Path(words[0]).name != "git":
            continue
        sub, args, keys = git_call(words)
        if any(overrides_hooks(k) for k in keys):
            return "a core.hooksPath override"
        env = {n for n in assigned | exported if config_override(n)}
        if env and sub in HOOKED:
            return "a GIT_CONFIG_*, HOME or XDG_CONFIG_HOME override"
        if sub == "commit" and commit_bypasses(args):
            return "git commit --no-verify"
        if sub in ("push", "merge") and any(is_no_verify(a) for a in args):
            return f"git {sub} --no-verify"
        if sub == "config" and config_writes_hooks_path(args):
            return "a core.hooksPath change"
    return None


def main() -> int:
    ev = _input.read_event()
    if ev.tool_class != "shell" or "git" not in ev.command:
        return 0
    what = bypass(ev.command)
    if not what:
        return 0
    print(REASON.format(what=what), file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:                                  # never brick the shell on a bug here
        print(f"guard_git_bypass error, command allowed: {type(exc).__name__}", file=sys.stderr)
        sys.exit(0)
