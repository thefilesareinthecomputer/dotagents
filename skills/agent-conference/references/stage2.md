# Blind review

A panel of models each answered the question below independently. Their answers follow, labeled {{LABELS}}. The labels are shuffled and the authors are hidden; one of them may be yours. Review them on accuracy and insight alone. Do not try to guess authorship and do not favor an answer because it reads like your own.

The files the answers refer to are below the answers. Check claims against them. {{TOOLS}} {{REDACTION}}

# Question

{{QUESTION}}

# Files

{{FILES}}

# Answers

{{RESPONSES}}

# What to return

First, write a short paragraph for each answer: what it gets right, what it gets wrong (with the file and line that shows it), and what it alone contributes.

Then rank all {{N}} answers from best to worst. End your message with exactly one fenced JSON block and nothing after it:

```json
{"ranking": ["<best label>", "...", "<worst label>"], "rationale": {"A": "one sentence on why A sits where it does", "B": "..."}, "errors_found": "concrete errors you verified against the files, by label, or 'none'", "disagreements": "where the answers contradict each other and which side the files support"}
```

The `ranking` list must hold every label exactly once.
