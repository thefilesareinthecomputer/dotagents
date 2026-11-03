---
type: reference
title: Business Requirements
description: What this project is accountable for delivering, and the constraints it delivers under.
tags:
  - requirements
  - brd
skills:
  - <a skill this project requires>
status: draft
updated: YYYY-MM-DD
---

# BUSINESS REQUIREMENTS

> ==One line on what this project delivers and why it matters.==

The top of the ladder. Every story in [[user-stories]] rolls up to something stated here, and anything in flight that does not is either scope creep or a requirement nobody wrote down. Who the vault serves and who is who is in [[01-north-star]].

> [!tip]- How to fill this in (delete when intake is done)
> - Fill the frontmatter's `skills:` list and every section above the two derived ones. A ==highlight== marks each spot that needs your answer, and intake is done when none is left.
> - The derived sections stay on _Pending_ until an agent drafts them from the intake. Requirements come first and the technical design second, each written only after you approve it, and each approved pass gets one line in `log.md`.
> - Derived content cites its sources: a vault note as a wikilink, and a file outside the vault, such as a knowledge base entry, in backticks with the date it was last checked. A claim from a source older than six months is re-verified or marked STALE.
> - People go in the TEAM table in [[01-north-star]], and open questions and pending decisions go in [[notes-questions]], so neither has a section here.

## Project identity

- **Project or initiative:** ==name==
- **Who it is for:** ==the client, team or person, and their industry or field==
- **Regulatory profile:** ==for example HIPAA, SOX, GDPR, PCI-DSS, or none==
- **Type of work:** ==greenfield, migration, modernization, proof of concept or learning project==
- **Start date:** ==YYYY-MM-DD==
- **Current status:** ==for example pre-kickoff, discovery or in flight==

## Your position

- **Stated role:** ==your role on this project==
- **Mandate:** ==what you can decide on your own==
- **Owns vs advises:** ==what you own outright, and where you only advise==

## Current state

What exists today, stated plainly enough that someone joining in month three can tell what was already there from what this project built.

- **Platforms and infrastructure:** ==what is already in place==
- **Source systems and inputs:** ==how many, and of what kind==
- **Known pain:** ==the real problem driving this work, technical debt included==
- **Team skills:** ==what the people who will run the result can and cannot operate==

## Desired state

What is true when this is done, written so that it can be checked rather than argued about.

- **Outcomes:** ==what success looks like for the people it serves, outcomes before technology==
- **Mandated technology:** ==only what is already fixed; mark anything still open==
- **Definition of done:** ==measurable success criteria==

## Known technologies

Every tool, platform or method named so far. Each one the project needs someone to know also goes in the `skills:` frontmatter, which a knowledge base diffs against its proven skills to find the gaps.

- ==a technology==

## Constraints

Each one with who owns it.

- **Budget:** ==budget==
- **Headcount:** ==headcount==
- **Timeline pressure:** ==timeline pressure==
- **Compliance:** ==compliance==
- **Appetite for change:** ==appetite for change==
- **Lock-in tolerance:** ==open source first, cloud-native is fine, or indifferent==
- **Security and tooling restrictions:** ==for example no public internet egress, or an approved-vendor list==

## Milestones

| Milestone | Target date | Hard deadline? | Notes |
|---|---|---|---|
| ==milestone== | ==YYYY-MM-DD== | ==yes or no== | ==notes== |

## Scope boundaries

What is in, and what is explicitly out. The out list is the one that earns its keep.

- **In scope:** ==what this work covers==
- **Out of scope:** ==what it explicitly does not==

## Risks and gaps

Your own read of the known gaps and risks at intake. The derived risk register below refines it.

- ==a gap or risk==

## Decisions

Settled decisions that constrain the work, newest first. Anything still open belongs in [[notes-questions]], not here.

- YYYY-MM-DD - <the decision> - <why>

## Derived requirements and delivery

> [!warning] Not filled at intake
> Drafted from the sections above once intake is done, and written only after you approve it.

### Functional requirements

_Pending._

### Non-functional requirements

Performance, availability, security posture, compliance controls, observability and cost ceilings. _Pending._

### Stakeholders and RACI

_Pending._

### Acceptance criteria

Sharpened until each one is testable. _Pending._

### Risk register, dependencies and assumptions

_Pending._

### Phased roadmap

Foundation, then a minimum viable product, then hardening, then scale. _Pending._

### Recommendations on pending decisions

One recommendation per open decision in [[notes-questions]]. _Pending._

### Knowledge gaps

Anything the intake names that the knowledge sources do not cover, and every source re-verified for staleness.

| Topic or source | Found in | Coverage or result | Action | Status |
|---|---|---|---|---|
| _Pending._ | | | | |

## Derived technical design

> [!warning] Not filled at intake
> Drafted after the requirements are approved, and written only after you approve it. It builds on the requirements and never rewrites them. It is a whole-project draft: each feature's solution design starts from it and can override it.

### Candidate approaches

Two or three shapes, and the tradeoff that decides between them. _Pending._

### Recommended approach

The decision first, then the rationale, with its sources cited. _Pending._

### Component selection

For each component: the choice, the source it traces to and that source's date, and the tradeoff in cost, complexity, lock-in, skill gap or governance. _Pending._

### Data model and interfaces

_Pending._

### Integration and orchestration

How inputs arrive, how work is scheduled, and how changes propagate. _Pending._

### Security, access and governance

_Pending._

### Operations

Observability, the cost model, CI/CD and the rollback path. _Pending._

### Delivery slices

Vertical slices from foundation to scale, each with its acceptance criteria and how it is checked. Once approved they become the board in [[user-stories]]. _Pending._

### Named bottleneck and technical risks

The one constraint, whether skills, budget, timeline or technology, most likely to break the design. _Pending._

## Related

- [[user-stories]] - the work this document is the aggregate of
- [[01-north-star]] - who the project serves, and the team
- [[notes-questions]] - the open questions and pending decisions against these requirements
