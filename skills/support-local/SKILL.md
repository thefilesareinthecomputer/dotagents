---
name: support-local
description: Hands one information goal to a goal-bound Haiku 5.5 worker that drives the local models (local-model-task, code-kg, obsidian-kg, a guarded vault's ask) over a named corpus and returns one JSON answer with verified evidence references, so the session never pays frontier tokens to read a large body of files. Use whenever a session needs a question answered from a repo, a folder of documents, an index or a vault - "find out from this codebase how X works", "what does the vault say about Y", "survey these notes for Z" - and for the onboarding that harvests, cleans and fine-tunes the local models on the user's own history (Phase 2). Never reads guarded files itself.
---

# support-local

A cheap mid-tier worker does the reading through local models; the session gets back one structured answer and reads its `evidence` and `coverage` before trusting `answer`. The design and phase records live in the source repo's `tasks/` folder, which is held back from the published copy.

## Two ways to run the worker

**In a session:** write the brief, then spawn the `support-local` subagent with it as the prompt. The agent definition (`agents/support-local.md`) pins `claude-haiku-5-5`; the `haiku` alias resolves to Haiku 4.5 in Claude Code 2.1.280, so the full ID is the pin.

```bash
python3 ~/.agents/skills/support-local/scripts/support_local.py brief --goal "<one sentence>" --corpus <path|index|vault:name> \
    [--complete "<what a complete answer holds>"] [--out-of-scope "<text>"] [--budget-turns 30] [--budget-calls 20]
```

**Headless, measured:** the script runs `claude -p` as the worker, asserts the model it ran on, verifies the answer and records tokens and cost under the state directory.

```bash
python3 ~/.agents/skills/support-local/scripts/support_local.py run --goal "..." --corpus <path> [brief options] [--variant default|full|terse] [--effort low|medium|high|max] [--autocompact auto|N] [--timeout 1200] [--retries 1]
python3 ~/.agents/skills/support-local/scripts/support_local.py verify --answer answer.json --corpus <path>   # check an answer by hand
python3 ~/.agents/skills/support-local/scripts/support_local.py doctor
python3 ~/.agents/skills/support-local/scripts/eval_goals.py --variants default,local-first,terse --efforts medium,high   # the goal matrix, graded against evals/goals.jsonl keys; spends tokens
python3 ~/.agents/skills/support-local/scripts/eval_goals.py --report <results.jsonl>                               # re-print a table, no runs
python3 -m unittest discover -s ~/.agents/skills/support-local/tests
```

Brief variants: `default` (also `local-first`) forbids Read until a local search has run and says abstention is a correct result; `full` is the longer original; `terse` is a short brief. The 72-run matrix of 2026-10-09 picked the default: 22/24 correct against 18/24 for the others, cheapest, and the only one that abstained on absent goals. `evals/goals.jsonl` keys were drafted by Sonnet readers and are unreviewed until the user signs them off.

## Reading the answer

The worker returns `{"goal", "answer", "answerable", "evidence": [{"claim", "ref", "verified"}], "coverage", "local_calls", "stop_reason"}`.

- `verify` and `run` re-resolve every `ref` themselves: a `path:line` must exist, a `path` must be a file, and a `vault:<name>#<section>` reference stays unverified because only the vault can confirm it. The worker's own `verified` flag is replaced by the script's.
- A claim with no resolvable reference is kept and marked `?? ` in the capsule. Read those before using the answer; do not drop them, and do not trust them.
- `coverage` says what was searched. An `answerable: false` with a coverage line is a good result; an answer with no evidence is not.
- `stop_reason` is `answered`, `budget` or `no progress`. A `budget` stop with low coverage means the brief was too wide.

## Bounds and recovery

Every layer has a ceiling and a recorded exit; nothing runs unbounded and nothing dies silently.

- **The worker** is bounded by `maxTurns` (30 in the definition, `--budget-turns` headless), a subprocess timeout (`--timeout`, default 1200 s), and its own budget rule: with two turns left it returns what it has with `stop_reason: "budget"`.
- **Each local call** is bounded by `local-model-task`'s timeout, lock and memory checks, and reports failure by exit code. The briefs state the protocol: exit 3 or a denied tool call means stop with `stop_reason: "blocked"`; exit 4 or 5 means one narrower retry then move on; exit 6 means one plain retry then move on; no failing call runs more than twice, and nothing calls Ollama directly.
- **A dead worker** is a recorded outcome. In a headless run, a timeout, crash or prose-only ending is salvaged into `answerable: false` with the reason and the worker's last text in `coverage`, then retried once (`--retries`, default 1) with half the turns and the prior coverage in the brief. Every attempt's tokens and cost are summed in `runs.jsonl` under `attempt_log`. `run` exits 4 only when every attempt died; the record still exists.
- **In a session,** a subagent return that is not the JSON object is a failed run: re-delegate once with its text as the prior attempt and half the budget, and never accept prose as an answer.
- **A `blocked` stop** is a first-class result. Under memory pressure the station's gate answers "ask", which a headless worker cannot answer; the worker reports `blocked` with the call named rather than retrying or guessing.

## Rails

- The worker's tools are Bash, Read, Grep and Glob; the station's permission rules, sandbox and deny rules apply to it exactly as to the session. On a vault root it has no read access by construction, and the vault's Phase 3 probe is the proof.
- It never calls Ollama directly: every local call goes through `local-model-task` or an index tool, so the shared memory budget applies.
- A headless run that reports any model other than `claude-haiku-5-5` is refused before its answer is read (exit 3).
- `~/.local/state/support-local/runs.jsonl` (0600) holds per-run tokens, cost and counts, never answers or file content.
- Onboarding (harvest, clean, train) is Phase 2 and is not built. Nothing trains without a selection the user wrote and a clean report.
