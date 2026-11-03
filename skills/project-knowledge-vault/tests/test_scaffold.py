"""Scaffolder: seeds 18 files, never overwrites, is byte-identical across runs, and seeds the graph."""
from __future__ import annotations

import filecmp
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCAFFOLD = SKILL / "scripts" / "vault_scaffold.py"
TEMPLATE = SKILL / "templates" / "knowledge-vault"
BRD = SKILL / "templates" / "templates" / "brd.md"
# The vault filename of every seed file, mapped to its one source copy.
SEEDS = {**{p.name: p for p in TEMPLATE.iterdir() if not p.name.startswith(".")}, "00-brd.md": BRD}
PROFILES = SKILL / "templates" / "markdown-kg-profiles.md"
KG = SKILL.parent / "markdown-kg" / "scripts" / "markdown_kg.py"
SEED_COUNT = 18
DELIVERABLES = SKILL / "templates" / "deliverables"
# The deliverables folder's path for every seed file, mapped to its source, and the folders it makes.
DELIVERABLE_SEEDS = {**{p.name: p for p in DELIVERABLES.iterdir() if not p.name.startswith(".")},
                     **{f"templates/{n}": SKILL / "templates" / "templates" / n for n in ("adr.md", "solution-design.md")}}
DELIVERABLE_FOLDERS = ("adrs", "solution-designs")
DELIVERABLE_COUNT = len(DELIVERABLE_SEEDS) + len(DELIVERABLE_FOLDERS)
needs_kg = unittest.skipUnless(KG.exists(), "markdown-kg not installed beside this skill")


def run(*args: str, graph: bool = False) -> subprocess.CompletedProcess:
    extra = [] if graph else ["--no-graph"]
    return subprocess.run([sys.executable, str(SCAFFOLD), *args, *extra], capture_output=True, text=True)


def config_rows(vault: Path) -> dict:
    text = (vault / "markdown-kg" / "markdown-kg-config.md").read_text()
    return json.loads(re.search(r"```json\n(.*?)```", text, re.S).group(1))


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)


