---
name: dimensional-data-modeling
description: Designs, reviews, and hardens Kimball-style dimensional models - star schemas, conformed dimensions, bus matrix, slowly changing dimensions. Use when modeling analytical data for a warehouse, lakehouse, or BI semantic layer - declaring a fact table's grain, deciding whether something is a fact or a dimension attribute, picking an SCD type for an attribute that changes, or drafting the bus matrix that makes cross-process reporting reconcile. MUST be used whenever star-schema DDL, a dbt mart, or a model spec is reviewed or handed to an ETL team, because mixed grains, nullable foreign keys and a type 2 dimension keyed on its business key are cheap to catch there and expensive once history is loaded. Ships an offline checker (scripts/dim_check.py).
license: MIT
---

# dimensional-data-modeling

**The grain declaration is the binding contract.** It states exactly what one row
of a fact table represents, and every later decision inherits its mistakes:
a dimension is admissible only if it is single-valued at the grain, a measure is
admissible only if it is true at the grain. Declare it before choosing dimensions
or facts, in one sentence, at the atomic level the source captures. A model whose
grain was declared vaguely cannot be repaired by fixing the ETL or the BI layer;
it gets restated, which means reloading history.

Three more mistakes account for most of the rest, and all three are mechanical:
descriptive text sitting in a fact table, a nullable foreign key where the unknown
member row belonged, and a second `dim_customer` that means something slightly
different from the first.

## First: which situation is this?

**Cold start, designing a model.** Work the four steps in order (below), then run
the sessions in `references/workshop-runbook.md` and capture each decision in the
artifacts in `references/templates.md`. The grain gate is a real gate: do not
proceed to dimensions until the grain sentence is written and agreed.

**Inherited warehouse, judging what is there.** Do not redesign. Profile first,
then diff the existing model against the laws below and report findings by blast
radius: grain defects are restatements, conformance defects are enterprise-wide,
a snowflaked dimension is a view away from fixed. Run the checker over the DDL to
get the mechanical findings for free, then spend judgment on the rest. Their
naming conventions outrank the ones used below.

