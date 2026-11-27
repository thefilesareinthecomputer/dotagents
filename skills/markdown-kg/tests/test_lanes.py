#!/usr/bin/env python3
"""Tests for the lanes model: graph discovery (`graphs`), the scope line
every read command prints, and the widen line after a zero-result answer.

Each test builds a small workspace in a temp folder: a repo marker, a
`docs/` lane and a `kb/` lane, and a `PROJECTS/` workspace where needed."""
import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import markdown_kg as kg


def run(*argv: str) -> tuple[int, str, str]:
    """One engine call in-process: (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = kg.main(list(argv))
        except SystemExit as e:
            if isinstance(e.code, int) or e.code is None:
                rc = e.code or 0
            else:
                rc = 1
                err.write(str(e.code))
    return rc, out.getvalue(), err.getvalue()


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class Workspace(unittest.TestCase):
    """A repo with `docs/` (graph) and `kb/` (notes, graph on demand)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mdkg-lanes-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = self.tmp / "repo"
        (self.root / ".git").mkdir(parents=True)
        self.docs = self.root / "docs"
        self.kb = self.root / "kb"
        write(self.docs / "SPEC.md", "# Spec\n\nThe water system.\n")
        write(self.kb / "notes-learnings.md", "# Learnings\n\nSoil notes.\n")
        self.assertEqual(run("ingest", str(self.docs))[0], 0)

    def ingest_kb(self):
        self.assertEqual(run("ingest", str(self.kb))[0], 0)


class WorkspaceRootTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mdkg-root-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_stops_at_the_repo_root(self):
        (self.tmp / "r" / ".git").mkdir(parents=True)
        deep = self.tmp / "r" / "docs" / "adr"
        deep.mkdir(parents=True)
        self.assertEqual(kg.workspace_root(deep), self.tmp / "r")

    def test_a_projects_folder_stops_the_walk_before_a_repo_above(self):
        (self.tmp / ".git").mkdir()
        vault = self.tmp / "ws" / "PROJECTS" / "ALPHA"
        vault.mkdir(parents=True)
        self.assertEqual(kg.workspace_root(vault), self.tmp / "ws")

    def test_never_above_the_home_folder(self):
        (self.tmp / ".git").mkdir()
        home = self.tmp / "home"
        inside = home / "notes"
        inside.mkdir(parents=True)
        with mock.patch.object(Path, "home", return_value=home):
            self.assertEqual(kg.workspace_root(inside), home)

    def test_a_file_starts_from_its_folder(self):
        (self.tmp / ".git").mkdir()
        f = write(self.tmp / "kb" / "a.md", "# A\n")
        self.assertEqual(kg.workspace_root(f), self.tmp)


class DiscoveryTests(Workspace):
    def test_lists_graphs_and_unindexed_lanes_by_label(self):
        found = kg.discover_graphs(self.kb)
        self.assertEqual(found["root"], str(self.root))
        self.assertEqual([g["label"] for g in found["graphs"]], ["docs"])
        self.assertEqual([n["label"] for n in found["not_indexed"]], ["kb"])
        self.ingest_kb()
        found = kg.discover_graphs(self.kb)
        self.assertEqual([g["label"] for g in found["graphs"]], ["docs", "kb"])
        self.assertEqual(found["not_indexed"], [])
        self.assertTrue(all(g["ingested_at"] for g in found["graphs"]))

    def test_a_lane_with_only_contract_files_is_not_unindexed(self):
        shutil.rmtree(self.kb)
        write(self.kb / "AGENTS.md", "# contract\n")
        write(self.kb / "README.md", "# readme\n")
        self.assertEqual(kg.discover_graphs(self.root)["not_indexed"], [])

    def test_a_legacy_docs_kb_graph_carries_the_move_hint(self):
        legacy = self.docs / "kb"
        write(legacy / "index.md", "# Index\n")
        self.assertEqual(run("ingest", str(legacy))[0], 0)
        rows = kg.discover_graphs(self.root)["graphs"]
        self.assertEqual(rows[-1]["label"], "docs/kb")
        self.assertTrue(rows[-1]["legacy"])
        self.assertIn("move docs/kb/ to kb/", rows[-1]["hint"])
        rc, out, _ = run("graphs", str(self.root))
        self.assertEqual(rc, 0)
        self.assertIn("docs/kb", out)
        self.assertIn("LEGACY", out)

    def test_projects_workspace_spots(self):
        ws = self.tmp / "ws"
        (ws / "PROJECTS").mkdir(parents=True)
        alpha = ws / "PROJECTS" / "ALPHA"
        write(alpha / "index.md", "# Alpha\n")
        write(ws / "PROJECTS" / "BETA" / "kb" / "notes-a.md", "# B\n")
        self.assertEqual(run("ingest", str(alpha))[0], 0)
        found = kg.discover_graphs(alpha)
        self.assertEqual([g["label"] for g in found["graphs"]],
                         ["PROJECTS/ALPHA"])
        self.assertEqual([n["label"] for n in found["not_indexed"]],
                         ["PROJECTS/BETA", "PROJECTS/BETA/kb"])

    def test_graphs_json(self):
        rc, out, _ = run("graphs", str(self.docs / "SPEC.md"), "--json")
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(sorted(data), ["graphs", "not_indexed", "root"])
        self.assertEqual(data["graphs"][0]["label"], "docs")
        self.assertFalse(data["graphs"][0]["legacy"])

    def test_graphs_refuses_a_missing_path(self):
        rc, _, err = run("graphs", str(self.root / "nope"))
        self.assertEqual(rc, 1)
        self.assertIn("path not found", err)


