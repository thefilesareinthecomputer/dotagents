# Slowly changing dimensions and keys

| § | Topic |
|---|---|
| 1 | The three key types and what each is for |
| 2 | SCD types 0 through 7 |
| 3 | Type 2 housekeeping columns |
| 4 | Detecting the change |
| 5 | The surrogate key pipeline |
| 6 | Late arriving data |
| 7 | Choosing, and the costs you are choosing |

## 1. The three key types

**Surrogate key.** A meaningless sequential integer, assigned by the warehouse,
serving as the dimension's primary key and the fact table's foreign key. Every
dimension gets one. Reasons it cannot be the operational natural key: change
tracking produces several rows per natural key, several source systems produce
incompatible natural keys for the same entity, and the source controls its keys
under business rules you do not see.

Generate them from a sequence the ETL calls directly, or from the ETL tool. Not
from database triggers (they bottleneck), and never by concatenating the
operational key with a date stamp: it looks simple, carries the source's problems
into your key, and does not scale.

**Natural key.** The source system's identifier. Keep it in the dimension as an
attribute for lineage and lookups. It does not belong in the fact table once
surrogate keys are assigned.

**Durable key** (also called durable supernatural key). One permanent warehouse
identifier per real-world entity, constant across all of that entity's type 2 rows
and immune to source-side renumbering. Make it an independent sequential integer;
a format derived from the business process will eventually inherit that process's
changes. This is the key that behavior study groups and type 7 current-perspective
joins depend on.

**The date dimension is the standing exception.** A meaningful `YYYYMMDD` integer
key is preferred, because the dimension is stable, entirely predictable, built once
without a source, and the key helps fact table partitioning. It still needs a row
for unknown or to-be-determined dates.

**Fact table surrogate keys** are a separate, optional idea: a single-column key
assigned in load sequence. Worth it to identify a row without traversing
dimensions, to resume or unwind an interrupted load, and to turn risky updates into
inserts plus deletes.

## 2. SCD types 0 through 7

**Type 0, retain original.** The attribute never changes after first write. Right
for anything labeled "original" (original credit score, original signup date), for
durable identifiers, and for most date dimension attributes.

**Type 1, overwrite.** Replace the value in place. History is destroyed, which is
correct when the change is a correction or when nobody needs the prior value.
Consequences to handle: if the dimension also tracks type 2 changes, overwrite the
attribute on **every** row sharing that durable key, or the "current" value
disagrees with itself. Type 1 also invalidates any aggregate or cube built on the
changed attribute, so those must be dropped and rebuilt. Segregate updates from
inserts in the load; UPDATE-else-INSERT convenience functions are a performance
trap at volume.

**Type 2, add new row.** The workhorse. Copy the current row, assign a new
surrogate key, apply the changed values, expire the previous row. From that moment
new fact rows carry the new key and old fact rows keep pointing at the old context,
which is what makes historical reports reproduce. Requires the housekeeping columns
in §3 and an updated surrogate key map for the pipeline in §5. Type 2 does not
invalidate aggregates, provided the change is effective today rather than
backdated.

**Type 3, add new attribute.** Add a column holding the prior value while the main
column takes the new one, giving an alternate reality: users can group by either.
One prior value only, no dates, no full history. Used rarely, and it means a schema
change plus an aggregate rebuild.

**Type 4, add mini-dimension.** When a cluster of attributes changes fast enough
that type 2 would explode a large dimension (the rapidly changing monster
dimension), split those attributes into their own dimension with its own key, and
put **both** keys in the fact table. Also worth doing for frequently-queried
attribute clusters in multimillion-row dimensions even when they change slowly.

**Type 5, mini-dimension plus type 1 outrigger.** Type 4, plus a type 1 reference
from the base dimension to the mini-dimension's current row. Historical facts stay
accurate through the fact table's mini-dimension key, and the currently-assigned
values are reachable directly from the base dimension without traversing a fact
table. Present the pair as one table in the presentation layer. The ETL must
overwrite that reference on every base row whenever the current assignment changes.

**Type 6, type 1 attributes inside a type 2 dimension.** Each tracked attribute
appears twice on the row: the as-was type 2 value and a systematically overwritten
current value. Filter or group by either. The overwrite touches every row sharing
the durable key.

