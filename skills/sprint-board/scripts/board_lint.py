#!/usr/bin/env python3
"""Validate a sprint-board markdown file against the structural rules.

EXECUTE this script; do not read it into context. It covers the mechanical half
of the pre-handoff checklist in references/audit.md - hierarchy, IDs, parent and
dependency integrity, ordering, required blocks, template residue and body
budgets. Judgment checks (is a criterion testable, is a story really two days)
stay with the agent.

    python3 board_lint.py BOARD.md [--json] [--warnings-as-errors]

Exit 0 clean, 1 findings, 2 usage error.
"""

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

# Heading -> (level name, parent level name, parent field label)
LEVELS = {
    "EPIC": ("epic", None, None),
    "FEATURE": ("feature", "epic", "Parent"),
    "STORY": ("story", "feature", "Parent"),
}
HEADING_DEPTH = {"epic": 1, "feature": 2, "story": 3}

HEADING_RE = re.compile(r"^(#{1,6})\s+(EPIC|FEATURE|STORY)-(\S+)\s*$")
TITLE_RE = re.compile(r"^-\s+\[([ xX])\]\s+(.*)$")
PARENT_RE = re.compile(r"^-\s+Parent:\s*(.*)$")
# Parent is the only link an item must declare. A predecessor is written only where
# something genuinely blocks the start, and downward links are never written at all:
# children and successors are the inverse of a link that already exists, so declaring
# them creates a second copy that drifts silently.
DEPENDS_RE = re.compile(r"^-\s+(?:Predecessor|Depends on):\s*(.*)$")
OWNER_RE = re.compile(r"^-\s+Owner:\s*(.*)$")
# Optional. The vocabulary is the board's own: this file never names a state value,
# and the checks below discover the set from the board and judge only its shape.
STATE_RE = re.compile(r"^-\s+State:\s*(.*)$")
BLOCK_RE = re.compile(r"^\*\*([A-Z][A-Z ]+)\*\*\s*$")
FENCE_RE = re.compile(r"^(`{3,})\s*$")
LABEL_RE = re.compile(r"^\*\*([A-Z][A-Z /]+)\*\*:")
# Case-insensitive twin of LABEL_RE, for the check that catches the same section
# written twice in two spellings. Everything else keys on the canonical form.
ANY_LABEL_RE = re.compile(r"^\*\*([A-Za-z][A-Za-z /]+)\*\*:")
# A state written as a hedge: two values, a question mark, a bracketed doubt.
HEDGED_STATE_RE = re.compile(r"[/?()]|\bor\b", re.I)
# The section that records why an item closed with a required box still open.
# The field set inside it is the team's to define; that one exists is not.
EXCEPTION_LABEL = "EXCEPTION"
CHECKBOX_RE = re.compile(r"^\s*-\s+\[[ xX]\]\s*(.*)$")
BULLET_RE = re.compile(r"^\s*-\s+(?!\[[ xX]\])(.+)$")

# Three ID regimes. "Real" means six digits as a tracker issues them; the linter
# never sees a tracker and only judges shape. Every ID in this skill's own docs,
# tests and examples is a fixture - NNNNnn, a repdigit run, a consecutive run such
# as 123456, or a zero-padded counter - and EPIC-/FEATURE-/STORY- are universal
# agile terms. None of it is sensitive. A scanner for leaked identifiers passes
# those shapes silently and surfaces anything else for judgment, never a hard fail:
# a test asserting which six-digit values are real goes stale the day it is written.
REAL_ID_RE = re.compile(r"^\d{6}$")
SCRATCH_ID_RE = re.compile(r"^0{2}\d{4}$")
PLACEHOLDER_RE = re.compile(r"^NNNN\d{2}$")

# A feature criterion closes by way of named stories, written as a trailing
# reference: "- [ ] <condition> (STORY-123456, STORY-NNNN02)".
TRACE_RE = re.compile(
    r"\s*\(\s*(STORY-[A-Z0-9]+(?:\s*,\s*STORY-[A-Z0-9]+)*)\s*\)\s*$", re.IGNORECASE)

# Template residue that must not survive into an authored item.
RESIDUE = [
    "{role}", "{team}", "{business case}", "{new functionality}",
    "{development actions}", "{downstream functionality}", "{Epic Title}",
    "{Feature Title}", "{Story Title}", "Criterion 1", "Criterion n",
    "Step 1:", "Step n:", "Test case 1:", "Test case n:",
]

# label -> (min, max) checkbox count, per references/anatomy.md
BUDGETS = {
    "DEVELOPMENT APPROACH": (3, 4),
    "DEFINITION OF DONE": (3, 5),
    "VALIDATION": (2, 5),
    "TESTING APPROACH": (2, 2),     # retired from the template; still budgeted for legacy boards
    "KEY ACTIVITIES": (3, 7),
    "ACCEPTANCE CRITERIA": (2, 4),
}
# A feature's acceptance criteria are a coverage map across its stories, so they run
# wider than a story's own: references/anatomy.md sets 4-8 with the hard cap at eight.
# Keyed on the label alone, the story budget flags every feature for sitting inside
# the documented standard.
BUDGETS_BY_KIND = {
    ("feature", "ACCEPTANCE CRITERIA"): (4, 8),
}
# Sections whose content must be checkboxes rather than plain bullets.
CHECKBOX_SECTIONS = set(BUDGETS)
# Acceptance-criteria sections enforce their upper bound as an error, not a hint.
HARD_CAPPED = {"DEFINITION OF DONE", "TESTING APPROACH", "ACCEPTANCE CRITERIA"}

