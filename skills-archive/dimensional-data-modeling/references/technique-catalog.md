# Technique catalog

Kimball's official technique set, condensed to the mechanical rule and the
condition that calls for it. Grouped as the authors group them, so a technique's
neighbors are its alternatives.

| § | Group | Read when |
|---|---|---|
| 1 | Fundamentals | Every design, before anything else |
| 2 | Fact table basics | Choosing the fact table type and its columns |
| 3 | Dimension table basics | Building any dimension |
| 4 | Conformance and the bus | More than one business process is in scope |
| 5 | Hierarchies | A dimension has parent/child structure |
| 6 | Advanced fact table patterns | The simple three types do not fit |
| 7 | Advanced dimension patterns | A dimension is multivalued, huge, volatile, or strange |
| 8 | Special purpose schemas | Heterogeneous products, real time, data quality tracking |
| 9 | Techniques to avoid | Reviewing someone else's model |

Slowly changing dimension techniques are in `scd-and-keys.md`.

## 1. Fundamentals

**Gather business requirements and data realities together.** Requirements come
from sessions with business representatives (their KPIs, decisions, analytic
needs); realities come from source system experts and high-level data profiling.
Doing only the first produces models the data cannot fill; doing only the second
produces a mirror of the source.

**Model collaboratively.** The modeler runs the sessions and owns the deliverables, but
the model unfolds in interactive workshops with business subject matter experts and
data stewards. A model designed in isolation by people who do not know the business
fails on contact with it. If an outside expert is engaged, insist they facilitate
rather than disappear and return with a finished design.

**The four-step process:** select the business process, declare the grain,
identify the dimensions, identify the facts. In that order. Only then name tables
and columns, collect sample domain values, and write the business rules.

**Business processes** are operational activities that generate or capture metrics.
Each becomes one row of the bus matrix and usually at least one atomic fact table.
Choosing one defines the design target, which is what makes grain declarable.

**Grain** establishes exactly what a single fact table row represents, and it is a
binding contract. Declare it before dimensions or facts, because every candidate
must be tested against it. Prefer the atomic grain, the lowest level the process
captures: it withstands unpredictable queries, whereas a rolled-up grain
presupposes the questions. Each distinct grain is a separate physical table.

**Dimensions** supply the who, what, where, when, why and how. They hold the
attributes used for filtering and grouping, and they are the entry points business
users actually experience, which is why a disproportionate share of governance
effort belongs to them. A dimension should be single-valued at the grain wherever
possible.

**Facts** are the numeric results of the event, one fact row per measurement event
at the atomic grain. A fact table corresponds to a physical observable event, never
to the demands of a particular report. Only measures consistent with the grain are
admissible: quantity sold belongs on a retail sales row, the store manager's salary
does not.

**Star schemas and OLAP cubes** are the two deployment forms. A cube is usually
derived from the relational star, is accessed through MDX or XMLA rather than SQL,
and often carries the aggregate layer. Model dimensionally first; the cube is a
deployment decision.

**Dimensional models extend gracefully.** Four changes are safe against existing
queries and existing results: adding a measure consistent with the grain, adding a
dimension foreign key that does not alter the grain, adding an attribute to a
dimension, and making the grain more atomic by restating the fact table while
preserving existing column names. This resilience is the payoff for the
constraints above.

## 2. Fact table basics

