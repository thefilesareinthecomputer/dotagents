# Dimensional modeling in a medallion lakehouse

How the classical techniques are actually applied on Databricks, Microsoft Fabric,
Snowflake and dbt, and which classical assumptions those platforms break.

Platform mechanics verified 2026-07-29 against primary vendor documentation. Claims
that are practitioner practice rather than vendor guidance are labelled as such,
because the difference decides how hard you argue for them. §11 records what a
verification pass could not confirm, so folklore does not get reasserted here later.
Version-sensitive lines rot; re-verify before leaning on one.

| § | Topic |
|---|---|
| 1 | Where the model lives across the layers |
| 2 | The enforcement collapse: keys are metadata now |
| 3 | Grain when the source is a change feed |
| 4 | Surrogate keys per platform |
| 5 | SCD type 2 per platform |
| 6 | Star versus wide gold table |
| 7 | Physical layout is a concurrency decision |
| 8 | Conformance across a lakehouse |
| 9 | The semantic layer boundary |
| 10 | What the lakehouse genuinely changed |
| 11 | Checked and inconclusive |

## 1. Where the model lives across the layers

Vendor guidance converges on the dimensional model living at the serving layer and
diverges on how much modeling happens before it.

- **Databricks** puts it in gold explicitly: gold is where you model data for
  reporting and analytics using a dimensional model, establishing relationships and
  defining measures. The same page says modeling commonly *starts* in silver,
  specifically how to represent nested and semi-structured data (VARIANT versus
  structs versus flattening). Medallion doc updated 2026-05-07.
- **Microsoft Fabric** goes further: a star schema is "a recommended design approach"
  for a Fabric Warehouse and "a prerequisite for enterprise Power BI semantic
  models". Fabric also concedes a boundary honestly: a self-service
  "quasi-dimensional model" built in Power Query cannot manage historical change, so
  any SCD requirement forces a real warehouse plus ETL. Doc updated 2026-07-06.
- **Snowflake** publishes no medallion-layer guidance (do not claim it does), but its
  semantic views documentation says plainly: start with a simple star schema.

**The transform-layer mapping.** The modern toolchain has a named slot for each
Kimball job, and the names are worth using because they carry the rules:

| Layer | Rule |
|---|---|
| Staging | One model per source object, 1:1, renaming and recasting only. No joins, no business logic. |
| Intermediate | Structural simplification and **re-graining**. This is where fan-out happens if it happens. |
| Marts | One canonical model per business entity at one declared grain. Multi-source unions resolve **here, once**. |

Conforming many per-source variants into one subject-area table *is* the Kimball
integration layer. The named anti-pattern is per-team rebuilds of the same concept,
which is the bus matrix's job to prevent.

**Two rules about the layers that are easy to get wrong:**

- **Silver must retain at least one validated, non-aggregated representation of every
  record. Aggregation is a gold-only act.** A silver layer that has already summarized
  has destroyed the atomic grain that gold's flexibility depends on.
- **Deduplication belongs exactly one layer downstream of where duplicates are
  created.** An append-only raw layer plus a rebuildable conformed layer is what makes
  at-least-once ingestion sufficient: the raw layer is allowed to contain duplicates
  because the layer that reads it removes them and can be rebuilt. Trying to guarantee
  exactly-once at the landing layer buys complexity that the next layer makes redundant.
- **Start less normalized and add normalization only when query patterns justify it**,
  rather than normalizing on principle. Silver is often described as "mostly 3NF-like",
  which describes where it tends to land rather than prescribing a shape.

**Silver layout is a genuine tradeoff** (practitioner practice). Schema-per-source
buys coarse grant boundaries and re-introduces the per-source sprawl you then have to
re-conform; schema-per-domain buys one canonical model and pushes access control onto
table grants, dynamic views or row filters. Platform guidance leans domain-aligned but
explicitly declines to mandate a schema hierarchy. Present it as a tradeoff to whoever
owns access control.

**Naming and catalog layout** (practitioner practice, *not* vendor guidance - checked
2026-07-29 and no Databricks guidance on either point exists): encoding the layer or
the source system into table-name prefixes duplicates what the catalog and schema
already say. Catalog-per-environment with medallion-as-schemas is the common default
for SDLC isolation; catalog-per-layer alone collapses environment isolation, because
there is then nowhere left to put dev and prod.

