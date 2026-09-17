#!/usr/bin/env python3
"""Audit a dbt project from its manifest.json for mechanical faults.

Reads a manifest and reports structural problems that are visible without a
warehouse: staging models that join, models with no tests, sources with no
freshness block, marts selecting straight from sources, arrival timestamps used
as an event boundary, and incremental configurations whose failure mode is
silent.

Offline and read-only. It parses JSON and never evaluates, imports or executes
anything the manifest contains. Manifest content is treated as untrusted: every
identifier is sanitized before it reaches the output.

Usage:
    python3 dbt_audit.py target/manifest.json
    python3 dbt_audit.py target/manifest.json --json
    python3 dbt_audit.py target/manifest.json --compare state/manifest.json

Exit codes: 0 clean or warnings only, 1 at least one FAIL, 2 could not read.

What it cannot see: it reads structure, not data. It cannot tell you whether a
key is unique, whether a watermark moves, whether a partition column suits the
query pattern, or whether the numbers are right. Silence is not approval.
"""

import argparse
import json
import re
import sys

# Node path segments that identify a layer. Checked against the model's path,
# so a project using different directory names needs these adjusted.
STAGING_DIRS = ("staging", "stg")
MART_DIRS = ("marts", "mart", "curated", "gold")
INTERMEDIATE_DIRS = ("intermediate", "int")

# The sanctioned escape hatch for a staging model that must join.
BASE_MARKERS = ("base_", "/base/")

# Column names that record when a row arrived rather than when the event
# happened. Using one as an event boundary silently drops backdated rows.
ARRIVAL_NAME_PARTS = (
    "loaded_at",
    "load_ts",
    "_loaded",
    "ingest",
    "synced",
    "sync_ts",
    "inserted_at",
    "insert_ts",
    "arrival",
    "arrived",
    "extract_ts",
    "extracted_at",
    "dbt_updated_at",
    "etl_",
    "_dw_",
)

# Strategies whose correctness depends on a unique key.
KEYED_STRATEGIES = ("merge", "delete+insert", "delete_insert")

MAX_IDENT = 120


def sanitize(text):
    """Reduce an identifier from the manifest to bounded printable ASCII."""
    if not isinstance(text, str):
        text = str(text)
    kept = "".join(c for c in text if c.isprintable() and c.isascii())
    return kept[:MAX_IDENT]


class Finding:
    def __init__(self, level, code, node, message):
        self.level = level
        self.code = code
        self.node = sanitize(node)
        self.message = message

    def as_dict(self):
        return {
            "level": self.level,
            "code": self.code,
            "node": self.node,
            "message": self.message,
        }

    def __str__(self):
        return "{}: [{}] {} - {}".format(
            self.level, self.code, self.node, self.message
        )


def load_manifest(path):
    """Read and minimally validate a manifest. Raises ValueError on bad shape."""
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("manifest root is not an object")
    if "nodes" not in data or not isinstance(data.get("nodes"), dict):
        raise ValueError("manifest has no 'nodes' object; is this a manifest.json?")
    return data


def config_of(node):
    cfg = node.get("config")
    return cfg if isinstance(cfg, dict) else {}


def depends_on(node):
    dep = node.get("depends_on")
    if not isinstance(dep, dict):
        return []
    nodes = dep.get("nodes")
    return nodes if isinstance(nodes, list) else []


def path_of(node):
    for key in ("original_file_path", "path"):
        value = node.get(key)
        if isinstance(value, str):
            return value.replace("\\", "/")
    return ""


def in_layer(node, dirs):
    """True when the node's path sits under one of the named directories."""
    parts = [p.lower() for p in path_of(node).split("/") if p]
    # The filename is not a directory; drop it before matching.
    return any(p in dirs for p in parts[:-1])


def is_base_model(node):
    lowered = (path_of(node) + "/" + str(node.get("name", ""))).lower()
    return any(marker in lowered for marker in BASE_MARKERS)


def looks_like_arrival(column_name):
    lowered = str(column_name).lower()
    return any(part in lowered for part in ARRIVAL_NAME_PARTS)


