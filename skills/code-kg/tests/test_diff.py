"""`ingest --keep-previous` and `diff`: what changed between the live graph
and a checkpoint, by file and by symbol, in the shape markdown-kg's `diff`
gives for notes and sections. Every bucket below is seeded by hand."""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_symbol_edges import run  # noqa: E402

import code_kg  # noqa: E402

# Creating a symlink on Windows needs Developer Mode or admin rights.
needs_symlinks = unittest.skipIf(sys.platform == "win32",
                                 "symlinks need Developer Mode or admin rights on Windows")

BEFORE = {
    "a.py": """def keep():
    x = 1
    return x


def edit_me():
    y = 2
    return y


def old_name():
    z = 3
    z += 1
    return z


def gone():
    q = 4
    return q
""",
    "b.py": """def mover():
    m = 5
    m *= 2
    return m
""",
    "d.py": """def dup():
    a = 1
    return a
""",
}

AFTER = {
    "a.py": """def keep():
    x = 1
    return x


def edit_me():
    y = 20
    return y


def new_name():
    z = 3
    z += 1
    return z


def fresh():
    f = 6
    return f
""",
    "b.py": "X = 1\n",
    "c.py": BEFORE["b.py"],
    "d.py": """def dup():
    b = 0
    return b


def dup():
    a = 1
    return a
""",
}


class DiffCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ckg-diff-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = self.tmp / "repo"
        self.write(BEFORE)

    def write(self, files: dict):
        for rel, text in files.items():
            p = self.repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")

    def cli(self, *argv):
        rc, out, err = run(argv[0], str(self.repo), *argv[1:], "--json")
        self.assertEqual(rc, 0, err)
        return json.loads(out)

    def changed(self):
        self.cli("ingest")
        for rel in set(BEFORE) - set(AFTER):
            (self.repo / rel).unlink()
        self.write(AFTER)
        return self.cli("ingest", "--keep-previous")


class CheckpointTests(DiffCase):
    def test_plain_ingest_writes_no_checkpoint(self):
        got = self.cli("ingest")
        self.cli("ingest")
        self.assertFalse(code_kg.prev_db_path(self.repo).exists())
        self.assertNotIn("checkpoint", got)

    def test_keep_previous_checkpoints_the_pre_ingest_db(self):
        self.cli("ingest")
        before = code_kg.db_path(self.repo).read_bytes()
        self.write(AFTER)
        got = self.cli("ingest", "--keep-previous")
        self.assertEqual(got["checkpoint"], str(code_kg.prev_db_path(
            self.repo)))
        self.assertEqual(code_kg.prev_db_path(self.repo).read_bytes(),
                         before)

    def test_first_ingest_with_flag_has_no_checkpoint(self):
        got = self.cli("ingest", "--keep-previous")
        self.assertIsNone(got["checkpoint"])
        self.assertFalse(code_kg.prev_db_path(self.repo).exists())

    def test_the_checkpoint_is_gitignored(self):
        self.changed()
        gi = code_kg.kg_dir(self.repo) / ".gitignore"
        self.assertEqual([ln for ln in gi.read_text().splitlines() if not ln.startswith("#")], ["*.db*"])

    def test_an_older_gitignore_gains_the_checkpoint_line(self):
        self.cli("ingest")
        gi = code_kg.kg_dir(self.repo) / ".gitignore"
        gi.write_text("code-kg.db\ncoverage-tmp.json\n", encoding="utf-8")
        self.cli("ingest", "--keep-previous")
        self.assertIn(code_kg.PREV_DB_NAME, gi.read_text().split())

    @needs_symlinks
    def test_a_planted_link_is_never_written_through(self):
        self.cli("ingest")
        for kind in ("symlink", "hardlink"):
            target = self.tmp / f"planted-{kind}"
            target.write_bytes(b"keep")
            prev = code_kg.prev_db_path(self.repo)
            if prev.exists() or prev.is_symlink():
                prev.unlink()
            (os.symlink if kind == "symlink" else os.link)(target, prev)
            live = code_kg.db_path(self.repo).read_bytes()
            self.cli("ingest", "--keep-previous")
            self.assertEqual(target.read_bytes(), b"keep", kind)
            self.assertFalse(prev.is_symlink(), kind)
            self.assertEqual(prev.read_bytes(), live, kind)
            leftovers = [p for p in prev.parent.iterdir()
                         if p.name.endswith(".tmp")]
            self.assertEqual(leftovers, [], kind)


