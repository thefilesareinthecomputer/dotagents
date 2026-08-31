# Cost

What drives the bill, which knobs move it, and which guardrails actually prevent spend
rather than merely reporting it.

**Scope decision, made deliberately:** the subject here is **billing units, drivers and
guardrails**, not a forecasting method with worked list prices. Published prices rot faster
than any other content in data engineering, and a stale worked example is worse than none
because it is quoted with confidence. **No magnitudes appear here.** Directions and mechanisms are
transferable; another estate's percentages are not, and repeating them as if they were
benchmarks is how a forecast becomes indefensible.

**Up:** `architecture-decisions.md` fixed the cost model's *shape* when it picked the
platform. **Down:** `optimization.md` holds the physical levers, `source-to-bronze.md` holds
connector billing mechanics.

## Contents

1. [Establish the billing unit first](#1-establish-the-billing-unit-first)
2. [Measure composition before optimizing](#2-measure-composition-before-optimizing)
3. [Where the money usually is](#3-where-the-money-usually-is)
4. [Compute selection](#4-compute-selection)
5. [The bytes-scanned traps](#5-the-bytes-scanned-traps)
6. [Storage](#6-storage)
7. [The guardrail inventory](#7-the-guardrail-inventory)
8. [Attribution and chargeback](#8-attribution-and-chargeback)
9. [Writing a cost model someone will hold you to](#9-writing-a-cost-model-someone-will-hold-you-to)
10. [Checked and inconclusive](#10-checked-and-inconclusive)

## 1. Establish the billing unit first

**The billing unit decides which levers exist.** Every guardrail and every knob either moves
the unit you are billed in or it does not, and the intuitive lever frequently does not.
Before proposing any saving, name the unit.

| Tool class | Typical unit | The lever that does nothing |
|---|---|---|
| Lakehouse compute | compute-second or a normalized compute unit, per node size | reducing rows processed on an idle-but-running cluster |
| Warehouse compute | credit per warehouse-second, by size | shrinking result sets on a warehouse that stays up |
| Serverless SQL | **bytes scanned or processed** | shortening runtime |
| Capacity-based platform | a purchased capacity unit, smoothed over time | per-query tuning below the capacity ceiling |
| Managed connector | **distinct rows active per month**, or rows moved | lowering sync frequency |
| Object storage | GB-month plus **transaction count** | compressing when the problem is file count |
| Observability | GB ingested, by price tier | sampling when the tier is the driver |

**The connector case is the sharpest, and it is worked through in `source-to-bronze.md`.**
The short form: under per-row-per-month billing, excluding a table reduces the bill,
excluding a column typically does not, filtering helps only when pushed to the source, and
**lowering sync frequency does not reduce the bill at all** because the same rows are still
active that month. Pausing defers cost into the resume month rather than avoiding it, and
deselecting a table discards incremental state so re-enabling bills a full history.

**A platform migration changes the shape of the cost model, and that is a finance
conversation before it is a technical one.** Per-bytes-scanned and per-compute-hour reward
opposite workload shapes: dense scheduled batch usually favors metered compute, sparse
unpredictable ad-hoc usually favors per-scan. **Forecast the new shape, not the new rate.**

## 2. Measure composition before optimizing

**The dominant component decides whether your target is even the lever.** This applies
equally to a bill and to a runtime, and it is the single most reliable way to avoid expensive
wasted work.

**A deterministic fix routinely beats an expensive redesign**, and you only see that from
the breakdown. Correcting a table stuck on full reload, excluding a table nobody reads,
dropping an unused connector, or fixing a predicate that stopped pruning are all cheap, and
all invisible without composition data.

**Before quoting any cost range, take the two or three cheapest measurements**: per-unit
footprint, concurrent active load, actual movement duration. **A range spanning the whole
pricing ladder reads as "unsized" to whoever approves budget**, and correctly so.

## 3. Where the money usually is

Stated as a shape rather than a number, because the shape transfers and the number does not.

**The BI serving tier is frequently the dominant line, and it scales with concurrent users
and report complexity rather than with source count or data volume.** That is
counter-intuitive for a data platform, and it has a direct consequence: **spend the
forecasting effort on load-testing the serving tier with realistic concurrency.** It is
usually also the largest cost *uncertainty*, and it is resolvable only by measurement, not
by analysis.

**The second driver is extract-layer data movement, scaling with volume times frequency.**
Moving from full loads to incremental extraction is typically the highest-return outstanding
optimization on a young platform. **Prioritize the largest tables**, because table size
distribution is heavily skewed and a small minority of tables account for most movement cost.

**A curated table can exceed the size its consuming BI tool's licensing tier can import, and
that is a modelling constraint rather than a licensing footnote.** Discovering at delivery
that the detail-grain product cannot be loaded forces either a licence upgrade or a re-grained
aggregate. **Establish the consumption tool's size and refresh limits during intake, at the
same time as the grain.**

**On tier-gated managed services, the cost decision is made at tier selection**, because
capability presence is tier-bound. Geo-replication, duplicate detection, protocol
transactions and embedded stream processing each require a specific tier, and some (duplicate
detection notably) must be enabled at entity creation and **cannot be turned on later**. A
capability inventory has to precede the tier choice.

**Where a consolidated analytics platform has a practical production minimum capacity, that
floor is an economic commitment rather than a technical setting**, and it, not the feature
list, is the decision.

## 4. Compute selection

**Reserved-capacity objections to a serverless-first platform usually confuse how compute
scales with how software is purchased.** A volume-discount commitment is a draw-down pool
against consumption, not a hardware reservation, and it does not oblige you to provision
anything. **Scale-to-zero means idle costs nothing.** The narrow genuine exception is
latency-sensitive real-time model serving, where provisioned throughput exists to remove cold
starts.

**A cost-optimized and a latency-optimized serverless mode differ in resources allocated
rather than in unit price, so the saving is entirely workload-dependent.** A headline
"cheaper" claim is a benchmark on parallelizable batch work, and a small sequential job may
save nothing. **The operational constraint that usually decides it: the cost-optimized mode
is typically restricted to triggered execution**, so a continuously running pipeline cannot
use it at all.

**Choose the trigger mode deliberately, because a continuous default checks for new data
constantly and bills object-storage API calls for doing so.** Where the freshness requirement
is minutes rather than seconds, an incremental-batch trigger that processes everything
available and then exits is materially cheaper than a short fixed interval, and files
arriving between fires are simply picked up by the next one.

**Serverless bytes-scanned SQL frequently beats a provisioned warehouse for a batch
materialize-and-serve workload.** The heuristic: **provisioned massively-parallel compute
only wins when sustained processing volume is far above your current level.** Related, and
easy to miss: where the transformation is expressible as SQL over columnar files, a
bytes-scanned engine also beats a managed Spark runtime billed by cluster time, because the
managed data-flow feature is a Spark cluster underneath with a per-core-hour bill, a minimum
size and a billable cold start. **Pay for the Spark-shaped feature only where SQL genuinely
cannot express the work.**

**Running a data-movement runtime on your own infrastructure cuts the unit rate substantially
at the cost of host infrastructure**, which for high availability means more than one node.
That host cost is easy to forget entirely when comparing unit rates, and forgetting it is how
a self-hosting proposal gets approved and then disappoints.

**A materialized view that recomputes fully every run is usually a compute-choice problem
before it is a query problem.** Incremental refresh commonly requires a specific compute tier
*and* requires upstream sources to have row tracking and a change feed enabled. Without those
prerequisites the engine has no choice but full recomputation, **and the bill climbs
quietly** because nothing has failed.

**Object-storage-native brokers trade write latency for a large TCO reduction**, because
cross-availability-zone replication stops being your traffic and becomes the object store's
problem. Good for log aggregation, observability ingest and lower-criticality change streams;
wrong for latency-critical paths.

## 5. The bytes-scanned traps

**"Data processed" includes uncompressed intermediate results shuffled between compute nodes,
not just bytes read.** This is the non-obvious serverless billing trap: a `SELECT *` over
well-compressed columnar files can generate several times the compressed read volume in
intermediate transfer. Four rules follow directly:

1. **Always project explicit columns.** Never `SELECT *` in anything scheduled.
2. **Partition by date and use path predicates**, so whole folders are skipped rather than
   opened.
3. **Target file sizes in the hundreds of megabytes.** Small files inflate both scan overhead
   and storage transaction counts.
4. **Set a hard data-processed limit as a circuit breaker.** This is the single guardrail
   that converts a runaway query from an invoice into an error.

**Review scanned-bytes trends monthly specifically to catch query regressions.** A sudden
scan increase usually means a predicate stopped pruning or a small-files problem appeared,
and both are cheap to fix early and expensive to discover from a bill.

## 6. Storage

**Monitor storage transaction cost as the early warning that query cost is about to creep.**
Unexpectedly high transaction counts usually mean a small-files problem rather than a volume
problem, and transactions are charged in fixed-size blocks on some storage tiers, so many
small files inflate the count disproportionately.

**Geo-redundancy doubles the storage line, and the correct question is per layer rather than
global.** Where the system of record lives elsewhere and the lake layers are derived and
reproducible, locally-redundant storage is defensible for raw and conformed. Only a
sole-serving curated layer might warrant geo-redundancy.

**Lifecycle tiering is free to configure, but minimum-residency penalties make aggressive
tiering of frequently-rebuilt data counterproductive.** Raw only needs to be readable while
downstream layers are being built, so age-based demotion is safe there and not in a layer
that gets rewritten.

**Same-region service-to-service transfer is free, and that should govern resource placement
before any other networking consideration.** Ingress is free too: the cost is the gateway
infrastructure, not the bytes.

**Archival is a cost-benefit decision with a readability horizon.** Retaining data costs
storage and slows loads and queries; discarding it fails audit. The non-obvious part is the
long tail: a multi-decade retention requirement implies a plan for reading the media and
interpreting the format later, which in practice means periodic refresh and migration rather
than write-once. **When retiring a source system, sunset its data into a vanilla
application-independent format before the licence lapses.**

**Observability logging has price tiers, and most pipeline telemetry belongs in the cheap
one.** Reserve the expensive tier for signals you actually alert on in real time. Verbose
diagnostics enabled everywhere "just in case" is a real and avoidable line item.

## 7. The guardrail inventory

**The distinction that matters: which of these prevent spend, and which only report it.** A
budget alert has never stopped a single query.

| Guardrail | Prevents or reports | Notes |
|---|---|---|
| Auto-termination / auto-suspend | **prevents** | the highest-value single setting; an idle cluster bills |
| Compute / cluster policy | **prevents** | caps node size, node count, instance type before a cluster exists |
| Data-processed or bytes-scanned limit per query | **prevents** | the circuit breaker for runaway serverless queries |
| Warehouse size ceiling | **prevents** | caps the per-second rate |
| Query timeout | **prevents** | bounds the worst case |
| Statement / concurrency limits | **prevents** | bounds parallel spend |
| Resource monitor with a suspend action | **prevents** | only if the action is suspend rather than notify |
| Resource monitor with a notify action | reports | commonly mistaken for a control |
| Budget / cost alert | reports | arrives after the spend |
| Tags and cost attribution | reports | necessary for allocation, prevents nothing |
| Scheduled teardown of non-production | **prevents** | lower environments running overnight are pure waste |

**Cost hygiene that also signals engineering hygiene:** delete inactive pipelines, which
carry a standing charge; tag every resource with environment and component; set explicit
rather than automatic data-movement unit counts after benchmarking throughput; and audit for
connectors whose destination tables no model, report or query touches, which is a recurring
task with a calculable payoff.

**Environment multiplication is a guardrail question.** N environments running the same
connector means N initial syncs and N fixed charges. A "bill only in production" model
requires that lower environments' connections **do not run at all**, which in turn requires
cloning production data downward rather than syncing it. That clone must be deep rather than
shallow, or the lower environment reads production's files and breaks the moment a retention
boundary moves.

## 8. Attribution and chargeback

**Attribute cost per business entity by tagging at the point the resource is created, and
expect the mechanism to be immature.** Two cautions worth carrying: serverless usage
attribution generally depends on policies or tags applied to workloads, and **resources
triggered indirectly, such as a pipeline launched by a job, frequently inherit the wrong
attribution or none at all.** Verify attribution against a known workload before building a
chargeback model on it.

Unit economics are the only durable way to forecast across a platform change, because they
survive a change of rate card: cost per GB ingested, per model built, per dashboard refresh,
per active user. **Establish them on the current platform before migrating**, or the
comparison has no baseline and the migration's cost case cannot be settled afterwards.

## 9. Writing a cost model someone will hold you to

**A cost model is a live document with three explicit sections:**

1. **Known and estimable now.**
2. **Unknown until measured at production scale.**
3. **Decisions not yet made that affect cost.**

**Separating them is what prevents an estimate being read as a commitment.** A single number
with no uncertainty structure will be quoted back as a promise, and the second section is
where the serving tier belongs on most platforms.

**Never let a client-facing document assert a disputed number.** A documentation sentence one
research pass reproduced and a later pass could not is *disputed*, and a subsequent search
surfacing the same sentence does not resolve it, because re-surfacing the same unverified
artifact is not independent corroboration. **What settles a pricing question is a dated
written answer from the vendor against your specific contract.** Until then the deliverable
may describe the mechanism and must not state the price. Vendor TCO comparisons against named
alternatives are marketing until independently modelled.

## 10. Checked and inconclusive

- **No list prices, pricing units per named product, or worked examples** appear here by
  design. They were the fastest-rotting content in the source material and the scope decision
  was to exclude them.
- **No measured magnitudes are carried forward.** The source estate's ratios were real
  measurements of one estate and do not generalize; only directions and mechanisms transfer.
  Where you need a number, measure your own, per §2.
- **Commitment and discount modelling, reserved-capacity mathematics** were not researched and
  no guidance is offered.
- **Capacity behavior under load** for consumption-capacity models (smoothing, bursting,
  throttling) and the concurrency and queuing model for warehouse platforms were not verified
  and are platform-specific.
- **Whether a given platform's resource monitor can suspend rather than only notify** is
  version-sensitive and must be checked per platform; the prevent-versus-report column in §7
  is the durable distinction, the per-product capability is not established here.