# Placeholder phrasing that stands where a real name belongs. A story built from
# these reads identically on any system, so nobody can act on it without asking.
VAGUE_PHRASES = [
    "the table", "the inventory", "the runbook", "the document", "the register",
    "the pipeline", "the job", "the connector", "the workflow", "the estate",
    "the agreed location", "the approved scope", "where practical", "as needed",
    "as appropriate", "where applicable", "the relevant", "representative",
    "materially different", "various", "several", "certain", "some sources",
    "each source", "every source", "the system", "the platform", "the process",
]

# Cryptic writing: five habits that leave every fact present and none of it stated.
# These fire on the shape of a line rather than on a vocabulary, because a banned-word
# list is only ever as complete as the memory that wrote it and fails open on the rest.

# A clause that closes a line by arguing for it. The reasoning belongs in Purpose,
# once; repeated onto each criterion it is noise. Anchored to end-of-line so that
# "the rows that ran, because X" is caught and "a run that failed because of X"
# (where the cause IS the content) is not.
TRAILING_RATIONALE_RE = re.compile(
    r",\s+(?:so|since|because|which\s+is|which\s+means|which\s+makes|"
    r"rather\s+than|instead\s+of|not)\b[^,;]*$", re.I)

# Naming a thing by what it does instead of what it is called. Only meaningful when
# the item demonstrably knows the real name, which is what makes this positive
# evidence rather than a wordlist: the writer had the name and reached past it.
ROLE_NOUN_RE = re.compile(
    r"\bthe\s+(register|inventory|document|runbook|export|spreadsheet|"
    r"the\s+file|workbook)\b", re.I)
# A concrete artifact name: something with a file extension, anywhere in the item.
ARTIFACT_RE = re.compile(r"\b[\w./-]+\.(?:md|csv|tsv|json|yml|yaml|sql|py|xlsx)\b")

# Words that resolve only for whoever wrote the line. "Ours" assumes the reader
# already knows where the repository boundary falls, which is usually the very
# thing the item exists to establish.
DEIXIS_RE = re.compile(
    r"\b(?:ours|theirs|our\s+own|the\s+newest|the\s+latest|this\s+one)\b", re.I)

# A SQL comment is a label for a query that gets copied out and read detached from
# its prose. It names what the query returns and stops.
SQL_FENCE_RE = re.compile(r"^\s*```+\s*sql\s*$", re.I)
SQL_COMMENT_RE = re.compile(r"^\s*--\s*(.+?)\s*$")
SQL_COMMENT_MAX = 60

# People are tracker fields, not prose. Initials in a body go stale on reassignment
# and produce absurdities, such as asking an item's owner to confirm their own work.
# Approvers are named by ROLE so the item stays true when the person changes.
# An @mention is unambiguous. Otherwise only flag initials in a person-shaped
# context - "confirm with XX", "approved by XX" - because a bare two-letter token
# is far more often domain vocabulary (CRM, ERP, CDC) than somebody's initials.
# Precision matters more than recall here: a linter that cries wolf gets ignored.
MENTION_RE = re.compile(r"@[A-Za-z][A-Za-z.]{0,3}\b")
PERSON_CONTEXT_RE = re.compile(
    r"\b(?:with|by|from|to|ask|asks|tell|confirm(?:ed)?\s+with|reviewed\s+by|"
    r"approved\s+by|assigned\s+to|owner\s+is|contact)\s+"
    r"([A-Z]{1,3})\b(?![-.]?\d)(?!\s*[a-z])"       # DEF-01 and PR-7 are ids, not initials
)

# Field labels whose value may name a person, and which must carry a role instead.
ROLE_LABELS = {"OWNER", "OWNERS", "REVIEWER", "REVIEWERS", "PRIMARY OWNER",
               "IMPLEMENTATION OWNER", "CONTRIBUTORS", "APPROVER", "APPROVERS"}

# A role reads as a job, not a person. Anything on a role label that is short and
# capitalised, and matches none of these, is almost certainly initials.
ROLE_WORDS = re.compile(
    r"\b(?:engineer|architect|analyst|owner|lead|manager|developer|admin|"
    r"administrator|steward|sme|team|guild|reviewer|approver|scientist|"
    r"governance|security|business|technical|product|delivery|support)\b",
    re.I)

# Blocks holding verbatim tracker history rather than authored prose.
VERBATIM_BLOCKS = {"COMMENTS", "STORY-EDITS-AND-NOTES"}
# Labelled sections quoting someone else's words, which are preserved as written
# and so are not the board's prose to correct.
VERBATIM_LABELS = {"ORIGINAL REQUEST"}
# Sections whose job is to explain why. The rule is that reasoning lives in one of
# these once, instead of trailing every criterion beneath them, so flagging it here
# would fight the rule it enforces.
RATIONALE_LABELS = {"PURPOSE", "OUTCOME", "SCOPE BOUNDARY", "NOTE",
                    "PRIMARY QUESTION ANSWERED", "USER STORY"}

REQUIRED_BLOCKS = {
    "epic": ["DESCRIPTION"],
    "feature": ["DESCRIPTION"],
    "story": ["DESCRIPTION", "ACCEPTANCE CRITERIA"],
}


class Item:
    def __init__(self, kind, ident, line):
        self.kind = kind
        self.id = ident
        self.line = line
        self.depth = None
        self.title = None
        self.parent = None
        self.parent_line = None
        self.depends = None
        self.depends_line = None
        self.owner = None
        self.state = None
        self.state_line = None
        self.done = False
        self.blocks = {}
        self.index = None

    @property
    def ref(self):
        return f"{self.kind.upper()}-{self.id}"


