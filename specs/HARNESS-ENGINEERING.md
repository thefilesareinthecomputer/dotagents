# Harness engineering

This file is the hub for every agent harness in this folder.
It is the source of truth for three things:
- what a harness is;
- which components every harness needs;
- which patterns the major harnesses share.

Each harness's own spec describes its install and its architecture, and links back here.
The research behind each rule is in the ai-engineering corpus, [`agent-stack-map.md`](../skills/ai-engineering/resources/agent-stack-map.md):
- B.6 compares the core loops of 14 harnesses, read from source at pinned commits where the code is open (2026-11-25);
- B.5 covers local runtimes and caching;
- B.1 covers ACP;
- B.2 covers per-harness mechanics.

## What a harness is

A harness is the program around a model.
It sends the model a request, runs the tools the model asks for, and repeats.
Everything else exists to keep that loop correct, affordable and safe over a long session.
- Context assembly
- Permissions
- Session state
- Compaction
- Measurement

## Core components

Every working harness has these components, and each one serves the loop.
The "standard" column is what most of the harnesses in B.6 do.

| Component | Job | Standard |
|---|---|---|
| Loop | Call the model, run its tool calls, append the results, repeat | A reply with no tool calls ends the turn |
| Context builder | Assemble each request from a stable prefix plus the history | History stored exactly as sent; volatile context appended as messages |
| Tool registry | Tool schemas and their implementations | Parallel execution by default; schema errors returned to the model as tool errors |
| Permission gate | Decide which calls run, ask or are refused | Modes plus per-tool rules and hooks; an OS sandbox in the stricter harnesses |
| Output limits | Keep one tool result from flooding the context | Head and tail kept, middle cut with a marker; very large output spilled to a file |
| Compaction | Shrink the history before the window fills | Trigger at window minus a reserve; keep about 15-20k recent tokens; summary with fixed sections |
| Session store | An append-only record for resume and replay | JSONL or SQLite; most support forks |
| Rules files | Load standing instructions | `AGENTS.md`, read from the repo root down to the working directory |
| Event stream | One interface every front end consumes | Text, thinking, tool status, usage and stop events; protocol adapters such as ACP on top |
| Metrics | Per-call tokens, timings and cache reuse | Taken from the runtime's own counts |

Memory and subagents are optional components.
Most coding harnesses have subagents.
Memory across sessions is mostly delegated to rules files.

## The loop

1. Append the user message.
2. Build the request: the prefix plus the history.
3. Stream the reply.
4. Run the tool calls and append each result, then go back to step 2.
5. Stop when a reply has no tool calls, or when a limit is reached.

**Limits.** Most harnesses set no turn limit by default. A local or unattended harness should set them anyway.
- A cap on tool rounds per turn.
- A wall-clock cap that does not count the wait for the first token. A cold prefill can take minutes.
- Loop detection that warns before it stops. For example, Cline warns at 3 identical calls and stops at 5.
- At the cap, run one last step with tools disabled and a wrap-up prompt, but keep the tool definitions in the request so the prefix still caches.

**Failure handling.**
- Return a malformed tool call to the model as a tool error, never raise it as an exception.
- Turn any exception a tool raises into a tool result.
- Retry provider errors with exponential backoff and jitter.
- Treat a context overflow as a signal to compact, not to retry.
- A stream without its final chunk, or with a streamed error object, is a failure. Never commit a partial reply or a partial summary.
- Cancelling a turn ends it and leaves the session valid.

## Harness index