class TestSeed(Base):
    def test_seed_writes_every_template_file(self) -> None:
        result = run("--target", str(self.tmp), "--name", "TEST")
        self.assertEqual(result.returncode, 0, result.stderr)
        dest = self.tmp / "PROJECTS" / "TEST"
        names = sorted(p.name for p in dest.iterdir())
        self.assertEqual(names, sorted(SEEDS))
        self.assertEqual(len(names), SEED_COUNT)
        for name, src in SEEDS.items():
            self.assertTrue(filecmp.cmp(src, dest / name, shallow=False), name)

    def test_rerun_skips_everything_and_writes_nothing(self) -> None:
        run("--target", str(self.tmp), "--name", "TEST")
        dest = self.tmp / "PROJECTS" / "TEST"
        (dest / "00-brd.md").write_text("edited by hand\n")
        before = {p.name: p.stat().st_mtime_ns for p in dest.iterdir()}
        result = run("--target", str(self.tmp), "--name", "TEST")
        self.assertEqual(result.returncode, 0)
        # a summary line per folder plus one per file and deliverables folder
        self.assertEqual(result.stdout.count("skipped"), SEED_COUNT + DELIVERABLE_COUNT + 2)
        self.assertEqual((dest / "00-brd.md").read_text(), "edited by hand\n")
        self.assertEqual({p.name: p.stat().st_mtime_ns for p in dest.iterdir()}, before)

    def test_partial_vault_gets_only_the_gaps(self) -> None:
        dest = self.tmp / "PROJECTS" / "TEST"
        dest.mkdir(parents=True)
        (dest / "index.md").write_text("mine\n")
        result = run("--target", str(self.tmp), "--name", "TEST")
        self.assertEqual(result.returncode, 0)
        self.assertEqual((dest / "index.md").read_text(), "mine\n")
        self.assertEqual(len(list(dest.iterdir())), SEED_COUNT)

    def test_an_older_run_sheet_name_fills_the_role(self) -> None:
        for older in ("user-stories-runsheet.md", "user-stories-tasks.md"):
            with self.subTest(older=older), tempfile.TemporaryDirectory() as d:
                tmp = Path(d)
                dest = tmp / "PROJECTS" / "TEST"
                dest.mkdir(parents=True)
                (dest / older).write_text("the existing run sheet\n")
                result = run("--target", str(tmp), "--name", "TEST")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse((dest / "user-runsheet.md").exists())
                self.assertIn(f"user-runsheet.md (the vault already has {older}", result.stdout)
                self.assertEqual(len(list(dest.iterdir())), SEED_COUNT)  # the older name stands in for the new one

    def test_older_split_chat_files_fill_the_general_notes_role(self) -> None:
        for older in ("notes-chat-notes-client.md", "notes-chat-notes-internal.md"):
            with self.subTest(older=older), tempfile.TemporaryDirectory() as d:
                dest = Path(d) / "PROJECTS" / "TEST"
                dest.mkdir(parents=True)
                (dest / older).write_text("the existing chat log\n")
                result = run("--target", d, "--name", "TEST")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse((dest / "notes-general-notes.md").exists())
                self.assertIn(f"notes-general-notes.md (the vault already has {older}", result.stdout)

    def test_dry_run_writes_nothing(self) -> None:
        result = run("--target", str(self.tmp), "--name", "TEST", "--dry-run")
        self.assertEqual(result.returncode, 0)
        self.assertFalse((self.tmp / "PROJECTS").exists())
        self.assertEqual(result.stdout.count("would write"), SEED_COUNT + DELIVERABLE_COUNT + 2)

    def test_two_seeds_are_byte_identical(self) -> None:
        run("--target", str(self.tmp / "a"), "--name", "X")
        run("--target", str(self.tmp / "b"), "--name", "X")
        cmp = filecmp.dircmp(self.tmp / "a" / "PROJECTS" / "X", self.tmp / "b" / "PROJECTS" / "X")
        self.assertFalse(cmp.diff_files or cmp.left_only or cmp.right_only)

    def test_seed_prints_the_pointer_relative_to_the_host_repo(self) -> None:
        repo = self.tmp / "repo"
        (repo / ".git").mkdir(parents=True)
        result = run("--target", str(repo), "--name", "TEST")
        self.assertIn("Project knowledge vault: `PROJECTS/TEST/`", result.stdout)
        self.assertIn("`PROJECTS/TEST/markdown-kg/`", result.stdout)
        self.assertIn("persistent memory", result.stdout)
        self.assertNotIn(str(self.tmp), result.stdout.split("next:", 1)[1])
        into = run("--into", str(repo / "docs" / "vault"))
        self.assertIn("Project knowledge vault: `docs/vault/`", into.stdout)
        self.assertNotIn("next:", run("--target", str(repo), "--name", "DRY", "--dry-run").stdout)

    def test_name_must_be_a_single_visible_folder(self) -> None:
        for bad in ("a/b", ".hidden", "..", "tab\there"):
            with self.subTest(name=bad):
                self.assertEqual(run("--target", str(self.tmp), "--name", bad).returncode, 2)


