# Workshop runbook

Running a dimensional modeling engagement, from before the first meeting to design
sign-off. Written so someone leading their first session can produce a defensible
model.

| § | Topic |
|---|---|
| 1 | Before the first session |
| 2 | Day 1 |
| 3 | The six-session arc |
| 4 | Session discipline |
| 5 | Handling the standard objections |
| 6 | When to escalate |
| 7 | The review cycle |
| 8 | Failure modes and recovery |

Expect three to four weeks for a single business process, faster where conformed
dimensions already exist (the effort collapses onto the fact table), slower where
requirements are thin, the source data is messy, or nobody present has authority to
settle a definition.

## 1. Before the first session

**Get the right people in the room.** The modeler runs the sessions and owns the
deliverables, but the model needs business subject matter experts (often the people
who have historically extracted this data by hand), data stewards for the domains in
scope, someone who knows the source systems' actual behavior, and ideally a DBA and
an ETL representative. The last two are there to learn why the design trades ETL
complexity for presentation-layer simplicity, rather than to argue for third normal
form or to defer complexity into the BI tool.

**Deal with governance at the start.** An enterprise model committed to
dimensional design is committed to conformed dimensions, and conformance is settled
by data stewardship rather than by modeling. If there is no stewardship function, this is
where one starts. The difficulty is almost never technical: it is getting different
parts of the business to accept common names, definitions and rules. If every group
keeps its own, there is no single version of the truth to deliver.

**Read the requirements before designing.** Skipping this produces a model driven
entirely by what the source happens to store. The modeler's job is to translate
requirements into something that supports a broad range of analysis rather than only
the specific reports that were asked for.

**Set up four things:**

- A spreadsheet for the model. It beats a modeling tool while the design is moving;
  convert once it firms up, then let the tool forward-engineer the physical objects.
- A data profiling capability, even if it is just SQL. You need the source's real
  content, relationships and derivation rules, which its documentation will not
  reliably give you.
- Naming conventions, adopted from whatever the organization already has or
  established here. Table and column names become the BI interface: "Description"
  is clear in a data model and meaningless in a report legend. A prime word,
  optional qualifiers, and a class word is the usual structure.
- Sessions on calendars: two to three hours, morning and afternoon, three or four
  days a week, rather than full days. Participants have other jobs, and the gaps are
  where profiling, definition-chasing and document updates actually happen.

**Bring to Day 1:** the in-scope deliverables, the business question behind each,
named stakeholders by role, an inventory of source system names, the target BI tool
and what its semantic layer can do, the agreed session cadence, and blank bus matrix
and grain statement templates ready to fill in live.

## 2. Day 1

Ninety minutes:

| Time | Block |
|---|---|
| 0:00 | Introductions, and what each person speaks for on this engagement |
| 0:05 | Orientation: what dimensional modeling is and what these sessions will produce |
| 0:15 | Confirm reporting scope: what is in, what is explicitly out |
| 0:25 | List candidate business processes (each a candidate fact table) |
| 0:50 | List candidate shared dimensions |
| 1:05 | Draft the bus matrix live on screen |
| 1:20 | Read decisions back; assign owners to open items |
| 1:25 | Confirm the next session and its homework |

**The orientation, in one paragraph:** we are defining the structure of the
analytical model that reports will rely on. We are not designing reports and we are
not designing pipelines. By the end we will have agreed which business events get
measured, what one row represents in each measurement, what attributes describe
those events, how changes over time are tracked, and how it all connects. If the
structure is clean, implementation becomes mechanical.

**Ask these, explicitly.** Per report or dashboard in scope: what business question
does it answer; who reads it and what do they decide from it; what event in the
business creates a row behind the metric; what does "complete" or "final" mean for
that event, so we know when it is safe to count; what time grain matters; what do
users slice and filter by; must its totals reconcile against any other report.

