---
name: cli-design
description: >-
  CLI design standard and checker - builds, extends and audits any CLI, command-line tool or
  shell or Python script with flags, for people, pipes and AI agents. Covers
  argument parsing, --help text, stdout and stderr, exit codes, errors and
  tracebacks, color, progress bars, prompts, --dry-run, --json and Ctrl-C.
  MUST be used before writing any new CLI or script that takes flags or arguments, however
  small - do not just write the script. MUST be used before editing a CLI, script, REPL, chat
  shell or TUI that hangs or prompts for input in CI, cron or a pipe, puts escape codes or
  junk in piped output, reports success when it failed, or dies or breaks the terminal on
  Ctrl-C - even when the fix looks obvious. Also when adding a subcommand, flag or output mode, making a tool non-interactive or
  callable by an agent, or reviewing a CLI before release. Other CI failures, packaging, library
  and HTTP API design, web UI and MCP servers belong elsewhere.
license: MIT
---

# cli-design

This skill gets a command-line program to behave the way its callers already expect.
Its callers are a person at a terminal, a shell script, and an agent with no terminal at all.
The work has three parts: agree the contract, build to the standard, and probe the result.

## 1. Agree the contract before the parser

Write this down first, and show it to the user when the program is new or the change alters what callers see.

| Item | Decide |
|---|---|
| Commands | Each command, in one line, and whether it reads, writes or destroys |
| Input | Arguments, flags, and what comes from stdin |
| Result | What goes to stdout, in text and with `--json` |
| Exit codes | 0, the usage-error code, and each failure a caller would handle differently |
| Without a terminal | What happens to every prompt when stdin is not a terminal |
| Settings | Flags, environment variables and files, and which wins |
| Files touched | Every path the program writes outside what the user named |

An existing program already has a contract: its current flags, output and exit codes.
Add to it. Changing or removing something callers use is a breaking change, and the user decides on it.

## 2. Build to the standard

These rules are the ones callers break on most. The full standard, with the source for each rule, is `references/standard.md`.

- `--help` and `-h` print help with an example to stdout and exit 0. `--version` prints a version.
- stdout holds the result and nothing else. Progress, warnings, errors and prompts go to stderr.
- Exit 0 on success, 2 on a usage error, 1 or a documented code on failure.
- An error names what was wrong and the next thing to do. A usage error never shows a stack trace.
- Color and progress appear only on a terminal, and never when `NO_COLOR` is set to a non-empty value.
- With stdin closed or piped, the program returns. Every prompt has a flag, and `--no-input` turns prompts off.
- Anything that writes offers `--dry-run`. Anything that destroys asks first, and needs `--force` without a terminal.
- `--json` puts one JSON value, or one JSON object per line, on stdout with nothing else, in a shape that only grows.
- Every network call and child process has a time limit, and children stop when the program stops.
- Running a command twice is safe.

Read `references/standard.md` when designing the contract, when a rule here needs its detail, and for configuration, secrets and programs that agents call.

Read `references/interactive.md` for a prompt loop, a chat or agent shell, or a full-screen interface: one-shot mode, Ctrl-C and Ctrl-D, restoring the terminal, and streaming output.

## 3. Probe the built program

EXECUTE the probe; do not read it to learn the rules.

```
python3 scripts/cli_probe.py -- COMMAND [ARGS...]
python3 scripts/cli_probe.py --sub init --sub run -- COMMAND
python3 scripts/cli_probe.py --no-args --json-args 'list --json' -- COMMAND
```

`scripts/cli_probe.py` is relative to the folder this file is in; call it by its full path from wherever the program lives. It needs `python3`.
One check runs the program on a pseudo-terminal, a stand-in that makes the program believe it is writing to a real terminal. Windows has none, so the check is skipped there.
`COMMAND` is everything after `--`: a program on `PATH`, a path to one, or an interpreter and a script (`-- python3 tool.py`). The probe exits 2 when it cannot find it.

**Before the first probe, confirm the program parses its arguments.** A script with no argument parser may do its real work when called with `--help` or an unknown flag. Read its entry point first. A parser is anything that rejects an unknown flag before the work starts: `argparse`, `getopts`, a command framework, or a hand-written check. When there is none, that is the first finding, and the probe waits until one exists. Check too that `-h` and `--version` either mean help and version or are not defined: a program where `-h` means "host" or "halt" would act on the probe's call.

By default the probe makes five calls, each with stdin at end-of-file and a 10-second limit: `--help`, `-h`, `--version`, one unknown flag, and `--help` once more on a pseudo-terminal with `NO_COLOR=1`. It removes `NO_COLOR`, `FORCE_COLOR` and `CLICOLOR_FORCE` from the environment for the other four.

| Option | Effect | Use when |
|---|---|---|
| `--sub NAME` | Also runs `COMMAND NAME --help` | The program has subcommands; repeat per subcommand |
| `--no-args` | Also runs `COMMAND` exactly as given after `--` | That call changes nothing and starts nothing heavy |
| `--json-args 'ARGS'` | Also runs `COMMAND ARGS` and requires JSON on stdout | `ARGS` is a read-only call |
| `--timeout SECONDS` | Changes the limit for each call | The program is slow to start |
| `--strict` | Exits 1 on a warning too | Gating a release |
| `--json` | Writes the report as JSON | Another program reads it |

Skip `--no-args` for a session program whose bare call opens its prompt loop, loads a model or connects to a service. Read the entry point to see what a bare call with no terminal does. If it starts the session, record that as a finding against `references/interactive.md` without running it.

Each line of the report is a status, a check name, and what was seen.

| Status | Meaning | Do |
|---|---|---|
| `FAIL` | A rule is broken | Fix it |
| `WARN` | A judgment call, such as no example in the help or no `-h` | Fix it, or say why it stands |
| `SKIP` | The `no-color` check could not run: no pseudo-terminal, or `--help` never returned | Report it as not checked |
| `PASS` | The check held | Nothing |

With `--json` the statuses are lowercase, and the report has `command`, `results` and `summary`. Each result's `rule` is a section name in `references/standard.md`.
The probe exits 0 with no failures, 1 with a failure, and 2 when it was called wrongly.

The probe sees only the surface, and it is lenient where a rule needs judgment. It accepts any nonzero code for a usage error and notes when it is not 2. It does not test `TERM=dumb` or `--no-color`. It cannot check that a result is correct, that `--dry-run` matches the real run, that a destructive command asks first, or how a session program behaves once inside. Check those by running the program, and say which ones were checked.

## 4. Report

Say what the contract is, what the probe reported, what was checked by hand, and what was not checked.
A check that was not run is reported as not run.

## Boundaries

- The shape of a library, module or HTTP API is interface design, not this skill.
- A web page or app screen is `frontend-aesthetics`.
- A server that exposes tools to a model over MCP goes to an MCP server builder skill such as `build-mcp-server`, where one is installed.
- The rules for how a script starts and stops child processes are in `skill-authoring`; this skill covers what the user sees when it does.
