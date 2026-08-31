#!/usr/bin/env python3
"""Tests for check_eval_coverage.py - stdlib only.

    python3 -m unittest discover -s skills/skill-authoring/tests

Fixtures are whole skill trees built in a temp directory, so the suite exercises
the CLI the way the gate does and never depends on the live repo's coverage,
which shifts every time a skill is authored.

The load-bearing case is trigger cases in a file named `evals.json`: that is the
trap the checker exists to catch, and it must exit non-zero. A missing file must
not, because backfill is opportunistic.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_eval_coverage.py"

TRIGGER_CASES = [
    {"query": "audit my skills", "should_trigger": True, "why": "direct request"},
    {"query": "write a skill for X", "should_trigger": True, "why": "authoring intent"},
    {"query": "what is the weather", "should_trigger": False, "why": "unrelated"},
]

EVAL_CASES = {
    "skill_name": "example",
    "evals": [
        {"id": "1", "prompt": "do the thing", "expected_output": "done",
         "expectations": ["mentions the thing"]},
    ],
}


def run(*args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


class CoverageTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "skills").mkdir()

    def make_skill(self, name: str, *, exempt: bool = False, evals_dir: bool = True,
                   files: dict[str, str] | None = None) -> Path:
        skill = self.root / "skills" / name
        skill.mkdir()
        frontmatter = ["---", f"name: {name}", "description: An example skill."]
        if exempt:
            frontmatter.append("disable-model-invocation: true")
        frontmatter += ["---", "", f"# {name}", ""]
        (skill / "SKILL.md").write_text("\n".join(frontmatter), encoding="utf-8")
        if evals_dir:
            (skill / "evals").mkdir()
            for filename, content in (files or {}).items():
                (skill / "evals" / filename).write_text(content, encoding="utf-8")
        return skill

    def report(self) -> tuple[int, dict]:
        code, out, err = run("--root", str(self.root), "--json")
        self.assertEqual(err, "", f"the checker wrote to stderr: {err}")
        return code, json.loads(out)

    def status(self, payload: dict, skill: str, filename: str) -> dict:
        entry = next(s for s in payload["skills"] if s["skill"] == skill)
        return next(f for f in entry["files"] if f["name"] == filename)


class TestBothFilesPresent(CoverageTestCase):
    def test_correct_shapes_pass(self) -> None:
        self.make_skill("well-covered", files={
            "triggers.json": json.dumps(TRIGGER_CASES),
            "evals.json": json.dumps(EVAL_CASES),
        })
        code, payload = self.report()
        self.assertEqual(code, 0)
        self.assertEqual(self.status(payload, "well-covered", "triggers.json")["status"], "ok")
        self.assertEqual(self.status(payload, "well-covered", "evals.json")["status"], "ok")
        self.assertEqual(payload["summary"]["mismatches"], 0)

    def test_text_output_names_both_files(self) -> None:
        self.make_skill("well-covered", files={
            "triggers.json": json.dumps(TRIGGER_CASES),
            "evals.json": json.dumps(EVAL_CASES),
        })
        code, out, _ = run("--root", str(self.root))
        self.assertEqual(code, 0)
        self.assertIn("triggers.json ok", out)
        self.assertIn("evals.json ok", out)
        self.assertIn("1 skills |", out)


class TestShapeNameMismatch(CoverageTestCase):
    def test_trigger_cases_in_a_file_named_evals_fail(self) -> None:
        self.make_skill("trapped", files={"evals.json": json.dumps(TRIGGER_CASES)})
        code, payload = self.report()
        self.assertEqual(code, 1)
        entry = self.status(payload, "trapped", "evals.json")
        self.assertEqual(entry["status"], "mismatch")
        self.assertIn("triggers cases", entry["detail"])
        self.assertEqual(payload["summary"]["mismatches"], 1)

    def test_mismatch_is_explained_in_text_output(self) -> None:
        self.make_skill("trapped", files={"evals.json": json.dumps(TRIGGER_CASES)})
        code, out, _ = run("--root", str(self.root))
        self.assertEqual(code, 1)
        self.assertIn("MISMATCH skills/trapped/evals/evals.json", out)

    def test_benchmark_cases_in_a_file_named_triggers_fail(self) -> None:
        self.make_skill("inverted", files={"triggers.json": json.dumps(EVAL_CASES)})
        code, payload = self.report()
        self.assertEqual(code, 1)
        self.assertEqual(self.status(payload, "inverted", "triggers.json")["status"], "mismatch")

    def test_list_without_should_trigger_is_a_mismatch(self) -> None:
        self.make_skill("half-shaped", files={
            "triggers.json": json.dumps([{"query": "do a thing"}]),
        })
        code, payload = self.report()
        self.assertEqual(code, 1)
        entry = self.status(payload, "half-shaped", "triggers.json")
        self.assertEqual(entry["status"], "mismatch")
        self.assertIn("should_trigger", entry["detail"])


class TestMissingFiles(CoverageTestCase):
    def test_missing_triggers_is_reported_but_passes(self) -> None:
        self.make_skill("benchmark-only", files={"evals.json": json.dumps(EVAL_CASES)})
        code, payload = self.report()
        self.assertEqual(code, 0)
        self.assertEqual(self.status(payload, "benchmark-only", "triggers.json")["status"], "missing")
        self.assertEqual(payload["summary"]["triggers_missing"], 1)

    def test_missing_evals_is_reported_but_passes(self) -> None:
        self.make_skill("triggers-only", files={"triggers.json": json.dumps(TRIGGER_CASES)})
        code, payload = self.report()
        self.assertEqual(code, 0)
        self.assertEqual(self.status(payload, "triggers-only", "evals.json")["status"], "missing")
        self.assertEqual(payload["summary"]["evals_missing"], 1)

    def test_no_evals_directory_is_reported(self) -> None:
        self.make_skill("bare", evals_dir=False)
        code, payload = self.report()
        self.assertEqual(code, 0)
        self.assertFalse(next(s for s in payload["skills"] if s["skill"] == "bare")["has_evals_dir"])
        self.assertEqual(payload["summary"]["no_evals_dir"], 1)
        self.assertIn("no evals/ directory", run("--root", str(self.root))[1])

    def test_directory_without_skill_md_is_not_a_skill(self) -> None:
        (self.root / "skills" / "not-a-skill").mkdir()
        code, payload = self.report()
        self.assertEqual(code, 0)
        self.assertEqual(payload["summary"]["skills"], 0)


class TestExemption(CoverageTestCase):
    def test_disable_model_invocation_exempts_from_triggers(self) -> None:
        self.make_skill("explicit-only", exempt=True, files={"evals.json": json.dumps(EVAL_CASES)})
        code, payload = self.report()
        self.assertEqual(code, 0)
        entry = self.status(payload, "explicit-only", "triggers.json")
        self.assertEqual(entry["status"], "exempt")
        self.assertEqual(payload["summary"]["triggers_exempt"], 1)
        self.assertEqual(payload["summary"]["triggers_missing"], 0)

    def test_exempt_skill_still_has_its_triggers_file_checked(self) -> None:
        self.make_skill("explicit-only", exempt=True, files={"triggers.json": json.dumps(EVAL_CASES)})
        code, payload = self.report()
        self.assertEqual(code, 1)
        self.assertEqual(self.status(payload, "explicit-only", "triggers.json")["status"], "mismatch")

    def test_false_value_does_not_exempt(self) -> None:
        skill = self.make_skill("normal")
        skill_md = skill / "SKILL.md"
        skill_md.write_text(
            skill_md.read_text(encoding="utf-8").replace(
                "description: An example skill.",
                "description: An example skill.\ndisable-model-invocation: false",
            ),
            encoding="utf-8",
        )
        code, payload = self.report()
        self.assertEqual(code, 0)
        self.assertEqual(self.status(payload, "normal", "triggers.json")["status"], "missing")

    def test_body_mention_does_not_exempt(self) -> None:
        self.make_skill("prose-only", files={})
        skill_md = self.root / "skills" / "prose-only" / "SKILL.md"
        skill_md.write_text(
            skill_md.read_text(encoding="utf-8") + "\nUse disable-model-invocation: true here.\n",
            encoding="utf-8",
        )
        code, payload = self.report()
        self.assertEqual(code, 0)
        self.assertEqual(self.status(payload, "prose-only", "triggers.json")["status"], "missing")


class TestMalformedInput(CoverageTestCase):
    def test_invalid_json_reports_position_without_a_traceback(self) -> None:
        """A file no consumer can parse cannot match its name, so it fails the gate."""
        self.make_skill("broken", files={"triggers.json": '[{"query": "x", ]'})
        code, out, err = run("--root", str(self.root))
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)
        self.assertNotIn("Traceback", out)
        self.assertIn("UNPARSEABLE skills/broken/evals/triggers.json", out)
        self.assertIn("invalid JSON at line", out)

    def test_invalid_json_is_counted_separately_from_mismatches(self) -> None:
        self.make_skill("broken", files={"evals.json": "not json at all"})
        code, payload = self.report()
        self.assertEqual(code, 1)
        self.assertEqual(payload["summary"]["unparseable"], 1)
        self.assertEqual(payload["summary"]["mismatches"], 0)

    def test_empty_list_is_a_mismatch_not_a_crash(self) -> None:
        self.make_skill("hollow", files={"triggers.json": "[]"})
        code, payload = self.report()
        self.assertEqual(code, 1)
        self.assertIn("empty list", self.status(payload, "hollow", "triggers.json")["detail"])

    def test_json_scalar_is_reported(self) -> None:
        self.make_skill("scalar", files={"evals.json": "42"})
        code, payload = self.report()
        self.assertEqual(code, 1)
        self.assertIn("top-level JSON is int", self.status(payload, "scalar", "evals.json")["detail"])


class TestRootResolution(CoverageTestCase):
    def test_empty_root_is_reported_not_crashed(self) -> None:
        code, out, err = run("--root", str(self.root))
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertIn("no skills found", out)

    def test_default_root_is_the_repo_the_script_ships_in(self) -> None:
        code, out, err = run("--json")
        self.assertNotIn("Traceback", err)
        payload = json.loads(out)
        self.assertEqual(Path(payload["root"]), SCRIPT.resolve().parents[3])
        self.assertIn("skill-authoring", [s["skill"] for s in payload["skills"]])
        self.assertIn(code, (0, 1))


if __name__ == "__main__":
    unittest.main()
