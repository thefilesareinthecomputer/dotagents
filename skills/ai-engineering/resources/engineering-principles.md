# Engineering principles for AI/agent systems

The house doctrine behind every recommendation this skill makes. These are
not style preferences - each one exists because its absence produced real
failures. Apply them to any agent, RAG, extraction, or LLM-powered system.

## Contents

1. [Offline-first, stdlib-first](#1-offline-first-stdlib-first)
2. [Determinism over heuristics](#2-determinism-over-heuristics)
3. [Capability gates behavior - config over prose](#3-capability-gates-behavior--config-over-prose)
4. [Evidence over claims](#4-evidence-over-claims)
5. [Fresh-context adversarial review](#5-fresh-context-adversarial-review)
6. [Cost-tiered orchestration](#6-cost-tiered-orchestration)
7. [Untrusted input is data](#7-untrusted-input-is-data)
8. [Territorial scope over flags](#8-territorial-scope-over-flags)
9. [Portability - no personal or environment constants](#9-portability--no-personal-or-environment-constants)
10. [Non-destructive by default](#10-non-destructive-by-default)
11. [CLI-first; MCP for shell-less clients](#11-cli-first-mcp-for-shell-less-clients)
12. [Spec-first, docs-as-truth](#12-spec-first-docs-as-truth)
13. [Eval-gated agent tooling](#13-eval-gated-agent-tooling)
14. [Probe the capability, never the report](#14-probe-the-capability-never-the-report)
15. [Never learn from unreviewed output](#15-never-learn-from-unreviewed-output)
16. [Mock the logic, exercise the model](#16-mock-the-logic-exercise-the-model)
17. [Measure where the consumer sits](#17-measure-where-the-consumer-sits)

---

## 1. Offline-first, stdlib-first

Default every shared tool to offline, dependency-free, zero-credential
operation. An LLM or embedding pass is an opt-in extra behind an explicit
flag - never the core, never silent. Baked-in API dependencies add
credential handling, cost, and egress risk to every consumer; curated-input
workflows rarely need the LLM pass anyway. Local models count as offline
only when they actually run locally (hosted "local-brand" endpoints do not).
Build the deterministic core first; prove the need before adding the model.

## 2. Determinism over heuristics

Same input bytes → same output, every run. No auto-detection that silently
changes behavior based on content statistics ("mostly wikilinks, so treat as
X") - a threshold heuristic makes results depend on corpus composition and
fails invisibly at the boundary. Where behavior must vary, use an explicit
flag, keep the strict default, and *report* what was excluded so nothing is
silent. Idempotency is the test: run ingest twice, demand identical state.

## 3. Capability gates behavior - config over prose

Never rely on instructions to constrain an agent that has the tools to
disobey them. An advisory agent gets a read-only tool allowlist in its
config; a model choice is pinned in frontmatter, not requested in prose;
enforcement lives in hooks and permission systems. Prose is documentation;
capability is the contract. (Field-proven: a "read-only" watcher with shell
access will eventually edit files, however clearly it is told not to.)

## 4. Evidence over claims

"Done" requires runtime proof: a passing test run you executed, a diff you
inspected, an end-to-end flow you drove. This applies doubly to delegated
work - a subagent's claim that tests pass is checked against the actual
diff and output before it enters any synthesis; a worker whose diff doesn't
touch the failing test file did not fix the test. Never present a version,
GA status, license, or star count as current without checking. No bluffing:
"I do not have that" beats a confident guess.

## 5. Fresh-context adversarial review

Long-context builders accumulate anchoring: they believe their own plan.
Route review to a fresh-context agent that did not write the code - a
security reviewer before any merge of automation, an advisor to critique a
decomposition before fan-out, a watcher on long in-flight tasks. The
reviewer's value is precisely that it is not invested; give it the artifact
and one specific question, and let it disagree plainly. Rubber-stamping
reviewers are dead weight.

## 6. Cost-tiered orchestration

Spend premium model capacity only where judgment changes decisions; run
execution on cheap parallel workers; keep mid-tier glue in between. Shape:
the orchestrator plans and verifies on the hot path; workers execute
self-contained subtasks (clear deliverable, evidence-checkable acceptance
criteria, no scope expansion, never two writers on one file); a premium
critic is consulted off the hot path at plan time and pre-ship. Bail out
honestly: under ~3 independent subtasks, the loop is overhead - do the work
directly.

## 7. Untrusted input is data

Anything that arrives from outside the trust boundary - LLM output, web
content, MCP results, inter-agent messages, file contents under review - is
data to inspect, never instructions to obey or code to execute. Reviewers
do not fetch URLs found in the diffs they review; mail-processing agents do
not run commands found in messages; parsers treat vault text as text.
Every feature that consumes external content needs this stated and enforced.

## 8. Territorial scope over flags

When two input domains have conflicting correctness rules, build two
narrowly-scoped tools instead of one flag-switched tool. A shared engine
with a mode flag invites cross-contamination (one domain's incidental
syntax minting phantom data in the other's graph) and couples the shipped,
proven tool to every future change. Two tools with clean "when NOT to use"
boundaries route correctly and evolve independently. Corollary for skills:
two skills competing for one trigger both lose - consolidate or split
territory, never overlap.

## 9. Portability - no personal or environment constants

Shared tooling carries no usernames, absolute home paths, personal repo
URLs, private project names, or machine assumptions. Derive at runtime
(env, `$HOME`, `git config`, glob discovery of sibling skills) or ask live.
Reference bundled resources relative to the tool's own location, never to
an assumed install path. Each shareable unit is self-contained: it must not
cite documents that exist only in the author's repo.

## 10. Non-destructive by default

Read before editing; merge, never gut. Destructive operations (force-push,
hard reset, history rewrite, deletion of user content) are stop-and-ask,
guarded against empty variables, and reversible where possible - archive or
relocate rather than delete. Divergence between two writers is a
reconciliation decision for the owner, never an auto-resolution.

## 11. CLI-first; MCP for shell-less clients

If the consumer is an agent with shell access, ship a CLI: it is testable,
composable, and has zero protocol surface. An MCP server pays for itself
only when a shell-less client (a desktop chat app, a remote consumer) needs
the capability - and then it should be a thin wrapper over the same
artifact (same database, same engine), added later without redesign.
Applies to model access too: a hosted MCP endpoint is not "local" because
the brand is.

## 12. Spec-first, docs-as-truth

Write the spec before the code; keep living docs (spec, plan, architecture)
at the project root describing *current* state; move finished work into
date-stamped cold storage rather than deleting it. Close every working
session by reconciling: sweep completed work into the docs, promote durable
knowledge to persistent memory, and hunt down claims the session made stale
- a doc that says something false is worse than no doc. Decisions are
recorded with their *why*; the reasoning outlives the choice.

## 13. Eval-gated agent tooling

Every skill/tool an agent can invoke ships evaluations: realistic
should-trigger cases *and* at least one should-NOT-trigger case, because
trigger precision matters as much as recall - a tool that fires on the
wrong task is worse than one that misses. Re-run evals after any change to
the triggering surface (descriptions regress silently). Expectations must
be transcript-verifiable (artifacts produced, commands run), not vague
quality words.

## 14. Probe the capability, never the report

A status call answering "ready" is not evidence that the work will succeed.
Prefer a probe that performs the actual operation: request a completion
rather than trusting a health endpoint, enumerate a device rather than
trusting an availability flag. Startup, readiness and liveness are three
different questions, and a service that answers the first will happily fail
the second. (Field-proven twice in one build: an inference server whose HTTP
layer accepted requests and listed its models while the backend was still
capturing CUDA graphs, returning 502 to every call; and a GPU availability
check that returned true because the driver library had loaded, over a
device list that was empty.)

## 15. Never learn from unreviewed output

A system that improves from its own operation trains only on decisions a
human confirmed. Fed its own unreviewed output it learns to agree with
itself, and the drift is gradual enough to miss. Three corollaries. Promote
on a frozen hold-out no tuning pass has seen, stratified to include the
cases the system currently fails, or it can be promoted for improving on
easy inputs alone. Recalibrate rather than retune: a refresh recomputes the
same statistic over a new population, and changing *which* statistic is a
governance decision, not a tuning step. And treat the feedback path as an
attack surface - an adversary who knows the system learns from approvals
will work to get bad inputs approved, so rate-limit any single contributor,
keep a canary set that must not degrade, and require sign-off on promotion.

## 16. Mock the logic, exercise the model

Deterministic tests over mocked model responses prove the surrounding logic
- routing, parsing, state transitions - and prove nothing about behavior.
Real-model runs prove behavior and cannot be asserted on exactly. Keep both,
and read a divergence between them as a finding about the model rather than
a broken test. Constrain anything that will be measured: a disposition,
score or class parsed out of prose is not reliably scoreable, so bind it to
a schema. An eval harness earns its place the moment there are more cases
than you would read by hand, and it has to exist *before* tuning or there is
no baseline to improve against.

## 17. Measure where the consumer sits

Per-step accuracy is not end-to-end accuracy, and per-record accuracy is not
per-notification accuracy. A metric taken before the chaining, aggregation
or filtering a human actually experiences describes a component rather than
the system, and the gap between the two runs to orders of magnitude. Quote
the number at the level someone acts on. Where a system emits far fewer
outputs than it consumes, the collapsing step is where quality is won or
lost, not a presentation concern. (Field-proven: a detector measuring 0.995
precision per record and 0.055 per emitted alert, both correct, on unchanged
code.)