def parse(text):
    """Return (items, findings-from-parsing)."""
    items, findings = [], []
    lines = text.splitlines()
    current = None
    block_name = None
    fence = None
    i = 0
    while i < len(lines):
        raw = lines[i]
        # Inside a fenced block, accumulate until the matching closing fence.
        if fence is not None:
            if raw.rstrip() == fence and current is not None:
                current.blocks[block_name]["end"] = i + 1
                fence = None
                block_name = None
            elif current is not None:
                current.blocks[block_name]["body"].append((i + 1, raw))
            i += 1
            continue

        m = HEADING_RE.match(raw)
        if m:
            hashes, word, ident = m.groups()
            kind, _, _ = LEVELS[word]
            current = Item(kind, ident, i + 1)
            current.depth = len(hashes)
            current.index = len(items)
            items.append(current)
            block_name = None
            i += 1
            continue

        if current is not None:
            m = TITLE_RE.match(raw)
            if m and current.title is None and not current.blocks:
                current.title = m.group(2).strip()
                current.done = m.group(1).lower() == "x"
                i += 1
                continue
            m = OWNER_RE.match(raw)
            if m and current.owner is None:
                current.owner = m.group(1).strip()
                i += 1
                continue
            m = STATE_RE.match(raw)
            if m and current.state is None:
                current.state = m.group(1).strip()
                current.state_line = i + 1
                i += 1
                continue
            m = PARENT_RE.match(raw)
            if m:
                current.parent = m.group(1).strip()
                current.parent_line = i + 1
                i += 1
                continue
            m = DEPENDS_RE.match(raw)
            if m:
                current.depends = m.group(1).strip()
                current.depends_line = i + 1
                i += 1
                continue
            m = BLOCK_RE.match(raw)
            if m:
                block_name = m.group(1).strip()
                current.blocks[block_name] = {
                    "line": i + 1, "fence": None, "body": [], "end": None,
                }
                i += 1
                continue
            m = FENCE_RE.match(raw)
            if m and block_name and current.blocks[block_name]["fence"] is None:
                fence = m.group(1)
                current.blocks[block_name]["fence"] = fence
                i += 1
                continue
        i += 1

    if fence is not None:
        findings.append(("error", len(lines), "unclosed-fence",
                         "A code fence is never closed; the file cannot be parsed reliably."))
    return items, findings


def classify_ids(items):
    """Decide which ID regime the board is in."""
    real = [it for it in items if REAL_ID_RE.match(it.id) and not SCRATCH_ID_RE.match(it.id)]
    return bool(real)