**The conformance gap in vendor guidance.** Databricks' medallion page recommends a
dimensional model without ever defining conformed dimensions, a bus matrix or a grain
declaration, and encourages multiple per-domain gold layers. Per-domain gold without
conformed dimensions is precisely the arrangement that produces two `dim_customer`
definitions and reports that will not reconcile. The guidance is not wrong, it is
silent on the part that fails.

## 2. The enforcement collapse

Kimball assumed a relational database that enforces primary and foreign keys. No major
lakehouse platform does. This moves grain and referential integrity from the database
into the ETL, permanently.

| Platform | Enforced | Declared only |
|---|---|---|
| Databricks (Unity Catalog + Delta) | NOT NULL, CHECK | PRIMARY KEY, FOREIGN KEY, UNIQUE |
| Microsoft Fabric Warehouse | NOT NULL | PRIMARY KEY, FOREIGN KEY, UNIQUE (`NONCLUSTERED NOT ENFORCED` syntax required) |
| Snowflake standard tables | NOT NULL, CHECK | PRIMARY KEY, FOREIGN KEY, UNIQUE |
| Snowflake hybrid tables | all of them, and a primary key is mandatory | none |

Databricks specifics: PK/FK are Unity Catalog and Delta only, from DBR 13.3 LTS and GA
from DBR 15.2; foreign keys are unsupported in `hive_metastore`; UNIQUE is public
preview from DBR 18.2; `CREATE TABLE AS SELECT` ignores constraints entirely; and
deleting a parent row triggers nothing, with no restrict, cascade or nullify available.

**The `RELY` trap, which both major vendors document as a wrong-answer risk.** A
declared constraint is inert until you tell the optimizer to trust it, and then it
stops being inert:

- Databricks: "relying on an unsatisfied constraint may lead to incorrect query
  results." The demonstrated case is a `RELY` primary key letting Photon rewrite
  `SELECT DISTINCT` into a plain `SELECT`, so duplicate keys surface as duplicated
  rows. Default is `NORELY`.
- Snowflake ships a formal behavior-change note titled "Potential for wrong results
  when the RELY property is set" (bundle 2025_03, BCR-1902). `RELY` enables join
  elimination and is off by default.

Declare keys, because BI tools and semantic-model builders read the declarations to
infer relationships. Enable `RELY` only where the load provably guarantees the
constraint. A `RELY` declaration over dirty data converts a data quality problem into
wrong numbers with no error raised.

**What replaces enforcement** is the discipline Kimball already specified, now
load-bearing. Fabric states it as a requirement: the ETL must test integrity between
related tables on load, and a fact row whose dimension lookup fails is still inserted
against a special Unknown member and corrected later. Rejecting the row makes the
measure silently wrong; nulling the key breaks referential integrity outright.

**Re-graining demands a new primary-key test at the new grain.** The intermediate
layer's whole job is re-graining, and nothing else in the stack will notice that a
join fanned out. On an enforcing database a duplicated key raises an error; here it
silently doubles a measure. The uniqueness test at the new grain is not optional
hygiene, it is the only detector.

**And the usual way of establishing that a key is unique is wrong.** A column unique
across a *sample* is a shortlist entry, never a merge key. A key that holds most of the
time fans out the merge and writes duplicate rows into history, and no later correction
repairs that, because the duplication is now historical fact. Two rules follow:

- **Settle each shortlisted column with an exact distinct count against every row, run
  at the source.** It is cheap precisely because the shortlist is short.
- **Approximate cardinality errs in the dangerous direction.** An approximate distinct
  count can over-count and therefore *nominate* a column that is not unique. Use it to
  build the shortlist, never to make the decision. The asymmetry generalizes: cheap and
  wrong is fine for description, never for a gate that writes history.

If the profiling sample hit its row cap, uniqueness within it proves nothing at all and
the shortlist must be treated as empty.

## 3. Grain when the source is a change feed

This is where classical practice most needs updating, and where the obvious
implementation is wrong.

**A CDC cursor tracks modified time, so a backdated record arrives in bronze
correctly. The loss happens downstream, at the predicate.** A row with a month-end
business date entered ten days later gets a fresh modified timestamp, so the cursor
catches it and bronze is complete. A transform that then selects on *business* date
drops it, and no window width fixes that. The rules that follow:

- **Select by arrival, MERGE on a unique key.** Keep the business-date window purely
  as a bounded reprocessing scope.
- **`DELETE+INSERT` over a business-date window is the specific antipattern.** It
  deletes rows the new window will not re-supply.
- **Widening the reprocessing window is symptom treatment whenever the predicate
  column is wrong.** A quality screen selecting on business date rejects
  correctly-loaded late rows, and more days only buys grace sized to the close
  calendar. Diagnose the predicate before touching the width.

**A modified date and a business date are indistinguishable by shape.** Profiling the
column will not tell you which one you have, so this is a contract question to settle
with the source owner rather than a data question to answer by inspection.

**When two sources get the same widened window and only one recovers, the window was
never the variable.** The defect lives in one of three places, and naming which one
comes before any window change: whether the extract actually returns the changed rows,
whether the transform's predicate selects them, or whether the downstream dimension
joins **fail open** (dropping or nulling the row) or **fail closed** (raising). Two
sources differing under identical treatment are differing in join behavior, and
re-running an unchanged-input pipeline simply rewrites the same wrong values.

**Effective-date filtering and incremental-watermark filtering are orthogonal, and
conflating them is a silent correctness bug.** A source table carrying
effective-start/effective-end rows already *is* SCD type 2 at the source. A cursor on
last-update tells you which rows are new *to you*; it says nothing about which version
is *current*. Bronze inherits the versions; point-in-time needs a `BETWEEN` on the
effective dates, and full history drops the filter and orders by effective start plus
any intra-day sequence.

**The sequencing column is a design-time decision, and the obvious column is the wrong
one.** Databricks AUTO CDC requires a sequencing column that is monotonically
increasing, has no NULLs, and has exactly one distinct update per key per value.
Extraction timestamps are *not* monotonic with load order, so `WHERE ts > max(ts)`
against one silently drops rows permanently. Choose the ordering column while choosing
the source, which is well before the pipeline can tell you it was wrong.

**A pure high-water-mark read cannot detect hard deletes, on any engine.** Every
watermark design needs a companion delete strategy: log-based capture, a periodic
active-key reconciliation extract, or an explicitly accepted soft-delete-only
contract. For full-extract-only sources the pattern is set reconciliation: a separate
job extracts the complete current key set, warehouse keys absent from it are
soft-deleted after a grace period, and reappearing keys reactivate. The grace period
exists to absorb schedule skew between the two jobs.

**Soft delete is the default in managed ingestion, so "the current row" always
requires an explicit filter**, and consumers who forget it double-count. The
current-row pattern is `ROW_NUMBER()` partitioned by the key, ordered by extraction
time then the connector's tie-break index, keeping rank 1 and not-deleted. Under
history mode the pattern inverts: do not window at all, filter the active flag.

## 4. Surrogate keys per platform

- **Fabric Warehouse** recommends the smallest possible integer type and now has
  IDENTITY columns, with limitations. This is a real 2025 to 2026 change: Fabric
  Warehouse previously had neither IDENTITY nor SEQUENCE, forcing `ROW_NUMBER()`, key
  control tables or hash keys. Guidance written before that change is stale.
- **Fabric's documented failure mode**, which generalizes everywhere: never truncate
  and fully reload a dimension whose surrogate keys are generated, because every fact
  row referencing the old keys is invalidated. Date and time dimensions are exempt,
  their keys being computed rather than assigned.
- **Snowflake sequences** carry explicit caveats: values are not guaranteed gap-free;
  global uniqueness holds only while the interval sign is unchanged, and flipping the
  sign may duplicate; `NOORDER` gives up ordering.
- **Computed date keys** (`YYYYMMDD`) remain sanctioned and Fabric names them
  explicitly. The date dimension stays the standing exception to the meaningless-key
  rule.
- **Hash keys** (a deterministic hash of the natural key, plus the effective timestamp
  for type 2 rows) are the common distributed substitute: uniqueness and joinability
  without coordination, at the cost of the small-integer property, ordering, and extra
  bytes in every fact table. Choose them for the coordination-free property and say so.