| Technique | Rule |
|---|---|
| Fact table structure | Foreign keys for every associated dimension, numeric measures, optional degenerate dimension keys and date/time stamps. The design follows the physical activity rather than the report. |
| Additive, semi-additive, non-additive | Fully additive measures sum across every dimension. Semi-additive (balances) sum across everything except time. Non-additive (ratios, percentages) must be stored as additive components and combined after aggregation. |
| Nulls in fact tables | Fine in measures; the aggregate functions handle them correctly. Never in a foreign key: use the dimension's unknown member row. |
| Conformed facts | The same measurement in two fact tables must be identically defined if it is identically named. If the definitions differ, name them differently so the difference is visible. |
| Transaction fact table | One row per measurement event at a point in space and time. The most dimensional and expressive form; sparse by nature. |
| Periodic snapshot | One row per entity per standard period. Dense in its foreign keys: a row exists even for a period with no activity, carrying zero or null. |
| Accumulating snapshot | One row per pipeline instance, with a date foreign key per milestone, revisited and updated as the process advances. Unique among the three in being updated. Carries lag measures and milestone counters. |
| Factless fact table | An event with no numeric result (a student attends a class) or a coverage table of everything that could happen. Subtract activity from coverage to answer what did not happen. |
| Aggregate fact tables | Numeric rollups built only for speed, joined to shrunken conformed dimensions. They must be navigated transparently, like indexes, so every query tool benefits without knowing they exist. |
| Consolidated fact tables | Facts from two processes at the same grain combined into one table (actuals with forecast). Shifts work from every query onto the ETL; justified when the cross-process comparison is constant. |

## 3. Dimension table basics

| Technique | Rule |
|---|---|
| Dimension table structure | One primary key column, embedded as the foreign key wherever that row's context is exactly right. Wide, flat, denormalized, many low-cardinality text attributes, verbose descriptions over codes. |
| Surrogate keys | Anonymous sequential integers owned by the warehouse in place of the operational natural key. Required because tracking change over time means multiple rows per natural key, and because natural keys from several sources may be incompatible. |
| Natural, durable, supernatural keys | The natural key belongs to the source and can change (an employee resigns and is rehired). The durable key is the warehouse's permanent identifier for the entity across all its type 2 rows; make it an independent integer, never a business-formatted string. |
| Drilling down | Adding a row header, which is just another attribute in the GROUP BY. It needs no predefined hierarchy or drill path. |
| Degenerate dimensions | An operational identifier with no descriptive attributes left (an invoice number on invoice line rows). It lives in the fact table with no dimension table behind it. Common in transaction and accumulating snapshot tables. |
| Denormalized flattened dimensions | Collapse many-to-one fixed depth hierarchies into positional attributes on one row. The denormalization here is deliberate. |
| Multiple hierarchies | Several natural hierarchies coexist in one dimension as separate attribute sets (day to week to fiscal period alongside day to month to year). |
| Flags and indicators as text | Expand cryptic abbreviations and true/false flags into words that stand alone in a report. Decompose smart codes so each embedded part becomes its own attribute. |
| Null attributes | Substitute "Unknown" or "Not Applicable". Databases group and constrain on nulls inconsistently. |
| Calendar date dimension | Attached to virtually every fact table; holds week numbers, month names, fiscal periods, holiday indicators, everything you would otherwise compute in SQL. May use a meaningful `YYYYMMDD` key to help partitioning, and still needs a row for unknown or to-be-determined dates. For finer precision add a plain date/time stamp column; for time-of-day grouping add a separate time-of-day dimension. |
| Role-playing dimensions | One physical dimension referenced several times (order date, ship date, due date). Each reference must go through its own view with uniquely named columns so the roles stay independent. |
| Junk dimensions | Collapse scattered low-cardinality flags and indicators into one transaction profile dimension. Populate only the combinations that actually occur rather than the Cartesian product. |
| Snowflaked dimensions | Normalizing a dimension's hierarchies into secondary tables. Avoid: it carries no more information than the flat form, and it costs comprehension and query performance. |
| Outrigger dimensions | A dimension referencing another dimension. Permissible, used sparingly. Usually the correlation belongs in the fact table as two foreign keys instead. |

## 4. Conformance and the bus

**Conformed dimensions** have identical column names and identical domain contents
wherever they appear. That identity is what allows separate queries against
separate fact tables to align on a shared row header. Define them once, with data
governance, and reuse them; the reuse is where the development savings come from.