def check(items, parse_findings, glossary=None):
    findings = list(parse_findings)
    add = lambda sev, line, code, msg: findings.append((sev, line, code, msg))

    if not items:
        add("error", 1, "no-items", "No EPIC-, FEATURE- or STORY- headings found.")
        return findings

    by_id = {}
    for it in items:
        if it.id in by_id:
            add("error", it.line, "duplicate-id",
                f"{it.ref} reuses an ID already used at line {by_id[it.id].line}.")
        else:
            by_id[it.id] = it

    has_real = classify_ids(items)

    # Hierarchy: heading depth and containment.
    open_parent = {"epic": None, "feature": None}
    for it in items:
        if it.depth != HEADING_DEPTH[it.kind]:
            add("error", it.line, "heading-level",
                f"{it.ref} is at H{it.depth}; {it.kind} must be H{HEADING_DEPTH[it.kind]}.")
        if it.kind == "epic":
            open_parent["epic"] = it
            open_parent["feature"] = None
        elif it.kind == "feature":
            open_parent["feature"] = it
            if open_parent["epic"] is None:
                add("error", it.line, "orphan-position",
                    f"{it.ref} appears before any epic.")
        elif it.kind == "story" and open_parent["feature"] is None:
            add("error", it.line, "orphan-position",
                f"{it.ref} appears before any feature.")

        if it.title is None:
            add("error", it.line, "missing-title",
                f"{it.ref} has no '- [ ] Title' line.")

        # ID form.
        if not (REAL_ID_RE.match(it.id) or PLACEHOLDER_RE.match(it.id)):
            add("error", it.line, "bad-id-form",
                f"{it.ref} is neither a six-digit ID nor an NNNNnn placeholder.")
        elif has_real and SCRATCH_ID_RE.match(it.id):
            add("error", it.line, "wrong-placeholder-regime",
                f"{it.ref} uses a zero-sequence placeholder in a board that already "
                f"has real IDs; use the NNNNnn form.")

    # Parent and dependency fields.
    containing = {"epic": None, "feature": None}
    for it in items:
        if it.kind == "epic":
            containing["epic"] = it
            containing["feature"] = None
            continue
        if it.kind == "feature":
            containing["feature"] = it

        _, parent_kind, _ = LEVELS[it.kind.upper()]
        if it.parent is None:
            add("error", it.line, "missing-parent",
                f"{it.ref} has no '- Parent:' line.")
        elif not it.parent:
            add("error", it.parent_line, "empty-parent",
                f"{it.ref} has an empty Parent.")
        else:
            raw_parent = it.parent.split()[0]
            prefix = f"{parent_kind.upper()}-"
            if not raw_parent.startswith(prefix):
                add("warning", it.parent_line, "unprefixed-parent",
                    f"{it.ref} names its parent as '{raw_parent}'; write it as "
                    f"'{prefix}{raw_parent}' so the reference is self-describing.")
            pid = raw_parent.replace(prefix, "")
            if pid not in by_id:
                add("error", it.parent_line, "unresolved-parent",
                    f"{it.ref} names parent {pid}, which is not an item in this file.")
            else:
                enclosing = containing[parent_kind]
                if enclosing is not None and enclosing.id != pid:
                    add("error", it.parent_line, "parent-mismatch",
                        f"{it.ref} names parent {pid} but sits under "
                        f"{enclosing.ref}.")

        if it.depends is not None and it.depends.strip().lower() in ("none", "n/a", "-"):
            add("warning", it.depends_line, "empty-predecessor",
                f"{it.ref} declares no predecessor; omit the line rather than writing "
                f"\"{it.depends.strip()}\".")

    # Dependency graph.
    deps = {}
    for it in items:
        deps[it.id] = []
        if not it.depends or it.depends.lower() == "none":
            continue
        for token in re.split(r"[,;]", it.depends):
            token = token.strip()
            if not token:
                continue
            did = re.sub(r"^(EPIC|FEATURE|STORY)-", "", token).split()[0]
            if did not in by_id:
                add("error", it.depends_line, "unresolved-dependency",
                    f"{it.ref} depends on {did}, which is not an item in this file.")
                continue
            if did == it.id:
                add("error", it.depends_line, "self-dependency",
                    f"{it.ref} depends on itself.")
                continue
            deps[it.id].append(did)
            if by_id[did].index > it.index:
                add("error", it.depends_line, "order-violation",
                    f"{it.ref} depends on {by_id[did].ref}, which appears later in "
                    f"the file; document order is execution order.")

    for cycle in find_cycles(deps):
        node = by_id[cycle[0]]
        add("error", node.line, "dependency-cycle",
            "Dependency cycle: " + " -> ".join(by_id[c].ref for c in cycle + [cycle[0]]))

    # Spine shape: compound titles, feature fan-out, epic contract sections.
    children = {it.id: 0 for it in items}
    containing = {"epic": None, "feature": None}
    for it in items:
        if it.kind == "epic":
            containing["epic"] = it
            containing["feature"] = None
        elif it.kind == "feature":
            containing["feature"] = it
            if containing["epic"]:
                children[containing["epic"].id] += 1
        elif it.kind == "story" and containing["feature"]:
            children[containing["feature"].id] += 1

        if it.title and it.kind == "story":
            if re.search(r"\band\b|\balso\b|,", it.title):
                add("warning", it.line, "compound-title",
                    f"{it.ref} title joins several outcomes; a story that needs "
                    f"'and' is usually more than one story.")

    for it in items:
        if it.kind == "feature":
            if children[it.id] == 0:
                add("warning", it.line, "empty-feature",
                    f"{it.ref} has no stories; it is either unfinished or was a story.")
            elif children[it.id] > 8:
                add("warning", it.line, "feature-fan-out",
                    f"{it.ref} has {children[it.id]} stories; beyond eight this is "
                    f"probably two features.")
        elif it.kind == "epic":
            body = "\n".join(t for _, t in it.blocks.get("DESCRIPTION", {}).get("body", [])).upper()
            for label in ("OUT OF SCOPE", "END STATE", "COMPLETION EVIDENCE"):
                if label not in body:
                    add("warning", it.line, "epic-missing-section",
                        f"{it.ref} has no {label} section; an epic without one has no "
                        f"closing condition.")

    # Filler: a checkbox line repeated across many items is boilerplate, and a
    # Definition of Done that restates a Development Approach step says nothing.
    seen_lines = {}
    for it in items:
        for name, block in it.blocks.items():
            for lineno, text in block.get("body", []):
                m = CHECKBOX_RE.match(text)
                if m and m.group(1).strip():
                    seen_lines.setdefault(m.group(1).strip().lower(), []).append((it, lineno))
    for text, uses in seen_lines.items():
        owners = {it.id for it, _ in uses}
        if len(owners) > 2:
            it, lineno = uses[0]
            add("warning", lineno, "boilerplate-line",
                f"\"{text[:50]}\" appears in {len(owners)} items; a line repeated that "
                f"widely is filler rather than a criterion.")

    for it in items:
        dev = section_lines(it, "DESCRIPTION", "DEVELOPMENT APPROACH")
        dod = section_lines(it, "ACCEPTANCE CRITERIA", "DEFINITION OF DONE")
        for text, lineno in dod.items():
            if text in dev:
                add("warning", lineno, "criterion-restates-step",
                    f"{it.ref} Definition of Done repeats a Development Approach step; "
                    f"a criterion states the resulting condition, not the action.")

    # Level discipline: a feature criterion that restates a child story's
    # Definition of Done states nothing at the feature level.
    holder = None
    kids = {}
    for it in items:
        if it.kind == "feature":
            holder = it
            kids[it.id] = []
        elif it.kind == "story" and holder is not None:
            kids[holder.id].append(it)
        elif it.kind == "epic":
            holder = None
    for it in items:
        if it.kind != "feature":
            continue
        child_dod = set()
        for kid in kids.get(it.id, []):
            child_dod |= set(section_lines(kid, "ACCEPTANCE CRITERIA", "DEFINITION OF DONE"))
        # Traceability: a feature criterion names the stories that satisfy it, and
        # every story under the feature satisfies something the feature asked for.
        child_ids = {kid.id.upper() for kid in kids.get(it.id, [])}
        covered = set()
        for text, lineno in section_lines(it, "DESCRIPTION", "ACCEPTANCE CRITERIA").items():
            condition, refs = split_trace(text)
            if any(similar(condition, d) for d in child_dod):
                add("warning", lineno, "level-violation",
                    f"{it.ref} criterion repeats a child story's Definition of Done; a "
                    f"feature criterion states the condition across its stories.")
            if not refs:
                add("error", lineno, "criterion-untraced",
                    f"{it.ref} criterion names no story that satisfies it; end the line "
                    f"with the story reference, as \"(STORY-123456)\".")
                continue
            unknown = sorted(r for r in refs if r not in child_ids)
            if unknown:
                add("error", lineno, "criterion-misrouted",
                    f"{it.ref} criterion traces to {', '.join('STORY-' + u for u in unknown)}, "
                    f"which {'is' if len(unknown) == 1 else 'are'} not a story under this "
                    f"feature. A criterion is closed by its own children.")
            covered |= {r for r in refs if r in child_ids}
        if child_ids and section_lines(it, "DESCRIPTION", "ACCEPTANCE CRITERIA"):
            for orphan in sorted(child_ids - covered):
                kid = next(k for k in kids[it.id] if k.id.upper() == orphan)
                add("warning", kid.line, "story-uncovered",
                    f"{kid.ref} is not named by any {it.ref} acceptance criterion; either "
                    f"it satisfies nothing the feature asked for, or a criterion is missing.")

    # The epic's Out of Scope is a gate every item passes, not background prose.
    exclusions = out_of_scope_terms(items)
    for it in items:
        if it.kind == "epic":
            continue
        # A Scope Boundary naming an exclusion is declaring it out, not doing it.
        scanned, in_boundary = [], False
        for b in it.blocks.values():
            for _, line in b.get("body", []):
                m = LABEL_RE.match(line)
                if m:
                    in_boundary = m.group(1).strip() == "SCOPE BOUNDARY"
                    continue
                if not in_boundary:
                    scanned.append(line)
        text = f"{it.title or ''} {' '.join(scanned)}".lower()
        for line, terms in exclusions:
            hits = {t for t in terms if re.search(rf"\b{re.escape(t)}", text)}
            if len(hits) >= 2:
                add("warning", it.line, "out-of-scope-overlap",
                    f"{it.ref} overlaps an epic exclusion ({', '.join(sorted(hits)[:3])}) "
                    f"- \"{line[:60]}\". Confirm it is in scope or route it out.")

    # Specificity: a story an engineer cannot act on without asking a question.
    for it in items:
        if it.kind != "story":
            continue
        body = "\n".join(t for b in it.blocks.values() for _, t in b.get("body", []))
        low = body.lower()
        vague = sorted({p for p in VAGUE_PHRASES if p in low})
        if len(vague) >= 3:
            add("warning", it.line, "vague-reference",
                f"{it.ref} leans on placeholder phrasing ({', '.join(vague[:4])}); "
                f"name the object, source or system instead.")
        if glossary:
            named = [g for g in glossary if g.lower() in low]
            if not named:
                add("error", it.line, "no-named-object",
                    f"{it.ref} names nothing from the grounding source; it would read "
                    f"identically on any system.")

    # Cryptic writing. Walked line by line, skipping ORIGINAL REQUEST (the
    # requester's own words, preserved verbatim) and verbatim tracker history.
    for it in items:
        artifacts = set()
        for b in it.blocks.values():
            for _, line in b.get("body", []):
                artifacts.update(ARTIFACT_RE.findall(line))
        for block_name, block in it.blocks.items():
            if block_name in VERBATIM_BLOCKS:
                continue
            in_sql = verbatim = explains = False
            for lineno, line in block.get("body", []):
                m = LABEL_RE.match(line)
                if m:
                    label = m.group(1).strip()
                    verbatim = label in VERBATIM_LABELS
                    explains = label in RATIONALE_LABELS
                    continue
                if SQL_FENCE_RE.match(line):
                    in_sql = True
                    continue
                if in_sql and line.strip().startswith("```"):
                    in_sql = False
                    continue
                if in_sql:
                    cm = SQL_COMMENT_RE.match(line)
                    if cm and (len(cm.group(1)) > SQL_COMMENT_MAX
                               or TRAILING_RATIONALE_RE.search(cm.group(1))):
                        add("warning", lineno, "sql-comment-argues",
                            f"{it.ref} query comment explains why rather than naming what "
                            f"the query returns; it is a label, around eight words.")
                    continue
                if verbatim or not line.strip():
                    continue

                if not explains and TRAILING_RATIONALE_RE.search(line):
                    add("warning", lineno, "trailing-rationale",
                        f"{it.ref} line closes by arguing for itself; state the check and "
                        f"stop. The reasoning belongs in the purpose, once.")
                if artifacts and ROLE_NOUN_RE.search(line):
                    named = ", ".join(sorted(artifacts)[:2])
                    add("warning", lineno, "role-noun",
                        f"{it.ref} calls an artifact by its role while the item already "
                        f"names {named}; use the name it has on disk.")
                d = DEIXIS_RE.search(line)
                if d:
                    add("warning", lineno, "insider-deixis",
                        f"{it.ref} uses \"{d.group(0)}\", which resolves only for whoever "
                        f"wrote it; name the repository, field or column.")

    # People are fields, not prose. An initial in a body duplicates an authoritative
    # field, rots on reassignment, and asks an owner to confirm their own work.
    for it in items:
        for block_name, block in it.blocks.items():
            if block_name in VERBATIM_BLOCKS:
                continue
            in_code = False
            for lineno, line in block.get("body", []):
                stripped = line.lstrip()
                if stripped.startswith(("```", "~~~")):
                    in_code = not in_code
                    continue
                if in_code:
                    continue
                m = LABEL_RE.match(line)
                if m:
                    label, value = m.group(1).strip(), line.split(":", 1)[1].strip()
                    if label in ROLE_LABELS and value and not ROLE_WORDS.search(value):
                        add("error", lineno, "person-not-role",
                            f"{it.ref} {label} reads \"{value[:40]}\"; name the ROLE that "
                            f"approves, such as Data Engineer or Data Architect, so the "
                            f"item survives reassignment.")
                    continue
                hits = set(MENTION_RE.findall(line)) | set(PERSON_CONTEXT_RE.findall(line))
                if hits:
                    add("error", lineno, "named-person",
                        f"{it.ref} names a person in body text ({', '.join(sorted(hits)[:3])}); "
                        f"ownership and review are tracker fields. If a person must act, name "
                        f"the role, and prefer a check the system can answer instead.")

    # Closeout shape: the checks a real closeout exposes, none of which need an
    # opinion about what any state value means.
    kids = children_of(items)
    for it in items:
        secs = sections(it)

        # The same section twice, in two spellings or two forms. Traceability and
        # status read only the checkbox list, so the other is silently ignored, and
        # at closeout nobody knows which one closes the item.
        by_label = {}
        for s in secs:
            by_label.setdefault(s["label"], []).append(s)
        for label, group in by_label.items():
            if len(group) < 2:
                continue
            first, second = group[0], group[1]
            forms = {("boxes" if s["boxes"] else "bullets") for s in group}
            if len(forms) == 2:
                add("warning", second["line"], "criteria-dual-form",
                    f"{it.ref} carries '{label}' twice (lines {first['line']} and "
                    f"{second['line']}), once as plain bullets and once as checkboxes; "
                    f"only the checkbox list is read. Keep one, or state which closes "
                    f"the item.")
            else:
                add("warning", second["line"], "duplicate-section",
                    f"{it.ref} carries '{label}' twice (lines {first['line']} and "
                    f"{second['line']}); merge them.")

        # A feature with a body and no criteria is not empty, and it cannot be
        # closed against anything - which only shows when someone tries.
        if it.kind == "feature" and "DESCRIPTION" in it.blocks:
            body_text = any(t.strip() for _, t in it.blocks["DESCRIPTION"].get("body", []))
            if body_text and "ACCEPTANCE CRITERIA" not in by_label:
                add("warning", it.line, "feature-no-criteria",
                    f"{it.ref} has a body but no ACCEPTANCE CRITERIA section; nothing "
                    f"says when it closes.")

        # Declared done against the item's own boxes, in both directions.
        if it.title is None:
            continue
        checked, total = box_counts(it)
        if it.done and total and checked < total:
            dod_open = [ln for s in secs if s["label"] == "DEFINITION OF DONE"
                        for ln in s["open"]]
            other_open = total - checked - len(dod_open)
            if dod_open and not has_exception(it):
                add("error", it.line, "done-without-exception",
                    f"{it.ref} is ticked done with {len(dod_open)} Definition of Done "
                    f"box(es) still open (line {dod_open[0]}); either finish them or "
                    f"add an **EXCEPTION** section naming what is unmet and why.")
            if other_open:
                add("warning", it.line, "done-with-open-boxes",
                    f"{it.ref} is ticked done but {other_open} of its own {total} "
                    f"box(es) remain open; the title and the body disagree.")
        elif not it.done and total and checked == total:
            blocking = [k for k in kids.get(it.id, []) if not k.done]
            if not blocking:
                add("warning", it.line, "boxes-done-title-open",
                    f"{it.ref} has every box ticked{' and every child done' if kids.get(it.id) else ''} "
                    f"but its title is still open; close it or say what is missing.")

    # State field: vocabulary by discovery. The set of valid values is the set the
    # board already uses, and the checks judge the shape of a value, never its meaning.
    stated = [it for it in items if it.state]
    if stated:
        norm = lambda v: re.sub(r"\s+", " ", v.strip()).lower()
        counts, spellings = {}, {}
        for it in stated:
            counts[norm(it.state)] = counts.get(norm(it.state), 0) + 1
            spellings.setdefault(norm(it.state), {}).setdefault(it.state.strip(), []).append(it)
        largest = max(counts.values())
        for it in stated:
            if HEDGED_STATE_RE.search(it.state):
                add("warning", it.state_line, "state-hedged",
                    f"{it.ref} State reads \"{it.state[:40]}\"; a hedge has been written "
                    f"into a field that holds one value. Pick one.")
            elif counts[norm(it.state)] == 1 and largest >= 10:
                add("warning", it.state_line, "state-singleton",
                    f"{it.ref} State \"{it.state}\" appears once on a board where another "
                    f"value covers {largest} items; probably a typo.")
        for key, forms in spellings.items():
            if len(forms) > 1:
                ranked = sorted(forms.items(), key=lambda kv: -len(kv[1]))
                for spelling, users in ranked[1:]:
                    add("warning", users[0].state_line, "state-variant",
                        f"State \"{spelling}\" ({len(users)}) and \"{ranked[0][0]}\" "
                        f"({len(ranked[0][1])}) differ only in case or spacing; use one.")
        # A state carried by both ticked and unticked titles cannot mean one thing.
        # Asked as a question, because the board's vocabulary decides which is wrong.
        for key in counts:
            group = [it for it in stated if norm(it.state) == key]
            if any(it.done for it in group) and any(not it.done for it in group):
                for it in (i for i in group if i.done):
                    add("warning", it.state_line, "state-box-disagree",
                        f"{it.ref} is ticked done with State \"{it.state}\", which "
                        f"unticked items also carry; is the box or the state wrong?")

    # Blocks, residue and budgets.
    for it in items:
        for name in REQUIRED_BLOCKS[it.kind]:
            if name not in it.blocks:
                add("error", it.line, "missing-block",
                    f"{it.ref} is missing its **{name}** block.")
        for name, block in it.blocks.items():
            if block["fence"] is None:
                add("error", block["line"], "unfenced-block",
                    f"{it.ref} block **{name}** has no code fence.")
                continue
            if len(block["fence"]) != 4:
                add("error", block["line"], "fence-width",
                    f"{it.ref} block **{name}** uses a {len(block['fence'])}-backtick "
                    f"fence; the template uses four.")
            body = block["body"]
            if not any(t.strip() for _, t in body):
                add("warning", block["line"], "empty-block",
                    f"{it.ref} block **{name}** is empty.")
            for lineno, t in body:
                for token in RESIDUE:
                    if token in t:
                        add("error", lineno, "template-residue",
                            f"{it.ref} still contains template placeholder '{token}'.")
                        break
            check_sections(it, name, body, add)

    return findings


