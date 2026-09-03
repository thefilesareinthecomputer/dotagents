"""Tests for scripts/dim_check.py: unit, integration, and end-to-end.

Run with:
    python3 -m unittest discover skills/dimensional-data-modeling/tests
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "dim_check.py"
GOOD = SKILL / "tests" / "fixtures" / "good"
BAD = SKILL / "tests" / "fixtures" / "bad"

sys.path.insert(0, str(SKILL / "scripts"))
import dim_check  # noqa: E402


# ------------------------------------------------------------------- unit

class TestClassification(unittest.TestCase):
    def test_naming_convention_wins(self):
        for name in ("fact_sales", "fct_sales", "f_sales", "sales_fact", "FACT_SALES"):
            self.assertEqual(dim_check.classify(name), ("fact", True), name)
        for name in ("dim_customer", "d_customer", "customer_dim", "DIM_CUSTOMER"):
            self.assertEqual(dim_check.classify(name), ("dimension", True), name)

    def test_schema_qualified_and_quoted_names(self):
        self.assertEqual(dim_check.classify('gold."fact_sales"'), ("fact", True))
        self.assertEqual(dim_check.classify("[edw].[dim_date]"), ("dimension", True))

    def test_unconventional_name_is_unknown(self):
        self.assertEqual(dim_check.classify("sales_ledger"), ("unknown", False))

    def test_shape_inference(self):
        sql = """
        CREATE TABLE sales_ledger (
            date_key INT NOT NULL,
            customer_key INT NOT NULL,
            amount DECIMAL(18,2) NOT NULL
        );
        """
        table = dim_check.parse_ddl(sql, Path("x.sql"))[0]
        self.assertEqual(table.kind, "fact")
        self.assertFalse(table.by_name)


class TestDdlParsing(unittest.TestCase):
    def setUp(self):
        self.sql = """
        -- a comment mentioning NOT NULL should not matter
        CREATE TABLE IF NOT EXISTS edw.dim_thing (
            thing_key INT NOT NULL PRIMARY KEY,
            price DECIMAL(18,2) NOT NULL,   /* commas inside parens */
            label VARCHAR(50),
            CONSTRAINT fk_other FOREIGN KEY (other_key) REFERENCES dim_other (other_key)
        );
        """
        self.table = dim_check.parse_ddl(self.sql, Path("x.sql"))[0]

    def test_name_is_unqualified_and_lowercased(self):
        self.assertEqual(self.table.name, "dim_thing")

    def test_types_survive_parenthesised_arguments(self):
        types = {c.name: c.type_name for c in self.table.columns}
        self.assertEqual(types["price"], "decimal")
        self.assertEqual(types["label"], "varchar")

    def test_nullability(self):
        nullable = {c.name: c.nullable for c in self.table.columns}
        self.assertFalse(nullable["thing_key"])
        self.assertFalse(nullable["price"])
        self.assertTrue(nullable["label"])

    def test_column_level_primary_key(self):
        self.assertEqual(self.table.pk, ["thing_key"])

    def test_foreign_key_constraint_is_not_read_as_a_primary_key(self):
        self.assertNotIn("other_key", self.table.pk)

    def test_table_level_primary_key(self):
        sql = """CREATE TABLE fact_x (a INT NOT NULL, b INT NOT NULL,
                 PRIMARY KEY (a, b));"""
        self.assertEqual(dim_check.parse_ddl(sql, Path("x.sql"))[0].pk, ["a", "b"])

    def test_comments_do_not_shift_line_numbers(self):
        sql = "-- header\n\nCREATE TABLE fact_x (\n  amount FLOAT\n);"
        table = dim_check.parse_ddl(sql, Path("x.sql"))[0]
        self.assertEqual(table.line, 3)
        self.assertEqual(table.columns[0].line, 4)

    def test_identifiers_are_sanitized_before_they_reach_output(self):
        sql = "CREATE TABLE fact_x (\x1b[31mcustomer\N{ZERO WIDTH SPACE}name VARCHAR(10));"
        table = dim_check.parse_ddl(sql, Path("x.sql"))[0]
        name = table.columns[0].name
        self.assertTrue(all(c.isprintable() and c.isascii() for c in name), name)

    def test_split_top_level_respects_nesting(self):
        self.assertEqual(
            dim_check.split_top_level("a DECIMAL(18,2), b INT"),
            ["a DECIMAL(18,2)", " b INT"],
        )


class TestSpecParsing(unittest.TestCase):
    def test_fenced_blocks_are_ignored_so_templates_do_not_fail(self):
        text = "# Templates\n\n```markdown\n## Fact: fact_x\n\n**Type**: transaction\n```\n"
        self.assertEqual(dim_check.parse_spec(text), [])

    def test_fields_and_measure_rows_are_captured(self):
        text = (
            "## Fact: fact_x\n\n"
            "**Grain**: one row represents one thing.\n\n"
            "**Measures**:\n\n"
            "| Name | Additivity |\n|---|---|\n| amount | additive |\n"
        )
        block = dim_check.parse_spec(text)[0]
        self.assertEqual(block["kind"], "fact")
        self.assertEqual(block["name"], "fact_x")
        self.assertIn("grain", block["fields"])
        self.assertEqual(len(block["rows"]), 2)  # header row plus one measure

    def test_tables_outside_the_measures_section_are_not_read_as_measures(self):
        text = (
            "## Fact: fact_x\n\n"
            "**Grain**: one row represents one thing.\n\n"
            "**Type**: transaction\n\n"
            "**Sources**:\n\n| System | Table |\n|---|---|\n| crm | orders |\n"
        )
        block = dim_check.parse_spec(text)[0]
        self.assertEqual(block["rows"], [])
        self.assertEqual(dim_check.spec_findings(block, Path("x.md")), [])

    def test_template_placeholders_count_as_missing(self):
        block = dim_check.parse_spec("## Fact: fact_x\n\n**Grain**: <one sentence>\n")[0]
        codes = [f.code for f in dim_check.spec_findings(block, Path("x.md"))]
        self.assertIn("SPEC-FACT-NO-GRAIN", codes)

    def test_grain_with_an_alternative_clause_is_flagged_vague(self):
        text = (
            "## Fact: fact_x\n\n"
            "**Grain**: one row per shipment, or per line for international orders.\n\n"
            "**Type**: transaction\n"
        )
        block = dim_check.parse_spec(text)[0]
        codes = [f.code for f in dim_check.spec_findings(block, Path("x.md"))]
        self.assertIn("SPEC-GRAIN-VAGUE", codes)

    def test_one_or_more_is_not_flagged_vague(self):
        text = (
            "## Fact: fact_x\n\n"
            "**Grain**: one row represents one shipment of one or more units.\n\n"
            "**Type**: transaction\n"
        )
        block = dim_check.parse_spec(text)[0]
        self.assertEqual(dim_check.spec_findings(block, Path("x.md")), [])


class TestJoinDetection(unittest.TestCase):
    def test_fact_to_fact_join_fails(self):
        sql = "SELECT 1 FROM fact_sales s JOIN fact_returns r ON r.k = s.k;"
        codes = [f.code for f in dim_check.join_findings(sql, Path("q.sql"))]
        self.assertEqual(codes, ["FACT-TO-FACT-JOIN"])

    def test_fact_joined_to_dimensions_is_fine(self):
        sql = ("SELECT 1 FROM fact_sales s JOIN dim_date d ON d.date_key = s.date_key "
               "JOIN dim_customer c ON c.customer_key = s.customer_key;")
        self.assertEqual(dim_check.join_findings(sql, Path("q.sql")), [])

    def test_union_branches_are_not_a_join(self):
        sql = "SELECT k FROM fact_sales UNION ALL SELECT k FROM fact_returns;"
        self.assertEqual(dim_check.join_findings(sql, Path("q.sql")), [])


# ------------------------------------------------------------ integration

class TestRunOverFixtures(unittest.TestCase):
    def test_correct_model_produces_nothing_at_all(self):
        findings, tables = dim_check.run([str(GOOD)])
        self.assertEqual([f.as_text() for f in findings], [])
        self.assertEqual(len(tables), 4)
        self.assertTrue(all(t.by_name for t in tables))

    def test_bad_model_produces_every_expected_code(self):
        findings, _ = dim_check.run([str(BAD)])
        codes = {f.code for f in findings}
        self.assertEqual(codes, {
            "DIM-NO-PK",
            "DIM-SCD2-INCOMPLETE",
            "DIM-SCD2-NO-SURROGATE",
            "DIM-SNOWFLAKE",
            "FACT-CENTIPEDE-DATE",
            "FACT-FLOAT-MONEY",
            "FACT-NATURAL-KEY",
            "FACT-NULL-FK",
            "FACT-TEXT-ATTR",
            "FACT-TO-FACT-JOIN",
            "SPEC-DIM-NO-DURABLE-KEY",
            "SPEC-DIM-NO-NATURAL-KEY",
            "SPEC-DIM-NO-SCD",
            "SPEC-DIM-SCD2-NO-SURROGATE",
            "SPEC-FACT-NO-GRAIN",
            "SPEC-FACT-NO-TYPE",
            "SPEC-GRAIN-VAGUE",
            "SPEC-MEASURE-NO-ADDITIVITY",
        })

    def test_findings_are_sorted_for_stable_output(self):
        findings, _ = dim_check.run([str(BAD)])
        self.assertEqual([f.key() for f in findings],
                         sorted(f.key() for f in findings))

    def test_the_skill_directory_itself_is_clean_apart_from_the_bad_fixtures(self):
        findings, _ = dim_check.run([str(SKILL)])
        offenders = {Path(f.path).name for f in findings}
        self.assertEqual(offenders, {"star.sql", "report.sql", "spec.md"})

    def test_inferred_classification_downgrades_failures_to_warnings(self):
        sql = """
        CREATE TABLE sales_ledger (
            date_key INT NOT NULL,
            customer_key INT,
            customer_name VARCHAR(50),
            sales_amount FLOAT,
            quantity INT
        );
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.sql"
            path.write_text(sql, encoding="utf-8")
            findings, tables = dim_check.run([str(path)])
        self.assertEqual(tables[0].kind, "fact")
        self.assertFalse(tables[0].by_name)
        self.assertTrue(findings)
        self.assertEqual({f.severity for f in findings}, {"WARN"})

    def test_a_missing_path_is_reported_without_crashing(self):
        findings, tables = dim_check.run(["/nonexistent/path/to/model.sql"])
        self.assertEqual((findings, tables), ([], []))


