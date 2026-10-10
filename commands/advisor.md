---
description: Consult the advisor. Spawn the fresh-context advisor subagent with a specific question about a plan - decomposition seams, sequencing, hidden risks, proportion, or whether a synthesized deliverable meets the bar. An optional first word picks its model (fable, opus, sonnet, haiku); otherwise it runs on the session's model. Off the hot path and advisory; never for implementation.
argument-hint: "[fable|opus|sonnet|haiku] [focus]"
---

Spawn the **`advisor`** subagent and hand it a brief that stands on its own.

**Model.** If the first word of the arguments is `fable`, `opus`, `sonnet` or
`haiku`, pass it as the Agent call's `model` and drop it from the focus text.
Otherwise pass no `model`: the definition says `inherit`, so the advisor runs on
the session's own model. State in one line which model the advisor ran on.
(`haiku` is the harness alias and resolved to Haiku 4.5 on Claude Code 2.1.280.)

**Brief**, in this order:

1. **The question**: the one decision or judgment wanted from it, in a sentence.
2. **The plan or deliverable**: file paths it should read (specs, briefs, code),
   not a retelling of the conversation. It has Read, Grep, Glob, WebSearch and
   WebFetch and reads for itself.
3. **What is settled**: decisions the user has already made, so it does not
   relitigate them, and the constraints that bind (budget, machines, rules).
4. **What is measured**: numbers that exist, with where they came from.

The remaining argument text sets the focus (e.g. "is the sequencing right",
"what would you cut"). If the question is not clear from the conversation,
infer it from the current work and state the inference in the brief.

Relay the advisor's verdict and its reasoning back to the user, ranked, with the
disagreements it has with the plan stated plainly. It is **advisory**: present
the findings and let the user decide; do not act on them unasked. For in-flight
drift watching use `/supervisor`; for code or security depth route to the review
skills.