About the business as a whole: what are the reporting periods and their exact
boundaries (calendar and fiscal both); is the model serving one population or
several segregated ones, and if so what enforces the separation; are any metrics
defined differently in different parts of the business, and where do those
disagreements live; what changes about your customers, employees and products that
you care about historically, and what changes do you not care about.

About the engagement: what is the source of truth for each process; does a model or
warehouse already exist and is it to be replaced or extended; who has authority to
decide when stakeholders disagree.

**Leave with:** the in-scope process list, the candidate dimension list, a draft bus
matrix, a written scope statement (in, out, backlog), stakeholders confirmed by
role, and the date and focus of session 2. Without these, Day 1 is not finished;
book a follow-up rather than advancing.

**Keep these out of the first sessions:** source table mapping, ETL design, physical
storage, indexing and partitioning, BI implementation, report layout, and metric
implementation in DAX or SQL. Separating what from how is the main job early on.
When the room drifts into source tables or tool features, redirect.

## 3. The six-session arc

One purpose and one output each. Do not advance until the output is approved.

**Session 1, choose processes and draft the bus matrix.** Confirm reporting scope.
List candidate processes and, for each, what event occurs, when it is final, and
whether it is measurable. List candidate shared dimensions. Draft the matrix live.
Output: selected processes, draft matrix, scope statement.

**Session 2, declare the grain. This is a hard gate.** For each process write "one
row in `fact_x` represents ___", filled with one atomic sentence, stable over time,
independent of any report filter or tool state. Do not discuss measures. Output: an
approved grain statement per candidate fact table. If consensus cannot be reached,
do not proceed to session 3: the fact is not ready. Escalate, defer, or break the
process into smaller candidates until the grain becomes statable.

**Session 3, dimensions and conformance.** With the grain fixed, ask what entities
describe the event and what users filter and group by. Per dimension capture the
one-sentence business meaning, the natural key, the core attributes, the cardinality
against each fact, and any segregation behavior. A dimension used by two or more
facts must be one shared definition; no fact invents a local variant. Update the
matrix. Output: dimension inventory, conformed dimension list, updated matrix.

**Session 4, facts.** List the measures each report needs, document additivity for
each (fully additive, semi-additive, non-additive), flag derived measures with their
logic (implementation deferred), and confirm every measure is valid at the declared
grain. Foreign keys and numeric measures only; no descriptive attributes. A measure
that implicitly needs a finer grain means the grain is wrong or the measure belongs
elsewhere. Output: measure inventory with additivity, plus any grain conflicts
surfaced.

**Session 5, dimension change behavior.** Per attribute, in business language:
"when this changes, should historical reports change too?" Route the answer to an
SCD type (see `scd-and-keys.md`), and confirm the surrogate key requirement, the
effective-date and current-flag conventions, and the segregation approach. Output:
SCD policy per dimension, surrogate key policy confirmed.

**Session 6, finalize and validate against the reports.** Verify every fact has a
declared grain, required dimensions and valid joins; that conformed dimensions are
genuinely identical; that date roles are named explicitly (work date, posted date,
created date); and that cross-fact reconciliation expectations are stated. Then map
each in-scope report visual to a fact measure, a dimension attribute, and a declared
join path. A visual that cannot be mapped means the model is incomplete: add what is
missing or scope it out in writing. Output: the authoritative bus matrix, the
modeling contract approved, engineering cleared to build.

## 4. Session discipline

Every session: state the objective (5 min), recap prior decisions (5), work the
current step (45 to 60), read the decisions back to the room (10), assign open items
with owners and dates (5).

**Never end a session without the read-back.** A verbal yes with no written
read-back is not approval, and it evaporates before the next session.

Guardrails to hold, out loud when necessary: no modeling from source tables, no
mixed grains, no defining measures before grain, no non-conformed duplicate
dimensions, no fixing it in the BI tool. Scope is what session 1 agreed; anything
new is backlog.

