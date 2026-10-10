#!/usr/bin/env python3
"""Tests for the copy, tree and doctor modes of skills/sanitize/scripts/sanitize.py.

A fixture tree with planted invented terms is copied and scanned; the original is
checked byte for byte afterwards, the report is checked for never holding a value.
Run: python3 -m unittest discover -s skills/sanitize/tests -v
"""

import hashlib
import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "sanitize.py"

spec = importlib.util.spec_from_file_location("sanitize", SCRIPT)
sz = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sz)

PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(64))


def tree_hash(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.terms_path = self.root / "terms.txt"
        self.terms_path.write_text("zorbulate\nQuintaxia\n", encoding="utf-8")
        self.env = mock.patch.dict(os.environ, {"IDENTIFIER_TERMS_FILE": str(self.terms_path)})
        self.env.start()
        self.src = self.root / "staging"
        (self.src / "proj-a" / "deep").mkdir(parents=True)
        (self.src / "proj-b").mkdir()
        (self.src / ".git").mkdir()
        (self.src / ".git" / "config").write_text("zorbulate in git metadata\n")
        (self.src / "proj-a" / "notes.md").write_text("# notes\nowner zorbulate, mail x@example.test\n")
        (self.src / "proj-a" / "deep" / "data.json").write_text(json.dumps({"k": "Quintaxia", "n": 2}))
        (self.src / "proj-a" / "pic.png").write_bytes(PNG)
        (self.src / "proj-b" / "clean.txt").write_text("nothing here\n")
        (self.src / "proj-b" / "paper.pdf").write_bytes(b"%PDF-1.4 zorbulate")
        (self.src / "proj-b" / "zorbulate-plan.md").write_text("plan body\n")
        self.before = tree_hash(self.src)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def run_cli(self, args, stdin_text=""):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(stdin_text)), redirect_stdout(out), redirect_stderr(err):
            code = sz.main(args)
        return code, out.getvalue(), err.getvalue()


