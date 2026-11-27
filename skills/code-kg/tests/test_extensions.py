"""Tests for the config extension keys (components, declared links, markers),
the `config` check command, the interpreter floor, and `docs`, which joins
this graph with the markdown-kg skill's.

Behavior tests run against a temporary copy of tests/fixture-extend so the
committed fixture never grows a database.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import code_kg  # noqa: E402
from fixture_copy import copy_fixture  # noqa: E402

# Creating a symlink on Windows needs Developer Mode or admin rights.
needs_symlinks = unittest.skipIf(sys.platform == "win32",
                                 "symlinks need Developer Mode or admin rights on Windows")

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture-extend"


def run(*argv: str) -> tuple[int, str, str]:
    """One engine call in-process: (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = code_kg.main(list(argv))
        except SystemExit as e:
            if isinstance(e.code, int) or e.code is None:
                rc = e.code or 0
            else:
                rc = 1
                err.write(str(e.code))
    return rc, out.getvalue(), err.getvalue()


class TestStdlibNames(unittest.TestCase):
    """`sys.stdlib_module_names` is 3.10+; the stock macOS python3 is 3.9."""

    CORE = ("os", "json", "sqlite3", "re", "pathlib", "collections", "sys",
            "math", "email", "xml")

    def test_core_modules_present(self):
        names = code_kg._stdlib_names()
        for name in self.CORE:
            self.assertIn(name, names)

    def test_fallback_without_the_attribute(self):
        with mock.patch.object(sys, "stdlib_module_names", None, create=True):
            names = code_kg._stdlib_names()
        for name in self.CORE:
            self.assertIn(name, names)
        for name in ("site-packages", "__pycache__", "test", "lib-dynload",
                     "requests", "pip"):
            self.assertNotIn(name, names)

    def test_fallback_agrees_with_the_interpreter_list(self):
        real = getattr(sys, "stdlib_module_names", None)
        if real is None:
            self.skipTest("interpreter predates sys.stdlib_module_names")
        with mock.patch.object(sys, "stdlib_module_names", None):
            fallback = code_kg._stdlib_names()
        # The folder scan cannot see modules this platform does not build
        # (winreg, msvcrt), so agreement is checked one way.
        public = {n for n in fallback if not n.startswith("_")}
        self.assertEqual(public - set(real), set())
        self.assertGreater(len(public), 150)


class TestPyprojectScripts(unittest.TestCase):
    """`tomllib` is 3.11+; the line reader must agree with it."""

    TABLE = ('[build-system]\nrequires = ["setuptools"]\n\n[project]\n'
             'name = "x"\n\n[project.scripts]\n'
             'cli = "pkg.cli:main"  # comment\n'
             "'other-tool' = 'pkg.other:run'\n\n"
             '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
    INLINE = ('[project]\nname = "x"\n'
              'scripts = { cli = "pkg.cli:main", two = "pkg.two:go" }\n')

    def scripts_without_tomllib(self, text):
        with mock.patch.dict(sys.modules, {"tomllib": None}):
            return code_kg._pyproject_scripts(text)

    def test_table_form(self):
        self.assertEqual(self.scripts_without_tomllib(self.TABLE),
                         ["pkg.cli:main", "pkg.other:run"])

    def test_inline_form(self):
        self.assertEqual(self.scripts_without_tomllib(self.INLINE),
                         ["pkg.cli:main", "pkg.two:go"])

    def test_agrees_with_tomllib(self):
        try:
            import tomllib  # noqa: F401
        except ImportError:
            self.skipTest("interpreter predates tomllib")
        for text in (self.TABLE, self.INLINE):
            self.assertEqual(self.scripts_without_tomllib(text),
                             code_kg._pyproject_scripts(text))


class TestTermSafe(unittest.TestCase):
    """Every prose path is sanitized; kg_core's tests cover the escaping
    itself. Characters are built with chr() so this file holds none."""

    RLO, ZWSP = chr(0x202E), chr(0x200B)

    def test_error_messages_and_stderr_are_sanitized_too(self):
        tmp = Path(tempfile.mkdtemp(prefix="codekg-err-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "a.py").write_text("x = 1\n", encoding="utf-8")
        (tmp / ".kg").mkdir()
        esc, bel = chr(0x1B), chr(0x07)
        (tmp / ".kg" / "code-kg-config.json").write_text(json.dumps(
            {"profile": esc + "]52;c;eA==" + bel}), encoding="utf-8")
        rc, out, err = run("ingest", str(tmp))
        self.assertEqual(rc, 1)
        self.assertIn("unknown profile", err)
        for ch in (esc, bel):
            self.assertNotIn(ch, out + err)
        self.assertIn("\\x1b]52;c;eA==\\x07", err)

    def test_a_test_command_that_could_hide_itself_is_refused(self):
        tmp = Path(tempfile.mkdtemp(prefix="codekg-cmd-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "a.py").write_text("x = 1\n", encoding="utf-8")
        (tmp / ".kg").mkdir()
        for hidden in (chr(0x1B) + "[2K\r", self.RLO, self.ZWSP):
            (tmp / ".kg" / "code-kg-config.json").write_text(json.dumps(
                {"test_command": "sh -c 'echo hidden' " + hidden
                                 + "python3 -m pytest"}), encoding="utf-8")
            rc, out, err = run("coverage", str(tmp), "run")
            self.assertEqual(rc, 1)
            self.assertIn("'test_command' must be one line", err)
        (tmp / ".kg" / "code-kg-config.json").write_text(json.dumps(
            {"test_command": "python3 -m coverage run -m pytest -q"}),
            encoding="utf-8")
        self.assertEqual(code_kg.load_config(tmp)["test_command"],
                         "python3 -m coverage run -m pytest -q")

    def test_a_reordering_comment_is_shown_in_read_output(self):
        tmp = Path(tempfile.mkdtemp(prefix="codekg-safe-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "a.py").write_text(
            "# TODO: check " + self.RLO + "this\nx = 1" + self.ZWSP + "\n",
            encoding="utf-8")
        run("init", str(tmp))
        for cmd in (("read", "a.py"), ("annotations",), ("search", "check"),
                    ("stats",)):
            rc, out, _ = run(cmd[0], str(tmp), *cmd[1:])
            self.assertEqual(rc, 0, cmd)
            for ch in (self.RLO, self.ZWSP):
                self.assertNotIn(ch, out, cmd)
        rc, out, _ = run("read", str(tmp), "a.py")
        self.assertIn("check \\u202ethis", out)
        # The json path is for a parser and keeps the text as written.
        rc, out, _ = run("annotations", str(tmp), "--json")
        self.assertIn(self.RLO, json.loads(out)["rows"][0]["payload"])


class TestTomlFallbackBounds(unittest.TestCase):
    def test_hostile_lines_stay_fast(self):
        import time
        text = ("[a" + " " * 200000 + "x\n"
                + "[project]\nscripts = {" + "}x" * 100000 + "\n"
                + '[project.scripts]\ncli = "pkg.cli:main"\n')
        start = time.time()
        with mock.patch.dict(sys.modules, {"tomllib": None}):
            got = code_kg._pyproject_scripts(text)
        self.assertLess(time.time() - start, 2.0)
        self.assertEqual(got, ["pkg.cli:main"])

    def test_table_header_spacing(self):
        text = '[ project . scripts ]  # entry points\ncli = "a.b:c"\n'
        with mock.patch.dict(sys.modules, {"tomllib": None}):
            self.assertEqual(code_kg._pyproject_scripts(text), ["a.b:c"])


class RepoCase(unittest.TestCase):
    """Base: a temp copy of fixture-extend, with helpers to edit its config."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="codekg-ext-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = self.tmp / "repo"
        copy_fixture(FIXTURE, self.repo)
        self.cfg_file = self.repo / ".kg" / "code-kg-config.json"
        # Read commands refuse to run without a database; after this, a
        # config edit is picked up by the drift check on the next read.
        run("ingest", str(self.repo))

    def config(self) -> dict:
        return json.loads(self.cfg_file.read_text(encoding="utf-8"))

    def write_config(self, cfg) -> None:
        self.cfg_file.write_text(json.dumps(cfg), encoding="utf-8")

    def json(self, *argv: str):
        rc, out, err = run(argv[0], str(self.repo), *argv[1:], "--json")
        self.assertEqual(rc, 0, err)
        return json.loads(out)

    def edges(self, where: str = "1=1", *params):
        import sqlite3
        con = sqlite3.connect(code_kg.db_path(self.repo))
        rows = con.execute(
            "SELECT src, dst, kind, status FROM edges WHERE " + where
            + " ORDER BY src, dst, kind", params).fetchall()
        con.close()
        return rows


class TestConfigValidation(RepoCase):
    def rejects(self, cfg: dict, fragment: str) -> None:
        self.write_config(cfg)
        rc, _, err = run("ingest", str(self.repo))
        self.assertEqual(rc, 1)
        self.assertIn(fragment, err)

    def test_config_without_extension_keys_loads_as_before(self):
        self.write_config({"roots": ["web"]})
        cfg = code_kg.load_config(self.repo)
        self.assertEqual(cfg["roots"], ["web"])
        for key in code_kg.EXTENSION_KEYS:
            self.assertEqual(cfg[key], [])

    def test_init_scaffold_is_unchanged(self):
        self.cfg_file.unlink()
        run("init", str(self.repo))
        self.assertEqual(self.config(), code_kg.DEFAULT_CONFIG)

    def test_components_must_be_a_list(self):
        self.rejects({"components": {"name": "x"}}, "'components' must be")

    def test_component_needs_name_and_paths(self):
        self.rejects({"components": [{"paths": ["a/**"]}]}, "needs a 'name'")
        self.rejects({"components": [{"name": "a"}]}, "non-empty 'paths'")

    def test_component_names_and_aliases_are_unique(self):
        self.rejects({"components": [
            {"name": "core", "paths": ["a/**"]},
            {"name": "other", "aliases": ["Core"], "paths": ["b/**"]}]},
            "claimed by both")

    def test_control_characters_are_refused(self):
        self.rejects({"components": [
            {"name": "bad\u001b[31m", "paths": ["a/**"]}]}, "printable")
        self.rejects({"components": [
            {"name": "bad" + chr(0x202E) + "name", "paths": ["a/**"]}]},
            "printable")

    def test_paths_and_aliases_per_component_are_bounded(self):
        self.rejects({"components": [
            {"name": "wide", "paths": [f"d{i}/**" for i in range(51)]}]},
            "more than 50 paths or aliases")
        self.rejects({"components": [
            {"name": "wide", "paths": ["a/**"],
             "aliases": [f"alias{i}" for i in range(51)]}]},
            "more than 50 paths or aliases")

    def test_link_needs_both_sides_and_a_boolean_live(self):
        self.rejects({"links": [{"from": "a.py"}]}, "'from' and 'to'")
        self.rejects({"links": [{"from": "a.py", "to": "b.py",
                                 "live": "yes"}]}, "true or false")

    def test_marker_token_rules(self):
        self.rejects({"markers": ["lowercase"]}, "must be 2-32 chars")
        self.rejects({"markers": ["TODO"]}, "core marker")
        self.rejects({"markers": ["SAFETY", "SAFETY"]}, "registered twice")


class TestComponents(RepoCase):
    def test_member_counts(self):
        got = {c["name"]: c for c in self.json("components")["components"]}
        self.assertEqual({n: c["files"] for n, c in got.items()},
                         {"control": 4, "sensors": 3, "actuators": 3,
                          "reporting": 3, "dashboard": 2})

    def test_cross_component_edge_counts(self):
        got = {c["name"]: c for c in self.json("components")["components"]}
        # cli.py reaches both sensor modules and their package init; the
        # registry reaches the plugins through the declared live link.
        self.assertEqual(got["control"]["depends_on"],
                         {"actuators": 3, "reporting": 1, "sensors": 5})
        self.assertEqual(got["actuators"]["depends_on"],
                         {"control": 2, "reporting": 1, "sensors": 6})
        self.assertEqual(got["dashboard"]["depends_on"], {})
        self.assertEqual(got["sensors"]["used_by"],
                         {"actuators": 6, "control": 5, "reporting": 5})

    def test_overlaps_and_unassigned(self):
        got = self.json("components")
        self.assertEqual(got["overlaps"], [
            {"file": "greenhouse/sensors/humidity.py",
             "components": ["reporting", "sensors"]}])
        self.assertEqual(got["unassigned"], ["scripts/nightly.sh"])

    def test_detail_by_alias(self):
        got = self.json("components", "plugins")
        self.assertEqual(got["name"], "actuators")
        self.assertEqual([f["file"] for f in got["files"]],
                         ["greenhouse/plugins/__init__.py",
                          "greenhouse/plugins/misting.py",
                          "greenhouse/plugins/shade.py"])
        self.assertIn({"src": "greenhouse/registry.py",
                       "dst": "greenhouse/plugins/misting.py",
                       "kind": "declared-live", "component": "control"},
                      got["inbound"])

    def test_unknown_component_is_an_error(self):
        rc, _, err = run("components", str(self.repo), "nope")
        self.assertEqual(rc, 1)
        self.assertIn("unknown component", err)

    def test_no_components_declared(self):
        self.write_config({})
        self.assertEqual(self.json("components")["status"], "NO_COMPONENTS")
        rc, out, _ = run("components", str(self.repo))
        self.assertEqual(rc, 0)
        self.assertIn("no components declared", out)

    def test_text_render(self):
        rc, out, _ = run("components", str(self.repo))
        self.assertEqual(rc, 0)
        self.assertIn("control  (4 files", out)
        self.assertIn("depends on: actuators (3)", out)
        self.assertIn("source files in no component (1):", out)


class TestDeclaredLinks(RepoCase):
    PLUGINS = ["greenhouse/plugins/__init__.py",
               "greenhouse/plugins/misting.py", "greenhouse/plugins/shade.py"]

    def tiers(self) -> dict:
        return self.json("dead")["tiers"]

    def test_live_link_becomes_executable_edges(self):
        run("ingest", str(self.repo))
        self.assertEqual(
            self.edges("kind='declared-live'"),
            [("greenhouse/registry.py", p, "declared-live", "resolved")
             for p in self.PLUGINS])

    def test_live_link_makes_the_plugins_live(self):
        tiers = self.tiers()
        for p in self.PLUGINS:
            self.assertIn(p, tiers["live"])

    def test_weak_link_does_not_join_liveness(self):
        tiers = self.tiers()
        self.assertIn("greenhouse/reports/summary.py", tiers["weak-only"])
        self.assertNotIn("greenhouse/reports/summary.py", tiers["live"])

    def test_without_links_the_plugins_are_unreachable(self):
        cfg = self.config()
        del cfg["links"]
        self.write_config(cfg)
        tiers = self.tiers()
        for p in self.PLUGINS + ["greenhouse/reports/summary.py"]:
            self.assertIn(p, tiers["unreachable"])
        self.assertEqual(self.edges("kind LIKE 'declared%'"), [])

    def test_live_false_keeps_plugins_out_of_the_live_tier(self):
        cfg = self.config()
        cfg["links"][0]["live"] = False
        self.write_config(cfg)
        tiers = self.tiers()
        for p in self.PLUGINS[1:]:
            self.assertIn(p, tiers["weak-only"])

    def test_declared_edge_shows_in_importers_and_path(self):
        got = self.json("importers", "greenhouse/plugins/misting.py")
        self.assertIn("greenhouse/registry.py", json.dumps(got))
        chain = self.json("path", "greenhouse/registry.py",
                          "greenhouse/plugins/shade.py")
        self.assertEqual(len(chain), 2, chain)

    def test_unmatched_row_is_warned_about_not_fatal(self):
        rc, out, _ = run("ingest", str(self.repo))
        self.assertEqual(rc, 0)
        self.assertIn("config links row matched nothing on 'to':"
                      " greenhouse/scheduler.py -> jobs/**", out)

    def test_row_is_capped(self):
        old = code_kg.DECLARED_CAP
        self.addCleanup(setattr, code_kg, "DECLARED_CAP", old)
        code_kg.DECLARED_CAP = 2
        cfg = self.config()
        cfg["links"] = [{"from": "greenhouse/**", "to": "greenhouse/**"}]
        self.write_config(cfg)
        counts = self.json("ingest")
        self.assertEqual(counts["declared_edges"], 2)
        self.assertIn("capped at 2 of", counts["link_warnings"][0])

    def test_cap_never_builds_the_cross_product(self):
        import tracemalloc
        files = [f"pkg/m{i:04d}.py" for i in range(1500)]
        for rel in files:
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x = 1\n", encoding="utf-8")
        cfg = self.config()
        cfg["links"] = [{"from": "pkg/**", "to": "pkg/**"}]
        self.write_config(cfg)
        tracemalloc.start()
        counts = code_kg.ingest(self.repo)
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        self.assertEqual(counts["declared_edges"], code_kg.DECLARED_CAP)
        self.assertIn("capped at 2000 of 2248500 edges",
                      counts["link_warnings"][0])
        # 2.2 million pairs held as tuples is well over 100 MB.
        self.assertLess(peak, 60 * 1024 * 1024)

    def test_row_count_is_bounded(self):
        cfg = self.config()
        cfg["links"] = [{"from": "a.py", "to": "b.py"}] * 201
        self.write_config(cfg)
        rc, _, err = run("ingest", str(self.repo))
        self.assertEqual(rc, 1)
        self.assertIn("more than 200 rows", err)

    def test_report_keys_absent_without_the_config_keys(self):
        self.write_config({})
        counts = self.json("ingest")
        for key in ("declared_edges", "link_warnings", "components"):
            self.assertNotIn(key, counts)


class TestAnnotations(RepoCase):
    def rows(self, *argv: str) -> list:
        return [(r["file"], r["line"], r["marker"], r["owner"], r["payload"])
                for r in self.json("annotations", *argv)["rows"]]

    def test_every_marker_in_the_fixture(self):
        self.assertEqual(self.rows(), [
            ("greenhouse/cli.py", 12, "TODO", "",
             "accept a --dry-run flag that skips the actuators"),
            ("greenhouse/registry.py", 9, "SAFETY", "",
             "a plugin that fails to import must not stop the others"),
            ("greenhouse/reports/summary.py", 6, "TODO", "reports",
             "include the weekly average"),
            ("greenhouse/scheduler.py", 7, "FIXME", "",
             "every job runs on every call; there is no due-time check yet"),
            ("greenhouse/sensors/humidity.py", 6, "NOTE", "",
             "the bench sensor reports 0 when it is unplugged"),
            ("web/api.ts", 3, "TODO", "", "retry once on a network error"),
            ("web/dashboard.ts", 3, "HACK", "",
             "polls on a timer until the controller exposes events"),
        ])

    def test_a_marker_word_outside_a_comment_is_not_a_marker(self):
        # scheduler.py assigns STATUS = "TODO"; only its FIXME comment counts.
        self.assertEqual([r[2] for r in self.rows(
            "--path", "greenhouse/scheduler.py")], ["FIXME"])

    def test_symbol_is_the_innermost_one(self):
        got = self.json("annotations", "--marker", "FIXME")["rows"][0]
        self.assertEqual(got["symbol"],
                         "greenhouse/scheduler.py::run_due_jobs")

    def test_filters_and_counts(self):
        got = self.json("annotations", "--marker", "TODO")
        self.assertEqual(got["total"], 3)
        self.assertEqual(got["counts"], {"FIXME": 1, "HACK": 1, "NOTE": 1,
                                         "SAFETY": 1, "TODO": 3})
        self.assertEqual(len(self.rows("--path", "web/**")), 2)

    def test_custom_marker_needs_registration(self):
        cfg = self.config()
        cfg["markers"] = []
        self.write_config(cfg)
        self.assertNotIn("SAFETY", [r[2] for r in self.rows()])
        rc, _, err = run("annotations", str(self.repo), "--marker", "SAFETY")
        self.assertEqual(rc, 1)
        self.assertIn("unknown marker", err)

    def test_truncation_is_declared(self):
        got = self.json("annotations", "--limit", "2")
        self.assertEqual(got["status"], "TRUNCATED 2 of 7")
        self.assertEqual(len(got["rows"]), 2)

    def test_scanner_units(self):
        scan = code_kg.scan_annotations
        core = code_kg.CORE_MARKERS
        self.assertEqual(scan("python", "x = 1  # TODO: later\n", core),
                         [(1, "TODO", "", "later")])
        self.assertEqual(scan("javascript", "/* FIXME(ana): tidy */\n", core),
                         [(1, "FIXME", "ana", "tidy")])
        self.assertEqual(scan("c", " * NOTE continues here\n", core),
                         [(1, "NOTE", "", "continues here")])
        self.assertEqual(scan("sql", "SELECT 1; -- HACK: temp\n", core),
                         [(1, "HACK", "", "temp")])
        self.assertEqual(scan("html", "<!-- TODO: alt text -->\n", core),
                         [(1, "TODO", "", "alt text")])
        # Not a comment, not at a word boundary, or a language with no
        # comment syntax: nothing.
        self.assertEqual(scan("python", 'url = "http://TODO"\n', core), [])
        self.assertEqual(scan("python", "# TODOLIST of things\n", core), [])
        self.assertEqual(scan("json", '{"a": "# TODO: x"}\n', core), [])
        self.assertEqual(scan("python", "#" + " TODO: x" * 400 + "\n", core),
                         [])

    def test_payload_and_owner_drop_control_characters(self):
        got = code_kg.scan_annotations(
            "python", "# TODO(a\u001b[1mb): red\u001b[31m alert\n",
            code_kg.CORE_MARKERS)
        self.assertEqual(got, [(1, "TODO", "a[1mb", "red[31m alert")])


class TestConfigCommand(RepoCase):
    def test_reports_what_each_row_matched(self):
        got = self.json("config")
        self.assertEqual(got["status"], "WARNINGS")
        self.assertEqual(got["warnings"], [
            "links row matched nothing: greenhouse/scheduler.py -> jobs/**"])
        self.assertEqual({c["name"]: c["files"] for c in got["components"]},
                         {"control": 4, "sensors": 3, "actuators": 3,
                          "reporting": 3, "dashboard": 2})
        self.assertEqual(got["links"][0]["targets"], 3)
        self.assertEqual(got["declared_edges"],
                         {"declared": 1, "declared-live": 3})
        custom = [m for m in got["markers"] if not m["core"]]
        self.assertEqual(custom, [{"marker": "SAFETY", "core": False,
                                   "count": 1}])

    def test_empty_component_path_is_a_warning(self):
        cfg = self.config()
        cfg["components"].append({"name": "jobs", "paths": ["jobs/**"]})
        self.write_config(cfg)
        got = self.json("config")
        self.assertIn("component jobs: path matched nothing: jobs/**",
                      got["warnings"])

    def test_clean_config_is_ok(self):
        self.write_config({"roots": ["web"]})
        got = self.json("config")
        self.assertEqual(got["status"], "OK")
        self.assertEqual(got["roots"], [{"root": "web", "exists": True}])

    def test_control_characters_never_reach_the_terminal(self):
        hostile = "\u001b]0;x\u0007\u001b[2Jr"
        self.write_config({"roots": [hostile], "entry_points": [hostile]})
        rc, out, _ = run("config", str(self.repo))
        self.assertEqual(rc, 0)
        self.assertNotIn("\u001b", out)
        self.assertNotIn("\u0007", out)
        self.assertIn("\\x1b]0;x\\x07\\x1b[2Jr", out)
        rc, out, _ = run("ingest", str(self.repo))
        self.assertNotIn("\u001b", out)

    def test_control_characters_in_a_file_name_are_escaped(self):
        name = "greenhouse/odd\u001b[2Jname.py"
        (self.repo / name).write_text("# TODO: rename this file\n",
                                      encoding="utf-8")
        for cmd in (("annotations",), ("components",), ("stats",),
                    ("dead",), ("components", "control")):
            rc, out, _ = run(cmd[0], str(self.repo), *cmd[1:])
            self.assertEqual(rc, 0, cmd)
            self.assertNotIn("\u001b", out, cmd)
        rc, out, _ = run("annotations", str(self.repo))
        self.assertIn("odd\\x1b[2Jname.py", out)

    def test_a_root_outside_the_repo_is_never_probed(self):
        (self.tmp / "outside").mkdir()
        self.write_config({"roots": ["greenhouse", "../outside", "/tmp"]})
        got = self.json("config")
        self.assertEqual(got["roots"], [
            {"root": "greenhouse", "exists": True},
            {"root": "../outside", "exists": False},
            {"root": "/tmp", "exists": False}])

    def test_missing_config_reports_defaults(self):
        self.cfg_file.unlink()
        run("ingest", str(self.repo))
        got = self.json("config")
        self.assertFalse(got["exists"])
        self.assertEqual(got["status"], "OK")

    def test_writes_nothing(self):
        run("ingest", str(self.repo))
        before = self.cfg_file.read_bytes()
        run("config", str(self.repo))
        self.assertEqual(self.cfg_file.read_bytes(), before)


class TestGitignoreSeed(RepoCase):
    def test_an_existing_gitignore_is_never_rewritten(self):
        gi = code_kg.kg_dir(self.repo) / ".gitignore"
        gi.parent.mkdir(parents=True, exist_ok=True)
        gi.write_text("code-kg.db\n", encoding="utf-8")
        rc, _, err = run("ingest", str(self.repo))
        self.assertEqual(rc, 0, err)
        self.assertEqual(gi.read_text(encoding="utf-8"), "code-kg.db\n")

    @needs_symlinks
    def test_a_dangling_link_at_the_seed_path_is_not_written_through(self):
        planted = self.tmp / "planted"
        gi = code_kg.kg_dir(self.repo) / ".gitignore"
        if gi.exists():
            gi.unlink()
        os.symlink(planted, gi)
        rc, _, err = run("ingest", str(self.repo))
        self.assertEqual(rc, 0, err)
        self.assertFalse(planted.exists())


class TestIndexRevision(RepoCase):
    def test_a_revision_bump_reingests_on_the_next_read(self):
        run("ingest", str(self.repo))
        import sqlite3
        con = sqlite3.connect(code_kg.db_path(self.repo))
        con.execute("DELETE FROM annotations")
        con.commit()
        con.close()
        self.assertEqual(self.json("annotations")["total"], 0)
        old = code_kg.INDEX_REV
        self.addCleanup(setattr, code_kg, "INDEX_REV", old)
        code_kg.INDEX_REV = old + 1
        self.assertEqual(self.json("annotations")["total"], 7)


# The docs-and-code fixture lives in the markdown-kg skill, the sibling the
# `docs` command joins with, so there is one copy of it.
LINKED = code_kg.SIBLING_CLI.parent.parent / "tests" / "linked-fixture-repo"


@unittest.skipUnless(LINKED.is_dir(), "the markdown-kg skill is absent")
class TestDocs(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ckg-docs-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = self.tmp / "repo"
        shutil.copytree(LINKED, self.repo)
        run("ingest", str(self.repo))

    def index_vault(self, rel: str = "docs") -> None:
        r = subprocess.run(
            [sys.executable, str(code_kg.SIBLING_CLI), "ingest",
             str(self.repo / rel)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def json(self, *argv: str):
        rc, out, err = run(argv[0], str(self.repo), *argv[1:], "--json")
        self.assertEqual(rc, 0, err)
        return json.loads(out)

    def test_the_doc_sections_that_link_to_a_file(self):
        self.index_vault()
        got = self.json("docs", "src/tidelog/reader.py")
        self.assertEqual(got["file"], "src/tidelog/reader.py")
        self.assertEqual(got["missing"], [])
        self.assertEqual(
            [(s["vault"], s["doc"], s["heading_path"])
             for s in got["sections"]],
            [("docs", "docs/design/decisions.md",
              "Design decisions > Raw lines are kept"),
             ("docs", "docs/guide.md", "Operating guide > Reading a gauge")])
        guide = got["sections"][1]
        self.assertTrue(guide["section_id"])
        # The link sits on line 8 of docs/guide.md.
        self.assertLessEqual(guide["line_start"], 8)
        self.assertGreaterEqual(guide["line_end"], 8)
        self.assertEqual(got["doc_links"], [
            {"src": "docs/design/decisions.md", "kind": "link", "line": 6},
            {"src": "docs/guide.md", "kind": "link", "line": 8}])

    def test_a_link_only_the_vault_graph_holds(self):
        """The guide reaches cli.py through a reference-style link, which
        this engine's own markdown reader does not follow."""
        self.index_vault()
        got = self.json("docs", "src/tidelog/cli.py")
        self.assertEqual([s["heading_path"] for s in got["sections"]],
                         ["Operating guide > Daily report"])
        self.assertEqual([r["src"] for r in got["doc_links"]], ["README.md"])

    def test_a_link_below_a_code_block_lands_in_its_own_section(self):
        self.index_vault()
        got = self.json("docs", "scripts/backfill.sh")
        section = got["sections"][0]
        self.assertEqual(section["heading_path"], "Operating guide > Backfill")
        line = [r["line"] for r in got["doc_links"]
                if r["src"] == "docs/guide.md"][0]
        self.assertLessEqual(section["line_start"], line)
        self.assertGreaterEqual(section["line_end"], line)

    def test_a_vault_at_the_repo_root(self):
        self.index_vault(".")
        got = self.json("docs", "scripts/backfill.sh")
        self.assertEqual([(s["vault"], s["doc"]) for s in got["sections"]],
                         [(".", "README.md"), (".", "docs/guide.md")])

    def test_every_vault_in_the_repo_answers(self):
        self.index_vault()
        self.index_vault(".")
        got = self.json("docs", "src/tidelog/report.py")
        self.assertEqual([(s["vault"], s["doc"]) for s in got["sections"]],
                         [(".", "docs/guide.md"), ("docs", "docs/guide.md")])

    def test_a_path_that_starts_with_a_dash_is_a_path(self):
        (self.repo / "-odd.py").write_text("x = 1\n", encoding="utf-8")
        (self.repo / "docs" / "odd.md").write_text(
            "# Odd\n\n[x](../-odd.py)\n", encoding="utf-8")
        self.index_vault()
        rc, out, err = run("docs", "--json", "--", str(self.repo), "-odd.py")
        self.assertEqual(rc, 0, err)
        self.assertEqual([s["doc"] for s in json.loads(out)["sections"]],
                         ["docs/odd.md"])

    def test_prose(self):
        self.index_vault()
        rc, out, _ = run("docs", str(self.repo), "src/tidelog/reader.py")
        self.assertEqual(rc, 0)
        self.assertIn("docs/guide.md  L", out)
        self.assertIn("Operating guide > Reading a gauge", out)

    def test_the_vault_folder_is_left_as_it_was(self):
        self.index_vault()

        def snapshot():
            return sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns)
                          for p in (self.repo / "docs" / ".kg")
                          .iterdir())
        before = snapshot()
        self.json("docs", "src/tidelog/reader.py")
        self.assertEqual(snapshot(), before)

    def test_no_vault_in_the_repo(self):
        got = self.json("docs", "src/tidelog/reader.py")
        self.assertEqual(got["sections"], [])
        self.assertEqual(len(got["missing"]), 1)
        self.assertIn("markdown-kg", got["missing"][0])
        self.assertEqual(len(got["doc_links"]), 2)
        self.assertEqual(sorted(p.name for p in (self.repo / "docs").iterdir()),
                         ["data", "design", "guide.md", "index.md",
                          "reference.md"])

    # ---- names written in code spans ----
    def resolve(self, *texts: str) -> dict:
        rc, out, err = run("resolve", "--json", "--", str(self.repo), *texts)
        self.assertEqual(rc, 0, err)
        return {r["text"]: r for r in json.loads(out)}

    def test_resolve_a_path(self):
        got = self.resolve("src/tidelog/reader.py", "./src/tidelog/reader.py",
                           "tidelog/reader.py", "reader.py",
                           "src/tidelog/reader.py:4-12", "reader.py:7",
                           "__init__.py", "/src/tidelog/reader.py",
                           "~/src/tidelog/reader.py", "tidelog/", "gone.py")
        self.assertEqual(
            {t: (r["status"], r["file"]) for t, r in got.items()},
            {"src/tidelog/reader.py": ("file", "src/tidelog/reader.py"),
             "./src/tidelog/reader.py": ("file", "src/tidelog/reader.py"),
             "tidelog/reader.py": ("file", "src/tidelog/reader.py"),
             "reader.py": ("file", "src/tidelog/reader.py"),
             "src/tidelog/reader.py:4-12": ("file", "src/tidelog/reader.py"),
             "reader.py:7": ("file", "src/tidelog/reader.py"),
             "__init__.py": ("file", "src/tidelog/__init__.py"),
             "/src/tidelog/reader.py": ("none", None),
             "~/src/tidelog/reader.py": ("none", None),
             "tidelog/": ("none", None),
             "gone.py": ("none", None)})

    def test_resolve_a_path_ending_two_files_share(self):
        (self.repo / "scripts" / "cli.py").write_text("x = 1\n",
                                                      encoding="utf-8")
        got = self.resolve("cli.py", "tidelog/cli.py")
        self.assertEqual(got["cli.py"]["status"], "ambiguous")
        self.assertEqual(sorted(c["file"] for c in got["cli.py"]["candidates"]),
                         ["scripts/cli.py", "src/tidelog/cli.py"])
        self.assertEqual(got["tidelog/cli.py"]["file"], "src/tidelog/cli.py")

    def test_resolve_a_name(self):
        got = self.resolve(
            "parse_line", "parse_line()", "Station", "high_low",
            "Station.read_day", "Station::read_day", "Station#summary",
            "reader.parse_line", "tidelog.reader.read_day",
            "report.parse_line", "read_day", "main", "export", "summary",
            "TIDELOG_HOME", "len")
        self.assertEqual(
            {t: (r["status"], r["file"], r["symbol"]) for t, r in got.items()},
            {"parse_line": ("symbol", "src/tidelog/reader.py", "parse_line"),
             "parse_line()": ("symbol", "src/tidelog/reader.py", "parse_line"),
             "Station": ("symbol", "src/tidelog/station.py", "Station"),
             "high_low": ("symbol", "src/tidelog/report.py", "high_low"),
             "Station.read_day":
                 ("symbol", "src/tidelog/station.py", "Station.read_day"),
             "Station::read_day":
                 ("symbol", "src/tidelog/station.py", "Station.read_day"),
             "Station#summary":
                 ("symbol", "src/tidelog/station.py", "Station.summary"),
             "reader.parse_line":
                 ("symbol", "src/tidelog/reader.py", "parse_line"),
             "tidelog.reader.read_day":
                 ("symbol", "src/tidelog/reader.py", "read_day"),
             # A qualifier that names another module matches nothing.
             "report.parse_line": ("none", None, None),
             # Two definitions: never guessed.
             "read_day": ("ambiguous", None, None),
             # One definition, but an ordinary word, or a member written
             # without its class: reported, not linked.
             "main": ("weak", None, None),
             "export": ("weak", None, None),
             "summary": ("weak", None, None),
             "TIDELOG_HOME": ("none", None, None),
             "len": ("none", None, None)})
        self.assertEqual(got["parse_line"]["lines"], "4-12")
        self.assertEqual(got["parse_line"]["kind"], "function")

    def test_docs_mentions(self):
        self.index_vault()
        got = self.json("docs", "src/tidelog/reader.py", "--mentions")
        self.assertEqual(
            [(m["doc"], m["heading_path"], m["line"], m["text"], m["symbol"])
             for m in got["mentions"]],
            # The span that names the file outright ranks first.
            [("docs/reference.md", "Reference > Reading", 9,
              "src/tidelog/reader.py:4-12", None),
             ("docs/reference.md", "Reference > Reading", 7, "parse_line",
              "parse_line"),
             ("docs/reference.md", "Reference > Reporting", 14,
              "tidelog.reader.parse_line", "parse_line")])
        # `read_day()` has two definitions, so it is not a mention of either.
        station = self.json("docs", "src/tidelog/station.py", "--mentions")
        self.assertEqual(sorted(m["text"] for m in station["mentions"]),
                         ["Station", "Station.read_day"])

    def test_docs_mentions_cap_the_spans_one_file_is_asked_about(self):
        """A line suffix is dropped before a path is matched, so a vault
        can name one file in any number of distinct spans."""
        (self.repo / "docs" / "flood.md").write_text(
            "# Flood\n\n" + "\n".join(
                f"`reader.py:{i}`" for i in range(1, 1206)) + "\n",
            encoding="utf-8")
        self.index_vault()
        got = self.json("docs", "src/tidelog/reader.py", "--mentions",
                        "--limit", "0")
        self.assertEqual(len(got["mentions"]), code_kg.MENTION_TEXTS)
        self.assertEqual(len(got["missing"]), 1)
        self.assertIn("208 of 1208", got["missing"][0])
        cut = self.json("docs", "src/tidelog/reader.py", "--mentions")
        self.assertEqual(len(cut["mentions"]), code_kg.DOCS_LIMIT)
        self.assertEqual(cut["status"], f"TRUNCATED mentions"
                         f" {code_kg.DOCS_LIMIT} of {code_kg.MENTION_TEXTS}")

    def test_docs_reports_its_scope(self):
        """Text output opens with the scope line; json keeps stdout as it
        was and sends the scope to stderr. `docs` asks every vault inside
        the repo, so nothing is left unsearched here."""
        self.index_vault()
        rc, out, _ = run("docs", str(self.repo), "src/tidelog/reader.py")
        self.assertEqual(rc, 0)
        self.assertRegex(out.splitlines()[0],
                         r"^scope: docs \(ingested \S+\); not searched: none;"
                         r" not indexed: none$")
        rc, out, err = run("docs", str(self.repo), "src/tidelog/reader.py",
                           "--json")
        self.assertEqual(rc, 0)
        self.assertNotIn("scope", json.loads(out))
        scope = json.loads(err.strip().splitlines()[-1])["scope"]
        self.assertEqual([g["graph"] for g in scope["searched"]], ["docs"])
        self.assertEqual(scope["not_searched"], [])

    def test_docs_without_the_flag_is_as_before(self):
        # As before, plus the `status` every capped answer carries.
        self.index_vault()
        got = self.json("docs", "src/tidelog/reader.py")
        self.assertEqual(sorted(got),
                         ["doc_links", "file", "missing", "sections", "status"])
        self.assertEqual(got["status"], "COMPLETE")

    def test_docs_mentions_agree_with_the_vault_side(self):
        """Every name the vault side resolves into a file is a mention the
        code side lists for that file, and the reverse."""
        self.index_vault()
        r = subprocess.run(
            [sys.executable, str(code_kg.SIBLING_CLI), "code", "--json",
             "--mentions", "--", str(self.repo / "docs"), "reference"],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        vault_side = {(m["file"], m["text"], m["corroborated"])
                      for m in json.loads(r.stdout)["mentions"]
                      if m["status"] in ("file", "symbol")}
        self.assertEqual(len(vault_side), 9)
        code_side = set()
        for f in sorted({v[0] for v in vault_side}):
            code_side |= {(f, m["text"], m["corroborated"]) for m in
                          self.json("docs", f, "--mentions")["mentions"]}
        self.assertEqual(code_side, vault_side)
        # Nothing in the note names or links station.py.
        self.assertEqual({c for f, _, c in vault_side
                          if f == "src/tidelog/station.py"}, {False})

    def test_a_vault_folder_without_a_database(self):
        (self.repo / "docs" / ".kg").mkdir()
        got = self.json("docs", "src/tidelog/reader.py")
        self.assertEqual(got["sections"], [])
        self.assertEqual(len(got["missing"]), 1)
        self.assertIn("ingest", got["missing"][0])
        self.assertEqual(
            list((self.repo / "docs" / ".kg").iterdir()), [])

    @needs_symlinks
    def test_a_symlinked_vault_folder_is_never_asked(self):
        """markdown-kg refreshes its database before it answers, so a link
        here would let the repo choose where that write lands."""
        self.index_vault()
        real = self.tmp / "elsewhere"
        shutil.move(str(self.repo / "docs" / ".kg"), str(real))
        os.symlink(real, self.repo / "docs" / ".kg")
        (self.repo / "docs" / "added.md").write_text(
            "# Added\n\n[x](../src/tidelog/reader.py)\n", encoding="utf-8")

        def snapshot():
            return sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns)
                          for p in real.iterdir())
        before = snapshot()
        got = self.json("docs", "src/tidelog/reader.py")
        self.assertEqual(got["sections"], [])
        self.assertEqual(len(got["missing"]), 1)
        self.assertIn("no markdown-kg database", got["missing"][0])
        self.assertEqual(snapshot(), before)

    def test_the_sibling_skill_absent(self):
        self.index_vault()
        self.index_vault(".")
        old = code_kg.SIBLING_CLI
        self.addCleanup(setattr, code_kg, "SIBLING_CLI", old)
        code_kg.SIBLING_CLI = self.tmp / "nowhere" / "markdown_kg.py"
        got = self.json("docs", "src/tidelog/reader.py")
        self.assertEqual(got["sections"], [])
        self.assertEqual(len(got["missing"]), 1)
        self.assertIn("markdown-kg", got["missing"][0])
        self.assertEqual(len(got["doc_links"]), 2)
        rc, out, _ = run("docs", str(self.repo), "src/tidelog/reader.py")
        self.assertEqual(rc, 0)
        self.assertIn("docs/guide.md:8", out)
        self.assertEqual(sum("markdown-kg" in ln for ln in out.splitlines()),
                         1)


class ClosedPipeTests(unittest.TestCase):
    """A reader that stops early (`| head`) gets no traceback on stderr."""

    def test_read_into_a_closed_pipe_is_quiet(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        # About 150 KB of output, well past a 64 KB pipe buffer.
        (tmp / "big.py").write_text("".join(
            f"def f_{i:05d}():\n    return {i}\n" for i in range(6000)))
        engine = str(SKILL_DIR / "scripts" / "code_kg.py")
        subprocess.run([sys.executable, engine, "ingest", str(tmp)],
                       capture_output=True, check=True, timeout=120)
        p = subprocess.Popen([sys.executable, engine, "read", str(tmp), "big.py"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p.stdout.read(64)
        p.stdout.close()
        err = p.stderr.read().decode()
        p.stderr.close()
        p.wait(timeout=120)
        self.assertEqual(err, "")


if __name__ == "__main__":
    unittest.main()