def models_of(manifest):
    return {
        uid: node
        for uid, node in manifest.get("nodes", {}).items()
        if isinstance(node, dict) and node.get("resource_type") == "model"
    }


def tested_node_ids(manifest):
    """unique_ids that at least one data test depends on."""
    tested = set()
    for node in manifest.get("nodes", {}).values():
        if not isinstance(node, dict):
            continue
        if node.get("resource_type") != "test":
            continue
        for parent in depends_on(node):
            tested.add(parent)
    return tested


def check_sources(manifest):
    findings = []
    sources = manifest.get("sources")
    if not isinstance(sources, dict):
        return findings
    for uid, src in sources.items():
        if not isinstance(src, dict):
            continue
        freshness = src.get("freshness")
        has_freshness = isinstance(freshness, dict) and any(
            isinstance(freshness.get(k), dict) for k in ("warn_after", "error_after")
        )
        if not has_freshness:
            findings.append(
                Finding(
                    "WARN",
                    "SRC-NO-FRESHNESS",
                    uid,
                    "source declares no freshness threshold, so a source that "
                    "stops arriving reports nothing; freshness is the only "
                    "instrument that asserts on arrival rather than content",
                )
            )
        elif not src.get("loaded_at_field") and not (
            isinstance(src.get("config"), dict)
            and src["config"].get("loaded_at_field")
        ):
            findings.append(
                Finding(
                    "WARN",
                    "SRC-FRESHNESS-NO-FIELD",
                    uid,
                    "freshness is configured but no loaded_at_field is set; "
                    "unless the adapter supports metadata-based freshness this "
                    "check cannot evaluate",
                )
            )
    return findings


def check_staging(manifest, models):
    findings = []
    for uid, node in models.items():
        if not in_layer(node, STAGING_DIRS):
            continue
        parents = depends_on(node)
        sources = [p for p in parents if p.startswith("source.")]
        refs = [p for p in parents if p.startswith("model.")]

        if len(parents) > 1 and not is_base_model(node):
            findings.append(
                Finding(
                    "FAIL",
                    "STG-JOIN",
                    uid,
                    "staging model depends on {} upstreams, so it is joining; "
                    "staging is documented as 1-to-1 with a source table. Move "
                    "the join to intermediate, or make this a base model in a "
                    "base/ subdirectory".format(len(parents)),
                )
            )
        if len(sources) > 1:
            findings.append(
                Finding(
                    "FAIL",
                    "STG-MULTI-SOURCE",
                    uid,
                    "staging model reads {} different sources; cross-system "
                    "integration belongs in the conformed layer, not in "
                    "staging".format(len(sources)),
                )
            )
        if refs and not is_base_model(node):
            findings.append(
                Finding(
                    "WARN",
                    "STG-REFS-MODEL",
                    uid,
                    "staging model refs another model rather than a source; "
                    "staging is the only place the source macro should be used",
                )
            )
        materialized = config_of(node).get("materialized")
        if materialized and materialized not in ("view", "ephemeral"):
            findings.append(
                Finding(
                    "WARN",
                    "STG-NOT-VIEW",
                    uid,
                    "staging model is materialized as '{}'; the documented "
                    "default is view, so downstream models compose the freshest "
                    "data and the warehouse is not filled with models no "
                    "consumer queries".format(sanitize(materialized)),
                )
            )
    return findings


def check_marts(manifest, models):
    findings = []
    for uid, node in models.items():
        if not in_layer(node, MART_DIRS):
            continue
        direct_sources = [p for p in depends_on(node) if p.startswith("source.")]
        if direct_sources:
            findings.append(
                Finding(
                    "FAIL",
                    "MART-FROM-SOURCE",
                    uid,
                    "mart selects directly from {} source(s), bypassing "
                    "staging; the source's shape is now coupled to a "
                    "business-facing model and a source change breaks it "
                    "without warning".format(len(direct_sources)),
                )
            )
    return findings


def check_tests(manifest, models):
    findings = []
    tested = tested_node_ids(manifest)
    for uid, node in models.items():
        if config_of(node).get("materialized") == "ephemeral":
            continue
        if uid not in tested:
            findings.append(
                Finding(
                    "WARN",
                    "MODEL-NO-TESTS",
                    uid,
                    "model has no data tests; nothing here can fail, and a "
                    "check that cannot fail is indistinguishable from a pass",
                )
            )
    return findings


