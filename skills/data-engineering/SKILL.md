---
name: data-engineering
description: Data platform engineering on Databricks, Microsoft Fabric, Snowflake and open source. Use when choosing a platform, layering or boundaries; when picking an engine or dataframe library or a job outgrew one machine; when onboarding a source and weighing CDC against cursor polling; when a dbt or SQLMesh project is laid out or reviewed; when an incremental model leaves stale rows or a MERGE runs far too long; when quality checks must be placed; when a bill grew or must be capped; when catalogs, grants, masking or record matching are set up; and when judging an inherited platform. MUST be used when rows go missing or duplicate while every run reports green. Routes grain and SCD to dimensional-data-modeling, RAG to ai-engineering, quality-threshold choice and anomaly judgment to statistics.
---

# data-engineering

Building and running a data platform, from the decision that picks a shape down to the
line that makes a load wrong. The companion skill `dimensional-data-modeling` is the
theory; this is the practice.

**Altitude is the organizing principle, not the topic list.** "Which platform" and "why
is this MERGE slow" are the same question at different heights, and the value here is
moving between them without losing the thread. Every reference file carries all three
altitudes for its topic, plus explicit up-links and down-links.

| Altitude | Question it answers | What it produces |
|---|---|---|
| Architecture | What shape, which platform, which boundaries, what drives the bill | A decision with its conditions and its reversal cost |
| Implementation | How is this built here, in what order, gated by what | A pipeline, a model, a bundle, a test suite |
| Line of code | Why is this specific thing wrong, slow, or silently incorrect | A diff |

The seams matter more than the levels, because they run downward and they are one-way. A
platform choice forecloses implementation options; an implementation choice forecloses
line-of-code options. A partitioned table forecloses row-level concurrency. A
serverless-only feature forecloses where pipelines can run. When you answer at one
altitude, name what you just foreclosed at the one below.

## Route by situation

| The situation | Go to |
|---|---|
| Choosing a platform, layering, or boundaries; judging an inherited estate; migrate versus stay | `references/architecture-decisions.md` |
| Onboarding a source; picking CDC versus cursor; deletes; what bronze must contain | `references/source-to-bronze.md` |
| Laying out or reviewing a dbt project; incrementality; snapshots; Slim CI; SQLMesh | `references/transform-dbt.md` |
| Picking an engine or dataframe library; a job that outgrew one machine; pandas, Polars, PySpark or DuckDB migration traps; Arrow interop | `references/dataframes-and-engines.md` |
| How a query is written; NULL semantics, anti-joins, window frames, deduplication, CTE behavior, dialect differences | `references/sql-craft.md` |
| Profiling an unfamiliar source; designing a validation suite; reconciliation | `references/profiling-and-validation.md` |
| Catalogs, grants, tags, masking, retention, erasure; matching and golden records | `references/governance-and-mdm.md` |
| Freshness, volume and quality monitors; lineage; alert design; run metrics | `references/observability.md` |
| A slow or expensive pipeline; layout, concurrency, compute selection, query shape | `references/optimization.md` |
| A bill that grew; what drives spend; which guardrails actually prevent it | `references/cost.md` |
| Terraform, asset bundles, CI/CD, environments, promotion | `references/deployment.md` |
| A version-sensitive platform mechanic, or what could not be verified | `references/platform-notes.md` |
| **A symptom you cannot explain yet** | the failure index below, then the file it names |
| Grain, fact table types, SCD semantics, conformance, the bus matrix | the `dimensional-data-modeling` skill |

## The laws

These hold at every altitude and each one has cost real money somewhere.

**A merge is not a deploy, and a deploy is not a release.** One change reaches production
through several channels that fire on different triggers: trunk-sourced code on the next
scheduled run, job and pipeline definitions on deploy, configuration rows on a separate
apply step, cluster and warehouse settings on restart. Between the first channel and the
last, production runs new code against old configuration while every component reports
healthy. Before calling a change live, enumerate its channels and their triggers, then
diagnose by reading what the engine actually reads rather than what the repository says.
Unsequenced multi-channel change has produced a material misstatement at a period close.

**Green is not correct, and a check that cannot fail is worse than no check.** An empty
quality-check result reads as a pass. A dynamic partition overwrite reports success while
stale partitions persist indefinitely. A frozen watermark reports success forever while
processing nothing. Every mechanism you rely on needs a check that can fail for the
specific reason you care about, and you prove it can fail by making it fail once.

