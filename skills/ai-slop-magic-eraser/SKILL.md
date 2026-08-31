---
name: ai-slop-magic-eraser
description: Strips the tells of machine-generated writing while preserving meaning exactly, then corrects errors, hallucinations, contradictions and inventions. Removes hedging, sycophancy, meta-commentary, inflated register, formulaic cadence, em dashes and emojis, and equally fixes the opposite failure - clipped aphoristic prose that asserts instead of informs. Use when text is described as reading like AI, like ChatGPT, generic, templated, bloated, corny, cringe, or "not how I talk"; when it reads as clipped, noir, preachy, or like it is performing authority; when polishing any model-drafted document before it ships; when asked to de-slop, tighten, or humanize writing. Read it BEFORE drafting a document someone else will read. Ships a linter (scripts/slop_check.py). Not for code logic.
license: MIT
---

# ai-slop-magic-eraser

Model prose fails in a predictable way. It does not make mistakes so much as
make **the average**: the most likely phrasing, the most balanced structure, the
most agreeable tone. The result reads fluent and says less than it appears to.

This skill runs two passes that must not be conflated:

| Pass | Changes | Never changes |
|---|---|---|
| **1. De-slop** | How it reads | What it claims |
| **2. Correct** | What it claims, where the claim is wrong | Anything already true |

Pass 1 is meaning-preserving by definition. Pass 2 deliberately changes meaning,
but only where the current meaning is false. Running them as one pass is how
content gets quietly deleted under cover of "tightening".

## The invariant

**A deletion that removes information is a bug, not a cleanup.**

Every cut in pass 1 must be justifiable as "the same claim, fewer words". If you
cannot restate the removed text's content in what remains, you have not
de-slopped it, you have lost it. When in doubt, keep the fact and cut the
framing around it.

Three corollaries, all learned the expensive way:

- **Do not neuter real warnings.** A plain statement of a genuine hazard is good
  writing. The target is the reaching-for-effect version, never the warning.
- **Do not flatten deliberate repetition.** Some duplication is a designed
  redundancy with a stated owner. Check before removing it.
- **Do not turn a conditional claim into a universal.** Cutting a qualifier is a
  deletion of information like any other. See pass 1 step 3.

## The over-correction

This pass has its own signature failure, and it is worse than the bloat it
replaces. Strip the hedges, cut the filler, tighten every sentence, and the
prose collapses into clipped declaratives and aphorisms: a hardboiled narrator
explaining a data pipeline. Verbless fragments, two-word imperatives, blanket
"never" directives and sentences built for the callback are not concision. They
are a costume, and the reader hears someone performing authority rather than
explaining a system.

**The target is regular professional prose**, in the voice of a senior engineer
explaining a system to a colleague who has to go and do the work. Full
sentences. If the person whose name is on the document would have to re-word
paragraphs rather than fact-check them, the pass failed.

Terse is a setting for chat replies. It is not a prose style. Applying it to a
shipped document is the most common route into this failure. The full catalog is
`references/tells.md` § Over-corrected register, which covers register by
audience, "we" over "you", headings that locate rather than argue, and keeping
product names concrete.

## Landmines

A failure separate from register, and the one carrying an actual professional
cost. A **landmine** is a sentence whose payload is *this part of your system is
broken, unowned, unfinished or unsafe*, sitting inside a document whose job is
something else.

Recognize one by asking what the sentence would be if lifted out. If the answer
is an audit finding, a defect report, meeting minutes, a status update or an
opinion about who should own something, it is a landmine.

Four costs. The document outlives the conversation and reaches people who were
not in the room, including whoever built the thing being criticized. It is not
what the document is for. It recasts the author from helper to auditor, a role
nobody agreed to. And a defect buried mid-document has no owner and no decision
path, so it changes nothing while costing goodwill.

**Give the reader the action, drop the verdict.** Where a defect genuinely will
bite the reader during the task at hand, allow one sentence inside that
procedure: the behavior and the workaround, no heading, no verdict, no
attribution of blame. A defect that matters more than that is worth routing
properly, to a risk register, an ADR, a findings memo, or a conversation with a
named owner.

Related and equally juvenile: the **horror-story register**, where ordinary
mechanics get narrated for dread. Cause and effect stated once is documentation.
Cause and effect narrated for effect is a horror story. Both are catalogued in
`references/tells.md`.

## Pass 1: de-slop

Run the linter first for the countable tells, then work the judgment list.

```bash
python3 scripts/slop_check.py <path> [more paths...]
```

Exit 0 clean, exit 1 findings. `--json` for machine output. `--only` filters which
categories are reported.

### The `symbol` category: characters a standard typer cannot produce

Anything outside ASCII arrived from a model, a word processor's autocorrect, or a
paste, so every non-ASCII character is reported by codepoint and name. Findings
sort into three tiers:

| Tier | Examples | `--fix` |
|---|---|---|
| Has an ASCII form | em and en dashes, curly quotes, `…`, `•`, `→`, `×`, `≥`, `′`, ligatures, no-break and thin spaces | rewritten |
| Invisible or banned | zero-width spaces, soft hyphens, bidi overrides, tag characters, emoji | deleted |
| Everything else | accented letters, `°`, `½`, box drawing, CJK, currency | reported only, never touched |

The third tier is report-only because a scanner cannot tell an accented proper
noun from a stray math symbol, and guessing costs content. Keep it where a quoted
source or a name spells it that way; retype it otherwise.