**Type 7, dual type 1 and type 2 perspectives.** Put both the surrogate key and the
durable key in the fact table. Join on the surrogate key for the historical view;
join on the durable key with the current row indicator constrained for the current
view. Deploy the two perspectives as separate views so the choice is explicit at
the BI layer rather than implicit in a join.

Types 5, 6 and 7 all answer "preserve history but also let me report on current
values". Type 6 is the least machinery when the attribute set is small; type 4 or 5
when the volatile attributes are a distinct cluster; type 7 when both perspectives
must be first-class and named.

## 3. Type 2 housekeeping columns

Minimum three:

- row effective date (or date/time stamp)
- row expiration date (or date/time stamp), defaulting to `9999-12-31` on the
  current row
- current row indicator

Full form adds two more:

- change date as a foreign key to a date dimension outrigger
- reason for change

Derive the effective stamps from the system or as-of date, **not** from a source
column such as `last_modified_date`. Back-end scripts routinely modify source rows
without touching their metadata columns, and a dimension timestamped from those
columns will disagree with reality in ways that are hard to trace later.

## 4. Detecting the change

Change data capture is upstream of all of this, and its quality bounds what SCD
processing can do. If the source tells you what changed, use that. If it does not,
compare a hash or CRC of the tracked attributes against the stored row and treat a
difference as a change.

Split the comparison by intent before acting: a type 2 attribute changed means
insert a new row and expire the old, a type 1 attribute changed means overwrite
across the durable key's rows, and a change in an untracked attribute means do
nothing. Ask the source system experts whether a given change is a genuine event or
a data correction, because the same column can be either and the answer selects
type 1 or type 2 for that instance.

## 5. The surrogate key pipeline

Every fact table load must replace the incoming natural keys with the correct
dimension surrogate keys before the row lands.

1. **Load the dimensions first.** They are the source of the keys, so a fact load
   that runs first is loading against stale keys.
2. For each natural key on the incoming fact row, look up the dimension row whose
   effective span contains the fact's event time (or the current row, for a
   current-only load). Pin the dimension lookups in memory where possible.
3. Every lookup must resolve to a real key or to the dimension's unknown member
   key. An unresolved lookup is a referential integrity failure: route it back to
   the responsible process, do not write a null.
4. Handle key collisions explicitly: halt, suspend the row, or apply a correction
   rule and write an error event row. Choosing none of these means duplicates.
5. Drop the natural keys. The fact row carries surrogate keys only.
6. Do not write anything to the target until every row has passed every step.

Referential integrity is the guarantee this pipeline exists to produce: for every
foreign key value in the fact table there is a row in the dimension. Without it a
business user can write a perfectly reasonable query that silently omits sales.

## 6. Late arriving data

**Late arriving facts.** The measurement is delayed, so the current dimension
context is the wrong context. Find the surrogate key whose effective span contains
the fact's event date. This is a different code path from the normal load and it is
the same path a history reload needs.

**Late arriving dimensions.** The fact arrives before its context, which is normal
in real-time delivery. Insert a placeholder dimension row carrying the unresolved
natural key with generic unknown values for everything else, so the fact can post.
When the real context arrives, type 1 overwrite the placeholder.

**Retroactive type 2 changes.** A change effective in the past requires inserting a
row in the middle of the entity's history, adjusting the neighbouring rows'
effective spans, and restating the fact rows whose event dates now fall in the new
row's span. This is the expensive case; it is also the one people forget to specify
until it happens.

## 7. Choosing, and the costs you are choosing

Ask the business, per attribute: **when this changes, should historical reports
change too?** Their answer selects the type. Do not offer them the type list.

| Decision | Type | What it costs |
|---|---|---|
| Never changes | 0 | Nothing |
| Always show current | 1 | History gone; aggregate rebuild; overwrite across all rows of the durable key |
| Preserve as it was | 2 | Row growth; three housekeeping columns; a surrogate key map; a real load procedure |
| Current plus one prior | 3 | Schema change; aggregate rebuild; only one prior value ever |
| High-churn attribute cluster | 4 | A second dimension and a second foreign key in every affected fact table |
| Both perspectives | 5, 6, 7 | Type 1 overwrites layered on type 2 processing; more ETL, and hybrids are harder to explain to users |

Two practical notes. Different attributes in the same dimension routinely get
different types, and the design worksheet records the type per attribute rather than
per table. And type 2 row churn that has become unmanageable is usually the signal
for type 4: move the volatile cluster to a mini-dimension and leave the slow
attributes where they are.
