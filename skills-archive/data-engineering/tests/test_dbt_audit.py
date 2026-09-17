"""Tests for dbt_audit.py: unit, integration and end-to-end.

Run from the skill root:
    python3 -m unittest discover -s tests
"""

import copy
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_ROOT, "scripts"))

import dbt_audit  # noqa: E402

GOOD = os.path.join(SKILL_ROOT, "tests", "fixtures", "good", "manifest.json")
BAD = os.path.join(SKILL_ROOT, "tests", "fixtures", "bad", "manifest.json")


def run_cli(args):
    """Drive main() the way a user does and capture what they would see."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = dbt_audit.main(args)
    return code, out.getvalue(), err.getvalue()


class TestSanitize(unittest.TestCase):
    def test_strips_control_characters(self):
        self.assertEqual(dbt_audit.sanitize("model\x00.a\x1bb"), "model.ab")

    def test_strips_non_ascii(self):
        self.assertEqual(dbt_audit.sanitize("modél中x"), "modlx")

    def test_bounds_length(self):
        self.assertEqual(len(dbt_audit.sanitize("a" * 500)), dbt_audit.MAX_IDENT)

    def test_coerces_non_string(self):
        self.assertEqual(dbt_audit.sanitize(42), "42")

    def test_preserves_ordinary_identifier(self):
        self.assertEqual(
            dbt_audit.sanitize("model.proj.stg_crm__customers"),
            "model.proj.stg_crm__customers",
        )


class TestPathHelpers(unittest.TestCase):
    def test_path_prefers_original_file_path(self):
        node = {"original_file_path": "models/staging/a.sql", "path": "other.sql"}
        self.assertEqual(dbt_audit.path_of(node), "models/staging/a.sql")

    def test_path_falls_back_and_normalises_separators(self):
        node = {"path": "models\\staging\\a.sql"}
        self.assertEqual(dbt_audit.path_of(node), "models/staging/a.sql")

    def test_path_of_missing_is_empty(self):
        self.assertEqual(dbt_audit.path_of({}), "")

    def test_in_layer_matches_directory(self):
        node = {"original_file_path": "models/staging/crm/stg_x.sql"}
        self.assertTrue(dbt_audit.in_layer(node, dbt_audit.STAGING_DIRS))

    def test_in_layer_ignores_the_filename(self):
        """A model named staging.sql outside a staging dir is not staging."""
        node = {"original_file_path": "models/marts/staging.sql"}
        self.assertFalse(dbt_audit.in_layer(node, dbt_audit.STAGING_DIRS))

    def test_in_layer_is_case_insensitive(self):
        node = {"original_file_path": "models/Staging/crm/stg_x.sql"}
        self.assertTrue(dbt_audit.in_layer(node, dbt_audit.STAGING_DIRS))

    def test_base_model_detected_by_prefix_and_directory(self):
        self.assertTrue(
            dbt_audit.is_base_model({"original_file_path": "models/staging/crm/base/b.sql"})
        )
        self.assertTrue(
            dbt_audit.is_base_model(
                {"original_file_path": "models/staging/crm/base_customers.sql"}
            )
        )
        self.assertFalse(
            dbt_audit.is_base_model({"original_file_path": "models/staging/crm/stg_c.sql"})
        )


class TestArrivalNames(unittest.TestCase):
    def test_arrival_names_detected(self):
        for name in [
            "_loaded_at",
            "dw_loaded_at",
            "ingested_at",
            "synced_at",
            "inserted_at",
            "etl_timestamp",
            "extracted_at",
        ]:
            self.assertTrue(dbt_audit.looks_like_arrival(name), name)

    def test_business_event_names_not_flagged(self):
        for name in [
            "invoiced_at",
            "order_date",
            "event_timestamp",
            "occurred_at",
            "posted_date",
            "source_modified_at",
        ]:
            self.assertFalse(dbt_audit.looks_like_arrival(name), name)


class TestMalformedNodes(unittest.TestCase):
    """The manifest is untrusted input; malformed shapes must not raise."""

    def test_config_of_tolerates_bad_types(self):
        self.assertEqual(dbt_audit.config_of({"config": None}), {})
        self.assertEqual(dbt_audit.config_of({"config": "nope"}), {})
        self.assertEqual(dbt_audit.config_of({}), {})

    def test_depends_on_tolerates_bad_types(self):
        self.assertEqual(dbt_audit.depends_on({"depends_on": None}), [])
        self.assertEqual(dbt_audit.depends_on({"depends_on": {"nodes": "x"}}), [])
        self.assertEqual(dbt_audit.depends_on({}), [])

    def test_audit_survives_non_dict_node_entries(self):
        manifest = {"nodes": {"model.a": "not a dict", "model.b": None}, "sources": {}}
        self.assertEqual(dbt_audit.audit(manifest), [])


class TestLoadManifest(unittest.TestCase):
    def test_loads_good_fixture(self):
        manifest = dbt_audit.load_manifest(GOOD)
        self.assertIn("nodes", manifest)

    def test_rejects_non_object_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "m.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump([1, 2, 3], handle)
            with self.assertRaises(ValueError):
                dbt_audit.load_manifest(path)

    def test_rejects_object_without_nodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "m.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"metadata": {}}, handle)
            with self.assertRaises(ValueError):
                dbt_audit.load_manifest(path)


class TestGoodFixture(unittest.TestCase):
    def test_good_fixture_is_silent(self):
        """A correct project must produce nothing at all, or the tool is noise."""
        findings = dbt_audit.audit(dbt_audit.load_manifest(GOOD))
        self.assertEqual(
            findings, [], "unexpected findings: {}".format([str(f) for f in findings])
        )

    def test_ephemeral_model_exempt_from_test_requirement(self):
        manifest = dbt_audit.load_manifest(GOOD)
        codes = {f.code for f in dbt_audit.audit(manifest)}
        self.assertNotIn("MODEL-NO-TESTS", codes)


class TestBadFixture(unittest.TestCase):
    def setUp(self):
        self.findings = dbt_audit.audit(dbt_audit.load_manifest(BAD))
        self.codes = {f.code for f in self.findings}

    def test_every_implemented_code_fires(self):
        expected = {
            "SRC-NO-FRESHNESS",
            "SRC-FRESHNESS-NO-FIELD",
            "STG-JOIN",
            "STG-MULTI-SOURCE",
            "STG-REFS-MODEL",
            "STG-NOT-VIEW",
            "MART-FROM-SOURCE",
            "MODEL-NO-TESTS",
            "INC-NO-STRATEGY",
            "INC-NO-UNIQUE-KEY",
            "INC-KEY-EXPRESSION",
            "INC-OVERWRITE-NO-PARTITION",
            "INC-SCHEMA-CHANGE-IGNORE",
            "INC-ARRIVAL-AS-EVENT",
            "INC-MICROBATCH-NO-EVENT-TIME",
            "INC-MICROBATCH-NO-BEGIN",
            "INC-MICROBATCH-UPSTREAM-NO-EVENT-TIME",
            "SNAP-IN-MODELS",
            "SNAP-TIMESTAMP-NO-UPDATED-AT",
            "SNAP-ARRIVAL-AS-UPDATED-AT",
        }
        self.assertEqual(expected - self.codes, set())

    def test_fails_are_sorted_before_warnings(self):
        levels = [f.level for f in self.findings]
        self.assertEqual(levels, sorted(levels, key=lambda l: 0 if l == "FAIL" else 1))

    def test_merge_without_key_is_a_fail_not_a_warning(self):
        match = [f for f in self.findings if f.code == "INC-NO-UNIQUE-KEY"]
        self.assertTrue(match)
        self.assertEqual(match[0].level, "FAIL")

    def test_base_model_is_exempt_from_the_join_rule(self):
        manifest = dbt_audit.load_manifest(BAD)
        node = manifest["nodes"]["model.bad_project.stg_crm__customers_joined"]
        node["original_file_path"] = "models/staging/crm/base/base_customers.sql"
        codes = {f.code for f in dbt_audit.audit(manifest)}
        self.assertNotIn("STG-JOIN", codes)
        # The multi-source rule still applies: a base model may join, but
        # cross-system integration still does not belong in staging.
        self.assertIn("STG-MULTI-SOURCE", codes)


class TestMaterializationDrift(unittest.TestCase):
    def test_no_drift_when_manifests_match(self):
        manifest = dbt_audit.load_manifest(GOOD)
        findings = dbt_audit.check_materialization_drift(manifest, copy.deepcopy(manifest))
        self.assertEqual(findings, [])

    def test_change_into_incremental_is_a_fail(self):
        current = dbt_audit.load_manifest(GOOD)
        previous = copy.deepcopy(current)
        previous["nodes"]["model.good_project.fct_invoice_line"]["config"][
            "materialized"
        ] = "table"
        findings = dbt_audit.check_materialization_drift(current, previous)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "MAT-CHANGED")
        self.assertEqual(findings[0].level, "FAIL")

    def test_change_between_non_incremental_is_a_warning(self):
        current = dbt_audit.load_manifest(GOOD)
        previous = copy.deepcopy(current)
        previous["nodes"]["model.good_project.dim_customer"]["config"][
            "materialized"
        ] = "view"
        findings = dbt_audit.check_materialization_drift(current, previous)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "WARN")

    def test_new_model_absent_from_previous_is_not_drift(self):
        current = dbt_audit.load_manifest(GOOD)
        previous = copy.deepcopy(current)
        del previous["nodes"]["model.good_project.dim_customer"]
        self.assertEqual(dbt_audit.check_materialization_drift(current, previous), [])


class TestCli(unittest.TestCase):
    def test_good_fixture_exits_zero(self):
        code, out, _ = run_cli([GOOD])
        self.assertEqual(code, 0)
        self.assertIn("No mechanical faults found", out)

    def test_good_fixture_states_its_limits(self):
        """Silence must not read as approval."""
        _, out, _ = run_cli([GOOD])
        self.assertIn("structure, not data", out)

    def test_bad_fixture_exits_one(self):
        code, out, _ = run_cli([BAD])
        self.assertEqual(code, 1)
        self.assertIn("FAIL", out)

    def test_missing_file_exits_two(self):
        code, _, err = run_cli([os.path.join(SKILL_ROOT, "no-such-manifest.json")])
        self.assertEqual(code, 2)
        self.assertIn("could not read manifest", err)

    def test_malformed_json_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "m.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{not json")
            code, _, err = run_cli([path])
        self.assertEqual(code, 2)
        self.assertIn("could not read manifest", err)

    def test_json_output_is_valid_and_counted(self):
        _, out, _ = run_cli([BAD, "--json"])
        payload = json.loads(out)
        self.assertGreater(payload["fail_count"], 0)
        self.assertEqual(
            payload["fail_count"] + payload["warn_count"], len(payload["findings"])
        )

    def test_json_output_is_byte_identical_across_runs(self):
        """Regenerating output twice must produce identical bytes."""
        _, first, _ = run_cli([BAD, "--json"])
        _, second, _ = run_cli([BAD, "--json"])
        self.assertEqual(first, second)

    def test_compare_flag_reports_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = dbt_audit.load_manifest(GOOD)
            previous["nodes"]["model.good_project.fct_invoice_line"]["config"][
                "materialized"
            ] = "table"
            old_path = os.path.join(tmp, "old.json")
            with open(old_path, "w", encoding="utf-8") as handle:
                json.dump(previous, handle)
            code, out, _ = run_cli([GOOD, "--compare", old_path])
        self.assertEqual(code, 1)
        self.assertIn("MAT-CHANGED", out)

    def test_compare_with_unreadable_manifest_exits_two(self):
        code, _, err = run_cli([GOOD, "--compare", "/no/such/old.json"])
        self.assertEqual(code, 2)
        self.assertIn("comparison manifest", err)


class TestSafety(unittest.TestCase):
    def test_script_never_executes_input(self):
        """The auditor parses a manifest; it must never evaluate one."""
        with open(os.path.join(SKILL_ROOT, "scripts", "dbt_audit.py"), "r", encoding="utf-8") as handle:
            source = handle.read()
        forbidden = [
            "exec(",
            "eval(",
            "__import__",
            "importlib",
            "subprocess",
            "os.system",
            "popen",
            "pickle",
        ]
        for token in forbidden:
            self.assertNotIn(token, source, "found {} in dbt_audit.py".format(token))

    def test_findings_are_sanitised_before_output(self):
        manifest = {
            "nodes": {
                "model.evil": {
                    "name": "evil",
                    "resource_type": "model",
                    "unique_id": "model.evil\x1b[31m\x00",
                    "original_file_path": "models/marts/evil.sql",
                    "config": {"materialized": "table"},
                    "depends_on": {"nodes": ["source.a.b"]},
                }
            },
            "sources": {},
        }
        findings = dbt_audit.audit(manifest)
        self.assertTrue(findings)
        for finding in findings:
            self.assertNotIn("\x1b", finding.node)
            self.assertNotIn("\x00", finding.node)


if __name__ == "__main__":
    unittest.main()