class LinkedStoreTests(DiffCase):
    """A repo is untrusted: a committed link at the engine's folder or db
    would carry every write to a place the planter chose."""

    @needs_symlinks
    def test_a_linked_engine_folder_is_refused(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        os.symlink(outside, self.repo / ".kg")
        for argv in (("ingest",), ("ingest", "--keep-previous")):
            rc, _, err = run(argv[0], str(self.repo), *argv[1:])
            self.assertNotEqual(rc, 0)
            self.assertIn("link", err)
        self.assertEqual(list(outside.iterdir()), [])

    @needs_symlinks
    def test_a_linked_database_is_refused(self):
        self.cli("ingest")
        other = self.tmp / "other.db"
        sqlite3.connect(other).close()
        db = code_kg.db_path(self.repo)
        db.unlink()
        os.symlink(other, db)
        before = other.read_bytes()
        rc, _, err = run("ingest", str(self.repo), "--keep-previous")
        self.assertNotEqual(rc, 0)
        self.assertEqual(other.read_bytes(), before)
        self.assertFalse(code_kg.prev_db_path(self.repo).exists())


class DiffTests(DiffCase):
    def test_every_bucket_classifies_its_seeded_case(self):
        self.changed()
        d = self.cli("diff")
        self.assertEqual([e["symbol_id"] for e in d["added"]],
                         ["a.py::fresh", "d.py::dup"])
        self.assertEqual([e["symbol_id"] for e in d["removed"]],
                         ["a.py::gone"])
        pairs = {k: [(e["from_id"], e["to_id"]) for e in d[k]]
                 for k in ("edited", "renamed", "moved")}
        self.assertEqual(pairs, {
            "edited": [("a.py::edit_me", "a.py::edit_me")],
            "renamed": [("a.py::old_name", "a.py::new_name")],
            "moved": [("b.py::mover", "c.py::mover")]})
        # keep, and the shifted dup~2 that is the old dup.
        self.assertEqual(d["unchanged"], 2)
        self.assertEqual(d["files"], {"added": ["c.py"], "removed": [],
                                      "edited": ["a.py", "b.py", "d.py"]})

    def test_no_change_diff_is_all_zeros_and_deterministic(self):
        self.cli("ingest")
        self.cli("ingest", "--keep-previous")
        one, two = self.cli("diff"), self.cli("diff")
        self.assertEqual(one, two)
        for k in ("added", "removed", "edited", "renamed", "moved"):
            self.assertEqual(one[k], [], k)
        self.assertEqual(one["files"], {"added": [], "removed": [],
                                        "edited": []})
        self.assertEqual(one["unchanged"], 6)

    def test_a_one_line_body_never_pairs_as_moved(self):
        self.write({"e.py": "def a():\n    pass\n"})
        self.cli("ingest")
        (self.repo / "e.py").unlink()
        self.write({"f.py": "def b():\n    pass\n"})
        self.cli("ingest", "--keep-previous")
        d = self.cli("diff")
        self.assertEqual(d["moved"], [])
        self.assertIn("f.py::b", [e["symbol_id"] for e in d["added"]])
        self.assertIn("e.py::a", [e["symbol_id"] for e in d["removed"]])

    def test_missing_checkpoint_and_bad_against_error(self):
        self.cli("ingest")
        rc, _, err = run("diff", str(self.repo))
        self.assertNotEqual(rc, 0)
        self.assertIn("--keep-previous", err)
        rc, _, err = run("diff", str(self.repo), "--against",
                         str(self.tmp / "nope.db"))
        self.assertNotEqual(rc, 0)
        junk = self.tmp / "junk.db"
        sqlite3.connect(junk).execute("CREATE TABLE t(x)").connection \
            .commit()
        rc, _, err = run("diff", str(self.repo), "--against", str(junk))
        self.assertNotEqual(rc, 0)
        self.assertIn("not a code-kg db", err)

    def test_against_is_never_written(self):
        self.changed()
        prev = code_kg.prev_db_path(self.repo)
        before = (prev.read_bytes(), prev.stat().st_mtime_ns)
        self.cli("diff")
        self.cli("diff", "--against", str(prev))
        self.assertEqual((prev.read_bytes(), prev.stat().st_mtime_ns),
                         before)

    def test_against_uri_cannot_smuggle_query_parameters(self):
        self.changed()
        odd = self.tmp / "x?mode=rwc"
        odd.mkdir()
        target = odd / "a.db"
        shutil.copy(code_kg.prev_db_path(self.repo), target)
        d = self.cli("diff", "--against", str(target))
        self.assertEqual(d["against"], str(target))

    def test_cross_repo_against_another_db(self):
        self.changed()
        other = self.tmp / "other"
        shutil.copytree(self.repo, other)
        d = self.cli("diff", "--against", str(code_kg.db_path(other)))
        self.assertEqual(d["added"], [])
        self.assertEqual(d["unchanged"], 7)

    def test_text_render(self):
        self.changed()
        rc, out, err = run("diff", str(self.repo))
        self.assertEqual(rc, 0, err)
        self.assertIn("renamed: a.py::old_name -> a.py::new_name", out)
        self.assertIn("edited: a.py::edit_me", out)
        self.assertIn("files: 1 added, 0 removed, 3 edited", out)
        self.assertIn("symbols: 2 added, 1 removed, 1 edited, 1 renamed,"
                      " 1 moved, 2 unchanged", out)


if __name__ == "__main__":
    unittest.main()