**Shrunken dimensions** are conformed subsets: fewer rows, fewer columns, or a
higher level of a hierarchy. Required for aggregate fact tables, and for processes
that genuinely capture at a coarser level (a forecast by month and brand against
sales by date and product).

**Drilling across** is the only correct way to combine fact tables: query each
separately with identical conformed attributes as row headers, then sort-merge the
answer sets on those headers. BI tools call it stitching or multipass query.

**Value chain** is the natural sequence of an organization's processes (purchasing
to warehousing to retail sales). Each step produces its own metrics at its own
granularity, so each spawns at least one atomic fact table. Mapping the value chain
is how the bus matrix rows get discovered.

**Enterprise data warehouse bus architecture** decomposes the program into
process-sized increments that integrate because they share conformed dimensions.
It is platform independent and it is what makes incremental delivery add up to an
enterprise system instead of a pile of marts.

**Bus matrix**: processes as rows, conformed dimensions as columns, cells marking
association. Read rows to test that a candidate dimension is well-defined for that
process. Read columns to find where conformance is required. Then use it to
prioritize with business management, one row at a time.

**Detailed implementation bus matrix** expands each process row into its actual
fact tables or cubes, with the grain statement and fact list recorded per row.

**Opportunity/stakeholder matrix** swaps the dimension columns for business
functions (marketing, sales, finance) to show which groups care about which
process. Use it to decide who to invite to each design session.

## 5. Hierarchies

| Shape | Technique |
|---|---|
| Fixed depth, agreed level names | Positional attributes, one column per level. Easiest to understand, predictable performance. The default. |
| Slightly ragged (depth varies a little, as in geography) | Force-fit into fixed depth positional attributes for the maximum depth, populating by a business rule. Do not reach for the heavy machinery. |
| Profoundly ragged, indeterminate depth (organization trees) | A hierarchy bridge table with one row per path. Handles alternative hierarchies, shared ownership, and time-varying structures, all with plain SQL. |
| Ragged, and a bridge table is too much | A pathstring attribute encoding the full path from the top node. Cheap, but no alternative hierarchies, no shared ownership, and a structural change can force relabeling everything. |

## 6. Advanced fact table patterns

| Technique | Use when |
|---|---|
| Fact table surrogate key | Optional single-column key assigned in load order. Useful to identify a row without traversing dimensions, to resume or back out an interrupted load, and to decompose updates into inserts plus deletes. |
| Numeric values as attributes or facts | A number used mainly for calculation is a fact; a stable number used mainly for filtering and grouping is an attribute, usefully supplemented with band attributes. Occasionally both. |
| Lag/duration facts | Store one lag per milestone measured from the process start, so any milestone-to-milestone lag is one subtraction rather than a stored column per pair. |
| Header/line fact tables | Put all header-level foreign keys and degenerate dimensions on the line-level fact table. The line grain is the useful one. |
| Allocated facts | Header-level amounts (freight, discounts) allocated down to the line grain using business-supplied rules, so they slice by every dimension. Usually removes the need for a header fact table. |
| Profit and loss fact tables | The full revenue minus cost equation at the atomic revenue grain, enabling profitability by customer, product, promotion, channel. Requires allocating every cost component, which is a major ETL subsystem and a political project. Not an early increment. |
| Multiple currency facts | A column pair per financial measure: the transaction's true currency and a single standard currency converted by an approved rule, plus a currency dimension. |
| Multiple units of measure | Store facts once in a standard unit and store the conversion factors on the same row, then expose per-audience views. Keeping the factors on the row is what keeps the view arithmetic correct. |
| Timespan tracking in fact tables | Row effective date, row expiration date and current row indicator on a fact table, when a periodic snapshot would otherwise reload identical rows (slow-moving inventory balances). Unusual; know why you are doing it. |
| Late arriving facts | The current dimensional context is the wrong context for a delayed measurement. Search the dimension for the key that was effective at event time. |

