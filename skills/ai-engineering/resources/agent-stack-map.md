---
name: agent-stack-map
description: Opinionated, comparison-table map of the modern OSS agent stack - frameworks, harnesses, memory, retrieval/context, skills, ingestion, tuning/RL, self-improvement, and the NVIDIA NeMo stack - with recommended architectures and a current shortlist. The analytical core of the ai-engineering skill.
updated: 2026-07-29
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

| Project | Stars | License | Stack role | What it does | Cautions | Status | Repo |
|---|---:|---|---|---|---|---|---|
| LangChain | 133k | MIT | General agent framework | LLM apps/agents with the largest integration ecosystem. | Abstract/heavy; long-term memory needs extra design. | Include | [repo](https://github.com/langchain-ai/langchain) |
| LangGraph | 28.9k | MIT | Stateful orchestration runtime | Durable, explicit-state graphs for long-running agents; HITL. | Lower-level; more upfront architecture. | Include | [repo](https://github.com/langchain-ai/langgraph) |
| LlamaIndex | 48.5k | MIT | Data + agent framework | Agents over documents, indices, graphs, retrieval. | Broad surface; many packages. | Include | [repo](https://github.com/run-llama/llama_index) |
| CrewAI | 48.5k | MIT | Multi-agent framework | Role/task/flow multi-agent orchestration. | Some enterprise features skew commercial. | Include | [repo](https://github.com/crewAIInc/crewAI) |
| Agno | 39.3k | Apache-2.0 | Agent framework + runtime | Agents/teams/workflows/memory/knowledge + AgentOS. | Some value sits in hosted control plane. | Include | [docs](https://docs.agno.com/introduction) |
| Semantic Kernel | 27.7k | MIT | Enterprise orchestration SDK | Model-agnostic agents/plugins/memory/process; multi-language. | Heavier enterprise framing. | Include | [repo](https://github.com/microsoft/semantic-kernel) |
| Haystack | 24.8k | Apache-2.0 | Retrieval + orchestration | Production RAG / retrieval / agent pipelines. | Retrieval-first; some setups verbose. | Include | [repo](https://github.com/deepset-ai/haystack) |
| OpenAI Agents SDK | 20.7k | MIT | Multi-agent workflow SDK | Tools, sessions, tracing, handoffs, HITL; provider-agnostic. | Less opinionated on long-term memory. | Include | [repo](https://github.com/openai/openai-agents-python) |
| PydanticAI | 16.2k | MIT | Type-safe agent framework | Strongly typed agentic apps; strong provider support incl. Ollama. | Not batteries-included on memory. | Include | [repo](https://github.com/pydantic/pydantic-ai) |
| smolagents | 26.5k | Apache-2.0 | Minimal agent framework | "Agents that think in code"; model/tool agnostic. | Assemble persistence/memory yourself. | Include | [repo](https://github.com/huggingface/smolagents) |
| Strands Agents | 5.6k | Apache-2.0 | Model-driven SDK | Clean provider model; built-in MCP; local/cloud switching. | Smaller ecosystem. | Include | [repo](https://github.com/strands-agents/sdk-python) |
| Letta | 22k | Apache-2.0 | Stateful agent platform | Memory-first, self-improving agents; memory blocks. | Opinionated architecture. | Include | [repo](https://github.com/letta-ai/letta) |
| Google ADK | - | Apache-2.0 | Complete framework / SDK | Code-first build/eval/deploy; model-agnostic, Google-optimized; local via Ollama. | Younger ecosystem; strongest in Google's stack. | Include | [repo](https://github.com/google/adk-python) |
| Microsoft Agent Framework | - | verify | Orchestration SDK | Build/orchestrate/deploy agents + multi-agent across Python/.NET. | APIs still maturing; SK successor-layer. | Include | [repo](https://github.com/microsoft/agent-framework) |
| AnythingLLM | 58k | MIT | End-user agent + RAG app | All-in-one private AI app: agents, docs, tools, vector DB, local/cloud. | Less of a low-level SDK. | Include | [repo](https://github.com/mintplex-labs/anything-llm) |
| AutoGen | 56.9k | MIT | Multi-agent research framework | Influential MS multi-agent framework. | ⚠️ **Maintenance mode**; prefer Agent Framework for new builds. | Flagged | [repo](https://github.com/microsoft/autogen) |
| NeMo Agent Toolkit | ~2.5k | Apache-2.0 | **Interop + profiling layer, not a framework** | Wraps an existing framework's agents/tools as composable functions; adds YAML workflows, an eval harness, a token/latency/bottleneck profiler and MCP in both directions. v1.8 (2026-06-16), verified 2026-07-28. | Renamed twice in three minors (`agentiq`→`aiqtoolkit`→`nvidia-nat`) with the shims now deleted; breaking changes ship in minor releases. See Section J. | Include (alongside, not instead of) | [repo](https://github.com/NVIDIA/NeMo-Agent-Toolkit) |
| OpenClaw | verify | MIT | Personal assistant platform | Self-hosted assistant controllable from chat apps. | Rapidly changing; provider-policy sensitive. | Caution | [repo](https://github.com/openclaw/openclaw) |

### Platform-style builders (app/workflow over library)

| Project | License | Stack role | What it does | Cautions | Repo |
|---|---|---|---|---|---|
| Dify | Dify OSS License (Apache-based + conditions) | Platform / workflow builder | Production agentic workflows: RAG, tools, plugins, observability. | ⚠️ Source-available-with-conditions, not plain Apache. | [repo](https://github.com/langgenius/dify) |
| Mastra | Dual (Apache-2.0 core + `ee/`) | TS agent/app framework | TypeScript agents/workflows/memory for product teams. | ⚠️ Some enterprise features source-available. | [repo](https://github.com/mastra-ai/mastra) |
| FastGPT | Apache-based + conditions | KB + RAG + workflow platform | Knowledge platform: data processing, RAG, APIs, visual workflows. | ⚠️ Conditions for commercial/SaaS use. | [repo](https://github.com/labring/FastGPT) |
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
> now `aaif-goose/goose` (`block/goose` redirects); **Google is sunsetting consumer
> Gemini CLI / Code Assist on 2026-06-18** in favor of **Antigravity** (enterprise
> keeps Gemini CLI); the original Go **opencode** was archived and continues as
> **Crush** (Charm), while the TypeScript **OpenCode** (`sst/opencode` →
> `anomalyco/opencode`) kept the name; **Roo Code** archived (May 2026, migrate to
> Cline/Kilo Code); **Aider** is still maintained but cadence slowed (last push
> 2026-05-22). Verify stars/licenses before citing - they move.

> **Vendor-agnostic by default:** every harness below can be pointed at open/local or
> Ollama **cloud** models via Ollama's OpenAI-compatible endpoint
> (`ollama launch <harness> --model <model>:cloud`) instead of its default vendor model
> - 1M-context open models, local-first with cloud escalation, no lock-in.

Stars/status verified 2026-07-01 where dated; treat undated `verify` cells as unchecked.

| Project | License | Stack role | What it does | Cautions | Repo |
|---|---|---|---|---|---|
| Claude Code | proprietary (Anthropic) | Coding-agent harness | Terminal/IDE/web agent harness with skills, subagents, hooks, MCP, plugins. | Anthropic-hosted models; not OSS. | [docs](https://code.claude.com/docs/en/overview) |
| OpenAI Codex CLI | Apache-2.0 | Coding-agent harness | OpenAI's terminal coding agent; Rust, sandboxed shell by default, MCP, Python SDK. Defaults to GPT-5.5 (ChatGPT login) / GPT-5.2-Codex (API). ~85k★, v0.142.x (2026-06). | Tuned for OpenAI models. | [repo](https://github.com/openai/codex) |
| Gemini CLI | Apache-2.0 | Coding-agent harness | Google's open terminal agent; TS/npm, ReAct loop, MCP, GitHub Actions mode, only genuinely free tier (1k req/day). ~105k★. | **Consumer access ends 2026-06-18 → migrate to Antigravity; enterprise (Code Assist Std/Ent) retains.** | [repo](https://github.com/google-gemini/gemini-cli) |
| OpenCode | MIT | Coding-agent harness (OSS default) | Provider-agnostic terminal agent (75+ providers), TUI + client/server + LSP, build/plan agents. ~160–178k★, very active. Lowest-risk OSS default in 2026. | `sst/opencode` → `anomalyco/opencode`; not the archived Go "opencode" (that's now Crush). | [repo](https://github.com/sst/opencode) |
| Pi | MIT | Minimal/hackable harness | Deliberately minimal 4-tool core (Read/Write/Edit/Bash), self-extends at runtime; BYOK 20+ providers; tree-based sessions. ~54–66k★. By M. Zechner. | **No built-in permission system - sandbox/containerize it.** Fork: `can1357/oh-my-pi` (omp). | [repo](https://github.com/earendil-works/pi) |
| Cline | open source | IDE+CLI coding agent | Plan/Act modes, MCP, parallel agents + Kanban boards; grew standalone CLI + SDK in 3.x. 8M+ users. Roo Code/Kilo Code forked from it. | VS Code-first heritage. | [repo](https://github.com/cline/cline) |
| Aider | Apache-2.0 | Git-native pair-programmer | Terminal pair-programming pioneer; every edit a git commit; model-agnostic BYOK. ~46.8k★. | **Cadence slowed - last push 2026-05-22; leaderboard not refreshed for 2026 frontier models.** | [repo](https://github.com/Aider-AI/aider) |
| goose | Apache-2.0 | Coding agent harness | Open, extensible agent (Rust; desktop/CLI/API), recipes (YAML), subagents, MCP, 15+ providers. v1.39.0 (2026-06-25). | **Governance moved Block → Agentic AI Foundation (Linux Foundation); `block/goose` redirects to `aaif-goose/goose`.** | [repo](https://github.com/aaif-goose/goose) |
| deepagents | MIT | Batteries-included harness | LangChain's opinionated harness on `create_agent`/LangGraph. Built-ins: filesystem (`ls`/`read_file`/`write_file`/`edit_file`/`delete`/`glob`/`grep`, pluggable backends), `write_todos` planning, `task` subagents, `execute` shell, `eval` (QuickJS), skills, `AGENTS.md` memory, auto-summarization. **Middleware is the composition model.** v0.7.0 (2026-07-29), ~27k★, py≥3.11. JS twin `langchain-ai/deepagentsjs` publishes to npm as **`deepagents`** (v1.11.x - versions are not aligned, the API is). | A harness *and* a framework layer; needs the LangGraph runtime. ⚠️ **Pre-1.0, breaking changes at minor versions** - 0.7.0 removed `read_file`'s line-number gutter and changed empty `ls`/`glob` output. Model-agnostic in claim but Anthropic-shaped in practice (prompt caching is Anthropic/Bedrock; the JS default model is Claude). | [repo](https://github.com/langchain-ai/deepagents) |
| OpenHands | verify | Autonomous SWE agent | End-to-end software-engineering agent (ex-OpenDevin); hit 1.0 on a new Software Agent SDK (2026); browse/edit/test/retry, CI-friendly. 65k★, $18.8M Series A. | Higher autonomy = more guardrails needed. | [repo](https://github.com/OpenHands/OpenHands) |
| Crush | verify | Terminal coding agent | Charm's continuation of the original (archived) Go opencode codebase. | Verify license/status; don't confuse with TS OpenCode. | [repo](https://github.com/charmbracelet/crush) |
| Jules | proprietary (Google) | Async coding agent | Assign a full task; runs in an isolated VM and returns a PR. GA at I/O 2026; Gemini 3.1 Pro/3 Flash; Jules Tools CLI + API; self-healing CI. | Not OSS; async model (not interactive). | [site](https://jules.google/) |
| Antigravity | proprietary (Google) | Agentic IDE/platform | Agent-first dev platform (2.0): desktop app + CLI + SDK, multi-agent manager, browser-in-the-loop testing, artifacts. Free tier. Gemini 3.5 Flash + Claude/GPT-OSS. | Not OSS; successor to consumer Gemini CLI. | [site](https://antigravity.google/) |
| Cursor agent | proprietary | IDE coding-agent harness | Agent mode inside the Cursor IDE. | Not OSS. | [docs](https://docs.cursor.com/) |
| Google agents-cli | verify | Agent CLI harness | Google's runnable agents CLI (deploy agents on Google Cloud). | Verify status. | [repo](https://github.com/google/agents-cli) |
| OpenHarness | verify | Agent harness | Pure-Python harness: tools/knowledge/observation/action/safety. | Early-stage. | [repo](https://github.com/HKUDS/OpenHarness) |
| Nanobot | verify | Personal/local agent | Lightweight personal agent with memory + sandboxing; long-running focus. | Young; assistant-specific architecture. | [repo](https://github.com/HKUDS/nanobot) |
| Hermes | verify | Agent harness | Nous's agent; an offshoot of OpenClaw. | Include with care; see OpenClaw caution. | [repo](https://github.com/NousResearch/hermes-agent) |
| OpenClaw | MIT | Personal assistant harness | Self-hosted assistant driven from chat apps. | **Advise against** - over-privileged / insecure to run on an average dev's device. | [repo](https://github.com/openclaw/openclaw) |
| browser-use | verify | Browser-driving harness | Drives a real browser for web tasks. | Brittle to site changes. | [repo](https://github.com/browser-use/browser-harness) |
| Omnigent | Apache-2.0 | **Meta-harness** (layer *above* harnesses) | Databricks-built: runs Claude Code, Codex, Cursor, OpenCode, Hermes + YAML-defined custom agents behind one orchestration API; OS-level sandboxing (bubblewrap/seatbelt), stacked cost/access policies, sessions shareable across terminal/web/mobile. ~7.2k★ (2026-07-14). | **Self-described alpha; 571 open issues - pin versions.** Corporate backing (Databricks + Neon). | [repo](https://github.com/omnigent-ai/omnigent) |
| QM | MIT | **Meta-harness** (company-scale, layer *above* harnesses) | Y Combinator's multiplayer agent harness, open-sourced 2026-07-31 and run internally across accounting, legal, events and engineering. Per-person and per-room workspaces with scoped memory, files, keychain, permissions, crons and durable sandboxes; Slack + web under one identity. Headless core over Postgres; adapters for Pi, OpenCode, Codex, Claude Code. ~12.4k★ (2026-08-08). | **A deployed service, not a local CLI** - `qm init` scaffolds a Fly/AWS deployment repo; BYO model keys, no hosted tier. Skills arrive as git skill packs under `deploy/layers/<org>/`, not from `~/.agents/skills`. YC calls it early and buggy. | [repo](https://github.com/yc-software/qm) |
| alook | Apache-2.0 | Multi-agent coordination layer | Gives local coding agents email addresses, roles and an org chart; agents route tasks to each other, report via inbox/Kanban. ~0.9k★ (2026-07-14). | v0.0.x; **"self-hosted" is partial - the orchestrator is a Cloudflare-hosted component.** Shared-memory claim undocumented. | [repo](https://github.com/alookai/alook) |
| Grok Build | Apache-2.0 | Coding-agent harness (vendor) | xAI's terminal coding agent: Rust full-screen TUI, headless mode for CI, editor integration over the Agent Client Protocol. ~22.8k★ (2026-07-27). | **Squashed periodic exports from an internal monorepo** (1 contributor, 12 commits) - a vendor drop, not a community codebase. Tuned for Grok. | [repo](https://github.com/xai-org/grok-build) |
| herdr | Apache-2.0 | Multi-agent terminal multiplexer | One Rust binary showing every running agent's state (blocked/working/done); sessions survive detach and restart; socket API lets agents spawn their own panes. ~21.1k★ (2026-07-27). | Plugin marketplace - vet extensions separately. Sits beside the harnesses and runs them; it has no agent loop of its own. | [repo](https://github.com/ogulcancelik/herdr) |
| Shepherd | MIT | Agent runtime substrate | Makes a run a reversible git-like trace: fork, replay, revert; syscall-level permissions (Seatbelt/Landlock); outputs held as reviewable proposals. ~1.6k★ (2026-07-27). | **Self-declared alpha, APIs changing.** macOS/Linux only. The fork-and-replay primitive is the transferable idea. Re-verified 2026-08-14: still early alpha; companion repo `shepherd-experiments` now carries the paper's meta-agent applications, microbenchmarks and a frozen substrate snapshot for reproducibility. | [repo](https://github.com/shepherd-agents/shepherd) |
| Raven (EverMind) | Apache-2.0 | Self-improving harness | Harness over EverOS memory: durable user + agent memory, evolving skills, Agent Templates, scheduler, tracing. ~2.8k★ (2026-07-27). Backed by EverMind (Shanda Group). | **Pre-alpha by its own README**; not on PyPI (install is a Release wheel). Memory benchmark claims are first-party. | [repo](https://github.com/EverMind-AI/Raven) |
| OpenWorker | MIT | Desktop task agent | Andrew Ng's desktop "AI coworker": files + 25 app integrations, decomposes a task into steps, gates consequential actions behind approval. ~7.1k★ (2026-07-27). | Open beta, 4 contributors, published 2026-07-20. Read it as a **HITL-approval reference implementation**, not a dependency. Re-verified 2026-08-14: still beta, MIT, ~14.5k★, no material change. | [repo](https://github.com/andrewyng/openworker) |
| Aiden | **AGPL-3.0** | Autonomous work engine | Drives files, terminal, browser and APIs from a prompt; 76 skills, 121 tools, 19 providers. ~0.8k★ (2026-07-27). | ⚠️ **AGPL core + paid commercial relicensing** - dual-license trap, not a permissive dependency. Solo-maintained. | [repo](https://github.com/taracodlabs/aiden) |

> **Emerging tier - the meta-harness (noted 2026-07-14):** a layer *above* Section B
> that treats individual harnesses as interchangeable execution backends and moves
> governance (sandboxing, cost caps, tool allowlists) out of the prompt and into the
> orchestrator. **Omnigent** is the serious general-purpose entrant; **alook** attacks
> the same problem via org-chart/email routing; **T3MP3ST** (Section: security) is the
> same pattern applied to offensive security. Too young to recommend as a default -
> watch it. If it holds, "which harness?" stops being a lock-in question.

---

## Section C - Memory / long-term context / entity recall

| Project | Stars | License | Memory style | What it does | Cautions | Status | Repo |
|---|---:|---|---|---|---|---|---|
| Letta | 22k | Apache-2.0 | Stateful agent memory | Persistent state, memory blocks, self-improvement. | Opinionated. | Include | [repo](https://github.com/letta-ai/letta) |
| Mem0 | 52.5k | Apache-2.0 | Universal memory layer | Drop-in user/session/agent memory; self-host or hosted. | Not a full framework. | Include | [repo](https://github.com/mem0ai/mem0) |
| Graphiti | 24.7k | Apache-2.0 | Temporal knowledge graph | Evolving entity/fact/provenance/time graphs. | One layer of a larger stack. | Include | [repo](https://github.com/getzep/graphiti) |
| MemOS | 8.3k | verify | Memory OS | Unified store/retrieve/manage for long-term/multimodal/tool/KB memory. | Younger; verify license. | Include | [repo](https://github.com/MemTensor/MemOS) |
| Cognee | 15.1k | verify | Knowledge engine | Learns context over time via vectors + graphs + ontology. | Complex mental model. | Include | [repo](https://github.com/topoteretes/cognee) |
| claude-mem | verify | verify | Claude memory add-on | Memory daemon for Claude/Claude Code. | Niche; verify status. | Unverified | [repo](https://github.com/thedotmack/claude-mem) |
| Acontext | verify | verify | Context platform | Self-learning context store. | Verify current OSS status. | Unverified | [repo](https://github.com/memodb-io/Acontext) |
| Memori | verify | verify | SQL-native memory | SQL-native agent memory engine. | Verify status. | Unverified | [repo](https://github.com/MemoriLabs/Memori) |
| Hindsight | verify | verify | Human-like memory | Memory concept/system. | Verify status. | Unverified | [repo](https://github.com/vectorize-io/hindsight) |
| mempalace | verify | verify | Memory palace | Structured long-term store. | Verify status. | Unverified | [repo](https://github.com/MemPalace/mempalace) |
| Memoria | 0.5k | Apache-2.0 | **Version-controlled** memory | Snapshot / branch / merge / roll back a memory store like a git repo; hybrid vector + full-text recall, contradiction detection, audit trail per mutation. | ⚠️ Branching rides **MatrixOne's** copy-on-write MVCC engine - the headline feature carries a DB dependency, not a drop-in store. Quiet since 2026-06-29. | Caution | [repo](https://github.com/matrixorigin/Memoria) |
| EverOS | verify | Apache-2.0 | Markdown-native local memory | Local-first portable memory layer; the store underneath Raven (Section B). | Pre-1.0, moves with Raven. | Unverified | [repo](https://github.com/EverMind-AI/EverOS) |

> **Branch-and-merge memory (noted 2026-07-27):** Memoria and Shepherd (Section B)
> arrive at the same primitive from opposite ends - versioning an agent's *state* so a
> run can be forked, replayed and reverted. Both are early and both couple it to
> specific infrastructure, so neither is a recommendation yet. The *primitive* is the
> thing to watch: it makes agent work auditable and undoable, which is what
> production actually asks for.

---

## Section D - Knowledge / retrieval / context engines

The durable knowledge/context layer agents operate on.

| Project | Stars | License | Stack role | What it does | Cautions | Repo |
|---|---:|---|---|---|---|---|
| LlamaIndex | 48.5k | MIT | KB + retrieval + agents | Indexing/querying/graphs/retrievers over your data. | Broad surface. | [repo](https://github.com/run-llama/llama_index) |
| Haystack | 24.8k | Apache-2.0 | Retrieval + pipelines | Production RAG, routing, tool pipelines. | More engineering than turnkey. | [repo](https://github.com/deepset-ai/haystack) |
| LightRAG | 32.8k | verify | GraphRAG engine | Dual-level retrieval + KG; server/UI; local. | License verify before procurement. | [repo](https://github.com/HKUDS/LightRAG) |
| RAGFlow | 77.7k | Apache-2.0 | Full context platform | Deep doc understanding, citations, agent templates. | Platform, not a tiny SDK. | [repo](https://github.com/infiniflow/ragflow) |
| txtai | verify | verify | Semantic search + workflows | Embeddings DB, graph, relational storage, LLM workflows. | More context engine than full agent stack. | [repo](https://github.com/neuml/txtai) |
| Graphiti | 24.7k | Apache-2.0 | Temporal KB / graph memory | Evolving entity/fact graph. | Needs surrounding stack. | [repo](https://github.com/getzep/graphiti) |
| FalkorDB | 3.9k | **SSPL** | Graph DB substrate | Graph DB for KG / GraphRAG. | ⚠️ SSPL not OSI-approved. | [repo](https://github.com/falkordb/falkordb) |
| WrenAI | 16.7k | multi (see cautions) | **Semantic layer** over warehouses | Governed text-to-SQL for agents: an MDL semantic model (entities, relationships, metrics, access policy) sits between question and 20+ warehouses, so generation is schema-aware and traceable to approved definitions. | ⚠️ **Licensed by path** - `core/`/`sdk/`/`skills/`/`examples/` Apache-2.0, `docs/` CC-BY-4.0, and the LICENSE pre-stages **AGPL-3.0** for future modules (verified 2026-07-27). Re-check before depending on a new subtree. | [repo](https://github.com/Canner/WrenAI) |

> **When an agent must query a real warehouse**, the WrenAI pattern is the one to
> copy even if the product is not: model the semantics first (entities, joins,
> metrics, who may see what), generate SQL second. Text-to-SQL straight off a raw
> schema guesses joins and invents metric definitions; a semantic layer makes the
> answer traceable to something a human approved.

---

## Section E - Web & document ingestion

| Project | Stars | License | Stack role | What it does | Cautions | Repo |
|---|---:|---|---|---|---|---|
| Firecrawl | 107k | AGPL-3.0 | Web knowledge ingestion | Scrape/crawl/extract/search + MCP for agents. | ⚠️ AGPL may block some orgs. | [repo](https://github.com/firecrawl/firecrawl) |
| Crawl4AI | verify | verify | Web ingestion / crawling | LLM-friendly crawler → markdown/structured. | ⚠️ Recent supply-chain hotfix (litellm→unclecode-litellm); pin current versions. | [docs](https://docs.crawl4ai.com/) |
| Docling | 57.5k | MIT | Document parsing | Complex docs → structured, agent-ready data. | Parsing layer only. | [repo](https://github.com/docling-project/docling) |
| Scrapling | verify | verify | Adaptive scraping | Stealth/adaptive web scraping. | Verify status. | [repo](https://github.com/D4Vinci/Scrapling) |
| surya | verify | verify | OCR / layout | OCR, layout, reading-order detection. | - | [repo](https://github.com/datalab-to/surya) |
| pdfplumber | verify | MIT | PDF extraction | PDF text/table extraction. | Single-purpose. | [repo](https://github.com/jsvine/pdfplumber) |
| langextract | 37.9k | Apache-2.0 | Structured extraction (grounded) | Pulls structured records out of unstructured text and maps every extraction back to exact character offsets in the source; schema enforced from few-shot examples; multi-pass chunking for long documents; Gemini, OpenAI and Ollama backends; emits interactive HTML for review. v1.6.0, active (2026-07-27). | Published by Google but **not an officially supported Google product** - no vendor SLA. OpenAI backends need `fence_output=True` with `use_schema_constraints=False`. | [repo](https://github.com/google/langextract) |
| Instructor | 13.6k | MIT | Structured outputs (typed) | Pydantic-typed LLM responses with validation and automatic retries across providers. v1.15.4, active (2026-07-27). | Types and validates the response; no source grounding and no long-document strategy. | [repo](https://github.com/instructor-ai/instructor) |
| Outlines | 15.4k | Apache-2.0 | Constrained decoding | Constrains generation against a grammar, regex or JSON schema so malformed output cannot be emitted in the first place. v1.3.2, active (2026-07-27). | Operates at the decoding layer and needs a backend exposing logits; it is not an extraction pipeline. | [repo](https://github.com/dottxt-ai/outlines) |

---

## Section F - Skills / tool packs / capability layers

| Project | License | Role | What it does | Repo |
|---|---|---|---|---|
| affaan-m/ECC | MIT | Harness config OS | The largest skill/config distribution in this space: 67 agents, 281 skills, 94 commands, 34+ rule sets, hooks on 20+ event types, a memory/instincts layer and AgentShield, installable across ~12 harnesses. v2.1.0, ~234.6k★ (2026-07-28). Renamed from `everything-claude-code`; match on `affaan-m` because same-name copies are common. Mine it for patterns and install profile-scoped - a `full` install rewrites agents, hooks and rules, and 281 skills is a trigger-collision surface. | [repo](https://github.com/affaan-m/ECC) |
| affaan-m/agentshield | MIT | Agent-config security scanner | Audits agent/skill definitions, MCP configs and tool permissions against a stated 102 rules; CLI, GitHub Action, plugin, GitHub App. ~1.0k★ (2026-07-28). The off-the-shelf analogue to a hand-written agent-tooling security checklist; rules are first-party and unaudited, so diff rather than adopt. | [repo](https://github.com/affaan-m/agentshield) |
| addyosmani/agent-skills | verify | Skill pack | Reusable agent skills. | [repo](https://github.com/addyosmani/agent-skills) |
| NVIDIA/skills | verify | Skill pack | NVIDIA agent skills. | [repo](https://github.com/NVIDIA/skills) |
| anthropics/skills | Apache-2.0 (most skills) | Skill pack | Anthropic's own public Agent Skills repo; includes the document skills (docx/pdf/pptx/xlsx) that back Claude's document handling. | [repo](https://github.com/anthropics/skills) |
| K-Dense-AI/scientific-agent-skills | verify | Skill pack | Scientific agent skills across biology, chemistry, medicine and drug discovery, plus scientific databases; portable across harnesses via the Agent Skills standard. 154 skills (2026-07-27). Community-maintained, not an Anthropic project; the four document skills are vendored from `anthropics/skills`. | [repo](https://github.com/K-Dense-AI/scientific-agent-skills) |
| CopilotKit / AG-UI | verify | Agent-to-UI protocol | Agents ↔ frontend state, UI, HITL. | [repo](https://github.com/copilotkit/copilotkit) |
| Firecrawl MCP / Docling MCP / Strands tools | MIT/varies | MCP tool servers | Web + document + provider tools over MCP. | see ingestion rows |
| rtk-ai/rtk | verify | CLI token optimizer | Token-killing CLI output proxy. | [repo](https://github.com/rtk-ai/rtk) |
| JuliusBrussee/caveman | verify | Output style | Token-compressed communication style. | [repo](https://github.com/JuliusBrussee/caveman) |
| cobusgreyling/loop-engineering | MIT | Loop design patterns + CLI | Patterns, starters and tools (`loop`, `loop-audit`, `loop-init`, `loop-cost`) for designing the loop an agent runs in - scheduled triage, CI sweeps, cost accounting - rather than the prompt. ~9.5k★ (2026-07-27). Half tooling, half essays; the essays are the reason to read it. | [repo](https://github.com/cobusgreyling/loop-engineering) |

> **MCP servers:** to *build* one, defer to the system's `build-mcp-server` /
> `build-mcp-app` skills (official `mcp-server-dev` plugin) and `plugin-dev`'s
> `mcp-integration`. This skill does not reimplement them.

---

## Section G - Fine-tuning / adaptation / local training

| Project | Stars | License | Role | What it does | Repo |
|---|---:|---|---|---|---|
| Unsloth | 60.8k | Apache-2.0 + AGPL components | Fine-tuning / local training | Fast local tuning + RL for open models; studio UI. | [repo](https://github.com/unslothai/unsloth) |
| TRL | - | Apache-2.0 | RLHF / post-training | HF Transformer RL: RLHF, DPO/PPO, post-training loops. | [repo](https://github.com/huggingface/trl) |
| PEFT | - | Apache-2.0 | Adaptation | Parameter-efficient fine-tuning (LoRA-style). | [repo](https://github.com/huggingface/peft) |
| Axolotl | - | Apache-2.0 | Training stack | Popular open fine-tuning stack. | [repo](https://github.com/axolotl-ai-cloud/axolotl) |

---

## Section H - RL / agent optimization / self-improvement

| Project | License | Stack role | Why it matters | Repo |
|---|---|---|---|---|
| Agent Lightning | verify | Agent RL / prompt optimization | Framework-agnostic trainer: RL + auto prompt-opt + SFT; wraps multiple frameworks. | [repo](https://github.com/microsoft/agent-lightning) |
| OpenPipe ART | Apache-2.0 | Agent reinforcement trainer | RL over multi-step agent trajectories with an LLM judge supplying the reward, so a task needs no hand-written reward function. ~10.5k★ (2026-07-27). | [repo](https://github.com/OpenPipe/ART) |
| Molt (NVIDIA labs) | Apache-2.0 | Agentic-first RL research framework | Fully async, multi-turn, multimodal RL on Ray + vLLM rollouts + FSDP2, scaling to trillion-param MoE; ~9.2K lines of RL-specific code, meant to be read and forked. ~0.6k★ (2026-07-27). **NVIDIA labs - research code, not a supported NeMo product.** | [repo](https://github.com/NVIDIA-NeMo/labs-molt) |
| Letta / Mem0 / MemOS / Cognee / Graphiti | - | Behavioral improvement via memory | The practical path to "agents that get better over time" in most production systems. | see Section C |

**Stance:** treat agent RL as a specialized layer. Do not pick an agent framework
primarily on its RL story unless you have an explicit post-training roadmap. For
most teams, "improvement over time" comes from the memory layer, not RL.

---

## Section I - Eval, observability & code intelligence

| Project | Role | Repo |
|---|---|---|
| deepeval | LLM eval framework | [repo](https://github.com/confident-ai/deepeval) |
| openai/evals | Eval harness | [repo](https://github.com/openai/evals) |
| Opik (Comet) | LLM tracing/eval/observability | [repo](https://github.com/comet-ml/opik) |
| MLflow | Experiment tracking, registry, GenAI tracing | [repo](https://github.com/mlflow/mlflow) |
| Weights & Biases | Tracking / Weave LLM tracing | [repo](https://github.com/wandb/wandb) |
| Giskard v3 (`giskard-oss`) | Agent evals + red-teaming + test generation: scenario APIs, LLM-as-judge, adversarial scanner. Apache-2.0, ~5.7k★ (2026-07-27). **v3 is a rewrite, not a rename** - v2 is unmaintained; pin deliberately. | [repo](https://github.com/Giskard-AI/giskard-oss) |
| agent-flow | Run-level observability: interactive node graph of a Claude Code / Codex run branching into subagents and tool calls, timeline + JSONL replay. Apache-2.0, ~1.4k★ (2026-07-27). | [repo](https://github.com/patoles/agent-flow) |

### I.1 - Codebase → queryable knowledge graph (verified 2026-07-27; graphify re-verified 2026-07-28)

The layer that replaces "the agent greps until it finds it" with "the agent queries
a structural index." All the serious entrants share one architecture: **tree-sitter
AST parse → persistent graph of symbols, calls, imports and dependents → served to
the agent over MCP (or as a skill), so retrieval is targeted instead of exhaustive.**

| Project | License | Lang | Stars (2026-07-27) | Index | Interface | Scope beyond code | Notes |
|---|---|---|---:|---|---|---|---|
| [graphify](https://github.com/Graphify-Labs/graphify) | Apache-2.0 | Python | 97.6k (07-28) | `graphify-out/graph.json` + HTML report | CLI + MCP (extra) + `/graphify` skill | docs, PDFs, SQL schemas, configs, media (**LLM pass**) | Widest scope and easiest install; Leiden community detection gives "what is this subsystem" answers. PyPI `graphifyy` 0.9.29, py>=3.10. 676 open issues; anonymous org. Its installer also edits `CLAUDE.md` and registers PreToolUse hooks - see caveat 6. |
| [colbymchenry/codegraph](https://github.com/colbymchenry/codegraph) | MIT | C | 62.6k | SQLite + FTS5 | MCP, 8 agent clients | code only | Auto-syncs on file change. **Releases carry `gh attestation verify` build attestations** (2026-07 onward) - the best supply-chain story here. |
| [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) | MIT | C | 35.7k | embedded, static binary | MCP (15 tools) | code only | ~158 languages, LSP type resolution for ~11. Only entrant with a public write-up ([arXiv 2603.27277](https://arxiv.org/html/2603.27277v1)), which reports **83% answer quality vs 92% for plain file exploration at ~10x fewer tokens**. |
| [code-review-graph](https://github.com/tirth8205/code-review-graph) | MIT | Python | 26.7k | SQLite | MCP + CLI | code only | Incremental change tracking aimed specifically at review and blast-radius questions. |
| [repowise](https://github.com/repowise-dev/repowise) | **AGPL-3.0** | Python | 4.2k | - | CLI | code health, docs, git analytics | Analytics rather than a queryable graph. ⚠️ AGPL. |
| [GitVizz](https://github.com/adithya-s-k/GitVizz) | **none** | TS | 0.5k | - | web/CLI | repo visualization | ⚠️ No license file (all rights reserved) and untouched since 2026-02-12. Do not vendor. |

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
| [NeMo Guardrails](https://github.com/NVIDIA/NeMo-Guardrails) | Programmable I/O rails for LLM apps | Apache-2.0, ~6.8k★, v0.23.0. Usable standalone; the only platform piece that is genuinely independent. |
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

⚠️ **The licence is not uniform across the family.** Nano and Super are published
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

⚠️ **The pin asymmetry is a live hazard.** AI-Q pins the toolkit exactly
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

**RAPIDS** ([`cuML`](https://github.com/rapidsai/cuml), plus `cuDF` and `cuVS`) is the GPU dataframe and classical-ML layer. It is
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
retrieval, doc→markdown, structured output, safety and agent loops; Apache-2.0, ~2.3k★
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