**Establish the mechanism before turning any knob.** The instinct on a missing-rows
symptom is to widen a window. That assumes a causal model, and the model is usually
wrong: a retention window governs how far back capture can still reach, not how far back
it re-reads; a downstream rebuild keyed on the wrong date column loses rows no upstream
width can recover. Classify the symptom as a scope miss, an extract miss, or a downstream
predicate problem first. Remediating before classifying is how one bug becomes two.

**Sampled uniqueness is not uniqueness, and approximate cardinality errs toward danger.**
A column unique in a sample is a candidate, not a key. The estimator can over-count and so
nominate a non-unique column, which fans out the merge and writes duplicates into history
that no later correction repairs. Approximate to build the shortlist, exact over every row
to make the decision.

**Prove a column moves before trusting it as a watermark.** "Fully populated" and
"named last-updated" both survive inspection while the column was written once at insert
and never moved. Two observations separated by a known source change is the test. A NULL
anywhere in an audit column disqualifies the column outright, and audit columns are only
trustworthy when the database writes them rather than the application.

**A better source-side signal should delete machinery, not join it as a fallback.** The
cost of a per-source incremental strategy is dominated by human classification and its
drift, not by runtime. When you obtain engine-level change tracking, delete the
compensating branch rather than keeping it. Ask the source owner for the signal before
building around its absence, because nobody usually has.

**The billing unit decides which lever exists.** Every guardrail and every knob either
moves the unit you are billed in or it does not, and the intuitive lever frequently does
not. Reducing sync frequency does not reduce a bill counted in distinct active rows.
Establish the unit (compute-second, DBU, credit, capacity unit, active row, row moved,
byte scanned) before proposing a saving, and see `references/cost.md` for which
guardrails prevent spend versus merely report it.

**Nothing enforces your keys anymore.** Databricks, Fabric Warehouse and Snowflake
standard tables all accept PRIMARY KEY, FOREIGN KEY and UNIQUE as declarative metadata and
enforce none of them, so grain and referential integrity are entirely the pipeline's
responsibility. Worse than inert: `RELY`-style hints let the optimizer act on an
unverified constraint, and the vendors publish warnings that this returns wrong results
over data that violates it. Details in `dimensional-data-modeling`.

**Profiling is a gate, not documentation.** It runs twice: a light pass at candidate
identification that produces a go/no-go before commitment, and a deep pass during design
that produces the cleansing requirements and sizes the quality apparatus. Its output is
either a change request to the source owner or a specification for the screens. A source
admitted without the first pass is a schedule risk discovered months late.

**Layer seams are firm and violating them is the recurring deployment error.**
Infrastructure-as-code provisions the platform (workspace, metastore, catalogs, external
locations, network, grants); the bundle layer deploys the workload into it (jobs,
pipelines, wheels, models, dashboards); CI/CD promotes both behind gates and authors
neither; the transformation framework changes data inside the workload; the container
layer packages what the workload runs. Provisioning a metastore from the bundle layer and
deploying a job from raw infrastructure code are the two standard violations.

## Failure index, by symptom

Failure modes are cheap to look up and expensive to rediscover, and they do not belong to
one altitude. Match the symptom, then read the mechanism where it lives.

| Symptom | Likely mechanism | Where |
|---|---|---|
| Rows missing downstream, runs green | frozen watermark, non-monotonic tool timestamp, or a downstream window keyed on a business date | `source-to-bronze.md` |
| Stale rows persist forever, runs green | dynamic partition overwrite mistaken for a rebuild | `transform-dbt.md`, `optimization.md` |
| Duplicates in history after a merge | non-unique merge key admitted on sampled evidence | `source-to-bronze.md` |
| Quality suite passes on obviously bad data | a screen whose empty result is indistinguishable from a pass | `profiling-and-validation.md` |
| Streaming reader stops; change feed unreadable at one version | a non-additive schema change applied as rename-plus-create-plus-drop | `source-to-bronze.md` |
| Source database disk fills | a stalled log-based capture pinning write-ahead-log retention | `source-to-bronze.md` |
| Deletes never arrive | query-based capture miscategorized as CDC | `source-to-bronze.md` |
| Bill jumped with no volume change | re-enabled table resyncing from zero, or a resumed connector paying the pause | `cost.md` |
| A job finishes far faster than usual | it processed nothing; treat as a defect signal, not luck | `observability.md` |
| Stage inexplicably slow, should be CPU-bound | whole-stage codegen fell back to interpretation past the method-size limit | `optimization.md` |
| Concurrent writes conflict on the same table | partitioning where liquid clustering or row-level concurrency was needed | `optimization.md` |
| A variable did not expand | interpolation phase mismatch, not syntax | `deployment.md` |
| Hand edit to a resource reverted | the bundle layer owns it; configuration is the source of truth | `deployment.md` |
| First production deploy fails on a path | a current-user-interpolated path plus a missing service principal | `deployment.md` |
| One team's deploy broke another's pipeline | schema compatibility mode is a deploy-order contract | `governance-and-mdm.md` |