Avoid: **centipede fact tables** (a foreign key for every level of a hierarchy, or
for every low-cardinality flag; collapse to the lowest grain, or build a junk
dimension), **stored year-to-date facts** (the request mutates into fiscal
period-to-date and close-of-period variants; calculate in the BI layer or cube),
and **joining fact tables on their foreign keys** (drill across instead).

## 7. Advanced dimension patterns

| Technique | Use when |
|---|---|
| Dimension-to-dimension joins | Demote the correlation to the fact table as two foreign keys when an outrigger's type 2 changes would otherwise force type 2 processing, and explosive growth, in the base dimension. |
| Multivalued dimensions and bridge tables | A dimension legitimately takes several values at the grain (a patient with simultaneous diagnoses). Attach it through a group key to a bridge table with one row per member of the group, optionally weighted. |
| Time-varying multivalued bridge | The bridge itself sits between two type 2 dimensions (accounts and customers). Add effective and expiration stamps and constrain the bridge to a moment in time, or the linkages are wrong. |
| Behavior tag time series | Store a sequence of data-mining behavior tags as positional attributes in the dimension, optionally with the full string, because they are queried in combination rather than computed. |
| Behavior study groups | Capture the output of an expensive iterative analysis as a table of durable keys, then use it as a filter against any schema with that dimension. Study groups intersect, union and difference. |
| Aggregated facts as dimension attributes | Put banded aggregate performance metrics (lifetime spend band) in the dimension for filtering and labeling. Cost lands on ETL, relief lands on the BI layer. |
| Dynamic value bands | Report rows defining varying-sized ranges of a fact, resolved at query time. A small banding dimension joined by greater-than/less-than beats a CASE statement, which forces a near-unconstrained scan. |
| Text comments dimension | Free-form comments belong in their own dimension (or as attributes of a per-transaction dimension), never as text in the fact table. |
| Multiple time zones | Dual foreign keys to role-playing date and time-of-day dimensions, one for universal standard time and one for local. |
| Step dimensions | Sequential process rows (web page events) get a step dimension saying which step this is and how many remain in the session. |
| Hot swappable dimensions | One fact table paired with alternative copies of the same dimension, each carrying a different party's proprietary attributes. |
| Audit dimensions | ETL metadata attached at fact row creation: data quality indicators, ETL code version, execution timestamps. This is what makes "which load produced this row" answerable, and it is often a compliance requirement. |
| Late arriving dimensions | Facts arrive before their context. Create a placeholder row carrying the unresolved natural key with generic unknown attributes, then type 1 overwrite it when the real context arrives. Retroactive type 2 changes instead insert a row and restate the affected facts. |

Avoid: **measure type dimensions** (collapsing a sparse fact row into one generic
measure identified by a type dimension multiplies row count and makes intra-row
arithmetic hard; acceptable only when potential measures number in the hundreds and
a handful apply per row) and **abstract generic dimensions** (one location
dimension for stores, warehouses and customers, or one person dimension for
employees and vendors: the attribute sets differ, the labels stop being
distinguishable, and the table gets larger).

## 8. Special purpose schemas

**Supertype and subtype schemas** for heterogeneous products: a supertype fact
table with the intersection of facts common to every product type, plus a separate
custom fact and dimension pair per subtype. Attempting one table with the union of
all facts and attributes fails, because financial products have hundreds of
mutually inapplicable columns. Also called core and custom tables.

**Real-time fact tables** need update frequency beyond a nightly batch. The
techniques are platform-specific: a hot partition pinned in memory with
aggregations and indexes deliberately withheld, or deferred updating that lets
running queries finish first.

**Error event schemas** are dimensional models of data quality itself, living only
in the ETL back room: an error event fact table at the grain of one screen failure,
plus a detail fact table at the grain of one column in one failing row. Pair with
audit dimensions on the delivered facts.
