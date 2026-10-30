---
name: agent-stack-map
description: Opinionated, comparison-table map of the modern OSS agent stack - frameworks, harnesses, memory, retrieval/context, skills, ingestion, tuning/RL, self-improvement, the NVIDIA NeMo stack, and media production (local speech and podcast pipelines) - with recommended architectures and a current shortlist. The analytical core of the ai-engineering skill.
updated: 2026-10-19
---

# Agent Stack Software Map

The opinionated catalog behind the `ai-engineering` skill. Use its taxonomy when
answering "what are my choices for X" - survey the layer, then recommend.

> **Currency caveat.** Star counts and license fields are point-in-time from
> prior research passes (≤ 2026-06) unless a row carries its own later date.
> Treat undated figures as directional, not live. A refresh pass re-verifies
> stars, licenses, GA and maintenance status, and surfaces new entrants. Every
> "verify" cell is an explicit open item - do not invent a value to fill it.

## How to read the stack

The strongest OSS systems today are **composed, not monolithic**. A serious
stack is usually one of each:

1. **Framework / orchestration** - the agent loop, tools, state.
2. **Memory / personalization** - persistence, recall, entity/temporal memory.
3. **Knowledge / retrieval / context** - the durable data layer agents reason over.
4. **Tooling / skills / MCP** - capabilities the agent can call.
5. **Ingestion / parsing** - getting web + documents into the stack.
6. **Model serving / routing** - local-first, cloud escalation.
7. **Training / RL / adaptation** - only with an explicit post-training roadmap.
8. **Frontend / copilot UX** - if there's a user-facing app.

Most "agent frameworks" are really orchestration layers and depend on separate
memory, retrieval, and tool stacks. Choose per layer, not one box to rule them all.

---

## Section A - Complete agent frameworks

Orchestration + tools + prompts/workflows + usually some memory/persistence/knowledge.