- **When the source has no primary key, the ingestion tool mints the key**, and that
  key becomes load-bearing outside the modeler's control. A connector-generated
  synthetic id plus an ordering index is what makes deduplication possible at all, so
  those columns cannot be dropped from the model even though nobody designed them.

The durable key requirement survives all of this: something must identify the entity
across all of its type 2 rows.

## 5. SCD type 2 per platform

No platform automates the full catalog. Types 3 through 7, mini-dimensions and bridge
tables are hand-built everywhere.

**Databricks Lakeflow Declarative Pipelines, AUTO CDC.** Formerly APPLY CHANGES;
`AUTO CDC INTO` in SQL, `create_auto_cdc_flow()` in Python, plus
`create_auto_cdc_from_snapshot_flow()` for snapshot sources. Old names still work and
Databricks recommends the new ones. Delta Live Tables is now Lakeflow Declarative
Pipelines, docs under `/ldp/`.

- Two entry points: AUTO CDC when the source has a change feed, AUTO CDC FROM SNAPSHOT
  (Python only) when it does not, comparing consecutive snapshots into a synthetic
  change feed. The old batch-versus-CDC fork is now two named APIs.
- Both compute type 1 and type 2 via `STORED AS SCD TYPE 1 | SCD TYPE 2` and
  `TRACK HISTORY ON`. `STORED AS BITEMPORAL` (Beta) tracks valid time and system time
  together, going past the classical type list.
- Contracts that are really modeling constraints: target must be a declared streaming
  table; specifying the schema means including `__START_AT` and `__END_AT` typed like
  `sequence_by`; the sequencing column must be monotonic with one distinct update per
  key per value and no NULLs; snapshots must arrive in ascending version order and
  out-of-order snapshots are ignored.
- Entitlement: requires serverless Lakeflow pipelines or the Pro and Advanced
  editions, and is absent from open-source Spark Declarative Pipelines.

**Hand-rolled `MERGE` is the fallback, and it has two preconditions.** Delta raises
`DELTA_MULTIPLE_SOURCE_ROW_MATCHING_TARGET_ROW_IN_MERGE` when multiple source rows
match one target row, because the result would be ambiguous, so **pre-deduplicating
the source is a correctness precondition, not an optimization**. (On DBR 15.4 LTS and
below, only ON-clause conditions count toward matching.) Second, add
`WHEN MATCHED AND source_ts > target_ts` so a late-delivered older event can never
overwrite a newer committed row.

**dbt snapshots.** Type 2 only, on every warehouse dbt supports. Meta columns
`dbt_valid_from`, `dbt_valid_to`, `dbt_scd_id`, `dbt_updated_at`, plus
`dbt_is_deleted` when `hard_deletes='new_record'`. Strategies are `timestamp`
(recommended) and `check` with `check_cols`. From dbt Core v1.9 the YAML `snapshots:`
config is the recommended form over `{% snapshot %}` blocks, adding
`dbt_valid_to_current`, `snapshot_meta_column_names` and `hard_deletes`. Documented
limits: snapshots cannot share a directory with models, dbt will not drop a column
that disappears from source, and it will not change column types beyond widening
varchars. Docs updated 2026-07-28.

**Snowflake contradicts itself, so decide deliberately rather than by whichever page
you land on.** The decision guide routes type 2 to streams and tasks, describing
dynamic tables as maintaining current state rather than history; the dynamic tables
overview says a dynamic table can produce type 2 using window functions over a change
stream. If you take the dynamic tables route, know what silently forces a full refresh
instead of incremental: unsupported constructs, a `FULL` refresh upstream, window
functions without `PARTITION BY`, the change-tracking requirement, and
reinitialization after clone or failover. A type 2 dimension that quietly switched to
full refresh is a cost and latency problem that looks like nothing at all.

**Fabric.** `MERGE` in Fabric Warehouse is still maturing and partitioning is
unavailable, so hand-rolled type 2 merges are rougher there than on Delta.

**A managed connector's "history mode" is SCD type 2 at bronze, and it is not
retroactive.** It captures history only from the moment it is switched on, per table.
That moves the type 2 decision earlier than classical practice assumes: it becomes an
ingestion-design decision made before the first sync, not a modeling decision made
during session 5. Switching it on later leaves a permanent hole, and it raises the
billing meter because every version counts as a row.

