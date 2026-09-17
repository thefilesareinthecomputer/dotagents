# Optimization

Making a pipeline faster or cheaper, in an order that does not waste the effort. Most
performance work fails because it starts from intuition about which line is slow.

**Up:** `architecture-decisions.md` picked the engine, which fixed most of what is tunable.
**Down:** a diff. **Sideways:** `cost.md`, because on metered compute a speed win and a cost
win are frequently the same change, and on capacity-based platforms they are not.

## Contents

1. [Measure composition first](#1-measure-composition-first)
2. [The triage order](#2-the-triage-order)
3. [Lazy engines: the script's shape is not the work's shape](#3-lazy-engines-the-scripts-shape-is-not-the-works-shape)
4. [Layout: clustering versus partitioning](#4-layout-clustering-versus-partitioning)
5. [File physics](#5-file-physics)
6. [Shuffle, skew and parallelism](#6-shuffle-skew-and-parallelism)
7. [Query shape](#7-query-shape)
8. [Designing for restart and back-out](#8-designing-for-restart-and-back-out)
9. [Streaming-specific physics](#9-streaming-specific-physics)
10. [Checked and inconclusive](#10-checked-and-inconclusive)

## 1. Measure composition first

**Measure composition before optimizing, because the dominant component decides whether your
target is even the lever.** This applies identically to a runtime and to a bill. A
deterministic fix - a table stuck on full reload, a predicate that stopped pruning, an
unused connector still running - routinely beats an expensive redesign, **and you only see
that from the breakdown.**

**Monitoring is the entry point for all performance analysis.** A scheduler that does not
emit per-run process metadata makes the pipeline a black box, and no amount of tuning
intuition substitutes for the series. Capture step reached, start time, duration, records
processed, error summaries and actions taken, into a database rather than a text log.

**A proprietary vectorized engine's performance is not portable.** Any code path whose
service level depends on it cannot move to an open-source runtime without re-benchmarking.
**Confirm the runtime before promising a number**, because "it runs in two minutes" is a
statement about a specific engine on a specific tier.

## 2. The triage order

**Triage pipeline performance in a fixed order rather than by intuition**, most-costly cause
first. This ordering is the durable content; the individual items are unremarkable on their
own and valuable as a sequence.

1. Unindexed queries against the source or an intermediate table
2. SQL phrasing that misleads the optimizer
3. Insufficient memory causing thrashing
4. Sorting inside the database
5. Slow transformation steps
6. Excessive input/output
7. Writes immediately followed by reads
8. Rebuilding aggregates from scratch instead of incrementally
9. **Change-filtering applied too late in the pipeline**
10. Untapped parallelism
11. Unnecessary transaction logging on updates
12. Network and file-transfer overhead

**Item 9 deserves separate emphasis: push change filtering as early as possible, ideally
before any bulk transfer.** Every byte filtered at the source is a byte not paid for in
movement, storage, transactions and scanning, four times over. It is the only item on this
list that improves all four cost lines at once.

## 3. Lazy engines: the script's shape is not the work's shape

**In a lazy engine, a long chain of transformations collapses into a small number of physical
stages after optimization**, so "this filter is slow" is nearly always a misdiagnosis: the
filter is free, and the *action* triggered the entire upstream pipeline.

**Time actions, not transformations. Read the physical plan.** Optimizing the script for
readability is an independent activity from optimizing the work, and conflating them wastes
both.

**Whole-stage code generation falls back to interpreted execution silently past the method-size
limit imposed by the runtime.** The symptom is a stage that should be CPU-bound being
inexplicably slow. The causes are wide transformation chains (dozens of sequential column
additions) and deeply nested plans. The fixes: **collapse the chain into a single projection
building a struct**, or insert a cache or a write-then-read boundary to break the plan.

**Adaptive query execution is frequently disabled by inheritance** - legacy cluster configs
and copy-pasted settings. Without it, the default shuffle-partition count produces pathological
partition sizes on real data and skew goes entirely unhandled. **Verify it is on before tuning
anything else**, because every other tuning decision assumes it. Note the honest framing: it
has been on by default for several major versions, so "it is probably off" is an estate
observation rather than a version fact, and it costs one command to check.

## 4. Layout: clustering versus partitioning

**Clustering beats directory-style partitioning on a merge-heavy table.** Physical
partitioning on a high-cardinality or skewed column produces small files **and**
concurrent-merge conflicts on the same partition. Liquid or adaptive clustering on the merge
keys plus the common filter columns avoids both without committing to a directory layout.

**This is the clearest example of an implementation choice foreclosing a line-of-code option
one altitude down:** once a table is physically partitioned, row-level concurrency on writes
that touch the same partition is no longer available to you, and no query rewrite recovers it.

**Do not enable automatic or predictive optimization over tables another system manages.**
Enabling it over a raw layer that an external tool writes and rewrites means paying to
optimize files that are about to be replaced.

**Partition by date and use path predicates so whole folders are skipped.** On a
bytes-scanned engine this is usually the single largest lever, because it removes data from
consideration rather than processing it faster.

## 5. File physics

**Measure the file-size distribution before optimizing anything else in a lake.** Small files
create disproportionate metadata overhead, and **unexpectedly high storage transaction costs
usually mean a small-files problem rather than a volume problem.**

Working targets: compaction toward files in the hundreds of megabytes, with files under
roughly ten megabytes carrying disproportionate metadata overhead. **Compaction is a planned
job, not a reaction**, and it is the known cost of an append-only raw layer rather than a
defect in it.

**Restrict compaction to cold partitions to avoid commit conflicts with the writer.** A
compaction job competing with an active writer on the same partition converts a maintenance
task into an availability problem.

**Hierarchical-namespace storage suits a directory-heavy layout**, because atomic folder
rename is what makes overwrite-by-swap safe. The named trade-off is that transactions are
charged in fixed-size blocks, so many small files inflate transaction counts.

## 6. Shuffle, skew and parallelism

**Key skew recreates the single-partition bottleneck at any partition count.** One dominant
entity carrying most of the volume defeats provisioning entirely. Mitigate with salted or
composite keys. The same reasoning applies to any hash-partitioned write, not only to a log.

**Partition count is a near-irreversible capacity decision on a keyed log.** Consumer
parallelism is capped at partition count, so under-provisioning throttles throughput
permanently. But adding partitions changes the hash-modulo routing and **destroys per-key
ordering**, so the only safe remedy is a new topic plus dual-write plus consumer drain. Size
it up front from the target throughput divided by the per-partition producer and consumer
rates, take the larger, add headroom, and **round to a number with many divisors rather than
to a prime.** Soft ceilings sit in the low hundreds of partitions per broker and degrade
badly past a few thousand.

**Parallelism should be automatic per stage rather than hand-wired**, because hand-built
parallel flows do not benefit when processors are added; someone has to edit the pipeline.
Extraction parallelizes by logically partitioning on an attribute range, **but verify the
source engine handles that without spawning conflicting work.**

**Read-side parallelization bounds must hug the actual data range.** Bounds do not filter:
rows outside them collect into the first and last partitions. Setting them from a remembered
value gives one or two enormous tasks with every other executor idle, which **presents as a
mysteriously slow job rather than a broken one.** Read the actual min and max before the
load, at the cost of one aggregate query, and remove the settings after the initial load or
they fire on every run.

**Bound fan-out over a source fleet explicitly, and only after profiling.** Database sizes
vary enormously across a same-schema fleet, so naive fan-out over the full
server-by-database-by-table matrix can overwhelm individual servers. The failure lands on the
source, which is someone else's system.

## 7. Query shape

**Always project explicit columns.** Beyond readability, on serverless engines "data
processed" includes uncompressed intermediate results shuffled between nodes, so a select-all
over well-compressed columnar files can generate several times the compressed read volume in
transfer alone.

**Merge is the upsert and history primitive**, and its cost is dominated by how much of the
target it has to touch. Two levers, in order: narrow the target with predicates the engine can
use to prune files, and cluster on the merge keys so the files it must touch are few.

**Deduplicate to one row per key before the merge.** A merge with multiple source rows per key
raises an error on most engines rather than choosing one, and the deduplication needs an
ordering column to rank by, or an arbitrary row survives. This is a correctness issue that
presents as a performance issue when someone "fixes" it by widening the merge.

**Rebuilding aggregates from scratch instead of incrementally** is item 8 on the triage list
and is worth naming separately, because a materialized view that recomputes fully every run is
usually a **compute-choice** problem before it is a query problem: incremental refresh commonly
requires a specific compute tier and requires upstream sources to have row tracking and a
change feed enabled. Without those prerequisites the engine has no choice but full
recomputation.

**Sorting inside the database** earns its place on the triage list because a dedicated sort can
emit several differently-ordered outputs from one read, which is also a cheap profiling
instrument.

## 8. Designing for restart and back-out

**Design for restart and back-out at the row level.** A single-column surrogate key on the
fact table lets a halted load resume or be fully backed out by constraining a key range,
identifies one row unambiguously without constraining several dimensions, and turns updates
into insert-then-delete.

**Commit in small tunable batches and track what committed**; batch size has engine-specific
performance consequences, so it is a measured setting rather than a copied one.

**Deciding where to physically stage to disk is deciding where your recovery points are.**
That reframing is what turns a staging decision from a storage question into an operational
one.

**Extract-to-file beats stream-through-transform on restartability, and restartability usually
wins.** A retained extract file can be re-run without touching the source, verified by
comparing row counts before and after transfer, and compressed and encrypted independently.
**Compress before encrypting; encrypted bytes do not compress.**

## 9. Streaming-specific physics

**Streaming writes into a lakehouse are governed by file physics, and the two levers are
checkpoint interval and compaction.** Working shape: checkpoint on the order of minutes rather
than seconds, bounded file sizes per commit, and compaction running on a schedule against cold
partitions only.

**Consumer eviction has two independent clocks, and confusing them causes the most common "the
stream is stuck" ticket.** The heartbeat and session timeout runs on a separate thread, while
the maximum poll interval evicts a consumer whose *processing* loop stalls even though its
heartbeats are landing. Static group membership plus a longer session timeout suppresses
rebalances on transient restarts.

**Strict global ordering and high throughput are mutually exclusive**, and this belongs in the
first design review rather than in tuning. Strict ordering requires a single partition and a
single consumer; partition-key ordering is the pragmatic answer for nearly everyone.

**A watermark is an explicit freshness-versus-completeness dial** whose default is
unforgiving: allowed lateness of zero means late records are dropped silently unless a side
output is configured. That is a correctness decision, not a tuning detail.

## 10. Checked and inconclusive

- **Spark-specific depth is thin here by inheritance.** The source reference for partitioning,
  shuffle configuration, join strategy selection, caching storage levels, Arrow and vectorized
  UDFs, plan reading and cluster sizing was a stub with one section written. What appears above
  is the durable subset that survived; **the coverage above is triage and layout rather than
  Spark tuning.**
- **Per-platform query-profile reading** (warehouse query profiles, clustering-key and
  search-optimization decisions, warehouse right-sizing, result-cache behavior, direct-lake
  semantics and its fallback conditions) was not researched and is not covered.
- **Concrete file-size and checkpoint-interval targets** are stated as ranges and shapes rather
  than as tuned values, because the right value depends on the engine, the write rate and the
  query pattern. Measure, per §1.
- **Whether adaptive execution is commonly disabled in practice** is an estate observation
  rather than a version fact, and it is labelled as such above.