# --------------------------------------------------------------------- e2e

def cli(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=str(SKILL),
    )


class TestCommandLine(unittest.TestCase):
    def test_good_fixtures_exit_zero_and_print_nothing(self):
        result = cli(str(GOOD))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_bad_fixtures_exit_one(self):
        result = cli(str(BAD))
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL", result.stdout)

    def test_warnings_alone_do_not_fail_the_run(self):
        sql = "CREATE TABLE dim_thing (thing_name VARCHAR(50));"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "d.sql"
            path.write_text(sql, encoding="utf-8")
            result = cli(str(path))
        self.assertEqual(result.returncode, 0)
        self.assertIn("WARN", result.stdout)

    def test_json_output_is_valid_and_counts_match(self):
        result = cli("--json", str(BAD))
        payload = json.loads(result.stdout)
        fails = [f for f in payload["findings"] if f["severity"] == "FAIL"]
        self.assertEqual(payload["summary"]["fail"], len(fails))
        self.assertEqual(payload["summary"]["tables"], len(payload["tables"]))
        self.assertIn("classified_by", payload["tables"][0])

    def test_json_output_is_byte_identical_across_runs(self):
        self.assertEqual(cli("--json", str(BAD)).stdout,
                         cli("--json", str(BAD)).stdout)

    def test_directories_and_single_files_are_both_accepted(self):
        self.assertEqual(cli(str(GOOD / "star.sql")).returncode, 0)
        self.assertEqual(cli(str(BAD / "spec.md")).returncode, 1)

    def test_the_checker_never_executes_what_it_reads(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("exec(", "eval(", "__import__", "importlib",
                          "subprocess", "os.system", "popen"):
            self.assertNotIn(forbidden, source, f"{forbidden} in dim_check.py")


if __name__ == "__main__":
    unittest.main()
