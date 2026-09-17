"""Tests for scripts/ml_check.py.

Run from skills/machine-learning/:

    python3 -m unittest discover -s tests

Fixtures are never executed. They are read as text by the checker and by
nothing else, which is the same guarantee the checker gives its users.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "ml_check.py"
FIXTURES = SKILL / "tests" / "fixtures"
CLEAN = FIXTURES / "clean"
DEFECTIVE = FIXTURES / "defective"
MALFORMED = FIXTURES / "malformed"

sys.path.insert(0, str(SKILL / "scripts"))
import ml_check  # noqa: E402


def codes(path):
    return sorted(f.code for f in ml_check.check_file(path))


def findings(path):
    return ml_check.check_file(path)


# Every catalog code, its defective fixture, and the severity it must carry.
CATALOG = {
    "FIT_BEFORE_SPLIT": ("fit_before_split.py", ml_check.ERROR),
    "TEST_USED_IN_TUNING": ("test_used_in_tuning.py", ml_check.WARNING),
    "NO_RANDOM_STATE": ("no_random_state.py", ml_check.WARNING),
    "TARGET_IN_FEATURES": ("target_in_features.py", ml_check.WARNING),
    "NO_BASELINE": ("no_baseline.py", ml_check.WARNING),
    "TEMPORAL_SPLIT_MISSING": ("temporal_split_missing.py", ml_check.ERROR),
    "RESAMPLE_BEFORE_SPLIT": ("resample_before_split.py", ml_check.WARNING),
    "METRIC_MISMATCH": ("metric_mismatch.py", ml_check.WARNING),
    "GROUP_LEAK": ("group_leak.py", ml_check.WARNING),
}


class TestCatalogCoverage(unittest.TestCase):
    """Recall: each defective fixture must produce its own code and no other."""

    def test_every_catalog_code_has_a_fixture(self):
        for code, (name, _) in CATALOG.items():
            with self.subTest(code=code):
                self.assertTrue((DEFECTIVE / name).exists(), f"missing fixture for {code}")

    def test_each_defective_fixture_produces_only_its_own_code(self):
        for code, (name, _) in CATALOG.items():
            with self.subTest(code=code):
                found = set(codes(DEFECTIVE / name))
                self.assertEqual(found, {code})

    def test_severities_match_the_catalog(self):
        for code, (name, severity) in CATALOG.items():
            with self.subTest(code=code):
                for f in findings(DEFECTIVE / name):
                    self.assertEqual(f.severity, severity)

    def test_only_two_codes_are_errors(self):
        errors = {c for c, (_, sev) in CATALOG.items() if sev == ml_check.ERROR}
        self.assertEqual(errors, {"FIT_BEFORE_SPLIT", "TEMPORAL_SPLIT_MISSING"})

    def test_every_finding_carries_a_fix(self):
        for name, _ in CATALOG.values():
            for f in findings(DEFECTIVE / name):
                self.assertTrue(f.fix.strip(), f"{f.code} has no fix text")
                self.assertGreater(f.line, 0)


class TestFalsePositives(unittest.TestCase):
    """Precision. The clean fixtures are the false-positive gate: a checker
    that fires on correct code gets muted, and a muted checker protects nothing.
    """

    def test_clean_fixtures_are_completely_silent(self):
        for path in sorted(CLEAN.glob("*.py")):
            with self.subTest(fixture=path.name):
                self.assertEqual(findings(path), [])

    def test_every_catalog_code_has_a_clean_counter_fixture(self):
        # Which clean fixture is the meaningful counter for which code. Each
        # names a file that contains the ingredients of the defect and handles
        # them correctly, so silence there is evidence rather than absence.
        counters = {
            "FIT_BEFORE_SPLIT": ["clean_baseline.py", "clean_pipeline.py"],
            "TEST_USED_IN_TUNING": ["clean_pipeline.py"],
            "NO_RANDOM_STATE": ["clean_baseline.py", "clean_temporal.py"],
            "TARGET_IN_FEATURES": ["clean_baseline.py", "clean_grouped.py"],
            "NO_BASELINE": ["clean_baseline.py", "clean_temporal.py"],
            "TEMPORAL_SPLIT_MISSING": ["clean_temporal.py"],
            "RESAMPLE_BEFORE_SPLIT": ["clean_pipeline.py"],
            "METRIC_MISMATCH": ["clean_imbalanced.py", "clean_baseline.py"],
            "GROUP_LEAK": ["clean_grouped.py"],
        }
        self.assertEqual(set(counters), set(CATALOG))
        for code, names in counters.items():
            for name in names:
                with self.subTest(code=code, fixture=name):
                    path = CLEAN / name
                    self.assertTrue(path.exists())
                    self.assertNotIn(code, codes(path))

    def test_the_checker_does_not_fire_on_itself(self):
        self.assertEqual(findings(SCRIPT), [])

    def test_kfold_without_shuffle_needs_no_seed(self):
        self.assertEqual(self.run_source("from sklearn.model_selection import KFold\n"
                                         "cv = KFold(n_splits=5)\n"), [])

    def test_kfold_with_shuffle_needs_a_seed(self):
        self.assertEqual(self.run_source("from sklearn.model_selection import KFold\n"
                                         "cv = KFold(n_splits=5, shuffle=True)\n"),
                         ["NO_RANDOM_STATE"])

    def test_scoring_the_test_split_is_not_tuning_on_it(self):
        source = ("from sklearn.model_selection import train_test_split\n"
                  "a, b, c, d = train_test_split(X, y, random_state=1)\n"
                  "model.fit(a, c)\n"
                  "print(model.score(b, d))\n")
        self.assertNotIn("TEST_USED_IN_TUNING", self.run_source(source))

    def test_popped_target_is_not_in_the_features(self):
        source = ("y = frame.pop('churned')\n"
                  "X = frame\n")
        self.assertNotIn("TARGET_IN_FEATURES", self.run_source(source))

    def test_a_dropped_id_column_is_not_a_group_leak(self):
        source = ("from sklearn.model_selection import train_test_split\n"
                  "y = frame['churned']\n"
                  "X = frame.drop(columns=['churned', 'customer_id'])\n"
                  "a, b, c, d = train_test_split(X, y, random_state=1)\n")
        self.assertNotIn("GROUP_LEAK", self.run_source(source))

    def test_a_kept_id_column_is_a_group_leak(self):
        source = ("from sklearn.model_selection import train_test_split\n"
                  "y = frame['churned']\n"
                  "X = frame.drop(columns=['churned'])\n"
                  "print(frame['customer_id'].nunique())\n"
                  "a, b, c, d = train_test_split(X, y, random_state=1)\n")
        self.assertIn("GROUP_LEAK", self.run_source(source))

    def test_a_docstring_mentioning_a_baseline_is_not_a_baseline(self):
        source = ('"""Scores the model against no baseline at all."""\n'
                  "from sklearn.metrics import accuracy_score, f1_score\n"
                  "print(accuracy_score(y_true, y_pred), f1_score(y_true, y_pred))\n")
        self.assertIn("NO_BASELINE", self.run_source(source))

    def test_a_manual_cutoff_split_counts_as_temporal(self):
        source = ("import pandas as pd\n"
                  "frame['event_date'] = pd.to_datetime(frame['event_date'])\n"
                  "train = frame[frame['event_date'] < '2024-01-01']\n"
                  "test = frame[frame['event_date'] >= '2024-01-01']\n")
        self.assertNotIn("TEMPORAL_SPLIT_MISSING", self.run_source(source))

    def run_source(self, source):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snippet.py"
            path.write_text(source, encoding="utf-8")
            return sorted(f.code for f in ml_check.check_file(path))


class TestNotebooks(unittest.TestCase):
    def test_clean_notebook_carries_only_the_ordering_note(self):
        found = findings(CLEAN / "clean_notebook.ipynb")
        self.assertEqual([f.code for f in found], ["NOTEBOOK_ORDER"])
        self.assertEqual(found[0].severity, ml_check.NOTE)

    def test_markdown_and_magics_do_not_break_the_parse(self):
        found = findings(CLEAN / "clean_notebook.ipynb")
        self.assertNotIn("PARSE_ERROR", [f.code for f in found])

    def test_ordering_findings_downgrade_to_warning_in_a_notebook(self):
        found = {f.code: f for f in findings(DEFECTIVE / "notebook_fit_before_split.ipynb")}
        self.assertIn("FIT_BEFORE_SPLIT", found)
        self.assertEqual(found["FIT_BEFORE_SPLIT"].severity, ml_check.WARNING)
        self.assertEqual(found["NOTEBOOK_ORDER"].severity, ml_check.NOTE)

    def test_the_same_defect_is_an_error_in_a_module(self):
        found = {f.code: f for f in findings(DEFECTIVE / "fit_before_split.py")}
        self.assertEqual(found["FIT_BEFORE_SPLIT"].severity, ml_check.ERROR)

    def test_a_notebook_finding_names_its_cell(self):
        found = {f.code: f for f in findings(DEFECTIVE / "notebook_fit_before_split.ipynb")}
        self.assertIn("[cell ", found["FIT_BEFORE_SPLIT"].message)

    def test_a_notebook_with_no_code_cells_reports_nothing(self):
        self.assertEqual(findings(MALFORMED / "markdown_only.ipynb"), [])


class TestParseRobustness(unittest.TestCase):
    def test_malformed_python_is_an_error_not_a_traceback(self):
        found = findings(MALFORMED / "broken_syntax.py")
        self.assertEqual([f.code for f in found], ["PARSE_ERROR"])
        self.assertEqual(found[0].severity, ml_check.ERROR)
        self.assertIn("Not analyzed", found[0].message)

    def test_the_parse_error_names_the_running_interpreter(self):
        message = findings(MALFORMED / "broken_syntax.py")[0].message
        self.assertIn(".".join(str(p) for p in sys.version_info[:3]), message)

    def test_syntax_newer_than_the_interpreter_never_reads_as_clean(self):
        # PEP 695 generics parse on 3.12 and later and fail before that. Either
        # outcome is acceptable; a traceback or a silent skip is not.
        found = findings(MALFORMED / "future_syntax.py")
        if sys.version_info < (3, 12):
            self.assertEqual([f.code for f in found], ["PARSE_ERROR"])
            self.assertIn("newer than this interpreter", found[0].message)
        else:
            self.assertEqual(found, [])

    def test_invalid_notebook_json_is_an_error(self):
        found = findings(MALFORMED / "not_json.ipynb")
        self.assertEqual([f.code for f in found], ["PARSE_ERROR"])
        self.assertIn("notebook JSON", found[0].message)

    def test_an_empty_file_is_clean(self):
        self.assertEqual(findings(MALFORMED / "empty.py"), [])

    def test_a_missing_path_is_reported_rather_than_crashing(self):
        targets, missing = ml_check.iter_targets(["does/not/exist.py"], False)
        self.assertEqual(targets, [])
        self.assertEqual(missing, ["does/not/exist.py"])

    def test_a_file_above_the_size_limit_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "huge.py"
            path.write_text("x = 1\n" * 400_000, encoding="utf-8")
            found = findings(path)
        self.assertEqual([f.code for f in found], ["PARSE_ERROR"])
        self.assertIn("byte limit", found[0].message)

    def test_non_utf8_bytes_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "latin.py"
            path.write_bytes(b"x = '\xff\xfe'\n")
            found = findings(path)
        self.assertEqual([f.code for f in found], ["PARSE_ERROR"])
        self.assertIn("UTF-8", found[0].message)

    def test_control_characters_in_a_path_are_stripped_from_output(self):
        self.assertEqual(ml_check.safe("train\n.py"), "train?.py")


class TestFindingShape(unittest.TestCase):
    def test_findings_are_frozen(self):
        f = findings(DEFECTIVE / "no_baseline.py")[0]
        with self.assertRaises(FrozenInstanceError):
            f.code = "OTHER"

    def test_field_order_is_the_documented_one(self):
        f = findings(DEFECTIVE / "no_baseline.py")[0]
        self.assertEqual(
            list(f.__dataclass_fields__),
            ["code", "severity", "file", "line", "message", "fix"],
        )


def cli(*args):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=str(SKILL), timeout=120,
    )
    return proc.returncode, proc.stdout, proc.stderr


class TestCommandLine(unittest.TestCase):
    def test_clean_directory_exits_zero(self):
        code, out, _ = cli(str(CLEAN))
        self.assertEqual(code, 0, out)
        self.assertIn("clean", out)

    def test_an_error_exits_one(self):
        code, out, _ = cli(str(DEFECTIVE / "fit_before_split.py"))
        self.assertEqual(code, 1)
        self.assertIn("FIT_BEFORE_SPLIT", out)

    def test_warnings_alone_exit_zero(self):
        code, _, _ = cli(str(DEFECTIVE / "no_baseline.py"))
        self.assertEqual(code, 0)

    def test_warnings_as_errors_exits_one(self):
        code, _, _ = cli(str(DEFECTIVE / "no_baseline.py"), "--warnings-as-errors")
        self.assertEqual(code, 1)

    def test_a_note_alone_never_fails_the_run(self):
        code, out, _ = cli(str(CLEAN / "clean_notebook.ipynb"), "--warnings-as-errors")
        self.assertEqual(code, 0, out)
        self.assertIn("NOTEBOOK_ORDER", out)

    def test_json_shape(self):
        code, out, _ = cli(str(DEFECTIVE), "--json")
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertEqual(set(payload), {"files", "counts", "findings"})
        self.assertEqual(set(payload["counts"]), {"error", "warning", "note"})
        for finding in payload["findings"]:
            self.assertEqual(
                set(finding), {"code", "severity", "file", "line", "message", "fix"})
            self.assertIn(finding["severity"], {"error", "warning", "note"})
        found = {f["code"] for f in payload["findings"]}
        # The directory holds a defective notebook too, so the ordering note
        # rides along with the nine catalog codes.
        self.assertEqual(found, set(CATALOG) | {"NOTEBOOK_ORDER"})

    def test_json_output_is_stable_across_runs(self):
        first = cli(str(DEFECTIVE), "--json")[1]
        second = cli(str(DEFECTIVE), "--json")[1]
        self.assertEqual(first, second)

    def test_recursive_reaches_nested_files_and_the_default_does_not(self):
        shallow = json.loads(cli(str(FIXTURES), "--json")[1])["files"]
        deep = json.loads(cli(str(FIXTURES), "--recursive", "--json")[1])["files"]
        self.assertEqual(shallow, 0)
        self.assertGreaterEqual(deep, 15)

    def test_a_missing_path_exits_one_with_a_message(self):
        code, out, _ = cli("no/such/file.py")
        self.assertEqual(code, 1)
        self.assertIn("does not exist", out)

    def test_the_checker_imports_nothing_outside_the_standard_library(self):
        # Success criterion 3 - it must run in a bare environment. `-I` isolates
        # the interpreter from PYTHONPATH and user site-packages, so an import
        # of pandas or sklearn would fail here.
        proc = subprocess.run(
            [sys.executable, "-I", str(SCRIPT), str(CLEAN)],
            capture_output=True, text=True, cwd=str(SKILL), timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_no_fixture_is_ever_executed(self):
        # The defective fixtures import xgboost and imblearn and read csv files
        # that do not exist. Running one would raise; the checker reports on all
        # of them and exits on findings alone.
        code, out, err = cli(str(DEFECTIVE))
        self.assertEqual(code, 1)
        self.assertEqual(err, "")
        self.assertNotIn("Traceback", out)


if __name__ == "__main__":
    unittest.main()
