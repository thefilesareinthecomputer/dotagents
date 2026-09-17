#!/usr/bin/env python3
"""Structural checker for Kimball-style dimensional models.

Reads star-schema DDL (.sql) and model specs written on the shapes in
references/templates.md (.md), and reports the violations that need no judgment.

It never imports or executes what it reads: the SQL is parsed with regular
expressions and the markdown is read as text.

Usage:
    python3 dim_check.py <path>...
    python3 dim_check.py --json <path>...

Exit status is 1 when any FAIL is reported, 0 otherwise.
"""

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- vocabulary

FACT_PREFIXES = ("fact_", "fct_", "f_", "facts_")
FACT_SUFFIXES = ("_fact", "_facts")
DIM_PREFIXES = ("dim_", "dims_", "dimension_", "d_")
DIM_SUFFIXES = ("_dim", "_dimension")

TEXT_TYPES = (
    "char", "varchar", "varchar2", "nchar", "nvarchar", "text", "ntext",
    "string", "clob", "nclob",
)
NUMERIC_TYPES = (
    "int", "integer", "bigint", "smallint", "tinyint", "decimal", "numeric",
    "number", "float", "real", "double", "money", "smallmoney",
)
FLOAT_TYPES = ("float", "real", "double")

KEY_SUFFIXES = ("_key", "_sk", "_skey")
# Operational identifiers that legitimately sit in a fact table as degenerate
# dimensions. Kimball's canonical example is the transaction or invoice number.
DEGENERATE_SUFFIXES = ("_number", "_no", "_num", "_nbr", "_ref", "_reference")
# In a fact table a text identifier is more often a natural key that should have
# been replaced by a surrogate key in the pipeline. Worth a look, not a failure.
NATURAL_KEY_SUFFIXES = ("_id", "_uuid", "_guid")
MONEY_WORDS = (
    "amount", "amt", "price", "cost", "revenue", "balance", "total", "fee",
    "charge", "salary", "wage", "profit", "margin", "tax", "discount",
)
# Coarser date grains that must not appear alongside a date key.
DATE_ROLLUPS = (
    "month", "quarter", "year", "week", "yearmonth", "fiscal_month",
    "fiscal_quarter", "fiscal_year", "fiscal_week", "period",
)

SCD2_START = re.compile(
    r"^(row_)?(effective|valid|start|begin|active)_?(from|date|dt|ts|time|timestamp|at|on)?$"
)
SCD2_END = re.compile(
    r"^(row_)?(end|expiry|expiration|expire[d]?|valid_to|effective_to|inactive)"
    r"_?(to|date|dt|ts|time|timestamp|at|on)?$"
)
SCD2_CURRENT = re.compile(r"^(is_)?current(_(flag|row|ind|indicator|version))?$")

VAGUE_GRAIN = (
    "-ish", "etc.", "various", "summar", "aggregat", "rolled up", "roll-up",
    "rollup", "depends", "per report", "tbd", "and/or", "approximately",
    ", or ",  # an alternative clause is two grains; "one or more" is not caught
)
PLACEHOLDER = re.compile(r"^(<[^>]*>|tbd|todo|n/a|\?+|-+)$", re.IGNORECASE)
ADDITIVITY = ("non-additive", "nonadditive", "semi-additive", "semiadditive", "additive")


class Finding:
    def __init__(self, severity, code, path, line, message):
        self.severity = severity
        self.code = code
        self.path = path
        self.line = line
        self.message = message

    def key(self):
        return (str(self.path), self.line, self.code)

    def as_text(self):
        return f"{self.severity} {self.path}:{self.line} [{self.code}] {self.message}"

    def as_dict(self):
        return {
            "severity": self.severity,
            "code": self.code,
            "path": str(self.path),
            "line": self.line,
            "message": self.message,
        }


class Column:
    def __init__(self, name, type_name, nullable, is_pk, line):
        self.name = name
        self.type_name = type_name
        self.nullable = nullable
        self.is_pk = is_pk
        self.line = line

    @property
    def is_text(self):
        return self.type_name.startswith(TEXT_TYPES)

    @property
    def is_numeric(self):
        return self.type_name.startswith(NUMERIC_TYPES)

    @property
    def is_float(self):
        return self.type_name.startswith(FLOAT_TYPES)

    @property
    def is_key(self):
        return self.name.endswith(KEY_SUFFIXES)


