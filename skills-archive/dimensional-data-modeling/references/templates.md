# Artifacts and templates

The documents a modeling engagement produces. `scripts/dim_check.py` parses the
fact and dimension specs below, so keep the bold field labels and the measure table
header intact; the prose around them is free.

| § | Artifact | Produced in |
|---|---|---|
| 1 | Grain statement | Session 2 |
| 2 | Bus matrix | Session 1, refined through 6 |
| 3 | Fact specification | Sessions 2 and 4 |
| 4 | Dimension specification | Sessions 3 and 5 |
| 5 | SCD policy | Session 5 |
| 6 | Design worksheet | Detailed design |
| 7 | Decision log | Every session |
| 8 | Sign-off checklists | Session 6 |

## 1. Grain statement

```markdown
## Grain statement: fact_<name>

**One row represents**: <one atomic sentence>

**Stability**: this definition holds across <time horizon>.

**Segregation context**: <how tenant, business unit or partition identity
participates in the grain, or "not applicable">.

**Approved by**: <names>, <date>
```

Examples that pass:

- One row in `fact_sales_line` represents one line item on one point-of-sale
  transaction at one store.
- One row in `fact_account_balance_month` represents one account's balance at the
  close of one calendar month.
- One row in `fact_claim_pipeline` represents one insurance claim's progress
  through the adjudication pipeline.

Examples that do not: "one row per transaction-ish", "one row per report line",
"one row per customer per month, or per week for retail", "one row summarizing
daily sales".

## 2. Bus matrix

| Process | Date | Customer | Product | Employee | Location | Organization |
|---|---|---|---|---|---|---|
| Sales transaction | X (transaction date) | X | X | X (sales rep) | X (store) | X (region) |
| Invoice issuance | X (issue date) | X | X | | | X (billing entity) |
| Inventory snapshot | X (snapshot date) | | X | | X (warehouse) | X (division) |
| Employee assignment | X (work date) | X (client) | | X | X (worksite) | X (branch) |

Mark cells `X` for confirmed, `?` for candidate, blank for not applicable. Note the
date role in the cell. Any dimension in two or more rows is conformed by
definition and must be identical across them.

Construction, live with the group: write processes down the left, dimensions across
the top, then walk **row by row** asking "is this process described by this
dimension?". Then walk **column by column** asking "is this dimension's definition
identical for every process that uses it?" The second pass is where conformance
conflicts surface, and it is the pass people skip.

Pitfalls: departments as rows (a department is not a measurable event), reports as
rows (reports are consumers), two stakeholders using one dimension name for two
entities, missing date roles (the build then picks one arbitrarily), and marking
everything conformed by default (conformance is a commitment to keep two
definitions identical forever, so mark it only where that is genuinely intended).

## 3. Fact specification

```markdown
## Fact: fact_<name>

**Grain**: <one atomic sentence>

**Type**: transaction | periodic snapshot | accumulating snapshot | factless

**Foreign keys**:
- date_key (role: <transaction | posted | created | shipped>)
- <dimension>_key
- <degenerate dimension, noted as such>

**Measures**:

| Name | Data type | Additivity | Definition |
|---|---|---|---|
| <measure> | decimal(18,2) | additive \| semi-additive \| non-additive | <one sentence> |

**Source**: <system, table or stream>

**Update pattern**: append-only | merge | overwrite | milestone update

**Owner**: <stakeholder>
```

Every measure needs an additivity value. Non-additive measures must name the
additive components stored alongside them.

## 4. Dimension specification

```markdown
## Dimension: dim_<name>

**Business meaning**: <one sentence>

**Natural key**: <source column>

**Surrogate key**: dim_<name>_key (required for SCD type 2 and above)

**Durable key**: <name, required where type 2 applies>

**SCD type**: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7

**Attributes**:

| Name | SCD behavior | Source |
|---|---|---|
| <attribute> | inherits \| type <N> | <source> |

**Hierarchies**: <fixed depth levels, or the ragged technique chosen>

**Conformance scope**: <facts that use this dimension>

**Unknown member**: <the key and label used for unresolved or not-applicable>

**Owner**: <stakeholder>
```

## 5. SCD policy

```markdown
## SCD policy: dim_<name>

**Default type**: <type>

**Per-attribute overrides**:
- <attribute>: type <N>, because <reason>

**Effective-date convention**:
- effective_from (timestamp, inclusive)
- effective_to (timestamp, exclusive; 9999-12-31 on the current row)
- is_current (boolean)

**Change detection**: <source CDC | hash comparison over tracked attributes>

**Retroactive change handling**: <insert and restate | reject | escalate>

**Approved by**: <names>, <date>
```

## 6. Design worksheet

One worksheet per table, and the direct input to the source-to-target mapping.

For a **dimension**, per attribute: name, description, sample values, source
system and column, derivation rule, and SCD type.

For a **fact table**: the grain statement, each foreign key and the dimension it
resolves to, degenerate dimensions, and per measure the name, description, sample
values, additivity, and derivation rule.

The physical team then adds physical names, data types and key declarations.

## 7. Decision log

| Date | Decision | Decided by | Rationale | Objections on record |
|---|---|---|---|---|

Named individuals, not "the team". One sentence of rationale. Objections recorded
even when overruled, because they are the first thing to re-read when the decision
turns out to have been wrong.

## 8. Sign-off checklists

**Bus matrix ready:**

- [ ] Every process row has a grain statement
- [ ] Every dimension column has a one-sentence business definition
- [ ] Every dimension used by two or more processes is marked conformed
- [ ] Date roles enumerated explicitly
- [ ] Cross-fact reconciliation expectations stated where they exist
- [ ] Segregation rules encoded where the model serves multiple populations
- [ ] Every in-scope report visual maps to a process and dimension pair
- [ ] Sign-off recorded per stakeholder, by name and date

**Model ready to build:**

- [ ] Every fact has an approved grain statement
- [ ] Every fact has a measure inventory with additivity documented per measure
- [ ] Every dimension has a business definition, natural key, and SCD type
- [ ] Surrogate and durable keys specified wherever type 2 applies
- [ ] Every dimension has an unknown member row defined
- [ ] Conformed dimensions identified and verified identical
- [ ] Bus matrix final and approved
- [ ] Every in-scope report visual maps to a measure, an attribute, and a join path
- [ ] Decision log complete
- [ ] Open items owned and dated
- [ ] Out-of-scope items documented as backlog
- [ ] `scripts/dim_check.py` reports no FAIL over the specs and the DDL