## 6. Star versus wide gold table

Settled: Snowflake-style normalization of dimensions has lost on columnar engines.
Compression makes repeated dimension strings cheap, so normalizing buys little storage
and costs join hops. Start from a star.

**The real deciding factor between a wide gold table and a star is
incrementalizability, not query speed.** This is the finding that replaces a decade of
unsourced performance argument with a mechanical test:

- Incremental refresh of a Databricks materialized view is **serverless-only**;
  non-serverless materialized views fully recompute on every refresh. Row tracking is
  required for some operations, and change data feed is a performance recommendation
  rather than a hard requirement.
- `EXPLAIN CREATE MATERIALIZED VIEW` reports whether a definition is structurally
  eligible for incremental refresh **before you build it**. Run it.
- Even when eligible, the `AUTO` refresh policy lets the cost model choose a full
  recompute anyway; `INCREMENTAL STRICT` forces the issue.

So: choose a wide denormalized gold materialized view when the definition
incrementalizes *and* consumption is a small number of known queries. Choose a star
when the view would fully recompute, when consumers slice by dimensions nobody
anticipated, or when conformed dimensions must be shared across processes. A wide view
that cannot incrementalize is a full recompute of a wide join on every refresh, which
is a cost problem that grows silently.

What is still missing from the star-versus-wide debate is performance evidence: no
current reproducible vendor benchmark turned up, and no engine documents join behavior
specifically for star schemas. Treat performance arguments in either direction as
unsourced. The one documented mechanical trade is that a fully flattened table reads
more bytes per query than a narrow fact joined to small dimensions.

The decision that holds regardless: build the star at the atomic grain, and treat any
wide table as a derived projection with an owner and a refresh contract, never as the
place the grain lives.

## 7. Physical layout is a concurrency decision

Classical physical design optimizes for pruning. On a lakehouse with continuous
merges, layout decides whether concurrent writes collide at all.

- Databricks documents it directly: "Tables with liquid clustering automatically
  enable row-level concurrency", and "Tables do not support row-level concurrency if
  they have partitions defined or do not have deletion vectors enabled." Conflicts are
  framed as file-set overlap: partitioned tables conflict when two writers may touch
  the same files, which is narrower than conflicting on every concurrent merge.
- Practical consequence: prefer liquid clustering over explicit partitioning for any
  table that takes continuous merges, which covers CDC-fed silver tables and type 2
  dimensions by construction.
- Cluster on the ingestion-order timestamp for CDC-fed tables, which is also the
  column §3 says to select on.
- Clustering must be set at table creation to take effect on a vendor-managed landing
  table.
- Do not stack two automatic optimizers on one table. If an ingestion vendor already
  runs scheduled VACUUM and OPTIMIZE on the tables it lands, enabling the platform's
  own predictive optimization there is double maintenance. Apply platform optimization
  to the tables you own.

## 8. Conformance across a lakehouse

Conformance was always an organizational problem. On a lakehouse it acquires a
mechanical cost boundary as well.

- **The catalog is the isolation boundary, not the metastore.** One metastore per
  region with business units isolated by catalog, workspace-catalog binding and
  storage isolation. Metastore-per-business-unit is justified only when zero sharing
  is required. `USE CATALOG` and `USE SCHEMA` grant no data access on their own.
- **A conformed dimension is cheap inside one metastore and expensive across
  metastores.** Inside, it is a grant. Across region, workspace or organization, it is
  a sharing protocol plus pairwise shares plus cloud egress on every cross-region
  read. Same-region Delta Sharing incurs no egress; cross-region and cross-cloud draw
  cloud-vendor egress charges (and Databricks bills SecureConnect egress itself).
  A bus matrix spanning two regions has a per-query bill attached to it.
- **Lineage does not survive a rename** of catalog, schema, table, view or column, and
  does not cross a metastore or region boundary, including cross-metastore sharing in
  the same account. **Renaming a conformed dimension is therefore a lineage-destroying
  act**, and any planned schema migration is a lineage event to be sequenced against
  whatever depends on the graph.
