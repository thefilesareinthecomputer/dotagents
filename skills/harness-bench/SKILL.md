---
name: harness-bench
description: >-
  Benchmarks open-source agent harnesses (goose and pi so far; more as adapters land) on a
  fixed eleven-task coding battery, each run headless inside a per-run macOS sandbox against one
  Ollama cloud tag reached only through a loopback recording proxy that pins thinking and
  temperature, then graded by hidden tests on a clean copy the agent never touched. Use
  when asked to compare, benchmark or evaluate agent harnesses, to run a harness over the
  battery, or to table the results. Explicitly invoked; every live run spends on a hosted
  model.
license: MIT
disable-model-invocation: true
---

# harness-bench

Runs one harness on one battery task per run and records what it did. The script builds the
sandbox boundary, runs the proxy, harvests the workspace and grades it; you choose the
harness, model, tasks and reps, then read the table. Execute the scripts; do not read them
to use the skill.

## Before a live run

- Ask the user before every batch: each run is a hosted-model call billed by token.
  The battery's files and every prompt go to a third-party hosted model, so the bench
  runs only on its own fixture, never on private code.
- The harness must be installed and on `PATH` (`goose --version`). The Ollama daemon must
  answer on `127.0.0.1:11434` and the tag must be registered (`ollama list`).
- Run one batch at a time. Runs are serial by design; two batches at once share the
  daemon and skew wall clock.
- Keep the lid open. `caffeinate` stops idle sleep but not lid-close sleep, and a batch
  that runs through sleep records stalls and timeouts that are not the harness's.

## Commands

```
python3 ~/.agents/skills/harness-bench/scripts/harness_bench.py tasks
python3 ~/.agents/skills/harness-bench/scripts/harness_bench.py run --harness goose \
    --model glm-5.3-flash:cloud --task <id|all> [--reps 3] (--think low | --native) \
    [--temperature 0] [--timeout 900]
python3 ~/.agents/skills/harness-bench/scripts/harness_bench.py table [--harness H] [--model M]
python3 ~/.agents/skills/harness-bench/scripts/harness_bench.py clean [--run DIR | --older-than-days 14]
python3 ~/.agents/skills/harness-bench/scripts/harness_bench.py versions [--quiet]
```

- `--think <level>` is a pinned run: the proxy rewrites thinking to that level and
  temperature to `--temperature` (default 0) on every task call, and logs what the
  harness sent. Use a level the tag lists (`low`, `high`, `max` on GLM). Do not use an
  "off" value, which on GLM moves the reasoning into the answer instead of stopping it.
- `--native` passes the harness's own settings through and only records them.
- Give the Bash call a timeout above `--timeout` times the number of runs, or run it in
  the background.
- `versions` compares each installed harness with its latest published release
  (Homebrew, npm's `latest` tag, PyPI) and never follows alpha or beta tracks. With
  `--quiet` it prints one line only when something is newer; a station can run it that
  way from a once-a-day session-start hook. Upgrading is the user's call: before trusting
  a new version, re-check what network calls it makes (a static read of its code for
  telemetry, update checks and other outbound calls), and the bench records each run's
  harness version.

Exit codes: `0` every run was graded (pass or fail is in each `run.json`); `2` bad
arguments; `3` the harness is not installed; `4` at least one run could not be graded
(no output, or the harness never reached the model).

## What a run does

1. Builds the task's starting tree from `battery/fixture` plus the task's overlay, and
   copies it to `ws/`, the only folder the agent may write (none for answer tasks).
2. Starts the proxy on a loopback port. The proxy forwards chat and listing endpoints to
   the daemon, refuses any other tag and every management endpoint, and logs every
   request with its tokens, tool calls, malformed calls and a system-prompt hash.
3. Runs the harness under `sandbox-exec` with an environment cut to a named list, a fake
   `HOME`, and its own state root in the run folder. The profile denies reads under every
   home folder, mounted volumes and the temp trees except the run's own folder, writes
   outside the run, every network connection except the proxy's port, and the macOS
   channels that would start something outside the sandbox (`open`, Apple Events) or
   read the clipboard. The harness cannot reach the daemon directly or the internet.
4. Kills the harness's whole process group, compares `ws/` with the starting tree,
   copies only allowed regular files into a clean copy, adds the hidden tests and runs
   them in their own no-network sandbox. Answer tasks are graded against a key.
5. Attempts a sentinel write under the run's profile (a run whose sentinel is not denied
   is reported as a broken profile), and after the batch reads the kernel's denials for
   each run from the unified log by the run's tag. The log arrives seconds late, so the
   batch ends with a short settle.

## Reading the results

`table` prints one row per harness, version, model, mode, thinking level and task:
pass count, median wall-clock time, mean tokens, summed list cost, tool calls, malformed tool
calls, out-of-scope edits, scope-trap attempts, and read and network denials. A run's
folder holds `run.json`, the proxy log, the harness's stdout, `final.txt` and the
grading output.

- **Out of scope** edits are reported and never graded. **Trap** counts an attempt on
  the scope-trap task's forbidden file even when the agent reverted it.
- **Read denials** in the home folder mean the agent tried to read outside the project.
  Denial counts are a lower bound: macOS drops some sandbox reports, so zero does not
  prove nothing was attempted. The boundary itself is enforced either way.
- **Cost** uses the input rate for every prompt token (`references/rates.json`), so it
  is an upper bound when the provider caches.
- A harness's own report (turns, tool failures, its token counts) sits beside the proxy's
  counts in `run.json`; the proxy's counts are the ones to compare across harnesses.

## Limits

- macOS only (`sandbox-exec`, the unified log).
- The proxy sees the model, not the harness's tools, so tool failures come from each
  harness's own report.
- Results expire with harness versions; every run records its version.

## Verification

`python3 -m unittest discover -s ~/.agents/skills/harness-bench/tests` runs the proxy
against a fake daemon, the battery against its reference solutions, and the runner end
to end with a fake harness under the real sandbox. The tests call no model and use no
network beyond loopback.
