#!/usr/bin/env python3
"""Golden-output guard for markdown_kg.py.

Every command that existed before the extension keys is run over the three
committed fixture vaults, and its output is compared with a stored capture in
`golden/`. An engine change that alters what an existing command prints, or
what an existing table holds, fails here before it reaches a real vault. New
commands, flags and tables are covered by their own tests, never by this file.

Regenerate deliberately, after reading the diff:
`python3 skills/markdown-kg/tests/test_golden.py --update`."""
import contextlib
import difflib
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import markdown_kg
from fixture_copy import copy_fixture

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden"
FIXTURES = ("fixture-vault", "kb-fixture-vault", "adversarial-vault")
TERMS = ("water", "irrigation", "garden plan", "note", "review")
STAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")

# Explicit column lists: a column added to one of these tables later must not
# read as a change to what the table held before.
DUMPS = {
    "notes": "SELECT id, path, title, tags, aliases, content_hash, profile,"
             " weight, doc_date, status FROM notes ORDER BY id",
    "sections": "SELECT id, note_id, parent_id, heading, heading_path, level,"
                " ord, char_start, char_end, line_start, line_end, doc_date,"
                " slot, weight, words, is_unit, oversize, section_hash, setext"
                " FROM sections ORDER BY id",
    "properties": "SELECT note_id, key, value FROM properties ORDER BY 1, 2",
    "tags": "SELECT note_id, tag FROM tags ORDER BY 1, 2",
    "aliases": "SELECT note_id, alias FROM aliases ORDER BY 1, 2",
    "edges": "SELECT src, dst, target, syntax, kind, status, section_id"
             " FROM edges ORDER BY src, syntax, kind, target",
    "members": "SELECT section_id, note_id, group_name, name, ord"
               " FROM members ORDER BY 1, 5, 4",
    "entities": "SELECT canonical, type, time, note, t_start, t_end"
                " FROM entities ORDER BY 1",
    "entity_aliases": "SELECT canonical, alias FROM entity_aliases"
                      " ORDER BY 1, 2",
    "mentions": "SELECT canonical, section_id, note_id, doc_date, count"
                " FROM mentions ORDER BY 1, 2",
    "ignored": "SELECT path, rule FROM ignored ORDER BY 1",
    "annotations": "SELECT note_id, section_id, line, marker, payload, target,"
                   " date FROM annotations ORDER BY 1, 3",
    "annotation_candidates": "SELECT token, kind, count"
                             " FROM annotation_candidates ORDER BY 1, 2",
}