class Table:
    def __init__(self, name, path, line):
        self.name = name
        self.path = path
        self.line = line
        self.columns = []
        self.pk = []
        self.kind = "unknown"
        self.by_name = False  # classified from the naming convention, not inferred

    @property
    def measures(self):
        return [c for c in self.columns if c.is_numeric and not c.is_key]


# ------------------------------------------------------------------ DDL parse

def sanitize(identifier):
    """Reduce a parsed identifier to printable ASCII, bounded in length.

    Identifiers come from files that may be hostile, and they end up in output an
    agent or a terminal reads, so control characters and escape sequences are
    stripped here rather than echoed back.
    """
    kept = "".join(c for c in identifier if c.isprintable() and c.isascii())
    return kept[:64]


def classify(name):
    """Return (kind, by_name) from the table name alone."""
    bare = name.split(".")[-1].strip('"`[]').lower()
    if bare.startswith(FACT_PREFIXES) or bare.endswith(FACT_SUFFIXES):
        return "fact", True
    if bare.startswith(DIM_PREFIXES) or bare.endswith(DIM_SUFFIXES):
        return "dimension", True
    return "unknown", False


def infer_kind(table):
    """Classify an unconventionally named table from its shape."""
    keys = [c for c in table.columns if c.is_key]
    if len(keys) >= 2 and table.measures:
        return "fact"
    if len(table.pk) == 1 and len([c for c in table.columns if c.is_text]) >= 3:
        return "dimension"
    return "unknown"


def split_top_level(body):
    """Split a CREATE TABLE body on commas that are not inside parentheses."""
    parts, depth, current = [], 0, []
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if "".join(current).strip():
        parts.append("".join(current))
    return parts


CREATE_RE = re.compile(
    r"create\s+(?:or\s+replace\s+)?(?:external\s+|temporary\s+|temp\s+)?table\s+"
    r"(?:if\s+not\s+exists\s+)?([A-Za-z0-9_.\"`\[\]]+)\s*\(",
    re.IGNORECASE,
)
CONSTRAINT_START = re.compile(
    r"^\s*(primary\s+key|foreign\s+key|constraint|unique|check|key\s|index\s)",
    re.IGNORECASE,
)
PK_COLS_RE = re.compile(r"primary\s+key\s*\(([^)]*)\)", re.IGNORECASE)


def strip_comments(sql):
    """Blank out comments, preserving character offsets so line numbers hold."""
    out = re.sub(r"--[^\n]*", lambda m: " " * len(m.group(0)), sql)
    return re.sub(
        r"/\*.*?\*/",
        lambda m: re.sub(r"[^\n]", " ", m.group(0)),
        out,
        flags=re.DOTALL,
    )


def parse_ddl(sql, path):
    """Return the tables declared by CREATE TABLE statements in sql."""
    sql = strip_comments(sql)
    tables = []
    for match in CREATE_RE.finditer(sql):
        depth, end = 1, None
        for i in range(match.end(), len(sql)):
            if sql[i] == "(":
                depth += 1
            elif sql[i] == ")":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end is None:
            continue
        raw_name = match.group(1)
        table = Table(
            sanitize(raw_name.split(".")[-1].strip('"`[]').lower()),
            path,
            sql.count("\n", 0, match.start()) + 1,
        )
        table.kind, table.by_name = classify(raw_name)
        body = sql[match.end():end]
        cursor = match.end()
        for part in split_top_level(body):
            # Point at the declaration itself, not at the whitespace before it.
            lead = len(part) - len(part.lstrip())
            line = sql.count("\n", 0, cursor + lead) + 1
            cursor += len(part) + 1  # the comma the split consumed
            item = part.strip()
            if not item:
                continue
            if CONSTRAINT_START.match(item):
                pk = PK_COLS_RE.search(item)
                if pk and "foreign" not in item.lower()[: pk.start()]:
                    table.pk.extend(
                        c.strip().strip('"`[]').lower() for c in pk.group(1).split(",")
                    )
                continue
            tokens = item.split()
            if len(tokens) < 2:
                continue
            name = sanitize(tokens[0].strip('"`[]').lower())
            type_name = sanitize(tokens[1].split("(")[0].lower())
            lowered = item.lower()
            column = Column(
                name=name,
                type_name=type_name,
                nullable="not null" not in lowered,
                is_pk="primary key" in lowered,
                line=line,
            )
            table.columns.append(column)
            if column.is_pk:
                table.pk.append(name)
        if table.kind == "unknown":
            table.kind = infer_kind(table)
        tables.append(table)
    return tables