- **Governance can hard-fail modeling operations.** Time-travel queries fail on tables
  with active row filters or column masks (error class `ROW_COLUMN_ACCESS`), deep and
  shallow clones of such tables are unsupported, and a tag-driven column mask makes a
  `DROP` of the tagged column fail until the tag is removed. Validating a type 2
  dimension's history with time travel does not work on a masked table.
- **Some relationships are implementation-defined rather than discoverable.** Vendor
  documentation occasionally states that two concepts "may be unrelated, identical, or
  many-to-one". That is a business mapping to extract from people rather than a join to
  discover by profiling, and recognizing the class of question early saves weeks.

## 9. The semantic layer boundary

Every current semantic layer assumes a star, or something star-like, underneath. They
move metric *definitions* out of the physical tables; none removes the need for
conformed dimensions and declared keys.

- **Snowflake semantic views** arrived feature by feature rather than in one release:
  preview 2025-04-17, Snowsight 2025-10-02, standard-SQL querying 2026-03-02, entity
  filters 2026-05-05, variables 2026-06-26. Join paths resolve from declared
  `REFERENCES`, a direct dependency on the declared-key discipline in §2.
- **Databricks metric views** are YAML above the physical tables, queried with the
  `MEASURE()` function; docs gate them on DBR 16.4+ and 17.3+, and local metric views
  remain preview.
- **dbt Semantic Layer / MetricFlow** generates SQL for warehouse execution, where
  Snowflake and Databricks execute semantic objects in-engine. MetricFlow infers
  multi-hop join paths from entities in a semantic graph rather than from declared
  foreign keys.
- **Power BI semantic models** are the strongest documented case: Fabric calls a star
  schema a prerequisite for the enterprise version of them.
- **Open Semantic Interchange** is an announced cross-vendor initiative (Snowflake,
  Salesforce, dbt Labs and others, 2025-09-23) aimed at a portable semantic
  specification. Treat it as announced, and check its status before designing around
  it.

The consequence is small and sharp: a semantic layer is the right home for metric
definitions and the wrong home for grain and conformance. Two semantic models defining
the same measure over two unconformed dimensions have centralized the arithmetic and
preserved the disagreement.

## 10. What the lakehouse genuinely changed

Six things, separated from the longer list of things that only changed vocabulary.

1. **Enforcement moved to the ETL.** The assumption that the database protects the
   grain is now false everywhere, which makes the uniqueness test at each grain the
   only detector of fan-out.
2. **Types 1 and 2 became declarative**, with ordering expressed as a column contract
   rather than bespoke merge logic - and that contract constrains which source column
   may serve as the sequence.
3. **The type 2 decision moved earlier**, into ingestion design, because connector
   history mode is not retroactive.
4. **Bitemporal history is entering platforms directly**, extending past the classical
   type catalog rather than reinterpreting it.
5. **Representation decisions moved earlier**, into silver, because semi-structured
   source data must be typed and flattened before a dimensional model can exist.
6. **Layout became a concurrency decision** on top of being a pruning decision.

Everything else in the classical catalog survives unchanged: grain declaration, the
four steps, conformance, the bus matrix, fact table types, degenerate and junk and
role-playing dimensions, bridge tables, and the unknown member. What the lakehouse
changed is the mechanism layer underneath that reasoning.

## 11. Checked and inconclusive

Deliberately not asserted, because a pass on 2026-07-29 could not confirm it from a
primary source. Candidates for a future verification pass rather than gaps in the
reasoning above.

- Whether Apache Iceberg's table specification supports declared constraints at all,
  and in which spec version.
- A single GA date for Databricks metric views (docs gate on DBR versions instead) or
  for Snowflake semantic views as a whole (availability arrived feature by feature).
- Any reproducible current benchmark for star versus wide table, or engine
  documentation of join behavior specific to star schemas.
- Databricks IDENTITY column concurrency semantics, and Snowflake
  AUTOINCREMENT/IDENTITY behavior, hash-key guidance, and sequence behavior across
  clone and replication.
- Whether Unity Catalog lineage system tables have a published freshness SLA. None was
  found, but the search did not complete, so do not state the absence as a fact.
  Retention is documented as "rolling 1 year"; whether it is configurable was not
  established, and UI/API lineage is retained indefinitely for events after
  2024-09-01.
- Whether any authoritative source argues against building a physical date dimension.
  None was found and no search completed, so silence here is not evidence.