SCOPE_STOPWORDS = {
    "and", "or", "the", "of", "a", "an", "in", "to", "for", "within", "beyond",
    "outside", "with", "on", "by", "from", "any", "all", "other", "than",
    "issues", "items", "work", "solution", "implementation", "procedures",
}


def out_of_scope_terms(items):
    """Terms unique to the epic's exclusions.

    An epic states what it excludes using much of the same vocabulary it uses to
    state what it delivers, so raw term matching flags every in-scope item. Only
    terms absent from the epic's in-scope wording discriminate.
    """
    epic = next((i for i in items if i.kind == "epic"), None)
    if not epic:
        return []
    body = epic.blocks.get("DESCRIPTION", {}).get("body", [])

    exclusions, in_scope_text, inside = [], [], False
    for _, text in body:
        stripped = text.strip()
        # Section labels appear as "Out of Scope", "**OUT OF SCOPE**:" and so on.
        label = re.sub(r"[*:]", "", stripped).strip().lower()
        if label == "out of scope":
            inside = True
            continue
        if inside and stripped and not stripped.startswith("-"):
            inside = False
        if inside:
            if stripped.startswith("-"):
                exclusions.append(stripped.lstrip("- ").strip())
        else:
            in_scope_text.append(stripped)

    in_scope = set(re.findall(r"[a-zA-Z][a-zA-Z-]{3,}", " ".join(in_scope_text).lower()))
    out = []
    for line in exclusions:
        words = re.findall(r"[a-zA-Z][a-zA-Z-]{3,}", line.lower())
        terms = {w for w in words if w not in SCOPE_STOPWORDS and w not in in_scope}
        if len(terms) >= 2:
            out.append((line, terms))
    return out


