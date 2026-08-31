# Source to bronze

Getting data out of a source and onto the platform without losing rows, duplicating them,
or paying twice. This is where most silent wrongness originates, because the pipeline's
own reporting cannot see a row that was never extracted.

**Up:** the decision that put you here is in `architecture-decisions.md` (which platform,
which lanes exist, whether a landing zone is worth its storage).
**Down:** what you commit to by choosing here lands in `transform-dbt.md` (a source with
no delete signal forces a reconciliation job downstream) and `cost.md`, since choosing the
route is what fixes the billing unit you will be arguing about later.

## Contents

1. [The order of operations](#1-the-order-of-operations)
2. [Route versus strategy](#2-route-versus-strategy)
3. [Change-capture mechanism selection](#3-change-capture-mechanism-selection)
4. [The load strategy table, and what each does to a delete](#4-the-load-strategy-table-and-what-each-does-to-a-delete)
5. [Watermarks, checkpoints and windows](#5-watermarks-checkpoints-and-windows)
6. [Keys at ingestion time](#6-keys-at-ingestion-time)
7. [Managed connector economics and lifecycle](#7-managed-connector-economics-and-lifecycle)
8. [Packaged ERP and SaaS extraction](#8-packaged-erp-and-saas-extraction)
9. [The bronze contract](#9-the-bronze-contract)
10. [Checked and inconclusive](#10-checked-and-inconclusive)

## 1. The order of operations

**Architecture altitude.** Four activities in a fixed order, and every attempt to run them
concurrently costs more than it saves.

1. **Discovery** establishes what the source *holds*: object list, read access, shape,
   types, candidate keys.
2. **Profiling** establishes how the data *behaves*: row counts, freshness, null rate per
   column, uniqueness on each candidate key, ranges, cardinality.
3. **Route selection** picks how the source physically reaches the platform.
4. **Strategy selection** picks, per table, how much is read and what happens to the
   target.

Discovery's sample is what profiling runs against, so discovery necessarily precedes it,
and both precede the first line of configuration. Conflating discovery with profiling
wastes the cheapest window you will ever have.

**Profiling before connecting is a cost decision wherever the tool bills on rows moved.**
A consumption-billed managed connector typically starts its free evaluation window the
moment a connection is created. Connect first and decide the table set by looking at what
arrives, and you spend that window on design instead of validation, while every
table-selection mistake lands as billed volume. Profile out-of-band against the source's
own interface, decide the table set and per-table strategy, then enter the window with a
plan so the window pays for validation.

**Implementation altitude: the profiler's contract.** A profiling pass should hold no
credential of its own (take them from the environment's secret store by reference), write
nothing that outlives the pass, and never become an ungoverned copy of source data. One
unreadable object must not stop the run: catch per object, report the object and the
exception class, continue. That failure list is itself a finding, because it is the access
request nobody has made yet.

Bound every source's sample identically (one per-object row cap) so two sources' profiles
are legible side by side however each was reached. Two front ends, one for query-capable
sources and one for API sources, can share a single profiler if the contract is "return a
frame of records for an object".

**Push the cap into the source's dialect, not the reader.** A distributed reader's `limit`
applies after the data crosses the wire, so `SELECT *` plus a limit drags the whole table
across the network before capping it. Same rule for counts and aggregates: compute them at
the source rather than by pulling rows. Where a scan is refused or unaffordable, the
engine's maintained row-count estimates in its system views are free and stale by
construction, which is fine for sizing an extract and wrong for a reconciliation figure.
Carry the caveat with the number.

**Confirm the profiling account can see every row.** Role-based row visibility,
availability-group routing and object-level grants all produce clean, successful,
incomplete reads. This belongs in the discovery checklist beside protocol and credentials,
not in incident triage.

**Profile against the same four checks the platform will run after every load** - row
count, freshness, null rate, uniqueness. Then the strategy is chosen from measured
behavior and the live table's alert thresholds come from observed numbers rather than
invented ones. The one check that cannot be pre-run is volume anomaly, because it compares
a load against previous loads and has no history yet.

**The profiler's real output is a draft configuration plus an explicit list of what a
machine cannot settle.** Emitting a proposed strategy is half the job. The other half is
the named confirmations: confirm this key is unique over every row, confirm this is a
modified date and not a business date, confirm this table will not cross the size
threshold soon. A recommendation without its confirmations reads as settled and gets
shipped as settled. Where an input is unmeasurable - whether existing rows can be *changed*
or *hard-deleted* after they are written cannot be inferred from a snapshot - assume the
unsafe answer, because that assumption produces the safe strategy, and print the
unanswered question rather than hiding it behind a recommendation.

**Two profiling findings that destroy data silently.**

- **Identifier columns carrying leading zeros must land as strings.** Zero-padded account
  or company codes lose their zeros to numeric coercion, which collapses distinct
  identifiers into one. The damage is invisible in the landed table (the values look like
  valid numbers) and surfaces as a join that loses or duplicates rows. Detect it with a
  leading-zero pattern test per string column during profiling, and fix it at the earliest
  point that can carry an explicit schema. A file lane with an inferring reader is the
  wrong place to discover this.
- **Sampled uniqueness proves nothing about a key.** See [§6](#6-keys-at-ingestion-time).

## 2. Route versus strategy

**Route is a property of the source. Load strategy is a property of the table.** One
source has exactly one route and can carry a different strategy per table. Collapsing the
two into a single "how do we ingest X" question is the most common cause of a wrong
per-table decision.

**The first diagnostic question about any raw-layer defect is which route the source is
on, and the answer must come from a query rather than from memory.** Presence or absence
of a row in the ingestion framework's configuration table is a decisive route test. Make
it one query and put it at the top of the runbook.

**A route rule built only from reachability commits you to recurring cost without ever
mentioning cost.** Rules shaped like "do we own it / does a driver exist / is it managed
SaaS" are all reachability tests. The managed-connector lane carries a per-row recurring
charge plus a per-connection fixed charge that a self-built lane does not; the self-built
lane carries engineering and maintenance load the managed lane does not. Add an explicit
question to the rule: what will this route cost per month once live, and who reviews that
number. The cheapest route to stand up is regularly the most expensive to keep running.

**A lane on the decision tree with no implementation in the estate is a deferred decision,
not a made one.** "Build a custom extractor" is not a route until something exists to
build on. Before committing to build rather than buy, establish the source's access
stability and rate limits, and establish that the team can own a connector's lifecycle:
retries, schema drift, cursor state, on-call.

**Expect a mix per estate, including at least one gated vendor.** Sources with a native
driver, sources reachable only through a bridge to an older connectivity standard, and at
least one vendor-gated system with no public API documentation, where the plan must include
vendor or integrator coordination as a scheduled dependency rather than an assumption.

**Whether to stage to files at all is a per-lane decision.** A landing zone buys replay and
audit: a staged copy lets you re-drive a load without re-reading the source, and preserves
evidence of what the source actually returned on a given day. A direct-extract lane has
neither; its protection is an idempotent window plus a durable checkpoint, which covers
reprocessing but not "what did the source send us". Decide per lane and state what you
would measure to know the landing zone earned its storage and its operational surface.
Where the engine bills or scans per byte, land columnar, typed and compressed files:
column and predicate pruning plus splittability cut scanned bytes substantially and
preserve types, which avoids downstream inference errors.

**Replay cost differs per lane, and one lane usually has no replay control at all.** A
framework lane replays by rewinding a checkpoint and re-running. A staged lane replays
from retained files. A managed-connector lane replays only by asking the connector to
re-sync, which is a billed operation whose cost you do not control. Knowing which lane a
defect is on tells you which remediation is even available.

## 3. Change-capture mechanism selection

**Architecture altitude.** The mechanism decides which correctness guarantees you can
offer downstream, so it is an architecture decision wearing implementation clothes.

| Mechanism | Sees updates | Sees deletes | Source impact | Prerequisite you do not control |
|---|---|---|---|---|
| Full extract each run | yes | yes | full scan per run | none |
| Timestamp / cursor watermark | only if the column moves | **never** | filtered read | a column that provably moves |
| Monotonic identity watermark | **never** (inserts only) | never | filtered read | an ascending key |
| Engine-level change tracking | yes, regardless of app logic | yes | light | source owner enables it |
| Log-based capture | yes | yes | near zero, reads a log already written | log exposure, stable row identity, retention |
| Full-diff compare | yes | yes | one full read per cycle | ability to push comparison to the source |

**Timestamp extraction structurally cannot capture deletes**, because a predicate can only
see rows that still exist. Where neither change tracking nor log capture is available, the
safety net is a periodic key reconciliation: compare the full set of source keys against
the landed set and delete the difference. Its cost is one full key scan per cycle, and it
is a distinct scheduled job with its own budget rather than a flag on the main extract.

**Query-based managed connectors are frequently miscategorized as CDC.** A connector that
polls a cursor is not reading a change log, and every delete-detection assumption
downstream breaks on that difference. Establish what a connector's incremental mechanism
actually is before reasoning about any of its warnings or limits, because guidance scoped
to log-based capture does not transfer.

**The cost of a per-table watermark design is dominated by human classification and its
drift, not by runtime.** It requires classifying every table, verifying per table that a
modified-date column exists and is trustworthy, and choosing a lookback per table.
Engine-level change tracking collapses all of it to one strategy plus one new metadata
field, the key column for the change-function join. It wins because it removes a human
decision surface, not because it is faster. It also removes two correctness bug classes
outright: it captures updates regardless of whether the application maintains a
modified-date (back-end scripts and bulk fixes bypass application logic and silently break
that assumption), and it reports deletes.

**So ask the source owner for the signal before building around its absence.** When you
obtain it, delete the compensating per-table branch rather than keeping it as a fallback.
A better source-side signal should delete machinery.

**Prefer lightweight change tracking over full log capture when the binding constraint is
load on the production source rather than fidelity.** A defensible preference order driven
by source load, operational complexity, deployability and replayability: a custom
watermark with externally persisted state, then the orchestrator's native capture, then
source-database log capture as an explicit last resort.

**Log-based capture on the source database has one failure mode that takes the source
down.** A stalled connector pins write-ahead-log retention and the log grows until the disk
fills. The mitigations are not optional hardening: a heartbeat table so the slot keeps
advancing during quiet periods, the narrower replica-identity setting rather than the full
one on captured tables, narrow payloads, and partition-plus-drop for cleanup because
row-level deletes themselves bloat the log.

**Transaction-log scraping is the last resort because its failure mode is destructive and
out of your control.** When a production log fills, the responsible administrator's fastest
fix is to empty it, and every change in it is gone. If forced onto this path, negotiate a
dedicated log.

**Message-queue-derived change capture has no replay.** Lose the connection, lose the
changes.

**Change-tracking retention is a first-class documented artifact per source system**: which
tables are tracked, the retention window or an explicit "unknown, needs confirmation", and
the required response per failure mode. A stored position older than retention means a full
reload or a bounded backfill; a cleanup gap means a rebuild. Compare the stored position
against the source's minimum valid version and fall back deliberately. Test it by forcing a
stale-position scenario in the lowest environment. Where detection is deferred, deferring
it *with the gap written down* is the acceptable form.

**Push change filtering as early as possible, ideally before any bulk transfer.** Every
byte filtered at the source is a byte not paid for in movement, storage, transactions and
scanning, four times over.

## 4. The load strategy table, and what each does to a delete

**"How much do we read" and "what do we do to the target" are independent settings, and
neither implies the other.** Read scope (full, incremental, merge-scoped) and write
behavior (overwrite, append, merge) form a matrix. Documenting them as one "load type"
hides the combinations that are legal but unused, and the first person to configure an
unused combination is doing untested work on production data. Implementation is not
evidence of correctness: being first to configure a never-used code path warrants a
dev-environment proof and a second reviewer.

| Strategy | Choose when | Requires | Reflects a source delete |
|---|---|---|---|
| Full overwrite | table is small or stable, or has nothing reliable to filter or key on | nothing | yes, if unpartitioned |
| Incremental append | table is large and rows are only ever inserted | a filter column | never |
| Incremental replace | table is large, rows change or arrive late, no reliable key | a date column | only inside the window |
| Merge | table is large, rows change, a reliable unique or composite key exists | key **and** ordering column | never |

Append filters on `>= checkpoint`, so the boundary row is re-read every run and the write
must tolerate that. Incremental replace is idempotent over its window, which is what makes
re-running it a safe recovery step.

**Delete behavior, as a runbook table**, because it is the question nobody asks until
reconciliation fails: full unpartitioned reflects deletes; full partitioned reflects them
only within incoming partitions; append never; incremental replace only inside the window;
merge never, because merge has no delete clause. If the source can hard-delete and
downstream accuracy depends on catching it, that changes which strategy is correct, so it
must be raised during profiling.

**A full overwrite on a partitioned target can replace only the partitions present in the
incoming data, so calling it a rebuild is wrong.** Whether it does is governed by an engine
setting rather than by the write itself, and the setting's default has varied by engine and
version, so **read the resolved configuration rather than assuming either behavior** - the
two outcomes differ by the entire contents of the table. `platform-notes.md` carries the
per-platform gating with dates. If a source stops emitting a
partition - a closed period, a decommissioned entity, an upstream filter change - the stale
rows sit in the table indefinitely while every run reports success. This is the exact
configuration that produces "the total is right for this month and wrong for last". Call it
a dynamic partition overwrite, and add a completeness check for partitions the source has
stopped emitting.

**A row-count threshold that selects incremental over full is authoring-time judgment, and
nothing enforces it at runtime.** A table onboarded under the threshold and left on full
overwrite keeps paying a growing full-scan cost silently as it grows past it. Nothing
alerts, because nothing reads the threshold at run time. Two fixes and you need both: a
monitor comparing live row counts against each table's configured strategy, and treating
the threshold as a refinement checkpoint whenever a table's work is picked up again rather
than a one-time onboarding answer.

**Line-of-code altitude: two settings containing the word "partition" do unrelated
things.** A read-side partition column (with a partition count and lower/upper bounds)
parallelizes a JDBC read by splitting it into range predicates. A write-side partition
specification determines the target's physical layout and, per above, what a full overwrite
actually replaces. Naming them similarly in one configuration schema guarantees the mix-up.

Read-side bounds do not filter: rows outside them are collected into the first and last
partitions. Set them from a remembered value rather than from the data and you get one or
two enormous tasks with every other executor idle, which presents as a mysteriously slow
job rather than a broken one. Read the actual min and max before the load, at the cost of
one aggregate query per run. **Then remove the read-parallelization settings after the
initial load**, or they fire on every subsequent run, adding planning cost and pinning the
read to bounds that go stale as the data grows.

**Predicate pushdown happens in generated SQL, so a derived incremental column needs a
different predicate form.** Where the incremental column is an expression - a date
assembled from a numeric `yyyymmdd` field, a cast, an alias - the predicate must be
expressed against the expression, not against a column name that does not exist at the
source. The base-column form silently fails or errors at the source, and the fix belongs in
the SQL generator rather than in configuration.

## 5. Watermarks, checkpoints and windows

**A checkpoint and a lookback window are different things, and the second exists because
the first is not enough.** The checkpoint is where the last successful run stopped. The
lookback window is how far back before it the next run rewinds before filtering. Every run
therefore re-reads and rewrites a trailing slice of already-ingested history, which is
exactly how source-side edits and late-arriving rows get picked up.

**A lookback window is only sound if the write is idempotent over that window.**
Re-reading a trailing window is safe with replace-a-window or merge semantics and actively
harmful with append, which duplicates every re-read row. The window and the write mode are
one decision.

**Prove the watermark column moves.** A column populated at insert and never updated is
the most dangerous possible incremental column: the pipeline runs green forever, silently
ingests nothing new after the first load, and the first person to notice is a business user
asking why a figure stopped changing. The test is two observations across a known source
edit. It is the check most often skipped, because the column's *name* implies the answer.
Any NULL in an audit column disqualifies it outright, and audit columns are trustworthy
only when a database trigger writes them rather than the application.

**A business date and a modified date are not interchangeable, and no window width fixes
the difference.** A business date describes when an event happened; a modified date moves
whenever the row is touched. A row posted or adjusted into an already-closed period keeps
its original business date, so a window keyed on the business date will never pick it up
however wide the window is. Profiling cannot distinguish the two, because the shapes are
identical. Ask a human who knows the source.

**The two watermark types need opposite treatment.** For a timestamp watermark, persist the
run-snapshot time rather than the maximum extracted value: it avoids an extra source query
and is immune to source clock skew producing a position ahead of rows not yet visible. For
a monotonic-identity watermark you *must* query the maximum after the copy, because there
is no snapshot equivalent, and its lookback is **zero**, because an identity value either
exists or does not and there are no late arrivals in that dimension.

**Write state on success only.** Failure means the position never advances, so the next run
reprocesses exactly the same window. Combined with an append-only raw layer that makes
reprocessing harmless, at-least-once delivery is sufficient and exactly-once is
unnecessary, which is what licenses a simple extractor. Per-table state as a document in
object storage (one file per environment, source and table) beats a control table when the
extract path must not depend on a database: it buys per-table failure isolation,
hand-editable state during an incident, and environment-agnostic promotion, since an empty
state folder in a newly promoted environment naturally produces a first full load and there
is no separate initial-load pipeline at all. Past a few thousand tables a control table
wins on observability instead, because per-table files stop being greppable.

**Express a window in the unit the checkpoint is stored in, and distrust a config key whose
name states one unit while the engine infers another.** A framework that infers months when
the stored checkpoint is a six-digit period and days otherwise will read the same number
two ways depending on the shape of a value nobody is looking at. Make the unit explicit in
stored configuration, and until it is, check the checkpoint's shape before setting any
window number.

**A period-aligned window and a rolling-day window are different rules, and financial data
needs the aligned one.** For period-dated transactional tables the defensible window is
"current period to date plus the whole of the prior period", because that is the range into
which the business can still post or adjust. A rolling day count approximates it. If the
aligned rule must be expressed in days, use the widest the window can ever be (two
consecutive 31-day months is 62 days); on every other day it reaches further back than
needed, which costs a little compute and changes nothing *because the write is idempotent
over its window*. That clause is what makes the approximation legal.

**Reference and dimension tables do not get the transactional window.** Chart of accounts,
department, location and calendar tables are not period-dated, so a period window is
meaningless on them. Each takes whatever the strategy table selects for it individually.
Scope "the standard window" explicitly to period-dated transaction tables or it becomes
estate-wide folklore.

**Every layer sets its own window, none is derived from another, and a mismatch surfaces
only at a period boundary.** A raw table re-extracting two periods whose downstream fact
model recomputes three, or one, produces a table that disagrees with its own source.
Nothing fails; totals simply differ, and only near a period edge. Whenever history looks
wrong at a period boundary, check both windows. A downstream model that rebuilds in full
has no window to reconcile and is immune.

**Three window traps that send teams to the wrong remediation.**

- **A vendor's "retention" setting is not a lookback setting.** Change-log retention
  governs how far back the *capture mechanism* can still fetch changes, protecting a paused
  or lagging reader. It does not re-read already-synced history. An engineer hunting
  late-arriving rows who finds this number and widens it has widened a setting with no
  bearing on the symptom.
- **A connector's "synced at" stamp is not a monotonic high-water mark.** It records when
  the tool wrote the row and is not guaranteed to increase across concurrent or retried
  syncs, so a downstream `where synced_at > max(synced_at)` filter skips rows stamped below
  an already-advanced maximum, permanently. Window with an overlap and merge idempotently,
  or track processed batches explicitly rather than inferring them from a timestamp.
- **A widened window recovers rows only if the miss was caused by scope.** Two sources given
  the identical widened window can behave differently: one self-heals, the other rewrites
  the same wrong values. The variable is not the window. It is whether the upstream extract
  actually returns the changed rows, and whether the downstream dimension joins fail open
  (drop or null the unmatched row) or fail closed (error). A join that fails open produces
  a silently short result that a re-run reproduces identically. Classify the defect as
  scope, extract, or downstream predicate before touching any window.

**A trailing re-read window is right only for sources whose change signal is a timestamp.**
Log-based connectors have no trailing-window setting because they do not infer change from a
timestamp; the log states exactly what changed. The absence of the feature is a consequence
of the mechanism, not a gap. Conversely a trailing window is *necessary* wherever the
change signal can move retroactively or arrive out of order.

**Late arrival is a per-table property found by profiling, not a global setting.** Two
shapes to look for: a transaction source that remains updateable after insert (often a
legacy invariant that is not fixable, so it needs a wider window or real change tracking),
and a companion staging table holding in-process records that later finalize into the main
table, which means the arrival event and the finalized event are different rows in
different tables.

## 6. Keys at ingestion time

**Sampled uniqueness is not uniqueness, and the failure it causes is unrepairable.** A
column unique across a sample is a shortlist entry, not a merge key. A key that holds most
of the time fans out the merge and writes duplicate rows into history that no later
correction repairs. The sufficient test is an exact distinct count over every row, run at
the source, and it is cheap precisely because the shortlist is short. **If the sample hit
its row cap, uniqueness within it proves nothing at all and the shortlist is empty.**

**Approximate cardinality errs in the dangerous direction.** An approximate distinct count
can over-count and thereby nominate a column that is not unique. Approximate to build the
shortlist, exact to make the decision. The asymmetry generalizes: cheap-and-wrong is
acceptable for description and never for a gate that writes history.

**A merge without an ordering column has lost the ability to decide which candidate row is
true.** Deduplicating an incoming frame to one row per key requires a rank; with no ordering
column an arbitrary row survives. This passes every day-one test, because day one rarely
presents two versions of one key in a single batch, and starts producing wrong answers the
first time the source emits a genuine update inside one window. That is typically a month
later, typically at a period boundary.

**Prefer a composite key of columns that are unique together over minting a surrogate at
ingestion.** A surrogate minted in the raw layer has no source-side meaning, cannot be
reconciled against the source, and becomes a second identity to maintain. Where nothing is
unique and a full pull is unaffordable, ask the source owner to expose a modified date or a
stable key rather than fabricating one.

**A business key identifies nothing across an estate until it is qualified by its source
system.** Different sources reuse the same codes for different entities, so any conformed
dimension assembled from more than one source must carry the source-system qualifier as
part of its natural key, with the surrogate minted over the qualified pair. Omitting the
qualifier produces silent cross-system collisions that look like duplicate members. The
surrogate key mechanics themselves belong to dimensional modelling rather than to
ingestion; settle them before the first merge is written.

**Composite keys break query-composition shortcuts.** Wrapping an existing per-table
extract query to add an incremental predicate keeps the curated projection and filter logic
in one versioned artifact and stops it drifting into a parallel copy, but it breaks on
composite keys. The defensible resolution is to hand-write dedicated incremental queries
for the few such tables rather than build a multi-key parser in orchestration expressions.
The generalizable heuristic: when a generic solution would be more complex than N
hand-written artifacts, and N is small and bounded, write the N artifacts.

## 7. Managed connector economics and lifecycle

**Establish the billing unit first.** Under per-row-per-month billing on distinct rows
touched, the levers that feel like savings mostly are not:

| Action | Effect on a bill counted in distinct monthly active rows |
|---|---|
| Exclude a table | reduces it |
| Exclude a column | typically does not; the row is still active |
| Filter rows | reduces it only if the filter is pushed to the source |
| Lower sync frequency | **does not**; the same rows are still active that month |
| Retain more history | increases it |

Sync frequency and column exclusion are the two teams get wrong most often, both because
they feel like the obvious lever.

**Pausing defers cost into the resume month rather than avoiding it.** A paused connector
keeps its cursor, so on resume it extracts everything that changed during the pause and it
all counts in the resume month. Where the same rows churn every period, pausing can lower
the total, because a row edited three times across three months counts three times when
synced monthly and once when synced once. That is a *derivation from the counting rule*,
not published vendor guidance, and it must be labeled as such before it is repeated to
anyone paying the bill. A long pause also carries a source-side risk independent of what it
saves: if the pause outlives the source's change-log retention, a log-based connector
cannot resume incrementally and falls back to a full re-import.

**Deselecting a table and pausing a connection are not the same operation, and only one is
reversible for free.** Pause preserves the cursor, so resume is incremental. Deselect
discards per-table incremental state, so re-enabling behaves as a fresh initial sync of that
table's whole history, billed on rows synced. "The history already synced once and has not
changed" is reasonable-sounding and does not hold, because the tool is not billing for
change, it is billing for rows moved. What the previously-synced distinction actually buys
is a pre-flight estimate, not an exemption: check per-table sync history before enabling any
previously-disabled set, and account for the connector *class*, because automatic re-sync
is billed differently between log-based database connectors and application connectors.

**Three lifecycle facts that turn into unexpected charges.**

- **A connector that syncs nothing anyone reads still costs a per-connection fixed
  charge.** Auditing for connectors whose destination tables no model, report or query
  touches is a recurring cost-control task with a calculable payoff.
- **Promotion between environments creates a new connection, and a new connection has no
  cursor.** Copying a configuration into another environment produces a distinct connection
  carrying settings and table selection but no sync history, so its first sync is a full
  historical load, billed. N environments running the same connector means N initial syncs
  and N fixed charges, and "bill only in production" requires that lower environments'
  connections do not run at all, which in turn requires cloning production data downward
  rather than syncing it.
- **A connector created through an API defaults to a particular run state, and automation
  that overrides that default has silently made a spending decision.** If creation defaults
  to paused and the script resumes it, the script started a full historical sync. That
  belongs in a review comment and a runbook line, not in a default argument.

**Schema-drift policy has a blast radius, and type changes are governed by a different
mechanism than new objects.** A connection-level drift setting typically governs whether
*new* tables and columns are picked up automatically, blocked, or allow-listed. An existing
column changing type is handled outside that setting, usually by widening to a permissive
type, and some widenings cannot be undone. The drift setting is therefore not the control
you think it is for the case that actually breaks downstream models.

**A type change applied as rename-plus-create-plus-drop is a non-additive change**, which
stops streaming readers and makes the change feed unreadable across that table version.
Consumers reading incrementally need a documented response to it, and the response is
usually a full refresh of that consumer rather than a retry.

**Default deletion behavior is a soft delete, and the opt-in alternative moves work onto
every consumer.** Deleted source rows typically remain in the landed table with a deletion
flag. Switching to full history mode replaces the flag with validity-period columns,
increases billed volume, and obliges every downstream consumer to filter to the current
version, a change that **fails open**: a consumer who does not know simply reads too many
rows and reports a number that is too high.

**Confirm a consumption question with the vendor rather than inferring it from
documentation.** A documentation sentence one research pass reproduced and a later pass
could not is *disputed*, and a subsequent search surfacing the same sentence does not
resolve it, because re-surfacing the same unverified artifact is not independent
corroboration. A live page that no longer contains a sentence is evidence against it. What
settles it is a dated written answer from the vendor against your specific contract. Until
then a client-facing deliverable may describe the mechanism and must not state the price.

**The two named tools behind the abstractions above, checked 2026-08.** No rates or figures
appear below, deliberately, and the paragraph immediately above is why: the mechanisms are
durable and the rate cards are not. What follows is the shape of each meter and the event
that makes it jump.

**Azure Data Factory: the integration runtime is the priced surface, not the pipeline.** The
pipeline itself is a definition and costs nothing to hold. The charges assemble from meters
that teams discover one at a time: orchestration counted per activity run, data movement
counted in data-integration-unit hours for the copy activity, mapping data flows counted in
vCore hours of a cluster the service spins up on your behalf, and self-hosted integration
runtime hours when the movement runs on a machine you own. Three runtimes with three
different economics sit under this: the managed Azure runtime (serverless, per-hour meters
while work runs), the self-hosted runtime (a service you install on a VM you patch, metered
per hour of data movement *plus* the VM), and the provisioned SSIS runtime (billed while it
exists, whether or not anything runs on it).

**The pricing cliff is per-execution overhead meeting a metadata-driven fan-out.** A
`ForEach` over a table list is charged per activity run, and a mapping data flow pays cluster
startup as part of each execution. Five hundred small tables therefore buy five hundred
cluster startups, and on small tables the startup dominates the transfer by an order of
magnitude, so the bill scales with the *number of objects* rather than with the data. Two
mitigations exist and both change the pipeline's shape rather than a setting: a data-flow
time-to-live keeps a cluster warm so consecutive activities within the window skip startup,
and batching many small tables into fewer activities replaces N charges with one. The
default configuration is the expensive one.

**Three smaller ADF charges that recur as surprises.** A data-flow debug session bills while
it is open, so a developer who leaves one running overnight generates a charge nobody
attributes. A provisioned runtime left behind after a migration is pure loss, because
pausing it is an explicit action rather than an idle timeout. And an activity that merely
invokes an external service is metered by ADF *and* by that service, so a notebook activity
is billed twice under two different units, per the billing-unit law.

**Where ADF stops being the cheap answer:** it is orchestration plus copy. Using mapping data
flows as the transformation engine buys a Spark cluster with a designer and a per-run startup
to do work the warehouse would do without either.

**Fivetran: the unit is a distinct primary key touched at least once in a calendar month**,
counted per table per connection. The table at the top of this section is that model. Its
practical shape is that cost tracks *how many rows change*, not sync frequency and not bytes
moved, so a hundred-million-row table with two percent monthly churn is cheap and a
ten-million-row table that some nightly job rewrites in full is not. The most expensive
tables in an estate are frequently ones where an upstream process stamps every row for
reasons no consumer cares about, and the fix is a conversation with the source owner rather
than any connector setting.

**The resync is what blows the bill up, and most resyncs are not deliberate.** A resync
re-reads the table from the beginning and marks every row active for that month, so it costs
roughly the table's entire row count on top of normal churn, in one billing period. What
triggers one: a schema change the connector cannot apply incrementally, notably some type
changes and any change to the primary key; re-enabling a table that was deselected, because
deselect discarded the cursor; the source's change-log retention lapsing past the connector's
position; recreating or re-authorizing a connection; and a vendor-side correction that
requires it. The consequence for cost modeling is that the variance is driven by *events*,
and the events are usually triggered by someone else's change in a system you do not own.
Which resyncs are billed is exactly the kind of consumption question the previous paragraph
says to settle in writing with the vendor.

**Two Fivetran facts that break naive estimates.** The rate is tiered and decreasing, so a
per-row cost measured on a pilot does not extrapolate to production in either direction, and
the tier boundaries come from the contract rather than from the public page. And the meter
counts a row as active once per month however many times it changed, which is the derivation
already noted above: the same churn synced more often is not more expensive, so the intuitive
frequency lever does nothing.

**The crossover, and it is not about data volume.** A managed connector buys three things and
only three: the initial implementation, the ongoing response to API and schema drift, and the
operational apparatus of retries, state and alerting. It does not buy correctness, because
everything in sections 3 to 6 remains yours either way. So the crossover is driven by the
number of distinct sources and their drift rate.

**Build wins when all of these hold**: a small number of sources, on the order of a handful;
each one either a stable versioned API with a cursor or a database with native change
tracking; a schema that moves once or twice a year; a team that already runs a scheduler and
an alerting path, so the marginal operational burden is near zero; and a high-churn row
profile, which is precisely where the metered price is worst while the mechanical work is
unchanged. In that configuration the extraction genuinely is about fifty lines: page on the
cursor, write the raw payload to the landing zone, and checkpoint the cursor atomically with
the write, per section 5.

**Buy wins when** the source count is large, the sources are packaged SaaS with idiosyncratic
APIs, there is no on-call rota, a compliance requirement is satisfied by the vendor's
certification, or a delivery date will not survive a build.

**Price the build honestly, because the fifty lines are its smallest component.** The real
cost is the state store, the alerting path, the schema-drift response, the re-authentication
when a token rotates, the on-call rota, and the successor to whoever wrote it. Name that
burden explicitly before choosing to build, and expect fifty lines to become two hundred the
first time the API returns a nested object or changes its pagination style.

**The hybrid usually beats either pure answer**, and it is measurable rather than a matter of
taste, because the vendor's cost lines are per connector: buy the long tail, build the two or
three high-churn sources whose active-row count dominates the bill.

**Whichever way you go, write down the landed shape before you need to reverse it.**
Replacing a connector with your own code is cheap only if the bronze contract in section 9 is
identical across the swap. If downstream models depend on the connector's own metadata
columns, its soft-delete flag and its type mapping, the replacement must reproduce all of
them, and discovering that during the migration is how a two-week job becomes a quarter.

## 8. Packaged ERP and SaaS extraction

**Packaged ERP clouds do not expose their database, and the bulk extraction surface is a
view layer rather than base tables.** Proposing a direct database connection is rejected on
principle, not on configuration. The supported bulk path is a purpose-built extraction
service over published view objects, where a single view object spans several base tables
and resolves joins, code and lookup decoding, and effective-dating that raw table access
would leave to you. The practical consequence is that *finding the right view object*
becomes the hard discovery problem, because object names encode an internal module
hierarchy rather than a business entity.

**Expect four or five extraction surfaces per packaged suite, and match the surface to the
job.** A bulk extraction service for historical and incremental loads; a REST API for
single-record lookups, which cannot carry bulk because pagination and rate limits make it a
latency and quota problem rather than a throughput one; an interactive reporting layer for
*validating* an extract and never for feeding a pipeline, because it competes for the
resources users are querying; a document or report generator for formatted output; and
often a separate outbound mechanism for the HR domain. Choosing the reporting layer as a
pipeline feed degrades the source instance for its actual users, which carries a political
cost as well as a technical one. Where extract-purposed and reporting-purposed view objects
both exist for what looks like the same data, the naming carries the signal: pull through
the extract-purposed object.

**The authoritative mapping from a view object's attributes to physical tables and columns
is a vendor artifact you must obtain, not something to reverse-engineer.** Build the lineage
mapping once, keep it beside the extract definition, and state a fallback for objects the
artifact does not cover: sample the object, compare against a known-correct report, and
record the inference *as* an inference.

**Extensible field types are absent from an extract by default, and making them appear is a
source-side administrative action with a job to run.** Chart-of-accounts segment columns and
customer-defined fields both fail to appear for the same structural reason: they are not
part of the shipped object definition. The fix is a source-side enablement step plus a
metadata-refresh job, after which an *existing* extract definition usually has to be
revisited to include them. Budget for it explicitly; it is the most common cause of "the
extract landed but the columns the business asked for are missing".

**Read final accounting from the accounting subsystem, not from the transactional table.**
Account columns on a subledger transaction table represent the entry as captured, not as
finally accounted. The authoritative path runs subledger transaction to accounting engine to
general ledger, and the accounting engine holds the final distribution. Reading the
transactional table instead understates or overstates against the general ledger, and the
person who notices is whoever reconciles at period close, which is late and expensive.

**Four mechanical traps specific to this class of source.**

- **The incremental extract's overlap setting is not a lookback over business history.** It
  keys on an internal last-update column in a specific timezone, and the overlap exists to
  catch rows whose update landed near the previous extract's boundary, so a run's effective
  range is "since the last successful extract, minus the overlap". It is not a retry window.
  Set it from the extract cadence: a wide default suits a daily extract and is absurd for an
  hourly one.
- **A normal extract cannot detect deletes, and the vendor's answer is a separate key-set
  mechanism.** Incremental extracts emit changed and new rows only. Capturing hard deletes
  means periodically extracting the full set of active primary keys and reconciling the
  landed set against it, as a distinct scheduled job with its own cost.
- **A column the source computes internally without touching the row's last-modified stamp
  is a permanent loss channel.** If the cursor is the last-modified column and the source
  updates a value without moving it, the changed row is invisible to every incremental run
  at any width. No configuration on either side fixes this. The two mitigations are a
  periodic full refresh of the affected object, accepting the cost, or deriving the affected
  value downstream from columns that do move.
- **When a managed connector drives the vendor's own extraction service underneath, you have
  lost direct control of scope and schedule.** The connector creates and manages extraction
  jobs on your behalf and submits schedules on each sync, and editing those jobs directly is
  explicitly warned against because the connector reasserts its own definition.

**Effective-dated source rows produce multiple rows per entity and will double-count
downstream unless the model chooses a view.** A source table carrying validity-period
columns per version emits one row per version. From the same landed data you can produce a
point-in-time view (filter where the as-of date falls inside the validity period) or a
full-history view (keep all versions and treat the validity period as the type-2 range).
The critical discipline: the *incremental key* and the *effective dates* are independent
concerns. Conflating them - using the validity start as the watermark, or the watermark as
the version boundary - corrupts both the incremental load and the history.

**Per-principal API rate limits are a real ceiling that arrives as tenant count grows, and
sharding across identities is a redesign.** Plan for it before it is an incident. The same
applies to per-dataset refresh caps and finite refresh history on a BI surface: caps
foreclose intra-day refresh without redesign, and finite history means audit and trend data
must be pulled and warehoused externally or it is gone.

## 9. The bronze contract

**State layer contracts as invariants, not guidelines, because every other decision follows
from them.**

- **Raw is append-only and never updated, deleted or overwritten.** It is the audit log.
- **The conformed layer is rebuildable and overwritable.**
- **The curated layer is a replaceable snapshot.**

**The payoff is mechanical: because raw is append-only and the conformed layer is rebuilt
from the full raw set, duplicates from overlapping windows are harmless by construction.**
Deduplication belongs exactly one layer downstream of where duplicates are created. This is
also what makes at-least-once extraction sufficient.

**The price of the append-only contract: every conformed read must select the latest load
per source**, and one expression that forgets it fans out the whole downstream build. Apply
it uniformly, and prefer a shared macro or view over per-model repetition.

**What a bronze row must carry.** Beyond the source columns: arrival or load timestamp,
source system identifier, batch or run identifier, and a row hash where full-diff
comparison or dedup is expected. These are what make replay, reconciliation and
row-level provenance possible; adding them later means backfilling them as nulls, which
makes them useless for the period that matters.

**Name landed files per run, and treat "one file per table" as a trap.** A
`table_source_timestamp[_batch]` convention is debuggable, sortable, immutable and
per-run isolated. One file per table forces overwrite semantics into a layer whose entire
value is immutability.

**Plan compaction at design time.** The known cost of append-only is small-file
proliferation: more files means more file-open overhead, higher bytes-scanned billing, and
higher storage transaction counts. Plan a periodic compaction job targeting roughly 100 MB
to 1 GB files; files under about 10 MB carry disproportionate metadata overhead. **Monitor
storage transaction cost as the early warning that query cost is about to creep**, and
measure the file-size distribution before optimizing anything else in a lake, because
unexpectedly high storage transaction costs usually mean a small-files problem rather than
a volume problem.

**Plain columnar files rather than a transactional table format can be the right call, and
the rationale is what makes it defensible.** Where raw is append-only, ACID and time travel
are not needed at that layer, the query engine pays measurable overhead processing a
transaction log, and adopting the format would push a dependency into the consumption
layer, the trade on offer is source isolation and operational simplicity against ACID and
time travel. The resulting shape, immutable data files plus mutable per-table state files,
is transaction-log-shaped without the transaction log. Record the trade and its
reversibility; neither choice is obvious.

**Two storage-layer mechanics worth deciding deliberately.** Hierarchical-namespace storage
over flat object storage suits a directory-heavy layout, because atomic folder rename is
what makes overwrite-by-swap safe; the named trade-off is that transactions are charged in
fixed-size blocks, so many small files inflate transaction counts. And where a layer is
rebuilt wholesale, blue/green swap it by atomic folder rename: delete the previous
generation, rename current to previous, then rebuild, so the last good version is always one
rename away and consumers never see a half-built layer. Wire the delete step's dependency
on "completed" rather than "succeeded", because a missing previous folder is a legitimate
state. Object versioning on the storage account is the cheap recovery net for a bad
pipeline write, cheaper and simpler than building rollback into the pipelines.

**Verify exact source column casing before writing it into control metadata.** Case
sensitivity between extraction queries and the views over landed files is a live hazard
that deserves a standing rule rather than a guess.

## 10. Checked and inconclusive

- **Per-connector billing treatment of an automatic re-sync** differs between log-based
  database connectors and application connectors, but the exact rule per vendor is
  contract-specific. It is settled by a dated written answer from the vendor against your
  contract, not by documentation.
- **How a managed connector's control of an underlying vendor extraction service interacts
  with that service's own scheduling preferences** was recorded as genuinely unknown rather
  than inferred. Treat it as unknown.
- **Whether a specific connector class can outlive its source's change-log retention**
  cannot be concluded from a warning scoped to log-based capture. Establish the connector's
  actual incremental mechanism first.
- **The named-tool mechanics added to section 7 were written from practice, not from a
  fetched vendor page in this pass (checked 2026-08).** The meter *shapes* are stable and
  are what the section relies on. The specific list of what forces a Fivetran resync, and
  ADF's exact set of billable meters and their names, are the two items to re-verify against
  current documentation before either reaches a client, and no figure from either vendor is
  stated here for the reason given at the end of that section.
- **File-drop and REST archetype mechanics** (completeness signalling, duplicate delivery
  detection, pagination safety under concurrent inserts) are covered in
  `platform-notes.md` with their verification dates, because they are version-sensitive per
  platform rather than general principles.