| Project | License | Stack role | What it does | Cautions | Status | Repo |
|---|---|---|---|---|---|---|
| LangChain | MIT | General agent framework | LLM apps/agents with the largest integration ecosystem. | Abstract/heavy; long-term memory needs extra design. | Include | [repo](https://github.com/langchain-ai/langchain) |
| LangGraph | MIT | Stateful orchestration runtime | Durable, explicit-state graphs for long-running agents; HITL. | Lower-level; more upfront architecture. | Include | [repo](https://github.com/langchain-ai/langgraph) |
| LlamaIndex | MIT | Data + agent framework | Agents over documents, indices, graphs, retrieval. | Broad surface; many packages. | Include | [repo](https://github.com/run-llama/llama_index) |
| CrewAI | MIT | Multi-agent framework | Role/task/flow multi-agent orchestration. | Some enterprise features skew commercial. | Include | [repo](https://github.com/crewAIInc/crewAI) |
| Agno | Apache-2.0 | Agent framework + runtime | Agents/teams/workflows/memory/knowledge + AgentOS. | Some value sits in hosted control plane. | Include | [docs](https://docs.agno.com/introduction) |
| Semantic Kernel | MIT | Enterprise orchestration SDK | Model-agnostic agents/plugins/memory/process; multi-language. | Heavier enterprise framing. | Include | [repo](https://github.com/microsoft/semantic-kernel) |
| Haystack | Apache-2.0 | Retrieval + orchestration | Production RAG / retrieval / agent pipelines. | Retrieval-first; some setups verbose. | Include | [repo](https://github.com/deepset-ai/haystack) |
| OpenAI Agents SDK | MIT | Multi-agent workflow SDK | Tools, sessions, tracing, handoffs, HITL; provider-agnostic. | Less opinionated on long-term memory. | Include | [repo](https://github.com/openai/openai-agents-python) |
| PydanticAI | MIT | Type-safe agent framework | Strongly typed agentic apps; strong provider support incl. Ollama. | Not batteries-included on memory. | Include | [repo](https://github.com/pydantic/pydantic-ai) |
| smolagents | Apache-2.0 | Minimal agent framework | "Agents that think in code"; model/tool agnostic. | Assemble persistence/memory yourself. | Include | [repo](https://github.com/huggingface/smolagents) |
| Strands Agents | Apache-2.0 | Model-driven SDK | Clean provider model; built-in MCP; local/cloud switching. | Smaller ecosystem. | Include | [repo](https://github.com/strands-agents/harness-sdk) |
| Letta | Apache-2.0 | Stateful agent platform | Memory-first, self-improving agents; memory blocks. | Opinionated architecture. | Include | [repo](https://github.com/letta-ai/letta) |
| Google ADK | Apache-2.0 | Complete framework / SDK | Code-first build/eval/deploy; model-agnostic, Google-optimized; local via Ollama. | Younger ecosystem; strongest in Google's stack. | Include | [repo](https://github.com/google/adk-python) |
| Microsoft Agent Framework | verify | Orchestration SDK | Build/orchestrate/deploy agents + multi-agent across Python/.NET. | APIs still maturing; SK successor-layer. | Include | [repo](https://github.com/microsoft/agent-framework) |
| AnythingLLM | MIT | End-user agent + RAG app | All-in-one private AI app: agents, docs, tools, vector DB, local/cloud. | Less of a low-level SDK. | Include | [repo](https://github.com/mintplex-labs/anything-llm) |
| AutoGen | MIT | Multi-agent research framework | Influential MS multi-agent framework. | **Maintenance mode**; prefer Agent Framework for new builds. | Flagged | [repo](https://github.com/microsoft/autogen) |
| NeMo Agent Toolkit | Apache-2.0 | **Interop + profiling layer, not a framework** | Wraps an existing framework's agents/tools as composable functions; adds YAML workflows, an eval harness, a token/latency/bottleneck profiler and MCP in both directions. v1.8 (2026-06-16), verified 2026-07-28. | Renamed twice in three minors (`agentiq`→`aiqtoolkit`→`nvidia-nat`) with the shims now deleted; breaking changes ship in minor releases. See Section J. | Include (alongside, not instead of) | [repo](https://github.com/NVIDIA/NeMo-Agent-Toolkit) |
| OpenClaw | MIT | Personal assistant platform | Self-hosted assistant controllable from chat apps. | Rapidly changing; provider-policy sensitive. | Caution | [repo](https://github.com/openclaw/openclaw) |

### Platform-style builders (app/workflow over library)

| Project | License | Stack role | What it does | Cautions | Repo |
|---|---|---|---|---|---|
| Dify | Dify OSS License (Apache-based + conditions) | Platform / workflow builder | Production agentic workflows: RAG, tools, plugins, observability. | Source-available-with-conditions, not plain Apache. | [repo](https://github.com/langgenius/dify) |
| Mastra | Dual (Apache-2.0 core + `ee/`) | TS agent/app framework | TypeScript agents/workflows/memory for product teams. | Some enterprise features source-available. | [repo](https://github.com/mastra-ai/mastra) |
| FastGPT | Apache-based + conditions | KB + RAG + workflow platform | Knowledge platform: data processing, RAG, APIs, visual workflows. | Conditions for commercial/SaaS use. | [repo](https://github.com/labring/FastGPT) |
| CAMEL | verify | Multi-agent framework | Agent societies, simulated environments, research-heavy. | Less turnkey for product teams. | [repo](https://github.com/camel-ai/camel) |

---

## Section B - Agent harnesses (agents you operate)

A **harness is a ready-to-run agent you operate** - model + tools + loop already
wrapped into a usable app (terminal / IDE / chat). This is a different layer from an
**SDK/API** (Section A), which is a library you *write code against* to build your own
agent. The test: **a harness is an agent you run; an SDK is a library you build an
agent with.** So OpenAI Agents SDK, Claude Agent SDK, Google ADK, LangGraph,
PydanticAI, smolagents, and Strands are **NOT** harnesses - they live in Section A.

> **Currency - the 2026 terminal-agent shakeout (verified 2026-07-01):** the "big
> three" platform terminal agents are **Claude Code**, **OpenAI Codex CLI**, and
> **Google Gemini CLI**; the leading OSS provider-agnostic default is **OpenCode**,
> with **Pi** the notable new minimal/hackable harness. Movements to know: **Goose**
> left Block governance for the **Agentic AI Foundation (Linux Foundation)** - repo is
> now `aaif-goose/goose` (`block/goose` redirects); **Google retired consumer
> Gemini CLI / Code Assist on 2026-06-18** in favor of **Antigravity** (enterprise
> keeps Gemini CLI); the original Go **opencode** was archived and continues as
> **Crush** (Charm), while the TypeScript **OpenCode** (`sst/opencode` →
> `anomalyco/opencode`) kept the name; **Roo Code** archived (May 2026, migrate to
> Cline/Kilo Code); **Aider** is still maintained but cadence slowed (last push
> 2026-05-22). Verify stars/licenses before citing - they move.

> **Vendor-agnostic by default:** most harnesses below can be pointed at open/local or
> Ollama **cloud** models via Ollama's OpenAI-compatible endpoint
> (`ollama launch <harness> --model <model>:cloud`) instead of its default vendor model
> - 1M-context open models, local-first with cloud escalation, no lock-in. Check what
> the model actually receives: Ollama's `/v1` drops `developer`-role messages, so a
> harness that sends its system prompt in that role (Pi does) needs a compatibility
> setting or the model runs without it (observed 2026-10). An Ollama `:cloud` model is
> hosted remotely, not local.

Stars/status verified 2026-07-01 where dated; treat undated `verify` cells as unchecked.

| Project | License | Stack role | What it does | Cautions | Repo |
|---|---|---|---|---|---|
| Claude Code | proprietary (Anthropic) | Coding-agent harness | Terminal/IDE/web agent harness with skills, subagents, hooks, MCP, plugins. | Anthropic-hosted models; not OSS. | [docs](https://code.claude.com/docs/en/overview) |
| OpenAI Codex CLI | Apache-2.0 | Coding-agent harness | OpenAI's terminal coding agent; Rust, sandboxed shell by default, MCP, Python SDK. The model lineup turns over quickly (gpt-6.x and gpt-5.6 at 0.162.1, 2026-10-14); read the live list from `~/.codex/models_cache.json` rather than a doc. | Tuned for OpenAI models. **The sandbox bounds writes, not reads**: at `-s read-only` it still read a file outside the workspace (2026-08-29). An interactive session can leave a daemon polling the vendor with the home's credentials until `daemon_auto_start` is off (0.162.1, 2026-10). See B.2. | [repo](https://github.com/openai/codex) |
| Gemini CLI | Apache-2.0 | Coding-agent harness | Google's open terminal agent; TS/npm, ReAct loop, MCP, GitHub Actions mode, only genuinely free tier (1k req/day). | **Consumer access ended 2026-06-18 and moved to Antigravity; enterprise access (Code Assist Standard and Enterprise) continues.** | [repo](https://github.com/google-gemini/gemini-cli) |
| OpenCode | MIT | Coding-agent harness (OSS default) | Provider-agnostic terminal agent (75+ providers), TUI + client/server + LSP, build/plan agents. Very active, and the most adopted provider-agnostic OSS harness. | `sst/opencode` moved to `anomalyco/opencode`; not the archived Go "opencode" (that's now Crush). **`serve`, `web` and `acp` listen on 127.0.0.1:4096 with no auth unless `OPENCODE_SERVER_PASSWORD` is set**; three advisories have been published against that server (CVE-2026-22812, CVE-2026-22813, GHSA-632h-h47v-g4x4), so stay on 1.18.22 or later. Its permission system is not a sandbox by project policy. See `advisories.md`. | [repo](https://github.com/anomalyco/opencode) |
| Pi | MIT | Minimal/hackable harness | Deliberately minimal 4-tool core (Read/Write/Edit/Bash), self-extends at runtime; BYOK across many providers; tree-based sessions. By M. Zechner. | **No built-in permission system - sandbox/containerize it.** Fork: `can1357/oh-my-pi` (omp). | [repo](https://github.com/earendil-works/pi) |
| Cline | open source | IDE+CLI coding agent | Plan/Act modes, MCP, parallel agents + Kanban boards; grew standalone CLI + SDK in 3.x. 8M+ users. Roo Code/Kilo Code forked from it. | VS Code-first heritage. | [repo](https://github.com/cline/cline) |
| Aider | Apache-2.0 | Git-native pair-programmer | Terminal pair-programming pioneer; every edit a git commit; model-agnostic BYOK. | **Cadence slowed - last push 2026-05-22; leaderboard not refreshed for 2026 frontier models.** | [repo](https://github.com/Aider-AI/aider) |
| goose | Apache-2.0 | Coding agent harness | Open, extensible agent (Rust; desktop/CLI/API), recipes (YAML), subagents, MCP, 15+ providers. v1.39.0 (2026-06-25). | **Governance moved Block → Agentic AI Foundation (Linux Foundation); `block/goose` redirects to `aaif-goose/goose`.** | [repo](https://github.com/aaif-goose/goose) |
| deepagents | MIT | Batteries-included harness | LangChain's opinionated harness on `create_agent`/LangGraph. Built-ins: filesystem (`ls`/`read_file`/`write_file`/`edit_file`/`delete`/`glob`/`grep`, pluggable backends), `write_todos` planning, `task` subagents, `execute` shell, `eval` (QuickJS), skills, `AGENTS.md` memory, auto-summarization. **Middleware is the composition model.** v0.7.0 (2026-07-29), py≥3.11. JS twin `langchain-ai/deepagentsjs` publishes to npm as **`deepagents`** (v1.11.x - versions are not aligned, the API is). | A harness *and* a framework layer; needs the LangGraph runtime. **Pre-1.0, breaking changes at minor versions** - 0.7.0 removed `read_file`'s line-number gutter and changed empty `ls`/`glob` output. Model-agnostic in claim but Anthropic-shaped in practice (prompt caching is Anthropic/Bedrock; the JS default model is Claude). | [repo](https://github.com/langchain-ai/deepagents) |
| OpenHands | verify | Autonomous SWE agent | End-to-end software-engineering agent (ex-OpenDevin); hit 1.0 on a new Software Agent SDK (2026); browse/edit/test/retry, CI-friendly. $18.8M Series A. | Higher autonomy = more guardrails needed. | [repo](https://github.com/OpenHands/OpenHands) |
| Crush | verify | Terminal coding agent | Charm's continuation of the original (archived) Go opencode codebase. | Verify license/status; don't confuse with TS OpenCode. | [repo](https://github.com/charmbracelet/crush) |
| Jules | proprietary (Google) | Async coding agent | Assign a full task; runs in an isolated VM and returns a PR. GA at I/O 2026; Gemini 3.1 Pro/3 Flash; Jules Tools CLI + API; self-healing CI. | Not OSS; async model (not interactive). | [site](https://jules.google/) |
| Antigravity | proprietary (Google) | Agentic IDE/platform | Agent-first dev platform (2.0): desktop app + CLI + SDK, multi-agent manager, browser-in-the-loop testing, artifacts. Free tier. Gemini 3.5 Flash + Claude/GPT-OSS. | Not OSS; successor to consumer Gemini CLI. | [site](https://antigravity.google/) |
| Cursor agent | proprietary | IDE coding-agent harness | Agent mode inside the Cursor IDE, plus the `cursor-agent` CLI. | Not OSS. A project's `.cursor/cli.json` loads automatically and **replaces** the global permissions object, deny list included; GHSA-v64q-396f-7m79 chained that auto-load with prompt injection to reach code execution. Permission tokens are glob-matched, so a bare literal like `Read(secrets.json)` never matches (use `Read(**/secrets.json)`). See B.2. | [docs](https://docs.cursor.com/) |
| GitHub Copilot CLI | proprietary (GitHub) | Coding-agent harness | `copilot` CLI sharing config with the VS Code agent; skills, custom agents, hooks, MCP; models from OpenAI, Anthropic, Google, xAI, Moonshot and Microsoft, billed per token in AI credits. | **No telemetry off switch** short of a fully offline mode (1.0.81, 2026-10-29). A built-in GitHub MCP server acts with the user's GitHub login and needs `--disable-builtin-mcps` to stay off. Only `--available-tools` is deny-by-default; `--deny-tool` and `--available-tools` take different tool vocabularies, and a rule in the wrong one does nothing. See B.2. | [docs](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/use-copilot-cli) |
| Google agents-cli | verify | Agent CLI harness | Google's runnable agents CLI (deploy agents on Google Cloud). | Verify status. | [repo](https://github.com/google/agents-cli) |
| OpenHarness | verify | Agent harness | Pure-Python harness: tools/knowledge/observation/action/safety. | Early-stage. | [repo](https://github.com/HKUDS/OpenHarness) |
| Nanobot | verify | Personal/local agent | Lightweight personal agent with memory + sandboxing; long-running focus. | Young; assistant-specific architecture. | [repo](https://github.com/HKUDS/nanobot) |
| Hermes | verify | Agent harness | Nous's agent; an offshoot of OpenClaw. | Include with care; see OpenClaw caution. | [repo](https://github.com/NousResearch/hermes-agent) |
| OpenClaw | MIT | Personal assistant harness | Self-hosted assistant driven from chat apps. | **Advise against** - over-privileged / insecure to run on an average dev's device. | [repo](https://github.com/openclaw/openclaw) |
| browser-use | verify | Browser-driving harness | Drives a real browser for web tasks. | Brittle to site changes. | [repo](https://github.com/browser-use/browser-harness) |
| Omnigent | Apache-2.0 | **Meta-harness** (layer *above* harnesses) | Databricks-built: runs Claude Code, Codex, Cursor, OpenCode, Hermes + YAML-defined custom agents behind one orchestration API; OS-level sandboxing (bubblewrap/seatbelt), stacked cost/access policies, sessions shareable across terminal/web/mobile. | **Self-described alpha; 571 open issues - pin versions.** Corporate backing (Databricks + Neon). | [repo](https://github.com/omnigent-ai/omnigent) |
| QM | MIT | **Meta-harness** (company-scale, layer *above* harnesses) | Y Combinator's multiplayer agent harness, open-sourced 2026-07-31 and run internally across accounting, legal, events and engineering. Per-person and per-room workspaces with scoped memory, files, keychain, permissions, crons and durable sandboxes; Slack + web under one identity. Headless core over Postgres; adapters for Pi, OpenCode, Codex, Claude Code. | **A deployed service, not a local CLI** - `qm init` scaffolds a Fly/AWS deployment repo; BYO model keys, no hosted tier. Skills arrive as git skill packs under `deploy/layers/<org>/`, not from a shared skills tree. YC calls it early and buggy. | [repo](https://github.com/yc-software/qm) |
| Buzz | Apache-2.0 | **Human-agent team workspace** (Slack-shaped, one Nostr relay) | Block's channels, threads, DMs, git hosting and YAML workflows, with every agent a keyed member signed for by its owner. `buzz-acp` drives Goose, Claude Code, Codex and ten preset harnesses over ACP; agents act through the `buzz` CLI. Relay + Postgres 17 + Redis + S3; Postgres full-text search only. | Pre-1.0. Harnesses default to `bypassPermissions` with every ACP request auto-approved; channel membership is the only access control; workflow approval gates not implemented (verified in code 2026-09-25). No knowledge curation beyond per-agent memory and uncurated notes. A team server you operate, not a local tool. | [repo](https://github.com/block/buzz) |
| alook | Apache-2.0 | Multi-agent coordination layer | Gives local coding agents email addresses, roles and an org chart; agents route tasks to each other, report via inbox/Kanban. | v0.0.x; **"self-hosted" is partial - the orchestrator is a Cloudflare-hosted component.** Shared-memory claim undocumented. | [repo](https://github.com/alookai/alook) |
| Grok Build | Apache-2.0 | Coding-agent harness (vendor) | xAI's terminal coding agent: Rust full-screen TUI, headless mode for CI, editor integration over the Agent Client Protocol. | **Squashed periodic exports from an internal monorepo** (1 contributor, 12 commits) - a vendor drop, not a community codebase. Tuned for Grok. | [repo](https://github.com/xai-org/grok-build) |
| herdr | Apache-2.0 | Multi-agent terminal multiplexer | One Rust binary showing every running agent's state (blocked/working/done); sessions survive detach and restart; socket API lets agents spawn their own panes. | Plugin marketplace - vet extensions separately. Sits beside the harnesses and runs them; it has no agent loop of its own. | [repo](https://github.com/herdrdev/herdr) |
| Shepherd | MIT | Agent runtime substrate | Makes a run a reversible git-like trace: fork, replay, revert; syscall-level permissions (Seatbelt/Landlock); outputs held as reviewable proposals. | **Self-declared alpha, APIs changing.** macOS/Linux only. The fork-and-replay primitive is the transferable idea. Re-verified 2026-08-14: still early alpha; companion repo `shepherd-experiments` now carries the paper's meta-agent applications, microbenchmarks and a frozen substrate snapshot for reproducibility. | [repo](https://github.com/shepherd-agents/shepherd) |
| Raven (EverMind) | Apache-2.0 | Self-improving harness | Harness over EverOS memory: durable user + agent memory, evolving skills, Agent Templates, scheduler, tracing. Backed by EverMind (Shanda Group). | **Pre-alpha by its own README**; not on PyPI (install is a Release wheel). Memory benchmark claims are first-party. | [repo](https://github.com/EverMind-AI/Raven) |
| OpenWorker | MIT | Desktop task agent | Andrew Ng's desktop "AI coworker": files + 25 app integrations, decomposes a task into steps, gates consequential actions behind approval. | Open beta, 4 contributors, published 2026-07-20. Read it as a **HITL-approval reference implementation**, not a dependency. Re-verified 2026-08-14: still beta, MIT, no material change. | [repo](https://github.com/andrewyng/openworker) |
| Agent Orchestrator | Apache-2.0 | **Meta-harness** (layer *above* harnesses) | Go daemon (`ao` CLI, SQLite, lifecycle/reaper, ~25 harness adapters) plus an Electron/React Kanban supervisor. One worker = one task = one agent process = one git worktree and branch, and the branch's owner owns its PR. Verification is CI and PR review; no LLM critic. Failure handling is declarative in `agent-orchestrator.yaml` (`event -> action`, `retries`, `escalateAfter` as count or duration). Architectural rule is **Observe -> Update -> Derive**: store observed facts, compute status at read time, never store a derived status. (checked 2026-09-02). | **No token or cost budget anywhere**, with automatic retry across premium agents. Handoff is unschema'd plain text injected into the agent's terminal. Two epoch counters mutated by different subsystems already cause session-resume bugs (#4122). Moved from `ComposioHQ`; npm `@aoagents/ao` frozen at 0.10.0 and legacy, so pre-rewrite tutorials describe a system that no longer exists. | [repo](https://github.com/OrchestratorInc/agent-orchestrator) |
| Aiden | **AGPL-3.0** | Autonomous work engine | Drives files, terminal, browser and APIs from a prompt; 76 skills, 121 tools, 19 providers. | **AGPL core + paid commercial relicensing** - dual-license trap, not a permissive dependency. Solo-maintained. | [repo](https://github.com/taracodlabs/aiden) |

> **Emerging tier - the meta-harness (noted 2026-07-14, re-read 2026-09-02):** a layer
> *above* Section B that treats individual harnesses as interchangeable execution
> backends and moves governance (sandboxing, cost caps, tool allowlists) out of the
> prompt and into the orchestrator. **Omnigent** is the serious general-purpose
> entrant; **Agent Orchestrator** is the largest by adoption; **alook** attacks the same
> problem via org-chart/email routing; **T3MP3ST** (Section: security) is the same
> pattern applied to offensive security. The tier has now converged on a shape: the
> sub-agent is an **OS process behind a per-harness adapter**, isolated by a git
> worktree, not an SDK call. Still too young to recommend as a default - and note that
> the adoption leader ships **no spend ceiling at all** while auto-retrying premium
> agents, so cost governance is the tier's open problem, not a solved one.
> The Agent Client Protocol (B.1) is becoming the standard shape of that per-harness adapter.

### B.1 - Agent Client Protocol: one driver for many harnesses (researched 2026-09-25)

ACP does for coding agents what LSP did for language servers: a client speaks one protocol and drives any agent that implements it, instead of carrying an argv builder and an output parser per CLI.
Claims below were verified against the [spec](https://github.com/agentclientprotocol/agent-client-protocol) at commit 4ef6c75, the [claude-agent-acp](https://github.com/agentclientprotocol/claude-agent-acp) and [codex-acp](https://github.com/agentclientprotocol/codex-acp) adapters at e6681d2 and bf37821, the [docs](https://agentclientprotocol.com/), and live `initialize` handshakes, all on 2026-09-25.

**How it works.**
The client launches the agent as a subprocess, and both sides exchange JSON-RPC 2.0 messages over stdio, one per line, with stdout reserved for protocol traffic and stderr for logs.
The client calls `initialize` to negotiate the integer protocol version and exchange capabilities, then `session/new` with an absolute working directory and the MCP servers the agent should connect to.
Each `session/prompt` is one turn: the agent streams `session/update` notifications (message and thought chunks, tool calls with status, plans, mode changes, usage), and the prompt's response carries the stop reason.
`session/cancel` is a notification, and the agent must stop and answer the pending prompt with `stopReason: "cancelled"` rather than an error.
The client is also a server, because the agent calls back into it for `session/request_permission` and, when the client advertises them, for `fs/*` and `terminal/*`, so a client must never block its read loop waiting for its own prompt to return.
Streamable HTTP is an active RFD rather than a stable transport, so remote agents have no standard wire yet.

**Resume works on current agents.**
`session/load` (replays history) and `session/resume` (restores without replay) are optional capabilities in v1.
Live handshakes on 2026-09-25 returned `loadSession: true` from OpenCode 1.18.15 (`opencode acp`), GitHub Copilot CLI 1.0.81 (`copilot --acp`) and cursor-agent 2026.08.25 (`cursor-agent acp`, which its top-level help does not list), and OpenCode also advertised resume, fork, list and close.
The Claude and Codex adapters advertise load, resume, list, fork and close in code.

**The client does not own permissions.**
The spec says an agent MAY request permission before a tool call, so which calls reach the client is the agent's policy.
The Claude adapter loads user, project and local Claude Code settings, so allow and deny rules and the permission mode settle a call first, and only calls still marked "ask" reach the client.
The Codex adapter forwards only what Codex's sandbox and approval policy escalate, and its default mode auto-reviews and asks only about actions it flags as unsafe.
Neither adapter routes edits or shell commands through the client's `fs/*` or `terminal/*` methods; the wrapped agent runs them in its own process.
ACP therefore centralizes the conversation and the approval UI, but a deny list held only in the client covers only the calls an agent chooses to ask about, and enforcement still belongs in each agent's configuration or an OS sandbox around it.

**Steering lives in extensions.**
Stable v1 offers cancel and nothing else mid-turn, and the v2 prompt RFD states that it "does not specify queueing, steering, or whether agents insert new prompts while busy."
The Claude and Codex adapters both implement a `_session/steering` request, advertised through `_meta.steering.supported`, that injects a message into the running turn, and the Claude adapter also queues a plain `session/prompt` sent mid-turn.
Goose has its own `_goose/unstable/session/steer`.
OpenCode, Copilot and cursor-agent advertised no steering in their handshakes, so a portable client needs cancel-and-re-prompt as the fallback.

**Claude billing.**
The Claude adapter offers subscription login only to clients that advertise terminal auth.
Anthropic's [Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview) (fetched 2026-09-25) says: "Unless previously approved, Anthropic does not allow third party developers to offer claude.ai login or rate limits for their products, including agents built on the Claude Agent SDK."
A product that ships an ACP client should plan on API keys for Claude, and no official source addresses an individual running the adapter on their own subscription.

**Versioning and governance.**
The stable wire version is 1, new capabilities are additive, and each connection speaks exactly one negotiated version.
The v2 draft (2026-07-20) replaces `session/load` with `session/resume` plus replay, drops session modes, and moves client-side `fs/*` and `terminal/*` to MCP.
Zed started ACP in August 2025 and co-governs it with JetBrains, and one lead maintainer from each holds the veto under an interim model aimed at a foundation.
The [registry](https://github.com/agentclientprotocol/registry) lists 42 agents, and the clients page lists Zed and JetBrains natively plus Neovim, Emacs, VS Code and dozens more through plugins.
IBM's Agent Communication Protocol shares the acronym and is unrelated: it was a REST protocol, and LF AI & Data announced on 2025-08-29 that it is winding down into A2A.

**Stance.**
Use ACP as the driver for non-Claude harnesses in any multi-agent client, because it removes per-CLI parsing, every agent probed supports resume, and several agents speak it natively.
Keep enforcement in agent configuration or an OS sandbox rather than the client, treat steering as an optional capability with cancel-and-re-prompt behind it, and write against v1 with the v2 draft in view.

### B.2 - Harness mechanics: what each one reads, enforces and sends (probed 2026-07 to 2026-10)

Facts below were observed by running each CLI unless marked doc-derived; each names the version it was seen on, because these change with self-updates.
The general lessons (enforcement fails open, a boundary is real only after a canary) are principles 18 and 19 in `engineering-principles.md`.

**Where skills, subagents and commands come from.**
`~/.agents/skills/` is the shared user-level skills location: Codex, Cursor, Copilot, goose, opencode, Pi, Kimi Code and Gemini CLI read it natively (doc-derived for Kimi and Gemini).
Claude Code reads only `~/.claude/skills/`, so a shared tree needs symlinks into it.
Antigravity reads `.agents/` per project but not globally; a global tree needs `~/.gemini/config/skills.json` with an absolute path, because `~` is not expanded (1.3.3, 2026-10-14).
Only skills are portable.
Claude Code and Cursor read subagent definitions (the Cursor CLI only from a project's `.cursor/agents/`, build 2026.08.25), and Gemini CLI uses the same subagent file shape at its own path.
Slash commands are markdown files in Claude Code and TOML files in Gemini CLI, and the other harnesses have none.
The strictest skill parser seen is Copilot's: it rejected skills Claude Code accepted, for descriptions over 1024 characters and for an unquoted `: ` in a YAML plain scalar (2026-08).

| Harness | Permission model and its traps | Telemetry and remote switches | Headless quirks |
|---|---|---|---|
| Claude Code | Deny rules beat allows at every scope. In a never-trusted directory the project's allow entries are dropped while its deny rules, hooks and `settings.local.json` still load; a hook's `ask` becomes a refusal in `-p` runs, listed in `permission_denials` (2.1.259 to 2.1.280). The sandbox covers shell commands; file tools fall under deny rules. Ignore files such as `.claudeignore` are not read. | `env.DISABLE_TELEMETRY`, `DISABLE_AUTOUPDATER=1`, `disableRemoteControl` | Hook exit 2 returns stderr to the agent; stderr at exit 1 and at exit 0 never reaches it. |
| Codex CLI | Sandbox modes gate writes and network, not reads (2026-08-29). A headless run writes a `trusted` entry into the real config even with `--ignore-user-config`; plugins and MCP servers installed by the desktop app load into every headless run from that home. A separate `CODEX_HOME` isolates all of it. | `[analytics] enabled=false`; `[features] daemon_auto_start=false` stops the background daemon an interactive session leaves running (0.162.1) | `exec` refuses an untrusted non-git directory without `--skip-git-repo-check` and reads stdin, so close it. Hooks in `~/.codex/hooks.json` since 0.162.1 use Claude Code's file shape; an untrusted hook is dropped silently. |
| Cursor CLI | First-run defaults: sandbox off, empty deny list, allowlist approval mode (2026-08-08). Tokens are glob-matched; a bare literal never matches. Shell allows match the literal first word, so a wrapper command defeats them. A project `cli.json` replaces the global permissions object. `-f` and `--yolo` bypass the allowlist. | Privacy mode is an account setting; requests still transit Cursor's servers. | The CLI rewrites its own config files and reset a hardened file mode within an hour, so harden the directory. `-p` needs `--trust` in a new workspace. |
| Copilot CLI | Grants are per-spawn flags with no persistent allow list; read-only commands auto-approve. `--deny-tool` takes `kind(arg)` permission syntax while `--available-tools` takes internal tool names, and only the latter is deny-by-default (1.0.81). Granting the shell tool forfeits any tool-level boundary. | `--no-remote-export` per session; **no telemetry off switch** (1.0.81, 2026-10-29); a built-in GitHub MCP server loads with no config entry. | A denial arrives as a JSONL `tool.execution_complete` with `code: "denied"`; there is no hanging prompt. There is no model-list command, but `--log-level all` logs the account's model list. |
| opencode | Permission system is not a sandbox (project policy). | `share` setting (manual, auto, disabled); `OPENCODE_DISABLE_MODELS_FETCH=1`; telemetry opt-out unverified. | `serve`, `web` and `acp` open an unauthenticated server on 127.0.0.1:4096 unless a password is set. |
| goose | Hooks: only PreToolUse and Stop can block (doc-derived). No switch disables context-file or skill discovery; `GOOSE_PATH_ROOT` isolates a run. | `GOOSE_TELEMETRY_ENABLED=false`; `serve` and `acp` are its network subcommands. | Last key wins in `config.yaml`. |
| Pi | No permission system; run it in a container or OS sandbox. | `PI_TELEMETRY=0` | Sends its system prompt in the `developer` role, which Ollama `/v1` drops; set `compat.supportsDeveloperRole: false`. No cap on tool output size (a 258 KB file went to the model whole). |
| Antigravity (`agy`) | A headless run that needs a permission is auto-denied. | `agy remote-control start` registers a daemon; telemetry opt-out unverified. | The installer appends PATH to every shell profile it finds; the binary self-updates. |

**Effort levels and model names.**
Both differ per harness, and an unknown value fails the spawn.
Claude Code and Antigravity take low to max; Codex's levels are per model; Copilot also accepts `none` and `minimal`; Cursor has no effort flag and encodes it in the model id (`-xhigh`, or a bracket parameter).
Model discovery: Codex has an undocumented `models_cache.json` with per-model reasoning levels; Cursor has `--list-models`; Claude Code and Copilot have no list command (2026-10-14).
Picking a Claude model inside Cursor or Copilot does not make the call Anthropic-direct: it runs on the host's infrastructure under the host's retention terms.

**MCP inventory.**
No single file lists a CLI's MCP servers.
Account-level connectors and built-in servers have no config entry, and desktop-app installers write entries into a CLI's config without notice, so take inventory from each CLI's own `mcp list`.

---

## Section C - Memory / long-term context / entity recall

| Project | License | Memory style | What it does | Cautions | Status | Repo |
|---|---|---|---|---|---|---|
| Letta | Apache-2.0 | Stateful agent memory | Persistent state, memory blocks, self-improvement. | Opinionated. | Include | [repo](https://github.com/letta-ai/letta) |
| Mem0 | Apache-2.0 | Universal memory layer | Drop-in user/session/agent memory; self-host or hosted. | Not a full framework. | Include | [repo](https://github.com/mem0ai/mem0) |
| Graphiti | Apache-2.0 | Temporal knowledge graph | Evolving entity/fact/provenance/time graphs. | One layer of a larger stack. | Include | [repo](https://github.com/getzep/graphiti) |
| MemOS | verify | Memory OS | Unified store/retrieve/manage for long-term/multimodal/tool/KB memory. | Younger; verify license. | Include | [repo](https://github.com/MemTensor/MemOS) |
| Cognee | verify | Knowledge engine | Learns context over time via vectors + graphs + ontology. | Complex mental model. | Include | [repo](https://github.com/topoteretes/cognee) |
| claude-mem | verify | Claude memory add-on | Memory daemon for Claude/Claude Code. | Niche; verify status. | Unverified | [repo](https://github.com/thedotmack/claude-mem) |
| Acontext | verify | Context platform | Self-learning context store. | Verify current OSS status. | Unverified | [repo](https://github.com/memodb-io/Acontext) |
| Memori | verify | SQL-native memory | SQL-native agent memory engine. | Verify status. | Unverified | [repo](https://github.com/MemoriLabs/Memori) |
| Hindsight | verify | Human-like memory | Memory concept/system. | Verify status. | Unverified | [repo](https://github.com/vectorize-io/hindsight) |
| mempalace | verify | Memory palace | Structured long-term store. | Verify status. | Unverified | [repo](https://github.com/MemPalace/mempalace) |
| Memoria | Apache-2.0 | **Version-controlled** memory | Snapshot / branch / merge / roll back a memory store like a git repo; hybrid vector + full-text recall, contradiction detection, audit trail per mutation. | Branching rides **MatrixOne's** copy-on-write MVCC engine - the headline feature carries a DB dependency, not a drop-in store. Quiet since 2026-06-29. | Caution | [repo](https://github.com/matrixorigin/Memoria) |
| EverOS | Apache-2.0 | Markdown-native local memory | Local-first portable memory layer; the store underneath Raven (Section B). | Pre-1.0, moves with Raven. | Unverified | [repo](https://github.com/EverMind-AI/EverOS) |
| TencentDB Agent Memory | MIT | Layered memory hub + LLM proxy | Four layers (raw turns, key facts, scenario summaries, user profile) plus team assets (skills, an LLM-wiki, a code graph). Local SQLite + sqlite-vec by default, Tencent Cloud VectorDB optional; BM25 + vector recall fused with RRF. v2 adds a Memory Proxy that speaks the Anthropic and OpenAI protocols and injects memory into the system prompt, with ACLs and adapters for Claude Code, Codex, OpenClaw and Hermes. TypeScript, v2.0.2 (2026-10-09; GitHub API checked 2026-10-19). | **Every benchmark is Tencent's own** (PersonaMem 47.85% to 76.10%, without vs with it); no LoCoMo or LongMemEval, and the one independent harness lists it not-run (2026-10-15). The proxy sits on the model-traffic path and sees every prompt and credential; its Claude Code path swaps Claude Code's credentials for a memory key and forwards upstream on an API key. v2.0.2 pins simple-git and drizzle-orm below their security fixes and ships no lockfile for Memory Core (field note 2026-10-19). No MCP server. 772 open issues. A static read (2026-10-19) found its Langfuse, ClickHouse and Opik sinks off by default and no built-in vendor endpoint; not runtime-verified. A managed edition is sold on Tencent Cloud's China site. | Caution | [repo](https://github.com/TencentCloud/TencentDB-Agent-Memory) |
| Hy-Memory (Tencent Hunyuan) | Apache-2.0 | Trained memory *writer* | A 30B-A3B model trained (on-policy distillation, then chunk-level GRPO) to decide what an existing memory framework stores, plus a Python SDK with chat, working and coding pipelines over ChromaDB/Qdrant/FAISS, Kuzu/Neo4j and SQLite. Paper arXiv 2610.22196 (2026-10-15). | Days old at check (2026-10-19). Its 55.49% vs Claude Opus 5's 54.62% macro score is the authors' own, on 20% subsamples. A 30B MoE writer is a GPU-serving dependency. GitHub tags reach v1.0.4 while PyPI `hy-memory` shows 2.0.4 with no project link, so confirm the package is Tencent's before installing. | Unverified | [repo](https://github.com/Tencent-Hunyuan/Hy-Memory) |

> **Branch-and-merge memory (noted 2026-07-27):** Memoria and Shepherd (Section B)
> arrive at the same primitive from opposite ends - versioning an agent's *state* so a
> run can be forked, replayed and reverted. Both are early and both couple it to
> specific infrastructure, so neither is a recommendation yet. The *primitive* is the
> thing to watch: it makes agent work auditable and undoable, which is what
> production actually asks for.

---

## Section D - Knowledge / retrieval / context engines

The durable knowledge/context layer agents operate on.

| Project | License | Stack role | What it does | Cautions | Repo |
|---|---|---|---|---|---|
| LlamaIndex | MIT | KB + retrieval + agents | Indexing/querying/graphs/retrievers over your data. | Broad surface. | [repo](https://github.com/run-llama/llama_index) |
| Haystack | Apache-2.0 | Retrieval + pipelines | Production RAG, routing, tool pipelines. | More engineering than turnkey. | [repo](https://github.com/deepset-ai/haystack) |
| LightRAG | verify | GraphRAG engine | Dual-level retrieval + KG; server/UI; local. | License verify before procurement. | [repo](https://github.com/HKUDS/LightRAG) |
| RAGFlow | Apache-2.0 | Full context platform | Deep doc understanding, citations, agent templates. | Platform, not a tiny SDK. | [repo](https://github.com/infiniflow/ragflow) |
| txtai | verify | Semantic search + workflows | Embeddings DB, graph, relational storage, LLM workflows. | More context engine than full agent stack. | [repo](https://github.com/neuml/txtai) |
| Graphiti | Apache-2.0 | Temporal KB / graph memory | Evolving entity/fact graph. | Needs surrounding stack. | [repo](https://github.com/getzep/graphiti) |
| FalkorDB | **SSPL** | Graph DB substrate | Graph DB for KG / GraphRAG. | SSPL not OSI-approved. | [repo](https://github.com/falkordb/falkordb) |
| WrenAI | multi (see cautions) | **Semantic layer** over warehouses | Governed text-to-SQL for agents: an MDL semantic model (entities, relationships, metrics, access policy) sits between question and 20+ warehouses, so generation is schema-aware and traceable to approved definitions. | **Licensed by path** - `core/`/`sdk/`/`skills/`/`examples/` Apache-2.0, `docs/` CC-BY-4.0, and the LICENSE pre-stages **AGPL-3.0** for future modules (verified 2026-07-27). Re-check before depending on a new subtree. | [repo](https://github.com/Canner/WrenAI) |

> **When an agent must query a real warehouse**, the WrenAI pattern is the one to
> copy even if the product is not: model the semantics first (entities, joins,
> metrics, who may see what), generate SQL second. Text-to-SQL straight off a raw
> schema guesses joins and invents metric definitions; a semantic layer makes the
> answer traceable to something a human approved.

---

## Section E - Web & document ingestion

| Project | License | Stack role | What it does | Cautions | Repo |
|---|---|---|---|---|---|
| Firecrawl | AGPL-3.0 | Web knowledge ingestion | Scrape/crawl/extract/search + MCP for agents. | AGPL may block some orgs. | [repo](https://github.com/firecrawl/firecrawl) |
| Crawl4AI | verify | Web ingestion / crawling | LLM-friendly crawler → markdown/structured. | Recent supply-chain hotfix (litellm→unclecode-litellm); pin current versions. | [docs](https://docs.crawl4ai.com/) |
| Docling | MIT | Document parsing | Complex docs → structured, agent-ready data. | Parsing layer only. | [repo](https://github.com/docling-project/docling) |
| Scrapling | verify | Adaptive scraping | Stealth/adaptive web scraping. | Verify status. | [repo](https://github.com/D4Vinci/Scrapling) |
| surya | verify | OCR / layout | OCR, layout, reading-order detection. | - | [repo](https://github.com/datalab-to/surya) |
| pdfplumber | MIT | PDF extraction | PDF text/table extraction. | Single-purpose. | [repo](https://github.com/jsvine/pdfplumber) |
| langextract | Apache-2.0 | Structured extraction (grounded) | Pulls structured records out of unstructured text and maps every extraction back to exact character offsets in the source; schema enforced from few-shot examples; multi-pass chunking for long documents; Gemini, OpenAI and Ollama backends; emits interactive HTML for review. v1.6.0, active (2026-07-27). | Published by Google but **not an officially supported Google product** - no vendor SLA. OpenAI backends need `fence_output=True` with `use_schema_constraints=False`. | [repo](https://github.com/google/langextract) |
| Instructor | MIT | Structured outputs (typed) | Pydantic-typed LLM responses with validation and automatic retries across providers. v1.15.4, active (2026-07-27). | Types and validates the response; no source grounding and no long-document strategy. | [repo](https://github.com/567-labs/instructor) |
| Outlines | Apache-2.0 | Constrained decoding | Constrains generation against a grammar, regex or JSON schema so malformed output cannot be emitted in the first place. v1.3.2, active (2026-07-27). | Operates at the decoding layer and needs a backend exposing logits; it is not an extraction pipeline. | [repo](https://github.com/dottxt-ai/outlines) |

---

## Section F - Skills / tool packs / capability layers

| Project | License | Role | What it does | Repo |
|---|---|---|---|---|
| affaan-m/ECC | MIT | Harness config OS | The largest skill/config distribution in this space: 67 agents, 281 skills, 94 commands, 34+ rule sets, hooks on 20+ event types, a memory/instincts layer and AgentShield, installable across ~12 harnesses. v2.1.0. Renamed from `everything-claude-code`; match on `affaan-m` because same-name copies are common. Mine it for patterns and install profile-scoped - a `full` install rewrites agents, hooks and rules, and 281 skills is a trigger-collision surface. | [repo](https://github.com/affaan-m/ECC) |
| affaan-m/agentshield | MIT | Agent-config security scanner | Audits agent/skill definitions, MCP configs and tool permissions against a stated 102 rules; CLI, GitHub Action, plugin, GitHub App. The off-the-shelf analogue to a hand-written agent-tooling security checklist; rules are first-party and unaudited, so diff rather than adopt. | [repo](https://github.com/affaan-m/agentshield) |
| addyosmani/agent-skills | verify | Skill pack | Reusable agent skills. | [repo](https://github.com/addyosmani/agent-skills) |
| NVIDIA/skills | verify | Skill pack | NVIDIA agent skills. | [repo](https://github.com/NVIDIA/skills) |
| anthropics/skills | Apache-2.0 (most skills) | Skill pack | Anthropic's own public Agent Skills repo; includes the document skills (docx/pdf/pptx/xlsx) that back Claude's document handling. | [repo](https://github.com/anthropics/skills) |
| K-Dense-AI/scientific-agent-skills | verify | Skill pack | Scientific agent skills across biology, chemistry, medicine and drug discovery, plus scientific databases; portable across harnesses via the Agent Skills standard. 154 skills (2026-07-27). Community-maintained, not an Anthropic project; the four document skills are vendored from `anthropics/skills`. | [repo](https://github.com/K-Dense-AI/scientific-agent-skills) |
| CopilotKit / AG-UI | verify | Agent-to-UI protocol | Agents ↔ frontend state, UI, HITL. | [repo](https://github.com/copilotkit/copilotkit) |
| Firecrawl MCP / Docling MCP / Strands tools | MIT/varies | MCP tool servers | Web + document + provider tools over MCP. | see ingestion rows |
| rtk-ai/rtk | verify | CLI token optimizer | Token-killing CLI output proxy. | [repo](https://github.com/rtk-ai/rtk) |
| JuliusBrussee/caveman | verify | Output style | Token-compressed communication style. | [repo](https://github.com/JuliusBrussee/caveman) |
| cobusgreyling/loop-engineering | MIT | Loop design patterns + CLI | Patterns, starters and tools (`loop`, `loop-audit`, `loop-init`, `loop-cost`) for designing the loop an agent runs in - scheduled triage, CI sweeps, cost accounting - rather than the prompt. Half tooling, half essays; the essays are the reason to read it. | [repo](https://github.com/cobusgreyling/loop-engineering) |

> **MCP servers:** to *build* one, defer to the system's `build-mcp-server` /
> `build-mcp-app` skills (official `mcp-server-dev` plugin) and `plugin-dev`'s
> `mcp-integration`. This skill does not reimplement them.

---

## Section G - Fine-tuning / adaptation / local training

| Project | License | Role | What it does | Repo |
|---|---|---|---|---|
| Unsloth | Apache-2.0 + AGPL components | Fine-tuning / local training | Fast local tuning + RL for open models; studio UI. | [repo](https://github.com/unslothai/unsloth) |
| TRL | Apache-2.0 | RLHF / post-training | HF Transformer RL: RLHF, DPO/PPO, post-training loops. | [repo](https://github.com/huggingface/trl) |
| PEFT | Apache-2.0 | Adaptation | Parameter-efficient fine-tuning (LoRA-style). | [repo](https://github.com/huggingface/peft) |
| Axolotl | Apache-2.0 | Training stack | Popular open fine-tuning stack. | [repo](https://github.com/axolotl-ai-cloud/axolotl) |

---

## Section H - RL / agent optimization / self-improvement

| Project | License | Stack role | Why it matters | Repo |
|---|---|---|---|---|
| Agent Lightning | verify | Agent RL / prompt optimization | Framework-agnostic trainer: RL + auto prompt-opt + SFT; wraps multiple frameworks. | [repo](https://github.com/microsoft/agent-lightning) |
| OpenPipe ART | Apache-2.0 | Agent reinforcement trainer | RL over multi-step agent trajectories with an LLM judge supplying the reward, so a task needs no hand-written reward function. | [repo](https://github.com/OpenPipe/ART) |
| Molt (NVIDIA labs) | Apache-2.0 | Agentic-first RL research framework | Fully async, multi-turn, multimodal RL on Ray + vLLM rollouts + FSDP2, scaling to trillion-param MoE; ~9.2K lines of RL-specific code, meant to be read and forked. **NVIDIA labs - research code, not a supported NeMo product.** | [repo](https://github.com/NVIDIA-NeMo/labs-molt) |
| Letta / Mem0 / MemOS / Cognee / Graphiti | - | Behavioral improvement via memory | The practical path to "agents that get better over time" in most production systems. | see Section C |

**Stance:** treat agent RL as a specialized layer. Do not pick an agent framework
primarily on its RL story unless you have an explicit post-training roadmap. For
most teams, "improvement over time" comes from the memory layer, not RL.

### H.1 - Harness self-improvement (researched 2026-10-19)

A separate lane from RL. The executor model stays frozen while a second model
rewrites the harness around it: prompts, guardrails, memory files, skills, scripts,
subagents and sometimes the harness code itself. Two questions separate the
entrants: what signal decides whether an edit stays, and whether the improvement
machinery can edit itself. Results are each paper's own; GitHub figures are from
the API, checked 2026-10-19.

| Project | License | What it edits | Keep/reject signal | Edits its own improver? | Headline result (self-reported) | Link |
|---|---|---|---|---|---|---|
| Harness² (Google Cloud AI Research) | Apache-2.0 | Eight harness files of an OpenCode or Codex executor, per task | **No labels.** Candidate and base runs of the same task are compared by an anonymized model selector | No. Stage prompts and the decision rule are fixed; a per-domain library of adopted harnesses and lessons grows, and starts empty on every sweep | One step: WorkBuddy-Bench +11.5, JobBench +4.5, LAB +11.8 pp; beats Meta-Harness at k=5. v0.1.0 | [repo](https://github.com/google-research/harness2) |
| Meta-Harness (Stanford) | MIT | Harness code, searched offline | Scores on a search set; the proposer reads every prior candidate's code, traces and scores | No | Gains over hand-built harnesses on TerminalBench-2 and text classification. | [repo](https://github.com/stanford-iris-lab/meta-harness) |
| RRSI (Google Cloud AI Research, UNC, Stanford, WashU) | Apache-2.0 | The whole harness, component by component | Evolve-set scores, regularized: an annealed cap on edits per candidate, a critic that rejects benchmark-specific edits, a pruner for low-value ones | No | Up to +14.1 on the evolve split and +4.7 on five unseen benchmarks, with 30% fewer tokens. | [repo](https://github.com/google-research/rrsi) |
| Darwin Gödel Machine (UBC, Sakana; ICLR 2026) | Apache-2.0 | **Its own agent code**, including the code that does the editing | Benchmark scores over an open-ended archive of variants | Yes | SWE-bench 20% to 50% (secondary source). quiet since 2025-08-13 | [repo](https://github.com/jennyzzt/dgm) |
| Evo² (Google, UIUC) | Paper only | Harness code **and** the evolver model's weights, trained on its own edit trajectories | Task scores | Yes (weights) | SWE-bench Verified 48.3%, Polyglot 82.1% | [arXiv 2610.13025](https://arxiv.org/abs/2610.13025) |
| ModularRSI | Paper only | Five harness modules evolved separately, then integrated | Success or failure on 2,000 tasks kept disjoint from the eval benchmarks | No | Gains on Terminal-Bench 2.0 and SWE-bench Verified (no figures on the abstract) | [arXiv 2609.14857](https://arxiv.org/abs/2609.14857) |
| Recursive Harness Self-Improvement (Sakana, UC Berkeley) | Paper only | A prompt-level specification of the agent loop | Pairwise comparison over its own revision history | No | Low-effort agents beat max-effort ones at up to 60% lower cost, on 30 synthetic tasks | [arXiv 2607.15524](https://arxiv.org/abs/2607.15524) |
| HSI | **No license** | Task harness code, plus the evolver's strategy through a meta-evolver | Environment reward | Yes (strategy) | BabyAI +39.3%, Crafter +33.0%. | [repo](https://github.com/TailinZhou/hsi) |

**Harness² in detail** (read in code at v0.1.0, 2026-10-19). Per task it runs
`4k` executor rollouts and `3k` editor sessions (k=1: 4 and 3; k=5: 20 and 15),
plus one selection and one reflection session. The default editor is Claude Opus
4.8. The editable surface is a path allowlist per executor, and an invalid
proposal gets one retry before the current harness is kept. Four patterns transfer
to any self-editing system:

- **Probe against the unmodified harness on the same task**, and treat "keep the
  base output" as a first-class verdict. The selector prompt states it is "a
  completely valid and expected outcome."
- **Anonymize and shuffle candidates** with a seeded order before a model chooses,
  so position and label cannot steer the pick.
- **Gate what enters memory.** A lesson is refused unless cue, lesson and evidence
  are all present, and stored harnesses are scanned for grader markers
  (`pass_rate`, `passed_count`) before they reach any context.
- **Make the composer the last gate.** Its prompt says that "merging an edit
  launders it", so every rule that bound the proposers binds the merge.

Cautions for Harness²:

- **Cost has no ceiling yet.** There is no spend cap (issue #4), resumed runs
  undercount spend (#50), and the paper reports compute only as a chart.
- **The executor is not isolated.** Codex runs with
  `--dangerously-bypass-approvals-and-sandbox` and `--dangerously-bypass-hook-trust`,
  network access is unrestricted, and the README leaves egress control to the
  operator. A third-party report says Codex fetched a public grading rubric during
  a run (unverified).
- **It is shaped as a benchmark runner.** Your own task stream needs a benchmark
  adapter. It is Linux-only, Vertex AI by default, and supports OpenCode and Codex
  executors only (Claude Code and Pi requested in #64). An open bug has the grader
  trusting a task's self-reported pass counts (#80). No independent reproduction
  existed at check time.

**Stance:** every entrant except Harness² needs a score, so they fit domains that
already have a test suite. Harness² is the one built for open-ended work with no
verifier, at the price of about seven model sessions per task at k=1. All of them
are methods rather than tools: trial one on a fixed task set with a hard spend cap
and a sandboxed executor before trusting a gain it reports about itself.

---

## Section I - Eval, observability & code intelligence

| Project | Role | Repo |
|---|---|---|
| deepeval | LLM eval framework | [repo](https://github.com/confident-ai/deepeval) |
| openai/evals | Eval harness | [repo](https://github.com/openai/evals) |
| Opik (Comet) | LLM tracing/eval/observability | [repo](https://github.com/comet-ml/opik) |
| MLflow | Experiment tracking, registry, GenAI tracing | [repo](https://github.com/mlflow/mlflow) |
| Weights & Biases | Tracking / Weave LLM tracing | [repo](https://github.com/wandb/wandb) |
| Giskard v3 (`giskard-oss`) | Agent evals + red-teaming + test generation: scenario APIs, LLM-as-judge, adversarial scanner. Apache-2.0. **v3 is a rewrite, not a rename** - v2 is unmaintained; pin deliberately. | [repo](https://github.com/Giskard-AI/giskard-oss) |
| agent-flow | Run-level observability: interactive node graph of a Claude Code / Codex run branching into subagents and tool calls, timeline + JSONL replay. Apache-2.0. | [repo](https://github.com/patoles/agent-flow) |

### I.1 - Codebase → queryable knowledge graph (verified 2026-07-27; graphify re-verified 2026-07-28)

The layer that replaces "the agent greps until it finds it" with "the agent queries
a structural index." All the serious entrants share one architecture: **tree-sitter
AST parse → persistent graph of symbols, calls, imports and dependents → served to
the agent over MCP (or as a skill), so retrieval is targeted instead of exhaustive.**

| Project | License | Lang | Index | Interface | Scope beyond code | Notes |
|---|---|---|---|---|---|---|
| [graphify](https://github.com/Graphify-Labs/graphify) | Apache-2.0 | Python | `graphify-out/graph.json` + HTML report | CLI + MCP (extra) + `/graphify` skill | docs, PDFs, SQL schemas, configs, media (**LLM pass**) | Widest scope and easiest install; Leiden community detection gives "what is this subsystem" answers. PyPI `graphifyy` 0.9.29, py>=3.10. 676 open issues; anonymous org. Its installer also edits `CLAUDE.md` and registers PreToolUse hooks - see caveat 6. |
| [colbymchenry/codegraph](https://github.com/colbymchenry/codegraph) | MIT | C | SQLite + FTS5 | MCP, 8 agent clients | code only | Auto-syncs on file change. **Releases carry `gh attestation verify` build attestations** (2026-07 onward) - the best supply-chain story here. |
| [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) | MIT | C | embedded, static binary | MCP (15 tools) | code only | ~158 languages, LSP type resolution for ~11. Only entrant with a public write-up ([arXiv 2603.27277](https://arxiv.org/html/2603.27277v1)), which reports **83% answer quality vs 92% for plain file exploration at ~10x fewer tokens**. |
| [code-review-graph](https://github.com/tirth8205/code-review-graph) | MIT | Python | SQLite | MCP + CLI | code only | Incremental change tracking aimed specifically at review and blast-radius questions. |
| [repowise](https://github.com/repowise-dev/repowise) | **AGPL-3.0** | Python | - | CLI | code health, docs, git analytics | Analytics rather than a queryable graph. AGPL. |
| [GitVizz](https://github.com/adithya-s-k/GitVizz) | **none** | TS | - | web/CLI | repo visualization | No license file (all rights reserved) and untouched since 2026-02-12. Do not vendor. |

**Shared caveats - apply to the whole category, not one entrant.**

1. **Star counts are not a quality signal here.** Every tool above was created in 2026 and the whole category spiked at once, with multi-thousand-stars-per-day bursts and aggregators reporting materially different totals for the same repo. Rank on license, attestation, benchmark method and issue backlog - never on stars.
2. **Every performance number is first-party.** The 82x, 120x, 99%, 69% and 8x figures come from vendors benchmarking themselves on self-selected repos with differing methods. They are not comparable to each other.
3. **The honest claim is a tradeoff, not a free win.** The one measured result in the category (codebase-memory-mcp's own paper) shows a graph index buying a ~10x token reduction at a ~9-point answer-quality cost. Graphs win decisively on *structural* questions - who calls this, what breaks if I change it, where does this route go - and lose to plain file reading on questions needing the actual prose of the code.
4. **"Fully local" needs reading twice.** It is true of AST parsing in all of these. It is not true of graphify's doc/PDF/media pass, which calls a model - Gemini when `GEMINI_API_KEY`/`GOOGLE_API_KEY` is present, otherwise the host coding agent itself via parallel `general-purpose` subagents. The second path bills session tokens instead of an API key, so "no API key needed" does not mean "free".
5. **All are pre-1.0** with large open-issue counts. Pin versions.
6. **Check what the installer touches before running it.** These ship as agent integrations, so "install" can mean writing outside the project. graphify's (verified 2026-07-28) writes the skill, injects an always-on block into `CLAUDE.md`, and registers PreToolUse hooks on `Bash|Grep` and `Read|Glob` in `settings.json`, user-global unless `--project` is passed. That is a reasonable design for its purpose and a bad surprise on a curated station; install project-scoped, or vendor the skill and skip the installer.

**The pick.** For giving a coding agent a queryable graph of a whole repo today,
start with **graphify** - it is the only one that also ingests the docs, schemas and
PDFs sitting beside the code, which is usually where the answer actually lives, and
it installs as a skill rather than needing MCP wiring. Choose **codegraph** instead
when supply-chain provenance is the deciding factor (it is the only one shipping
verifiable build attestations), or **codebase-memory-mcp** when the repo is
polyglot beyond graphify's language set (it claims 40; the published dependency
list is ~28 grammars in the core install plus 4 behind extras) or an honest
published benchmark matters
more than breadth. Use **code-review-graph** when the job is specifically
review/blast-radius rather than general navigation. Run any of them alongside plain
Read/Grep, not instead of it - caveat 3 is why.

> **The test that separates these:** a knowledge graph over a corpus - code or prose -
> is only trustworthy if it is deterministic and rebuilds idempotently from source.
> A parse → SQLite+FTS5 → offline query pipeline meets that bar with no API key. If a
> model is needed to *build* the graph, the graph is not reproducible.

---

## Section J - The NVIDIA NeMo stack (researched 2026-07-28)

NVIDIA ships an agent stack at every layer, but it is four products with one prefix
rather than one product. The single most useful thing to hold onto is **where the
free OSS ends and the licence begins**, because the boundary does not fall where
the "open source" framing suggests.

| Layer | What it is | License reality |
|---|---|---|
| [NeMo Agent Toolkit](https://github.com/NVIDIA/NeMo-Agent-Toolkit) | Interop + eval + profiling around *your* framework | Apache-2.0, plain `pip install nvidia-nat`. No GPU, no NVIDIA account, no licence. |
| [NeMo Guardrails](https://github.com/NVIDIA-NeMo/Guardrails) | Programmable I/O rails for LLM apps | Apache-2.0, v0.23.0. Usable standalone; the only platform piece that is genuinely independent. |
| [NeMo Framework](https://docs.nvidia.com/nemo-framework/user-guide/latest/overview.html) | Self-managed training / post-training / RL | Source Apache-2.0; the **container** ships under the NVIDIA AI Product Agreement. |
| [NeMo Platform (microservices)](https://docs.nvidia.com/nemo/microservices/latest/) | Customizer, Evaluator, Auditor, Data Designer, Safe Synthesizer, Entity/Data Store, Deployment Mgmt, NIM Proxy, Studio | NGC containers under NVIDIA's SLA. **Production requires NVIDIA AI Enterprise.** |
| [NIM](https://developer.nvidia.com/nim) | A model + inference engine in a container, exposed as an OpenAI-compatible endpoint | Free to self-host for dev/test/research/eval under free Developer Program membership. **Production requires NVAIE.** |
| [Blueprints](https://github.com/NVIDIA-AI-Blueprints) | Reference apps: source + Helm chart + sample | Blueprint *source* is Apache-2.0; the NIM containers they pull are not. |
| [Nemotron 3](https://www.nvidia.com/en-us/ai-data-science/foundation-models/nemotron/) | Open-weight model family, Nano / Super / Ultra | Permissive but **not uniform** - see the licence split below. |

### J.1 - NeMo Agent Toolkit: what it actually is

Read the name as a trap. It is **not** a competitor to LangGraph or CrewAI, and
adopting it does not mean replatforming. It wraps agents, tools and workflows from a
framework you already use as composable function calls, then adds the things those
frameworks are weakest at: a YAML workflow config, an eval harness, and a profiler
that reports tokens, latency, throughput, bottlenecks and concurrency spikes per
invocation. Shipped plugins cover LangChain/LangGraph, LlamaIndex, CrewAI, Semantic
Kernel, Google ADK, AutoGen and Agno, plus LiteLLM, Bedrock, OCI and OpenTelemetry.
It is an MCP **client and server** (`nat mcp serve`, `nat fastmcp server run`).

**The real caution is naming, not capability.** It has been renamed twice in three
minor versions - `agentiq` → `aiqtoolkit` (v1.1) → `nvidia-nat` with the CLI moving
`aiq` → `nat` (v1.2) - and the transitional package, the `aiq` module, the `aiq`
command and the `aiq_*` aliases are all **now deleted**. Every blog post, tutorial
and Stack Overflow answer written before mid-2025 is dead code against current
releases. Breaking changes also ship in *minor* versions (1.4 moved the function-group
separator `.` → `__`; 1.5 split the meta-package and moved import paths). Pin it.

### J.2 - The layer that answers "CI/CD for agentic state"

This is the part of the stack worth the most attention, and NVIDIA's published
answer is the **[Data Flywheel Blueprint](https://github.com/NVIDIA-AI-Blueprints/data-flywheel)**:
a continuously-running FastAPI orchestrator over NeMo Customizer (LoRA/SFT),
Evaluator (incl. tool-calling accuracy and LLM-as-judge), Data Store and Deployment
Manager. It replays production traffic logs on a schedule, fine-tunes and evaluates
smaller candidate models, and promotes one when it still clears the accuracy, latency
and cost bar. The Agent Toolkit feeds it: emitted traces carry a `workload_id`, and
the `client_id`+`workload_id` pair selects the training data.

NVIDIA's showcase result is a fine-tuned Llama 3.2 1B reaching tool-calling accuracy
near Llama 3.1 70B - a ~70x size reduction. Treat that as a vendor claim on a
favorable task, but treat the *architecture* as the serious contribution: it is a
concrete, deployable shape for the "how do agents stay current as the enterprise
changes" problem, and there is not much else published at this level of detail.
Note the operational seam - config is static during a run, so a change means
stop, edit, redeploy.

### J.3 - NeMo Framework: the monolith is gone

`NVIDIA/NeMo` no longer means what it used to. The repo now redirects to
[NVIDIA-NeMo/Speech](https://github.com/NVIDIA-NeMo/Speech) and has narrowed to
speech/multimodal; the rest was split across ~27 repos in a new `NVIDIA-NeMo` org
(Megatron-Bridge, RL, Automodel, Run, Curator, Evaluator, Export-Deploy, Skills,
Gym, Nemotron), nearly all Apache-2.0. **[NeMo-Aligner is unmaintained](https://github.com/NVIDIA/NeMo-Aligner)**
as of 2025-05-15 and is replaced by [NeMo RL](https://github.com/NVIDIA-NeMo/RL).
NeMo 2.0 also replaced YAML experiment config with Python config plus NeMo-Run
recipes/executors; NVIDIA documents the migration but has not formally declared the
1.0 YAML path deprecated.

Framework vs microservices is a genuine fork, not a packaging choice: the Framework
is code-level control over arbitrary checkpoints, while Customizer is an API over
*NIM-packaged* models, scoped to LoRA/SFT/DPO/GRPO, that redeploys its output as a
NIM. They version independently.

### J.4 - Nemotron 3 and local runnability

| Tier | Size | Local? |
|---|---|---|
| Nano | 30B total / ~3.5B active, hybrid Mamba-2 MoE, 1M context | **Yes** - official [Ollama library entry](https://ollama.com/library/nemotron-3-nano), 24GB at q4_K_M; third-party GGUFs exist. |
| Super | 120B / 12B active (2026-03-11) | Server-class only: vLLM / SGLang / TensorRT-LLM. |
| Ultra | 550B / 55B active (2026-06-04) | Multi-GPU; the 1M-token NVFP4 context needs Blackwell. |

**The licence is not uniform across the family.** Nano and Super are published
under the NVIDIA Open Model License; the Ultra announcement states **OpenMDW-1.1**
(Linux Foundation) instead. Both claims come from NVIDIA's own posts and were not
reconciled - check the specific model card before depending on either (verify).
All agentic benchmark figures NVIDIA publishes for these (PinchBench 85.6% Super /
91% Ultra, SWE-bench Verified 65-70.4%) are first-party and self-selected.

### J.5 - VSS: the video-corpus RAG architecture

[VSS 3](https://github.com/NVIDIA-AI-Blueprints/video-search-and-summarization)
went GA 2026-06-25 and open-sourced all its microservices; 3.1.0 is in early access.
The pipeline is three layers: real-time vision (DeepStream + RT-DETR/Sparse4D
detection, Cosmos-Embed1 embeddings, a VLM - Cosmos Reason or Qwen3-VL) → a message
broker (Kafka / Redis Streams / MQTT) → behaviour analytics and VLM-verified alerts →
an agent layer exposed over MCP. Audio is not a separate ASR stage in v3; it arrives
via the Nemotron 3 Nano Omni model handling video and audio together.

The retrieval design is the transferable idea. **CA-RAG** stores VLM-generated
captions plus embeddings (Milvus by default) *and* runs an LLM over those captions to
extract entities and relationships into a graph (Neo4j by default, ArangoDB
supported). Flat vector retrieval answers "find the clip"; the caption-derived
knowledge graph is what answers cross-clip and cross-stream questions, and the
"Advanced Retrieval" plan-and-execute mode only runs on a graph backend. That is a
concrete, working answer to what a graph buys you over a video corpus that pure
vector RAG cannot deliver. (Caveat: the CA-RAG database defaults were read from the
current docs but the 3.x top-level architecture page emphasises Elasticsearch, so
the Milvus/Neo4j defaults may describe the 2.x path carried forward - verify.)

### J.6 - What NVIDIA AI Enterprise actually buys

Worth stating precisely, because it is overstated in both directions. It is **not**
GPU compute and it is **not** required to run CUDA on bare metal. It gates: access to
NIM microservices, 9-month production branches and 3-year LTS branches with
monthly/quarterly CVE patching and API stability, SBOM + VEX records + signed
containers, NVIDIA vGPU for Compute, and SLA-backed support (4-hour initial
response). Licensed per GPU. The free path is real and generous for development -
hosted endpoints on build.nvidia.com plus self-hostable NIM containers under free
Developer Program membership - but NVIDIA defines "production" as anything beyond
development, testing, research and evaluation, which includes serving real end users.
NVIDIA also publishes [Enterprise Reference Architectures](https://docs.nvidia.com/enterprise-reference-architectures/index.html)
(32-256 GPU AI factories, plus an AI-Q Research Agent RA and a Secure Agent Workspace
reference design) if a hardware-through-observability blueprint is what is wanted.

### J.7 - Which agent framework to bring (researched 2026-07-29)

The Agent Toolkit is framework-agnostic on paper and all eight supported frameworks
(ADK, Agno, AutoGen, CrewAI, LangChain/LangGraph, LlamaIndex, Semantic Kernel,
Strands) get full tool calling and profiling. Support is **not** evenly deep, though,
and the [framework matrix](https://docs.nvidia.com/nemo/agent-toolkit/latest/components/integrations/frameworks.html)
is the tell:

| Dimension | Coverage |
|---|---|
| Tool calling, profiling | All 8 frameworks |
| Embedder providers | LangChain and LlamaIndex only |
| **Retriever providers** (NeMo Retriever, Milvus) | **LangChain only** |
| Extra LLM providers | LangChain adds Hugging Face; Semantic Kernel is OpenAI-only; Agno marked limited |

Three more signals point the same way. `nvidia-nat-langchain` is a single
distribution covering *both* LangChain and LangGraph, and it is what the
getting-started example installs, while the other frameworks get one extra each and
`crewai`/`adk` carry documented dependency conflicts with `openpipe-art`. Examples
skew to LangChain/LangGraph (3, including a dedicated `langgraph_wrapper` path and a
["Running Existing LangGraph Agents"](https://docs.nvidia.com/nemo/agent-toolkit/latest/run-workflows/existing-agents/langgraph.html)
doc page with no equivalent for the others), and CrewAI ships a plugin with zero
examples. And **LangGraph is the de facto orchestration layer across the blueprint
catalog** - aiq, vulnerability-analysis, ai-virtual-assistant, biomedical-aiq and
retail-shopping-assistant. No blueprint surfaced that is built on CrewAI, Semantic
Kernel, ADK or Agno.

**deepagents specifically sits inside a formal NVIDIA/LangChain partnership**, which
is the part not visible from NVIDIA's docs alone. The
[`langchain-ai/langchain-nvidia`](https://github.com/langchain-ai/langchain-nvidia)
monorepo, developed with NVIDIA, ships `langchain-nvidia-ai-endpoints` (`ChatNVIDIA`,
`NVIDIAEmbeddings`, `NVIDIARerank`), `langchain-nvidia-trt`,
`langchain-nvidia-langgraph` (NVIDIA-optimised execution applied at LangGraph compile
time - parallel independent nodes, speculative execution of both conditional
branches, no change to node logic) and `langchain-nvidia-openshell`, which wires
NVIDIA OpenShell sandboxes to Deep Agents specifically. LangChain joined the Nemotron
Coalition, a joint [enterprise platform announcement](https://www.langchain.com/blog/nvidia-enterprise)
landed around 2026-03, a **NemoClaw** blueprint (Deep Agents Code + Nemotron 3 Ultra
+ OpenShell) was announced 2026-07-08, and deepagents 0.7.0 shipped a built-in
Nemotron 3 Ultra harness profile with NIM attribution. The headline cost figure from
that partnership (0.86 aggregate at $4.48 vs $43.48 for the next closest model) is
announcement-grade and has no verified primary artifact.

**How AI-Q actually composes the two**, which is the reference pattern worth copying:
deepagents owns the inner loop (`create_deep_agent` coordinates subagents itself) and
the Agent Toolkit wraps it as a component of type `deep_research_agent`. NVIDIA
describes its own agents as toolkit-independent with "registration being a thin layer
in `register.py`". The toolkit supplies config-driven composition, MCP wiring, eval,
profiling and tracing; deepagents supplies planning, subagents and context. Models
reach it through the toolkit's `nim` provider resolving via `nvidia_nat_langchain` to
`ChatNVIDIA`, so `langchain-nvidia-ai-endpoints` arrives transitively rather than as a
direct dependency. AI-Q also adds its own middleware (`EmptyContentFix`,
`ToolNameSanitization`, `ModelRetry`) around the run, and post-processes the report
deterministically to verify every citation against sources actually retrieved.

**The pin asymmetry is a live hazard.** AI-Q pins the toolkit exactly
(`nvidia-nat*==1.8.0`) but deepagents as an open floor (`deepagents>=0.6.5`), and
deepagents ships breaking changes at minor versions. A fresh install today resolves
0.7.0, which is not the line AI-Q was built against. Pin deepagents yourself.

**Counterweight, stated plainly:** the Agent Toolkit's own docs never mention Deep
Agents. Support is expressed through the LangGraph/LangChain plugin surface and the
blueprints, and every deepagents-specific package lives in LangChain's org, not
NVIDIA's. So the honest claim is not "NVIDIA supports deepagents first-class"; it is
that LangGraph is NVIDIA's house orchestration layer, deepagents is a harness on top
of it with a partnership behind it, and the coupling is maintained from the LangChain
side. No public source ranks integration effort across frameworks, so "easiest to
integrate" is not a falsifiable claim - it is a reasonable read of where the
investment has gone.

### J.8 - The layer below NeMo: RAPIDS and Morpheus (first-hand, 2026-08)

NeMo is the agent and model half. Where the workload starts as data rather than as a
prompt, two more pieces carry it, and they are the ones an agent stack quietly depends
on when the input is large and tabular.

**RAPIDS** ([`cuML`](https://github.com/NVIDIA/cuml), plus `cuDF` and `cuVS`) is the GPU dataframe and classical-ML layer. It is
what makes "clean and score sixteen million rows before the LLM sees anything" a
half-minute operation rather than an overnight one. `cuML` covers the usual classical
models but **has no IsolationForest**, so unsupervised anomaly work uses
NearestNeighbors distance, DBSCAN or HDBSCAN instead.

[**Morpheus**](https://github.com/nv-morpheus/Morpheus) is NVIDIA's GPU streaming framework for cybersecurity pipelines. The
critical thing to hold, because the naming implies otherwise: **it supplies the
framework, not a model that fits your data.** Its bundled models are each narrow -
ABP is supervised XGBoost over GPU telemetry for crypto-mining, DFP is a per-entity
autoencoder requiring roughly 300+ records per entity - and there is no generic
unsupervised tabular anomaly stage. The documented and intended path is a custom
`SinglePortStage` wrapping your own model, which works cleanly. Treat Morpheus as
pipeline plumbing with GPU-native stages, not as a detection product.

**Both version as CalVer `YY.MM`, not semver.** `25.02` is February 2025. The version
string states its own age, and components across the stack must be pinned to the same
`YY.MM`, because a mismatched pair is a conflict rather than an upgrade. This is also
why installer choice matters: `pip` installing a CUDA-suffixed wheel into a container
built around a pinned RAPIDS will pull its own `cudf` and overwrite the one the
framework depends on. Use the conda channel pinned to the matching version.

The operational specifics for all of the above - including the silent multi-message
parquet corruption in Morpheus's file sink, the one-shot pipeline constraint, the
numba driver-binding requirement, and NIM's readiness-versus-liveness gap - are in
`field-notes.md` rather than here, because they are dated observations rather than
architecture.

**Stance.** Take the Agent Toolkit and Guardrails on their merits - both are
Apache-2.0, both work against non-NVIDIA providers, and the profiler has no real
OSS equivalent. Treat the blueprints as readable reference architectures and
starting points, which is what NVIDIA intends (AI-Q composes with the RAG blueprint;
the biomedical agent is a documented fork of AI-Q). Go into NeMo Platform, NIM
self-hosting and the Data Flywheel with the NVAIE production licence priced in from
the start, not discovered at deployment.

---

## Section K - Agent governance, identity and execution control (researched 2026-09-02)

The lane that answers **"what stops the agent, and who says so"** - distinct from
Section I (which measures what an agent did) and from the prompt-level guardrails in
`NeMo-Guardrails` (which shape what it says). Everything here constrains what an agent
is permitted to *do*, in code, before intent reaches the wire.

All star counts, licenses and push dates in this section come from the GitHub API on
2026-09-02, not from search summaries or README claims.

### K.1 - The organizing principle

**Deterministic interception, not prompt restraint.** The governing check runs in
application code between the model's decision and the tool's execution, so a denied
action is structurally impossible rather than discouraged. Every serious entrant in
this lane agrees on that much; they differ on **where** the interception point sits,
and that difference is the whole design space:

| Enforcement point | What it catches | What it misses |
|---|---|---|
| **In-process hook** (AGT, a harness's PreToolUse hooks) | any tool call routed through the hook | any code path that does not call the hook - a subprocess, a library issuing its own syscalls, a harness that forgets to wire it; and the hook itself, which fails open when it crashes or when its pattern silently matches nothing (principle 18 in `engineering-principles.md`) |
| **Process-separated gateway** (a proxy or sidecar every call must transit) | everything on the wire, whatever the caller | anything that never goes on the wire - local file writes, local exec |
| **OS sandbox** (Seatbelt, Landlock, gVisor, containers) | whatever its profile covers: syscalls, filesystem, network | policy that depends on *semantics* - "this specific customer's record" is not a syscall distinction; and whatever the vendor's profile leaves out - Codex's sandbox modes gate writes but not reads, and Claude Code's sandbox covers shell commands while file tools fall under deny rules (B.2) |

The practical reading: these compose, and any single one of them alone has a named
hole. A hook layer is the cheapest and the leakiest; the sandbox is the only one that
holds against code you did not route.

### K.2 - The standards layer

**OWASP Top 10 for Agentic Applications 2026**, published 2025-12-09 by the GenAI
Security Project's Agentic Security Initiative
([announcement](https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agentic-security-in-the-age-of-autonomous-ai/)):
ASI01 Agent Goal Hijack · ASI02 Tool Misuse · ASI03 Identity & Privilege Abuse ·
ASI04 Agentic Supply Chain Vulnerabilities · ASI05 Unexpected Code Execution ·
ASI06 Memory & Context Poisoning · ASI07 Insecure Inter-Agent Communication ·
ASI08 Cascading Failures · ASI09 Human-Agent Trust Exploitation · ASI10 Rogue Agents.

**Cite it by that name.** There is no OWASP artifact called "the OWASP Agentic Top 10";
that is a colloquial contraction, and a tool using it in its own documentation is a
small signal about how carefully it read the source. Three neighboring OWASP artifacts
are separate documents and are routinely conflated with it and with each other:
*Agentic AI Threats and Mitigations* (a taxonomy, 1.1), *Securing Agentic Applications
Guide* (1.0), and the *OWASP Top 10 for LLM Applications 2026*.

Not verified: a version number or explicit ratification label for the Top 10 - the PDF
itself was not read, only the announcement and resource pages.

**Identity** is converging on SPIFFE/SPIRE workload identity plus the IETF **WIMSE**
work (a WIT-SVID sub-profile for agent identity), with **MCP's OAuth 2.1 + RFC 9728**
profile carrying the delegation half - who the agent is acting *for*. Agent-specific
SPIRE deployment is emerging, not proven in production. This rests on thinner sourcing
than the rest of the section: treat the WIMSE detail as a lead to verify, not a fact.

**Authorization** is being answered with existing policy engines rather than new ones -
OPA/Rego and **Cedar** both appear as agent tool-call authorizers, and AWS has published
a Cedar pattern for least-privilege in multi-agent chains. The notable point for anyone
building here: nothing agent-native has displaced the general-purpose policy engines,
so the reusable skill is Rego or Cedar, not a vendor's agent DSL.

**Protocol governance** now sits in one foundation. The Agentic AI Foundation (a Linux
Foundation directed fund, founded 2025-12-09) hosts MCP, AGENTS.md and goose, and on
2026-10-22 it added Agent Skills, Open Responses, OpenEnv and OpenSandbox (Linux
Foundation release, checked 2026-10-29). MCP's 2026-07-28 specification deprecates Dynamic Client
Registration, Roots, Sampling, Logging and the legacy SSE transport, so servers and
clients built on those features need a migration plan (checked 2026-10-29).

### K.3 - The tools

| Project | License | Enforcement point | What it does | Cautions |
|---|---|---|---|---|
| [agent-governance-toolkit](https://github.com/microsoft/agent-governance-toolkit) | MIT | In-process interception, multi-language | Microsoft's runtime policy layer: intercepts every tool call, message send and delegation before it reaches the wire, evaluating YAML, OPA/Rego or Cedar policy. Python core plus TS/.NET/Rust/Go SDKs, AKS sidecar deployment, six architecture specs covering identity, coordination, execution control, SRE, an MCP security gateway and audit. 6, pushed 2026-09-02. | **Public preview, not GA.** Conformance-test count and OWASP coverage are both self-reported, and it names the OWASP list wrongly. In-process interception governs only paths that call the hook. |
| [abide](https://github.com/coldteadotai/abide) | MIT | Post-edit hook, semantic (Jev) | Checks each Claude Code, Codex or OpenCode edit against rules the agent compiles from AGENTS.md or CLAUDE.md into `.abide/rubric.json`, one Jev probability per rule; 0.8 or above tells the agent to repair, and a Stop hook re-checks the turn. pushed 2026-09-25 (GitHub API, checked 2026-09-25). | Runs after the edit lands and fails open. Sends the user's prompt despite the README; a repo `.env` can redirect the API endpoint; `.abide/` itself is unchecked; vendor-measured edit precision 26%. A model verdict rather than a control, so anything a script can decide stays with a script. |
| [OpenSandbox](https://github.com/opensandbox-group/OpenSandbox) | Apache-2.0 | OS/container isolation | Sandbox runtime for agent workloads, split into a Python/FastAPI control plane (lifecycle) and a Go `execd` daemon (command and file ops inside the sandbox), with session-ID reattachment for stateless workers. Docker local, Kubernetes distributed; `osb` CLI and MCP server; worked examples run Claude Code, Codex CLI, Gemini CLI, OpenCode and others inside it. Cosign-signed releases with provenance; PEP-style OSEP proposal process. 14, Go, pushed 2026-09-02. | Organizational backing behind "opensandbox-group" not established - verify governance before a production dependency. |
| [Shepherd](https://github.com/shepherd-agents/shepherd) | MIT | Syscall (Seatbelt/Landlock) + reversible trace | Makes a run a git-like reversible trace - fork, replay, revert - with syscall-level permissions and outputs held as reviewable proposals. See Section B. | Self-declared alpha; macOS/Linux only. |
| [NVIDIA/OpenShell](https://github.com/NVIDIA/OpenShell) | see repo | Sandboxed shell for agents | Sandbox execution wired to Deep Agents via `langchain-nvidia-openshell`. | Not re-verified this pass. |
| [Omnigent](https://github.com/omnigent-ai/omnigent) | Apache-2.0 | Meta-harness + OS sandbox | Adds bubblewrap/seatbelt sandboxing and stacked cost/access policies above interchangeable harnesses. See Section B. | Self-described alpha. |
| [NeMo-Guardrails](https://github.com/NVIDIA-NeMo/Guardrails) | Apache-2.0 | Conversational I/O rails | Topic boundaries, safety checks and dialogue policy as config. Complementary to this lane, not a substitute - it governs what an agent *says*, not what it *does*. | The one NeMo piece free of NVIDIA licensing. |

### K.4 - Stance

**Compose the layers; do not pick one.** For a workstation running local coding agents, the
practical stack is an in-process hook layer for semantic policy (the things only you can
express, like "never write this path"), an OS sandbox underneath it for everything the
hook cannot see, and an audit trail that survives both. The gap most setups have is the
middle one, because the hook layer is easy and feels sufficient until something spawns a
subprocess.

**Cost governance is unsolved in this lane and belongs in it.** The meta-harness tier
(Section B) treats governance as sandboxing plus tool allowlists and stops there; the
adoption leader auto-retries premium agents with no spend ceiling at all. A budget
ceiling is a governance control, not an accounting nicety, and no entrant here ships one.

---

## Section L - Media production: local speech and podcast pipelines (researched 2026-09-18)

The "documents to two-host audio" system is four stages: ingest, ground, write,
render. Every published reference architecture has the same shape; they differ in
who writes the dialogue and what renders it.

| Reference | Write stage | Render stage | What transfers | Link |
|---|---|---|---|---|
| NotebookLM Audio Overviews (Google) | undocumented | one audio model, up to 2 min multi-speaker per pass, disfluencies trained in | the render target: dialogue as one pass, not stitched turns | [DeepMind 2024-10-30](https://deepmind.google/blog/pushing-the-frontiers-of-audio-generation/) |
| NVIDIA pdf-to-podcast | outline, then segments, then transcript per segment in parallel, then stitch | ElevenLabs | the outline-first decomposition; monologue and dialogue as separate workflows | [repo](https://github.com/NVIDIA-AI-Blueprints/pdf-to-podcast) |
| PodAgent (ACL 2025) | Host, Guest and Writer agents interact, then a script is derived | CosyVoice with per-line style instructions | profiled hosts interacting beats one model writing the dialogue straight (measured) | [paper](https://aclanthology.org/2025.findings-acl.1226/) |
| MOSS-TTSD (2026-03) | n/a | one model, 1 to 5 speakers, 60 min single pass, cloning | the three dialogue-TTS failure modes: turn-taking, cross-turn consistency, long-form stability | [repo](https://github.com/OpenMOSS/MOSS-TTSD) |
| Open Notebook / podcast-creator | LangGraph nodes: `generate_outline` then `generate_transcript`, both written to disk as JSON before any audio | per-speaker TTS clips in batches of 5, then concatenated | the episode-profile versus speaker-profile split, and the outline as an inspectable artifact | [repo](https://github.com/lfnovo/podcast-creator) |
| Podcastfy | one LLM pass per content chunk, prior transcript resent as context | provider TTS per turn, pydub concatenation with no gap inserted | length controlled by chunk count rather than word count; named sections as one config line | [repo](https://github.com/souzatharsis/podcastfy) |

### What the published pipelines teach (verified 2026-09-18)

**Outline first, then prose.** Every system that measured itself against a single
pass writes an outline as a separate step. PodAgent's Host-agent produces guest
profiles plus an interview outline of five sub-questions, and the Guest-agents
answer that same outline in parallel rather than taking turns, so turn order is
decided at the later Writer pass instead of during generation ([arXiv
2503.00455](https://arxiv.org/abs/2503.00455), 2025-03-01). podcast-creator runs
`generate_outline` and `generate_transcript` as distinct LangGraph nodes and writes
`outline.json` before the script exists ([repo](https://github.com/lfnovo/podcast-creator),
read 2026-09-18).

**The writer pass is one instruction.** PodAgent's Writer-agent compiles the
parallel answers into one script, "eliminating redundancy while preserving the
distinct viewpoints". That instruction is what separates the pipeline that won
from the single-pass GPT-4 baseline it beat on information density (+0.558 to
+0.707) and on LLM-judge overall score (+1.4 to +1.75) ([arXiv 2503.00455](https://arxiv.org/abs/2503.00455)).

**Models ignore word counts, so control the number of passes.** Podcastfy had a
`word_count` field and removed it in v0.3.6 (2024-11-13) when chunked longform
landed; length is now `max_num_chunks` (default 7) and `min_chunk_size` (default
600 characters) ([usage docs](https://github.com/souzatharsis/podcastfy/blob/main/usage/how-to.md),
read 2026-09-18). NotebookLM ships Shorter / Default / Longer presets and publishes
no duration behind them ([help page](https://support.google.com/notebooklm/answer/16212820),
read 2026-09-18). Open Notebook uses `num_segments` (default 5, range 3-20) plus a
target length stated in prose. No shipped system accepts a target duration.

**Named sections are the cheapest structural lever.** Podcastfy's
`dialogue_structure` is a list of section names the model must follow, defaulting
to `["Introduction","Main Content Summary","Conclusion"]`. Replacing that one line
with `["Opening Statements","Rebuttals","Closing Remarks"]` converts the episode
into a debate, and the project ships exactly that as a worked config
([conversation_custom.md](https://github.com/souzatharsis/podcastfy/blob/main/usage/conversation_custom.md),
read 2026-09-18).

**Under-specify the personas.** NotebookLM's hosts carry no names and no heavy
character description, and are instructed not to say their names; disagreement is
tuned in deliberately, because two hosts who always agree are not interesting to
listen to ([Latent Space interview with the NotebookLM team](https://www.latent.space/p/notebooklm),
2024-10-25).

**Disfluency belongs to the render stage.** A banter pass over a sterile script is
a documented stage in NotebookLM, but the micro-interjections, overlaps and pauses
themselves are not in the transcript: they come from the audio model, which
generates up to two minutes of multi-speaker dialogue per pass with overlapping
speech and trained-in disfluencies ([Latent Space](https://www.latent.space/p/notebooklm),
2024-10-25; [DeepMind](https://deepmind.google/blog/pushing-the-frontiers-of-audio-generation/),
2024-10-30). A per-turn render with a constant gap cannot reproduce them, so
writing stage directions into a stitched script is the wrong layer.

**Script quality is measurable without a reference text.** PodAgent's automatic
metrics need no gold script: Distinct-N normalized over a 100-token sliding window,
MATTR (mean type-token ratio over a sliding window), Semantic-Div (cosine distance
between BERT embeddings of segments) and information density as Shannon entropy.
Its LLM-judge rubric scores coherence, engagingness, diversity, informativeness and
speaker-diversity on a -3 to +3 comparative scale ([arXiv 2503.00455](https://arxiv.org/abs/2503.00455)).
These run over any script file, which is what makes a slop gate falsifiable rather
than a matter of taste.

**Two profiles, not one config blob.** Open Notebook separates an episode profile
(speaker-config reference, outline model, transcript model, default briefing,
`num_segments`, language) from a speaker profile (`tts_provider`, `tts_model`, and
per speaker a name, `voice_id`, backstory and personality). Unset per-speaker
fields fall back to the profile level, with one exception: a per-speaker
`tts_config` **replaces** the profile-level config entirely rather than merging
([podcast-creator README](https://github.com/lfnovo/podcast-creator), read
2026-09-18). A cascade where one key replaces while its siblings merge is a trap
worth designing out of a new config surface.

**Ingestion in the shipped systems.** Open Notebook delegates extraction to
content-core, with Docling as the default engine and a lightweight path of pypdf
for PDFs and trafilatura for web pages; image types route through Docling OCR,
which is significantly slower and needs an extra ([content support](https://www.open-notebook.ai/features/content-support)
and [issue 1104](https://github.com/lfnovo/open-notebook/issues/1104), read
2026-09-18).

**Podcastfy's failure modes are the ones to design against.** Longform resends the
whole prior transcript with every chunk, so token cost grows quadratically with
episode length. Transcripts above 4096 characters fail against OpenAI TTS; the
issue is open and the proposed fix is chunk-then-stitch before synthesis
([issue 19](https://github.com/souzatharsis/podcastfy/issues/19), read 2026-09-18).
Speaker tags are recovered from free text by regex, and a malformed tag silently
drops the turn instead of raising. The quadratic-token and silent-drop points come
from a third-party audit of version 0.4.1 rather than from upstream, so treat them
as reported rather than confirmed.

**Stance.** No agent framework is warranted for the write stage. Two persona
contexts alternating turns over one loaded model, with a reusable prompt cache, is
a few dozen lines on mlx-lm or any chat API; CrewAI-class orchestration adds a
dependency and an LLM abstraction that does not speak local runtimes natively, for
a loop that has no branching. Ground by context-stuffing until the corpus outgrows
the window (262K on Gemma 4 and Qwen3.8), then add sqlite-vec or LanceDB, both
Apache-2.0. Avoid mlx-embeddings (GPLv3 per PyPI 0.1.0, 2026-03-24) and pymupdf4llm
(AGPL) in a repo that may go public.

| Layer | Pick on Apple Silicon | License | Verified |
|---|---|---|---|
| Ingest | Docling for layout, pypdf when text is enough, trafilatura for HTML | MIT, BSD-3, Apache-2.0 | 2026-09-18 |
| Write | [mlx-lm](https://github.com/ml-explore/mlx-lm) v0.31.3 (2026-04-22), documented reusable prompt cache for multi-turn; 4-bit Qwen3.8-27B loads text-only under stock mlx-lm, Gemma 4 31B mlx-community repos are mlx-vlm conversions | MIT | 2026-09-18 |
| Render | [mlx-audio](https://github.com/Blaizzy/mlx-audio) v0.5.4 (2026-09-14); Kokoro for speed, MOSS-TTSD for Apache-licensed multi-speaker with cloning, Higgs for quality under a non-Apache weight license | MIT runtime, see catalog for weights | 2026-09-18 |
| Whole app | none runs on MLX; Open Notebook (MIT) and SurfSense (custom license) are Docker web apps around Ollama and replace a pipeline rather than extend one | | 2026-09-18 |

Measured on mlx-audio on 2026-09-18 (Apple Silicon, 64GB, one two-host script):
Higgs Audio v2 3B q8 renders at RTF 0.35 warm, Kokoro 82M at RTF 0.066 on the same
input, so Kokoro is roughly five times faster. The MLX buffer cache is uncapped by
default and reached 50GB of resident memory on that 3B model during a single
render; `mx.set_cache_limit` bounds it and should be set before any long render on
a shared-memory machine. Details in [`field-notes.md`](field-notes.md).

Ollama v0.19 (2026-03-30) moved Apple Silicon inference to an MLX backend for
safetensors models, so the old speed argument for choosing Ollama over mlx-lm is
gone; the remaining difference is a server versus a library. No published benchmark
ranks open models on two-host dialogue writing; EQ-Bench's creative and longform
boards are the nearest proxy and are judge-scored.

---

## Section M - Knowledge graphs and markdown knowledge bases as agent grounding (researched 2026-10-29)

A knowledge base an agent reads is a context engine: it decides what the model sees before it reasons.
Three choices shape such a knowledge base: what kind of graph (if any) to build, where to store it, and how to keep the markdown underneath it healthy.
Repo facts (stars, license, last push, archived state) are stored in `github.tsv` and shown in `link-ledger.md` with their API check date.

### M.1 - The first decision: link graph, extracted graph, or no graph

| Approach | What builds it | Cost to build and update | Wins on | Loses on |
|---|---|---|---|---|
| **Deterministic link graph** | a parser over links, embeds, frontmatter and headings the authors already wrote | seconds, offline, no model; rebuild is exact and diffable | navigation, backlinks, "what depends on X", section-level retrieval, provenance | relations nobody wrote down |
| **LLM-extracted entity graph** (GraphRAG family) | a model reading every chunk and emitting entities and relations | model calls per chunk; reported at 10-50x vector RAG for indexing (blog-grade estimates, 2026), and community summaries are not recomputed on incremental update in most implementations | multi-hop questions and corpus-wide aggregation | single-fact lookup, cost, entity duplication, extraction noise |
| **Vector or hybrid (BM25 + vector) retrieval, no graph** | an embedding pass | cheap; re-embed on change | single-hop fact lookup | cross-document reasoning |

The evidence favors starting without an extracted graph.
GraphRAG-Bench (arXiv 2506.05690, v3 2026-02-22) found that GraphRAG "frequently underperforms vanilla RAG on many real-world tasks" and helps mainly on multi-hop and aggregation questions (abstract checked 2026-10-29).
Secondary summaries of the same benchmark report query cost of roughly 38.7k prompt tokens per question for local graph search and 331k for global search against under 1k for vector RAG (not checked against the paper body).
No published head-to-head between a deterministic link graph and an LLM-extracted graph over a personal or project knowledge base was found (2026-10-29).
House practice is to build the deterministic graph first, because it is free and exact, and then add hybrid search over the same sections.
Model extraction is added only for a measured gap, with extracted edges labeled as such and never mixed silently with authored links.

### M.2 - Graph storage

| Engine | Mode | License | Query language | Status and cautions | Repo |
|---|---|---|---|---|---|
| SQLite + FTS5 (pattern) | embedded, one file | public domain | SQL with recursive CTEs; FTS5 for text | Enough for link graphs well beyond a large vault; no server, rebuildable from the markdown, ships with every Python. The default for a deterministic graph. | [docs](https://www.sqlite.org/fts5.html) |
| Kuzu | embedded | MIT | openCypher | **Archived 2025-10-10** (final release v0.11.3) after Apple acquired the team. Pin or migrate; do not start new work on it. | [repo](https://github.com/kuzudb/kuzu) |
| LadybugDB | embedded | MIT | openCypher | The main Kuzu fork, v0.19.1 by 2026-08-12 and active; fork funding risk is real. Other forks: Bighorn, RyuGraph, NeuG. | [repo](https://github.com/LadybugDB/ladybug) |
| DuckPGQ | embedded (DuckDB extension) | MIT | SQL/PGQ | Graph queries inside DuckDB; fits analytical workloads already on DuckDB. | [repo](https://github.com/cwida/duckpgq-extension) |
| ArcadeDB | embedded (JVM) and server | Apache-2.0 | SQL, openCypher, Gremlin, GQL syntax (vendor claim) | Fully open including clustering; vendor-authored comparisons dominate search results, so verify claims yourself. | [repo](https://github.com/ArcadeData/arcadedb) |
| Apache AGE | Postgres extension | Apache-2.0 | openCypher inside SQL | The pick when Postgres is already the system of record. | [repo](https://github.com/apache/age) |
| Neo4j Community | server | **GPL-3.0** | Cypher | Clustering and embedded mode are Enterprise-only (commercial). The most documented option; GPL obligations apply to distribution. | [repo](https://github.com/neo4j/neo4j) |
| Memgraph | server, in-memory | **BSL 1.1** (source-available) | Cypher; GQL via a translator | Not OSI-approved; check the BSL additional-use grant before production. | [repo](https://github.com/memgraph/memgraph) |
| FalkorDB | server (Redis module) | **SSPL** | openCypher | Not OSI-approved (see Licensing & security cautions). | [repo](https://github.com/falkordb/falkordb) |
| SurrealDB | embedded and server | **BSL 1.1** | SurrealQL | Multi-model; source-available. | [repo](https://github.com/surrealdb/surrealdb) |

ISO GQL (ISO/IEC 39075) is not yet native in the open engines as of 2026-10; translators and partial syntax support exist.
Independent benchmarks at agent scale are thin: the 2026 comparisons found are either vendor-run or single-author, so measure on your own graph before choosing on speed.

### M.3 - Turning markdown into a graph

Parse, in order of value, links (wikilinks and markdown links, with heading and block anchors), embeds, frontmatter properties (aliases, tags, dates, type), and the heading tree.
Address content at **section level**: a heading and its body is the retrieval unit, and a link to `Page#Heading` resolves to that section, so an agent loads one section instead of a whole file.

Each of these failure modes is documented in at least one tool's issue tracker or release notes (2026).

- **Ambiguous titles.** Two notes with one title make a link ambiguous; report it in a health check rather than guessing.
- **Renames** break every inbound link unless references are rewritten or the old title is kept as an alias.
- **Forward references** to notes that do not exist yet need deferred resolution.
- **Links inside code spans and fences** are examples, not links; strip code before parsing.
- **Truncated or normalized identifiers** collide; equivalent filenames (case, Unicode normalization) must be rejected at write time.

House practice is one stdlib parser that writes to SQLite + FTS5, deterministic and offline.
It offers graph queries for backlinks, neighbors, orphans and unresolved links, a health report for ambiguity, and a rebuild that produces the identical index from the same files.

| Tool | What it is | License | Repo |
|---|---|---|---|
| Basic Memory | markdown files plus a SQLite index served over MCP; section indexing and range reads since v0.24 | **AGPL-3.0** | [repo](https://github.com/basicmachines-co/basic-memory) |
| memsearch | markdown as the source of truth with a rebuildable Milvus Lite index, hybrid BM25 + vector | MIT | [repo](https://github.com/zilliztech/memsearch) |
| markdown-oxide | a language server for markdown knowledge bases (links, references, completion) | Apache-2.0 | [repo](https://github.com/Feel-ix-343/markdown-oxide) |

Many Obsidian MCP servers expose backlinks, N-hop neighbors, orphans and unresolved links over a vault (at least eight seen 2026-10), and none is established enough to recommend by name.
An MCP server reading a private vault is untrusted code with read access to all of it.

### M.4 - The GraphRAG family

| Project | License | Status (2026-10) | Incremental update | Repo |
|---|---|---|---|---|
| Microsoft GraphRAG | MIT | v3.3.0, active | limited; the cheaper LazyGraphRAG is reported to ship in Microsoft products rather than the library (unverified) | [repo](https://github.com/microsoft/graphrag) |
| LightRAG | MIT | active | insert and delete supported; default in-memory stores are test-only; endpoints unauthenticated unless configured; see its record in `advisories.md` | [repo](https://github.com/HKUDS/LightRAG) |
| HippoRAG 2 | MIT | alpha (2.0.0a5) | skips known passages; delete by source | [repo](https://github.com/OSU-NLP-Group/HippoRAG) |
| Graphiti | Apache-2.0 | v0.31.2 (2026-10-20), active | built for real-time incremental updates, temporal edges | [repo](https://github.com/getzep/graphiti) |
| Cognee | Apache-2.0 | v1.6.1 (2026-09-24); the production Postgres graph store is a commercial product | yes | [repo](https://github.com/topoteretes/cognee) |
| KAG | Apache-2.0 | last release v0.8.0 (2025-06-27); slowed | - | [repo](https://github.com/OpenSPG/KAG) |
| nano-graphrag | MIT | inactive (last release about two years old) | - | [repo](https://github.com/gusye1234/nano-graphrag) |

Failure modes to plan for: entity duplication when merging is exact-match only, noisy or contradictory extracted triples, silent failure of global search on sparse graphs, and stale communities after incremental updates.
Extraction needs a strong model; weaker local models time out or loop.

### M.5 - Curating a markdown knowledge base as grounding context

These are the practices that keep a knowledge base useful to agents over months, drawn from house practice and the sources cited.

- **Separate sources from synthesis.** Raw sources (transcripts, exports, tickets) stay immutable; the agent writes summaries and topic notes that cite them. The LLM-wiki pattern ([Karpathy's gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f), 2026-04-04) uses the same split: raw sources, an LLM-maintained wiki, and a schema file.
- **A contract at the root.** One rules file states the layout, naming, what goes where, and which files are generated; scaffolding and a linter enforce it, so conformance is checked by a script rather than remembered.
- **Flat and dated.** A flat folder with predictable names beats deep hierarchies for both people and parsers. Logs (meetings, chat, decisions) are append-only with dated headings, so a section is addressable by date and a sweep can find everything since the last entry.
- **An index and a log.** An index file lists every note with a one-line summary and is read first; an append-only log records each ingest and edit with a consistent prefix so it can be searched.
- **Every claim is dated and sourced.** An undated claim cannot be told apart from a stale one.
- **Every category has an exit.** A section whose items never retire grows past any size budget while every check passes; give each category a condition for moving to an archive, and treat size budgets as a backstop.
- **Compaction keeps a fixed format and a backup.** Long logs are compacted into a fixed summary shape (takeaways, decisions, open questions, actions) after the original is backed up outside the knowledge base, and the result is verified against the original.
- **One writer per file kind.** Durable learnings reach their file through one routine, so two agents cannot write competing versions of the same fact.
- **Lint on a schedule.** Broken and ambiguous links, orphans, missing frontmatter, contradictions and superseded claims are reported by a script; the model or a person rules on each.
- **Always-loaded files stay short.** Gloaguen et al. (arXiv 2602.11988, 2026-02-12) found repository context files gave no significant task-success gain and raised cost by over 20%, and generated overviews mostly duplicated existing docs. Keep what loads on every request to rules and pointers, and load sections just in time, which is also Anthropic's guidance ([context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)).
- **Compaction loses rules.** "Compaction Cliff" (arXiv 2608.22752, CIKM 2026) measured one coding agent's built-in compaction keeping 53% of safety rules after one round and 10% after five, so rules that must survive a long session belong in a file the harness reloads, not only in the conversation.
- **Content is data, not instructions.** Memory and knowledge-base poisoning is measured and serious: PMPA (arXiv 2609.13889, 2026-09-12) reported cross-session attack success of 81.7% against a coding agent's persistent memory, and signing entries at write time (SMSR, arXiv 2606.12703) cut unsigned-injection success to 0% in its tests. Treat anything ingested from outside as untrusted, and scrub secrets and private identifiers at write time when a bundle leaves its home.
- **Portable bundles have no standard yet.** AGENTS.md (instructions), Agent Skills (procedures) and MCP (access) are open standards under the Agentic AI Foundation; no open format for a portable knowledge bundle existed as of 2026-10, so an export is a cleaned copy with its own manifest.

### M.6 - File-based agent memory

Harness memory is now mostly plain files: Claude Code loads CLAUDE.md files and the first 200 lines or 25 KB of an auto-memory index from a per-project folder; Anthropic's API memory tool (`memory_20250818`) is a client-side file directory; Codex keeps opt-in memories under its home folder (docs checked 2026-10-29).
The one benchmark comparing a files-only agent with graph memory (Letta, 2025-08, LoCoMo: 74.0% against 68.5% reported for Mem0's graph variant) is vendor-run and not like-for-like.
The defensible claim is therefore narrow: how an agent manages its context matters at least as much as the retrieval mechanism.
A memory index loaded every session is truncated past its limit, so keep one line per memory and move detail into the memory file.

---

## Recommended architectures by use case

### 1) Fastest path to a serious OSS agent stack
LangGraph **or** LlamaIndex (orchestration/KB) · Mem0 **or** Graphiti (memory) ·
Firecrawl + Docling (ingestion) · Ollama (local) · OpenAI/Anthropic/Gemini (cloud fallback).

### 2) Memory-first stack
Letta + Graphiti **or** Mem0 · Docling + Firecrawl (durable external knowledge) ·
CopilotKit if a user-facing app is needed.

### 3) All-in-one local/private stack
AnythingLLM (turnkey private) · Ollama (serving) · Docling (documents) ·
add Mem0 only if built-in memory is insufficient.

### 4) Retrieval-heavy / document-heavy stack
LlamaIndex **or** Haystack · Docling · LightRAG **or** RAGFlow ·
optional Graphiti if entity/time memory matters.

### 5) In-app copilot stack
CopilotKit frontend · backend: LangGraph / PydanticAI / OpenAI Agents SDK / Agno ·
memory: Mem0 **or** Letta.

### Local-first evaluation note
For "local Ollama by default, optional cloud escalation," favor components that
are: clean with **OpenAI-compatible local endpoints**, free of a paid hosted
control plane, composable with local storage/memory/graph, and friendly to
**incremental adoption**. Strongest practical stacks:

1. LangGraph + Ollama + Mem0/Graphiti + Docling/Firecrawl
2. Google ADK + Ollama + local SQLite/Postgres/graph layer
3. Letta + Ollama + external ingestion layer
4. LlamaIndex + Ollama + graph/vector KB
5. AnythingLLM for the fastest path to a serious local/private app

---

## Current shortlist (merged, post-second-pass)

- **Frameworks / runtimes:** LangChain · LangGraph · LlamaIndex · Agno · Letta · CrewAI · Semantic Kernel · Microsoft Agent Framework · Google ADK · PydanticAI · Haystack
- **Harnesses (agents you operate):** Claude Code · deepagents · Pi · OpenAI Codex CLI · goose · OpenClaw. Pick a harness when the job is to *operate* an agent; pick a framework when the job is to *build* one into a product. deepagents straddles both, being LangChain's opinionated harness over `create_agent`/LangGraph.
- **Platform-style builders:** Dify · FastGPT · AnythingLLM · RAGFlow
- **Memory:** Letta · Mem0 · Graphiti · MemOS · Cognee
- **Context / KB:** LlamaIndex · Haystack · LightRAG · RAGFlow · txtai
- **Ingestion:** Firecrawl · Crawl4AI · Docling
- **Local/private assistant:** Letta · Nanobot · AnythingLLM · Google ADK + Ollama · LangGraph + Ollama
- **Tuning / optimization:** Unsloth · Agent Lightning · OpenPipe ART · Molt · TRL · PEFT · Axolotl
- **Frontend:** CopilotKit
- **Codebase knowledge graph:** graphify · codegraph · codebase-memory-mcp (see Section I.1 for how to rank them)
- **Agent evals / red-team:** Giskard v3 · deepeval · Opik · NeMo Agent Toolkit (profiling + eval over an existing framework) · NeMo Guardrails (I/O rails)
- **NVIDIA stack:** NeMo Agent Toolkit · NeMo Guardrails · Nemotron 3 Nano (local) · Data Flywheel + VSS as reference architectures (see Section J for the licence boundary)

---

## Licensing & security cautions

- **Dify** - Dify Open Source License (Apache-based + additional conditions).
- **FastGPT** - Apache-based + additional conditions for some commercial/SaaS use.
- **Mastra** - dual: Apache-2.0 core + enterprise-licensed `ee/`.
- **FalkorDB** - **SSPL** (not OSI-approved).
- **Firecrawl** - AGPL-3.0; may be a blocker for some orgs.
- **Crawl4AI** - recent security hotfix replacing `litellm` with `unclecode-litellm` after a PyPI supply-chain compromise; keep included but pin current versions.
- **AutoGen** - flagged for new adoption (maintenance mode).
- **Nanobot / OpenHarness** - promising but young; higher change-rate components.
- **Aiden** - AGPL-3.0 core with paid commercial relicensing for closed-source use; a dual-license trap, not a permissive dependency (verified 2026-07-27).
- **WrenAI** - licensed by path (Apache-2.0 code, CC-BY-4.0 docs) with AGPL-3.0 pre-staged in the LICENSE for future modules that do not exist yet. Re-read the path→license table before depending on any new subtree (verified 2026-07-27).
- **repowise** - AGPL-3.0.
- **GitVizz** - **no license file** (all rights reserved by default) and untouched since 2026-02-12. Do not vendor (verified 2026-07-27).
- **Codebase knowledge-graph tools generally** - the category's star counts are inflated and every performance number is first-party; see Section I.1's shared caveats before citing any of them. No security advisories were open against graphify, codegraph, codebase-memory-mcp, code-review-graph, herdr or aiden as of 2026-07-27, and all ship auditable source.
- **Vendor monorepo drops** (Grok Build) - published as squashed periodic exports, so issues and PRs land against a snapshot rather than live history. Fine to use, wrong to treat as a community project you can upstream to.
- **NVIDIA NeMo Platform / NIM self-hosting** - free for development, testing, research and evaluation; **production requires an NVIDIA AI Enterprise licence**, where NVIDIA defines production as anything else, including serving real end users. Budget it before the pilot, not after (verified 2026-07-28).
- **NVIDIA Blueprints** - the repo source is Apache-2.0, but the NIM containers a blueprint pulls carry NVIDIA's own terms. "Apache-2.0 blueprint" does not mean an Apache-2.0 deployment (verified 2026-07-28).
- **Nemotron 3** - the family licence is **not uniform**: Nano and Super under the NVIDIA Open Model License, Ultra announced under OpenMDW-1.1. Check the individual model card (verified 2026-07-28).
- **NeMo Agent Toolkit** - renamed twice (`agentiq`→`aiqtoolkit`→`nvidia-nat`) with all compatibility shims deleted, and breaking changes ship in minor releases. Pin the version; treat any pre-2026 tutorial as stale (verified 2026-07-28).
- **NeMo-Aligner** - unmaintained since 2025-05-15; superseded by NeMo RL. Do not start new work on it (verified 2026-07-28).
- **Higgs Audio weights** - repo code is Apache-2.0 but v2 weights are under a Llama-3-derived community license and v3 weights are research and non-commercial with a creator grant. Read the HF LICENSE file, not the repo badge (verified 2026-09-18).
- **pymupdf4llm** - AGPL-3.0 or Artifex commercial, and its PyMuPDF Layout dependency went AGPL at 1.28.2 (verified 2026-09-18).
- **marker-pdf** - Apache-2.0 code, RAIL-M weights gated above USD 5M funding or revenue (verified 2026-09-18).
- **MinerU** - Apache-2.0 plus MAU and revenue terms; the model card still says agpl-3.0 (verified 2026-09-18).
- **mlx-embeddings** - GPLv3 per PyPI (verified 2026-09-18).
- **SurfSense** - custom license with a proprietary subtree (verified 2026-09-18).
- **Security record.** `advisories.md` lists every published GitHub security advisory and every vetted incident per catalogued tool, generated by `ledger.py`. `ledger.py advisories --pattern` names tools with any supply-chain or malicious-release incident, or three or more critical/high advisories, in 24 months. That rule surfaces candidates, and a high count can also mean open disclosure. Each "avoid" verdict is therefore written in these cautions with its date and evidence, and the tool gains the catalog's `avoid` tag.
- **LiteLLM** - malicious `litellm` 1.82.7 and 1.82.8 were published to PyPI on 2026-03-24 and quarantined after about 40 minutes (maintainer postmortem); CVE-2026-42208 joined CISA's Known Exploited Vulnerabilities list on 2026-05-08. Pin versions and verify hashes (checked 2026-10-29).
- **Langflow** - CVE-2026-33017 joined CISA's Known Exploited Vulnerabilities list on 2026-03-25, and the project published 30 critical or high advisories in the 24 months to 2026-10 (checked 2026-10-29).
- **Graph and memory store licenses** - Memgraph and SurrealDB are BSL 1.1, Neo4j Community is GPL-3.0 with clustering Enterprise-only, Basic Memory is AGPL-3.0, Arize Phoenix is Elastic License 2.0, and Langfuse is MIT except its `ee/` folders (license files read 2026-10-29).
- **Archived or closed (GitHub API, 2026-10-29)** - Kuzu (archived 2025-10-10; LadybugDB is the main fork), Airweave, Acontext, Supertonic (moved to an archive organization), and Daytona, whose public repo is archived with no license after the project closed its production code.
- **Avoid (verdict 2026-10-29, tagged `avoid` in the catalog).** **OpenClaw** - 263 critical or high advisories in the 24 months to 2026-10, on top of the over-privileged design noted in Section B. **LiteLLM** - a malicious PyPI release (2026-03-24) and a known-exploited CVE (CVE-2026-42208, CISA KEV 2026-05-08) alongside 12 critical or high advisories; if a gateway is required, pin an audited version, verify hashes and keep it off shared networks. **Langflow** - 30 critical or high advisories, one exploited in the wild (CVE-2026-33017, CISA KEV 2026-03-25).
- **Caution (verdict 2026-10-29, no tag).** Each published a dense run of critical or high advisories in 24 months without a supply-chain incident: **ArcadeDB** (30), **SurrealDB** (19), **FastGPT** (13), **Omnigent** (13 between 2026-06 and 2026-10, concentrated in its sandbox, policy and authentication layers - the features it is adopted for), **LightRAG** (12), **Paperclip** (9) and **RAGFlow** (8). Pin versions, keep their servers off untrusted networks, and re-read `advisories.md` before upgrading.
- **No license** - 33 catalogued repos publish no license, so they are all rights reserved however popular; `link-ledger.md` marks each as `NO-LICENSE`. Their code can be read but not copied.

---

## Adjacent infrastructure (not agent frameworks)

Useful but sit *adjacent* to the core agent stack: **Ollama** (serving),
**LMCache** (inference cache), **OpenRouter** (cloud routing), **Brave Search API**
(search), **Firecrawl** (web input), **Docling** (parsing), **FalkorDB** (graph DB),
**Spanner Graph** (managed property graph; GA January 2025, verified 2026-07-27 - not
a separate product but a graph schema mapped onto existing Cloud Spanner tables,
queried with ISO GQL and callable from SQL via `GRAPH_TABLE`, so relational and graph
workloads keep the same consistency guarantees; LangChain integration targets GraphRAG.
Managed and proprietary, so it carries Google Cloud lock-in that the OSS graph stores
here do not),
**Unsloth** (tuning), **Apify Actors** (automation substrate), **Bright Data MCP**
(web data), **DeepTeam / Strix** (red-team), **Qwen 3-TTS / Chatterbox** (voice),
**Deepface** (face recognition), **SIE** (Superlinked Inference Engine - one
self-hosted cluster serving 100+ open models on demand behind a single API covering
retrieval, doc→markdown, structured output, safety and agent loops; Apache-2.0
2026-07-27 - the consolidation play once a stack has a separate server per model,
heavier than Ollama and aimed at a cluster, not a laptop. Re-verified 2026-08-14:
now Superlinked's flagship - VectorHub is deprecated in its favor - and the scope
statement widened to embeddings, reranking, OCR, extraction and document
processing behind the one endpoint; license re-verify pending, the repo page was
unreachable this pass).

## Still un-normalized (verify before relying on)

TEN · Notte · Mino · PageIndex · Byterover · Dolphin PDF parsing · Data Formulator ·
TensorLake · Klaus Kode · Laptop RAG · Agentic Document Extraction (ADE) ·
SIM workflow builder. (Also the [To-triage list](reference-catalog.md#to-triage--unverified).)

*Normalized 2026-07-27: "GenBI Wren" resolved to [WrenAI](https://github.com/Canner/WrenAI), now in Section D.*

---

*Bottom line: pick a framework + memory + context + ingestion + model strategy -
not one monolith. The exhaustive URL set is in [`link-ledger.md`](link-ledger.md);
the categorized index is in [`reference-catalog.md`](reference-catalog.md).*