def similar(a, b, threshold=0.80):
    """True when two criteria say the same thing in near-identical words."""
    return difflib.SequenceMatcher(None, a, b).ratio() > threshold


def split_trace(text):
    """Split a criterion into its condition and the story IDs it traces to."""
    m = TRACE_RE.search(text)
    if not m:
        return text.strip(), []
    refs = [r.strip().upper().removeprefix("STORY-") for r in m.group(1).upper().split(",")]
    return text[:m.start()].strip(), refs


def sections(item):
    """Every labelled section of an item, in file order, with its form.

    Each entry: {"label": canonical upper-case name, "raw": the spelling as written,
    "line", "boxes": checkbox count, "checked": ticked count, "bullets": plain-bullet
    count, "open": [line numbers of unticked boxes]}. A block's unlabelled head, such
    as the criteria that open a story's ACCEPTANCE CRITERIA block, is a section named
    after the block. Labels match case-insensitively here and only here, so that
    "Acceptance Criteria" and "ACCEPTANCE CRITERIA" land in the same bucket.
    """
    def entry(label, raw, line, head=False):
        return {"label": re.sub(r"\s+", " ", label).upper(), "raw": raw, "line": line,
                "boxes": 0, "checked": 0, "bullets": 0, "open": [], "head": head}

    out = []
    for block_name, block in item.blocks.items():
        current = entry(block_name, block_name, block["line"], head=True)
        out.append(current)
        for lineno, text in block.get("body", []):
            m = ANY_LABEL_RE.match(text)
            if m:
                current = entry(m.group(1), m.group(1).strip(), lineno)
                out.append(current)
                continue
            if CHECKBOX_RE.match(text):
                current["boxes"] += 1
                if re.match(r"^\s*-\s+\[[xX]\]", text):
                    current["checked"] += 1
                else:
                    current["open"].append(lineno)
            elif BULLET_RE.match(text):
                current["bullets"] += 1
    # A block head with no list of its own is the block header, not a section.
    return [s for s in out if not s["head"] or s["boxes"] or s["bullets"]]