def check_incremental(manifest, models):
    findings = []
    for uid, node in models.items():
        cfg = config_of(node)
        if cfg.get("materialized") != "incremental":
            continue

        strategy = cfg.get("incremental_strategy")
        unique_key = cfg.get("unique_key")
        on_schema_change = cfg.get("on_schema_change")

        if not strategy:
            findings.append(
                Finding(
                    "WARN",
                    "INC-NO-STRATEGY",
                    uid,
                    "incremental model sets no incremental_strategy, so it "
                    "inherits an adapter default that differs across adapters "
                    "and versions; set it explicitly",
                )
            )

        if strategy and str(strategy).lower() in KEYED_STRATEGIES and not unique_key:
            findings.append(
                Finding(
                    "FAIL",
                    "INC-NO-UNIQUE-KEY",
                    uid,
                    "strategy '{}' needs a unique_key to identify the row to "
                    "update; without one it appends and duplicates on every "
                    "overlapping run".format(sanitize(strategy)),
                )
            )

        if isinstance(unique_key, str) and re.search(r"[(|]|\bconcat\b", unique_key, re.I):
            findings.append(
                Finding(
                    "WARN",
                    "INC-KEY-EXPRESSION",
                    uid,
                    "unique_key looks like a SQL expression; the documented "
                    "form is a list of column names, which dbt templates per "
                    "database",
                )
            )

        if str(strategy).lower() == "insert_overwrite" and not (
            cfg.get("partition_by") or cfg.get("partitions")
        ):
            findings.append(
                Finding(
                    "FAIL",
                    "INC-OVERWRITE-NO-PARTITION",
                    uid,
                    "insert_overwrite with no partition_by overwrites the "
                    "ENTIRE table each run; if that is intended, a table "
                    "materialization states it honestly",
                )
            )

        if on_schema_change in (None, "ignore"):
            findings.append(
                Finding(
                    "WARN",
                    "INC-SCHEMA-CHANGE-IGNORE",
                    uid,
                    "on_schema_change is unset or 'ignore', so a new upstream "
                    "column never appears here and a removed one fails the "
                    "run; neither outcome is announced at design time",
                )
            )

        event_time = cfg.get("event_time")
        if event_time and looks_like_arrival(event_time):
            findings.append(
                Finding(
                    "FAIL",
                    "INC-ARRIVAL-AS-EVENT",
                    uid,
                    "event_time '{}' is named like an arrival or load "
                    "timestamp, not a business event time; a row backdated "
                    "into a closed period is then invisible at any window "
                    "width".format(sanitize(event_time)),
                )
            )

        if str(strategy).lower() == "microbatch":
            if not event_time:
                findings.append(
                    Finding(
                        "FAIL",
                        "INC-MICROBATCH-NO-EVENT-TIME",
                        uid,
                        "microbatch requires event_time to generate its batch "
                        "predicates",
                    )
                )
            if not cfg.get("begin"):
                findings.append(
                    Finding(
                        "WARN",
                        "INC-MICROBATCH-NO-BEGIN",
                        uid,
                        "microbatch sets no begin; dbt does not probe the "
                        "minimum event_time, so history before the default "
                        "start is never processed",
                    )
                )
            for parent in depends_on(node):
                upstream = manifest.get("nodes", {}).get(parent)
                if isinstance(upstream, dict) and not config_of(upstream).get(
                    "event_time"
                ):
                    findings.append(
                        Finding(
                            "WARN",
                            "INC-MICROBATCH-UPSTREAM-NO-EVENT-TIME",
                            uid,
                            "upstream '{}' declares no event_time, so it is "
                            "not auto-filtered and every batch scans it in "
                            "full".format(sanitize(parent)),
                        )
                    )
    return findings