def run(vault: Path, *argv: str) -> dict:
    """One engine call in-process: exit code plus normalized stdout/stderr."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = markdown_kg.main(list(argv))
        except SystemExit as e:
            if isinstance(e.code, int) or e.code is None:
                rc = e.code or 0
            else:
                rc = 1
                err.write(str(e.code))
    return {"rc": rc, "out": _norm(out.getvalue(), vault),
            "err": _norm(err.getvalue(), vault)}


def _norm(text: str, vault: Path) -> str:
    # The widen line names this engine's script as a shell path, which
    # depends on the folder the tests run from.
    text = text.replace(markdown_kg.shell_path(
        Path(markdown_kg.__file__).resolve()), "<SCRIPT>")
    for p in sorted({str(vault), str(vault.resolve())}, key=len, reverse=True):
        text = text.replace(p, "<VAULT>")
    return STAMP_RE.sub("<UTC>", text)


def capture(fixture: str) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="mdkg-golden-"))
    try:
        vault = copy_fixture(HERE / fixture, tmp / "vault")
        v = str(vault)
        got: dict = {}

        def call(*argv: str) -> None:
            key = " ".join(a if a != v else "<VAULT>" for a in argv)
            got[key] = run(vault, *argv)

        call("ingest", v, "--json")
        con = sqlite3.connect(markdown_kg.db_path(vault))
        got["tables"] = {name: [list(r) for r in con.execute(sql)]
                         for name, sql in DUMPS.items()}
        notes = [r[0] for r in con.execute("SELECT id FROM notes ORDER BY id")]
        tags = [r[0] for r in con.execute(
            "SELECT DISTINCT lower(tag) FROM tags ORDER BY 1")]
        entities = [r[0] for r in con.execute(
            "SELECT canonical FROM entities ORDER BY 1")]
        con.close()

        for cmd in (("stats",), ("tags",), ("links", "--unresolved"),
                    ("props",), ("annotations",), ("relations",),
                    ("themes",), ("trends", "--by", "month"), ("profile",)):
            call(cmd[0], v, *cmd[1:])
            call(cmd[0], v, *cmd[1:], "--json")
        for nid in notes:
            for cmd in ("note", "sections", "links", "backlinks"):
                call(cmd, v, nid, "--json")
            call("neighbors", v, nid, "--depth", "2", "--json")
            call("backlinks", v, nid)
        if len(notes) > 1:
            call("path", v, notes[0], notes[-1], "--json")
        for tag in tags:
            call("tags", v, tag, "--json")
        for name in entities:
            for cmd in ("entity", "timeline", "during"):
                call(cmd, v, name, "--json")
        for term in TERMS:
            call("search", v, term, "--json")
            call("search", v, term)
            call("search", v, term, "--budget", "400", "--json")
            call("query", v, term, "--json")
            call("trajectory", v, term, "--json")
        # Last: it writes the one file the engine ever adds to a vault.
        call("index", v, "--out", "Golden Index.md")
        index = vault / "Golden Index.md"
        got["index file"] = (_norm(index.read_text(encoding="utf-8"), vault)
                             if index.exists() else None)
        return got
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def golden_path(fixture: str) -> Path:
    return GOLDEN / f"{fixture}.json"


def _show(value) -> list[str]:
    return json.dumps(value, indent=2, sort_keys=True,
                      ensure_ascii=False).splitlines()


class GoldenTests(unittest.TestCase):
    maxDiff = None

    def check(self, fixture: str) -> None:
        want = json.loads(golden_path(fixture).read_text(encoding="utf-8"))
        got = json.loads(json.dumps(capture(fixture)))
        self.assertEqual(sorted(want), sorted(got),
                         "the set of captured commands changed")
        for key in sorted(want):
            if want[key] != got[key]:
                diff = "\n".join(list(difflib.unified_diff(
                    _show(want[key]), _show(got[key]), "golden", "now",
                    lineterm=""))[:80])
                self.fail(f"{fixture}: output changed for `{key}`\n{diff}")

    def test_fixture_vault(self):
        self.check("fixture-vault")

    def test_kb_fixture_vault(self):
        self.check("kb-fixture-vault")

    def test_adversarial_vault(self):
        self.check("adversarial-vault")

    def test_output_does_not_depend_on_the_hash_seed(self):
        """Set iteration order changes with PYTHONHASHSEED, so any output
        ordered by a set differs between two runs of the same command."""
        for fixture in FIXTURES:
            dumps = []
            for seed in ("1", "2", "3"):
                r = subprocess.run(
                    [sys.executable, str(Path(__file__).resolve()), "--dump",
                     fixture], capture_output=True, text=True,
                    env={**os.environ, "PYTHONHASHSEED": seed})
                self.assertEqual(r.returncode, 0, r.stderr[-400:])
                dumps.append(json.loads(r.stdout))
            for other in dumps[1:]:
                for key in sorted(dumps[0]):
                    self.assertEqual(dumps[0][key], other[key],
                                     f"{fixture}: `{key}` varies by hash seed")


if __name__ == "__main__":
    if "--dump" in sys.argv:
        print(json.dumps(capture(sys.argv[sys.argv.index("--dump") + 1]),
                         sort_keys=True))
        sys.exit(0)
    if "--update" in sys.argv:
        GOLDEN.mkdir(exist_ok=True)
        for name in FIXTURES:
            golden_path(name).write_text(
                json.dumps(capture(name), indent=1, sort_keys=True,
                           ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"wrote {golden_path(name)}")
        sys.exit(0)
    unittest.main()