class ScopeLineTests(Workspace):
    def test_text_output_starts_with_the_scope_line(self):
        self.ingest_kb()
        rc, out, _ = run("search", str(self.docs), "water")
        self.assertEqual(rc, 0)
        first = out.splitlines()[0]
        self.assertRegex(first, r"^scope: docs \(ingested \S+\); "
                                r"not searched: kb; not indexed: none$")

    def test_unindexed_lane_is_named(self):
        rc, out, _ = run("stats", str(self.docs))
        self.assertEqual(rc, 0)
        self.assertTrue(out.startswith("scope: docs "))
        self.assertIn("not searched: none; not indexed: kb", out.splitlines()[0])

    def test_json_stdout_is_unchanged_and_scope_goes_to_stderr(self):
        self.ingest_kb()
        for argv in (("search", str(self.docs), "water"),
                     ("query", str(self.docs), "water"),
                     ("links", str(self.docs), "--unresolved"),
                     ("backlinks", str(self.docs), "SPEC"),
                     ("refs", str(self.docs), "x.png"),
                     ("stats", str(self.docs))):
            rc, out, err = run(*argv, "--json")
            self.assertEqual(rc, 0, argv)
            payload = json.loads(out)
            self.assertNotIn("scope", payload if isinstance(payload, dict)
                             else {}, argv)
            scope = json.loads(err.strip().splitlines()[-1])["scope"]
            self.assertEqual(scope["searched"][0]["graph"], "docs")
            self.assertEqual(scope["not_searched"], ["kb"])
            self.assertEqual(scope["not_indexed"], [])
            # links and stats run the tracked-state check; the marker here
            # is not a real work tree, so it ran and found no git.
            want = False if argv[0] in ("links", "stats") else None
            self.assertIs(scope["git"], want, argv)

    def test_json_stdout_matches_the_library_answer(self):
        rc, out, _ = run("query", str(self.docs), "water", "--json")
        lib = kg.query(self.docs, "water")
        self.assertEqual([r["section_id"] for r in json.loads(out)],
                         [r["section_id"] for r in lib])


