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
import shutil
import stat
import sys
import tempfile
import unittest
import zipfile
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
        # the fixture's PDF holds a term in readable text: copied through unscanned it would leak, and the
        # verifier reads it as flat text and refuses the copy
        code, _, err = self.run_cli(["copy", str(self.src), "--out", str(out_dir), "--include-binary"])
        self.assertEqual(code, 5)
        self.assertIn("paper.pdf", err)
        self.assertNotIn("zorbulate", err)
        self.assertFalse(out_dir.exists())
        code, _, err = self.run_cli(["copy", str(self.src), "--out", str(out_dir), "--include-binary", "--exclude", "*.pdf"])
        self.assertEqual(code, 0, err)
        self.assertEqual((out_dir / "proj-a" / "pic.png").read_bytes(), PNG)
        report = json.loads((out_dir / "sanitize-report.json").read_text())
        self.assertEqual([s["why"] for s in report["skipped"]], ["binary"])
        self.assertTrue(all(s["copied"] for s in report["skipped"]))
        self.assertIs(report["verified"], True)

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
        (out_dir / "sanitize-report.json").write_text("{}")      # an earlier copy, which --force may replace
        code, _, err = self.run_cli(["copy", str(self.src), "--out", str(out_dir)])
        self.assertEqual(code, 2)
        self.assertIn("--force", err)
        code, _, err = self.run_cli(["copy", str(self.src), "--out", str(out_dir), "--force"])
        self.assertEqual(code, 0, err)
        self.assertFalse((out_dir / "old.txt").exists())

    def test_force_replaces_the_whole_tree_and_a_partial_run_leaves_nothing(self):
        out_dir = self.root / "clean"
        out_dir.mkdir()
        (out_dir / "stale.txt").write_text("from an earlier run, never rescanned\n")
        (out_dir / "sanitize-report.json").write_text("{}")      # marks it as an earlier copy
        code, _, err = self.run_cli(["copy", str(self.src), "--out", str(out_dir), "--force"])
        self.assertEqual(code, 0, err)
        self.assertFalse((out_dir / "stale.txt").exists())
        self.assertTrue((out_dir / "proj-b" / "clean.txt").exists())
        self.assertEqual(stat.S_IMODE(out_dir.stat().st_mode), 0o700)
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith(".clean")], [])   # no staging left behind

    def test_force_never_removes_a_folder_that_is_not_an_earlier_copy(self):
        out_dir = self.root / "documents"
        out_dir.mkdir()
        (out_dir / "thesis.txt").write_text("years of work\n")
        code, _, err = self.run_cli(["copy", str(self.src), "--out", str(out_dir), "--force"])
        self.assertEqual(code, 2)
        self.assertIn("not an earlier copy", err.replace("other than an earlier copy", "not an earlier copy"))
        self.assertEqual((out_dir / "thesis.txt").read_text(), "years of work\n")
        single = self.root / "keep.md"
        single.write_text("mine\n")
        code, _, err = self.run_cli(["copy", str(self.src / "proj-b" / "clean.txt"), "--out", str(single), "--force"])
        self.assertEqual(code, 2)
        self.assertEqual(single.read_text(), "mine\n")

    def test_two_sources_that_clean_to_one_path_refuse_the_run(self):
        (self.src / "proj-b" / "Quintaxia-plan.md").write_text("other plan\n")    # both clean to [TERM]-plan.md
        out_dir = self.root / "clean"
        code, out, err = self.run_cli(["copy", str(self.src), "--out", str(out_dir)])
        self.assertEqual(code, 2)
        self.assertIn("same clean path", err)
        for term in ("zorbulate", "Quintaxia"):
            self.assertNotIn(term, out + err)
        self.assertFalse(out_dir.exists())                                            # nothing half-written
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith(".clean")], [])

    def test_output_through_a_link_and_a_reserved_name_are_refused(self):
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        link = self.root / "clean"
        link.symlink_to(elsewhere)
        code, _, err = self.run_cli(["copy", str(self.src), "--out", str(link), "--force"])
        self.assertEqual(code, 2)
        self.assertIn("link", err)
        self.assertEqual(list(elsewhere.iterdir()), [])
        (self.src / "sanitize-report.json").write_text("{}")
        code, _, err = self.run_cli(["copy", str(self.src), "--out", str(self.root / "clean2")])
        self.assertEqual(code, 2)
        self.assertIn("reserved", err)

    def test_every_copy_is_verified_by_the_parser_free_pass(self):
        out_dir = self.root / "clean"
        code, out, err = self.run_cli(["copy", str(self.src), "--out", str(out_dir)])
        self.assertEqual(code, 0, err)
        self.assertIs(json.loads((out_dir / "sanitize-report.json").read_text())["verified"], True)
        # a parser gap that let a term through is caught before the copy lands
        real = sz.scan_one

        def leaky(path, rel, opts, report, max_bytes):
            clean_rel, data, why = real(path, rel, opts, report, max_bytes)
            if rel.name == "notes.md":
                return clean_rel, path.read_bytes(), why      # the original bytes, as a broken parser would write
            return clean_rel, data, why

        shutil.rmtree(out_dir)
        with mock.patch.object(sz, "scan_one", leaky):
            code, out, err = self.run_cli(["copy", str(self.src), "--out", str(out_dir)])
        self.assertEqual(code, 5, err)
        self.assertIn("verifier refused", err)
        self.assertIn("residual hits", err)
        self.assertNotIn("zorbulate", out + err)
        self.assertFalse(out_dir.exists())
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith(".clean")], [])
        # --no-verify records that the pass did not run
        code, _, err = self.run_cli(["copy", str(self.src), "--out", str(out_dir), "--no-verify"])
        self.assertEqual(code, 0, err)
        self.assertIsNone(json.loads((out_dir / "sanitize-report.json").read_text())["verified"])

    def test_verify_command_reads_flat_text_zip_members_and_paths(self):
        tree = self.root / "written"
        (tree / "zorbulate-dir").mkdir(parents=True)
        (tree / "zorbulate-dir" / "a.txt").write_text("fine\n")
        (tree / "b.json").write_text('{"k": "zorb\\u0075late"}')          # a term behind an escape the flat view does not decode
        code, out, _ = self.run_cli(["verify", str(tree)])
        self.assertEqual(code, 1)
        result = json.loads(out)
        self.assertEqual([h["path"] for h in result["hits"]], ["[TERM]-dir/a.txt"])     # a path that is the hit is never printed raw
        self.assertTrue(result["hits"][0]["path_hit"])
        self.assertFalse(result["ok"])
        self.assertNotIn("zorbulate", json.dumps(result) + out)
        (tree / "link.txt").symlink_to(tree / "b.json")
        code, out, _ = self.run_cli(["verify", str(tree)])
        self.assertIn({"path": "link.txt", "why": "link"}, json.loads(out)["uninspected"])
        (tree / "link.txt").unlink()
        # a zip member is read like any other text; an undecodable file is uninspected unless allowed
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("word/document.xml", "<w:t>Quintaxia</w:t>")
            z.writestr("word/media/zorbulate.png", b"\x89PNG" + bytes(range(32)))     # a member's name is a path too
        clean = self.root / "clean-written"
        clean.mkdir()
        (clean / "memo.docx").write_bytes(buf.getvalue())
        code, out, _ = self.run_cli(["verify", str(clean)])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["hits"][0]["classes"]["term"], 2)      # the document text and the member name
        self.assertNotIn("zorbulate", out)
        (clean / "memo.docx").unlink()
        (clean / "blob.bin").write_bytes(bytes(range(256)))
        code, out, _ = self.run_cli(["verify", str(clean)])
        self.assertEqual(code, 4)
        self.assertEqual(json.loads(out)["uninspected"], [{"path": "blob.bin", "why": "undecodable"}])
        code, _, _ = self.run_cli(["verify", str(clean), "--allow-binary"])
        self.assertEqual(code, 0)

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

    def test_no_raw_path_component_reaches_the_report_stdout_or_stderr(self):
        # a top-level folder named after a term: origin and every path in the report are the clean ones
        (self.src / "zorbulate-corp").mkdir()
        (self.src / "zorbulate-corp" / "memo.md").write_text("Quintaxia memo\n")
        out_dir = self.root / "clean"
        code, out, err = self.run_cli(["copy", str(self.src), "--out", str(out_dir)])
        self.assertEqual(code, 0, err)
        report = json.loads((out_dir / "sanitize-report.json").read_text())
        origins = {f["origin"] for f in report["files_changed"]}
        self.assertIn("[TERM]-corp", origins)
        for blob in (json.dumps(report), out, err):
            self.assertNotIn("zorbulate", blob)
            self.assertNotIn("Quintaxia", blob)
        # the default output name of a single file named after a term is built from the clean name
        single = self.src / "proj-b" / "zorbulate-plan.md"
        code, out, err = self.run_cli(["copy", str(single)])
        self.assertEqual(code, 0, err)
        self.assertTrue((self.src / "proj-b" / "[TERM]-plan-clean.md").exists())
        self.assertNotIn("zorbulate", out + err)
        # an error about a path the user passed names the argument, never the value
        code, out, err = self.run_cli(["copy", str(self.root / "zorbulate-missing")])
        self.assertEqual(code, 2)
        self.assertNotIn("zorbulate", out + err)
        code, out, err = self.run_cli(["tree", str(self.root / "zorbulate-missing"), "--tracked"])
        self.assertEqual(code, 2)
        self.assertNotIn("zorbulate", out + err)
        code, out, err = self.run_cli(["copy", str(single), "--out", str(self.src / "proj-b" / "zorbulate-plan.md")])
        self.assertEqual(code, 2)
        self.assertNotIn("zorbulate", out + err)

    def test_an_unreadable_file_is_skipped_not_a_traceback(self):
        locked = self.src / "proj-b" / "locked.txt"
        locked.write_text("zorbulate\n")
        locked.chmod(0)
        try:
            out_dir = self.root / "clean"
            code, out, err = self.run_cli(["copy", str(self.src), "--out", str(out_dir)])
            self.assertEqual(code, 0, err)
            report = json.loads((out_dir / "sanitize-report.json").read_text())
            self.assertIn({"path": "proj-b/locked.txt", "why": "unreadable", "copied": False}, report["skipped"])
            self.assertNotIn("Traceback", err)
            code, out, err = self.run_cli(["tree", str(self.src)])
            self.assertEqual(code, 1)
            self.assertIn("unreadable", out)
        finally:
            locked.chmod(0o600)

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

    def test_a_file_that_could_hold_text_but_was_not_scanned_is_not_a_clean_verdict(self):
        folder = self.root / "docs"
        folder.mkdir()
        (folder / "paper.pdf").write_bytes(b"%PDF-1.4 anything")
        (folder / "pic.png").write_bytes(PNG)
        code, out, _ = self.run_cli(["tree", str(folder)])
        self.assertEqual(code, 4)                      # the PDF was not inspected
        report = json.loads(out)
        self.assertEqual(report["removed"], {})
        self.assertEqual(sorted(s["why"] for s in report["skipped"]), ["binary", "pdf"])
        (folder / "paper.pdf").unlink()
        code, _, _ = self.run_cli(["tree", str(folder)])
        self.assertEqual(code, 0)                      # a known binary type is not text and does not count
        (folder / "notes.txt").write_bytes(b"\xff\xfe\x00bad text")
        code, out, _ = self.run_cli(["tree", str(folder)])
        self.assertEqual(code, 4)
        self.assertIn("undecodable", [s["why"] for s in json.loads(out)["skipped"]])

    def test_duplicate_json_keys_are_a_finding_not_a_silent_last_wins(self):
        folder = self.root / "dup"
        folder.mkdir()
        (folder / "cfg.json").write_text('{"owner": "zorbulate", "owner": "nobody"}')
        code, out, _ = self.run_cli(["tree", str(folder)])
        self.assertEqual(code, 1)
        report = json.loads(out)
        self.assertEqual(report["removed"]["json_duplicate_key"], 1)
        self.assertEqual(report["removed"]["term"], 1)     # the first value was scanned, not dropped
        out_dir = self.root / "dup-clean"
        code, _, err = self.run_cli(["copy", str(folder), "--out", str(out_dir)])
        self.assertEqual(code, 0, err)
        self.assertEqual((out_dir / "cfg.json").read_text(), '{"owner": "[TERM]", "owner": "nobody"}')

    def test_exclude_globs(self):
        code, out, _ = self.run_cli(["tree", str(self.src), "--exclude", "proj-a", "zorbulate-*", "*.pdf"])
        self.assertEqual(code, 0, out)
        code, out, _ = self.run_cli(["tree", str(self.src), "--exclude", "proj-a", "zorbulate-*"])
        self.assertEqual(code, 4, out)      # the fixture's PDF was not inspected

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

    def test_doctor_exits_2_on_an_empty_list(self):
        self.terms_path.write_text("# only a comment\n", encoding="utf-8")
        code, out, _ = self.run_cli(["doctor"])
        self.assertEqual(code, 2)
        self.assertIn("no terms", out)

    def test_doctor_exits_2_without_the_list(self):
        os.environ["IDENTIFIER_TERMS_FILE"] = str(self.root / "nowhere.txt")
        code, out, _ = self.run_cli(["doctor"])
        self.assertEqual(code, 2)
        self.assertIn("station term list: missing", out)


if __name__ == "__main__":
    unittest.main()
