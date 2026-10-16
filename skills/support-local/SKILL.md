---
name: support-local
description: Hands one information goal to a goal-bound Haiku 5.5 worker that drives the local models (local-model-task, code-kg, obsidian-kg, a guarded vault's ask) over a named corpus and returns one JSON answer with verified evidence references, so the session never pays frontier tokens to read a large body of files. Use whenever a session needs a question answered from a repo, a folder of documents, an index or a vault - "find out from this codebase how X works", "what does the vault say about Y", "survey these notes for Z" - and, once Phase 2 is built, for the onboarding that harvests, cleans and fine-tunes the local models on the user's own history. A single summarize, extract or grep call on the local model is local-model-task. Never reads guarded files itself.
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

Brief variants: `default` (also `local-first`) forbids Read until a local search has run and says abstention is a correct result; `full` is the longer original; `terse` is a short brief. The 72-run matrix of 2026-10-09 picked the default: 22/24 correct against 18/24 for the others, cheapest, and the only one that abstained on absent goals. With the quote check and the 2026-10-15 changes in place, three repeats of the twelve goals scored 33 of 36, with abstention 9 of 9, at about $0.09 list price and 17 minutes for all twelve goals. The misses all came from one station guard denying a search pattern that spelled an env-file name, and the worker's rules now handle that case. `evals/goals.jsonl` keys were drafted by Sonnet readers and are unreviewed until the user signs them off. Goals over the user's own repos sit in the gitignored `evals/goals.local.jsonl` beside it, read when present.

## Reading the answer

The worker returns `{"goal", "answer", "answerable", "evidence": [{"claim", "ref", "quote", "verified"}], "coverage", "local_calls", "stop_reason"}`.

- `verify` and `run` check every claim themselves. The `ref` must resolve inside the corpus (a `path:line` or `path`), and the `quote`, at least eight characters long, must sit at that line, or in that file for a file-level claim, ignoring whitespace. A reference to a line that exists is not evidence by itself. A `vault:<name>#<section>` reference stays unverified because only the vault can confirm it. The worker's own `verified` flag is replaced by the script's, and an `answerable: true` with no verified claim is downgraded to `false` with `downgraded` saying so.
- An index or vault corpus has no path, so pass `--corpus-root <dir>` to `run` or `verify` to say where its files are; without it, no file reference verifies.
- A claim with no resolvable reference is kept and marked `?? ` in the capsule. Read those before using the answer; do not drop them, and do not trust them.
- `coverage` says what was searched. An `answerable: false` with a coverage line is a good result; an answer with no evidence is not.
- `stop_reason` is `answered`, `budget`, `no progress` or `blocked`. A `budget` stop with low coverage means the brief was too wide.

## Bounds and recovery

Every layer has a ceiling and a recorded exit, so nothing runs unbounded and no failure goes unrecorded.

- **The worker** is bounded by `maxTurns` (30 in the definition, `--budget-turns` headless), a subprocess timeout (`--timeout`, default 1200 s), and its own budget rule: with two turns left it returns what it has with `stop_reason: "budget"`.
- **Each local call** is bounded by `local-model-task`'s timeout, lock and memory checks, and reports failure by exit code. The agent definition states the protocol. Exit 3 or a denied tool call means stop with `stop_reason: "blocked"`. Exit 4, 5 or 130 (the Bash tool killed the call at its own ceiling, near 137 s) means one narrower retry, then move on, and exit 6 means one plain retry, then move on. No failing call runs more than twice, and nothing calls Ollama directly. A search sends the model at most 120 matches by default, which keeps a call to tens of seconds; the 400-match lists of the first matrix ran two minutes, at the Bash ceiling, and came back "absent".
- **A dead worker** is a recorded outcome. In a headless run, a timeout, crash, prose-only or non-object ending is salvaged into `answerable: false` with the reason and the worker's last text in `coverage`, then retried once (`--retries`, default 1) with half the turns and the prior coverage in the brief. A parsed `answerable: false` is a verdict and is never retried, whatever stopped the worker. Every attempt's tokens and cost are summed in `runs.jsonl` under `attempt_log`. `run` exits 4 only when every attempt died; the record still exists.
- **In a session,** a subagent return that is not the JSON object is a failed run: re-delegate once with its text as the prior attempt and half the budget, and never accept prose as an answer.
- **The memory gate** is checked by the headless runner before it spends anything. At critical the runner refuses with exit 3 and starts no worker; at warn it runs the worker and says so in the brief. The worker is seated (`AGENTS_APP_SEAT=support-local`), so at warn the gate denies a load-adding call outright with the `brain-gate: memory-pressure` prefix instead of raising an "ask" nobody can answer. The worker's fallback rule then continues with Grep, Glob and Read and names the gate in `coverage`. A Bash call held only because its text mentions an env-file name is rewritten once in words; a file tool reaching for an env file, every other deny, and exit 3 still mean `blocked`. On 2026-10-15 the ungated version lost 7 of 12 goals to that ask; the five that answered did so with Grep alone.
- **The worker's directory** in a headless run is an empty directory of its own under the state dir, so no project rules file or session memory index reaches it (one worker refused to search because it had read a rule from the orchestrating session's memory); the station's user-level hooks still apply. The corpus is written into the brief as an absolute path.

## Rails

- The worker's tools are Bash, Read, Grep and Glob; the station's permission rules, sandbox and deny rules apply to it exactly as to the session. On a vault root it has no read access by construction, and the vault's Phase 3 probe is the proof.
- It never calls Ollama directly: every local call goes through `local-model-task` or an index tool, so the shared memory budget applies.
- A headless run that reports any model other than `claude-haiku-5-5` is refused before its answer is read (exit 3).
- `~/.local/state/support-local/runs.jsonl` (0600) holds per-run tokens, cost and counts, never answers or file content.
- Onboarding (harvest, clean, train) is Phase 2 and is not built. Nothing trains without a selection the user wrote and a clean report.