| Harness | Station spec | Implementation | Architecture source |
|---|---|---|---|
| Claude Code | [`claude-code/`](claude-code/SPEC-CLAUDE-CODE.md#architecture) | closed | official docs |
| Codex CLI | [`codex/`](codex/SPEC-CODEX.md#architecture) | [openai/codex](https://github.com/openai/codex) | source, `06f334aa` |
| Copilot CLI | [`copilot/`](copilot/SPEC-COPILOT.md#architecture) | closed | official docs |
| Cursor | [`cursor/`](cursor/SPEC-CURSOR.md#architecture) | closed | official docs |
| Antigravity CLI | [`antigravity/`](antigravity/SPEC-ANTIGRAVITY.md#architecture) | closed | official docs |
| Gemini CLI | [`gemini/`](gemini/SPEC-GEMINI.md#architecture) | [google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli) | not yet researched |
| goose | [`goose/`](goose/SPEC-GOOSE.md#architecture) | [aaif-goose/goose](https://github.com/aaif-goose/goose) | source, `8256b9ac` |
| opencode | [`opencode/`](opencode/SPEC-OPENCODE.md#architecture) | [anomalyco/opencode](https://github.com/anomalyco/opencode) | source, `b6973f1b` |
| Pi | [`pi/`](pi/SPEC-PI.md#architecture) | [earendil-works/pi](https://github.com/earendil-works/pi) | source, `b882d08f` |
| Kimi CLI | [`kimi/`](kimi/SPEC-KIMI.md#architecture) | [MoonshotAI/kimi-cli](https://github.com/MoonshotAI/kimi-cli) (archived 2026-09-22) | web research only |
| deepagents | [`deepagents/`](deepagents/SPEC-DEEPAGENTS.md#architecture) | [langchain-ai/deepagents](https://github.com/langchain-ai/deepagents) | not yet researched |

These harnesses are read for reference and not installed. B.6 covers them:
- DeepSeek Harness, source at `4b399c39`;
- Cline, source at `34c104e6`;
- the OpenHands SDK, source at `ce9206ef`;
- Hermes Agent, source at `22facbc2`.

A self-built harness gets its own folder and a row here once it installs and runs on a station.
Until then, its design lives in its own repo.

### The architecture section

Every harness spec carries an `## Architecture` section that answers the same ten questions, so harnesses compare line by line.
Each answer is marked **source** (read at a pinned commit), **docs**, **observed** or **unknown**.

1. **Loop:** what ends a turn; turn, step and time limits; loop detection.
2. **Tools:** parallel or sequential; fixed or dynamic tool list.
3. **Permissions:** approval modes, rules, hooks, sandbox.
4. **Context:** tool-output limits, handling of old results, compaction trigger, summary format, what survives.
5. **Cache:** how the prefix stays stable; cache markers; whether history is stored as sent.
6. **Sessions:** storage format, resume, fork.
7. **Errors:** retries and backoff; overflow handling.
8. **Rules files:** names, discovery order, size caps.
9. **Front ends:** event stream, print or headless mode, ACP or another protocol.
10. **Subagents:** isolation, depth and concurrency limits.

## Breakouts

### Context engineering

A runtime can reuse its cached computation only for a prefix that is byte-identical to the previous call's.

- **Keep the prefix stable.** The system prompt, rules and tool schemas don't change within a session.
- **Append only.** Dynamic content arrives as new messages. goose stores time, working directory and turn budget as an agent-only message.
- **Serialize each message once.** Re-rendering an early message forced a full re-prefill on llama.cpp (oh-my-pi issue 3406). Hermes makes its send-time rewrites on a clone. goose has a test that bytes already sent never change.
- **Make tool-call IDs deterministic** when the runtime omits them (Hermes), so the history bytes stay stable.
- **Retrieve just in time.** Load memory and documents through tool calls, not on every step (Anthropic, 2025-09-29).
- **Cap tool output.** Keep the head and tail with a marker that says how to read the rest. Spill very large output to a file and return a pointer and a preview (goose, Hermes, Pi's `bash`).
- **Stub old results sparingly.** Replacing old tool output saves context but breaks the cache from that point on. Hermes gates it on a minimum amount reclaimed.
- **Keep always-loaded files short.** Repository context files raised cost by over 20% with no significant gain in task success in one study (corpus M.5).

### Compaction

- **Trigger at window minus a reserve.** The reserve covers the reply, one tool result and the summary call. Examples:
  - Pi: window - 16k;
  - opencode: window - max(15%, 16k);
  - DeepSeek: min(0.8 x window, window - reserve - 64k).
- **Keep about 15-20k recent tokens verbatim** (Pi, Cline, opencode, Codex). Keeping more makes the next call re-prefill everything that was kept.
- **Summarize on the cached prefix.** Send the summary request as the next message of the live conversation, so it reuses the cache (DeepSeek, goose, opencode).
- **Use fixed sections.** For example: goal, decisions, facts learned, open items, files touched. Keep the full history on disk.
- **Have a fallback:**
  - Hermes writes a deterministic summary without an LLM;
  - opencode shrinks the kept part in steps;
  - goose drops tool output progressively.
- **Keep rules out of summaries.** Keep rules in the prefix, or reload them after compaction as Claude Code does with CLAUDE.md. One measured compaction kept 53% of safety rules after one round and 10% after five ("Compaction Cliff", arXiv 2608.22752).

### Caching and local performance

- **Cache hit rate is the headline metric** (Manus). Count tokens with the runtime's own numbers.
- **Hosted APIs:**
  - Anthropic-style requests carry at most 4 cache markers: the system prompt, the tools and the conversation tail.
  - Codex and OpenHands send a session-scoped prompt cache key.
- **Ollama (MLX runner, measured 2026-11-24):**
  - `prompt_eval_cached_count` reports reuse.
  - The cache restores in 1,024-token blocks.
  - The cache lives in memory only, so an unload loses it.
  - A one-shot cold prefill of about 100k tokens or more panics the runner. Re-warm in steps of 32k or less.
- **Other local runtimes:**
  - The llama.cpp server can save a slot to disk. One measurement restored a 5k-token chat about 7x faster than re-prefilling it.
  - The mlx-lm server keeps an in-memory prefix cache.
- **Size the window by per-round latency, not the model's maximum.** Prefill of new tokens slows with depth: 686 tok/s at 31k and 190 tok/s at 218k on one local model. The details are in B.5.

### Permissions and sandboxing

- **Choose a sandbox model up front.**
  - Codex and DeepSeek Harness confine the shell at the OS level (sandbox-exec on macOS, landlock or bubblewrap on Linux). DeepSeek refuses to run unconfined.
  - Harnesses with approvals only (opencode, goose, Cline, Pi) depend on the gate being complete.
- **A command-name allowlist is not a boundary.**
  - `rg --pre=COMMAND` runs a program, `git diff --output=<file>` writes anywhere, and `git -c` sets config.
  - The shell expands `$x` and globs after the gate has inspected the words.
  - Run allowlisted commands without a shell, or sandbox them.
- **Confine writes** to workspace roots.
- **Own every process.** Run each command in its own process group with a timeout and an output cap, and kill the group on timeout or cancel ([process lifecycle](../skills/skill-authoring/references/process-lifecycle.md)).
- **Treat retrieved content as data.** Wrap memory, documents and web content in a labeled block. Hermes also scans rules files for prompt injection.
- **Keep telemetry off.**

### Sessions

- **Use an append-only log.**
  - JSONL: Claude Code, Codex, Pi, DeepSeek.
  - SQLite: opencode, goose, Hermes, Cline.
- **Forking copies a prefix and closes any open turn** with an interrupted or forked marker (Codex, DeepSeek, Pi, opencode, OpenHands).
- **Recover a torn final line** instead of failing the whole session.
- **Answer a tool call that has no result** with "interrupted, outcome unknown".

### Rules files

- **`AGENTS.md` is the shared filename.** Read it from the repo root down to the working directory, nearest file last.
- **Override files:** Codex, Pi and Hermes check `AGENTS.override.md` first in each directory.
- **Cap the size:**
  - Codex shares one byte budget across all files;
  - Hermes caps each file at 20k characters;
  - goose caps imports at depth 3 and 1 MiB.
- **Harness-specific names coexist with it:** `CLAUDE.md`, `.goosehints`, `.clinerules`, `GEMINI.md`. Claude Code reads `AGENTS.md` only when no `CLAUDE.md` exists.

### Front ends and ACP

- **Emit one event stream** of text chunks, thinking chunks, tool calls with status, usage and the stop reason. The terminal UI is just one consumer of it.
- **ACP** lets one client drive any agent that speaks it (corpus B.1). goose, Hermes, OpenHands, Cline and DeepSeek Harness speak it. Which standard this station uses for each link is in [`AGENT-PROTOCOLS.md`](AGENT-PROTOCOLS.md).
- **Route approvals through one function** that the front end supplies, so an adapter can forward them to ACP permission requests.

### Subagents

- **Give each child a fresh context, its own turn budget, and a depth and concurrency cap.** Defaults:
  - opencode: depth 1;
  - Claude Code: depth 3;
  - goose: 5 concurrent;
  - Hermes: 10 children.
- **A forked child may inherit the parent's history,** but never its authority (DeepSeek).

### Evaluation

- **A runtime bench comes first:** load time, prefill and decode speed at several context sizes, and prefix reuse.
- **A prefix test:** the system message and tool schemas are identical across every call in a session, including after compaction.
- **A rules test:** every rule is still in context after several compactions.
- **A long-session bench** at production window size, reporting the cache hit rate and whether an early fact survives compaction.
- **A task eval** scored on the final state (file contents, exact facts), not on whether the schema was valid.

## Learning resources

- [learn-harness-engineering](https://github.com/walkinglabs/learn-harness-engineering) (MIT): 14 lectures and 8 projects.
- [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) (Anthropic, 2025-09-29).
- [Context engineering lessons from building Manus](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus) (Manus).
- Source worth reading:
  - Pi, for a minimal loop and tree-shaped JSONL sessions;
  - DeepSeek Harness, for a plugin-per-concern design with a fail-closed sandbox;
  - Hermes Agent, for file memory and defensive compaction;
  - goose, for cache-invariance tests.
