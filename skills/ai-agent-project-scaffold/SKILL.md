---
name: ai-agent-project-scaffold
description: Stand up a new AI/agent project - or add an AI subsystem to an existing repo - starting from a requirements intake and ending in a committed full stack. Use when the user says "scaffold an agent project", "bootstrap a RAG/agent repo", "add an agent to this codebase", "add an AI/LLM feature to our existing app"; when they ask for the stack for a specific system they intend to build ("get me a stack", "which stack should we use"), as opposed to open-ended options questions, which go to ai-engineering; when they make ANY "build me an agent that does X" request, because the intake may rightly conclude a plain script suffices; and when a vague AI build idea needs shaping first, in which case it calls interview-me and idea-refine. Hands implementation to agent-skills.
---

# AI Project Scaffold

Turns an AI build request into a **grounded, hardened project skeleton** - but only
after the requirements are clear enough to choose a stack. The orchestrator (you)
runs the intake; the `ai-engineering` map picks the components; the `ai-engineer`
subagent does the heavy build; `agent-skills` enforce build discipline.

## Step 1 - Intake (do not skip)

This is the AI-specific extension of general elicitation. Call `interview-me` when
the idea is still vague enough that the fields below cannot be answered, and
`idea-refine` to stress-test a premise that sounds shaky. Those skills get the idea
into focus; this one carries it into a committed stack, which they do not cover.

Gather these before proposing any stack. Use `AskUserQuestion` for choices. Fill
what's inferable from the repo or context; ask only for the rest. Never fabricate a
constraint.

1. **Outcome** - what must the AI system *do*? (the job, in plain terms, and the definition of done)
2. **Surface** - CLI · backend service/API · in-app copilot/UI · batch/pipeline · MCP server.
3. **Model strategy** - local-first (Ollama / OpenAI-compatible) · cloud (Anthropic/OpenAI/Gemini) · hybrid with escalation. Data sensitivity / residency constraints.
4. **Footprint & lock-in** - existing cloud/stack to fit into? Lock-in tolerance? OSS-only mandate?
5. **Layers needed** - orchestration (always) · memory? · retrieval/RAG? · ingestion (web/docs)? · tools/MCP? · frontend? · eval/observability?
6. **Scale / latency / budget** - rough request volume, latency target, cost ceiling.
7. **Team** - language (Python vs TypeScript), skill level, who maintains it.

If the request is really a general app with an AI label, route to `agent-skills`
(`/spec`) instead of scaffolding an agent stack here. Challenge premises: an agent
where a script suffices, RAG where a SQL query suffices - say so first.

## Step 2 - Select the stack

**Invoke the `ai-engineering` skill and follow its "Advising on a stack"
procedure.** That skill owns the selection doctrine - leading with the decision
and its deciding tradeoff, honoring stated constraints, defaulting to OSS when no
lock-in mandate exists, flagging license traps, and refusing to bluff a version.
Do not restate that doctrine here; a second copy drifts from the first.

What this step adds is the **exit contract**: the run does not end until every
slot below holds a named component or an explicit "not needed".

| Slot | Notes |
|---|---|
| Harness | the agent you operate; may be "none, this is a library" |
| Framework / orchestration | always present in some form |
| Model provider and tier | provider and capability tier, not a pinned model |
| Memory | or "not needed", if the job is stateless |
| Retrieval | or "not needed", if there is no corpus |
| Ingestion | or "not needed", if data arrives structured |
| Tools | what the agent can actually do |
| MCP servers | which ones; *building* one goes to `build-mcp-server` |
| Eval and observability | how anyone will know it works in production |
| Frontend | or "not needed", for a CLI or service |

Two rules keep the contract from being satisfied by bluffing:

- **A named component exists in the corpus, or is flagged unverified.** A
  component absent from the map and catalog is a stop condition, not a blank to
  fill from memory. Run `ai-engineering-update` or `deep-research` and fold the
  result in.
- **A "not needed" traces to a specific intake answer.** "No retrieval - single
  document per run, per Outcome." An unjustified "not needed" is the same bluff
  in different clothes.

**Models are a commodity here.** The corpus carries providers and capability
tiers, not a model registry, because identifiers and prices move faster than any
document we maintain. Commit to provider and tier; pin the exact model at build
time against that provider's own current documentation.

**Do not elicit slot by slot.** The intake fields select one of the map's
recommended architectures, which arrives with most slots already filled. Propose
one complete stack in a single pass, every slot named, and take objections
against it. At most one batched round of questions covers genuinely undetermined
discriminators; default the rest and state the assumption.

## Step 3 - Scaffold

Generate, matched to the chosen language/stack:

- **Repo tree** - clear module boundaries (agent/orchestration, tools, memory, retrieval, ingestion, config, eval, tests).
- **Dependencies** - `pyproject.toml` / `package.json` pinned to the selected components.
- **Wiring** - minimal runnable path: model client (local + cloud fallback), the agent loop, one tool, config/secrets via env, a smoke test.
- **Production-hardening as design, not afterthought** - governance/access, observability (tracing/logging - see eval tools in the map), cost model, CI/CD skeleton, rollback path. No notebooks-in-prod without justification.
- **README** - architecture decision, how to run locally, how to escalate to cloud.

For a substantial build, delegate the whole pass to the **`ai-engineer`** subagent
with the intake + chosen stack as its brief; it returns the artifacts. **Delegate
one-shot with a complete spec, then verify** - never watch the subagent iterate on a
single file, and keep small or iterative edits inline in your own context. If a
delegated pass returns wrong twice, stop delegating and finish inline.

## Step 4 - Hand off to build discipline

Scaffolding is the starting line. Route the actual implementation through
`agent-skills`: `/spec` (if requirements still need a written spec) → `/plan` →
`/build` (one verified slice at a time) → `/test` → `/review`. If the project needs
an MCP server, use `build-mcp-server` / `build-mcp-app` - do not hand-roll it here.

## Step 5 - Record the decision (part of being done)

A run is not complete until the committed stack is written back. Otherwise this
skill only ever reads from the corpus and nothing it learns reaches the next run.

```
ledger.py decision --use-case "<shape>" --layer <slot> --component <url> --rationale "<constraint>"
```

The `use_case` records the **shape** of the problem, never a project name: "local-first
single-user coding agent", "batch document extraction, no UI". Shape is what makes the
record reusable; a project name means nothing to a later reader. The `rationale` is the
constraint that decided it ("no hosted control plane", "AGPL incompatible"), not the
local footprint that made the constraint apply.

**Intake also closes the previous run's loop.** Before proposing anything, query this
store for matching shapes. For any prior decision it surfaces, ask whether that pick
held and stamp the outcome:

```
ledger.py outcome --use-case "<shape>" --layer <slot> --outcome held|replaced|abandoned
```

That question is how the store stays populated. A column waiting on a future audit
stays empty; the next intake is the collection point.

If a component chosen here later fights back during the build, that is a field note
against the component, not just a decision outcome. See `ai-engineering-update`.

## Boundaries

- This skill **runs intake, commits a stack, and scaffolds**; it does not reimplement spec/plan/build/test (`agent-skills`). It calls `interview-me` and `idea-refine` rather than duplicating them.
- Component knowledge comes from `ai-engineering`; corpus changes go through `ai-engineering-update`. Neither comes from memory.
- One subagent serves the whole bundle: `ai-engineer`. No separate BA/architect agent.