def check_snapshots(manifest):
    findings = []
    for uid, node in manifest.get("nodes", {}).items():
        if not isinstance(node, dict) or node.get("resource_type") != "snapshot":
            continue
        path = path_of(node).lower()
        parts = [p for p in path.split("/") if p]
        if any(p == "models" for p in parts[:-1]):
            findings.append(
                Finding(
                    "WARN",
                    "SNAP-IN-MODELS",
                    uid,
                    "snapshot lives under models/; snapshots build history and "
                    "are not rebuildable, so co-locating them with rebuildable "
                    "models invites a destructive full refresh",
                )
            )
        cfg = config_of(node)
        strategy = cfg.get("strategy")
        if strategy == "timestamp" and not cfg.get("updated_at"):
            findings.append(
                Finding(
                    "FAIL",
                    "SNAP-TIMESTAMP-NO-UPDATED-AT",
                    uid,
                    "timestamp strategy requires updated_at",
                )
            )
        if cfg.get("updated_at") and looks_like_arrival(cfg.get("updated_at")):
            findings.append(
                Finding(
                    "WARN",
                    "SNAP-ARRIVAL-AS-UPDATED-AT",
                    uid,
                    "updated_at '{}' is named like a load timestamp; if it "
                    "moves on every reload the snapshot records versions that "
                    "did not happen".format(sanitize(cfg.get("updated_at"))),
                )
            )
    return findings


def check_materialization_drift(manifest, previous):
    """Compare against an earlier manifest for silent materialization changes."""
    findings = []
    old_models = models_of(previous)
    for uid, node in models_of(manifest).items():
        old = old_models.get(uid)
        if not old:
            continue
        was = config_of(old).get("materialized")
        now = config_of(node).get("materialized")
        if was and now and was != now:
            level = "FAIL" if was == "incremental" or now == "incremental" else "WARN"
            findings.append(
                Finding(
                    level,
                    "MAT-CHANGED",
                    uid,
                    "materialization changed from '{}' to '{}'; a change into "
                    "or out of incremental needs a full refresh, and without "
                    "one the table keeps rows built under the old "
                    "semantics".format(sanitize(was), sanitize(now)),
                )
            )
    return findings


def audit(manifest, previous=None):
    models = models_of(manifest)
    findings = []
    findings.extend(check_sources(manifest))
    findings.extend(check_staging(manifest, models))
    findings.extend(check_marts(manifest, models))
    findings.extend(check_tests(manifest, models))
    findings.extend(check_incremental(manifest, models))
    findings.extend(check_snapshots(manifest))
    if previous is not None:
        findings.extend(check_materialization_drift(manifest, previous))
    order = {"FAIL": 0, "WARN": 1}
    findings.sort(key=lambda f: (order.get(f.level, 2), f.code, f.node))
    return findings


def render_text(findings, manifest):
    lines = []
    meta = manifest.get("metadata")
    if isinstance(meta, dict):
        version = sanitize(meta.get("dbt_version", "unknown"))
        schema = sanitize(meta.get("dbt_schema_version", "unknown"))
        lines.append("manifest: dbt {} / schema {}".format(version, schema))
    if not findings:
        lines.append("No mechanical faults found.")
        lines.append(
            "This reads structure, not data. It cannot tell you whether a key "
            "is unique or whether the numbers are right."
        )
        return "\n".join(lines)
    for finding in findings:
        lines.append(str(finding))
    fails = sum(1 for f in findings if f.level == "FAIL")
    warns = len(findings) - fails
    lines.append("")
    lines.append("{} FAIL, {} WARN".format(fails, warns))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Audit a dbt project from its manifest.json."
    )
    parser.add_argument("manifest", help="path to target/manifest.json")
    parser.add_argument(
        "--compare",
        metavar="OLD_MANIFEST",
        help="an earlier manifest, to detect materialization changes",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(args.manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        sys.stderr.write("could not read manifest: {}\n".format(exc))
        return 2

    previous = None
    if args.compare:
        try:
            previous = load_manifest(args.compare)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            sys.stderr.write("could not read comparison manifest: {}\n".format(exc))
            return 2

    findings = audit(manifest, previous)

    if args.json:
        payload = {
            "findings": [f.as_dict() for f in findings],
            "fail_count": sum(1 for f in findings if f.level == "FAIL"),
            "warn_count": sum(1 for f in findings if f.level != "FAIL"),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(render_text(findings, manifest))

    return 1 if any(f.level == "FAIL" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