def box_counts(item):
    """(checked, total) over the item's OWN checkboxes.

    Children are separate items to the parser - a heading of any kind ends the
    current item - so a parent's count never absorbs its children's boxes. The
    title checkbox is the item's declared state and is not counted here.
    """
    checked = total = 0
    for s in sections(item):
        checked += s["checked"]
        total += s["boxes"]
    return checked, total


def children_of(items):
    """id -> direct children, by containment in document order."""
    kids = {it.id: [] for it in items}
    containing = {"epic": None, "feature": None}
    for it in items:
        if it.kind == "epic":
            containing["epic"] = it
            containing["feature"] = None
        elif it.kind == "feature":
            containing["feature"] = it
            if containing["epic"]:
                kids[containing["epic"].id].append(it)
        elif it.kind == "story" and containing["feature"]:
            kids[containing["feature"].id].append(it)
    return kids


def has_exception(item):
    return any(s["label"].startswith(EXCEPTION_LABEL) for s in sections(item))


def section_lines(item, block_name, label):
    """Checkbox text under one labelled section, mapped to its line number."""
    block = item.blocks.get(block_name)
    if not block:
        return {}
    out, inside = {}, False
    for lineno, text in block.get("body", []):
        m = LABEL_RE.match(text)
        if m:
            inside = m.group(1).strip() == label
            continue
        if inside:
            c = CHECKBOX_RE.match(text)
            if c and c.group(1).strip():
                out[c.group(1).strip().lower()] = lineno
    return out