**A single technique question** ("do I need a bridge table here", "is a junk
dimension right for these flags"): go straight to
`references/technique-catalog.md`, which is the condensed catalog of Kimball's
official techniques, grouped by where they apply.

**Anything platform-specific** - where the model sits in bronze/silver/gold, how
type 2 is implemented on this engine, whether a wide gold table beats a star, what
happens when the source is a CDC feed - goes to `references/lakehouse-practice.md`.
The classical techniques are platform independent; their mechanics are not, and
three of the platforms break assumptions the classical texts relied on.

## The four steps, in order

1. **Select the business process.** An operational activity that generates or
   captures metrics: taking an order, paying a claim, snapshotting every account
   monthly. Not a department, not a report, not a source table. Each process is
   one row of the bus matrix and usually spawns at least one atomic fact table.
2. **Declare the grain.** "One row in `fact_x` represents ___." One sentence,
   atomic, stable, independent of any report. Different grains are different
   tables, always. When the source is a change feed rather than a batch extract,
   the grain declaration also commits you to an ordering column, and the obvious
   candidate is usually wrong: see `references/lakehouse-practice.md` §3.
3. **Identify the dimensions.** The who, what, where, when, why and how context.
   Each must be single-valued at the grain, or it needs a bridge table (or the
   grain is wrong).
4. **Identify the facts.** The numeric measurements the event produces, and only
   those true at the grain. A measure that needs a finer grain than declared means
   the grain is wrong or the measure belongs in a different fact table.

Reordering these produces models that look reasonable and fail under load.
Choosing dimensions can legitimately send you back to step 2; choosing measures
should not.

## The laws

**Fact tables hold foreign keys, numeric measures, and degenerate dimension keys.
Nothing else.** No names, labels, categories, or free-text comments; those go to a
dimension (a comments dimension if the cardinality matches the transactions).
Classify every measure as fully additive, semi-additive (balances: additive across
everything except time), or non-additive (ratios - store the additive numerator
and denominator and divide after aggregation, in the BI layer). Nulls are fine in
measures, where SUM/AVG/COUNT do the right thing. Nulls are never acceptable in a
foreign key: point at the dimension's unknown member row instead, or referential
integrity is already broken.

**Dimension tables are wide, flat, denormalized, and verbose.** One column serves
as the primary key. Resist normalizing hierarchies into snowflakes: a flattened
dimension carries identical information and business users can navigate it.
Expand cryptic codes and flags into full-text attributes that mean something in a
report legend, substitute "Unknown" or "Not Applicable" for nulls (databases
group and constrain on nulls inconsistently), and let multiple hierarchies coexist
as separate positional attributes in the same table.

**Surrogate keys are the dimension's primary key, not the operational key.** Plain
integers assigned in sequence, owned by the warehouse. Natural keys change outside
your control, and a type 2 dimension has several rows per natural key by design,
so it also needs a **durable** key that never changes across those rows. The date
dimension is the standing exception: a meaningful `YYYYMMDD` integer is fine and
helps partitioning. Full treatment in `references/scd-and-keys.md`.

**Nothing enforces your keys anymore.** Kimball assumed a database that enforces
primary and foreign keys. Databricks, Fabric and Snowflake standard tables all treat
PK, FK and UNIQUE as declarative metadata and enforce none of them, so grain and
referential integrity are now entirely the ETL's responsibility. Worse than inert:
`RELY`-style hints let the optimizer act on an unverified constraint, and both
Databricks and Snowflake publish warnings that this returns wrong results over data
that violates it. Declare the keys anyway (BI tools infer relationships from them),
enable `RELY` only where the load provably guarantees the constraint, and treat the
unknown member as load-bearing rather than tidy. Details per platform in
`references/lakehouse-practice.md`.

**Conformance is the integration mechanism, and it is an organizational problem
wearing a technical costume.** Dimensions conform when their column names and
domain contents are identical, which is what lets two fact tables be queried
separately and their results aligned on a shared row header. That alignment is
drill-across, and it is the only correct way to combine fact tables: **never join
two fact tables on their foreign keys.** The cardinality of such a join is
uncontrollable and the answer is silently wrong. Facts conform too: if the same
measurement appears in two fact tables under one name, the definitions must be
identical, otherwise name them differently and let the difference be visible.

**The bus matrix is the enterprise contract.** Rows are business processes,
columns are conformed dimensions, cells mark which describes which. Scan rows to
test whether a candidate dimension is well-defined for that process; scan columns
to find where a dimension must conform across processes. It doubles as the
implementation roadmap: build one row at a time. If something is not on the
matrix, it is not in the model.

## Choosing the fact table type

| Type | One row is | Density | Update behavior |
|---|---|---|---|
| Transaction | One measurement event at a point in space and time | Sparse; rows exist only when something happened | Insert only |
| Periodic snapshot | The state of the period (day, week, month) | Dense; a row per entity per period regardless of activity | Insert per period |
| Accumulating snapshot | One instance of a pipeline with predictable milestones | One row per pipeline instance | Revisited and **updated** as milestones complete |
| Factless | An event or coverage relationship with no measure | Varies | Insert only |

Pick the type that matches the analytic pattern and never mix two in one table.
Accumulating snapshots carry a date foreign key per milestone plus lag measures;
store each lag against the process start point, so any lag between two milestones
is one subtraction. Factless coverage tables answer "what did not happen" when
subtracted from the activity table.

## Routing an SCD decision

Ask the business one question per attribute: **"when this changes, should
historical reports change too?"** Do not ask which SCD type they want.

| Their answer | Type | Cost |
|---|---|---|
| Never changes; it is the original value | 0 | None |
| Always show the current value | 1 | Destroys history; invalidates affected aggregates |
| History must be preserved as it was | 2 | New row, new surrogate key, three housekeeping columns |
| Show both current and one prior | 3 | New column, rarely worth it |
| It changes constantly and bloats the dimension | 4 | Mini-dimension, its own key in the fact table |
| Preserve history but also filter by current | 5, 6, or 7 | Hybrid; see the reference before choosing |

Different attributes in one dimension routinely get different types. Type 2 is the
workhorse. The mechanics, housekeeping columns and hybrid variants are in
`references/scd-and-keys.md`.

## Gate the output

EXECUTE:

```bash
python3 scripts/dim_check.py <path>...       # exit 1 on any FAIL
python3 scripts/dim_check.py --json .
```

Stdlib, offline, never imports or executes what it reads. It takes star-schema
DDL (`.sql`) and model specs written on the `references/templates.md` shapes
(`.md`), and it FAILs the violations that need no judgment: text attributes in a
fact table, nullable foreign keys, float money, centipede date hierarchies,
a type 2 dimension keyed on its business key, fact-to-fact joins, a fact spec with
no grain statement, a measure with no additivity, a dimension spec with no SCD
type.

Known limits, stated so it is not over-trusted: the DDL reader is a regex over
`CREATE TABLE` bodies rather than a SQL parser, so it does not follow views, CTAS,
dbt Jinja, or `ALTER TABLE`; it classifies fact and dimension tables by naming prefix
first and a column heuristic second, so unconventional naming degrades it to
warnings; it cannot see whether an unknown member row exists, whether a grain
statement is *true*, or whether two same-named dimensions actually conform. It is
a tripwire for the mechanical half, not a review.

## The judgment pass

The checker cannot do any of this. Do it before signing off a model.

1. **Is the grain atomic, or did someone pre-aggregate to save space?** Summary
   grains presuppose the questions. Load the atomic grain and let aggregates be a
   performance decision made later and navigated transparently.
2. **Does every measure survive the grain?** Header-level charges on a line-level
   fact table need allocation rules from the business rather than a second grain.
3. **Do two dimensions with the same name mean the same thing?** If two
   stakeholders both say "customer" and mean different entities, the resolution is
   usually to name two dimensions rather than to keep contesting one.
4. **Where do the metric definitions live?** If a report can redefine a metric,
   the model is not the source of truth and reports will disagree forever.
5. **What happens when a dimension row changes retroactively?** Late-arriving
   facts and retroactive type 2 changes both require finding the key that was
   effective at event time rather than the current key.
6. **Can the source actually deliver the declared grain?** Profile it. If not,
   re-grain honestly or escalate to the source team; do not pretend.
7. **Was the key's uniqueness proven exactly, or only sampled?** A column unique in a
   sample is a candidate, not a key. Unique "most of the time" fans out the merge and
   writes duplicates into history, which no later correction repairs. Settle it with an
   exact distinct count over every row at the source.

## Where the rest lives

| File | Contents |
|---|---|
| `references/technique-catalog.md` | The condensed catalog of Kimball's official techniques: fundamentals, basic and advanced fact and dimension patterns, hierarchies, special-purpose schemas, and the ones to avoid |
| `references/scd-and-keys.md` | SCD types 0 through 7 with ETL mechanics, housekeeping columns, key types, the surrogate key pipeline, late-arriving data |
| `references/workshop-runbook.md` | Running the modeling engagement: preparation, Day 1, the six-session arc, objection handling, review cycle, recovery from common failures |
| `references/templates.md` | The artifacts: grain statement, bus matrix, fact spec, dimension spec, SCD policy, design worksheet, sign-off checklists |
| `references/delivery-and-physical.md` | How the model lands: the 34 ETL subsystems, the ten-step ETL plan, physical design, real-time |
| `references/lakehouse-practice.md` | Medallion practice on Databricks, Fabric, Snowflake and dbt: layer placement and the staging/intermediate/marts mapping, the enforcement collapse and the `RELY` trap, grain against a change feed, per-platform key and type 2 mechanics, star versus wide gold table decided by incrementalizability, layout as a concurrency decision, conformance cost across metastores, the semantic layer boundary, and a register of what could not be verified |

## Verify

```bash
python3 -m unittest discover skills/dimensional-data-modeling/tests
```

`tests/fixtures/bad/` contains every mechanical violation and must FAIL;
`tests/fixtures/good/` is a correct star schema and must be **silent**. The quiet
test is the one that matters: a checker that fires on correct models gets muted,
and a muted checker protects nothing.

## Sources

Distilled from Ralph Kimball and Margy Ross, *The Data Warehouse Toolkit*, third
edition (Wiley, 2013) - chapter 2 is the authors' own official technique catalog,
chapter 17 the lifecycle, chapter 18 the modeling process, chapters 19 and 20 the
ETL subsystems and their build sequence, chapter 21 big data - together with *The
Data Warehouse Lifecycle Toolkit*, second edition (Wiley, 2008), from which
chapters 18 through 20 are condensed. Scope: dimensional modeling. Data mesh, data
vault and One Big Table are different answers to a neighbouring question and are
not covered.
