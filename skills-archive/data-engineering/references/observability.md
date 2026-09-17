# Observability

Knowing that a pipeline is healthy, and specifically knowing when "no alert" does not mean
"no problem". Silence gets the most attention below, because silence is where the expensive
failures live.

**Up:** `architecture-decisions.md` set the lanes, and each lane has a different evidence
surface. **Down:** what you find here routes to `optimization.md` (slow) or
`profiling-and-validation.md` (wrong).

## Contents

1. [Monitor for absence of success](#1-monitor-for-absence-of-success)
2. [Evidence surfaces differ per lane](#2-evidence-surfaces-differ-per-lane)
3. [Silent-stop mechanisms](#3-silent-stop-mechanisms)
4. [Coupling: the defects that come from missing dependencies](#4-coupling-the-defects-that-come-from-missing-dependencies)
5. [Run metrics worth capturing](#5-run-metrics-worth-capturing)
6. [Lineage and dependency are inverse queries](#6-lineage-and-dependency-are-inverse-queries)
7. [Alert design](#7-alert-design)
8. [Escalation](#8-escalation)
9. [Checked and inconclusive](#9-checked-and-inconclusive)

## 1. Monitor for absence of success

**"No alert, so no problem" is unreliable, and three separate alerting behaviors make it
so.** Failure notifications commonly fire after a delay or after several consecutive
failures rather than on the first; a failure whose cause the tool cannot classify may not
notify at all; and after a sustained failure period a tool may stop retrying and stop
notifying. **Each of those produces a silent window.**

The correction is a single sentence with wide consequences: **monitor for the absence of
success, not for the presence of failure.** A check that asserts "this table has a
successful load newer than N hours" catches every one of those three behaviors. A check
that waits to be told about a failure catches none of them.

**A job that finishes far faster than its history is as strong a defect signal as one that
runs long.** It usually means it processed nothing. Alert on deviation from historical
runtime in **both** directions.

**A completion event is not a success event.** Wiring a downstream trigger to "sync ended"
fires on failures too; the payload carries an explicit status field that has to be read.
Separately, webhook delivery is not guaranteed exactly-once or even at-all, so the
downstream job must be idempotent **and** must have a schedule-based fallback path.

## 2. Evidence surfaces differ per lane

**Monitoring surfaces are not symmetric across ingestion lanes, and the asymmetry must be
written down.** A source fed by a managed connector has no row in your ingestion framework's
configuration table, so it has no configured mode, no watermark, no merge keys, no window,
no schedule tag, no configured quality checks, no run-log entry and no checkpoint. An
operator who opens the framework's run log to debug that source is looking at a surface that
**structurally cannot contain it**, and will conclude that nothing ran.

State per lane where its evidence lives. That table belongs at the top of the runbook, next
to the route-identification query from `source-to-bronze.md`.

**Proving a per-table sync usually requires composing evidence, because there is often no
single "last successful sync for this table" field.** A connection-level success timestamp
proves the connection succeeded, not that any particular table moved rows. Per-table truth is
assembled from the tool's own metadata tables landed in your warehouse: one carrying
per-table row-change counts, one carrying the log of sync events. **The hard limit is on the
log leg, which has finite retention**, so a table last synced beyond that horizon cannot be
proven from the log and only absence-of-rows evidence remains.

**Detecting a never-synced table means reasoning from absence, and you must label which half
of the argument is documented behavior and which is inference.** "Enabled in the schema
configuration but no rows in the per-table activity metadata" is evidence, but the strength
of the inference depends on undocumented behavior of how that metadata table is populated.
Separating the two before asserting a conclusion is the difference between a finding and a
guess, **and the distinction has to survive into the written artifact**, because the reader
will not reconstruct it.

## 3. Silent-stop mechanisms

Four shapes, each of which reports nothing while doing nothing.

**An auto-disable-after-N-failures mechanism with no alert is a silent stop.** Any
self-protecting engine that disables a failing table needs its disabled state surfaced
somewhere a human looks daily; otherwise the protection converts a loud failure into a quiet
one. Put "is it still enabled, and what is its consecutive failure count" at the top of the
triage runbook.

**A two-sided schedule binding creates two distinct silent-nothing states.** Where a
configuration row carries a schedule tag *and* a scheduled job carries a task selecting that
tag, a row with a tag and no matching task never runs, and a task with no matching rows
selects nothing. **Neither reports as skipped, because from each side nothing was
requested.** A row with no tag at all runs only by hand, which is legitimate and must be
distinguishable from the two broken cases.

**Registrations required to make a source live are plural, independent, and produce a partial
pipeline when one is missed.** A new source typically has to be registered in the ingestion
framework's configuration, the staging tool's routing, the transformation project's source
registry, each downstream layer's source list, and the orchestration task list. Because they
are independent, **omitting one produces a pipeline that runs successfully and does part of
the job.** The fix is a single onboarding checklist whose check is "is it present in all N",
plus an inventory recording each source against every registry.

**A frozen watermark reports success forever.** Covered in `source-to-bronze.md`; it belongs
in this list because its observable signature is a green run with a falling row count, and
the monitor that catches it is a freshness check on the *target*, not on the run.

**A parameterless manual run that defaults to everything is a loaded gun.** Where selection
resolves through a fallback chain ending in "every enabled row", leaving all parameters blank
runs the entire estate. Either require a selector or make the empty case a no-op. Do not
document it as a caution, because a caution in a runbook is not a control.

## 4. Coupling: the defects that come from missing dependencies

**A downstream step with no dependency on the upstream sync will read a partial result.**
Where a landing step runs on its own schedule with no completion signal from the connector, a
partial sync produces a partial landing, successfully. **Generous schedule buffering is a
mitigation, not a fix**; the fix is explicit coupling, whether a completion signal, a sensor,
or a single orchestrator owning both steps.

**Single-table read consistency does not give you cross-table consistency.** Snapshot
isolation on a transactional table format means a reader never sees a torn row from one
table mid-write. It says nothing about several tables being loaded independently: a job
reading a fact and its dimension mid-load sees a fact row whose dimension member does not
exist yet. **To a business user that reads as missing or mis-attributed revenue, not as a
race condition.** Buffering the schedule reduces the probability; only a coupling mechanism
removes it.

**A file-staging step that deletes its destination before copying creates a silent empty
failure.** Delete-then-copy leaves the folder empty when the copy delivers nothing, the
downstream load ingests zero rows successfully, and against a full-overwrite target the
business sees an empty or truncated report. Two fixes: copy to a new dated location and
switch a pointer, or assert a minimum file count and row count before the load may proceed.

## 5. Run metrics worth capturing

**A scheduler that does not emit process metadata makes the pipeline a black box, and
monitoring is the entry point for all performance analysis.** Capture per run: step reached,
start time, duration, records processed, error summaries, actions taken. **Log to a database
rather than to text**, so trends are queryable rather than greppable.

That per-run record is what makes the two-directional runtime alert possible, what makes
volume-anomaly detection possible, and what turns "it feels slower lately" into a series.

**For any log-based pipeline, consumer lag (latest offset minus committed offset) is the
primary health metric, and dead-letter depth greater than zero is an alert rather than a
chart.** The three dead-letter failure modes to design against are poison pills, retry
storms, and silent accumulation. The third is the one that goes unnoticed, because nothing
about it is loud.

**Cloud monitoring metric definitions carry semantics you must read before building an SLO on
them.** Two concrete traps from managed messaging: dead-lettered messages are not counted as
outgoing, and an auto-forwarded message counts as incoming only on the destination entity. A
dashboard built on the naive reading of those counters silently misstates throughput and
loss, which is worse than having no dashboard because it is trusted.

## 6. Lineage and dependency are inverse queries

**Both are required, for different audiences.** Lineage runs backward from a delivered number
to its physical sources and every transformation between: this is the compliance answer.
Dependency runs forward from a source element to every downstream table and report affected:
this is the change-management answer, the one that says what breaks when a source system
changes. **Systems that provide only lineage leave impact analysis manual.**

**A platform's automatic lineage covers only the segment executed on its own compute, and the
gaps are structural rather than incidental.** Read-write edges between governed tables and
columns come free for queries run on platform compute. What it structurally cannot tell you:

- anything **upstream of the landing point**, because that read happened elsewhere
- anything **moved by an external tool**
- anything **downstream of the platform boundary**, such as which report consumes a curated
  table
- any transformation expressed **outside a governed query**

Each gap needs a deliberate mechanism, and **"we have lineage" is a claim about one
segment.**

**Automatic lineage is a rolling window, so it is not a durable record.** System-table lineage
typically retains a fixed rolling period and is often not configurable, so any estate-level
lineage asset intended as a durable record must **snapshot it on a schedule**. Note the event
that silently breaks historical continuity: renaming or recreating an object, because
historical rows point at an identity that no longer resolves. **A planned schema migration is
therefore a lineage event as well as a code event**, and the snapshot has to happen before it.

**Connecting the curated layer to reports requires the BI platform's own administrative APIs,
and the obvious response field is not the one you need.** A scan-style admin API's default
response typically gives a data source's server and database name rather than the table.
Table-level granularity comes from an explicit detail parameter, and that parameter is often
gated by a tenant-level administrative setting. **Have a fallback ready for when the setting
is refused**: parse the semantic model definitions from source control, or require reports to
declare their sources in a register.

**Distinguish pipeline-run lineage from business-logic lineage.** A run log tells you a table
loaded; it tells you nothing about what a transformation did. Only the second satisfies a
capture-before-retirement mandate, and confusing them is how a migration discovers late that
it has recorded schedules rather than logic.

## 7. Alert design

The design goal is a small number of alerts that are always worth reading. Every alert that
fires without requiring action trains people to ignore the channel, and a muted channel is
indistinguishable from a healthy platform.

| Signal | Fires on | Why it earns a page |
|---|---|---|
| Freshness on the target | no successful load newer than N | catches frozen watermarks, silent disables, unbound schedules, all at once |
| Volume anomaly | this load versus previous loads | the only control that catches a clean short read |
| Runtime deviation, both directions | far slower or far faster than history | far faster means it processed nothing |
| Uniqueness on the merge key | more than zero duplicate keys | catches a fanned-out merge before history accumulates |
| Dead-letter depth | greater than zero | silent accumulation is the failure mode |
| Disabled or paused state | any object auto-disabled | converts a silent stop back into a loud one |
| Expected-metrics-present | a quality metric missing entirely | an empty result set is not a pass |

**Set thresholds from numbers profiling already observed** rather than inventing them, per
`profiling-and-validation.md`. Invented thresholds are either so loose they never fire or so
tight they are muted within a week.

## 8. Escalation

**Escalation is designed, not improvised.** Tiered support (help desk, infrastructure,
pipeline owner, developer), automatic notification from the pipeline into escalation, and
**every notification event written to a database** so problem classes, status and resolution
become analyzable. Notification is a component of the scheduler's contract rather than an
afterthought bolted on later.

The reason to persist notification events is the same reason to persist quality events: it
converts incident handling from anecdote into a series you can ask questions of, such as
which source generates the most pages and whether last quarter's fix held.

## 9. Checked and inconclusive

- **Observability tool licences and governance** (DataHub, OpenMetadata, Elementary) were not
  verified. OpenLineage and Marquez were confirmed as LF AI and Data graduated projects, with
  **OpenLineage emitting and specifying while Marquez stores and serves** - a distinction worth
  keeping straight when someone says they "use OpenLineage".
- **How column-level lineage is actually obtained per tool** (parsed from SQL, taken from the
  engine's plan, or not at all) was not established. This matters, because a tool that parses
  SQL misses transformations expressed outside it, which is the same structural gap as platform
  lineage.
- **OpenTelemetry for data pipelines**, as distinct from application tracing, was not
  researched and no guidance is offered.
- **Per-pipeline cost and performance attribution from platform system tables** is
  platform-specific and version-sensitive; the general principle (log run metadata to a
  database) is durable, the query recipes are not established here.
- **Data SLI and SLO definitions with error-budget practice** were not verified against any
  source. The metric list in §7 is derived from the failure modes in this corpus rather than
  from a published SLO framework.