# ------------------------------------------------------------------ DDL rules

def fact_findings(table):
    sev = "FAIL" if table.by_name else "WARN"
    out = []
    key_columns = [c for c in table.columns if c.is_key]

    for column in table.columns:
        if column.is_text and not column.is_key:
            if column.name.endswith(DEGENERATE_SUFFIXES):
                pass  # a degenerate dimension, which belongs in the fact table
            elif column.name.endswith(NATURAL_KEY_SUFFIXES):
                out.append(Finding(
                    "WARN", "FACT-NATURAL-KEY", table.path, column.line,
                    f"{table.name}.{column.name} is a text identifier in a fact "
                    f"table: either declare it as a degenerate dimension or replace "
                    f"it with the dimension's surrogate key",
                ))
            else:
                out.append(Finding(
                    sev, "FACT-TEXT-ATTR", table.path, column.line,
                    f"{table.name}.{column.name} is a descriptive attribute in a fact "
                    f"table: move it to a dimension (junk dimension for flags, "
                    f"comments dimension for free text)",
                ))
        if column.is_key and column.nullable:
            out.append(Finding(
                sev, "FACT-NULL-FK", table.path, column.line,
                f"{table.name}.{column.name} is a nullable foreign key: declare it "
                f"NOT NULL and point unresolved rows at the dimension's unknown member",
            ))
        if column.is_float and any(w in column.name for w in MONEY_WORDS):
            out.append(Finding(
                sev, "FACT-FLOAT-MONEY", table.path, column.line,
                f"{table.name}.{column.name} stores a monetary measure as "
                f"{column.type_name}: use decimal or numeric",
            ))

    has_date = any(
        c.name.replace("_key", "").replace("_sk", "").endswith(("date", "day", "dt"))
        for c in key_columns
    )
    if has_date:
        for column in key_columns:
            base = re.sub(r"(_key|_sk|_skey)$", "", column.name)
            if base.endswith(DATE_ROLLUPS):
                out.append(Finding(
                    sev, "FACT-CENTIPEDE-DATE", table.path, column.line,
                    f"{table.name} has both a date key and {column.name}: collapse "
                    f"hierarchical date levels into the date dimension",
                ))
    if len(key_columns) > 20:
        out.append(Finding(
            "WARN", "FACT-CENTIPEDE-WIDE", table.path, table.line,
            f"{table.name} has {len(key_columns)} foreign keys: check for "
            f"hierarchical levels to collapse or flags to move into a junk dimension",
        ))
    if not table.measures:
        out.append(Finding(
            "WARN", "FACT-NO-MEASURE", table.path, table.line,
            f"{table.name} has no numeric measure: if it is a factless fact table, "
            f"declare that in its spec",
        ))
    return out


def dimension_findings(table, dim_names):
    sev = "FAIL" if table.by_name else "WARN"
    out = []
    starts = [c for c in table.columns if SCD2_START.match(c.name)]
    ends = [c for c in table.columns if SCD2_END.match(c.name)]
    currents = [c for c in table.columns if SCD2_CURRENT.match(c.name)]
    tracks_history = bool(starts and (ends or currents))

    if tracks_history:
        surrogate = [p for p in table.pk if p.endswith(KEY_SUFFIXES)]
        if table.pk and not surrogate:
            out.append(Finding(
                sev, "DIM-SCD2-NO-SURROGATE", table.path, table.line,
                f"{table.name} tracks history but is keyed on "
                f"{', '.join(table.pk)}: a type 2 dimension has several rows per "
                f"business key and needs a surrogate primary key",
            ))
        elif len(surrogate) > 1:
            out.append(Finding(
                "WARN", "DIM-SCD2-COMPOSITE-KEY", table.path, table.line,
                f"{table.name} has a composite primary key "
                f"({', '.join(table.pk)}): a dimension takes a single key column",
            ))
    if starts and not ends and not currents:
        out.append(Finding(
            "WARN", "DIM-SCD2-INCOMPLETE", table.path, starts[0].line,
            f"{table.name} has {starts[0].name} but no expiration column and no "
            f"current row indicator: type 2 needs all three",
        ))
    if not table.pk:
        out.append(Finding(
            "WARN", "DIM-NO-PK", table.path, table.line,
            f"{table.name} declares no primary key",
        ))
    for column in table.columns:
        if not column.is_key or column.name in table.pk:
            continue
        base = re.sub(r"(_key|_sk|_skey)$", "", column.name)
        for candidate in (base, f"dim_{base}", f"d_{base}", f"{base}_dim"):
            if candidate in dim_names and candidate != table.name:
                out.append(Finding(
                    "WARN", "DIM-SNOWFLAKE", table.path, column.line,
                    f"{table.name}.{column.name} references {candidate}: flatten the "
                    f"hierarchy into this dimension, or keep it as a deliberate "
                    f"outrigger",
                ))
                break
    return out