## Deterministic check

`scripts/dbt_audit.py` audits a dbt project from its `manifest.json`. It never touches a
warehouse and never runs a query.

```
python3 scripts/dbt_audit.py target/manifest.json
python3 scripts/dbt_audit.py target/manifest.json --json
```

EXECUTE it; do not read it as documentation. It flags staging models that join, models
with no tests, sources with no freshness block, marts selecting straight from sources,
arrival timestamps used as an incremental event boundary, and other mechanical faults
listed in its own output.

**What it cannot see.** It reads structure, not data, so it cannot tell you whether a
key is unique, whether a watermark moves, whether a partition column is right for the
query pattern, or whether the numbers are correct. A clean run means no mechanical fault
was visible in the manifest, never that the project is sound. Silence is not approval.

## Judgment pass

After the mechanical checks, before shipping:

1. **Which channels does this change reach production through, and in what order?** If
   more than one, what runs between the first and the last.
2. **What can fail here, and has it failed once on purpose?** Name the check and the
   input that trips it.
3. **What is the billing unit, and does this change move it?** A saving that does not
   move the unit is not a saving.
4. **What did this decision foreclose one altitude down?** Say it out loud, in the
   decision record.
5. **Is the source signal the best available, or the best available without asking?**
6. **What does this commit us to operating?** Every self-hosted component transfers a
   named operational burden; if you cannot name it, you have not chosen it.
7. **How would we back this out?** Write the reversal cost into the decision record while
   it is still cheap to establish.

## Files

| File | Covers |
|---|---|
| `references/architecture-decisions.md` | platform archetypes and their triggers, layering, table format and catalog, boundaries, migrate versus stay, ranked open-source options |
| `references/source-to-bronze.md` | source archetype routing, change-capture mechanism selection, deletes, watermarks and windows, the bronze contract |
| `references/transform-dbt.md` | staging/intermediate/marts, incremental strategies, snapshots, Slim CI, tests, adapter differences, SQLMesh |
| `references/dataframes-and-engines.md` | selection matrix by data size and memory model, eager versus lazy, pandas/Polars/PySpark migration traps, DuckDB as a dataframe API, Arrow interop, migration order |
| `references/sql-craft.md` | three-valued logic, anti-joins and the NOT IN trap, window frames, QUALIFY deduplication, CTE materialization, dialect differences that change a result |
| `references/profiling-and-validation.md` | profiling metric inventory and cost strategy, screen taxonomy, error-event schema, the data test pyramid, reconciliation |
| `references/governance-and-mdm.md` | catalog object models and grant mechanics, tags and ABAC, retention and erasure, matching, survivorship, golden records |
| `references/observability.md` | freshness, volume, quality and run metrics, lineage versus dependency, alert design, incident runbook shape |
| `references/optimization.md` | triage order, layout and clustering, shuffle and skew, compute selection, query shape, file physics |
| `references/cost.md` | billing unit per platform and tool class, what moves it, the guardrail inventory, chargeback |
| `references/deployment.md` | the layer seams, Terraform estate layout, bundle mechanics, environments, promotion, channel sequencing |
| `references/platform-notes.md` | dated per-platform mechanics and the could-not-verify register |
| `scripts/dbt_audit.py` | manifest auditor (execute) |

## Staleness convention

Platform mechanics carry the date they were verified, inline, because they rot at a rate
worth making visible. Every reference file ends with a **Checked and inconclusive**
register: what was looked for, and why it could not be settled from a primary source. An
honest register beats a confident guess, and a claim with no date should be treated as
unverified rather than as current.
