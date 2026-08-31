# Architecture decisions

Choosing the shape: which platform, which layers, which boundaries, which components you
run yourself. The output of this altitude is a decision with its conditions and its
reversal cost written down, not a diagram.

Version-sensitive facts carry the date they were verified. Anything not settled from a
primary source is in [§9](#9-checked-and-inconclusive) rather than stated.

**Up:** nothing. This is the top.
**Down:** every choice here forecloses options in `source-to-bronze.md` (which lanes exist),
`transform-dbt.md` (which strategies the adapter offers), `cost.md` (the billing unit) and
`deployment.md` (what can be expressed as code).

## Contents

1. [The discovery frame](#1-the-discovery-frame)
2. [Platform archetypes and their triggers](#2-platform-archetypes-and-their-triggers)
3. [Table format and catalog](#3-table-format-and-catalog)
4. [Open source treated as a vendor](#4-open-source-treated-as-a-vendor)
5. [Layering and the governance boundary](#5-layering-and-the-governance-boundary)
6. [Isolation: which layer is actually the boundary](#6-isolation-which-layer-is-actually-the-boundary)
7. [The serving layer and the two semantic layers](#7-the-serving-layer-and-the-two-semantic-layers)
8. [Migrate versus stay, build versus buy](#8-migrate-versus-stay-build-versus-buy)
9. [Checked and inconclusive](#9-checked-and-inconclusive)

## 1. The discovery frame

Requirements gathering for a data platform has a known checklist, and two items on it are
the ones that usually decide the architecture while being routinely omitted from
architecture documents: **available skills and existing licences.** The full frame is
business needs, compliance, data quality, security, integration, latency, archiving and
lineage, delivery interfaces, available skills, existing licences.

A recommendation that names a platform without naming who will operate it and what the
organization has already paid for is not a recommendation. **When a platform is already
fully paid for, optimize for the existing spend and design the exit rather than paying for
the exit now.** An event such as a governance catalog being open-sourced converts "we must
migrate to stay portable" into "we can migrate later if we want to", which is a different
and much cheaper decision.

**Prefer the well-tested path over the strategically better new one for a first production
build.** A newly announced managed connector may be the right long-term answer while a
mature orchestration tool is the right answer for the initial extraction layer. Adopt the
new path once it has been exercised, not because it was announced.

## 2. Platform archetypes and their triggers

Four archetypes, each with an explicit trigger set. The triggers matter more than the
descriptions, because the descriptions all sound reasonable.

**Stay with the hyperscaler's own bundle** when the workload is single-cloud, the team is
small, the operations budget is tight, and data gravity already sits in one provider's
storage. The reason is assembly cost: the bundles ship faster than assembling best-of-breed,
and assembly is paid for in headcount you do not have.

**Go Spark-centric lakehouse** when Spark and ML workloads dominate, multi-cloud is a hard
requirement, and governance must span structured and unstructured data uniformly under one
control plane. You are buying breadth of governed surface (both major table formats,
attribute-based access control, model serving, agent infrastructure) rather than SQL
ergonomics.

**Go SQL-centric warehouse** when SQL is the primary interface, workloads are analytical
rather than distributed-compute, and the team should not be operating Spark or Kubernetes.
You are buying governance simplicity and an in-SQL surface matching existing skills, at the
cost of governance breadth.

**Go best-of-breed open source** when engineering capacity exists, multi-cloud or hybrid is
non-negotiable, vendor neutrality has long-term value, or scale and latency requirements
fall outside what the bundles hit. Those four are the only conditions under which the
integration burden pays for itself.

**Note the framing choice underneath this.** Treating "which cloud" and "which platform" as
independent decisions is a real architectural stance, not a formatting convenience: the
major lakehouse and warehouse platforms run on all three hyperscalers, so they are the
cross-cloud answer rather than a per-cloud one. State which of the two questions you are
actually answering, because teams routinely conflate them and then defend a cloud choice
with platform arguments.

## 3. Table format and catalog

**The open-table-format question has largely resolved; the catalog question has not. Design
so the catalog is replaceable, because that is the layer still in contention.**

**Format state, verified 2026-07-29.** The Iceberg v3 spec was ratified mid-2025, with the
1.10 and 1.11 release line through May 2026 delivering deletion vectors, VARIANT with
shredding, row lineage and geospatial types. Delta Lake 4.0 shipped September 2025 and 4.1.0
March 2026. Databricks has publicly proposed that Delta 5.0 adopt the same adaptive metadata
tree core structure being designed for Iceberg v4, which would mean one shared metadata
layout; community acceptance is still an open discussion, so **v3 is the production target
and v4 is the horizon**. UniForm generates Iceberg metadata asynchronously over an existing
Delta table without rewriting Parquet, so one data copy can serve Iceberg readers.

**The decision rule.** Iceberg for greenfield open-lakehouse interoperability; Delta when
the primary compute is the platform whose governance catalog you are standardizing on.
**Decide on interoperability risk rather than on a feature checklist**, because the feature
gap has been closing and the metadata layouts are converging. Apache Hudi remains a live
third option (Apache-2.0, ASF, 1.2.0 released 2026-06-07) whose roadmap is differentiating
toward AI and ML workloads rather than competing for Iceberg and Delta parity, with
commercial energy concentrated in one vendor. Pick it when high-frequency upserts with
record-level indexing and incremental-pull semantics are the dominant workload; its reversal
cost is high because the timeline, indexes and merge-on-read layout are Hudi-specific.

**What convergence does not give you.** Shared metadata gives read compatibility, not shared
execution. Liquid clustering, predictive optimization and materialized views remain
platform-specific, so **the format is portable and the optimizations built on it are not.**
That asymmetry is the real lock-in and it belongs in the decision record.

**Catalog state, verified 2026-07-29.** Apache Polaris graduated to an ASF top-level project
on 2026-02-18, donated by Dremio and Snowflake in August 2024. Apache Gravitino graduated
in June 2025 (1.1.0 December 2025) and is positioned as a catalog of catalogs, federating
across engines and AI assets. Unity Catalog OSS is Apache-2.0 and compatible with both the
Hive metastore API and the Iceberg REST catalog API, but its governance is an LF AI and Data
**sandbox** project rather than an ASF one, so it is single-vendor-led. Project Nessie is
Apache-2.0 and independently governed, extending the Iceberg REST spec with Git-like
branching, merging and immutable tags.

**The Iceberg REST catalog OpenAPI spec is now the interoperability interface**: engines
integrate with the spec rather than with a metastore implementation. That is what makes
"design the catalog to be replaceable" actionable rather than aspirational.

**Hive Metastore is not deprecated upstream.** There is no Apache-level deprecation; the
deprecation is vendor-specific, and on the major lakehouse platform the built-in metastore
still exists with governance through it deprecated in favour of the newer catalog, additive
rather than a hard cutover. It is still changing though: **from Hive Metastore 4.0.1 the
deprecated Thrift APIs were removed**, which is a real client-compatibility break. The
driver for moving off it is maintenance burden and scale limits rather than an end-of-life
date.

## 4. Open source treated as a vendor

Open source is a first-class option here, held to the same rigor as a commercial product:
licence, liveness, and the operational burden self-hosting transfers to you. **A licence
change is the highest-value fact about any of these components**, because it is the one
thing that invalidates an architecture decision retroactively, and it is the fact most
likely to be stale in anyone's memory.

All facts below verified 2026-07-29 unless dated otherwise.

| Component | First choice | Second | Licence facts that decide it |
|---|---|---|---|
| Table format | Apache Iceberg (Apache-2.0, ASF) | Delta Lake | both permissive; pick on interoperability, per §3 |
| Catalog | Apache Polaris (Apache-2.0, ASF TLP 2026-02-18) | Apache Gravitino (ASF TLP 2025-06) | Unity Catalog OSS is Apache-2.0 but LF sandbox, single-vendor-led |
| Ingestion / EL | dlt (Apache-2.0 core) | Debezium (Apache-2.0) for CDC | **Airbyte Core is Elastic License 2.0, not OSI-approved**, since 0.30.0 on 2021-09-27 |
| Transformation | dbt Core (Apache-2.0) | SQLMesh (Apache-2.0, Linux Foundation 2026-03-25) | Fusion engine relicensed ELv2 to Apache-2.0 on 2026-06-01; **the precompiled Fusion binary stays proprietary** |
| Orchestration | Airflow 3.x (Apache-2.0, ASF) | Dagster (Apache-2.0) | **Prefect acquired Dagster Labs in July 2026**; "licence unchanged" is a stated intent, single-sourced |
| Query engine | Trino (federated SQL) | DuckDB (MIT, single-node) | see register: Trino's licence was not verified from its own LICENSE file |
| Quality | Great Expectations Core | Soda Core | **Soda Core moved to Elastic License 2.0**; repo badges still say Apache-2.0, so check the LICENSE at your tag |
| Semantic / metrics | MetricFlow (Apache-2.0 since 0.209.0, Oct 2025) | see register | previously BSL, and AGPL before that |
| Entity resolution | see register | | **Zingg core is AGPL-3.0**; Senzing's engine is proprietary EULA with Apache-2.0 SDKs only |

**The four licence facts most likely to be wrong in someone's head:**

1. **Airbyte Core is source-available, not open source.** ELv2 forbids offering the software
   as a hosted service to third parties. If your pipeline ships inside a product you host for
   customers, Airbyte requires a commercial conversation, which is a procurement fact rather
   than a technical one. Scope widened over time from the platform to Airbyte-maintained
   connectors; community connectors keep their own licences.
2. **Soda Core is no longer Apache-2.0.** It moved to Elastic License 2.0 per Soda's own
   announcement, while repository badges still show the old licence. v4.0 also broke the v3
   checks language, so a version bump is a rewrite.
3. **Great Expectations split in two during 2026, and only half of it survived as a
   product.** Fivetran became steward of the GX Core open-source project on 2026-05-13 and it
   continues under Apache-2.0; GX Cloud was acquired by FICO and stopped being publicly
   available on 2026-06-01. The repository moved under the Fivetran organization. Selecting
   GX now means selecting the open-source core under a new steward, not the hosted product,
   and any plan written against GX Cloud before mid-2026 needs revisiting.
4. **A quality feature that lives inside a pipeline construct cannot be pointed at a table
   written by something else, and that constraint usually decides the choice before any
   feature comparison does.** Databricks expectations exist only within a declarative
   pipeline, so a table written by an external Spark job cannot use them at any price. The
   monitoring capability is the opposite: it attaches to a governed table with no framework
   adoption. **Ask where the write happens before comparing feature lists.** Related naming
   churn, worth knowing when reading anything written before mid-2025: Delta Live Tables is
   now Lakeflow Declarative Pipelines, and Lakehouse Monitoring is now documented as data
   profiling under the catalog's data-quality monitoring.
5. **Zingg is AGPL-3.0**, which is copyleft and will matter to legal review in a way that
   Apache-2.0 does not. Senzing is proprietary object code, record-metered, with only the SDKs
   permissive. Neither is a drop-in "we will just use the open-source one".
6. **dbt and SQLMesh arrived at Apache-2.0 from opposite directions.** dbt loosened its
   runtime licence while keeping a proprietary binary layer and a recommended commercial
   distribution; SQLMesh kept its licence and moved to neutral governance under the Linux
   Foundation. **If neutral governance is the requirement, that distinction decides it**, and
   nothing in a feature comparison will surface it.

**The operational burden each component transfers to you**, which is the part a licence
comparison hides:

- **Catalog is where self-hosting transfers the most availability risk**, because a catalog
  outage is a full-platform outage. You own its HA database, credential vending and scope,
  the RBAC model, client-compatibility across every engine, and audit retention.
- **Table format** hands you compaction and clustering jobs, snapshot and orphan-file expiry,
  manifest rewriting, and commit-conflict retry policy. Getting small-file growth wrong shows
  up as query latency rather than as an error, which is why it goes unnoticed.
- **Ingestion** hands you connector upgrade churn against upstream API changes, cursor and
  state durability, schema-drift handling and backfill orchestration. **Managed EL absorbs
  connector maintenance, which is the recurring cost; setup is not.**
- **Orchestration** hands you the scheduler, API server, DAG processor, triggerer and worker
  fleet, plus the metadata database whose table growth is the historical bottleneck.
- **Quality tools give you an assertion engine, not an alerting or incident surface.** You
  build result storage, trend history, routing and de-duplication, which is precisely what
  the paid clouds sell.
- **Debezium** specifically hands you replication-slot and write-ahead-log growth monitoring,
  where a stalled connector can fill the source disk, plus snapshot orchestration for large
  tables and version skew between Debezium, the connector runtime and the JDK baseline.

**A note on how to read a vendor's own comparison.** Where the only available comparison of
two tools is authored by one of them, its mechanics are usually reliable and its conclusions
are interested. Extract the mechanism, discard the verdict.

**Dated hazards found in this sweep.** Spark 3.5.x is on extended security-only support
ending November 2027, which is the migration deadline for anyone still on 3.x. Debezium's
embedded engine changed its default implementation class from 3.2.0.Alpha1, and the previous
one is no longer available, which is a breaking change for embedded users. Kestra's
open-source edition runs single-server by default with horizontal scale and multi-tenancy in
the paid tier, so **the practical constraint there is the architecture rather than the
licence text**, and discovering it after adoption is the expensive path.

## 5. Layering and the governance boundary

**Each layer has one responsibility, and blurring them produces duplication rather than an
error.** The reuse test decides placement: is this dataset reused across multiple use cases?
Yes means the conformed layer, no means the curated layer. The transform-layer detail is in
`transform-dbt.md`; what belongs here is the boundary decision.

**Keep architectural patterns out of governance structures.** The namespace level carrying
permissions and ownership should represent something that does not change: an environment, a
residency boundary, a business unit. The levels below it represent the architecture: layers,
stages, domains. **Encoding the medallion layer into the governance boundary means adding a
layer or changing a pattern becomes a permissions migration.**

The honest tension, which should be stated rather than resolved by assertion:
environment-plus-layer as the governance boundary buys clean physical storage isolation and
an obvious promotion path, and it is widely adopted. An estate can hold this principle and
violate it. If it does, **record the trade rather than pretending it was not made.**

**Architect the conformed layer per source system and the curated layer by business
function.** Producer-oriented naming preserves traceability to origin; consumer-oriented
naming matches how the business asks questions. The hybrid resolves a
lineage-versus-discoverability tension that a single organizing axis cannot.

**A data product is not a table.** It bundles code, data, metadata and its serving contract,
and it can expose several datasets. Calling a single table a data product is defensible only
when that table genuinely ships with its own tests, validation rules, documentation, quality
checks and stated ownership. That is a useful working definition precisely because it is
checkable: **no owner, no tests and no docs means it is a table.**

**Grain is a property of a dataset, not of a product**, so an intake form with one grain
field per product under-specifies any product exposing several datasets. Either make the form
one per dataset, or make grain a repeating sub-table with one row per dataset.

**A data contract is the formalisation of the intake form**, specifying schema, semantics,
quality expectations and change policy between producer and consumer. The dominant
enforcement pattern is automated tests in the producer's pipeline rather than a runtime gate.
Recognizing the intake form as a proto-contract means asking, per field, what would enforce
this later.

## 6. Isolation: which layer is actually the boundary

Applies wherever more than one tenant, region or business unit shares a platform. The
failure mode is a leak, so the design rule is that **every layer must fail closed
independently.**

**The isolation stack, outermost first:** infrastructure and workspace role assignments (who
deploys), then storage access control lists (**the hard read boundary**), then per-tenant
application identity and workspace, then row filters inside the report as a backstop. If
storage denies the identity, no downstream system can return the data regardless of what SQL
objects exist.

**Row-level security fails open, so it must never be the inter-tenant boundary.** A token
minted without a role means no filter, and workspace administrators and members bypass it
entirely when viewing directly. Use it for intra-tenant scoping only.

**Declare explicitly which layer is not a security boundary.** A SQL or semantic projection
layer that no end user authenticates against should be documented as a modelling layer only.
One sentence prevents most future confusion.

**Prefer physical per-tenant partitioning of the serving layer over a filter predicate over
an all-tenant table.** A predicate leaves every tenant's rows reachable, so one mis-set
parameter is a leak, and on scan-billed engines every refresh also scans the full set.
**Apply physical isolation only at the consumer-facing layer**: isolating raw ingestion by
tenant explodes file counts and pipeline complexity for a layer no consumer reads, and the
conformed layer needs cross-tenant visibility to model at all. Logical in the middle (a key
on every row), physical at the edge (separate paths plus access lists).

**Enforce the isolation key at the fact's own grain, on every fact.** Filtering only through
dimensions lets a fact row with an unresolved dimension key escape the predicate entirely.
**A row with no resolvable isolation key is a hard load failure, never a warning and never a
nullable key**: a warning becomes a leak the moment someone stops reading warnings, and a
null key passes through many row-filter predicates. If you quarantine instead, the sentinel
must resolve to a member no user can see and be excluded from the serving layer by default.

**Make tenant resolution a build-time gate rather than a convention.** A bounded
foreign-key-graph query over the explicit ingestion set, traversing only relationships where
both sides are in scope, returns per table a hop count, an ordered join path, and a status of
valid, ambiguous or no-path. The readiness rule: **zero no-path permitted, ambiguous requires
named business sign-off.** A table with no resolvable tenant path cannot enter the conformed
layer at all, because isolation cannot be enforced on it. Bound the traversal to the
ingestion set rather than the whole schema, because full-graph traversal is both slow and
useless (it finds paths through tables nobody ingests), and **diff its results after every
source schema change, because that diff is your tenant-impact change detector.**

Two more mechanical points: correctness tests for a resolved path are two-sided, since a
join that resolves but multiplies rows is as broken as one that fails; and **"descendant of a
tenant root" is not the same as "owned by that tenant"**, because a strict descendant filter
silently deletes genuinely global reference data such as calendars and shared type catalogs
from every tenant's view.

**Verify by minting a real token and rendering through the application.** A BI tool's
view-as-role feature evaluates in workspace context rather than embedded-token context, so a
bug that only manifests through a minted token passes the test.

**Do not place an identity boundary in a layer whose provisioning cannot be expressed
idempotently in your deployment pipeline.** That is the generalisable reason to reject
database users as the tenant boundary, and it applies to any per-tenant object CI cannot
converge.

## 7. The serving layer and the two semantic layers

**Route the serving layer by query predictability.** Predictable metrics and actions belong
in a stream processor; unpredictable exploration and dashboards belong in a real-time
analytical store. The generalization is push (incrementally maintained answers to known
queries, sub-second) versus pull (on-demand ad-hoc, seconds-fresh).

**Name the two semantic layers separately and state the trade.** There is a logical SQL
projection layer over the lake (external tables, views, materializations) and an analytical
layer in the BI tool (measures, row filters). The accepted consequence of that split:
business measures live in the BI tool and external tables enforce no constraints, **so
quality has to be handled in the transformation layer** because neither semantic layer will
do it.

**Import-mode BI decouples report-interaction latency and cost from the query engine's
concurrency limits**, which is what makes a serverless scan-billed layer viable underneath.
Revisit that when hundreds of analysts run ad-hoc SQL, when dashboards need near-real-time,
or when measures must be shared across several tools.

**Two capacity facts that are design constraints rather than details.** Per-dataset refresh
caps foreclose intra-day refresh without redesign, and finite refresh history means audit and
trend data must be pulled and warehoused externally or it is gone. **Per-principal API rate
limits are a real ceiling that arrives as tenant count grows, and sharding across identities
is a redesign**, so plan for it before it is an incident.

**On the semantic interchange effort**, verified 2026-07-29: Open Semantic Interchange was
announced 2025-09-23 by Snowflake with Salesforce, dbt Labs and others as a vendor-neutral
semantic model specification in standardized YAML. **It is not an Apache project**, whatever
a search result suggests; governance is a Snowflake-led consortium with ASF donation stated
as intent. The spec was published on GitHub 2026-01-27, and sources disagree on whether that
is v0.1 or v1.0, so treat the version as unsettled. A practitioner report found spec fields
not yet supported by the reference metrics engine, producing parsing errors: **the spec is
ahead of the tooling**, so treat it as a direction rather than a dependency.

## 8. Migrate versus stay, build versus buy

**Do not migrate platforms while another major delivery is in flight.** Run the current
platform for six to twelve months and let the pain points surface first.

**Classify the pain before migrating, because a platform migration only fixes one class.**
If the pain is "we are fighting the platform's constraints", migrate. If it is "the model is
wrong" or "the service levels need work", a new platform will not fix it and will delay
fixing it.

**Before migrating, inventory the parts of the architecture that exist only because of the
current platform's limits.** Bespoke workarounds for missing data-manipulation support,
missing overwrite semantics, absent transactional guarantees or an unsupported transformation
framework are all deletable on migration, **and a lift-and-shift carries every one of them
forward.** That inventory is simultaneously the strongest argument for migrating and the
reason a rebuild can beat a lift-and-shift on total effort.

**Weigh maintenance burden and hiring pool as first-class criteria.** "Less bespoke code" and
"a more standardized skill set to hire against" are frequently the real case for a move,
while raw capability is not.

**State the honest case against**: a working platform, sunk cost in platform-specific
patterns, migration risk overlapping other delivery, and a cost model that requires new
financial-operations conversations. A recommendation omitting these is not a recommendation.

**A platform migration changes the shape of the cost model, and that is a finance
conversation before it is a technical one.** Per-terabyte-scanned and per-compute-hour reward
opposite workload shapes: dense scheduled batch usually favors metered compute, sparse
unpredictable ad-hoc usually favors per-scan. **Forecast the new shape rather than the new
rate.**

**Build versus buy, where the corpus has explicit verdicts.** Buy profiling, because
interactive exploration of relationships through a purpose-built interface is far more
productive than hand-coding content questions, and the productivity gap lands exactly during
the phase where the schedule is most at risk. Buy fuzzy matching, survivorship and
standardization where the matching problem is genuinely fuzzy, because that tool category is
mature. **Build the quality-screen and error-event apparatus**, because the screens encode
your business rules and the schema encodes your grain. The pattern: **buy the analysis tools,
build the control plane.**

**Treat an announced-but-unclosed vendor merger as a signal about where a consolidated
metadata layer will emerge, and architect for continued interoperability rather than for the
merged product.** This is a reusable stance rather than a one-off, and the current sweep
found three consolidations inside twelve months, so it is not a hypothetical.

## 9. Checked and inconclusive

Verification budget was consumed on the components where a 2025-26 licence or governance
change was most likely. These were not settled and must not be stated as fact without a
follow-up pass.

- **Trino's licence and governance** were not verified from its own LICENSE file or
  foundation page. Widely documented as Apache-2.0 under the Trino Software Foundation; not
  asserted here.
- **ClickHouse and StarRocks**: licence, current release and governance entirely unverified,
  including whether either has adopted a non-OSI licence and whether StarRocks sits under a
  foundation or a vendor.
- **Profiling tooling as a category**: ydata-profiling, whylogs and the catalog-embedded
  profilers were not verified for licence, version or maintenance status.
- **Observability licences**: DataHub's and OpenMetadata's licences and governance, and
  Elementary's OSS-versus-cloud split, were not verified. OpenLineage and Marquez were
  confirmed as LF AI and Data graduated projects, with OpenLineage emitting and specifying
  while Marquez stores and serves.
- **Cube and Malloy licences** unverified, including whether Cube Core remains Apache-2.0.
- **Splink and RecordLinkage** unverified. Only Zingg (AGPL-3.0) and Senzing (proprietary
  engine) were settled.
- **Unity Catalog OSS "not yet production-ready"** surfaced as an independent review claim
  with no primary corroboration. Explicitly unverified, and it is the kind of claim a vendor's
  competitor has an interest in.
- **Delta Lake 4.0 and 4.1 release dates** rest on one secondary technical source rather than
  the project's own release notes.
- **The Prefect acquisition of Dagster Labs (July 2026)** and its "licence and name unchanged"
  commitment are single-sourced from search-result content, with no vendor announcement
  fetched. This is the largest governance uncertainty in §4 and should be re-verified before
  it is relied on.
- **Airflow 2.x end-of-support** was not established. It is the most likely candidate for a
  retirement date inside twelve months in this set.
- **Great Expectations Core's licence file** was not opened, and the year of the 0.18
  retirement deadline was not confirmed. The 0.18 line is unsupported and the 1.x upgrade is a
  rewrite of the config and API surface rather than a version bump.
- **Airbyte's CDK and protocol licences**: the licence FAQ says the CDK remains open source
  without naming the licence.
- **No end-of-support date inside the next twelve months was confirmed for any component.**
  The Spark 3.5.x November 2027 date is outside the window but is the one hard migration
  deadline found.
