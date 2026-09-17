# Transformation on a medallion lakehouse

Laying out a transformation project, deciding what rebuilds and what accumulates, and
knowing which incremental settings quietly leave stale data behind.

Every version-sensitive claim here carries the date it was verified. Claims marked
**[second-hand]** come from a search summary of a primary page rather than the page itself;
re-verify those before putting them in a client deliverable. Anything unresolved is in
[§12](#12-checked-and-inconclusive) rather than stated.

**Up:** `architecture-decisions.md` decides the layer count, the governance boundary and
whether this is dbt at all.
**Down:** `optimization.md` owns the physical consequences (clustering, file sizes,
concurrency), `observability.md` owns whether a green run was actually correct.

## Contents

1. [Medallion versus staging/intermediate/marts](#1-medallion-versus-stagingintermediatemarts)
2. [Layer responsibilities and the one test that resolves arguments](#2-layer-responsibilities-and-the-one-test-that-resolves-arguments)
3. [The documented layout rules](#3-the-documented-layout-rules)
4. [Naming and governance boundaries](#4-naming-and-governance-boundaries)
5. [Incremental strategies](#5-incremental-strategies)
6. [The insert_overwrite trap](#6-the-insert_overwrite-trap)
7. [microbatch](#7-microbatch)
8. [Snapshots](#8-snapshots)
9. [Tests: four instruments that catch different things](#9-tests-four-instruments-that-catch-different-things)
10. [Slim CI](#10-slim-ci)
11. [Adapter differences that change project design](#11-adapter-differences-that-change-project-design)
12. [dbt, SQLMesh, and the licensing state](#12-dbt-sqlmesh-and-the-licensing-state)
13. [Checked and inconclusive](#13-checked-and-inconclusive)

## 1. Medallion versus staging/intermediate/marts

**Architecture altitude.** The two vocabularies are not the same partition of the work, and
treating them as synonyms is the most common structural mistake in a lakehouse dbt project.

| Medallion layer | Usual dbt home | Where the mapping breaks |
|---|---|---|
| Bronze / raw | **not dbt** - it is the ingestion tool's output, declared to dbt as a `source` | dbt models bronze only when dbt is doing the loading, which is rarely the right shape |
| Silver / conformed | `staging` plus `intermediate` | silver is cross-system and integrated; dbt staging is explicitly **source-conformed and single-source**, so the integration work is `intermediate`, not staging |
| Gold / curated | `marts` | a mart purpose-built for one outcome is gold; a reusable conformed dimension in `marts` is really silver by responsibility |

The practical consequence: **staging is not silver.** Staging is one model per source table,
source-shaped. Silver's defining property is cross-system integration, which by the layout
rules cannot happen in staging. If you map silver onto staging you will either put joins in
staging (against the documented rule) or discover you have no home for integration.

Declare bronze as sources with freshness rather than modelling it. A bronze table modelled
in dbt loses the append-only audit property that `source-to-bronze.md` establishes as the
whole point of that layer.

## 2. Layer responsibilities and the one test that resolves arguments

**Each layer has one responsibility, and blurring them produces duplication rather than an
error.** Raw reflects source systems with minimal transformation. The conformed layer holds
cleaned, integrated, cross-system tables reusable across use cases. The curated layer holds
business-ready products purpose-built for a specific outcome. The failure of blurred layers
is never a crash. It is three teams building three versions of the same entity.

**The test for "conformed or curated" is reuse, and it is one question: is this dataset
reused across multiple use cases?** Yes means conformed, no means curated. That single test
resolves most of what otherwise consumes a design review, and it stays stable as new use
cases arrive in a way that a taxonomy of table types does not.

**What breaks first as a platform scales is predictable, so design against the list from
the start**, in order of appearance: multiple versions of core datasets; duplicated
transformation logic across teams; inconsistent metrics between reports; unclear ownership
boundaries; rising onboarding cost per new team. Without explicit patterns, inconsistency is
the default outcome rather than a risk.

**The same metric differing between two reports is a layering defect, not a reporting
defect.** When a capability needs several datasets and those datasets are not standardized,
conformed and centrally managed, every consuming use case recreates the logic and produces
a different answer. Fixing it in the reports guarantees recurrence.

## 3. The documented layout rules

Verified against the dbt Labs "How we structure our dbt projects" staging page,
2026-07-29. These are documented rules rather than folklore, which matters when you are
arguing for them in review.

**Staging.**

- **One model per source table.** Staging models are the only place the `source` macro is
  used, and they hold a 1-to-1 relationship with source tables, acting as each one's entry
  point for everything downstream.
- **Joins are discouraged, not banned.** The documented wording is that joins here are
  "almost always a bad idea" because they create duplicated computation and confusing
  relationships that ripple downstream, with occasional exceptions.
- **The sanctioned escape hatch is a `base` model** in a subdirectory of the staging folder
  for that source system, used where a join is genuinely needed to keep the staging layer
  clean and non-repetitive.
- **Allowed transforms:** renaming, type casting, basic computations, categorizing.
  **Not allowed:** joins and aggregations.
- **Naming:** `stg_[source]__[entity]s.sql`, with a double underscore between source system
  and entity and the entity plural. `stg_[entity].sql` is explicitly marked as not
  recommended.
- **Materialize as views**, configured per directory in `dbt_project.yml`, so downstream
  models always compose the freshest component data and the warehouse is not filled with
  models no consumer queries.

```yaml
models:
  my_project:
    staging:
      +materialized: view
```

Subdirectories per source system, with a `__sources.yml` in the staging folder.

The intermediate and marts pages were not verified in this pass, so the `int_` prefix, the
`fct_`/`dim_` naming rules and marts materialization defaults are widely used convention
here rather than confirmed documentation. See [§13](#13-checked-and-inconclusive).

## 4. Naming and governance boundaries

**Conventions buy machine-checkability, and the value comes from having them rather than
from which one you pick.** Workable defaults: singular entity nouns for dimensions and the
business process for facts; lowercase with underscores; monetary columns ending in a money
word; booleans prefixed `is_` or `has_`; counts suffixed with an explicit unit; dates and
timestamps suffixed to say which they are; views suffixed distinctly; identifiers typed as
string. Two honest caveats: a singular-noun rule adopted late collides with an existing
plural estate, so the exceptions must be written down with their status ("agreed, not yet
renamed" versus "not agreed"); and dim/fact prefix conventions are optional but must be
all-or-nothing.

**Architect the conformed layer per source system and the curated layer by business
function.** Producer-oriented naming in the conformed layer preserves traceability to
origin; consumer-oriented naming in the curated layer matches how the business asks
questions. The hybrid resolves a lineage-versus-discoverability tension that a single
organizing axis cannot.

**Name a raw schema for the source system as the business refers to it, not for the tool
that moves the data.** Naming by tool couples the namespace to a routing decision that will
change; naming by business name survives a re-platform of the ingestion lane.

**Keep architectural patterns out of governance structures.** The namespace level carrying
permissions and ownership should represent something that does not change (an environment, a
residency boundary, a business unit); the levels below it represent the architecture
(layers, stages, domains). Encoding the medallion layer into the governance boundary makes
adding a layer a permissions migration. The honest tension: environment-plus-layer as the
governance boundary buys clean storage isolation and an obvious promotion path, and it is
common enough that an estate can hold this principle and violate it. If it does, record the
trade rather than pretending it was not made.

## 5. Incremental strategies

**Implementation altitude.** Adapter support matrix as tabulated on the dbt incremental
strategy page, 2026-07-29. The page notes it reflects adapters on the Fusion engine or the
"Latest" release track, so a pinned older dbt-core may not have all of these.

| Adapter | append | merge | delete+insert | insert_overwrite | microbatch |
|---|---|---|---|---|---|
| dbt-databricks | yes | yes (default) | yes, v1.11+ | yes | yes |
| dbt-snowflake | yes | yes | yes | yes | yes |
| dbt-spark | yes | yes | yes | yes | see register |
| dbt-fabric | yes | yes (default, adapter v1.9.7+) | yes | yes | yes |
| dbt-postgres / redshift / trino / athena / duckdb | yes | yes | yes | yes | see register |

**`unique_key` mechanics** (dbt incremental models page, 2026-07-29):

- **Prefer a list of column names** (`['col_a','col_b']`) over a string, because dbt
  templates the columns per database and the list form is documented as more universal.
  Avoid string expressions such as `'concat(a, b)'`.
- **A NULL in a `unique_key` column makes the model fail to match rows and generate
  duplicates.** Remedies given: `coalesce(col, 'VALUE_IF_NULL')`, or a surrogate built with
  a generate-surrogate-key macro. This is the dbt-level restatement of the law that nothing
  enforces your keys.
- **A non-unique `unique_key` may fail depending on database and strategy.** The docs frame
  the outcome as failure; whether a given adapter instead fans out silently was not
  confirmed. Either way the remedy is upstream: prove uniqueness exactly, per
  `source-to-bronze.md`, rather than relying on the adapter to complain.

**`on_schema_change`** (same page, 2026-07-29). Four values, and none of them backfills:

| Value | Behavior |
|---|---|
| `ignore` (default) | added columns do not appear in the target; **removed columns cause the run to fail** |
| `fail` | error when source and target schemas diverge |
| `append_new_columns` | adds new columns, does not remove absent ones |
| `sync_all_columns` | adds new and removes absent columns, including type changes |

Two limits worth knowing: **only top-level columns are tracked**, so nested column changes
do not trigger detection, and **no option backfills values into pre-existing rows for a new
column**. A column added under `append_new_columns` is NULL for all history, which reads
downstream as "we had no data then" rather than "we added this column".

**`full_refresh` config takes precedence over the `--full-refresh` flag.** Setting
`+full_refresh: false` pins a table against accidental rebuilds and the CLI flag will not
override it. This is the right guard on an expensive table and a genuine trap when someone
is trying to fix that table and cannot work out why the rebuild does nothing.

**Dated hazard inside the window: September 2026.** Snowflake increases the default column
size for string and binary types. `dbt-snowflake` below **v1.10.6** may fail to build
incremental models combining `materialized='incremental'`,
`on_schema_change='sync_all_columns'` and string columns with a defined collation. Fixed in
dbt-snowflake v1.10.6 and above. Verified 2026-07-29 from the dbt incremental models page.

## 6. The insert_overwrite trap

This is the mechanism behind "the total is right for this month and wrong for last", and it
is worth stating precisely because both of its outcomes are wrong in opposite directions.

**On dbt-databricks it is documented and gated on a global config.** Verified from the
databricks-configs page, 2026-07-29:

- Documented semantics: with `partition_by` specified, `insert_overwrite` overwrites
  partitions in the table with new data; with no `partition_by`, it overwrites the entire
  table.
- **The dynamic behavior is gated.** With `use_replace_on_for_insert_overwrite` set to
  `true`, dbt dynamically overwrites partitions and replaces only the partitions or clusters
  returned by the model query, issuing a `partitionOverwriteMode='dynamic'` statement.
- **With that flag false on a SQL warehouse, dbt truncates the entire table before
  inserting**, replacing all rows every run.
- The docs carry an explicit warning to re-select *all* relevant data for a partition when
  using this strategy.
- With `liquid_clustered_by` set, the replace-on keys are the same as the clustering keys.
- For atomic full replacement of a Delta table the docs point at the `table` materialization
  (`create or replace`) instead.

**So the two failure modes are opposite, and which one you get depends on a global flag
plus the compute type.** Dynamic mode leaves partitions the source stopped emitting sitting
in the table indefinitely while every run reports success. Non-dynamic mode on a SQL
warehouse silently discards everything the current run did not re-select. Read the resolved
configuration; do not reason from the strategy name.

**On dbt-spark the adapter sets nothing.** The incremental strategies macro emits a bare
`insert overwrite table ... partition (...)` and contains **no**
`SET spark.sql.sources.partitionOverwriteMode` statement (adapter source on `main`, read
2026-07-29). The overwrite mode therefore comes from the session or cluster configuration
rather than from dbt. For Iceberg the macro drops both the `table` keyword and the partition
clause.

**Corroborating evidence that this bites in practice:** a dbt-databricks issue reports that
after upgrading to adapter v1.8.0, `insert_overwrite` models began replacing the whole table
because a `SET ... partitionOverwriteMode = DYNAMIC` had been removed. Treat the mode as
something to assert explicitly and verify after any adapter upgrade, not as a stable
default.

**What to do about it.** Assert the setting rather than inheriting it; add a completeness
check for partitions the source has stopped emitting, because no run-level status will
reveal them; and prefer `replace_where` with explicit `incremental_predicates` on Delta
where the predicate is expressible, because the intent is then in the model rather than in
cluster configuration.

## 7. microbatch

Introduced in dbt Core **v1.9** (second-hand, 2026-07-29). It replaces a hand-rolled
`is_incremental()` window with declared event-time batching.

- **`event_time` is required** and must be when the event actually occurred, not when it was
  ingested. This is the dbt-level form of the business-date-versus-modified-date distinction
  in `source-to-bronze.md`.
- **dbt auto-filters upstream refs and sources that themselves declare `event_time`.
  Upstreams without it are not filtered and get a full table scan on every batch.** That is
  the main performance failure mode, and it is invisible until the bill arrives: the model
  is correct and each batch rescans everything.
- `batch_size` is `hour`, `day`, `month` or `year`. `lookback` is an integer of at least
  zero, **default 1**, reprocessing that many batches before the latest bookmark to catch
  late arrivals.
- `begin` is required to process from the true start of history, because **dbt does not
  probe the minimum `event_time`**. All values are assumed UTC.
- **The write mechanism is adapter-determined and not user-selectable**, and dbt reserves
  the right to change the default: partition replacement on some adapters, delete-plus-insert
  on others. Each batch runs independently and idempotently.
- On dbt-databricks, microbatch is implemented via `replace_where` with predicates derived
  from `event_time` (Delta only). On dbt-spark, microbatch reuses the insert_overwrite path
  and hard-requires `partition_by`.
- Parallel batch execution is supported on Snowflake, where dbt auto-detects parallelism and
  `concurrent_batches` is an override rather than a gate.

**The judgment call.** microbatch is the right default for a large event-time-partitioned
fact model, because it makes the window and the lookback declarative instead of buried in
Jinja, and each batch is independently retryable. It is the wrong choice where the upstreams
cannot declare `event_time`, because you then pay a full scan per batch and a single windowed
merge is cheaper.

## 8. Snapshots

Snapshots are dbt's type-2 mechanism. Use them rather than a hand-rolled merge where they
fit, because a hand-rolled merge puts you in charge of out-of-order handling, late events,
the delete path and the type-2 close-out, which is four places to get it wrong, each failing
silently. Second-hand unless noted, 2026-07-29.

- **The YAML snapshot config replaced the SQL `config` block in dbt v1.9**, with the legacy
  Jinja form moved to its own page. The YAML form is environment-aware, so schema and
  database need not be stated explicitly.
- **`strategy` is required and has no default.** `timestamp` (which needs `updated_at`) is
  recommended over `check`, because it tolerates columns being added or removed without
  constant config churn.
- Meta columns: `dbt_valid_from`, `dbt_valid_to`, `dbt_updated_at`, plus `dbt_is_deleted`
  when `hard_deletes: new_record`. All renameable through `snapshot_meta_column_names`.
- **`dbt_valid_to_current`** sets a sentinel such as `9999-12-31` for current rows instead of
  NULL. **Adopting it on an existing snapshot without migrating existing rows leaves mixed
  NULL and sentinel data and wrong downstream results**, because every `where dbt_valid_to is
  null` predicate silently stops matching the new rows. Back up and `alter` first.
- **`hard_deletes` (v1.9+)** takes `ignore` (default), `invalidate` (which replaces the
  legacy `invalidate_hard_deletes: true`), or `new_record`. `new_record` adds
  `dbt_is_deleted`, set true on delete and back to false if the row reappears, which
  preserves continuous history; the legacy invalidate path only closes `dbt_valid_to` and
  leaves gaps.

**Two rules that come from the modelling side and are cheap to enforce here.** Deduplicate
to one current row per key before the merge, because a merge with multiple source rows per
key raises an error rather than choosing. And add a late-arrival guard as a predicate on the
update clause requiring the incoming version to be newer than the stored one; without it a
replayed or delayed batch silently regresses the dimension to an older state. Where ties are
possible, sequence by a composite of timestamp plus a tiebreaker rather than a timestamp
alone.

**Where a platform offers declarative change application, prefer it for out-of-order
sources.** A managed change-application API takes keys plus an explicit sequencing
expression and handles ordering, deletes, truncates and type-1 or type-2 materialization.
Snapshots do not accept an out-of-order sequencing expression in the same way.

## 9. Tests: four instruments that catch different things

**None substitutes for another**, and most projects implement one and assume they are
covered.

| Instrument | Asserts against | Catches |
|---|---|---|
| Data test | live rows | a value or relationship that is wrong now |
| Unit test | mocked inputs | transformation logic being wrong, before any data exists |
| Contract | declared schema | schema drift, at build time, before rows are read |
| Source freshness | arrival time | an SLA on arrival, which says nothing about content |

**Unit tests shipped in dbt Core v1.8**, in the same release as the `tests:` to
`data_tests:` YAML key rename (both keys still supported, `tests:` deprecated). Verified
second-hand, 2026-07-29. Documented limits: SQL models only; models in the current project
only; **not supported on the materialized-view materialization**; no recursive SQL; no
introspective queries; versioned models run the test on all versions by default. Unit-test
YAML must not live in `tests/`, which is reserved for data tests. **Incremental models are
supported**, with the documented pattern overriding `is_incremental` per test so both the
full-refresh and incremental paths can be exercised, and an `input: this` block for the
existing table.

Select by type with `--select "test_type:unit"` or `"test_type:data"`.

**`dbt build --empty`** limits refs and sources to zero rows while still executing the model
SQL against the warehouse, so buildability and dependencies are validated without paying for
input reads. Caveat: dbt may skip processing a `ref()` or `source()` as an optimization, so
`.render()` is sometimes needed to force it and avoid compilation errors. Seeds referenced
in the model load in full.

**The law from `SKILL.md` applies hardest here: a check that cannot fail is worse than no
check.** An empty test result reads as a pass. Prove each test can fail by making it fail
once, on purpose, before trusting the suite.

## 10. Slim CI

`state:` compares nodes against a manifest supplied by `--state`. `state:new` means no node
with that `unique_id` exists in the comparison manifest; `state:modified` means new nodes
plus any change to existing ones. Sub-selectors exist because state comparison is complex
and every project differs: `state:modified.body` covers model SQL and seed values,
`state:modified.configs` covers configs while excluding database, schema and alias. The
inverses `state:old` and `state:unmodified` have no sub-selectors.

**The documented false-positive and false-negative sources**, which matter because Slim CI
silently over-builds or under-builds rather than failing:

- **Macros are the main cause of over-selection.** Any resource depending on a changed
  macro, or on a macro depending on a changed macro, is marked modified.
- **`var` and `env_var` changes are the false-negative.** dbt cannot trace that lineage, so
  a value change does not by itself put a model in `state:modified`, though it is likely
  flagged if it produces a different config.
- **Seeds under 1 MiB are compared by contents; at or above 1 MiB only by file path**, with
  a warning that contents cannot be compared. A large seed can change without being
  selected.
- **Pointing `--state` at `target/` fails silently.** dbt overwrites
  `target/manifest.json` during parsing, so you get a "saved manifest not found" warning and
  no detected changes. Copy the manifest into a dedicated `state/` directory, or use
  `--no-write-json`.
- **Stale comparison artifacts across concurrent work.** dbt uses the last successful run of
  *any* job in the deferred environment, so a busy staging environment overwrites the
  manifest, and a deploy that refreshes it while other pull requests are open makes those
  requests select unrelated modified nodes until they rebase.
- **Cross-environment test hazard.** A deferred `relationships` test with one modified and
  one unmodified parent queries across two environments. The documented workaround excludes
  `test_name:relationships` from the state-selected test run.

**`--defer` resolves a `ref` from the state manifest only if the node is unselected and
absent from the database**, unless `--favor-state`, which prefers the state definitions
unconditionally. `--defer-state` can point at a different manifest from `--state`.

**The `state:modified+` cost nobody budgets for:** the first CI execution of a modified
incremental model in a pull-request schema builds it in full, because `is_incremental()` is
false against an empty target. That can pass in CI while the post-merge incremental run
fails, for instance on schema drift under `on_schema_change: fail`. The documented
mitigation is to `dbt clone` pre-existing incremental models into the pull-request schema as
the first CI step. **This is a channel-sequencing failure in miniature**, and it is the
cheapest place to see the pattern: CI validated a different code path from the one
production will run.

Also worth stating plainly: **`state:modified` ignores upstream data changes**, so it is a
code-change detector and never a data-correctness gate.

## 11. Adapter differences that change project design

Verified 2026-07-29 from the adapter config pages; the dbt-snowflake and dbt-fabric items
are second-hand.

**dbt-databricks** (fetched). `merge` is the default strategy with no `incremental_strategy`
set, and is Delta and Hudi only. `replace_where` is Delta only and matches on
`incremental_predicates`. `delete+insert` is Delta only, v1.11+, and requires `unique_key`.
Materializations: `table`, `incremental`, `materialized_view`, `streaming_table`.

- **v1.11.0 is a breaking change**: incremental models require Databricks Runtime 12.2 LTS
  or higher, because of `INSERT BY NAME` syntax, and this affects every strategy. Check the
  runtime before upgrading the adapter.
- Clustering: `liquid_clustered_by` since 1.6.2, which issues `OPTIMIZE` after each run and
  is disabled with a skip-optimize variable; `auto_liquid_cluster` since 1.10.0, which must
  not be combined with `liquid_clustered_by`; legacy `clustered_by` requires `buckets`.
  Clustering on materialized views and streaming tables is 1.11+.
- Unity Catalog uses the three-level `catalog.schema.table` namespace, with an optional
  `catalog:` in the profile alongside the required `schema:`.
- `row_filter` is 1.12+ and is supported on table, incremental, materialized view and
  streaming table, **but not on views or Hive Metastore relations**.
- `on_configuration_change`: materialized views need drop-and-recreate for everything except
  schedule updates; streaming tables only for `partition_by` changes.

**dbt-snowflake dynamic tables** (second-hand). `materialized='dynamic_table'` with
`target_lag` (a time delta of at least one minute, or `downstream`) and
`snowflake_warehouse`. `refresh_mode` takes `INCREMENTAL`, `FULL`, `AUTO` or `ADAPTIVE`.
The scheduling model is the important part: **with `target_lag` set, Snowflake refreshes
autonomously and `dbt run` only creates or alters the definition without triggering a
refresh.** Omitting `target_lag`, or `scheduler: DISABLE`, makes dbt issue an explicit
synchronous refresh that does not cascade to downstream dynamic tables. Reported
limitations: SQL cannot be updated in place and needs `--full-refresh`; cannot sit downstream
of materialized views, external tables or streams; cannot reference a view downstream of
another dynamic table; model contracts unsupported.

**dbt-fabric** (second-hand). Default strategy is `merge` from adapter v1.9.7; also
`append`, `delete+insert`, `microbatch`. Documented limitations that change how you write
models: **nested CTEs are unsupported in model materialization** and multiple nested CTEs may
fail at compile or execute time; source table columns cannot carry constraints; indexes are
unsupported by Fabric Warehouse and the index config is ignored; grants with
auto-provisioning are unsupported. Warehouse snapshots require a `workspace_id` and a
snapshot name in `profiles.yml`.

**The design consequence.** The default strategy differs by adapter, the strategy set
differs by adapter and table format, and clustering configuration is adapter-specific. A
project intended to be portable across two of these platforms should set
`incremental_strategy` explicitly on every incremental model rather than inheriting a
default, and keep platform-specific physical configuration in one place instead of scattered
across models.

## 12. dbt, SQLMesh, and the licensing state

**The licensing position as of 2026-07-29** (second-hand from near-primary sources; fetch
the licenses FAQ and the dbt Core v2 announcement directly before repeating any of it in a
deliverable):

- The Fivetran and dbt Labs merger was announced 2025-10-13 and **completed 2026-06-01**.
- Fusion launched in public beta 2025-05-28 under Elastic License v2. On **2026-06-01** dbt
  Labs announced that the Fusion engine powers both dbt Core and the proprietary Fusion
  distribution of dbt v2.0, with that code published in the `dbt-core` repository under
  **Apache 2.0**, previously-ELv2 code relicensed, and the `dbt-fusion` repository archived.
  A separate product licensing agreement governs the Fusion **binary**, which remains
  proprietary.
- **MetricFlow moved to Apache 2.0 in October 2025** (AGPL through 0.140.0, BSL from
  0.150.0 to 0.208.2, Apache-2.0 from 0.209.0). This was independently confirmed by a second
  research pass.
- dbt Core v2.0 was reported as alpha and dbt State as preview at the 2026-06-01
  announcement, so **version pinning and the Core-versus-Fusion distribution choice are live
  decisions for a greenfield project** rather than settled ones.

**SQLMesh** is Apache 2.0, and Fivetran contributed it to the Linux Foundation, announced
2026-03-25. So both tools now sit under permissive licenses, and the merger placed both
under one commercial parent, which removes licensing as the axis of the decision and leaves
mechanism.

**The mechanical difference.** SQLMesh parses SQL into an AST with SQLGlot rather than
treating it as Jinja strings, which is what gives it compile-time validation, native
column-level lineage, transpilation, and automatic change categorization: `plan` classifies
each change as breaking or non-breaking and shows exactly which intervals need backfill
before anything executes. Its virtual data environments are sets of views over shared
physical snapshot tables, so a dev environment with no model changes points at the same
physical data with no copy, promotion is an atomic view-pointer swap, and rollback is the
same operation.

**Where dbt wins**, per the same sources: simplicity for small or low-risk pipelines, direct
execution with no state layer, and an ecosystem advantage. A single-dialect team with stable
macros gains little from the AST model. SQLMesh can run existing Jinja dbt models through
its dbt adapter, so migration friction is lower than a rewrite.

**Read the comparison critically.** The SQLMesh-versus-dbt comparison page is authored by
the SQLMesh vendor, and no dbt-authored rebuttal was located. Its framing of dbt is
interested rather than neutral, and the factual mechanics above are more reliable than its
conclusions.

**The decision heuristic.** Choose SQLMesh when the cost of a wrong deployment is high and
you need to know the blast radius before applying, because breaking-change classification and
atomic environment promotion are the features and they have no dbt equivalent. Choose dbt
when the ecosystem, hiring pool and integration surface matter more than deployment safety,
which is most estates. Reversal cost runs asymmetrically: dbt to SQLMesh is eased by the dbt
adapter, SQLMesh to dbt means giving up the virtual environments the workflow was built on.

## 13. Checked and inconclusive

- **Intermediate and marts layout pages** were not fetched, so the `int_` prefix, the
  `fct_`/`dim_` naming rules, marts materialization guidance and the per-directory `+schema`
  example are convention here rather than verified documentation. Fetch
  `docs.getdbt.com/best-practices/how-we-structure/3-intermediate` and `4-marts`.
- **Whether partitions the source has stopped emitting persist under dynamic mode on
  dbt-spark** is not stated by any source reached. It follows logically, and it is not
  asserted. The macro shows only a plain `insert overwrite`.
- **`--full-refresh` interaction with `insert_overwrite`** was not confirmed on either
  adapter.
- **Whether `partitionOverwriteMode=dynamic` is the effective default on dbt-spark** is
  unresolved; the adapter sets nothing and the docs guidance is second-hand.
- **microbatch maturity label** (beta versus GA as of 2026-07) is unverified, as is the
  microbatch column of the adapter matrix for adapters other than Databricks and Snowflake:
  the fetched matrix and the microbatch page conflict, and the conflict is recorded rather
  than resolved. **Do not encode the microbatch column into a linter rule without re-reading
  the live table.**
- **Constraint support and enforcement per adapter** was not established. The canonical
  constraints page was not fetched. Note that enforcement is separately governed by the
  platform, per the law that nothing enforces your keys.
- **`severity`, `error_if`, `warn_if`, `store_failures`, `store_failures_as`** were not
  verified at all and nothing is asserted about them.
- **`hard_deletes` support on dbt-databricks and dbt-fabric**: the docs list postgres,
  bigquery, snowflake and redshift. Absence from that list is not proof of non-support.
- **Default materializations for dbt-snowflake and dbt-fabric** were not stated on any page
  reached; dbt-core's `view` default is presumed but unverified.
- **Why snapshots are type-2 only**: no primary statement located.
- **manifest v12 field detail** for `config.incremental_strategy` and the source `freshness`
  sub-shape was not enumerated in prose docs. Use the machine-readable JSON Schema at
  `schemas.getdbt.com` for manifest v12. Note that **v12 spans Core 1.8 through 1.11 and
  Fusion 2.0**, so the schema version alone does not identify the dbt version: key off
  `metadata.dbt_version` and tolerate additive fields.
