# The catalog of tells

Every entry: what it looks like, why it reads as machine output, what replaces
it. Replacements are illustrative, not substitutions to apply blindly.

- [Sycophancy](#sycophancy)
- [Meta-commentary](#meta-commentary)
- [Hedging](#hedging)
- [Over-corrected register](#over-corrected-register)
- [Landmines](#landmines)
- [Cadence and rhetoric](#cadence-and-rhetoric)
- [Inflated register](#inflated-register)
- [Intensifiers and hand-waving](#intensifiers-and-hand-waving)
- [Filler transitions](#filler-transitions)
- [Structure](#structure)
- [Symbols and syntax](#symbols-and-syntax)
- [Thought patterns](#thought-patterns)

---

## Sycophancy

Agreement performed rather than meant. Costs credibility because it is
unconditional: praise that arrives before the content cannot be about it.

| Tell | Replace with |
|---|---|
| "Great question!" / "Excellent point!" | Nothing. Answer. |
| "You're absolutely right!" | "Yes." Or, if they are partly right, say which part. |
| "I'd be happy to help with that." | Nothing. |
| "That's a really insightful observation." | Nothing. |
| "Certainly! Here is..." | The thing itself. |
| "What a fascinating problem." | Nothing. |

In documents: any sentence complimenting the reader, the team, the product or
the decision. "This well-designed architecture" is an assertion nobody asked
for.

**The tell behind the tell:** if the same sentence would fit before any answer,
it is not carrying information.

---

## Meta-commentary

Writing about the document inside the document. Reads as notes-to-self that
survived into the artifact.

| Tell | Why it fails |
|---|---|
| "Version 2.0", version banners | Versioning belongs in git or a register |
| "This supersedes the earlier X" | The reader does not know an earlier one existed |
| "Where this and the previous version disagree, this is correct" | A note to the author, shipped |
| "The most consequential difference is..." | Same |
| "This section is incomplete", "coverage is partial" | Apologizing inside the artifact |
| "How to read this", "What this document is" | Addresses the artifact, not the subject |
| "As mentioned above", "as we will see below" | Navigation the structure already provides |
| "In this section we will..." | Announcing instead of doing |

**Stays:** a scope statement. What is covered and what is not, stated once,
without referring to the document as an object. "Deployment is out of scope" is
content. "This document does not cover deployment" is meta.

**In code:** comments narrating the edit rather than explaining the code.
`// changed this to fix the null bug` describes history; git holds history.

---

## Hedging

The failure is not caution. It is a hedge occupying the space where a fact
should be, which reads as diligence and conveys nothing.

| Tell | Replace with |
|---|---|
| "It's worth noting that X" | "X" |
| "It's important to understand that X" | "X" |
| "It should be noted that X" | "X" |
| "may or may not" | Which one. Or cut the sentence. |
| "This is not fully established, but likely" | Verify, or cut. |
| "Generally speaking", "in most cases", "typically" | Keep only where the exception is real and named |
| "somewhat", "fairly", "rather", "quite", "arguably" | Cut |
| "Not established" in a field | The fact, or "None". |

**Three outcomes per claim, no fourth.** Verified goes in as a plain assertion.
Unverified is cut entirely, no placeholder and no trace. Out of scope is covered
by the scope statement and never referenced again.

**Confirmed absence is a fact and is stated as one.** "There is no automated
rollback procedure" is resolved, not a gap. Hedging it into "a rollback
procedure may not currently be documented" makes a known thing unknown.

### Calibration is not hedging

The rules above are about whether a claim is *known*. They say nothing about how
wide the claim is, and reading them as "delete every qualifier" is how this pass
produces confident falsehoods.

A verified claim that holds under a condition carries its condition:

| Over-absolute | Accurate |
|---|---|
| "The flag means X" | "The flag means X when the input is already normalized" |
| "It changes the outcome" | "It can change the outcome" |
| "Anything that will outgrow the limit should be rebuilt now" | "Anything we know will outgrow the limit soon should be rebuilt now" |
| "The mismatch only appears at a boundary" | "The mismatch will usually only appear at a boundary" |

**The test: would removing the qualifier make the sentence wrong?** If yes, the
qualifier is content and stays. If no, it was filler and goes.

"It's worth noting that", "generally speaking", "somewhat" are filler: they
qualify the act of saying rather than the claim. "Can", "usually", "when X",
"we know" qualify the claim itself, and deleting them manufactures a universal
the writer never verified. An absolute the reader can find one counterexample to
costs more credibility than the qualifier ever saved.

---

## Over-corrected register

This section exists because a de-slopping pass has its own signature failure,
and it is worse than the bloat it replaced. Strip the hedges, cut the filler,
tighten every sentence, and the prose collapses into clipped declaratives and
aphorisms: a hardboiled narrator explaining a build system. It is not concision.
It is a costume, and a reader hears someone performing authority rather than
explaining a system.

The diagnosis is that a sentence is *asserting* where it should be *informing*.

| Tell | Example | Replace with |
|---|---|---|
| Verbless fragment for weight | "The workhorse." "Stops at the boundary." | A sentence |
| Two-word imperative kicker | "Plan accordingly." "Do not trim it." | Cut, or state the mechanism and why |
| Blanket imperative in prose | "Never hardcode the target name." | "Target names resolve at runtime from the deployment environment." |
| Aphoristic section closer | "Access is the real bottleneck, not the connection." | The operational point, plainly |
| Consequence-as-threat | "A script that survives becomes an undocumented path nothing monitors and no one owns." | "Remove the script when you are done with it." |
| Sentence built for the callback | "That number is not arbitrary, and it is not a window anyone chose." | State where the number comes from |

Each of these is individually defensible, which is why they accumulate. Audit by
count: more than a couple of imperatives or fragments in a document is the
signal, however good each one reads alone.

### Register by audience

| Audience | Register |
|---|---|
| Chat reply to the operator | Short, direct, first person. Fragments acceptable |
| Any shipped document | Full sentences, professional prose, "we" not "you" |

A rule tuned for chat brevity applied to a client deliverable is the most
common route into this failure. Terse is a chat setting. It is not a prose style.

### "We", not "you"

A shipped document is written by a member of the team about shared practice, not
by a vendor issuing instructions to an operator.

| Instructional | Collegial |
|---|---|
| "Use it when you control the source" | "Use it when we control the source" |
| "You do not need the tool to answer these" | "We do not need the tool to answer these" |
| "Work in development first" | "Make changes in development first" |

Second-person imperative belongs in numbered procedure steps, where the reader
is actively executing. In prose it reads as being managed.

### Headings locate, they do not argue

A heading is how a reader finds a section, not the thesis of it.

| Slogan | Locator |
|---|---|
| "Name it" | "Naming a new component" |
| "The decision tree" | "Choosing a strategy" |
| "Three settings that do not do what they read like" | "Three settings that are easily confused" |
| "Profile before you build anything" | "Profiling before building" |

**Never put a count in a heading.** "Five failure modes" is a promise the
document has to keep, and it breaks the moment one is cut or added. "The main
failure modes" carries the same information and cannot go stale.

### Abstracting away the product name

Replacing a named tool with a generic noun reads as neutrality and costs the
reader a translation on every sentence. They are looking at the vendor's own
console or docs while they read.

| Abstracted | Named |
|---|---|
| "a managed connector" | the vendor and product, as the reader sees it |
| "a staging service" | the actual service name |
| "the governed layer" | the platform's own term for it |
| "the destination store" | the store's actual name |

Scrubbing a **client alias** or an individual's name is a different rule and
still applies. Public vendor and product names are not sensitive.

Diagram node labels invert this: they are scanned, not read, so they take short
tokens rather than sentences. Long descriptive labels in a diagram node paired
with terse fragments in the prose is exactly backwards.

### Deferring to a sibling document

A document that keeps pointing elsewhere for what the reader needs has not been
written yet. Cut any section whose only content is a pointer, and inline the
detail the task requires. One cross-reference for genuinely out-of-scope depth
is fine.

---

## Landmines

Not a register problem, and the one failure here with a professional cost rather
than a stylistic one. A landmine is a sentence whose payload is *this part of
your system is broken, unowned, unfinished or unsafe*, planted inside a document
whose job is something else.

**How to recognize one:** lift the sentence out and ask what it would be on its
own. If the answer is any of these, it is a landmine.

| The sentence reads as | Shape it takes |
|---|---|
| An audit finding | "There is no X procedure", "nothing owns Y", "no one monitors Z" |
| A defect report | "X is implemented but unused, and currently unsafe" |
| A code review comment | "The committed configuration names the wrong target" |
| Meeting minutes | "**Open decision.** Whether X should Y is not settled" |
| A status update | "That is the target state; nothing has moved yet" |
| An opinion on the org chart | "No one owns this", "this should have been automated" |

Four reasons they do not belong there:

1. **The document outlives the conversation.** It reaches people who were not in
   the room, including whoever built the thing being criticized.
2. **It is not what the document is for.** A procedure tells someone how to do
   the work. A standard tells them what the rules are. Neither is a maturity
   assessment.
3. **It changes who the author is.** Writing a reference document is helping.
   Scattering findings through it is auditing, and nobody agreed to be audited
   inside a reference document.
4. **A real defect deserves better than a footnote.** Route it to a risk
   register, an ADR, a findings memo, or a conversation with a named owner. A
   landmine buried mid-document has no audience, no owner and no decision path,
   so it changes nothing and costs goodwill.

**The rewrite is nearly always the same: give the reader the action, drop the
verdict.**

| Landmine | Documentation |
|---|---|
| "There is no rollback procedure. Nothing can be reversed." | "To recover from a failed run, re-run the task; the operation is idempotent." |
| "Nothing in source control owns this, so a repository change will not affect it." | "Check the object's history to identify what writes it before changing it." |
| "Renaming invalidates every permission, and nothing warns you they are gone." | "Renaming invalidates every permission on the object. Reissue them after a rename." |
| "This component has no tests, so nobody knows if it works." | "Verify the output against X before relying on it." |

**One narrow exception.** Where a defect will bite the reader while performing
the exact task the section describes, state the behavior and the workaround in
one sentence, inside that procedure, with no verdict attached. That is a caveat,
and it is useful. It stops being a caveat the moment it gets its own heading, a
bold warning, or a clause about who should have fixed it.

### Status notes, and where the line sits

Not every mention of unfinished work is a landmine. The test is whether it
annotates a rule or demotes the document.

| Fine | Not fine |
|---|---|
| "This name is pending a rename that is agreed but not yet scheduled." | "**Open decision.** Whether X should Y is unsettled. Until ratified, Z stands." |
| "The exact set is still being agreed." | "That is the target state and nothing has moved yet. Build against it only once the migration lands." |

A short status clause attached to a specific rule is metadata, and the reader
uses it while following that rule. A callout block, or a paragraph telling the
reader that the section they just finished does not apply yet, tells them to
stop trusting the document.

### The horror-story register

Ordinary mechanics narrated for dread. It is the cadence failure applied to
consequences, and it reads as juvenile in a professional document.

| Dread | Plain |
|---|---|
| "nothing warns you", "no one will notice" | Cut. State the check that catches it |
| "silently", "quietly", "invisibly" | Usually cut. Keep only where the absence of an error is the actual mechanism |
| "destroys", "corrupts", "wipes out", "poisons" | "overwrites", "replaces", "leaves stale" |
| "by the time you find out, it is too late" | State when the check should run |
| "the most expensive way to find out" | State the cheaper order of operations |
| "and no later correction repairs it" | Cut, or state the cost once |
| "which is a piece of work in its own right" | Cut |

**Cause and effect stated once is documentation. Cause and effect narrated for
effect is a horror story.** State the mechanism, state the action, stop.

---

## Cadence and rhetoric

The shapes. This section is the highest-yield part of the catalog, because
these survive a vocabulary pass untouched.

### The "X, not Y" antithesis

The dominant tell. Every instance is individually defensible, which is exactly
why it accumulates: nothing flags it locally, and a document carrying twenty of
them reads unmistakably generated.

> "Mode is set per table, not per source."
> "It's not a bug, it's a design decision."
> "They are dimension labels, not sources."
> "A rename afterwards is a migration, not an edit."

**Keep it** where a wrong belief is genuinely common, the correction is the
payload, and the document uses the shape once or twice in total. "Mode is set
per table, not per source" earns it in a document that does not already have
nine others, because readers do assume per-source.

**Cut it** everywhere else. "They are dimension labels, not sources" → "They are
dimension labels." The negation adds nothing once the positive is stated.

**How to audit:** count them. More than two or three in a document is the signal,
regardless of how each one reads alone. Past that point the strongest instance
should survive and the rest become plain assertions.

### Other shapes

| Tell | Example | Replace with |
|---|---|---|
| Rule of three with a padded third | "fast, cheap, and effective" | The two that carry weight |
| "Not only X but also Y" | | "X and Y" |
| Rhetorical question as heading | "So what does this mean?" | The answer as the heading |
| Restating the prior conclusion to open | "Given this complexity, ..." | Start the new sentence |
| Verbless fragment for punch | "The workhorse." "Budget for it." | A sentence, or cut |
| Two-word imperative kicker | "Plan accordingly." | Cut |
| Antithesis as headline | "Source is the target, subject is the reality" | Say which is which |
| Correlative pile-up | "both X and Y, as well as Z" | A list |
| Self-answering setup | "The question is whether X. It is." | "X." |
| Symmetrical clause padding | "not just faster, but also cheaper" | Pick the one that matters |

---

## Inflated register

Words doing less work than a plain one. Individually harmless, collectively a
register that belongs to nobody.

| Inflated | Plain |
|---|---|
| leverage | use |
| utilize | use |
| facilitate | help, enable, let |
| ensure | make sure, or state the mechanism |
| delve into | examine, read |
| surface (verb) | show, find, raise |
| unlock, empower, elevate | say what it does |
| robust, seamless, comprehensive | say what property is meant |
| holistic, end-to-end (as praise) | cut |
| landscape, realm, space, ecosystem | the actual noun |
| journey, tapestry, testament | cut |
| navigate (metaphorical) | handle, work through |
| cutting-edge, state-of-the-art, best-in-class | cut, or date the claim |
| game-changing, revolutionize, transform | cut |
| myriad, plethora | many, or the number |
| paradigm, synergy | cut |

**Test:** read the sentence with the word removed. If the meaning survives, it
was decoration.

---

## Intensifiers and hand-waving

| Tell | Problem |
|---|---|
| significantly, dramatically, vastly, incredibly | Unquantified magnitude posing as measurement |
| critically, crucially, vitally, essentially | Importance asserted instead of shown |
| carefully, properly, correctly, appropriately | Describes an attitude, not an action. "Configure it properly" instructs nothing |
| "orders of magnitude" | A number, or cut |
| "This is crucial" / "Importantly," | If it is, structure shows it |
| "very", "really", "extremely" | Cut |
| "a wide range of", "a variety of" | The range, or cut |

**The pattern:** an adverb standing where a mechanism should be. "Carefully
review the config" → say what to look for.

---

## Filler transitions

| Cut | Keep instead |
|---|---|
| "That said," | Nothing, or "But" |
| "Furthermore," "Moreover," "Additionally," | Nothing. Ordering carries it |
| "In order to" | "To" |
| "At the end of the day" | Cut |
| "When it comes to X" | "For X", or start with X |
| "It goes without saying" | Then do not say it |
| "In today's fast-paced world" | Cut |
| "In conclusion," "Overall," "To summarize," | Cut, or make the summary do work |
| "Let's dive in" | Cut |
| "First and foremost" | "First" |

---

## Structure

| Tell | Why it reads generated |
|---|---|
| Every section the same length | Real content is unevenly weighted |
| Bullets where a sentence works | Fragmentation without hierarchy |
| Bullets that are full paragraphs | The list is doing nothing |
| Nesting three or more deep | Structure past the point of navigation |
| A summary restating rather than concluding | Adds length, not information |
| A table whose last column is "Why" and repeats column two | Padding a table to look analytical |
| Parallel structure held past usefulness | Forces content into a shape it does not have |
| Bold on every other phrase | Emphasis that emphasizes nothing |
| A horizontal rule between every section | Headings already separate |
| "Key Takeaways" / "TL;DR" bolted on | If needed, the document is too long |
| Every list exactly three items | Reality is rarely three |

---

## Symbols and syntax

Mechanically detectable. `scripts/slop_check.py` reports **every character
outside ASCII**, by codepoint and Unicode name, on the principle that a standard
typer produces ASCII and anything else arrived from a model, an autocorrect, or a
paste. The rows below are the common ones, not the whole set.

**Rewritten by `--fix`,** because an unambiguous ASCII form exists:

| Tell | Replace with |
|---|---|
| Em dash `—` | A spaced hyphen ` - `, or restructure. Rarely a colon |
| En dash `–` in prose | A hyphen, or "to" in ranges |
| Curly quotes `" "` `' '` | Straight quotes, unless the house style is typographic |
| Ellipsis `…` | `...`, or a full stop where the trailing-off is affectation |
| Bullet `•` mid-sentence | A hyphen, or restructure |
| Arrow `→` in prose | "becomes", "leads to". `->` in tables and diagrams |
| `×` `÷` `≤` `≥` `≠` `≈` | `x` `/` `<=` `>=` `!=` `~=` |
| Prime `′` `″` | Straight `'` and `"` |
| Ligatures `ﬁ` `ﬂ` | The letters. They paste in from PDFs and break every grep |
| No-break, thin, hair and em spaces | A real space |

**Deleted by `--fix`:**

| Tell | Why |
|---|---|
| Emojis in headings or body | House style. Especially ✨🚀🎯💡🔥⚡🌟✅🎉 |
| Emoji as a bullet marker | A real bullet |
| Zero-width spaces, soft hyphens, bidi overrides, tag characters | Invisible, and the standard vector for text hidden from a human reviewer |

**Reported but never rewritten,** because no safe ASCII form exists and a scanner
cannot tell an accented proper noun from a stray symbol: accented letters, `°`,
`§`, `½`, box drawing, CJK, currency. Keep them where a quoted source or a name
spells it that way; retype them otherwise.

Not character-level, and still worth fixing by hand:

| Tell | Replace with |
|---|---|
| `✓` / `✗` outside a table | Words |
| ALL-CAPS for emphasis | Bold, or restructure |
| Title Case On Every Heading | Sentence case, unless house style says otherwise |
| Trailing "!" in technical prose | A full stop |

**Exception:** code blocks, quoted material, test fixtures and any file whose job
is to contain these characters. The linter exempts fenced code, inline code and
link targets - **for visible characters only.** Invisible ones are reported
everywhere, exemptions included, because nothing legitimately holds a zero-width
space and the exempt spans are exactly where something hidden would be put.

---

## Thought patterns

Failure modes rather than phrasings. These are pass 2 material: they change what
the document claims, not how it reads.

### Confabulated negatives

**The highest-risk class.** "X has no Y", "the only way is", "you can't", "there
is no support for".

A positive claim needs recall of a fact. A negative needs only *absence* of
recall, which is indistinguishable from evidence of absence. So it arrives at
full confidence, and every rule keyed on felt uncertainty fails to fire.

**Trigger on sentence shape, not on doubt.** Any sentence matching that shape
near a product or capability name gets verified against a dated source, or
rewritten so the epistemic status leads: "I could not find support for Y" rather
than "Y does not exist".

### Invented specifics

Plausible and wrong: API methods, CLI flags, config keys, file paths, function
names, line numbers, citations. Fluency in the surrounding prose is the reason
they pass review. Check each against the source, not against how right it reads.

A citation that names a real document and a wrong section is the hardest to
catch and the most damaging, because the reference checks out at a glance.

### Contradictions across distance

A long generated document contradicting itself twenty pages apart, where both
statements are locally reasonable. Linear reading will not catch it. Extract
each claim about a given entity and compare them as a set.

### Symmetry bias

Inventing a counterpart because one exists. A `stop()` because there is a
`start()`. A disable path because there is an enable path. A fourth bullet
because three looked short. A "cons" section padded to match "pros".

### Averaging

Producing the statistically typical answer instead of the correct one. Shows up
as advice that fits the general case and contradicts the specifics already
given. Test: does this paragraph change if the stated constraints change? If
not, it was not written about this problem.

### Scope inflation

Features, options, error handling for impossible states, abstractions with one
caller, configuration nobody requested. Every element should trace to the
request.

### Restating the prompt as analysis

An opening paragraph paraphrasing the question and presenting it as
understanding. Cut it and start with the answer.

### Undated claims about moving targets

Product capabilities, pricing, limits, version support, "currently", "as of
now", "recently". Date it or cut it. An undated claim about a moving target is
wrong on a schedule.