class WidenLineTests(Workspace):
    def test_search_widens_with_all(self):
        self.ingest_kb()
        rc, out, _ = run("search", str(self.docs), "zebra")
        self.assertEqual(rc, 0)
        lines = out.splitlines()
        self.assertEqual(lines[1], "no matches for 'zebra'")
        self.assertTrue(lines[2].startswith("This covers only docs. To widen: python3 "))
        self.assertTrue(lines[2].endswith(" search " + str(self.docs) + " zebra --all")
                        or lines[2].endswith(" zebra --all"), lines[2])

    def test_query_widens_per_graph(self):
        self.ingest_kb()
        rc, out, _ = run("query", str(self.docs), "zebra")
        widen = out.splitlines()[-1]
        self.assertIn("To widen: python3 ", widen)
        self.assertIn(" query ", widen)
        self.assertIn("kb", widen)
        self.assertNotIn("--all", widen)

    def test_unindexed_lane_widens_by_indexing_it(self):
        rc, out, _ = run("links", str(self.docs), "--unresolved")
        self.assertEqual(out.splitlines()[1], "no outbound links")
        widen = out.splitlines()[2]
        self.assertIn(" init ", widen)
        self.assertIn(" && python3 ", widen)
        self.assertIn(" ingest ", widen)

    def test_alone_says_nothing_else_was_found(self):
        shutil.rmtree(self.kb)
        rc, out, _ = run("refs", str(self.docs), "missing.png")
        self.assertEqual(out.splitlines()[-1],
                         "This covers only docs; no other graph was found.")

    def test_json_mode_prints_no_widen_line(self):
        rc, out, err = run("search", str(self.docs), "zebra", "--json")
        self.assertNotIn("To widen", out + err)


class FederationTests(Workspace):
    def setUp(self):
        super().setUp()
        write(self.kb / "notes-learnings.md",
              "# Learnings\n\n## Water\n\nThe water pump needs priming."
              " See [the spec](../docs/SPEC.md) and [app](../src/app.py).\n")
        write(self.root / "src" / "app.py", "x = 1\n")
        self.ingest_kb()

    def test_search_all_labels_and_fuses_hits_from_every_graph(self):
        rc, out, err = run("search", str(self.docs), "water", "--all", "--json")
        self.assertEqual(rc, 0, err)
        res = json.loads(out)
        self.assertEqual({h["graph"] for h in res["results"]}, {"docs", "kb"})
        self.assertEqual(res["rung"], "fused")
        self.assertEqual([g["graph"] for g in res["graphs"]], ["docs", "kb"])
        # Rank 1 in each graph ties; the first graph in scope order wins.
        self.assertEqual(res["results"][0]["graph"], "docs")
        scope = json.loads(err.strip().splitlines()[-1])["scope"]
        self.assertEqual([g["graph"] for g in scope["searched"]], ["docs", "kb"])
        self.assertEqual(scope["not_searched"], [])
        rc, out, _ = run("search", str(self.docs), "water", "--all")
        self.assertTrue(any(line.startswith("[kb] ") for line in out.splitlines()))

    def test_graphs_flag_picks_labels_and_refuses_unknown_ones(self):
        rc, out, _ = run("search", str(self.docs), "pump", "--graphs", "kb",
                         "--json")
        self.assertEqual(rc, 0)
        self.assertEqual({h["graph"] for h in json.loads(out)["results"]},
                         {"kb"})
        rc, _, err = run("search", str(self.docs), "pump", "--graphs", "nope")
        self.assertEqual(rc, 1)
        self.assertIn("no graph labeled 'nope'", err)

    def test_session_and_slot_are_refused_across_graphs(self):
        for flag in (("--session", "s1"), ("--slot", "superseded")):
            rc, _, err = run("search", str(self.docs), "water", "--all", *flag)
            self.assertEqual(rc, 1)
            self.assertIn(flag[0], err)

    def test_budget_applies_after_fusion(self):
        rc, out, _ = run("search", str(self.docs), "water", "--all",
                         "--budget", "4000", "--json")
        res = json.loads(out)
        self.assertLessEqual(res["spent"], 4000)
        self.assertTrue(all("text" in h for h in res["results"]))

    def test_siblings_are_never_written(self):
        db = kg.db_path(self.kb)
        files = lambda: sorted(p.name for p in db.parent.iterdir())
        before = (db.stat().st_mtime_ns, kg.graph_ingested_at(self.kb), files())
        write(self.kb / "notes-questions.md", "# Questions\n\nWater?\n")
        run("search", str(self.docs), "water", "--all")
        run("refs", str(self.docs), "../src/app.py", "--all")
        self.assertEqual((db.stat().st_mtime_ns,
                          kg.graph_ingested_at(self.kb), files()), before)

    def test_read_graph_opens_a_hit_from_another_graph(self):
        rc, out, _ = run("search", str(self.docs), "pump", "--all", "--json")
        hit = next(h for h in json.loads(out)["results"] if h["graph"] == "kb")
        rc, out, err = run("read", str(self.docs), hit["section_id"],
                           "--graph", "kb", "--json")
        self.assertEqual(rc, 0, err)
        self.assertIn("priming", json.loads(out)["text"])
        rc, _, err = run("read", str(self.docs), hit["section_id"],
                         "--graph", "kb", "--session", "s")
        self.assertEqual(rc, 1)

    def test_backlinks_all_finds_links_from_sibling_graphs(self):
        rc, out, _ = run("backlinks", str(self.docs), "SPEC", "--json")
        self.assertEqual(json.loads(out), [])
        rc, out, _ = run("backlinks", str(self.docs), "SPEC", "--all", "--json")
        rows = json.loads(out)
        self.assertEqual([(r["graph"], r["src"], r["kind"]) for r in rows],
                         [("kb", "notes-learnings", "file")])

    def test_refs_all_finds_links_to_a_file_from_sibling_graphs(self):
        rc, out, _ = run("refs", str(self.docs), "../src/app.py", "--all")
        self.assertEqual(rc, 0)
        self.assertIn("[kb] notes-learnings", out)

    def test_a_widened_search_with_nothing_left_says_so(self):
        rc, out, _ = run("search", str(self.docs), "zebra", "--all")
        self.assertEqual(out.splitlines()[-1],
                         "This covers only docs, kb; no other graph was found.")


