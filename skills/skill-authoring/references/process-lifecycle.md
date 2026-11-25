# Process and resource lifecycle standard

This standard applies to anything in this repo that starts a process or holds a machine resource beyond its own call:

- agent CLIs (`claude -p`, codex, cursor, agy, gemini);
- model runners and model loads (Ollama and other local backends);
- shells and terminals, servers, proxies and daemons;
- background agent commands;
- hooks that detach a child.

Every such resource has an owner and a bounded life, and it ends with its owner on every exit path.

## Requirements

1. **Spawn through `procguard`.**
   - Agent CLIs, model runners, shells, servers and any child that can run for more than a few seconds start through `procguard.run`, `procguard.popen`, or `procguard.wrap` with `procguard.stop` for async callers.
   - The canonical file is `skills/skill-authoring/scripts/procguard.py`. A skill that spawns keeps a byte-identical copy in its own `scripts/`. `tests/test_procguard_copies.py` fails on any drift, and its `--sync` mode copies a canonical fix out to every copy.
   - A plain `subprocess.run` is allowed only for a short utility (`git`, `ps`, `sysctl`, a version probe) and always sets `timeout=`.
   - `skills/skill-authoring/scripts/check_spawns.py` enforces both rules.
2. **Every child has a wall-clock cap.**
   - "Until it finishes" is not a cap.
   - The default for an agent turn is the caller's own budget. Two hours is the ceiling, the same as Claude Code's own maximum for unattended background commands.
3. **Stopping is TERM, then grace, then KILL, to the whole process group.**
   - `claude -p` kills its own command trees and runs its SessionEnd hooks on SIGTERM. A bare SIGKILL, which is what `subprocess.run(timeout=)` sends to the direct child only, skips both.
4. **Every exit path stops what the process owns.**
   - The exit paths are: normal return, exception, Ctrl-C, SIGTERM, SIGHUP, and the owner being SIGKILLed.
   - A CLI that spawns calls `procguard.install_signal_handlers()` once in `main`.
   - Thread pools call `procguard.stop_all()` before leaving the executor on any exception, so shutdown never waits on a hung child.
   - The watchdog covers the SIGKILL case by stopping its group when its parent goes away.
5. **Agent children run without background work.**
   - A `claude -p` child gets `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` unless background work is its purpose.
   - Without it, a command that reaches its timeout moves to the background instead of stopping.
6. **Models are released.**
   - A tool that loads a local model unloads it (`keep_alive: 0`) in a `finally`, or sets a per-call `keep_alive` no longer than 10 minutes.
   - It checks memory pressure before loading and loads only the models the user named.
7. **Anything left running on purpose is registered.**
   - A daemon, server or proxy writes a pid file, has a stop command, and detects its own stale pid file.
   - Its stop command signals the whole group even when the leader has already died.
8. **Agent sessions run background commands under the watchdog.**
   - A `run_in_background` Bash command runs as `python3 ~/.claude/hooks/procguard.py --timeout <s> -- <command>`. The `background_guard` hook refuses any other form.
   - A local Claude Code session puts no time limit of its own on background commands.
9. **Safety.**
   - Signal only process groups you created. Never kill by name or pattern outside a test's own uniquely tokened processes.
   - The `reaper` hook only reports orphans. Stopping one is the user's call.
10. **Tests replay the exits.**
    - A spawner's tests use fake CLIs and real processes. They cover a timeout, the parent SIGKILLed, SIGTERM and SIGHUP, and assert that no tokened descendant survives.
    - Tests never start a real agent CLI or load a real model.
    - Test files may use `Popen` and omit timeouts: a hung test blocks the suite in the foreground, where it is seen, and an agent's background run of a suite is already under the watchdog.

## Checks

| Check | Where | When |
|---|---|---|
| `check_spawns.py` | `tests/test_spawn_lint.py`, skill-authoring audits, wrap-up | every suite run, every new skill, every closeout |
| `test_procguard_copies.py` | repo `tests/` | every suite run |
| `background_guard` hook | PreToolUse on shell commands | every background command |
| `reaper` hook | SessionStart and prompts; `reaper.py --report` in wrap-up | every session start, every 30 minutes of prompts, and closeout |
| resource step | wrap-up, beside the security review | every closeout |

## Known limit

A child that calls `setsid()` or daemonizes itself leaves the guarded group, so no group signal reaches it.
The reaper reports such escapees by their CPU time and their missing owner.
Browsers that Playwright or Puppeteer launch run detached in their own process group, so a group stop on the MCP server or test runner does not reach them; the reaper reports an orphaned one by its launch flags, with the group to stop.