class TestInto(Base):
    """--into seeds the vault into the named folder itself, such as a code repo's docs/."""

    def test_into_seeds_the_folder_itself(self) -> None:
        dest = self.tmp / "repo" / "docs"
        result = run("--into", str(dest))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(p.name for p in dest.iterdir()), sorted(SEEDS))
        self.assertFalse((self.tmp / "repo" / "PROJECTS").exists())
        self.assertFalse((dest / "PROJECTS").exists())

    def test_into_rerun_fills_gaps_and_keeps_edits(self) -> None:
        dest = self.tmp / "docs"
        run("--into", str(dest))
        (dest / "00-brd.md").write_text("edited by hand\n")
        (dest / "log.md").unlink()
        result = run("--into", str(dest))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((dest / "00-brd.md").read_text(), "edited by hand\n")
        self.assertTrue((dest / "log.md").exists())

    def test_into_refuses_a_folder_with_its_own_agent_rules(self) -> None:
        for name, text in (("AGENTS.md", "# Docs folder rules\n"), ("CLAUDE.md", "Repo notes for Claude.\n")):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as d:
                dest = Path(d) / "docs"
                dest.mkdir()
                (dest / name).write_text(text)
                result = run("--into", str(dest))
                self.assertEqual(result.returncode, 1)
                self.assertIn(name, result.stdout)
                self.assertEqual([p.name for p in dest.iterdir()], [name])
                self.assertEqual((dest / name).read_text(), text)

    def test_into_refuses_a_symlinked_or_lookalike_rules_file(self) -> None:
        outside = self.tmp / "repo-rules.md"
        outside.write_text("# Project Knowledge Vault - the contract\n")
        cases = (("AGENTS.md", lambda p: p.symlink_to(outside)),
                 ("CLAUDE.md", lambda p: p.write_text("@AGENTS.md\n\nRepo notes for Claude.\n")))
        for name, make in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as d:
                dest = Path(d) / "docs"
                dest.mkdir()
                make(dest / name)
                result = run("--into", str(dest))
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertEqual([p.name for p in dest.iterdir()], [name])

    def test_into_accepts_the_contract_it_wrote(self) -> None:
        dest = self.tmp / "docs"
        run("--into", str(dest))
        (dest / "index.md").unlink()
        result = run("--into", str(dest))
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((dest / "index.md").exists())

    def test_into_dry_run_writes_nothing(self) -> None:
        dest = self.tmp / "docs"
        result = run("--into", str(dest), "--dry-run")
        self.assertEqual(result.returncode, 0)
        self.assertFalse(dest.exists() or (self.tmp / "docs-DELIVERABLES").exists())
        self.assertEqual(result.stdout.count("would write"), SEED_COUNT + DELIVERABLE_COUNT + 2)

    def test_into_symlinked_folder_is_refused(self) -> None:
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        (self.tmp / "docs").symlink_to(elsewhere)
        result = run("--into", str(self.tmp / "docs"))
        self.assertEqual(result.returncode, 1)
        self.assertFalse(any(elsewhere.iterdir()))

    def test_into_and_target_are_exclusive_and_one_is_required(self) -> None:
        for args in ((), ("--name", "X"), ("--target", str(self.tmp)),
                     ("--into", str(self.tmp / "d"), "--target", str(self.tmp), "--name", "X"),
                     ("--into", str(self.tmp / "d"), "--name", "X")):
            with self.subTest(args=args):
                self.assertEqual(run(*args).returncode, 2)

    @needs_kg
    def test_into_seeds_the_graph_in_the_folder(self) -> None:
        dest = self.tmp / "docs"
        result = run("--into", str(dest), graph=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((dest / "markdown-kg" / "markdown-kg-config.md").is_file())
        self.assertIn("*.db*", (dest / "markdown-kg" / ".gitignore").read_text())


class TestDeliverables(Base):
    """Every vault gets a sibling <vault>-DELIVERABLES/ folder for the documents the project ships."""

    def test_seed_writes_the_deliverables_folder_beside_the_vault(self) -> None:
        result = run("--target", str(self.tmp), "--name", "TEST")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        out = self.tmp / "PROJECTS" / "TEST-DELIVERABLES"
        for name, src in DELIVERABLE_SEEDS.items():
            self.assertTrue(filecmp.cmp(src, out / name, shallow=False), name)
        for folder in DELIVERABLE_FOLDERS:
            self.assertTrue((out / folder).is_dir(), folder)
        self.assertFalse((self.tmp / "PROJECTS" / "TEST" / "adrs").exists())

    def test_rerun_keeps_the_deliverables_and_their_edits(self) -> None:
        run("--target", str(self.tmp), "--name", "TEST")
        out = self.tmp / "PROJECTS" / "TEST-DELIVERABLES"
        (out / "index.md").write_text("edited by hand\n")
        (out / "adrs" / "ADR-001-example.md").write_text("a record\n")
        result = run("--target", str(self.tmp), "--name", "TEST")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual((out / "index.md").read_text(), "edited by hand\n")
        self.assertEqual((out / "adrs" / "ADR-001-example.md").read_text(), "a record\n")

    def test_symlinked_templates_folder_is_refused_not_followed(self) -> None:
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        out = self.tmp / "PROJECTS" / "TEST-DELIVERABLES"
        out.mkdir(parents=True)
        (out / "templates").symlink_to(elsewhere)
        result = run("--target", str(self.tmp), "--name", "TEST")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("symlink", result.stdout)
        self.assertFalse(any(elsewhere.iterdir()))

    def test_into_dot_puts_the_deliverables_beside_the_vault(self) -> None:
        vault = self.tmp / "v"
        vault.mkdir()
        result = subprocess.run([sys.executable, str(SCAFFOLD), "--into", ".", "--no-graph"],
                                capture_output=True, text=True, cwd=vault)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.tmp / "v-DELIVERABLES" / "AGENTS.md").is_file())
        self.assertFalse((vault / "v-DELIVERABLES").exists())

    def test_symlinked_deliverables_folder_is_refused(self) -> None:
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        (self.tmp / "PROJECTS").mkdir()
        (self.tmp / "PROJECTS" / "TEST-DELIVERABLES").symlink_to(elsewhere)
        result = run("--target", str(self.tmp), "--name", "TEST")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("symlink", result.stdout)
        self.assertFalse(any(elsewhere.iterdir()))

    @needs_kg
    def test_deliverables_graph_leaves_out_the_templates(self) -> None:
        result = run("--target", str(self.tmp), "--name", "TEST", graph=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        out = self.tmp / "PROJECTS" / "TEST-DELIVERABLES"
        self.assertTrue((out / "markdown-kg" / "markdown-kg-config.md").is_file())
        found = subprocess.run([sys.executable, str(KG), "search", str(out), "decision options", "--json"],
                               capture_output=True, text=True)
        self.assertEqual(found.returncode, 0, found.stderr)
        ids = [h["section_id"] for h in json.loads(found.stdout)["results"]]
        self.assertFalse(any(i.startswith(("templates/", "AGENTS", "CLAUDE")) for i in ids), ids)


class TestSymlinks(Base):
    def test_symlinked_file_is_refused_not_followed(self) -> None:
        dest = self.tmp / "PROJECTS" / "T"
        dest.mkdir(parents=True)
        outside = self.tmp / "OUTSIDE.md"
        (dest / "log.md").symlink_to(outside)
        result = run("--target", str(self.tmp), "--name", "T")
        self.assertEqual(result.returncode, 1)
        self.assertFalse(outside.exists())
        self.assertIn("log.md", result.stdout)
        self.assertIn("symlink", result.stdout)
        self.assertEqual(len([p for p in dest.iterdir() if not p.is_symlink()]), SEED_COUNT - 1)

    def test_symlinked_projects_dir_is_refused(self) -> None:
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        (self.tmp / "v").mkdir()
        (self.tmp / "v" / "PROJECTS").symlink_to(elsewhere)
        result = run("--target", str(self.tmp / "v"), "--name", "T")
        self.assertEqual(result.returncode, 1)
        self.assertFalse(any(elsewhere.iterdir()))

    @needs_kg
    def test_symlinked_graph_dir_is_refused(self) -> None:
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        vault = self.tmp / "v" / "PROJECTS" / "T"
        vault.mkdir(parents=True)
        (vault / "markdown-kg").symlink_to(elsewhere)
        result = run("--target", str(self.tmp / "v"), "--name", "T", graph=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("symlink", result.stdout)
        self.assertFalse(any(elsewhere.iterdir()))

    @needs_kg
    def test_symlinked_file_in_graph_dir_is_refused(self) -> None:
        self.assertEqual(run("--target", str(self.tmp / "a"), "--name", "A", graph=True).returncode, 0)
        other_db = self.tmp / "a" / "PROJECTS" / "A" / "markdown-kg" / "markdown-kg.db"
        before = other_db.read_bytes()
        kg_dir = self.tmp / "b" / "PROJECTS" / "B" / "markdown-kg"
        kg_dir.mkdir(parents=True)
        (kg_dir / "markdown-kg.db").symlink_to(other_db)
        result = run("--target", str(self.tmp / "b"), "--name", "B", graph=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("symlink", result.stdout)
        self.assertEqual(other_db.read_bytes(), before)


@needs_kg
class TestDryRunGraph(Base):
    def test_dry_run_on_a_new_vault_says_it_would_initialize(self) -> None:
        result = run("--into", str(self.tmp / "docs"), "--dry-run", graph=True)
        self.assertIn("graph: would initialize markdown-kg/", result.stdout)

    def test_dry_run_on_a_vault_with_a_graph_says_it_is_present(self) -> None:
        dest = self.tmp / "docs"
        (dest / "markdown-kg").mkdir(parents=True)
        (dest / "markdown-kg" / "markdown-kg-config.md").write_text("```json\n{}\n```\n")
        result = run("--into", str(dest), "--dry-run", graph=True)
        self.assertNotIn("docs: graph: would initialize", result.stdout)
        self.assertIn("docs: graph: markdown-kg/ present", result.stdout)

    def test_dry_run_reports_the_refusals_the_real_run_makes(self) -> None:
        dest = self.tmp / "docs"
        dest.mkdir()
        (dest / "markdown-kg").write_text("not a folder\n")
        dry = run("--into", str(dest), "--dry-run", graph=True)
        self.assertNotIn("docs: graph: would initialize", dry.stdout)
        self.assertIn("not a directory", dry.stdout)
        real = run("--into", str(dest), graph=True)
        self.assertEqual(real.returncode, 1)

    def test_dry_run_on_a_legacy_graph_says_it_would_skip(self) -> None:
        dest = self.tmp / "docs"
        (dest / "vault-kg").mkdir(parents=True)
        result = run("--into", str(dest), "--dry-run", graph=True)
        self.assertIn("legacy vault-kg/", result.stdout)


class TestGraph(Base):
    def test_seed_initializes_configures_and_ingests_the_graph(self) -> None:
        result = run("--target", str(self.tmp), "--name", "T", graph=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        vault = self.tmp / "PROJECTS" / "T"
        shipped = json.loads(re.search(r"```json\n(.*?)```", PROFILES.read_text(), re.S).group(1))
        rows = config_rows(vault)
        for key in ("ignore", "profiles"):
            self.assertLessEqual({r["path"] for r in shipped[key]}, {r["path"] for r in rows[key]}, key)
        found = subprocess.run([sys.executable, str(KG), "search", str(vault), "learning sweep", "--json"],
                               capture_output=True, text=True)
        self.assertEqual(found.returncode, 0, found.stderr)
        ids = [h["section_id"] for h in json.loads(found.stdout)["results"]]
        self.assertTrue(ids and not any(i.startswith(("AGENTS", "CLAUDE")) for i in ids), ids)
        self.assertEqual((vault / "markdown-kg" / ".gitignore").read_text(), "*.db*\n")

    def test_shipped_slots_survive_init_on_a_folder_with_dated_notes(self) -> None:
        # init writes an exact-path row for each dated log it finds, which would outrank notes-*.md
        vault = self.tmp / "PROJECTS" / "T"
        vault.mkdir(parents=True)
        entries = "".join(f"## 2026-10-{d:02d}-WEEKLY\n\nshipped the thing\n\n### ACTIONS\n- [ ] ship\n\n" for d in (21, 14))
        (vault / "notes-updates.md").write_text(f"---\ntype: reference\n---\n\n# UPDATES\n\n{entries}")
        result = run("--target", str(self.tmp), "--name", "T", graph=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        paths = [r["path"] for r in config_rows(vault)["profiles"]]
        self.assertNotIn("notes-updates.md", paths)
        self.assertEqual(paths.count("notes-*.md"), 1)
        found = subprocess.run([sys.executable, str(KG), "sections", str(vault), "notes-updates"],
                               capture_output=True, text=True)
        self.assertEqual(found.stdout.count("> ACTIONS"), 2, found.stdout)  # a routine slot, not rolled into the entry

    def test_legacy_graph_folder_is_reported_not_written(self) -> None:
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        vault = self.tmp / "v" / "PROJECTS" / "T"
        vault.mkdir(parents=True)
        (vault / "vault-kg").symlink_to(elsewhere)
        result = run("--target", str(self.tmp / "v"), "--name", "T", graph=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("legacy vault-kg/", result.stdout)
        self.assertFalse(any(elsewhere.iterdir()) or (vault / "markdown-kg").exists())
        (vault / "markdown-kg").write_text("")  # a file where the folder belongs
        result = run("--target", str(self.tmp / "v"), "--name", "T", graph=True)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("not a directory", result.stdout)
        self.assertFalse(any(elsewhere.iterdir()))

    def test_existing_gitignore_without_db_line_is_warned_not_rewritten(self) -> None:
        vault = self.tmp / "PROJECTS" / "T"
        (vault / "markdown-kg").mkdir(parents=True)
        (vault / "markdown-kg" / ".gitignore").write_text("*.log\n")
        result = run("--target", str(self.tmp), "--name", "T", graph=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("WARNING", result.stdout)
        self.assertEqual((vault / "markdown-kg" / ".gitignore").read_text(), "*.log\n")

    def test_leftover_temp_file_fails_with_a_fix(self) -> None:
        run("--target", str(self.tmp), "--name", "T", graph=True)
        kg_dir = self.tmp / "PROJECTS" / "T" / "markdown-kg"
        config = kg_dir / "markdown-kg-config.md"
        text = config.read_text().replace('"path": "index.md"', '"path": "index-gone.md"')
        config.write_text(text)
        (kg_dir / ".markdown-kg-config.md.tmp").write_text("stale\n")
        result = run("--target", str(self.tmp), "--name", "T", graph=True)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("delete it and re-run", result.stdout)
        self.assertEqual(config.read_text(), text)

    def test_malformed_config_fails_cleanly_and_is_left_intact(self) -> None:
        run("--target", str(self.tmp), "--name", "T", graph=True)
        config = self.tmp / "PROJECTS" / "T" / "markdown-kg" / "markdown-kg-config.md"
        for bad in ('["not", "an", "object"]', '{"profiles": ["not-a-row"]}', '{"ignore": {"path": "x"}}'):
            with self.subTest(config=bad):
                text = f"# markdown-kg-config\n\n```json\n{bad}\n```\n"
                config.write_text(text)
                result = run("--target", str(self.tmp), "--name", "T", graph=True)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertIn("could not configure", result.stdout)
                self.assertEqual(config.read_text(), text)

    def test_rerun_restores_only_missing_rows_and_keeps_the_operators(self) -> None:
        run("--target", str(self.tmp), "--name", "T", graph=True)
        vault = self.tmp / "PROJECTS" / "T"
        config = vault / "markdown-kg" / "markdown-kg-config.md"
        rows = config_rows(vault)
        rows["profiles"] = [r for r in rows["profiles"] if r["path"] != "index.md"]
        rows["profiles"].append({"path": "notes-learnings.md", "profile": "reference"})
        text = config.read_text()
        block = re.search(r"```json\n(.*?)```", text, re.S)
        config.write_text(text[:block.start(1)] + json.dumps(rows, indent=2) + "\n" + text[block.end(1):])
        result = run("--target", str(self.tmp), "--name", "T", graph=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("1 profile row(s) merged", result.stdout)
        paths = [r["path"] for r in config_rows(vault)["profiles"]]
        self.assertEqual(paths.count("index.md"), 1)
        self.assertIn("notes-learnings.md", paths)
        again = run("--target", str(self.tmp), "--name", "T", graph=True)
        self.assertEqual(again.returncode, 0, again.stdout)
        self.assertIn("nothing to ingest", again.stdout)


if __name__ == "__main__":
    unittest.main()