Log every decision with what was decided, who decided it by name (not "the team"),
the date, the one-sentence rationale, and any objection on record. The log lives
beside the bus matrix.

## 5. Handling the standard objections

**"Just reverse-engineer our existing tables."** We start from business processes
because the source captures what the application stores, not what the business
measures. We will map back to sources, after grain and dimensions are agreed.
Otherwise the model inherits whatever shape the source happened to have, including
its mistakes.

**"Our BI reports already define these metrics; can we keep them there?"** If the
metric lives in the tool, every new report recreates it and they drift. The model
holds the definition once and every report consumes the same one. That is what makes
reports reconcile.

**"Can we do this in two sessions instead of six?"** We can compress, and sessions 1
and 6 are usually the short ones. Session 2 stays standalone: if the grain is wrong,
everything downstream is wrong.

**"Let's talk about the measures first, that is what people want to see."** No. A
measure cannot be defined correctly before we know what one row represents;
otherwise we discover it is incomputable at the grain we picked.

## 6. When to escalate

- The grain cannot be agreed in session 2. A stuck grain blocks everything.
- Two stakeholders define the same dimension differently and neither yields.
- Scope changes mid-engagement in a way that adds a business process.
- A source system cannot deliver data at the declared grain.
- Someone asks for a design that violates a principle you cannot defend abandoning
  (mixed grains, duplicate non-conformed dimensions).

Document each escalation: what was asked, what alternative was offered, what was
decided, by whom, when.

## 7. The review cycle

Three audiences, in this order, once the design team is confident.

**Peer IT review.** These reviewers know the operational system and will
instinctively apply transaction-processing rules to a dimensional model. Spend a
little time teaching dimensional concepts up front rather than debating modeling
philosophy for an hour. Then walk the bus matrix (scope, conformance, priorities),
show how the selected row became the high-level diagram, and spend the bulk of the
session in the dimension and fact worksheets and the open issues per table. Assign
someone to capture the resulting changes.

**Core business user review.** Often unnecessary because those users are on the
modeling team already. When needed it mirrors the IT review; in smaller
organizations combine the two.

**Broader business user review.** More education than review. Start with the bus
matrix as the roadmap, walk the high-level diagrams, then the critical dimensions
(customer, product). Reserve time to demonstrate answering a range of real questions
from the requirements document against the model.

**Deliverables at the end:** a short project description, the high-level model
diagram per fact table, a detailed design worksheet per fact and dimension table,
and the open issues list. Those worksheets are the first form of the source-to-target
mapping the ETL team will work from.

## 8. Failure modes and recovery

| Failure | Recovery |
|---|---|
| Grain stated vaguely ("one row per transaction-ish") | Refuse to advance. Split the process into more specific candidates until the grain is a clean sentence. |
| Same dimension defined differently by different stakeholders | Stop modeling and resolve the definition. Frequently the answer is that these are two dimensions rather than one. |
| Source cannot deliver the declared grain | Re-grain to what the source supports, or escalate to the source team to deliver it. Do not pretend the grain holds. |
| A fact table accumulating descriptive attributes | Move them to a dimension. Low-cardinality flags become a junk dimension; free text becomes a comments dimension. |
| A second non-conformed version of a shared dimension appears late | Halt that build. Reconcile to one conformed dimension, or split formally into two differently named dimensions with different definitions. |
| Reports defining their own metrics | Centralize the definition in the model or semantic layer and require reports to consume it. |
| Type 2 churn out of control | Move the high-churn attributes into a mini-dimension (type 4) and leave the slow ones in place. |
| "We will fix it in the BI tool" | Refuse. The BI tool is a consumer, not a repair shop. The issue goes back to the model. |
| Transaction and snapshot semantics mixed in one fact table | Split into two fact tables. |
| Joining mid-engagement with no idea where things stand | Locate the current bus matrix, the grain statements, the dimension inventory with SCD policy, the decision log, and the open items. If any is missing or stale, regenerate it before proceeding. |
