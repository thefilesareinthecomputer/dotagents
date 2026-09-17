"""Auditor precision and recall on manifest fixtures.

Level 3 of the testing strategy. Recall is the easy half: each defective
fixture must produce the code it was built to trip. Precision is the half that
decides whether the checker survives contact with a real analysis, so every
assertion here is exact rather than a membership test - a fixture that trips
its own code plus one extra fails, because a checker that cries wolf gets
muted and then nothing is checked at all.

Each defective fixture is the clean manifest with exactly one defect
introduced, so any second code in its report is a false positive by
construction.
"""

import json
import pathlib
import sys
import tempfile
import unittest

TESTS = pathlib.Path(__file__).resolve().parent
FIXTURES = TESTS / "fixtures"
sys.path.insert(0, str(TESTS.parent / "scripts"))

import stats_check  # noqa: E402


class AuditorFixtures(unittest.TestCase):

    def audit(self, name):
        return stats_check.audit_path(str(FIXTURES / name))

    def assert_only(self, name, code, severity="error"):
        """The fixture trips its own code, once, and nothing else."""
        findings = self.audit(name)
        self.assertEqual([f.code for f in findings], [code],
                         msg=f"{name} reported {[f.code for f in findings]}")
        finding = findings[0]
        self.assertEqual(finding.severity, severity)
        self.assertTrue(finding.where.strip(), "a finding must say where it sits")
        self.assertTrue(finding.message.strip(), "a finding must say what is wrong")
        self.assertTrue(finding.fix.strip(), "a finding must say what to do instead")

    # -- precision ---------------------------------------------------------

    def test_clean_manifest_is_clean(self):
        self.assertEqual(self.audit("manifest_clean.json"), [])

    def test_unknown_keys_are_tolerated_not_rejected(self):
        """The auditor reports what is present; it does not police the schema."""
        with open(FIXTURES / "manifest_clean.json", encoding="utf-8") as handle:
            manifest = json.load(handle)
        manifest["provenance"] = {"pipeline": "nightly", "version": "2.1"}
        manifest["data"]["partition"] = "2024-Q3"
        manifest["results"][0]["bootstrap_reps"] = 10000
        manifest["results"][0]["extra"] = {"anything": [1, 2, 3]}
        self.assertEqual(stats_check.audit(manifest), [])

    def test_a_missing_optional_block_is_not_a_defect(self):
        """Absent is not the same as wrong: what it cannot see, it does not accuse."""
        with open(FIXTURES / "manifest_clean.json", encoding="utf-8") as handle:
            manifest = json.load(handle)
        for key in ("backend", "comparisons", "design", "notes", "tool"):
            manifest.pop(key)
        self.assertEqual(stats_check.audit(manifest), [])

    # -- recall ------------------------------------------------------------

    def test_p_value_without_effect_size(self):
        self.assert_only("manifest_p_value_without_effect_size.json",
                         "P_VALUE_WITHOUT_EFFECT_SIZE")

    def test_missing_interval(self):
        self.assert_only("manifest_missing_interval.json", "MISSING_INTERVAL")

    def test_missing_n(self):
        self.assert_only("manifest_missing_n.json", "MISSING_N")

    def test_uncorrected_multiplicity(self):
        self.assert_only("manifest_uncorrected_multiplicity.json",
                         "UNCORRECTED_MULTIPLICITY")

    def test_in_sample_as_performance(self):
        self.assert_only("manifest_in_sample_as_performance.json",
                         "IN_SAMPLE_AS_PERFORMANCE")

    def test_causal_language_observational(self):
        self.assert_only("manifest_causal_language_observational.json",
                         "CAUSAL_LANGUAGE_OBSERVATIONAL")

    def test_silent_row_drops(self):
        self.assert_only("manifest_silent_row_drops.json", "SILENT_ROW_DROPS")

    def test_unseeded_resampling(self):
        self.assert_only("manifest_unseeded_resampling.json", "UNSEEDED_RESAMPLING")

    def test_degenerate_spread(self):
        self.assert_only("manifest_degenerate_spread.json", "DEGENERATE_SPREAD")

    def test_missing_assumption_is_a_warning_not_an_error(self):
        self.assert_only("manifest_missing_assumption.json", "MISSING_ASSUMPTION",
                         severity="warning")

    def test_manifest_unreadable(self):
        self.assert_only("manifest_manifest_unreadable.json", "MANIFEST_UNREADABLE")

    def test_valid_json_that_is_not_an_object_is_unreadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "list.json"
            path.write_text('[{"n": 10}]\n', encoding="utf-8")
            findings = stats_check.audit_path(str(path))
        self.assertEqual([f.code for f in findings], ["MANIFEST_UNREADABLE"])

    def test_a_file_that_does_not_exist_is_unreadable_not_a_crash(self):
        findings = stats_check.audit_path(str(FIXTURES / "no_such_manifest.json"))
        self.assertEqual([f.code for f in findings], ["MANIFEST_UNREADABLE"])


class ExitCodes(unittest.TestCase):
    """The exit code is what a pipeline reads, so it is part of the contract."""

    def run_main(self, *argv):
        import contextlib
        import io
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = stats_check.main(list(argv))
        return code, buffer.getvalue()

    def test_clean_exits_zero(self):
        code, out = self.run_main(str(FIXTURES / "manifest_clean.json"))
        self.assertEqual(code, 0)
        self.assertIn("0 findings", out)

    def test_an_error_exits_one(self):
        code, _ = self.run_main(str(FIXTURES / "manifest_missing_n.json"))
        self.assertEqual(code, 1)

    def test_a_warning_alone_exits_zero_until_asked_otherwise(self):
        path = str(FIXTURES / "manifest_missing_assumption.json")
        self.assertEqual(self.run_main(path)[0], 0)
        self.assertEqual(self.run_main(path, "--warnings-as-errors")[0], 1)

    def test_an_unreadable_manifest_exits_two(self):
        code, _ = self.run_main(str(FIXTURES / "manifest_manifest_unreadable.json"))
        self.assertEqual(code, 2)

    def test_json_output_carries_every_finding_and_its_counts(self):
        code, out = self.run_main("--json",
                                  str(FIXTURES / "manifest_silent_row_drops.json"))
        payload = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual(payload["counts"], {"error": 1, "warning": 0})
        self.assertEqual([f["code"] for f in payload["reports"][0]["findings"]],
                         ["SILENT_ROW_DROPS"])


if __name__ == "__main__":
    unittest.main()