class TestCopyFolder(Fixture):
    def test_copy_writes_a_clean_tree_and_leaves_the_original_alone(self):
        out_dir = self.root / "clean"
        code, out, err = self.run_cli(["copy", str(self.src), "--out", str(out_dir)])
        self.assertEqual(code, 0, err)
        self.assertEqual(tree_hash(self.src), self.before)
        self.assertEqual((out_dir / "proj-a" / "notes.md").read_text(), "# notes\nowner [TERM], mail [EMAIL]\n")
        self.assertEqual(json.loads((out_dir / "proj-a" / "deep" / "data.json").read_text()), {"k": "[TERM]", "n": 2})
        self.assertEqual((out_dir / "proj-b" / "clean.txt").read_text(), "nothing here\n")
        self.assertFalse((out_dir / "proj-a" / "pic.png").exists())
        self.assertFalse((out_dir / "proj-b" / "paper.pdf").exists())
        self.assertFalse((out_dir / ".git").exists())

    def test_file_named_after_a_term_is_renamed_and_counted(self):
        out_dir = self.root / "clean"
        self.run_cli(["copy", str(self.src), "--out", str(out_dir)])
        self.assertTrue((out_dir / "proj-b" / "[TERM]-plan.md").exists())
        self.assertFalse((out_dir / "proj-b" / "zorbulate-plan.md").exists())
        report = json.loads((out_dir / "sanitize-report.json").read_text())
        self.assertEqual(report["removed"]["path"], 1)

    def test_modes_are_0700_and_0600(self):
        out_dir = self.root / "clean"
        self.run_cli(["copy", str(self.src), "--out", str(out_dir)])
        self.assertEqual(stat.S_IMODE((out_dir / "proj-a").stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((out_dir / "proj-a" / "notes.md").stat().st_mode), 0o600)

    def test_report_holds_counts_paths_and_no_value(self):
        out_dir = self.root / "clean"
        code, out, _ = self.run_cli(["copy", str(self.src), "--out", str(out_dir)])
        report = json.loads((out_dir / "sanitize-report.json").read_text())
        self.assertEqual(report["mode"], "copy")
        self.assertEqual(report["files"], 4)
        self.assertEqual(report["removed"], {"term": 2, "email": 1, "path": 1})
        self.assertEqual(report["recall_layer"], "off")
        self.assertEqual(report["withheld"], 0)
        changed = {c["path"]: c for c in report["files_changed"]}
        self.assertEqual(changed["proj-a/notes.md"]["origin"], "proj-a")
        self.assertEqual(changed["proj-a/notes.md"]["removed"], 2)
        self.assertEqual(changed["proj-a/deep/data.json"]["removed"], 1)
        self.assertEqual(sorted(s["why"] for s in report["skipped"]), ["binary", "pdf"])
        text = (out_dir / "sanitize-report.json").read_text() + out
        for value in ("zorbulate", "Quintaxia", "x@example.test"):
            self.assertNotIn(value, text)
        self.assertEqual(json.loads(out)["files"], 4)

    def test_include_binary_copies_binaries_through_unchanged(self):
        out_dir = self.root / "clean"
        self.run_cli(["copy", str(self.src), "--out", str(out_dir), "--include-binary"])
        self.assertEqual((out_dir / "proj-a" / "pic.png").read_bytes(), PNG)
        self.assertEqual((out_dir / "proj-b" / "paper.pdf").read_bytes(), b"%PDF-1.4 zorbulate")
        report = json.loads((out_dir / "sanitize-report.json").read_text())
        self.assertEqual(sorted(s["why"] for s in report["skipped"]), ["binary", "pdf"])
        self.assertTrue(all(s["copied"] for s in report["skipped"]))

    def test_default_out_is_a_clean_sibling(self):
        code, _, err = self.run_cli(["copy", str(self.src)])
        self.assertEqual(code, 0, err)
        self.assertTrue((self.root / "staging-clean" / "proj-b" / "clean.txt").exists())

    def test_corpus_is_an_alias(self):
        code, _, err = self.run_cli(["corpus", str(self.src), "--out", str(self.root / "c")])
        self.assertEqual(code, 0, err)

    def test_existing_out_refuses_without_force(self):
        out_dir = self.root / "clean"
        out_dir.mkdir()
        (out_dir / "old.txt").write_text("x")
        code, _, err = self.run_cli(["copy", str(self.src), "--out", str(out_dir)])
        self.assertEqual(code, 2)
        self.assertIn("--force", err)
        code, _, err = self.run_cli(["copy", str(self.src), "--out", str(out_dir), "--force"])
        self.assertEqual(code, 0, err)

    def test_out_inside_src_refuses(self):
        code, _, err = self.run_cli(["copy", str(self.src), "--out", str(self.src / "inner")])
        self.assertEqual(code, 2)

    def test_missing_src_refuses(self):
        code, _, err = self.run_cli(["copy", str(self.root / "nope")])
        self.assertEqual(code, 2)

    def test_too_large_is_skipped(self):
        (self.src / "proj-b" / "big.txt").write_text("zorbulate " * 200_000)
        out_dir = self.root / "clean"
        self.run_cli(["copy", str(self.src), "--out", str(out_dir), "--max-mb", "1"])
        self.assertFalse((out_dir / "proj-b" / "big.txt").exists())
        report = json.loads((out_dir / "sanitize-report.json").read_text())
        self.assertIn("too-large", [s["why"] for s in report["skipped"]])

    def test_per_run_terms_apply_in_copy(self):
        out_dir = self.root / "clean"
        self.run_cli(["copy", str(self.src), "--out", str(out_dir), "--terms", "body"])
        self.assertEqual((out_dir / "proj-b" / "[TERM]-plan.md").read_text(), "plan [TERM]\n")


class TestCopyFile(Fixture):
    def test_single_file_copy_default_name(self):
        src = self.src / "proj-a" / "notes.md"
        code, out, err = self.run_cli(["copy", str(src)])
        self.assertEqual(code, 0, err)
        dst = self.src / "proj-a" / "notes-clean.md"
        self.assertEqual(dst.read_text(), "# notes\nowner [TERM], mail [EMAIL]\n")
        self.assertEqual(src.read_text(), "# notes\nowner zorbulate, mail x@example.test\n")
        report = json.loads(Path(str(dst) + ".sanitize-report.json").read_text())
        self.assertEqual(report["files"], 1)

    def test_single_file_copy_to_out(self):
        src = self.src / "proj-a" / "notes.md"
        dst = self.root / "elsewhere" / "n.md"
        code, _, err = self.run_cli(["copy", str(src), "--out", str(dst)])
        self.assertEqual(code, 0, err)
        self.assertEqual(stat.S_IMODE(dst.stat().st_mode), 0o600)
        self.assertIn("[TERM]", dst.read_text())


class TestTree(Fixture):
    def test_hits_exit_1_with_a_report_and_no_edits(self):
        code, out, _ = self.run_cli(["tree", str(self.src)])
        self.assertEqual(code, 1)
        self.assertEqual(tree_hash(self.src), self.before)
        report = json.loads(out)
        self.assertEqual(report["mode"], "tree")
        self.assertEqual(report["removed"], {"term": 2, "email": 1, "path": 1})
        self.assertIn("proj-a/notes.md", [c["path"] for c in report["files_changed"]])
        self.assertNotIn("zorbulate", out)
        self.assertFalse((self.src / "sanitize-report.json").exists())

    def test_clean_tree_exits_0(self):
        code, out, _ = self.run_cli(["tree", str(self.src / "proj-b" / "clean.txt")])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["removed"], {})

    def test_exclude_globs(self):
        code, out, _ = self.run_cli(["tree", str(self.src), "--exclude", "proj-a", "zorbulate-*"])
        self.assertEqual(code, 0, out)

    def test_files_changed_carry_per_class_counts(self):
        _, out, _ = self.run_cli(["tree", str(self.src)])
        changed = {c["path"]: c for c in json.loads(out)["files_changed"]}
        self.assertEqual(changed["proj-a/notes.md"]["classes"], {"email": 1, "term": 1})

    def test_tracked_scans_only_what_git_tracks(self):
        import subprocess
        repo = self.root / "repo"
        repo.mkdir()
        (repo / "tracked.txt").write_text("nothing here\n")
        (repo / "untracked.txt").write_text("zorbulate\n")
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
        code, out, _ = self.run_cli(["tree", str(repo), "--tracked"])
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["files"], 1)

    def test_tracked_outside_a_repo_refuses(self):
        code, _, err = self.run_cli(["tree", str(self.src), "--tracked"])
        self.assertEqual(code, 2)


class TestDoctor(Fixture):
    def test_doctor_reports_list_and_self_test(self):
        code, out, _ = self.run_cli(["doctor"])
        self.assertEqual(code, 0)
        self.assertIn("station term list: present (2 terms)", out)
        self.assertIn("normalization self-test: ok", out)
        self.assertIn("recall layer: off", out)
        self.assertNotIn("zorbulate", out)

    def test_doctor_exits_2_without_the_list(self):
        os.environ["IDENTIFIER_TERMS_FILE"] = str(self.root / "nowhere.txt")
        code, out, _ = self.run_cli(["doctor"])
        self.assertEqual(code, 2)
        self.assertIn("station term list: missing", out)


if __name__ == "__main__":
    unittest.main()
