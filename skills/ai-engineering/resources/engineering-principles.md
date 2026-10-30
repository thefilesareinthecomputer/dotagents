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
18. [Enforcement fails open](#18-enforcement-fails-open)
19. [A boundary is real only after a canary](#19-a-boundary-is-real-only-after-a-canary)

---

## 1. Offline-first, stdlib-first

Default every shared tool to offline, dependency-free, zero-credential
operation. An LLM or embedding pass is an opt-in extra behind an explicit
flag - never the core, never silent. Baked-in API dependencies add
credential handling, cost, and egress risk to every consumer; curated-input
workflows rarely need the LLM pass anyway. Local models count as offline
only when they actually run locally (hosted "local-brand" endpoints do not).
Build the deterministic core first; prove the need before adding the model.

A script that loads a local model checks memory pressure before the load and unloads the model on exit (for Ollama, `keep_alive: 0` sent from a `finally` block).
Before installing a third-party harness, audit the pinned version statically.
Fetch it without running install scripts (`npm pack`, `pip download`), read the first-party code for outbound calls (telemetry, update checks, registry fetches, fetch tools the model can call), and record each call's default and its off switch.
Some CLIs have no telemetry off switch short of a fully offline mode; record that as a finding.
Re-audit before every upgrade, because a new version can add calls.

## 2. Determinism over heuristics

Same input bytes → same output, every run. No auto-detection that silently
changes behavior based on content statistics ("mostly wikilinks, so treat as
X") - a threshold heuristic makes results depend on corpus composition and
fails invisibly at the boundary. Where behavior must vary, use an explicit
flag, keep the strict default, and *report* what was excluded so nothing is
silent. Idempotency is the test: run ingest twice, demand identical state.

The same split governs gates: a script surfaces candidates, and the model or a person decides.
A gate that issues verdicts from the shape of a token alone fires on harmless matches and gets muted, and a muted gate is worse than none because it still looks installed.
Split each check into the decidable part, which filters provable stand-ins such as placeholder values, and the contextual part, which reports labeled candidates to a reviewer.
Measure the false-positive rate over the real corpus before wiring a gate in, and pin each recurring false positive as a test fixture.
A hook backed by a model starts record-only, because in auto-approve modes a hook's "ask" can become a hard block.
To check a small model's judgment, make it quote the line it relied on and have a script confirm that the quote exists in the input.

## 3. Capability gates behavior - config over prose

Never rely on instructions to constrain an agent that has the tools to disobey them.
An advisory agent gets a read-only tool allowlist in its config, and that allowlist holds no general-purpose tool: a shell, a task or skill launcher, a SQL tool or a web fetch each reopens what the allowlist closed.
A model choice is pinned to a full model ID in the agent definition, not requested in prose, and the pin is only a default that a model named at the spawn call overrides (see [6](#6-cost-tiered-orchestration)).
Enforcement lives in hooks, permission deny rules and OS sandboxing.
Prose instructions document the intended behavior, and the capability configuration is what enforces it.
(Field-proven: a "read-only" watcher with shell access will eventually edit files, however clearly it is told not to.)

If the agent needs a shell, the boundary has to be the operating system, such as a separate user account or a container, because a shell can do anything its user can.
Prefer allowlists to denylists for unattended agents.
A too-narrow allowlist fails loudly on the first refused call, while a too-narrow denylist fails silently, and a harness release that adds tools is ignored by an allowlist but admitted by a denylist.
Ignore files are not security controls: across harnesses they guard only some tools or are not read at all.

Where a harness sets tools and model in the agent definition, as Claude Code does, the spawn call cannot scope tools, so scope belongs in the definition.
A definition's tools field narrows inherited permissions and never elevates them, and hooks still fire inside the subagent.
Omitting the spawn-capable tool from a worker's definition keeps a fan-out one level deep by construction.

## 4. Evidence over claims

"Done" requires runtime proof: a passing test run you executed, a diff you
inspected, an end-to-end flow you drove. This applies doubly to delegated
work - a subagent's claim that tests pass is checked against the actual
diff and output before it enters any synthesis; a worker whose diff doesn't
touch the failing test file did not fix the test. Never present a version,
GA status, license, or star count as current without checking. No bluffing:
"I do not have that" beats a confident guess.

A negative needs the same proof as a positive.
Before reporting something as missing, enumerate what is present and state what was searched.
A checker that does not recognize a file has not cleared it, and a subagent's "does not exist" is a failed search until a direct check confirms it.
A migration or copy report leads with what was left out.
A scan run to prove absence is never truncated: print the match count first and a sample second, so a capped listing cannot pass for a clean one.
A history scan needs both the diff of every commit and the first commit's full tree, because a diff-only pass can skip the root commit and a tree-only pass misses anything later removed.

## 5. Fresh-context adversarial review

Long-context builders accumulate anchoring: they believe their own plan.
Route review to a fresh-context agent that did not write the code - a
security reviewer before any merge of automation, an advisor to critique a
decomposition before fan-out, a watcher on long in-flight tasks. The
reviewer's value is precisely that it is not invested; give it the artifact
and one specific question, and let it disagree plainly. Rubber-stamping
reviewers are dead weight.

A scrubber or detector never contains the values it detects, in code, comments, examples, tests or list headers; its examples use invented values.
Have an independent reader review the gate, because its author is the likeliest evader: patterns written with the real values in mind tend to match only the forms the author thought of.

## 6. Cost-tiered orchestration

Spend premium model capacity only where judgment changes decisions; run
execution on cheap parallel workers; keep mid-tier glue in between. Shape:
the orchestrator plans and verifies on the hot path; workers execute
self-contained subtasks (clear deliverable, evidence-checkable acceptance
criteria, no scope expansion, never two writers on one file); a premium
critic is consulted off the hot path at plan time and pre-ship. Bail out
honestly: under ~3 independent subtasks, the loop is overhead - do the work
directly.

Every batch or fan-out spawn names its model, because an omitted model inherits the session's premium model.
Pilot one unit, then state the call count and model before fanning out N.
Model aliases resolve to whatever the CLI build knew, so after a release an alias can name an older model.
Pin full model IDs, have headless runs refuse a result whose reported model differs from the pin, and price from reported tokens rather than a lookup table that guesses on unknown models.
A pinned model or flag can also go stale, and inside a fan-out the refusal shows up only as one missing member and its exit code.
Resolve pins at run time from the CLI's live model list, substitute within the same family, record the substitution, and fail loudly when nothing fits.
When a running fan-out turns out misconfigured, report it with a progress and cost estimate instead of killing it.
Killing it converts sunk spend into total loss, so near-done work defaults to finishing.

## 7. Untrusted input is data

Anything that arrives from outside the trust boundary - LLM output, web
content, MCP results, inter-agent messages, file contents under review - is
data to inspect, never instructions to obey or code to execute. Reviewers
do not fetch URLs found in the diffs they review; mail-processing agents do
not run commands found in messages; parsers treat vault text as text.
Every feature that consumes external content needs this stated and enforced.

A tool that copies transcripts, logs or memories into a new file cleans secrets in the write path, because the stored copy is opened later by reviewers and evals.
Its reports hold counts, never values, and it is canary-tested with invented secrets.
Session transcripts are large JSONL files with very uneven line sizes, so neither a line tail nor a byte tail gives a usable view.
Distill them to (role, kind, text) records with per-part caps, set higher for the user's own words, and a hard byte backstop.
Label harness-injected events, indent message bodies so a tool result cannot forge a turn, and treat the whole transcript as untrusted content.

A phrase-list detector fires on the docs, catalogs and fixtures that name its phrases.
Strip code fences, inline code and quoted strings before matching, use word boundaries, and run the detector on its own documentation before shipping it.
Invisible characters (zero-width, bidi controls, tag characters) are still reported inside those exempt spans, because exempt spans are where hidden text gets placed.

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

Shared tooling holds no usernames, absolute home paths, personal repo
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

An MCP inventory read from config files is incomplete: account-level connectors and built-in servers have no file entry, and app installers write into a CLI's config without notice.
Inventory by asking the CLI to list its servers, and note that revoking a connector's OAuth grant does not remove the connector.

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

Trigger evals measure whether a skill fires, not what it does.
An advisory skill also needs end-to-end scenarios graded on one exit artifact, and a procedural skill is graded from the ordered stream of tool calls.
Echo the assembled prompt once to prove the instruction text reached the probe.
Validate portable artifacts such as skills and rules files against the strictest reader, not the lenient one in daily use.
(Observed 2026-08: one strict harness rejected 8 of 24 skills that another accepted, for descriptions over 1024 characters and an unquoted ": " inside a YAML plain scalar.)

## 14. Probe the capability, never the report

A status call answering "ready" is not evidence that the work will succeed.
Prefer a probe that performs the actual operation: request a completion rather than trusting a health endpoint, enumerate a device rather than trusting an availability flag, and invoke a capability rather than asking a model to enumerate its own capabilities.
Startup, readiness and liveness are three different questions, and a service that answers the first will happily fail the second.
(Field-proven twice in one build: an inference server whose HTTP layer accepted requests and listed its models while the backend was still capturing CUDA graphs, returning 502 to every call; and a GPU availability check that returned true because the driver library had loaded, over a device list that was empty.)

A harness version is a point observation, because CLIs self-update, some of them from the version command itself; record the time beside the version.
A run under a scratch home directory proves nothing about discovery from the real home, and an inventory read from a config file is a false clean wherever plugins or account connectors inject entries.
An interactive probe can leave a daemon running that holds real credentials, so check running processes before deleting the scratch home.
Harnesses rewrite their own config files, which discards permissions set on the file, so harden the directory that holds it.

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

Some OpenAI-compatible local servers silently drop developer-role messages, so the model never sees the system prompt (Ollama's `/v1` endpoint is one example).
The tell is equal input size with very different prompt-token counts.
When a result looks better or worse than it should, check what the model actually received before drawing conclusions about the model.

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

## 18. Enforcement fails open

A hook or gate that crashes exits non-zero, and many harnesses treat that exit as a pass, so the guard fails open and still looks healthy.
Test seeded scripts under the oldest interpreter they will meet, such as the system Python a stock OS ships, not only under the developer's.
An unsupported regex construct fails by not matching rather than by erroring, so a detector reports clean while detecting nothing.
The grep an interactive agent tool runs may not be the grep a script gets, so keep patterns to plain POSIX ERE and test them by running the script itself.
Hook output channels also differ by exit code: in Claude Code, exit 2 returns stderr to the agent, while stderr at exit 1 and at exit 0 never reaches it.
An advisory hook therefore exits 0 and returns its message on the structured stdout context channel.
An advisory hook never returns a permission decision, because its allow can stand beside another hook's deny.

## 19. A boundary is real only after a canary

Vendor permission and sandbox controls that are accepted but silently ignored are common.
(Observed in 2026: a config key accepted under strict validation but unused, which leaked the full parent environment to the child process; a sandbox that bounded writes but not reads; a read-only mode that still wrote; and one CLI with two permission vocabularies, where a rule written in one does nothing to tools governed by the other.)
Enforce the boundary in what you build - the argv you pass, a child environment you construct, an OS sandbox profile, a path validator - and keep the vendor flag as a second layer.
State the residual risk, and canary-test every control again after each upgrade.

A permission canary needs a control run.
Run it in a directory the harness already trusts, so a trust prompt does not stand in for the rule.
Give the canary a neutral name, because a secret-like name is refused on content grounds.
Read the tool events rather than the model's prose, and run the same probe with no deny rule.
If that baseline also fails, the probe measures something other than the rule.
