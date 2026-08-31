# Delivery and physical design

How an agreed model becomes loaded tables. The logical design should survive this
step nearly unchanged: in dimensional modeling the physical schema closely
resembles the logical one, and a physical design that renormalizes the star has
undone the work.

| § | Topic |
|---|---|
| 1 | The 34 ETL subsystems |
| 2 | The ten-step build sequence |
| 3 | Physical design |
| 4 | Real-time considerations |
| 5 | Lakehouse platforms (see `lakehouse-practice.md`) |

## 1. The 34 ETL subsystems

Kimball's inventory of what a dimensional back room needs. Use it as a coverage
checklist against an existing pipeline: the missing ones are usually 5, 6, 16, 24
and 29, and each absence has a characteristic failure.

**Extracting (1 to 3)**

| # | Subsystem | What it does |
|---|---|---|
| 1 | Data profiling | Establishes what the source actually contains before anyone promises a grain |
| 2 | Change data capture | Isolates what changed, so loads are incremental. Its quality bounds every SCD decision downstream |
| 3 | Extract system | Gets the data out and into the staging area |

**Cleaning and conforming (4 to 8)**

| # | Subsystem | What it does |
|---|---|---|
| 4 | Data cleansing | Applies data quality screens (column, structure, business rule) |
| 5 | Error event schema | The dimensional model of screen failures: an error event fact table plus a per-column detail table |
| 6 | Audit dimension assembler | Attaches load metadata and quality indicators to the facts produced |
| 7 | Deduplication | Survivorship and matching, typically for customer and party data |
| 8 | Conforming | Enforces conformed dimension and conformed fact definitions across sources |

**Delivering (9 to 21)**

| # | Subsystem | What it does |
|---|---|---|
| 9 | SCD manager | Applies types 0 through 7 and maintains housekeeping columns |
| 10 | Surrogate key generator | Independent and sequence-driven; database triggers bottleneck |
| 11 | Hierarchy manager | Populates fixed, slightly ragged and ragged hierarchy structures |
| 12 | Special dimensions manager | Date and time dimensions, junk dimensions, mini-dimensions, audit and shrunken dimensions, small static dimensions |
| 13 | Fact table builders | Transaction, periodic snapshot and accumulating snapshot loaders, each with different update semantics |
| 14 | Surrogate key pipeline | Replaces natural keys with the right surrogate keys and guarantees referential integrity |
| 15 | Bridge table builder | Builds and maintains multivalued and variable-depth hierarchy bridges, including time-varying ones |
| 16 | Late arriving data handler | The separate code path for delayed facts and placeholder dimensions |
| 17 | Dimension manager | The single authority publishing each conformed dimension to its subscribers |
| 18 | Fact provider | The subscriber that attaches published dimensions to its facts and rebuilds what a type 1 or type 3 change invalidated |
| 19 | Aggregate builder | Builds and maintains aggregate fact tables and their shrunken dimensions |
| 20 | OLAP cube builder | Feeds cubes from the relational star rather than from the source |
| 21 | Data propagation manager | Delivers conformed data outward to downstream consumers |

**Managing (22 to 34)**

| # | Subsystem | What it does |
|---|---|---|
| 22 | Job scheduler | Dependency-aware execution of the load sequence |
| 23 | Backup system | Backup, archive and retrieval, with retrieval actually tested |
| 24 | Recovery and restart | Resume or unwind a failed load, which is what fact table surrogate keys enable |
| 25 | Version control | The ETL code, versioned |
| 26 | Version migration | Promotion between environments |
| 27 | Workflow monitor | Job status, durations, trends |
| 28 | Sorting | Sorting as an explicit, tuned step |
| 29 | Lineage and dependency analyzer | Answers "where did this number come from" and "what breaks if I change this" |
| 30 | Problem escalation | Defined paths from automated detection to a human |
| 31 | Parallelizing and pipelining | Throughput without hand-written concurrency |
| 32 | Security | Role-based access across the back room and the delivered data |
| 33 | Compliance manager | Lineage, retention, and the audit trail regulators ask for |
| 34 | Metadata repository | Business, technical and process metadata in one place |

Requirements to settle before designing any of it: business needs, compliance,
data quality, security, data integration, latency, archiving and lineage, BI
delivery interfaces, available skills, and existing tool licenses. Latency is the
one that quietly determines the architecture.

## 2. The ten-step build sequence

