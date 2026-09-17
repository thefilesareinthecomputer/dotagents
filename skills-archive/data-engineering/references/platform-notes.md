# Platform notes

Dated, version-sensitive mechanics that the principle-level files deliberately leave out,
plus the register of what could not be settled.

**Everything here rots.** Each claim carries the date it was verified, and a claim with no
date should be treated as unverified rather than as current. Where a fact was taken from a
search summary of a primary page rather than the page itself it is marked
**[second-hand]**. Re-verify anything load-bearing before it reaches a client deliverable.

**All items below verified 2026-07-29 unless stated otherwise.**

## Contents

1. [Databricks: Auto Loader](#1-databricks-auto-loader)
2. [Databricks: COPY INTO versus Auto Loader](#2-databricks-copy-into-versus-auto-loader)
3. [Snowflake: file loading and its two separate dedup histories](#3-snowflake-file-loading-and-its-two-separate-dedup-histories)
4. [Snowflake: streaming ingest](#4-snowflake-streaming-ingest)
5. [Fabric: shortcuts, Mirroring and the movement options](#5-fabric-shortcuts-mirroring-and-the-movement-options)
6. [DuckDB: the embedded analytics engine](#6-duckdb-the-embedded-analytics-engine)
7. [REST API sourcing](#7-rest-api-sourcing)
8. [File-drop arrival contracts](#8-file-drop-arrival-contracts)
9. [The retirement clock](#9-the-retirement-clock)
10. [Checked and inconclusive](#10-checked-and-inconclusive)

## 1. Databricks: Auto Loader

**File detection has two modes, and the notification one was renamed.** Directory listing is
the default and needs no permissions beyond data access. The current documented notification
mechanism is **Auto Loader with file events** ("managed file events"), enabled with
`cloudFiles.useManagedFileEvents = true`; the older per-stream queue setup is now called
**classic file notification mode**.

**The scale mechanism is the queue count.** File events uses **one queue for all Auto Loader
streams on a bucket**, which is the documented way to stay under the cloud provider's
per-bucket notification limit. Classic mode creates a dedicated notification service and
queue **per stream**, needs credentials that can create those cloud resources, and needs
manual tuning. Databricks recommends file events over directory listing for most workloads.

**Full-listing fallback triggers, which is where a surprise cost comes from:** starting a new
stream; migrating from directory listing or classic notifications; **the stream has not run
for more than 7 days**; and external-location updates invalidating the read position
(toggling file events, changing the path, supplying a different queue). Databricks advises
running streams at least once every 7 days to keep discovery incremental. Separately the file
events service itself does a full directory listing to verify nothing was missed, first when
enabled and then 24 hours after the last full scan.

**Documented caveat that inverts the recommendation:** where latency matters more than
discovery cost, classic file notification mode is preferred, because file events adds a
caching hop.

### Schema evolution modes, and which ones fail the stream

`cloudFiles.schemaLocation` is **required** to infer schema. `cloudFiles.schemaEvolutionMode`
defaults to **`addNewColumns`** when no schema is provided and **`none`** when one is.

| Mode | On an unexpected column |
|---|---|
| `addNewColumns` (default when inferring) | **stream fails once**, then uses the evolved schema on restart |
| `failOnNewColumns` | **stream fails every time**; you restart and let it update the inferred schema |
| `rescue` | column goes to the rescued data column, stream keeps running |
| `none` | **column is silently ignored** - data loss for that column, no signal |
| `addNewColumnsWithTypeWidening` | adds the column and also widens int to long and float to double without rewrite. **Public Preview, DBR 16.4+** |

**`none` is the dangerous one**, because it is the default whenever you supply a schema, and
its failure mode is silent. **`_rescued_data`** is added automatically when Auto Loader
infers the schema and receives data on a missing column, a type mismatch, or a case mismatch,
holding a JSON blob plus the source file path of the record. Note the parser interaction: with
the rescued-data column set, type mismatches no longer drop records under `DROPMALFORMED` or
raise under `FAILFAST`, so only genuinely corrupt input fails.

**Case sensitivity trap:** unless case sensitivity is enabled, `abc`, `Abc` and `ABC` are the
same column and the case is picked arbitrarily from sampled data, with differently-cased
fields going to the rescued column.

### Throttling and reprocessing options

- `cloudFiles.maxFilesPerTrigger` default **1000**.
- `cloudFiles.maxBytesPerTrigger` is a **soft** maximum; files are never split, so a single
  file is processed whole even if it exceeds the limit. Whichever limit is hit first governs
  the micro-batch. **Configured dynamically in DBR 18.0+.**
- `cloudFiles.includeExistingFiles` default **`true`**, and **evaluated only on the first
  start of a stream**, so flipping it later has no effect on an existing checkpoint.
- `cloudFiles.allowOverwrites` default **`false`**: with the default, a file modified in place
  is **not** reprocessed.
- `cloudFiles.backfillInterval` exists because notification delivery is not guaranteed to be
  complete. **Do not use it when `useManagedFileEvents = true`.**
- `cloudFiles.cleanSource` default `OFF`, values `OFF | DELETE | MOVE`. **Documented warning:
  do not use it when multiple streams consume the same source location, because the fastest
  consumer deletes the files for everyone.**
- `cloudFiles.maxFileAge` governs dedup bookkeeping, with a documented warning that tuning it
  too aggressively "can cause data quality issues such as duplicate ingestion or missing
  files".

## 2. Databricks: COPY INTO versus Auto Loader

**The documented decision criteria are about file count**: thousands of files points to
`COPY INTO`; millions or more points to Auto Loader, which needs fewer operations to discover
files and can split work across batches. A frequently evolving schema points to Auto Loader
for its inference and evolution primitives. **Reprocessing a subset of files is easier with
`COPY INTO`**, and you can run it to reload a subset while an Auto Loader stream runs
concurrently.

**Auto Loader is not supported in Databricks SQL; `COPY INTO` is.**

**Idempotency comes from different places, which decides your recovery story.** `COPY INTO`
is **idempotent by default**, skipping already-loaded files, with a `force` option (default
false) that disables that and reloads regardless. Auto Loader's idempotency comes from the
**checkpoint**, giving exactly-once processing of discovered files.

**dbt-databricks specifics** are in `transform-dbt.md`, including the `insert_overwrite`
gating flag, the v1.11.0 runtime requirement, and the clustering configs.

## 3. Snowflake: file loading and its two separate dedup histories

**Snowflake file loading is the most duplicate-prone surface on any of these three platforms,
because two mechanisms keep two separate load histories with two different retentions and two
different matching rules.**

| Mechanism | Matches on | Retention | Behavior on a re-submitted file |
|---|---|---|---|
| Bulk `COPY INTO` | file plus checksum, in **table** metadata | **64 days** | ignored unless `FORCE = TRUE`, or unless modified and re-staged |
| Snowpipe | **file path and name only**, in **pipe** metadata | **14 days** | refused **even if the contents changed** |

**The two documented duplicate-delivery holes run in opposite directions:** "same name, new
contents" slips through bulk copy and is blocked by Snowpipe; "new name, same contents" slips
through both. Which hole you have depends on which mechanism you chose.

**The 64-day expiry has a silent-no-op failure mode.** While a staged file's last-modified
date is within 64 days, `COPY INTO` can determine its load status and prevent a reload. After
expiry, when the file is older than 64 days **and** the initial load into that table happened
more than 64 days ago, COPY **cannot determine the load status and skips the file by
default.** The escape hatches: `LOAD_UNCERTAIN_FILES = TRUE` attempts files with expired
metadata, and `FORCE = TRUE` ignores load metadata entirely and **can duplicate data**.

**Do not point both mechanisms at the same path and table.** Because the load histories are
separate, doing so produces duplicates. Snowflake's guidance is to load a given set of files
with bulk loading **or** Snowpipe, not both.

**Two more operational facts.** `TRUNCATE TABLE` does **not** clear Snowpipe's file-loading
metadata; reloading modified files requires `CREATE OR REPLACE PIPE`, which wipes the load
history, after which already-loaded files must not be resubmitted. And files that fail during
a pipe's copy are still registered in pipe metadata and are ignored by later pipe activity
including a refresh, so **skipped files need an explicit `COPY` statement**.

**`ON_ERROR` defaults differ by mechanism**, and one of them gates alerting: `COPY INTO`
defaults to `ABORT_STATEMENT`; Snowpipe defaults to `SKIP_FILE`, and **Snowpipe error
notifications only fire when `ON_ERROR = SKIP_FILE`**, so setting `CONTINUE` silently
disables the notifications.

## 4. Snowflake: streaming ingest

**Current architecture is Snowpipe Streaming high-performance**, with the older one now called
**Snowpipe Streaming Classic**. Rows load directly with no staged files. The central object is
the **PIPE**, which supports in-flight transformation via copy transformation syntax plus
clustering keys, default columns and identity columns; every target table gets a default pipe,
so no explicit DDL is strictly required. Channels and offset tokens are inherited from Classic.

**Availability:** GA on AWS and Azure, GA on GCP 2025-11-10, GA in China 2026-04-23. The
Snowflake Connector for Kafka v4.0 went GA 2026-04-20, rewritten on the high-performance
architecture with exactly-once and ordered delivery.

**Billing unit** (no figures, per the cost scope decision): a flat-rate model based on
**uncompressed data volume ingested, measured on input bytes received**, not on the final
bytes in the target table. That distinction matters because compression ratio does not reduce
it.

**Iceberg support differs by architecture**: high-performance supports Snowflake-managed
Iceberg v2 and v3 (Classic is v2 only), and **partitioned Iceberg tables and Iceberg schema
evolution are not supported**.

## 5. Fabric: shortcuts, Mirroring and the movement options

**The documented criterion between shortcuts and Mirroring is copy versus no-copy.**

- **Mirroring** is a continuously replicated *copy* of an external operational database landed
  in OneLake in Delta format with near-real-time change capture and no ETL pipeline. Best for
  operational databases needing continuous change data capture.
- **Shortcuts** are logical links that *virtualize* data in external storage or another
  workspace without copying. Ideal for **live, read-only access without replication**, and the
  recommendation when the data is already reachable over OneLake or when residency or
  duplication concerns forbid moving it.

**The overlap worth knowing: metadata mirroring** syncs catalog, schema and table metadata
rather than data, and **uses shortcuts underneath**. The mirrored catalog from another
lakehouse platform is the canonical case: only catalog structure is mirrored and data is read
through shortcuts, **so data changes may not appear immediately.** Anyone reasoning about
freshness needs to know which of the two they actually have.

**The documented medallion heuristic:** gold points to Mirroring (least setup, continuous
replication, single read-only destination); bronze and raw point to a Copy job (needs
transformation, schema mapping, scheduling, incremental load); real-time streaming points to
Eventstreams; complex orchestration points to a pipeline with a copy activity, where you own
the components and the last-run state for incremental copy.

**Dataflow Gen2 is not deprecated, but the classic variant is closed to new items.** As of
**April 2026 you can no longer create Dataflow Gen2 items without CI/CD and Git support**;
existing non-CI/CD items keep working and new items get CI/CD by default. Two related 2026
behavior changes: with just-in-time publishing, a refresh **fails** if the dataflow was last
saved after **2026-02-01** and the publish fails, even where an earlier publish succeeded; and
after a Git sync or pipeline deployment you must open and save the dataflow manually to
trigger the background publish. **Dataflow Gen1** has no announced deprecation but receives no
new features.

**dbt-fabric limitations** that change how models are written are in `transform-dbt.md`
[second-hand], notably that nested CTEs are unsupported in model materialization and that
index configuration is ignored.

## 6. DuckDB: the embedded analytics engine

**This section was verified 2026-08 rather than on the file's default date.** DuckDB moves
quickly and its release cadence is the fastest of anything on this page, so treat every
capability claim here as needing a version check before it reaches a deliverable.

**The embedded model is the whole design and everything else follows from it.** DuckDB is a
library linked into the calling process, not a server. There is no daemon, no cluster and no
wire protocol. A database is a single file, or purely in memory, and results materialize
directly in the host process's address space. Installation is a package install, and the
operational burden it transfers is close to zero, which is unusual enough to say out loud
against the judgment-pass question about what a component commits you to operating.

**The consequences that decide whether it fits.**

- **The latency floor is near zero**, because there is no connection setup and no result
  serialization across a socket. This is why it beats a far larger warehouse on small
  queries, and why it is the right engine for a test suite that needs real SQL.
- **Its resource limits are the host's.** The memory limit and thread count are settings
  with defaults derived from the machine; read the settings rather than assuming a figure.
- **Larger-than-memory work degrades rather than failing.** The vectorized engine spills to
  a temporary directory for joins, aggregations and sorts, so exceeding memory costs disk
  bandwidth instead of raising. Which operators spill is version-specific and is in §10.
- **Concurrency is the first constraint to check, and it is the one that rules it out most
  often.** A database file is held in read-write mode by one process; other processes can
  attach read-only only while no writer holds it. Inside one process, threads share the
  database under optimistic concurrency, so conflicting transactions abort rather than
  queue. There is no multi-user write serving, by design and not by omission.

### Reading Parquet, Iceberg and Delta in place

**Files are queryable without a load step.** A path or a glob is a table:
`SELECT * FROM 's3://bucket/prefix/*.parquet'`. Hive-style partition directories are
recognized and their key columns become predicates, and projection and predicate pushdown
reach into Parquet row groups and their statistics, so a selective query reads a fraction of
the bytes. Over object storage the `httpfs` extension issues ranged reads, fetching footers
first and then only the row groups the plan needs.

**That is also where the cost surprise lives.** A query with no usable pruning predicate
downloads the whole dataset and is billed as egress by the object store, on a platform whose
own bill shows nothing. Anyone querying a remote lake from a laptop needs the same
bytes-scanned discipline that `optimization.md` §4 applies to a warehouse.

**Iceberg and Delta arrive as extensions rather than as core.** The `iceberg` extension
reads tables from their metadata or through a catalog, and the `delta` extension reads Delta
tables through the Rust Delta kernel. **Read support is the mature side; write support and
REST catalog integration have been landing recently and are the specific things to re-verify
against the release notes before promising them** (checked 2026-08).

### Extensions, and the trust boundary they create

Extensions install on demand from a repository and several autoload on first use. The ones
that change what the engine is for: `httpfs` plus the cloud credential providers, `iceberg`
and `delta`, the `postgres`, `mysql` and `sqlite` scanners, `spatial`, `fts`, `json` and
`excel`, plus a separately hosted community repository.

**The database scanners are the underrated one for this discipline.** They let a single
statement join a live operational table to Parquet in a lake, which is exactly the shape of
a reconciliation between a source system and a bronze layer, with no intermediate load and
nothing to clean up afterward.

**Because an extension is loaded into your own process, extension trust is a real security
question rather than a vendor's problem.** Signed core extensions are the default path;
loading unsigned ones requires explicitly enabling it, and community extensions carry no
vendor support. In a client environment this needs a stated policy, not an ad hoc `INSTALL`.

### Where it stops being the right answer

- **Concurrent multi-user writes or a shared serving endpoint.** It is a library. The hosted
  variants exist and change this answer by putting a server in front of it (checked
  2026-08), which is a different product decision with a different bill.
- **Central governance.** There is no cross-team catalog, no grant model, no row filters or
  column masks of the kind `governance-and-mdm.md` describes. Access control is whoever can
  read the file.
- **Anything with a service level.** Connection pooling, workload isolation, query queuing
  and failover are all absent, because they are properties of a server.
- **Data that genuinely exceeds one node after pruning**, or a workload dominated by a
  shuffle large enough to need many machines. Sizing that judgment is
  `dataframes-and-engines.md` §1 and §2.
- **Streaming ingest and long-lived incremental state**, which need a process that is always
  running.
- **Estates where lineage and monitoring only observe the platform's own runtime.** A DuckDB
  step inside such a platform is a black box to its lineage graph, and that trade should be
  named in the decision record rather than discovered during an incident.

**One durability rule regardless of fit: the `.duckdb` file is a working format, not an
archival one.** The storage format carries a stability commitment from the 1.0 line onward
(checked 2026-08), and it is still a single engine's internal format. Keep Parquet as the
durable artifact and treat the database file as a cache you can rebuild.

## 7. REST API sourcing

**Documented, from a major API's own pagination guide:** link-header pagination returns a
`link` header carrying URLs with `rel="prev"`, `"next"`, `"first"`, `"last"`, with only a
subset present depending on position. **Consumers are meant to follow `rel="next"` rather than
construct page numbers.** Paginated endpoints use page, cursor (`before`/`after`) or `since`
parameters.

**Standards:** the `Link` header and its relation types are RFC 8288 (2017); HTTP 429 is
RFC 6585 (2012) and explicitly permits a `Retry-After` header; `Retry-After` is defined in
RFC 9110 (2022), taking either an HTTP-date or a delay in seconds, with **the server, not the
client, stating the wait.** Section numbers were cited from the standards without a fetch and
should be spot-checked.

**The concurrent-insert failure mode, labelled engineering reasoning rather than a vendor
warning** (no primary source for it was reached, and that is stated deliberately):

**Offset and page-number pagination address rows by ordinal position in a result set that is
recomputed on every request.** Sorted newest-first, a row inserted between fetching page N and
page N+1 shifts every row one position later, so the last row of page N reappears as the first
row of page N+1: a **duplicate**. A deletion shifts rows earlier and the row at the page
boundary is **never returned**: silent loss. **Neither event produces an error**; the page
count and HTTP status look normal, and loss scales with insert rate times read duration, which
is why it only shows up on long reads over hot collections.

**Cursor or keyset pagination is the safe style**, because the next request carries the
last-seen value of a stable, monotonic, unique ordering key, so position is defined by data
rather than by an ordinal. **Link-header pagination is safe or unsafe depending on what the
opaque next-URL encodes**: a cursor is safe, an embedded page number is not.

Three keyset requirements that are easy to get wrong: the key must be **unique**, hence a
tiebreaker on an id; it must **not be mutable**, because a cursor over a last-updated column
re-emits rows and can skip rows whose timestamp moves past the cursor; and reads must not mix
ascending page order with a descending sort.

**Where the API's ordering is not guaranteed, a cursor over its sort key is unsound.** The
durable patterns are to overlap the watermark by a safety margin and deduplicate downstream on
a record key, accepting at-least-once and making the sink idempotent, or to treat the
extraction as a full or window re-read. **Resumption after a mid-pagination failure is safe
only if the checkpoint is the cursor token plus the set of record keys already committed,
committed atomically with the data**; replaying from a page number re-reads a shifted result
set. With an at-least-once source, resumption correctness comes from the sink's idempotent
key rather than from the reader.

**Rate limiting:** a fixed-window counter resets on a wall-clock boundary, so clients
synchronize on the boundary and burst; a token bucket refills continuously and admits a
bounded burst, so a client can pace against the refill rate. Honor `Retry-After` when present,
otherwise use exponential backoff **with jitter** to break the synchronized-retry thundering
herd that plain exponential backoff creates across many workers, cap the delay, and **only
retry idempotent reads automatically.**

## 8. File-drop arrival contracts

**Documented, from the object store's own consistency model:**

- **Strong read-after-write consistency** for writes and deletes, including overwriting
  writes; a new object appears immediately in a subsequent listing.
- **"Updates to a single key are atomic."** A concurrent reader gets either the old data or
  the new data, **never partial or corrupt data.** This is the documented basis for the
  upload-then-publish contract: a reader never observes a half-written object under a
  published key.
- **No object locking for concurrent writers**, so simultaneous writes to one key are
  last-writer-wins and **a redelivered file silently overwrites.**
- **"There is no way to make atomic updates across keys"**, which is exactly why a per-batch
  sentinel or manifest exists: multi-file batch atomicity has to be built by the producer.
- Bucket **configuration** changes are eventually consistent, unlike object operations.

**Community convention, explicitly not vendor-documented.** No vendor documentation was found
for marker-file-gated ingestion in any of the three platforms above, so all of this is
labelled convention rather than contract:

- **Marker or sentinel files** (`_SUCCESS`, `.done`, a per-batch manifest listing files and
  row counts) as the completeness signal, with the reader triggering on the marker and never
  on the data files.
- **Atomic rename, or upload-to-staging-then-copy-to-published**, relying on the single-key
  atomicity above. On a POSIX or HDFS filesystem a same-filesystem rename is atomic; **on
  object storage there is no rename, so it is copy plus delete and therefore not atomic as a
  pair.**
- **Zero-byte and truncated files** guarded by a size check plus a manifest-declared byte or
  row count, rejecting to a quarantine prefix rather than failing the stream. **A zero-byte
  file is normally a legal, empty, successfully-parsed file to an ingest engine: it does not
  error, which is what makes it dangerous.**
- **Duplicate detection by content hash** recorded in a durable ledger rather than trusting
  the platform's own load history, **precisely because those windows expire** at 14 and 64
  days per §3.
- **Out-of-order and late arrival** handled with event-time watermarks and a declared lateness
  bound, plus a reconciliation pass for arrivals beyond it. **Ordering by filename timestamp is
  not an ordering guarantee.**

## 9. The retirement clock

Dates inside or near a twelve-month window from 2026-07-29, highest urgency first.

| Date | Item | Status |
|---|---|---|
| **2026-09** | Snowflake increases the default column size for string and binary types; `dbt-snowflake` below **v1.10.6** may fail incremental builds combining `sync_all_columns` with collated string columns | documented, fixed in v1.10.6+ |
| **mid-2026** | **Snowpipe Streaming Classic**: a notice of *planned* deprecation exists, with the formal announcement planned for mid-2026 | **not deprecated as of the access date**; no immediate action |
| **April 2026 (past)** | Fabric: creation of non-CI/CD Dataflow Gen2 items retired | already in effect |
| **2026-02-01 (past)** | Fabric: just-in-time publishing makes a refresh fail if the dataflow was last saved after this date and the publish fails | already in effect |
| **November 2027** | **Spark 3.5.x** extended security-only support ends | outside the window, and the one hard migration deadline found |
| unknown | **Airflow 2.x** end of support | **not established**; the most likely near-term retirement in this set |

**A messaging SDK and protocol retirement dated 2026-09-30** appears in the source corpus as a
single-source claim and **was not re-verified in this pass.** It is the nearest hard deadline
recorded anywhere in this material, so treat it as a prompt to check rather than as a fact.

## 10. Checked and inconclusive

**Auto Loader.**

- **The checkpoint reset procedure is not documented.** The options page states explicitly
  that the documentation does not detail behavior when checkpoints are reset or schemas are
  manually modified. Whether the procedure is a new checkpoint directory or deleting the
  existing one was not verified, and is not guessed here.
- **Whether an unchanged, already-committed file can be reprocessed in place** was not
  settled. `allowOverwrites = true` allows a *changed* file to overwrite, and
  `includeExistingFiles` is evaluated only at first stream start (which implies it cannot force
  reprocessing later), but no primary statement about the unchanged case was reached, and the
  interaction between `allowOverwrites` and file events is unverified.

**REST.**

- **No major-API primary citation was obtained for 429 handling or backoff guidance.** The
  pagination page fetched contains none of it, so §7's retry material rests on the RFCs plus
  engineering convention.
- **No primary-source vendor warning about offset-pagination drift was obtained.** Several
  major APIs document cursor pagination as the remedy, but none was fetched, so the mechanism
  in §7 is labelled reasoning rather than a cited warning. It is mechanically sound and it is
  not a quotable authority.
- **RFC section numbers** should be spot-checked; the URLs are correct.

**Fabric.**

- **Copy job idempotency on a re-delivered file** has no primary statement, so nothing is
  claimed. Given §3 and §8, assume duplicates are possible until proven otherwise.
- **Fabric deprecations beyond the Dataflow Gen2 items** were not swept.

**Snowflake.**

- **Whether the Snowpipe Streaming Classic formal deprecation has since been published** was
  not verified beyond the existence of the planned-deprecation notice.

**dbt** (full register in `transform-dbt.md`), with the two most consequential repeated here:

- **Whether partitions the source has stopped emitting persist under dynamic mode on
  dbt-spark** is not stated by any source reached. It follows logically and it is not
  asserted.
- **The microbatch adapter-support column conflicts between the matrix and the microbatch
  page.** The conflict is recorded rather than resolved. **Do not encode it into a linter rule
  without re-reading the live table.**

**DuckDB** (all items checked 2026-08).

- **Which operators spill to disk, and under what conditions, is version-specific** and no
  primary page was fetched in this pass. §6 claims only that larger-than-memory work
  degrades rather than failing, which is the documented design intent; do not promise a
  specific operator will survive a specific dataset without testing it.
- **Iceberg and Delta write support and REST catalog integration** are moving fast enough
  that the state at any given date was not established here. This is the single item on
  this page most likely to be wrong within a quarter.
- **The default memory limit and thread count** are deliberately not stated as figures,
  because they derive from the host and have changed. Read the settings.
- **No version number is asserted for the storage-format stability commitment beyond "the
  1.0 line onward."** The commitment exists; its exact boundaries were not verified.

**Cross-cutting.**

- **Platform-native validation syntax** (declarative pipeline expectations and their
  warn/drop/fail modes, data-metric functions, managed quality monitoring: what each computes,
  where it writes, what it costs) was not verified in this pass and is the largest remaining
  gap in the platform-specific material.
- **Per-platform grant syntax, privilege names and audit-log query recipes** were not verified.
- **Per-platform query-profile reading and right-sizing mechanics** were not verified.