def check_sections(item, block_name, body, add):
    """Walk labelled sections inside one block and apply budgets."""
    sections = []
    current = None
    for lineno, text in body:
        m = LABEL_RE.match(text)
        if m:
            current = {"label": m.group(1).strip(), "line": lineno,
                       "boxes": 0, "bullets": 0, "wrapped": []}
            sections.append(current)
            continue
        if current is None:
            continue
        if CHECKBOX_RE.match(text):
            current["boxes"] += 1
            # The story reference is a pointer, not prose, so it does not count
            # against the line budget.
            content = split_trace(CHECKBOX_RE.match(text).group(1))[0]
            if len(content) > 120:
                current["wrapped"].append(lineno)
        elif BULLET_RE.match(text):
            current["bullets"] += 1

    # A feature's acceptance criteria live under a heading, not a bold label.
    for sec in sections:
        label = sec["label"]
        if label in CHECKBOX_SECTIONS:
            if sec["bullets"] and not sec["boxes"]:
                add("warning", sec["line"], "missing-checkboxes",
                    f"{item.ref} section '{label}' uses plain bullets; this content "
                    f"should be checkboxes.")
            lo, hi = BUDGETS_BY_KIND.get((item.kind, label), BUDGETS[label])
            if sec["boxes"] and sec["boxes"] < lo:
                add("warning", sec["line"], "under-budget",
                    f"{item.ref} section '{label}' has {sec['boxes']} items; "
                    f"expected at least {lo}.")
            if sec["boxes"] > hi:
                # Acceptance-criteria sections carry a hard cap: past it nobody
                # reads the list, and the item is too big to close cleanly.
                sev = "error" if label in HARD_CAPPED else "warning"
                add(sev, sec["line"], "over-budget",
                    f"{item.ref} section '{label}' has {sec['boxes']} items; the "
                    f"limit is {hi}. Split the item rather than extending the list.")
        for lineno in sec["wrapped"]:
            add("warning", lineno, "long-checkbox",
                f"{item.ref} has a checkbox over 120 characters; one line each.")


def find_cycles(graph):
    """Return one representative cycle per strongly connected group."""
    seen, stack, out = set(), [], []

    def walk(node):
        if node in stack:
            out.append(stack[stack.index(node):])
            return
        if node in seen:
            return
        seen.add(node)
        stack.append(node)
        for nxt in graph.get(node, []):
            walk(nxt)
        stack.pop()

    for node in graph:
        walk(node)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Lint a sprint-board markdown file.")
    ap.add_argument("board", help="path to the board markdown file")
    ap.add_argument("--json", action="store_true", help="emit findings as JSON")
    ap.add_argument("--glossary", help="file of real identifiers, one per line; every "
                                       "story must name at least one")
    ap.add_argument("--warnings-as-errors", action="store_true")
    args = ap.parse_args(argv)

    path = Path(args.board)
    if not path.is_file():
        print(f"error: no such file: {path}", file=sys.stderr)
        return 2

    items, parse_findings = parse(path.read_text(encoding="utf-8"))
    glossary = None
    if args.glossary:
        gpath = Path(args.glossary)
        if not gpath.is_file():
            print(f"error: no such glossary file: {gpath}", file=sys.stderr)
            return 2
        glossary = [ln.strip() for ln in gpath.read_text(encoding="utf-8").splitlines()
                    if ln.strip() and not ln.startswith("#")]
    findings = check(items, parse_findings, glossary)
    findings.sort(key=lambda f: (f[1], f[2]))

    errors = [f for f in findings if f[0] == "error"]
    warnings = [f for f in findings if f[0] == "warning"]

    if args.json:
        print(json.dumps({
            "file": str(path),
            "items": len(items),
            "errors": len(errors),
            "warnings": len(warnings),
            "findings": [
                {"severity": s, "line": ln, "code": c, "message": m}
                for s, ln, c, m in findings
            ],
        }, indent=2))
    else:
        for sev, line, code, msg in findings:
            print(f"{path}:{line}: {sev}: [{code}] {msg}")
        print(f"\n{len(items)} items, {len(errors)} error(s), {len(warnings)} warning(s)")

    if errors or (args.warnings_as_errors and warnings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