1. **Draw the high-level plan.** Sources to targets on one page, before any tooling.
2. **Choose the ETL approach.** Tool or hand-code, decided on the requirements above
   rather than on preference.
3. **Develop default strategies** for extract, change capture, archiving, auditing,
   error handling and recovery, so each table does not reinvent them.
4. **Drill down by target table.** Detailed schematics per table, ensuring clean
   hierarchies, ending in the ETL specification document.
5. **Load dimension historically.** Start with the simplest dimensions to build the
   team's rhythm; date dimension first, then type 1 dimensions, then type 2 history.
6. **Load facts historically.** The bulk load, with audit statistics captured.
7. **Dimension incremental processing.** Extract, detect new and changed rows,
   then route each change to its attribute's SCD type.
8. **Fact incremental processing.** Extract, quality checkpoint, surrogate key
   pipeline, load. Snapshot tables and late arriving facts take different paths.
9. **Aggregates and OLAP.** Built after the atomic layer exists, never instead of it.
10. **Operate and automate.** Scheduling, predictable exceptions handled
    automatically, unpredictable ones failing gracefully and loudly.

Steps 5 and 6 exist only once; steps 7 and 8 run forever. Effort estimates that
treat the historic load as the project underestimate by the difference.

## 3. Physical design

**Naming and null standards first.** Table and column names are the BI interface.
Decide key declaration and null permissibility policy at the same time.

**Additional tables to plan for** beyond the star itself: staging tables for the
ETL, audit and data quality tables, and whatever structures secure access to a
subset of the warehouse requires.

**Indexing** for analytics is not indexing for transactions:

- Dimension tables get a unique index on the single-column primary key.
- Dimension attributes used for filtering and grouping, especially in combination,
  get bitmap indexes where the platform has them, otherwise evaluate B-trees.
- The first fact table index is typically a B-tree or clustered index on the primary
  key, with the **date foreign key in the leading position**, which helps both loads
  and queries because date is the most constrained column.
- High-cardinality bitmap indexes on individual fact foreign keys, where available,
  are more forgiving than a clustered index when users constrain dimensions in ways
  nobody predicted.
- On a row-store platform, remember that the clustered key is carried inside every
  nonclustered index, so a wide clustered key inflates all of them. Narrow, unique,
  ever-increasing and stable is the target; covering indexes with included columns
  are how a specific report query stops touching the base table.

**Aggregates beat hardware.** Aggregation is the most cost-effective performance
lever, and adding capacity is usually not. Aggregate either by dropping dimensions
or by rolling up to a shrunken conformed dimension. You cannot build every possible
aggregate, so choose using two inputs: the access patterns from requirements and
from real monitored usage, and the statistical distribution of the data.

**Partition large fact tables by activity date**, typically monthly, presenting as
one table. It pays off in loading, maintenance and query pruning at once.

Expect the aggregate and index strategy to change as usage becomes known, but ship
the first release already indexed and aggregated: a warehouse that is slow on day
one gets abandoned before day thirty.

## 4. Real-time considerations

Real-time delivery is a triage decision before it is a technical one: classify each
requirement as daily batch, frequent micro-batch, or genuine streaming, and push
back on anything claiming streaming without a decision that changes inside the hour.

What real-time typically costs: data quality screens get thinner, facts post before
their dimensional context arrives (which is what late arriving dimension
placeholders are for), staging shrinks or disappears, and a hot partition holds
recent rows unaggregated and unindexed until the batch cycle folds it in. Each of
those is a trade to decide explicitly.

## 5. Lakehouse platforms

The ETL subsystems and the ten steps above are platform independent. The mechanics of
applying them on Databricks, Fabric, Snowflake and dbt are not, and they change fast
enough to be worth isolating: they live in `lakehouse-practice.md`, which covers
medallion layer placement, the constraint-enforcement collapse and the `RELY`
wrong-results trap, per-platform surrogate key and SCD type 2 mechanics, the semantic
layer boundary, and a register of what a verification pass could not confirm.

Two things from that file belong here because they change the physical design advice
in §3 directly:

**Indexes mostly do not apply.** On columnar and lakehouse platforms, clustering,
partitioning, file-level statistics and data skipping replace bitmap and B-tree
tuning. What survives is the principle: give the engine a date column it can prune
on, and keep dimension tables small enough to broadcast.

**Nothing enforces referential integrity.** Primary and foreign keys are declarative
metadata on every major lakehouse platform, so the surrogate key pipeline's
unknown-member discipline is the only thing standing between a failed lookup and a
silently wrong measure.