**Invisible characters are reported everywhere, code fences included.** A code
block legitimately holds any visible character and never legitimately holds a
zero-width space, and the exempt spans are exactly where text hidden from a human
reviewer would be placed.

`--fix` rewrites and deletes per the table, then collapses the double spaces a
deletion leaves behind. Visible characters inside fenced code, inline code and
link targets are left alone, so a URL or a code sample is never rewritten. Note
that `--only` does not narrow `--fix`; the fix pass runs whole or not at all.

An em dash becomes a spaced hyphen, so ` — ` becomes `  -  ` unless the
surrounding spaces are part of the match. Check the diff for doubled spaces.

Then, in this order, because early fixes change what later ones see:

**1. Sycophancy.** Cut entirely. "Great question", "You're absolutely right",
"Excellent point", "I'd be happy to", "Certainly", and any opening that praises
the request instead of answering it. In a document, cut any sentence
complimenting the reader or the subject.

**2. Meta-commentary.** Any sentence whose subject is the document. Version
banners, "supersedes", "this replaces the earlier", "how to read this", "what
this is", completeness caveats, and code comments narrating the edit rather than
explaining the code. A scope statement is content and stays: what is covered and
what is not, stated once, without referring to the document as an object.

**3. Hedging, and only hedging.** A hedge shipped in place of a fact is the
worst case: it reads as caution and conveys nothing. Three outcomes per claim,
no fourth. Verified goes in flat. Unverified is cut entirely, with no
placeholder. Out of scope is covered by the scope statement. **Confirmed absence
is a fact**: "there is no rollback procedure" is a resolved sentence, not a gap,
though it belongs inside the procedure it affects rather than in a section of
its own.

**Calibration is not hedging.** Filler qualifies the act of saying ("it's worth
noting that", "generally speaking"). Calibration qualifies the claim ("*when the
input is already normalized*", "*can* change the outcome"). The test is whether
removing the qualifier makes the sentence wrong. If it does, the qualifier is
content, and cutting it manufactures a universal nobody verified.

**4. Cadence.** The formulaic shapes, worked in `references/tells.md`. The
dominant one by a wide margin is the **"X, not Y" antithesis**. Every instance
is individually defensible; the aggregate is the single strongest machine
signal. Keep it only where a wrong belief is genuinely common and the correction
is the payload. Convert the rest to plain assertions.

**5. Register, in both directions.** Down: inflated verbs and nouns doing less
work than a plain word, vague intensifiers, claims of importance standing in for
substance. Up: the over-corrected prose above. Verbless fragments, two-word
imperatives, blanket "never" directives, aphoristic closers. In a shipped
document also fix person ("we", not "you"), abstracted product names, and any
sentence assessing the reader's organization.

**6. Structure.** Uniform section length, bullets where a sentence works, a
summary that restates rather than concludes, over-emphasis, decorative rules.
Headings that argue rather than locate, and any heading carrying a count.

**7. Symbols.** Any character a standard keyboard cannot produce - dashes,
curly quotes, ellipses, bullets, arrows, math signs, ligatures, exotic spaces,
emoji, and anything invisible. The linter catches every one of them by
codepoint; the judgment calls are what replaces a dash and whether an accented
spelling is the source's own.

Read `references/tells.md` for the full catalog with replacements.

## Pass 2: correct

Now that the prose is legible, the errors are visible. Look for:

**Confabulated negatives, the highest-risk class.** "X has no Y", "the only way
is", "you can't". A negative needs only absence of recall, which is
indistinguishable from evidence of absence, so it arrives at full confidence and
no uncertainty-triggered rule can fire on it. **Trigger on sentence shape, not
on felt doubt.** Every capability negative gets verified or rewritten in
memory-form with its epistemic status leading.

**Invented specifics.** APIs, flags, parameters, file paths, function names,
config keys, line numbers and citations that are plausible and wrong. Check them
against the actual source rather than against how right they sound.

**Contradictions.** Between sections, between a document and its siblings,
between prose and an adjacent table or code block. A generated document
contradicting itself across a long span is common and invisible on a linear read.

**Unrequested inventions.** Features, options, error handling, abstractions and
configuration nobody asked for. Every element should trace to the request.

**Symmetry bias.** Inventing a counterpart because one exists: a `stop()`
because there is a `start()`, a disable path because there is an enable path, a
fourth item because three felt short.

**Undated claims about moving targets.** Product capabilities, pricing, version
support. Date them or cut them.

Report corrections separately from polish. The reader needs to know which edits
changed meaning.

## What this skill does not touch

- **The argument.** If a document makes a case, this pass makes the case read
  better, never differently. Disagreeing with it is a different job.
- **Code logic.** Comments and identifiers are in scope; behavior is not.
- **Voice that is deliberately informal.** Match the surrounding register. A
  chat message is not a spec.
- **Quoted material, fixtures and test data.** Slop inside a quotation is
  evidence. Detector fixtures need the patterns they detect.

## Reporting

Lead with what changed in meaning, because that is the part needing review:

1. **Corrections** - each with the wrong claim, the corrected claim, and the
   source that settles it.
2. **Cuts** - what came out, grouped by category, with counts.
3. **Anything left deliberately** - a hazard warning that reads strong because
   the hazard is real, or a duplication that is designed.
4. **Anything unverifiable** - claims that could not be checked, and what would
   settle each.

Do not report the polish line by line. Report the corrections line by line.
