# Dataframes and engines

Choosing what the transformation is actually written in. pandas, Polars, PySpark and DuckDB
are four different answers to "where does this data live while I am changing it", and the
choice decides the memory model, the debugging loop and the bill.

**Up:** `architecture-decisions.md` picked the platform, which constrains but does not
determine this; a Databricks estate can still run a single-node Polars job, and frequently
should.
**Down:** `optimization.md` §3 owns lazy evaluation from the performance angle (time actions
not transformations, read the physical plan) and is cross-referenced here rather than
repeated. `sql-craft.md` owns the SQL these engines run.
**Sideways:** `platform-notes.md` §6 for DuckDB's embedded mechanics, extensions and
concurrency model.

Version-specific claims carry the date they were believed current. Nothing here was
benchmarked in this pass; the sizing figures are shapes, not measurements.

## Contents

1. [The selection matrix](#1-the-selection-matrix)
2. [Most "big data" is under 100GB](#2-most-big-data-is-under-100gb)
3. [Eager versus lazy, and what it does to a debugging session](#3-eager-versus-lazy-and-what-it-does-to-a-debugging-session)
4. [pandas: the three traps that survive a port](#4-pandas-the-three-traps-that-survive-a-port)
5. [Polars: the expression API is the migration](#5-polars-the-expression-api-is-the-migration)
6. [PySpark: the driver is where it dies](#6-pyspark-the-driver-is-where-it-dies)
7. [DuckDB: SQL as the dataframe API](#7-duckdb-sql-as-the-dataframe-api)
8. [Arrow: the interop layer, and where zero-copy stops](#8-arrow-the-interop-layer-and-where-zero-copy-stops)
9. [Migration order](#9-migration-order)
10. [Checked and inconclusive](#10-checked-and-inconclusive)

## 1. The selection matrix

**The discriminator is the memory model, not the API.** Everything else about these four
libraries follows from where the data sits while it is being changed.

| Engine | Memory model | Where the work runs | Comfortable range | How it tells you it was the wrong choice |
|---|---|---|---|---|
| pandas | every intermediate materialized in process memory, eagerly | one core, one machine | source data comfortably under a gigabyte | `MemoryError`, or the machine starts swapping and the job never finishes |
| Polars | columnar and multi-threaded, with a lazy mode that can spill some operators to disk | all cores of one machine | up to memory, and beyond it for the operators that stream | a streaming query that quietly falls back to in-memory and then dies |
| DuckDB | columnar and vectorized, spills to disk as a normal mode of operation | all cores of one process | up to and past memory on one large node | a workload that needed concurrent writers, not more speed |
| PySpark | partitioned across executor JVMs, driver holds only the plan and the results you ask for | a cluster | data that genuinely exceeds one node, or a platform whose governance runs through it | a five-minute job that spends four of those minutes starting |

**Sizing rule of thumb for pandas, which is the one people get wrong by an order of
magnitude:** budget five to ten times the on-disk CSV size in RAM. Type inference widens
narrow columns, string columns in the historical object representation cost per element
rather than per byte, and every intermediate in a chain is a full materialization. A 2GB
CSV routinely needs 15GB to process comfortably. Parquet is worse for prediction, not
better, because the on-disk size is compressed and the expansion factor depends entirely on
the encoding.

**Choose the smallest engine that fits and move up only when a measurement forces it,
because the cost of being wrong is asymmetric.** Too small an engine fails loudly, on your
machine, in seconds. Too large an engine never fails at all: it just costs a cluster
forever, and it lengthens every debugging iteration from seconds to minutes, which is the
part nobody prices.

**Two things the matrix does not decide.** If the platform's governance, lineage or
scheduling only reaches jobs running on its cluster runtime, the runtime is chosen for you
regardless of data size. And if the team has one language, the engine that keeps them in it
wins arguments that a benchmark would not.

## 2. Most "big data" is under 100GB

**The finding that changes the most decisions here is that the overwhelming majority of
analytical workloads are under 100GB, and at that size a single node running DuckDB or
Polars beats a cluster on wall clock and on cost at the same time.** That combination is
unusual enough to state plainly: most engineering trade-offs move one against the other,
and this one moves both in the same direction.

**Be honest about where the claim comes from.** The most-cited version of it is an essay by
a founder whose product is hosted DuckDB, so it is an argument with an interest rather than
a neutral measurement, and it should be presented that way to a client. What survives the
interest is the mechanism, which anyone can check on their own estate.

**The mechanism, in three parts.**

- **Dataset sizes are heavily skewed small.** An organization that describes itself as
  having tens of terabytes usually has tens of terabytes of *history*, of which any given
  job reads one day or one month.
- **A cluster buys parallelism and pays coordination.** Job submission, executor startup,
  the scheduler round trip, shuffle over the network and idle capacity between runs are all
  fixed or near-fixed costs. Below a crossover they dominate, and the cluster is slower than
  one machine that simply reads the file.
- **The hardware moved and the habits did not.** A single cloud VM now offers hundreds of
  gigabytes of RAM and NVMe read throughput that required a rack when the distributed
  patterns were designed. The architecture that was correct in 2014 is being copied in 2026
  onto machines two orders of magnitude larger.

**The test, and it costs one query: measure the bytes the job actually reads after
projection and predicate pushdown, not the size of the source system.** That number is what
the engine has to hold, and it is routinely one or two orders of magnitude below the number
in the requirements document.

**"But we might grow" is answered by portability, not by provisioning.** Keep the
transformation in SQL, or in an expression layer that has more than one backend, so that
outgrowing the node is a runtime swap rather than a rewrite. Provisioning a cluster today
against growth that may not arrive pays the coordination cost every day for an option you
can buy later.

## 3. Eager versus lazy, and what it does to a debugging session

**Eager execution runs each statement when it is written; lazy execution accumulates a plan
and runs it at a sink.** pandas is eager. PySpark's DataFrame API is lazy with a set of
eager-looking actions. Polars is both, split by function name: `read_*` is eager, `scan_*`
is lazy, and `collect()` is the sink. DuckDB is lazy within a statement and eager at the
statement boundary.

The performance consequences are in `optimization.md` §3, which is the file that owns "time
actions, not transformations". What belongs here is the effect on debugging, because that
is what the person writing the code lives with.

**Under eager execution, debugging is bisection.** Every line produced a value you can
print, the exception points at the line that caused it, and the fix loop is as fast as the
slowest line. The price is that every intermediate was materialized whether anything needed
it or not, which is exactly the memory profile in §1.

**Under lazy execution, the traceback lies about location.** The failure surfaces at the
sink, several dozen lines below the transformation that caused it, and the frame you want
may have been optimized away entirely. Three habits recover most of what eager execution
gave you for free.

- **Print the plan as a reflex**, not as a last resort. `explain` before `collect` is the
  lazy equivalent of printing a dataframe, and it is the only view of what will actually
  run.
- **Collect on a bounded sample to isolate**, while remembering that this changes the work:
  a limit pushes down and the optimizer produces a different plan, so the timing you observe
  under the debugger is not the timing in production. Use the sample to find the wrong
  answer, never to predict the runtime.
- **Name the intermediates.** A single hundred-operation chain gives the optimizer nothing
  extra and gives you nowhere to break.

**The compensating gain is real and it is schema resolution.** A lazy engine knows the
output schema of the whole plan before reading a byte, so a misspelled column or an
impossible cast fails in milliseconds rather than forty minutes into a run. pandas finds
the same bug at the row that trips it. When someone asks what laziness bought them, this is
the answer that holds up.

**Mixing the two models in one script is its own defect.** Half the pipeline then reports
errors at write time and half at run time, and the person reading it has to track which
half they are in. Pick the model per stage and write down which.

## 4. pandas: the three traps that survive a port

These are the pandas behaviors that produce a *different number* somewhere else, rather
than an error. They matter twice over: once when writing pandas, and once when porting away
from it, because a mechanical translation carries the assumption and drops the mechanism
that made it true.

**The index is a semantic object, not a row number.** Binary operations align on it, `join`
and `concat` align on it, and `groupby` puts the key into it. Code that adds two series
relies on alignment producing the pairing, and no other engine here has an index at all.
Ported into Polars, DuckDB or Spark, that pairing becomes positional or becomes an explicit
join, and the result changes without erroring. Duplicate index labels make the alignment
fan out, which turns an addition into a cartesian product on the repeated label. Defend by
calling `reset_index(drop=True)` at every boundary and making every combination an explicit
key join, at which point the port is mechanical.

**Silent dtype coercion, with an identifier-destroying special case.** An int64 column that
acquires one missing value becomes float64, and past 2^53 a float64 stops representing
consecutive integers exactly, so two distinct bigint identifiers can land on the same value
and merge into one row. A boolean column with a missing value becomes object. `read_csv`
infers per chunk, so a column can be typed from the first block and disagree with the
tenth. Nullable extension dtypes and Arrow-backed strings fix most of this and have not
historically been the default; the pandas 3.0 line makes Arrow-backed strings the default
(checked 2026-08, from release-note summaries rather than a fetched page). The defense does
not depend on any of that: declare dtypes on read, assert them immediately after, and keep
every identifier as a string from the moment it enters the process.

**Copy versus view, and the warning that is a heuristic rather than a determination.**
Chained indexing (`df[mask]['col'] = x`) assigns into a temporary that may or may not be a
view of the original, so the write may or may not land. `SettingWithCopyWarning` is a guess
about that situation: it misses real cases and fires on safe ones, so neither its presence
nor its absence settles anything. Copy-on-Write, opt-in in the 2.x line and the default
from 3.0 (checked 2026-08), removes the ambiguity by making every such assignment behave as
a copy, which is correct and which breaks the code that was quietly relying on mutating a
view. Single-step `.loc` assignment is the fix that is right under every version. Related:
`inplace=True` rarely avoids the copy it appears to avoid and is not a memory lever.

**One performance note, because it is the trap a port reproduces:** row-wise `apply` and
`iterrows` run the Python interpreter per row. The translation of that idiom into another
engine is covered in §5, and the general principle is in `optimization.md`.

## 5. Polars: the expression API is the migration

**The migration is not syntax, it is the expression model, and a translation that treats it
as syntax produces working code that is slower than what it replaced.** A Polars expression
(`pl.col("x") * 2`) is a value: it is built, named, reused and passed around, and it means
something only once it is handed to a context - `select`, `with_columns`, `filter`, or the
aggregation inside `group_by`. A pandas reader expects statements that mutate a frame and
finds this foreign for about a day, after which the reuse is the point.

**Nothing mutates.** Every operation returns a new frame, there is no `inplace`, and the
pandas habit of assigning into a slice has no translation. Combined with the absence of an
index, this removes both pandas traps from §4 outright rather than mitigating them.

**The escape hatch is the trap.** `map_elements` applies a Python callable per element,
which leaves the engine, re-enters the interpreter and serializes per row. It is the single
largest performance regression available during a port, and it is exactly what a mechanical
translation of `apply` produces. Anything expressible as an expression should be one;
`when/then/otherwise` covers the conditional logic that most `apply` calls actually
contain.

**null and NaN are different values, and pandas conflates them.** Polars tracks a null bit
separately from a float NaN. Aggregations skip nulls; NaN propagates through them. A port
that assumed "NaN means missing" gets different aggregate results with no error anywhere.
Check every `fill_nan` against `fill_null` when reading a translated file.

**Strict typing at the boundaries surfaces bugs early.** Joins on mismatched key dtypes
raise rather than coercing, and concatenation of misaligned schemas raises rather than
producing a union with holes. This is a gain, not friction: the same mismatch in pandas
produces object columns and a join that matches nothing.

**Pin the version and distrust old examples.** The API moved fast before the 1.0 release
(2024), and the 1.x line carries a stability commitment (checked 2026-08). Blog code older
than that frequently uses names that no longer exist, which reads as a bug in your
environment rather than as a stale example.

## 6. PySpark: the driver is where it dies

**The driver is a single JVM process on one machine, and the entire distributed apparatus
sits upstream of it. Any line that pulls the dataset into the driver undoes the
distribution.** That is the whole mechanism behind most PySpark out-of-memory failures, and
it is worth stating as one sentence because the fixes all follow from it.

**`collect()` and `toPandas()` bring every row into the driver's heap.** Both read like a
read. Both are a full materialization on one machine, on a dataset that was sized for a
cluster. A `.limit(n)` in front of either is the entire defense, and the pattern that
replaces them for real output is write-then-read: write the result to storage and let the
consumer read it.

**The other driver killers, in the order they show up.**

- **An automatic broadcast join whose "small" side is not small any more.** The decision is
  made against a configured size threshold using an estimate, and a stale or missing
  statistic makes the estimate wrong. The broadcast table is assembled on the driver.
- **Accumulating into a Python list inside a loop**, which is `collect` spelled slowly.
- **A very large number of tasks**, whose per-task metadata accumulates in the driver. This
  is how a job with tiny data and pathological partitioning kills a driver.
- **`count()` or `show()` inside a loop**, each of which re-executes the whole upstream
  plan, because there is nothing cached between iterations.

**The symptom shape is recognizable.** Either an out-of-memory or GC-overhead error naming
the driver, or a job that hangs *after* every task reports complete: the stage bar reaches
the end and nothing happens, which is result assembly on one machine.

**Python UDFs cross a serialization boundary per row and pull data out of the JVM's
columnar path.** The preference order is built-in expression first, then an Arrow-based
(pandas) UDF that moves a batch at a time, then a plain Python UDF only for the thing that
genuinely has no expression. This is usually a larger factor than any cluster setting.

**Spark Connect separates the client from the driver** (checked 2026-08), which changes
where a `collect` result lands and how a client is packaged. It does not change the fact
that the result lands on one machine, so every rule above survives it.

Shuffle, skew, partition counts and whole-stage codegen fallback are in `optimization.md`
§3 and §6.

## 7. DuckDB: SQL as the dataframe API

**DuckDB's dataframe integration is that it reads the objects already in your process by
name.** A pandas, Polars or Arrow object in scope can be referenced directly in a query,
and Arrow-backed data crosses without a copy (§8). The result comes back as Arrow, or as
whichever frame you asked for.

**The consequence for how code is written is the point.** The joins, aggregations and
window functions go into SQL, where the semantics are the same ones the warehouse will
apply, and the surrounding orchestration stays in Python. A team stops maintaining two
mental models of what a join does, and the transformation becomes portable to the warehouse
by construction. The practical split that works: a dataframe library for awkward reshaping
and column-wise work, DuckDB for anything with a join or a window, per `sql-craft.md`.

**It is also the fastest way to make a pile of Parquet queryable**, including in place on
object storage, with projection and predicate pushdown into the files rather than a full
read.

The embedded model, reading Parquet and Iceberg in place, the extension ecosystem and the
concurrency limits that decide where it stops being the right answer are all in
`platform-notes.md` §6.

## 8. Arrow: the interop layer, and where zero-copy stops

**Arrow is the in-memory columnar layout these engines agree on; Parquet is the on-disk
one.** Keeping the pair straight prevents most of the confusion: Parquet is compressed and
encoded for storage, Arrow is laid out for scanning, and converting between them is real
work even where it looks free.

**What it buys.** A table can move between DuckDB, Polars, pyarrow and Spark without a
serialization pass, because each reads the same buffers. The C data interface is what makes
that work across language runtimes inside one process, and it is why "which library" is a
cheaper decision than it used to be: engines that speak Arrow compose at near-zero cost.

**Where zero-copy stops, which is the part that gets assumed away.**

- **Conversion to pandas' historical numpy block layout copies**, and any column that has to
  become an object column copies and then costs memory per element.
- **Nulls in an integer column force a representation change** where the destination has no
  null bit, which is the numpy path again.
- **Nested, decimal and timestamp-with-time-zone types map unevenly** between
  implementations. This is where a silent value change lives, not in the flat numeric
  columns everybody tests with.
- **Anything crossing a process or network boundary is a serialization**, even in Arrow's
  own transport. Flight is optimized, not free.

**Transport and drivers.** Arrow Flight and ADBC move result sets out of a database without
the row-at-a-time conversion that ODBC and DBAPI drivers perform, and the win scales with
result size. The cost is driver maturity, which varies per database and is worth checking
against the specific one you are using (checked 2026-08).

**The durable point:** choose engines that speak Arrow and the interop cost stays near
zero; choose one that does not and every boundary pays a full conversion, which frequently
exceeds the compute you were trying to optimize.

## 9. Migration order

**Measure before moving anything**, per §2: the bytes actually read, not the size of the
source. Most migrations away from a cluster are justified by a number the team already has
and has never looked at.

**Try the single node first, because the experiment is cheap and the result is a number.**
Reading the existing job's input with DuckDB or Polars on one large VM takes an afternoon
and either settles the argument or ends it.

**Keep the transformation in SQL wherever it can be.** SQL ports across all four engines
with the dialect caveats in `sql-craft.md` §7; a dataframe API ports across none of them.
This is the single decision that makes the next migration cheap.

**Migrate the boundaries before the middle.** Fix the read (scan with pushdown rather than
a full materialization) and the write first. They are mechanical, they deliver most of the
gain, and they leave the logic untouched while you are still learning the new engine.

**Port the intent, never the lines.** A line-by-line translation of a pandas script
reproduces the index assumptions from §4 and the row-wise `apply` from §5, and lands you
with a port that is slower than the original and harder to defend.

**One engine per pipeline stage, written down.** Two engines inside one function means two
null semantics and two type systems in the same scope, which is where the value that
changes without erroring comes from.

## 10. Checked and inconclusive

- **Nothing here was benchmarked in this pass.** Every size, factor and range is a shape
  drawn from common practice, and any of them can be off by a factor for a specific
  workload. The 100GB figure in §2 is a rule of thumb from a vendor essay, not a
  measurement.
- **pandas 3.0 defaults** (Copy-on-Write, Arrow-backed strings) are stated from release-note
  summaries rather than a fetched page, checked 2026-08. Confirm against the version in the
  environment before relying on either.
- **Which Polars operators actually stream to disk is version-specific** and the streaming
  engine has been rewritten more than once. Nothing is claimed about a specific operator
  here; verify against the running version before promising a job will survive a dataset
  larger than memory.
- **Spark's automatic broadcast threshold and its default** are deliberately not restated,
  because the config name and the value have both moved. Read the running configuration.
- **Spark Connect's exact boundaries** (which APIs are unsupported, how a UDF is packaged)
  were not verified, checked 2026-08.
- **Arrow zero-copy behavior per pair of engines** was not tested. The type-mapping hazards
  in §8 are the general shape; the specific pair you are using needs one round-trip test on
  a frame containing nulls, decimals and a time zone.
