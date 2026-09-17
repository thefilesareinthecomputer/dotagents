# Profiling and validation

Finding out what a source actually contains before committing to it, and building checks
that can fail for the reason you care about.

**Up:** `architecture-decisions.md` decides whether you buy a profiling tool or build the
control plane. **Down:** the screens designed here become the tests in `transform-dbt.md`
and the alert thresholds in `observability.md`.

## Contents

1. [Profiling as an admission gate](#1-profiling-as-an-admission-gate)
2. [Profile the catalog, not just the data](#2-profile-the-catalog-not-just-the-data)
3. [The metric inventory](#3-the-metric-inventory)
4. [Cost strategy: what to compute where](#4-cost-strategy-what-to-compute-where)
5. [Relationships, keys and the foreign-key graph](#5-relationships-keys-and-the-foreign-key-graph)
6. [Screens: the four ascending scopes](#6-screens-the-four-ascending-scopes)
7. [What to do when a screen fails](#7-what-to-do-when-a-screen-fails)
8. [Modelling quality events as data](#8-modelling-quality-events-as-data)
9. [Validating a load](#9-validating-a-load)
10. [Reconciliation and cutover](#10-reconciliation-and-cutover)
11. [Checked and inconclusive](#11-checked-and-inconclusive)

## 1. Profiling as an admission gate

**Profiling gates source admission, and it happens twice.** A light strategic pass at
candidate identification produces an early go/no-go; a long tactical pass during modelling
and pipeline design produces the cleansing requirements. The strategic pass exists precisely
so a source's unsuitability is discovered before commitment rather than months in. Its
output is either a change request to the source owner or a specification for the quality
subsystems.

**Profiling output is what sizes the cleansing machinery.** "How much data-quality apparatus
does this pipeline need" has no answer before profiling and a cheap answer after it. It is
also the answer to "what is the minimum I should do": run the full metric inventory in §3 first, then decide.

**The profiler's real output is a draft configuration plus an explicit list of what a
machine cannot settle.** A per-table verdict should include an explicit **"verify manually"**
value, which converts strategy assignment from opinion into a table-driven decision and
makes the manual verdict a deliberate refusal to guess rather than a gap.

**Distribute the profiler as an importable artifact rather than a paste-in snippet, and
delete the run afterwards.** A one-off profiling script that survives becomes an extraction
path nothing monitors, no schedule governs and nobody owns.

**Only a subset of the intake checklist should gate writing a configuration row.** A
ten-point gate before any table may land blocks the legitimate case of sampling a wide
source for analysis, so the gate gets bypassed wholesale. Mark the
required-before-configuration subset explicitly, and let the rest be advisory.

**Two human questions that profiling cannot answer and that change the architecture:**

- **Identify early who the recognized authority on the source data model is**, or the
  platform team re-derives institutional knowledge that already exists in someone's head, at
  higher cost and error rate.
- **Verify the headline scope claim before it sizes the plan.** An order-of-magnitude figure
  stated once at onboarding, hedged, corroborated nowhere, and sizing the largest workstream
  is an unratified claim, and by the time anyone checks it will already have constrained
  tooling selection.

**Audit a source capability before designing around it, and audit it before designing around
its absence.** Change capture is enabled per table by whoever owned the source at the time,
so coverage is arbitrary rather than uniform. **An infeasibility assumed rather than tested
is the most expensive kind of assumption, because it buys a permanently more complex
architecture** to work around a constraint that may not exist.

## 2. Profile the catalog, not just the data

One pass per source against the engine's own system views, before touching a row:

- Declared primary-key columns and their count, and **tables with no declared key at all**
- Identity columns
- Change-capture enablement per table, plus the minimum valid version
- Every temporal column with its type, nullability and default expression
- Approximate row counts

This is cheap, it is often refused-scan-proof, and it answers most strategy questions before
any data moves. Catalog row counts are stale by construction, because statistics maintenance
refreshes them rather than continuous accounting: acceptable for sizing an extract,
unacceptable as a reconciliation figure.

## 3. The metric inventory

What to compute per column, grouped by what the number is for.

| Group | Metrics | What it decides |
|---|---|---|
| Completeness | null rate, blank rate, zero rate, default-value rate | whether a column is usable, and whether an audit column is trustworthy (**any NULL disqualifies it**) |
| Uniqueness | exact distinct count, distinct ratio, duplicate count on candidate keys | the merge key, and nothing else settles it |
| Range | min, max, quantiles, negative and future-dated counts | window bounds, and outlier screens |
| Shape | inferred type, length distribution, regex and pattern inference, **leading-zero test** | landing types, and the identifier-corruption trap |
| Cardinality | distinct count per column, top-N value frequency | dimension candidates, and the low-cardinality mapping problem |
| Temporal | min and max of each date column, freshness, **does the column move** | watermark selection |
| Relational | foreign-key match rate, orphan count, functional dependencies | join safety, and the parent-path question |

**Three of these carry a specific trap.**

**Exact, not approximate, for any decision.** Approximate distinct counts can over-count and
thereby nominate a non-unique column, which is the dangerous direction. Approximate builds
the shortlist; exact settles it. **If the sample hit its row cap, uniqueness within it proves
nothing at all.**

**Leading zeros must be tested for explicitly.** Zero-padded identifiers lose their zeros to
numeric type inference, collapsing distinct identifiers into one. The damage is invisible in
the landed table because the values look like valid numbers, and it surfaces later as a join
that loses or duplicates rows.

**Profile the actual distinct values of every low-cardinality column before mapping it, and
map through an explicit lookup with an unmapped bucket rather than casting to boolean.** A
single-character flag routinely holds null, empty string, `'0'`, `'Y'` and `'N'` at once,
encodings accumulated across application generations. A boolean cast silently picks one
interpretation.

**Profile against the same checks the platform will run after every load**: row count,
freshness, null rate, uniqueness. Then the strategy is chosen from measured behavior and the
live alert thresholds come from observed numbers. The one check that cannot be pre-run is
volume anomaly, because it compares a load against previous loads and has no history yet.

## 4. Cost strategy: what to compute where

**Push computation to the source; do not pull rows to compute.** A distributed reader's
`limit` applies after data crosses the wire, so a naive select-plus-limit drags the whole
table across the network before capping. Push the row cap, the counts and the aggregates
into the source's own dialect.

**Sampling versus full scan is a per-metric decision, not a per-source one.** Description
tolerates a sample. Any metric used as a gate that writes history (uniqueness above all)
needs every row. The asymmetry generalizes: **cheap-and-wrong is acceptable for description
and never for a decision.**

**Bound every source's sample identically** so two profiles are legible side by side however
each source was reached. One per-object row cap, applied the same way everywhere.

**Sorting plus counting is a legitimate profiling instrument**, and a dedicated sort can emit
several differently-ordered outputs from one read. It gives cheap distribution and duplicate
diagnosis without a profiling tool.

**Operational rules for the profiling pass itself.** It should hold no credential of its own,
taking them from the environment's secret store by reference; write nothing that outlives the
pass, because anything persisted becomes an ungoverned copy of source data; and never let one
unreadable object stop the run. Catch per object, report the object and the exception class,
continue. **The failure list is itself a finding: it is the access request nobody has made
yet.** Confirm too that the profiling account can see every row, because role-based row
visibility, availability-group routing and object-level grants all produce clean, successful,
incomplete reads.

## 5. Relationships, keys and the foreign-key graph

**Compute the referential closure of the candidate extract set at scoping time by walking the
foreign-key graph, and decide explicitly for each out-of-set target**: bring it in, or accept
an unknown member. Selecting the extract set from reporting demand alone leaves most
foreign-key targets unextracted, which becomes key-lookup failures and joins that silently
drop facts.

**Read a high null rate on a foreign key as evidence that the modeller chose the wrong parent
path, not that the data is dirty.** That reframing is what turns a cleansing task back into a
modelling question.

**When a source claims full referential density on a business foreign key, ask what the
application does when the relationship is genuinely absent.** If the answer is that it creates
a placeholder parent row, the dimension contains synthetic non-business members and every
count and distinct-count needs a placeholder predicate. **The referential guarantee is real;
the semantic guarantee is not.**

**Declared foreign-key metadata in a long-lived schema encodes constraints with no real
semantic relationship**, so a mechanically shortest derived join path can be semantically
wrong. Derived paths need a source owner's review, and multiple equal-length paths must be
flagged ambiguous and signed off rather than tie-broken arbitrarily.

**"Not currently used" means different things to a report consumer and to a process owner.**
"No report reads it" does not license dropping a table; "this does not happen" does.
Reconcile the two before scoping anything out.

## 6. Screens: the four ascending scopes

Quality checks decompose into three ascending scopes plus a statistical fourth. **Most
validation suites implement the first tier and stop.**

1. **Column screens** operate within one column: nulls, range, format, allowed values.
2. **Structure screens** operate across columns: cross-column relationships, hierarchies,
   foreign-key integrity, composite validity such as a whole address being coherent.
3. **Business-rule screens** encode complex, often time-dependent conditions.
4. **Aggregate-threshold screens** fire only when an improbable *count* accumulates, rather
   than on any single row. Nothing in tiers one to three catches "twice as many cancellations
   as any previous day, all individually valid".

**The instruments are also four, and none substitutes for another**: data tests assert
against live rows; unit tests assert transformation logic against mocked inputs; contracts
fail the build on schema drift before any row is read; **source freshness is an SLA on
arrival, which says nothing about content.**

**Set live alert thresholds from numbers profiling already observed.** Thresholds invented at
configuration time are either so loose they never fire or so tight they are muted within a
week. The profiling output is the calibration data, which is one of the strongest arguments
for measuring these four before the source goes live.

**Derive a freshness threshold from the load cadence, per source rather than globally.** The
documented convention is to warn at roughly one load interval and fail at two, and to run the
freshness check itself at least twice as often as the tightest SLA it guards. An estate whose
sources run on different schedules cannot carry one global window without being wrong for
most of them. Where a separate monitor already defines staleness for the same tables,
reconcile the two: a source carrying two contradictory definitions of late is worse than one
that carries none, because each excuses the other.

**A tier-four threshold cannot be set at onboarding, and saying so is part of the design.**
Column and structure screens calibrate from a single profile, but an aggregate-threshold
screen bounds *normal variation*, which one observation cannot describe. Stable bounds need
roughly thirty observations and preferably a hundred, so a daily source is about six weeks
from a meaningful volume check. Configure the screens that can be calibrated now, record the
profiled count as the starting floor, and schedule the variation bound for when there is
history to derive it from. A number invented to fill the field is either never triggered or
muted, which is the failure this whole section exists to prevent.

**Prefer a median-based bound to a mean-based one, and handle seasonality explicitly.** A
z-score assumes normality and is corrupted by the outliers sitting inside its own training
window, so the anomalies it has already seen raise the bar for detecting the next. A modified
z-score over median absolute deviation is distribution-free and resistant to that. Neither
handles seasonality or trend, and a weekday-weekend split is seasonality: the remedies are to
compare like with like by segmenting, or to decompose the series and threshold the residual.

## 7. What to do when a screen fails

**The response to a failed check is a design decision with a default: tag, do not suspend,
and almost never halt.**

- **Halting** requires manual intervention and stops the whole pipeline for one bad row.
- **A suspense file is worse than it looks**: until the records return, the database is
  quietly incomplete, and nobody owns their return.
- **Tagging the row and letting it flow keeps integrity auditable**, because the row is
  present, marked, and countable.

**Where the check runs decides whether it prevents anything.** A quality check that runs
after the write commits and only appends results is **detection, not prevention**. The load
has already succeeded and the bad rows are readable. If you need prevention, the assertion
has to run before the write, or inside a pipeline construct that can fail the update. Knowing
which one you have is the point.

**The tag-do-not-halt default is about a bad row, and it does not survive a destructive
write.** Tagging assumes the row is present to tag and that the prior state is intact. Under
a full overwrite or a dynamic partition overwrite neither holds: a short or empty pull
replaces good rows with nothing, there is no row to mark, and the check that fires afterwards
reports a loss it cannot reverse. **The halt calculus is therefore set by the write mode
rather than by taste.** Non-destructive target, tag and let it flow. Destructive target, the
population assertions run before the write and refuse it.

The cheapest such assertion is a **minimum-row floor**: compare the incoming count against
what the target currently holds, and refuse a full overwrite that would drop it below a
configured bound. It costs one count and it catches the whole class of upstream failures that
present as a successful load of nothing, which is the normal signature of a staging or copy
step that clears its target before writing. Derive the floor from the profiled row count and
allow for the table's own legitimate decline.

**Cleansing carries two mandates that conflict, and the balance must be stated rather than
defaulted:** fix dirty data, versus faithfully represent what the production systems actually
captured. **Silently choosing "fix it" destroys the ability to reconcile with the source.**

**Data-quality defects are indicators of broken business processes, and a purely technical
fix routes around the real problem.** The canonical demonstration: constrain a required
identifier field to a valid format, and the data-entry operator, lacking the real value,
supplies a syntactically valid fake. The quality metadata from the cleansing subsystems is
the evidence base for fixing the process upstream, which is the only durable repair.

## 8. Modelling quality events as data

**Model data-quality events as data, not as logs.** A dimensional error-event schema whose
fact grain is "one error thrown by one screen", dimensioned by date, by batch or processing
step, and by screen (which encodes the test criterion, where its code lives, and what to do
on failure), plus a lower-grain detail table at "one field in one record participating in one
error". This converts quality into a measurable time series with trends and thresholds
instead of a log to grep after an incident.

**Attach the load's metadata context to the loaded rows themselves.** An audit dimension
carries screen versions, quality scores and error categories as at the moment each fact row
was created. A clean run produces one audit row shared by every row loaded, and each error
condition adds one. Row-level provenance becomes queryable without a separate lineage system.

**Build this rather than buying it.** The screens encode your business rules and the schema
encodes your grain, which is exactly the part no vendor can supply. Buy the analysis tools,
build the control plane.

## 9. Validating a load

**Validate a load with four checks, in this order, and then run it again.**

1. **Did it land, and did the checkpoint advance** (and not go backwards).
2. **Is the key unique in the target** - zero rows is the pass condition.
3. **What did the quality metrics say, and are the expected ones present.**
4. **Does the schema match.**

**Then run the load a second time and confirm no duplicates.** This is the strongest cheap
validation there is: a mis-set incremental column, a missing merge key and a non-idempotent
write all surface on the second run and are **invisible on the first**. One extra run catches
more configuration defects than any other single step.

**An empty quality-check result is not a pass.** Checks that only run when a threshold is
configured produce no rows when nobody configured them, which is visually indistinguishable
from all-clear. **Validation must confirm the expected metrics are present**, not merely that
nothing failed. This is the concrete form of the law that a check which cannot fail is worse
than no check.

**A short read that returns cleanly is worse than a failure, and it needs two independent
controls.** A source mid-reload upstream returns a fraction of its rows with no error;
against a full-overwrite target it destroys the good data while every log says success.
Either of two controls catches it, and you want both: a **volume-anomaly check** comparing
this load against previous loads, and a **write strategy that cannot destroy history in one
run** (a windowed replace, or a staged load promoted only after a row-count assertion).

**Never use a full reload to repair stale or incomplete data.** It replaces the target with
whatever the pull returns, so against an incomplete pull it converts a partial problem into a
total one. The correct recovery is to re-run the idempotent windowed load, having first
confirmed the source is enabled and any staging location is populated.

## 10. Reconciliation and cutover

**Reconciliation targets come from the business, and they must be named before building.**
The intake question is: which existing report, reconciliation, total or spreadsheet must this
tie to, for which periods, and who signs off. **Without a named baseline and a stated
tolerance, validation becomes an argument at the end of the project instead of a test.**

**Reconciliation between source and landed data is a distinct discipline from row-level
validation.** Row counts, control totals and checksum comparison answer "did everything
arrive"; column screens answer "is each row sane". Neither detects the other's failures.

**Prove equivalence before cutover with a parallel-schema, per-table, two-way comparison.**
Run the replacement pipeline into a compare schema and diff each table in both directions
(rows in A not in B, rows in B not in A) as well as at row-count level. **The comparison
macros in the common tooling need a unique key on both sides, which is a prerequisite rather
than a detail** - and the first thing the exercise usually reveals is that the key is
missing. For a column that legitimately differs by design, exclude it explicitly and record
why; never weaken the comparison globally to accommodate one column.

**Validation and sign-off are separate roles from engineering, and the intake should name the
person.** A named validation owner per data product, distinct from the builder and distinct
from the ongoing support owner. **Unassigned validation ownership is the most reliable
predictor of a delivery that stalls at "is this right?"**

## 11. Checked and inconclusive

- **Open-source profiling tooling** (ydata-profiling, whylogs, catalog-embedded profilers)
  was not verified for licence, current version or maintenance status. The build-versus-buy
  verdict here favors buying, but no specific tool is endorsed on verified evidence.
- **Great Expectations Core versus Soda Core**: GX 1.0 restarted versioning with a deliberate
  API break from the 0.18 line, which is retired, so the upgrade is a rewrite of the config
  and API surface rather than a version bump. Soda Core moved to Elastic License 2.0 while
  repository badges still showed the previous licence, and v4.0 broke the v3 checks language.
  Verified 2026-07-29. Neither licence file was opened directly; **check the LICENSE at the
  tag you intend to pin.**
- **Platform-native validation syntax** (declarative pipeline expectations and their
  warn/drop/fail modes, data-metric functions, managed quality monitoring) is version-sensitive
  per platform and belongs in `platform-notes.md` rather than here. It was not verified in this
  pass.
- **Anomaly-detection baselining periods and sensitivity tuning** carry no verified guidance.
  The durable principle is that thresholds come from observed profiling numbers; the tool-specific
  configuration is not established.
