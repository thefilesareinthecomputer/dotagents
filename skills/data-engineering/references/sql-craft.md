# SQL craft

The language itself: what an engine actually does with what you wrote, and the constructs
that return a wrong answer without raising anything.

**Scope note, because the seam is thin.** What a query *means* dimensionally - the grain it
is at, whether a measure is additive, which key conforms - belongs to the companion
modeling skill that `SKILL.md` routes grain and SCD questions to. This file owns how the
query is written: null semantics, join mechanics, window frames, deduplication, CTE
behavior and the dialect differences that change a result rather than its spelling.

**Up:** `transform-dbt.md` decides which model this query becomes and what materializes.
**Down:** `optimization.md` §7 owns query shape from the performance angle; everything here
is about correctness, and the two disagree often enough to be worth separating.
**Sideways:** `profiling-and-validation.md`, because several of the failure modes below
produce an empty result that reads as a pass.

## Contents

1. [Three-valued logic is the root of the silent wrongness](#1-three-valued-logic-is-the-root-of-the-silent-wrongness)
2. [The NOT IN trap, and how to write an anti-join](#2-the-not-in-trap-and-how-to-write-an-anti-join)
3. [Join multiplicity, mechanically](#3-join-multiplicity-mechanically)
4. [Window functions and the frame clause](#4-window-functions-and-the-frame-clause)
5. [QUALIFY and deduplication that stays readable](#5-qualify-and-deduplication-that-stays-readable)
6. [CTEs: materialized, inlined, recursive](#6-ctes-materialized-inlined-recursive)
7. [Dialect differences that change the meaning](#7-dialect-differences-that-change-the-meaning)
8. [The pre-merge checklist](#8-the-pre-merge-checklist)
9. [Checked and inconclusive](#9-checked-and-inconclusive)

## 1. Three-valued logic is the root of the silent wrongness

**NULL is unknown, not a value, and every comparison against it evaluates to UNKNOWN rather
than to false.** `WHERE` keeps only rows where the predicate is TRUE, so UNKNOWN and FALSE
are filtered identically and the difference between them is invisible in the output. That
single fact generates most of the rest of this section.

**The consequence people trip over first: two predicates that look like a partition of the
table are not one.** `WHERE status = 'active'` and `WHERE status <> 'active'` together miss
every row where `status` is NULL, so two reports built from the halves do not sum to the
whole and neither one is wrong on its own terms.

| A | B | A AND B | A OR B | NOT A |
|---|---|---|---|---|
| TRUE | NULL | NULL | TRUE | FALSE |
| FALSE | NULL | FALSE | NULL | TRUE |
| NULL | NULL | NULL | NULL | NULL |

The two cells worth memorizing are the ones where the unknown collapses: `FALSE AND NULL`
is FALSE, and `TRUE OR NULL` is TRUE. Everywhere else the unknown propagates, and
`NOT UNKNOWN` is still UNKNOWN, which is why negating a filter does not recover the rows it
excluded.

**Null-safe equality has a dedicated operator and change detection needs it.**
`IS DISTINCT FROM` and `IS NOT DISTINCT FROM` compare with NULL treated as a value, so
"this column went from NULL to 5" registers as a change. Plain `<>` reports nothing for that
transition, which is how a change-detection query silently stops emitting updates for
columns that start out empty. The spelling varies (`<=>` on some engines); the semantics do
not.

**NULLs are equal to each other in some clauses and not in others, and this is standard
behavior rather than a bug.** `GROUP BY`, `DISTINCT`, `UNION` and window `PARTITION BY`
treat all NULLs as one group. `WHERE`, `JOIN` and `HAVING` predicates do not. That is why a
deduplication written as `GROUP BY` and the same deduplication written as a self-join
disagree on rows with a null key, and why the join-based version quietly drops them.

**Aggregates skip NULLs and `COUNT(*)` does not.** `AVG(x)` divides by the count of
non-null values, so a column that is ninety percent empty returns the average of the
remaining tenth, presented with the same confidence as a complete one. `COUNT(x)` and
`COUNT(*)` differing is the cheapest completeness check available and belongs in the
profiling pass rather than in a debugging session. `SUM` over an empty set returns NULL
rather than zero, which then propagates through any arithmetic downstream and turns a total
into NULL rather than into a visible zero.

**Null placement in `ORDER BY` decides which row a deduplication keeps**, and the default
differs by engine (§7). Any ranking whose ordering column is nullable needs the placement
written out explicitly.

## 2. The NOT IN trap, and how to write an anti-join

**`x NOT IN (subquery)` returns zero rows the moment the subquery yields a single NULL.**
For any candidate `x`, the comparison against the null element is UNKNOWN, the conjunction
across the list can therefore never be TRUE, and the whole predicate fails for every row.
No error is raised.

**This is the most expensive shape of the general failure, because an empty result reads as
a pass.** The idiom's most common home is a reconciliation check - "which source keys are
missing from the target" - where zero rows is the answer everyone wants to see. One
nullable column in the target turns a broken check into a green one, permanently.

Note the asymmetry: `IN` is not affected in the same way. `x IN (1, 2, NULL)` still returns
TRUE when `x` is 1. Only the negation collapses.

**Three ways to write an anti-join, and what each commits you to.**

| Form | Null behavior | When to use it |
|---|---|---|
| `NOT EXISTS (SELECT 1 FROM r WHERE r.k = l.k)` | correct regardless of nulls on either side | the default; standardize on it |
| `LEFT JOIN r ON ... WHERE r.k IS NULL` | correct only if the column tested is non-nullable in `r` | when you also need columns from `r` in the same pass |
| `NOT IN (SELECT k FROM r)` | collapses to empty on one null | only with an explicit `WHERE k IS NOT NULL`, and even then someone will copy it without the guard |

**`NOT EXISTS` is a correctness choice, not a performance one.** Optimizers routinely
rewrite `IN`, `EXISTS` and the equivalent joins into the same physical plan, so the
argument for it is that it means what it says under every null configuration. Performance
belongs in `optimization.md` §7.

**The semi-join counterpart matters as much and is less discussed.** When the question is
"which left rows have at least one match", `EXISTS` and `IN` preserve the left cardinality
and an inner join does not: the inner join emits one row per match, so a left row with
three matches is counted three times. An inflated reconciliation count is almost always
this.

## 3. Join multiplicity, mechanically

**Before writing a join, state which side is unique on the join key.** If neither is, the
output carries the product of the matches per key. Whether that is the right result is a
modeling question and it is routed elsewhere; what belongs here is that the join changed
the row count, and that the change is invisible until someone sums a column.

**The fan-out hides in every column except the measures.** A `SELECT` of a few descriptive
attributes looks correct after a fan-out, because the duplicated rows are identical in the
columns being read. The first thing to reveal it is a `SUM`, at which point the number is
wrong by an integer multiple and looks plausible. Compare the row count before and after
the join, every time; it costs one query.

**A `LEFT JOIN` protects against loss, not against fan-out.** It guarantees every left row
appears at least once, and says nothing about how many times.

**Filtering the right side in `WHERE` silently converts a `LEFT JOIN` into an inner join.**
Any predicate on a right-side column is false for the null-extended non-matching rows, so
they are removed after the join produced them. The predicate belongs in the `ON` clause,
where it filters what is eligible to match instead. This is the single most common finding
in SQL review and it survives every level of seniority.

**`USING` versus `ON` is not only spelling.** `USING` merges the join columns into one
output column and changes what `SELECT *` returns, which matters where a downstream model
selects everything.

## 4. Window functions and the frame clause

A window function has three parts, and only the first is usually written deliberately:
`f() OVER (PARTITION BY ... ORDER BY ... frame)`.

**The default frame is the trap, and it is one word wide.** With an `ORDER BY` and no
explicit frame, the default is `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`, which
makes the aggregate a running total. Without an `ORDER BY` the frame is the whole
partition, which makes the same aggregate a partition total. So:

```sql
sum(amount) over (partition by customer_id)                     -- partition total
sum(amount) over (partition by customer_id order by order_date) -- running total
```

Two different numbers from the same function, distinguished by a clause that looks like it
only affects ordering.

**`RANGE` versus `ROWS` is the other half, and ties are what expose it.** `RANGE` frames by
*value*, so every row sharing the current row's `ORDER BY` value is in the frame together.
A running total over a date column with several rows per date therefore jumps by the whole
day at once, and every row within that day shows the same end-of-day figure. `ROWS` frames
by physical position and gives the row-by-row accumulation that people almost always mean.
**Whenever ties are possible in the ordering column, write `ROWS BETWEEN UNBOUNDED PRECEDING
AND CURRENT ROW` explicitly.** `GROUPS` exists as a third mode, framing by peer group, and
is supported unevenly.

**`LAST_VALUE` with the default frame returns the current row**, because the frame ends at
the current row. It is the second most common window surprise, and the fix is an explicit
frame ending at `UNBOUNDED FOLLOWING`.

**Evaluation order answers most of the remaining questions.** Logically:
`FROM` and joins, `WHERE`, `GROUP BY`, `HAVING`, window functions, `SELECT`, `QUALIFY`,
`DISTINCT`, `ORDER BY`, `LIMIT`. Window functions therefore cannot appear in `WHERE`,
`GROUP BY` or `HAVING` (they have not been computed yet), and filtering on one requires
`QUALIFY` or a wrapping subquery. The same order explains why a `SELECT` alias is
unavailable in `WHERE` on most engines.

**The ranking family differs in what it does with ties**, which is exactly what a
deduplication depends on: `ROW_NUMBER` is unique but arbitrary among tied rows, `RANK`
leaves gaps after a tie, `DENSE_RANK` does not, and `NTILE`, `PERCENT_RANK` and `CUME_DIST`
answer distribution questions rather than selection ones.

**Nondeterminism is the failure mode that outlives the query.** If the `ORDER BY` inside
the window is not a total order, `ROW_NUMBER` picks among the tied rows arbitrarily, and
the choice can differ between runs, between engines, and after a file compaction rewrote
the physical order. A deduplication built on it is not reproducible, and the resulting
"the numbers changed and nothing changed" incident is nearly undiagnosable. Always add a
tiebreaker that is unique.

**`LAG` and `LEAD` return NULL at the partition edge**, which then propagates through the
difference you were computing. The third argument is the default value and is usually what
was intended. `IGNORE NULLS` (the last-non-null carry-forward) is supported unevenly, and
where it is missing the portable substitute is a running count of non-null values used as a
grouping key.

## 5. QUALIFY and deduplication that stays readable

**The canonical "latest row per key" is one clause:**

```sql
select *
from events
qualify row_number() over (
  partition by entity_id
  order by updated_at desc, event_id desc
) = 1
```

**Why this is the right default.** It is a single pass, it keeps the whole row without
enumerating columns, and it neither self-joins nor correlates, so it cannot fan out. The
tiebreaker (`event_id desc`) is what makes it reproducible, per §4.

**The two alternatives people reach for are both worse, and one of them is dangerous.**

- **A self-join against `MAX(updated_at)` fans out on ties.** Two rows sharing the maximum
  timestamp both match, and the deduplication silently doubles the very keys it was written
  to fix.
- **A `GROUP BY key` with `MAX()` over each column composes a row that never existed.** Each
  column independently takes its maximum, so the output mixes values from different source
  rows into a single record that looks entirely plausible. This is the worst outcome
  available in this section, because nothing about the result signals that it is synthetic.

**Portability.** `QUALIFY` is available on Snowflake, Databricks SQL, DuckDB, BigQuery and
Teradata; PostgreSQL has no `QUALIFY` (checked 2026-08), and the portable form is the
same window function in a subquery with `WHERE rn = 1` outside it. Verify per engine before
relying on the clause in shared code. PostgreSQL and DuckDB also offer `DISTINCT ON`, which
is the same operation with a different spelling.

**Deduplicating before a merge is a separate requirement with the same tool.** Most engines
raise on a merge with multiple source rows per key rather than choosing one, so the
`QUALIFY` pass belongs in the source query. That interaction, and what it does to merge
cost, is in `optimization.md` §7.

## 6. CTEs: materialized, inlined, recursive

**The standard says nothing about whether a CTE is computed once or substituted into each
reference, so the engine decides and the decision is not stable across engines or
versions.** Three behaviors exist in production today: always inline, always materialize,
and choose by cost.

**Both choices have a cost, which is why neither default is safe to assume.**

- **Inlined**, a CTE referenced three times is *computed* three times, so an expensive scan
  runs three times and the query looks cheap in the text.
- **Materialized**, the CTE becomes an optimization fence: predicates from the outer query
  cannot be pushed into it, so a filter that would have pruned the scan does not, and the
  CTE reads everything.

**PostgreSQL is the named case where the behavior changed under people.** Before version 12
a CTE was always an optimization fence; from 12 onward a CTE that is referenced once, is
side-effect free and is not recursive is inlined unless `MATERIALIZED` or `NOT MATERIALIZED`
is written explicitly (checked 2026-08). Queries written against the old fence for
correctness-adjacent reasons, such as preventing a volatile function from being re-evaluated
per reference, changed meaning on upgrade without any code change.

**The durable rule: if a CTE is expensive and referenced more than once, do not leave the
decision to the engine.** Force it with the dialect's hint where one exists, or write it to
a temporary or intermediate table where one does not. Then read the plan to confirm which
happened, rather than inferring it from the runtime.

**Recursive CTEs have two runaway modes, not one.** A missing or wrong termination
condition is the obvious one. A cycle in the data is the other, and it turns a correct query
into an infinite one against a graph nobody promised was acyclic. Carry an explicit depth
column with a bound, and where the hierarchy can cycle, carry the visited path and exclude
it. Engines differ on whether any recursion limit is imposed by default.

**CTEs are a readability tool, not a performance tool.** A stack of twenty of them is still
one query to the optimizer, and it produces a plan nobody on the team can read. Splitting
that into materialized models is a modeling decision covered in `transform-dbt.md`.

## 7. Dialect differences that change the meaning

**The differences worth cataloging are the ones that return a different number. The ones
that raise an error find themselves.** A query ported between engines that runs clean and
reports different totals is the expensive case, and it comes from a short list.

| Behavior | How engines differ | What it breaks |
|---|---|---|
| Integer division | `1/2` truncates to 0 on some engines and returns 0.5 on others | a rate or ratio silently computes as zero |
| Empty string versus NULL | Oracle treats `''` as NULL; nearly everything else treats it as a value of length zero | every `IS NULL` check and every equality against `''` changes result |
| String concatenation with NULL | standard `||` yields NULL; some engines and functions skip nulls instead | a built key becomes NULL, or becomes a shorter key that collides |
| Case sensitivity of comparison | governed by collation, and the default differs by engine and sometimes by column | a join on a name or code column matches on one engine and not the other |
| Identifier case folding | unquoted identifiers fold up on some engines, down on others, and quoting freezes the case | "column not found" after a port, or two columns that differ only by case |
| Default null placement in `ORDER BY` | nulls sort first on some engines and last on others | a `ROW_NUMBER` deduplication keeps a different row |
| Division by zero | raises on some engines, returns NULL on others, and is mode-dependent on more than one | a pipeline that failed loudly starts emitting NULLs, or the reverse |
| Numeric overflow and implicit casts | wraps or truncates silently on some engines, raises on others | a total that is wrong rather than absent |
| Timestamp and time zone semantics | whether a literal is interpreted in the session zone, whether a date difference yields an interval or a number | a daily report shifts by a day at a boundary |

**Two of these are worth extra care because they are configuration rather than product.**
Collation is set per database, per column or per session on several engines, so two
deployments of the same product disagree. And ANSI or strict modes flip several behaviors
at once, including division by zero and overflow, so a single session setting changes
whether a class of bugs raises or returns NULL (checked 2026-08 as the general shape;
confirm the specific flags on the engine in use).

**The practical countermeasure is a conformance query, not a document.** Write one short
query per engine you support that exercises integer division, null ordering, division by
zero, empty-string handling, case folding and a time-zone round trip, run it on the real
engine, and keep the output beside the project. It takes an hour and it converts this table
from something to remember into something to look up. Adapter-level differences that change
how a *model* is written, as opposed to a query, are in `transform-dbt.md` §11.

## 8. The pre-merge checklist

Mechanical, and each item maps to a section above.

1. **Every join**: which side is unique on the key, and did the row count change as
   expected. (§3)
2. **Every `LEFT JOIN`**: is any right-side predicate in `WHERE` rather than `ON`. (§3)
3. **Every `NOT IN`**: replaced with `NOT EXISTS`, or guarded with an explicit
   `IS NOT NULL`. (§2)
4. **Every nullable column in a predicate**: is the null case intended, and does it need
   `IS DISTINCT FROM`. (§1)
5. **Every window aggregate**: is the frame written out, and is `ROWS` correct where ties
   exist. (§4)
6. **Every `ROW_NUMBER` deduplication**: is the ordering a total order, with a unique
   tiebreaker. (§4, §5)
7. **Every CTE referenced more than once**: is it expensive, and do you know which side of
   the materialization decision the engine took. (§6)
8. **Every aggregate over a nullable column**: does `COUNT(x)` equal `COUNT(*)`, and is the
   difference understood. (§1)
9. **Any query that must run on more than one engine**: has the conformance list been
   checked. (§7)
10. **Any check whose passing result is an empty set**: has it been made to fail once on
    purpose. (§2, and the corresponding law in `SKILL.md`)

## 9. Checked and inconclusive

- **The per-engine assignments in §7 are stated from practice rather than re-verified
  against each vendor's current documentation in this pass (checked 2026-08).** The
  mechanisms are stable and the assignment of a behavior to a named product is what to
  verify before it reaches a deliverable.
- **The `QUALIFY` support list in §5** is a moving target; engines have been adding it.
  Treat the list as "known to have it" rather than as exhaustive, and treat the PostgreSQL
  exclusion as needing a re-check.
- **The PostgreSQL CTE inlining rule in §6** is stated by version from memory of the
  release notes rather than a fetched page. The version boundary is load-bearing for anyone
  upgrading, so read the notes.
- **Which engines expose an explicit CTE materialization hint was not enumerated.** The
  advice in §6 is to check, not an assertion that a hint exists.
- **The default window frame** (`RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`) is
  standard, and engines are believed to follow it, but this was not verified per engine. It
  is the single fact in this file most worth confirming on the engine you use, because
  everything in §4 depends on it.
- **Recursion depth limits and cycle protection defaults** differ by engine and were not
  swept.