JOIN_RE = re.compile(r"\bjoin\s+([A-Za-z0-9_.\"`\[\]]+)", re.IGNORECASE)
FROM_RE = re.compile(r"\bfrom\s+([A-Za-z0-9_.\"`\[\]]+)", re.IGNORECASE)


def join_findings(sql, path):
    """Flag a single query joining two fact tables on their foreign keys."""
    out = []
    sql = strip_comments(sql)
    if CREATE_RE.search(sql) and "join" not in sql.lower():
        return out
    # UNION branches are separate FROM chains, so they are not fact-to-fact joins.
    for statement in re.split(r";|\bunion\b(?:\s+all)?", sql, flags=re.IGNORECASE):
        refs = []
        for match in list(FROM_RE.finditer(statement)) + list(JOIN_RE.finditer(statement)):
            kind, by_name = classify(match.group(1))
            if kind == "fact" and by_name:
                refs.append((match.group(1), match.start()))
        names = {r[0].split(".")[-1].strip('"`[]').lower() for r in refs}
        if len(names) > 1:
            offset = sql.index(statement) if statement in sql else 0
            out.append(Finding(
                "FAIL", "FACT-TO-FACT-JOIN", path,
                sql.count("\n", 0, offset + refs[0][1]) + 1,
                f"query joins fact tables {', '.join(sorted(names))}: the cardinality "
                f"of such a join is uncontrollable, so drill across instead (query "
                f"each separately, then merge on conformed row headers)",
            ))
    return out


# ------------------------------------------------------------- markdown specs

FENCE_RE = re.compile(r"^\s*(```|~~~)")
HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.*)$")
FIELD_RE = re.compile(r"^\s*\*\*([^*]+)\*\*\s*:\s*(.*)$")
SPEC_HEADING_RE = re.compile(r"^(fact|dimension)\s*:\s*(.+)$", re.IGNORECASE)


