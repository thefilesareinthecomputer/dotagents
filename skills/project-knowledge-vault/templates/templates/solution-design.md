# SD-[###]: [Solution Title]

- [tl-dr](#tl-dr)
- [context](#context)
- [goals-and-non-goals](#goals-and-non-goals)
- [proposed-design](#proposed-design)
- [decisions](#decisions)
- [alternatives-considered](#alternatives-considered)
- [cross-cutting-concerns](#cross-cutting-concerns)
- [rollout](#rollout)
- [risks-and-dependencies](#risks-and-dependencies)
- [references](#references)

> [!tip]- How to use this (delete when done)
> Write one when the design is unclear, contested, or touches several teams or systems. Aim for one to three pages for a single feature, and split the work into several designs past about ten. Leave out full schemas, interface definitions and code; sketch them and link the real thing. Open questions go in the project vault's `notes-questions.md`, the only place they are tracked. Keep the document current until the work ships, then leave it as the record of what was built.

| | |
|---|---|
| **Status** | Draft, In review, Approved or Shipped |
| **Updated** | YYYY-MM-DD |
| **Author** | [Names] |
| **Reviewers** | [Names, and who approves] |
| **Requirements** | [The requirements section or epic this design answers, as a link] |

**Related work**

- [Work item ID, what the work item is]
- [Related solution design or ADR, as a link]

---

## tl-dr

Current state: [how it works today, in plain sentences].

Proposed: [what we will build, and what stays as it is].

---

## context

[The problem and the background a reviewer needs to follow the design: what exists today and why it is changing now. Link the requirements instead of restating them.]

---

## goals-and-non-goals

Goals:

- [A measurable outcome this design must achieve]

Non-goals:

- [Something a reader could reasonably expect this design to cover that it deliberately does not]

---

## proposed-design

[The overview first, in a paragraph and one diagram that shows the system in its surroundings: the users, the systems it talks to, and the parts this work adds or changes.]

[Then the detail a builder needs: each component and what it is responsible for, the interfaces and data it owns, and the main flows through it. Sketch an interface or a data shape where it helps; link the full definition rather than pasting it.]

---

## decisions

[One line per decision this design depends on, each linking to its ADR.]

- [ADR-###, what it decides, Proposed or Accepted]

---

## alternatives-considered

[Each approach set aside, in one or two sentences: what it was and why it lost.]

---

## cross-cutting-concerns

[Only the concerns this design changes; drop the rest.]

- **Security and privacy:** [access, data handling, compliance]
- **Reliability and performance:** [availability, latency, volume targets]
- **Observability:** [the metrics, logs and alerts that show it is working]
- **Cost:** [what it costs to run, and what drives that cost]

---

## rollout

[How the work reaches production: the testing that proves it, any migration of existing data or users, the order of the rollout steps, and how to roll back if a step fails.]

---

## risks-and-dependencies

- [A risk, how likely it is and what it would cost, and how the design reduces it]
- [A team, system or decision this work waits on, and who owns it]

---

## references

- [Requirements, prior designs, vendor documentation or research, as links, with the date each was checked]