def git(cwd: Path, *argv: str) -> None:
    subprocess.run(["git", "-c", "user.email=t@example.com", "-c",
                    "user.name=t", "-c", "commit.gpgsign=false", *argv],
                   cwd=cwd, check=True, capture_output=True, timeout=60)


@unittest.skipUnless(shutil.which("git"), "needs git")
class LinkStatusTests(unittest.TestCase):
    """A real repo: `docs/` committed, `kb/` untracked, `tasks/` tracked
    and held back."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mdkg-status-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = self.tmp / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q")
        self.docs = self.root / "docs"
        write(self.root / "kb" / "notes.md", "# Notes\n")
        write(self.root / "tasks" / "plan.md", "# Plan\n")
        write(self.root / "src" / "app.py", "x = 1\n")
        write(self.docs / "guide.md", "# Guide\n\nSee [the app](../src/app.py).\n")
        git(self.root, "add", "docs", "tasks", "src")
        git(self.root, "commit", "-q", "-m", "init")

    def links(self, *argv: str) -> tuple[int, list, dict]:
        self.assertEqual(run("ingest", str(self.docs))[0], 0)
        rc, out, err = run("links", str(self.docs), *argv, "--json")
        scope = json.loads(err.strip().splitlines()[-1])["scope"]
        return rc, json.loads(out), scope

    def cite(self, body: str, commit: bool = True) -> None:
        write(self.docs / "cite.md", "# Cite\n\n" + body + "\n")
        if commit:
            git(self.root, "add", "docs/cite.md")

    def test_a_committed_note_linking_an_untracked_file_is_forbidden(self):
        self.cite("See [notes](../kb/notes.md).")
        rc, rows, scope = self.links("--forbidden")
        self.assertEqual(rc, 3)
        self.assertTrue(scope["git"])
        self.assertEqual([(r["src"], r["dst"], r["syntax"]) for r in rows],
                         [("cite", "kb/notes.md", "md")])
        # Staging the target settles it on the next query, with no ingest.
        git(self.root, "add", "kb/notes.md")
        rc, out, _ = run("links", str(self.docs), "--forbidden", "--json")
        self.assertEqual((rc, json.loads(out)), (0, []))
        rc, out, _ = run("links", str(self.docs), "cite", "--json")
        self.assertEqual([r["status"] for r in json.loads(out)], ["external"])

    def test_held_back_targets_are_not_committed(self):
        self.cite("See [plan](../tasks/plan.md).")
        self.assertEqual(self.links("--forbidden")[0], 0)
        kg.write_config(self.docs, {"holdback": ["tasks/"]})
        rc, rows, _ = self.links("--forbidden")
        self.assertEqual(rc, 3)
        self.assertEqual(rows[0]["dst"], "tasks/plan.md")
        rc, out, _ = run("config", str(self.docs))
        self.assertIn("holdback: tasks/", out)

    def test_targets_outside_the_repo_are_never_forbidden(self):
        outside = self.tmp / "secret.txt"
        outside.write_text("x\n")
        self.cite("[s](../../secret.txt) and `../../secret.txt` and `../secret.txt`")
        rc, rows, _ = self.links("--forbidden")
        self.assertEqual((rc, rows), (0, []))
        _, rows, _ = self.links("cite")
        self.assertEqual([r["status"] for r in rows if r["kind"] == "file"],
                         ["external"])

    def test_holdback_anchoring_follows_gitignore(self):
        self.assertTrue(kg.held_back("tasks/plan.md", ["tasks/"]))
        self.assertTrue(kg.held_back("docs/tasks/x.md", ["tasks/"]))
        self.assertTrue(kg.held_back("tasks/plan.md", ["/tasks/"]))
        self.assertFalse(kg.held_back("docs/tasks/x.md", ["/tasks/"]))
        self.assertTrue(kg.held_back("_RESEARCH/a/b.md", ["/_RESEARCH/"]))
        self.assertFalse(kg.held_back("docs/a.md", ["/tasks/", "/_RESEARCH/"]))

    def test_outside_git_the_empty_answer_says_the_check_did_not_run(self):
        shutil.rmtree(self.root / ".git")
        self.assertEqual(run("ingest", str(self.docs))[0], 0)
        rc, out, _ = run("links", str(self.docs), "--forbidden")
        self.assertEqual(rc, 0)
        self.assertIn("the check did not run", out)

    def test_an_uncommitted_source_is_never_forbidden(self):
        self.cite("See [notes](../kb/notes.md).", commit=False)
        rc, rows, _ = self.links("--forbidden")
        self.assertEqual((rc, rows), (0, []))

    def test_missing_targets_are_unresolved_and_external_ones_are_not(self):
        self.cite("[gone](../src/gone.py) and [app](../src/app.py)"
                  " and [local](guide.md)")
        rc, rows, _ = self.links("--unresolved")
        self.assertEqual(rc, 0)
        self.assertEqual([(r["target"], r["status"]) for r in rows
                          if r["kind"] == "file"],
                         [("../src/gone.py", "unresolved")])
        _, rows, _ = self.links("cite")
        self.assertEqual(sorted((r["target"], r["status"]) for r in rows
                                if r["kind"] == "file"),
                         [("../src/app.py", "external"),
                          ("../src/gone.py", "unresolved")])

    def test_code_spans_naming_an_uncommitted_file(self):
        self.cite("Steps in `kb/notes.md:3`, the lane `kb/`, and `src/app.py`.")
        rc, rows, _ = self.links("--forbidden")
        self.assertEqual(rc, 3)
        self.assertEqual([(r["syntax"], r["target"], r["dst"]) for r in rows],
                         [("code", "kb/notes.md:3", "kb/notes.md")])

    def test_a_path_wikilink_is_a_file_link(self):
        self.cite("See [[../kb/notes]].")
        _, rows, _ = self.links("cite")
        self.assertEqual([(r["kind"], r["syntax"], r["dst"], r["status"])
                          for r in rows],
                         [("file", "wiki", "kb/notes.md", "forbidden")])

    def test_stats_counts_file_links_by_status(self):
        self.cite("[a](../src/app.py) [b](../kb/notes.md) [c](../nope.md)"
                  " [d](guide.md)")
        self.assertEqual(run("ingest", str(self.docs))[0], 0)
        rc, out, _ = run("stats", str(self.docs), "--json")
        self.assertEqual(json.loads(out)["file_links"],
                         {"resolved": 0, "external": 2, "forbidden": 1,
                          "unresolved": 1})

    def test_outside_a_repo_nothing_is_forbidden(self):
        shutil.rmtree(self.root / ".git")
        self.cite("See [notes](../kb/notes.md).", commit=False)
        rc, rows, scope = self.links("--forbidden")
        self.assertEqual((rc, rows), (0, []))
        self.assertFalse(scope["git"])

    def test_a_bad_holdback_value_is_refused(self):
        self.assertEqual(run("ingest", str(self.docs))[0], 0)
        cfg = kg.config_path(self.docs)
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps({"holdback": "tasks/"}), encoding="utf-8")
        rc, _, err = run("links", str(self.docs), "--forbidden")
        self.assertEqual(rc, 1)
        self.assertIn("'holdback' must be a list", err)


if __name__ == "__main__":
    unittest.main()