def parse_spec(text):
    """Return spec blocks found outside fenced code, so templates are exempt."""
    blocks, current, in_fence, in_measures = [], None, False, False
    for number, line in enumerate(text.splitlines(), start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading = HEADING_RE.match(line)
        if heading:
            match = SPEC_HEADING_RE.match(heading.group(1).strip())
            current, in_measures = None, False
            if match:
                current = {
                    "kind": match.group(1).lower(),
                    "name": match.group(2).strip(),
                    "line": number,
                    "fields": {},
                    "rows": [],
                }
                blocks.append(current)
            continue
        if current is None:
            continue
        field = FIELD_RE.match(line)
        if field:
            label = field.group(1).strip().lower()
            current["fields"][label] = (field.group(2).strip(), number)
            in_measures = label in ("measures", "facts")
        elif in_measures and line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if cells and not set("".join(cells)) <= set("-: "):
                current["rows"].append((cells, number))
    return blocks


def value_of(block, *names):
    for name in names:
        if name in block["fields"]:
            value, line = block["fields"][name]
            if value and not PLACEHOLDER.match(value.strip()):
                return value, line
    return None, block["line"]


def spec_findings(block, path):
    out = []
    name = block["name"]
    if block["kind"] == "fact":
        grain, line = value_of(block, "grain", "one row represents")
        if grain is None:
            out.append(Finding(
                "FAIL", "SPEC-FACT-NO-GRAIN", path, block["line"],
                f"fact spec {name} declares no grain: write "
                f"\"one row represents ___\" before anything else",
            ))
        else:
            lowered = grain.lower()
            sentences = [s for s in re.split(r"[.!?]\s+", grain.strip()) if s]
            hits = [m for m in VAGUE_GRAIN if m in lowered]
            if hits or len(sentences) > 1:
                reason = (
                    f"contains {', '.join(repr(h) for h in hits)}" if hits
                    else "runs to more than one sentence"
                )
                out.append(Finding(
                    "WARN", "SPEC-GRAIN-VAGUE", path, line,
                    f"grain of {name} {reason}: a grain statement is one atomic "
                    f"sentence, and a vague one cannot be tested against",
                ))
        if value_of(block, "type", "fact table type")[0] is None:
            out.append(Finding(
                "WARN", "SPEC-FACT-NO-TYPE", path, block["line"],
                f"fact spec {name} does not say whether it is a transaction, "
                f"periodic snapshot, accumulating snapshot or factless table",
            ))
        for cells, line in block["rows"]:
            joined = " ".join(cells).lower()
            if joined.startswith("name ") or "additivity" in joined:
                continue  # header row
            if len(cells) < 2 or PLACEHOLDER.match(cells[0]):
                continue
            if not any(word in joined for word in ADDITIVITY):
                out.append(Finding(
                    "FAIL", "SPEC-MEASURE-NO-ADDITIVITY", path, line,
                    f"measure {cells[0]} of {name} declares no additivity: mark it "
                    f"additive, semi-additive or non-additive",
                ))
    else:
        scd, line = value_of(block, "scd type", "scd")
        types = re.findall(r"[0-7]", scd or "")
        if scd is None or not types:
            out.append(Finding(
                "FAIL", "SPEC-DIM-NO-SCD", path, block["line"],
                f"dimension spec {name} declares no SCD type: ask the business "
                f"whether historical reports should change when an attribute changes",
            ))
        elif any(t in ("2", "5", "6", "7") for t in types):
            if value_of(block, "surrogate key")[0] is None:
                out.append(Finding(
                    "FAIL", "SPEC-DIM-SCD2-NO-SURROGATE", path, line,
                    f"dimension spec {name} is type {'/'.join(types)} but names no "
                    f"surrogate key: history tracking means several rows per business "
                    f"key",
                ))
            if value_of(block, "durable key")[0] is None:
                out.append(Finding(
                    "WARN", "SPEC-DIM-NO-DURABLE-KEY", path, line,
                    f"dimension spec {name} is type {'/'.join(types)} but names no "
                    f"durable key: something has to identify the entity across its rows",
                ))
        if value_of(block, "natural key")[0] is None:
            out.append(Finding(
                "WARN", "SPEC-DIM-NO-NATURAL-KEY", path, block["line"],
                f"dimension spec {name} names no natural key",
            ))
    return out


# ------------------------------------------------------------------- the pass

def collect_paths(inputs):
    paths = []
    for raw in inputs:
        path = Path(raw)
        if path.is_dir():
            paths.extend(
                p for p in sorted(path.rglob("*"))
                if p.suffix.lower() in (".sql", ".md") and p.is_file()
            )
        elif path.is_file():
            paths.append(path)
        else:
            print(f"dim_check: no such path: {raw}", file=sys.stderr)
    return paths


def run(inputs):
    findings, tables = [], []
    documents = []
    for path in collect_paths(inputs):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"dim_check: cannot read {path}: {exc}", file=sys.stderr)
            continue
        documents.append((path, text))
        if path.suffix.lower() == ".sql":
            tables.extend(parse_ddl(text, path))

    dim_names = {t.name for t in tables if t.kind == "dimension"}
    for table in tables:
        if table.kind == "fact":
            findings.extend(fact_findings(table))
        elif table.kind == "dimension":
            findings.extend(dimension_findings(table, dim_names))

    for path, text in documents:
        if path.suffix.lower() == ".sql":
            findings.extend(join_findings(text, path))
        else:
            for block in parse_spec(text):
                findings.extend(spec_findings(block, path))

    findings.sort(key=lambda f: f.key())
    return findings, tables


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="dim_check.py",
        description="Check dimensional model DDL and specs for structural violations.",
    )
    parser.add_argument("paths", nargs="+", help="files or directories to check")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    findings, tables = run(args.paths)
    fails = sum(1 for f in findings if f.severity == "FAIL")

    if args.json:
        print(json.dumps({
            "findings": [f.as_dict() for f in findings],
            "tables": sorted(
                ({
                    "name": t.name,
                    "kind": t.kind,
                    "classified_by": "name" if t.by_name else "shape",
                    "path": str(t.path),
                    "line": t.line,
                } for t in tables),
                key=lambda t: (t["path"], t["line"]),
            ),
            "summary": {
                "fail": fails,
                "warn": len(findings) - fails,
                "tables": len(tables),
            },
        }, indent=2, sort_keys=True))
    else:
        for finding in findings:
            print(finding.as_text())
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
