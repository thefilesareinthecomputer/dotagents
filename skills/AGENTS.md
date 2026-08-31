# Skills folder rules

Every skill in this folder follows the house profile in [skill-authoring](skill-authoring/SKILL.md).
The rules below earn restating here because they shape every file an agent reads.

**SKILL.md is an interface, not a workshop.**
The file surfaced to the agent carries only what an operator needs at the moment of use: what each command or step does, how to invoke it, how to interpret its output, and the safety rails it must know exist.
Everything else - fixtures, answer keys, design rationale, test corpora, benchmarks - lives in `tests/`, `references/`, or the spec that built the skill, where it costs nothing until deliberately opened.

**Slim is the law, and the budget is context.**
A SKILL.md is loaded on every use, so every line in it is a recurring tax on every session that touches the skill.
Keep the file as slim as it can be while still operating the skill; when a section grows, the fix is moving depth behind the interface, not compressing sentences.

**Descriptions are charged to every session, and they route.**
Every skill's frontmatter `description` loads at session start whether the skill is used or not, so with this many skills the descriptions bloat context cumulatively or not at all.
Keep each one as short as it can be while still routing reliably: lead with what the skill is, then the trigger situations, then the boundary lines that send neighboring requests elsewhere.
Nothing else belongs there, and overlap with a sibling's description is a routing defect - two skills claiming the same words confuse the agent worse than either being verbose.
Hard limits stay as they are: the open standard caps a description at 1024 characters and this house holds them under 800, verified against the strictest parser (`copilot skill list`).

**Abstract behavior into tested code wherever possible.**
The reliable form of a skill capability is a deterministic script - usually stdlib Python or bash - that SKILL.md invokes and interprets, with its own tests behind it.
Code runs the gate outside the model; prose asks the model to remember.
A paragraph of instructions that a script could enforce is a defect in the skill, not a style choice.

**Prose-only skills take the same discipline without the code.**
A skill with no executable surface - pure method, standard, or advisory text - is exempt from the script rule but not from the budget: it is exactly as verbose as its purpose requires and no more.

**Everything in this folder is published.** The skills tree ships byte-identical
to a public repo, so a skill never carries client or engagement identifiers,
live-project details, personal constants, credentials, or paths that name a
person or machine. Write every skill for an outside reader, because it has one;
anything project-specific belongs in that project's own repo, and anything
private to this repo belongs in `tasks/`, which is held back from publication.
The pre-commit gate (`/my-security-review`) scans for exactly these, so a slip
is caught mechanically - but write as if the gate were not there.

**Systems of record stay behind the interface.**
Some skills carry one - the URL catalog and ledger in `ai-engineering`, the fixtures and answer keys in `code-kg`.
The skill's scripts read and maintain them; under normal operation the main agent never loads them into context once the skill is built.
If answering through the skill requires opening its system of record directly, the script layer is missing a query path - fix the skill rather than normalizing the read.
