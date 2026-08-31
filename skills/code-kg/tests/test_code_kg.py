"""Unit, behavior and end-to-end tests for code_kg.py.

Behavior tests run against a temporary copy of tests/fixture-repo so the
committed fixture never grows a .code-kg folder.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import code_kg  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixture-repo"
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
ENGINE = SKILL_DIR / "scripts" / "code_kg.py"


class TestGlob(unittest.TestCase):
    def test_basic(self):
        self.assertTrue(code_kg.glob_match("app/main.py", "app/*.py"))
        self.assertFalse(code_kg.glob_match("app/sub/main.py", "app/*.py"))

    def test_doublestar(self):
        self.assertTrue(code_kg.glob_match("a/b/c/d.py", "a/**/d.py"))
        self.assertTrue(code_kg.glob_match("web/lib/api.ts", "web/**"))

    def test_bare_pattern_matches_any_part(self):
        self.assertTrue(code_kg.glob_match("x/dist/y.js", "dist"))
        self.assertTrue(code_kg.glob_match("a/b/thing.min.js", "*.min.js"))

    def test_overlong_pattern_refused(self):
        self.assertFalse(code_kg.glob_match("a", "*" * 600))

    def test_adversarial_pattern_terminates(self):
        # Linear-time matcher: this input hangs a backtracking regex.
        self.assertFalse(code_kg._match_segment("a" * 60 + "c",
                                                "*a" * 12 + "*b"))


class TestLanguageAndRole(unittest.TestCase):
    def test_language_of(self):
        self.assertEqual(code_kg.language_of("Dockerfile"), "dockerfile")
        self.assertEqual(code_kg.language_of("x/Dockerfile.dev"), "dockerfile")
        self.assertEqual(code_kg.language_of("Makefile"), "make")
        self.assertEqual(code_kg.language_of("a/b.tsx"), "typescript")
        self.assertIsNone(code_kg.language_of("bundle.min.js"))
        self.assertIsNone(code_kg.language_of("package-lock.json"))
        self.assertIsNone(code_kg.language_of("photo.png"))

    def test_role_of(self):
        self.assertEqual(code_kg.role_of("tests/test_x.py", "python"), "test")
        self.assertEqual(code_kg.role_of("src/x.spec.ts", "typescript"),
                         "test")
        self.assertEqual(code_kg.role_of(".github/workflows/ci.yml", "yaml"),
                         "ci")
        self.assertEqual(code_kg.role_of("README.md", "markdown"), "docs")
        self.assertEqual(code_kg.role_of("conf/settings.yml", "yaml"),
                         "config")
        self.assertEqual(code_kg.role_of("app/main.py", "python"), "source")


class TestPythonResolver(unittest.TestCase):
    def setUp(self):
        files = {
            "app/__init__.py", "app/main.py", "app/util.py",
            "src/pkg/__init__.py", "src/pkg/mod.py",
            "dup.py", "dup/__init__.py",
        }
        self.r = code_kg.Resolver(Path("/nonexistent"),
                                  dict(code_kg.DEFAULT_CONFIG), files)

    def test_absolute(self):
        self.assertEqual(self.r.resolve_python("x.py", "app.util"),
                         ("app/util.py", "resolved"))

    def test_src_layout(self):
        self.assertEqual(self.r.resolve_python("x.py", "pkg.mod"),
                         ("src/pkg/mod.py", "resolved"))

    def test_relative(self):
        self.assertEqual(self.r.resolve_python("app/main.py", ".util"),
                         ("app/util.py", "resolved"))

    def test_stdlib_external(self):
        self.assertEqual(self.r.resolve_python("x.py", "json"),
                         (None, "external"))

    def test_missing_local_unresolved(self):
        self.assertEqual(self.r.resolve_python("x.py", "app.missing"),
                         (None, "unresolved"))

    def test_third_party_external(self):
        self.assertEqual(self.r.resolve_python("x.py", "requests"),
                         (None, "external"))

    def test_module_and_package_collision_ambiguous(self):
        self.assertEqual(self.r.resolve_python("x.py", "dup"),
                         (None, "ambiguous"))


class TestJsResolver(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        files = {"web/index.ts", "web/models.ts", "web/lib/api.ts",
                 "web/lib/index.ts"}
        self.r = code_kg.Resolver(Path(self.tmp),
                                  dict(code_kg.DEFAULT_CONFIG), files)
        self.r.aliases = [("@app/*", "web/*")]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_relative_ext_omitted(self):
        self.assertEqual(self.r.resolve_js("web/index.ts", "./models"),
                         ("web/models.ts", "resolved"))

    def test_directory_index(self):
        self.assertEqual(self.r.resolve_js("web/index.ts", "./lib"),
                         ("web/lib/index.ts", "resolved"))

    def test_alias(self):
        self.assertEqual(self.r.resolve_js("web/index.ts", "@app/models"),
                         ("web/models.ts", "resolved"))

    def test_bare_external(self):
        self.assertEqual(self.r.resolve_js("web/index.ts", "react"),
                         (None, "external"))

    def test_missing_relative_unresolved(self):
        self.assertEqual(self.r.resolve_js("web/index.ts", "./gone"),
                         (None, "unresolved"))

    def test_alias_dot_slash_target_probes_extensions(self):
        self.r.aliases = [("@/*", "./web/*")]
        self.assertEqual(self.r.resolve_js("web/index.ts", "@/models"),
                         ("web/models.ts", "resolved"))

    def test_alias_barrel_index(self):
        self.r.aliases = [("@/*", "web/*")]
        self.assertEqual(self.r.resolve_js("web/index.ts", "@/lib"),
                         ("web/lib/index.ts", "resolved"))

    def test_baseurl_bare_specifier_probes_repo(self):
        self.r.base_url = "."
        self.assertEqual(self.r.resolve_js("x.ts", "web/models"),
                         ("web/models.ts", "resolved"))
        self.assertEqual(self.r.resolve_js("x.ts", "react"),
                         (None, "external"))

    def test_no_baseurl_bare_stays_external(self):
        self.r.base_url = None
        self.assertEqual(self.r.resolve_js("x.ts", "web/models"),
                         (None, "external"))


class TestJsonc(unittest.TestCase):
    def test_glob_strings_survive(self):
        text = ('{"compilerOptions": {"baseUrl": ".",'
                ' "paths": {"@/*": ["./src/*"]}},'
                ' "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx"]}')
        data = json.loads(code_kg.strip_jsonc(text))
        self.assertEqual(data["compilerOptions"]["paths"]["@/*"], ["./src/*"])
        self.assertIn("**/*.ts", data["include"])

    def test_comments_removed_outside_strings_only(self):
        text = ('{\n// a line comment\n"url": "http://x//y",'
                ' /* block\ncomment */ "n": [1, 2,],\n}')
        data = json.loads(code_kg.strip_jsonc(text))
        self.assertEqual(data["url"], "http://x//y")
        self.assertEqual(data["n"], [1, 2])

    def test_comments_and_glob_strings_together(self):
        text = ('{\n  // next defaults\n  "compilerOptions": {\n'
                '    "paths": {"@/*": ["./src/*"]} /* alias */\n  },\n'
                '  "include": ["**/*.ts"],\n}')
        data = json.loads(code_kg.strip_jsonc(text))
        self.assertEqual(data["compilerOptions"]["paths"]["@/*"], ["./src/*"])

    def test_escaped_quotes(self):
        text = '{"a": "say \\"hi\\" // still a string"}'
        data = json.loads(code_kg.strip_jsonc(text))
        self.assertEqual(data["a"], 'say "hi" // still a string')


class TestAliasLoading(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name, text):
        (self.tmp / name).write_text(text, encoding="utf-8")

    def test_create_next_app_shape_loads(self):
        self._write("tsconfig.json", json.dumps({
            "compilerOptions": {"baseUrl": ".",
                                "paths": {"@/*": ["./src/*"]}},
            "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx"]}))
        aliases, notes, base = code_kg.load_aliases(
            self.tmp, dict(code_kg.DEFAULT_CONFIG))
        self.assertEqual(aliases, [("@/*", "src/*")])
        self.assertEqual(base, ".")
        self.assertTrue(any("tsconfig.json" in n for n in notes))

    def test_jsonc_comments_with_globs(self):
        self._write("tsconfig.json",
                    '{\n// hi\n"compilerOptions": {\n'
                    '"paths": {"@/*": ["./src/*"]}, /* x */\n},\n'
                    '"include": ["**/*.ts"],\n}')
        aliases, notes, base = code_kg.load_aliases(
            self.tmp, dict(code_kg.DEFAULT_CONFIG))
        self.assertEqual(aliases, [("@/*", "src/*")])

    def test_parse_failure_is_loud(self):
        self._write("tsconfig.json", '{"compilerOptions": {')
        aliases, notes, base = code_kg.load_aliases(
            self.tmp, dict(code_kg.DEFAULT_CONFIG))
        self.assertEqual(aliases, [])
        self.assertTrue(any("failed" in n for n in notes), notes)

    def test_baseurl_prefix_stripped_not_charset(self):
        self._write("tsconfig.json", json.dumps({
            "compilerOptions": {"baseUrl": "./app",
                                "paths": {"@/*": ["./lib/*"]}}}))
        aliases, notes, base = code_kg.load_aliases(
            self.tmp, dict(code_kg.DEFAULT_CONFIG))
        self.assertEqual(aliases, [("@/*", "app/lib/*")])
        self.assertEqual(base, "app")

    def test_extends_chain_merges_child_wins(self):
        self._write("tsconfig.base.json", json.dumps({
            "compilerOptions": {"paths": {"#shared/*": ["./src/shared/*"],
                                          "@/*": ["./base-src/*"]}}}))
        self._write("tsconfig.json", json.dumps({
            "extends": "./tsconfig.base.json",
            "compilerOptions": {"baseUrl": ".",
                                "paths": {"@/*": ["./src/*"]}}}))
        aliases, notes, base = code_kg.load_aliases(
            self.tmp, dict(code_kg.DEFAULT_CONFIG))
        self.assertIn(("@/*", "src/*"), aliases)
        self.assertIn(("#shared/*", "src/shared/*"), aliases)
        self.assertNotIn(("@/*", "base-src/*"), aliases)

    def test_multi_target_uses_first_and_notes_rest(self):
        self._write("tsconfig.json", json.dumps({
            "compilerOptions": {"paths": {
                "@/*": ["./src/*", "./generated/*"]}}}))
        aliases, notes, base = code_kg.load_aliases(
            self.tmp, dict(code_kg.DEFAULT_CONFIG))
        self.assertEqual(aliases, [("@/*", "src/*")])
        self.assertTrue(any("skip" in n for n in notes), notes)

    def test_package_json_imports_field(self):
        self._write("package.json", json.dumps({
            "name": "x", "imports": {"#lib/*": "./src/lib/*"}}))
        aliases, notes, base = code_kg.load_aliases(
            self.tmp, dict(code_kg.DEFAULT_CONFIG))
        self.assertEqual(aliases, [("#lib/*", "src/lib/*")])
        self.assertTrue(any("package.json" in n for n in notes))

    def test_config_aliases_merge_config_wins(self):
        self._write("tsconfig.json", json.dumps({
            "compilerOptions": {"paths": {"@/*": ["./src/*"]}}}))
        cfg = dict(code_kg.DEFAULT_CONFIG)
        cfg["aliases"] = {"@/*": "override/*", "#x/*": "x/*"}
        aliases, notes, base = code_kg.load_aliases(self.tmp, cfg)
        self.assertIn(("@/*", "override/*"), aliases)
        self.assertIn(("#x/*", "x/*"), aliases)
        self.assertNotIn(("@/*", "src/*"), aliases)


class TestDjangoProfile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp()
        cls.repo = Path(cls.tmpdir) / "repo"
        shutil.copytree(Path(__file__).resolve().parent / "fixture-django",
                        cls.repo)
        cls.counts = code_kg.ingest(cls.repo)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _rows(self, sql, *params):
        con = code_kg.connect(self.repo)
        rows = con.execute(sql, params).fetchall()
        con.close()
        return rows

    def test_profile_detected(self):
        self.assertEqual(self.counts["profiles"], ["django"])

    def test_convention_entry_points(self):
        got = {r[0] for r in self._rows(
            "SELECT file_id FROM entry_points WHERE kind='convention'")}
        expected = {"manage.py", "config/settings.py", "config/urls.py",
                    "config/wsgi.py", "config/asgi.py", "core/admin.py",
                    "core/apps.py", "core/migrations/0001_initial.py",
                    "core/management/commands/seed.py"}
        self.assertTrue(expected <= got, expected - got)

    def test_settings_string_edges(self):
        got = {(r[0], r[1]) for r in self._rows(
            "SELECT src, dst FROM edges WHERE kind='string-ref'"
            " AND status='resolved'")}
        for pair in [("config/settings.py", "config/urls.py"),
                     ("config/settings.py", "config/wsgi.py"),
                     ("config/settings.py", "core/middleware.py"),
                     ("config/settings.py", "core/models.py")]:
            self.assertIn(pair, got)

    def test_template_string_resolves_by_suffix(self):
        got = self._rows(
            "SELECT src, dst FROM edges WHERE src='core/views.py'"
            " AND dst='templates/emails/welcome.html'"
            " AND status='resolved'")
        self.assertTrue(got)

    def test_dead_orphan_only(self):
        report = code_kg.dead_report(self.repo)
        self.assertEqual(report["tiers"]["unreachable"],
                         ["core/unused_helper.py"])
        self.assertIn("core/middleware.py",
                      report["tiers"]["weak-only"] +
                      report["tiers"]["live"])

    def test_unresolved_empty(self):
        rows = self._rows("SELECT src, target FROM edges"
                          " WHERE status='unresolved'")
        self.assertEqual(rows, [])

    def test_dockerfile_workdir_exec_resolves(self):
        rows = self._rows(
            "SELECT kind FROM edges WHERE src='Dockerfile'"
            " AND dst='scripts/startup.sh' AND status='resolved'")
        self.assertTrue(rows)

    def test_agent_layer_roles(self):
        got = {r[0] for r in self._rows(
            "SELECT id FROM files WHERE role='agent'")}
        self.assertTrue({"CLAUDE.md", "AGENTS.md", "core/CLAUDE.md"} <= got,
                        got)

    def test_canned_queries(self):
        key = json.loads(
            (Path(__file__).resolve().parent / "fixture-django-key.json")
            .read_text(encoding="utf-8"))
        for q in key["queries"]:
            r = code_kg.search(self.repo, q["q"])
            top = [h["file"] for h in r["results"][:3]]
            self.assertIn(q["top3"][0], top, (q["q"], top))


class TestNextjsProfile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp()
        cls.repo = Path(cls.tmpdir) / "repo"
        shutil.copytree(Path(__file__).resolve().parent / "fixture-nextapp",
                        cls.repo)
        # The agent overlay is generated here: tooling write-guards block
        # committing .claude/ trees inside fixtures.
        tools = cls.repo / ".claude" / "tools"
        tools.mkdir(parents=True)
        (tools / "observe.ts").write_text(
            "const started = Date.now();\n\n"
            "export function observe(event: string): void {\n"
            "  const elapsed = Date.now() - started;\n"
            "  process.stdout.write(`${event} +${elapsed}ms\\n`);\n"
            "}\n\nobserve(\"boot\");\n", encoding="utf-8")
        skill = cls.repo / ".claude" / "skills" / "demo-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: demo-skill\ndescription: Minimal demo skill for"
            " the fixture agent overlay.\n---\n\nSummarize the invoices"
            " table when asked about billing.\n", encoding="utf-8")
        cls.counts = code_kg.ingest(cls.repo)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _rows(self, sql, *params):
        con = code_kg.connect(self.repo)
        rows = con.execute(sql, params).fetchall()
        con.close()
        return rows

    def test_profile_detected_via_package_dep(self):
        self.assertEqual(self.counts["profiles"], ["nextjs"])

    def test_pages_are_convention_entries(self):
        got = {r[0] for r in self._rows(
            "SELECT file_id FROM entry_points WHERE kind='convention'")}
        expected = {"src/app/page.tsx", "src/app/layout.tsx",
                    "src/app/invoices/page.tsx",
                    "src/app/api/health/route.ts", "src/middleware.ts"}
        self.assertTrue(expected <= got, expected - got)

    def test_alias_edges_resolve(self):
        got = {(r[0], r[1]) for r in self._rows(
            "SELECT src, dst FROM edges WHERE status='resolved'")}
        for pair in [("src/app/invoices/page.tsx", "src/services/api.ts"),
                     ("src/services/api.ts", "src/services/csrf.ts"),
                     ("src/services/api.ts", "src/lib/util.ts"),
                     ("src/services/api.ts", "src/shared/types.ts")]:
            self.assertIn(pair, got)

    def test_barrel_import_resolves_to_index(self):
        got = {(r[0], r[1]) for r in self._rows(
            "SELECT src, dst FROM edges WHERE status='resolved'")}
        self.assertIn(("src/app/invoices/page.tsx",
                       "src/components/index.ts"), got)

    def test_dead_orphan_only(self):
        report = code_kg.dead_report(self.repo)
        self.assertEqual(report["tiers"]["unreachable"],
                         ["src/legacy/old-cart.ts"])
        for page in ("src/app/page.tsx", "src/app/invoices/page.tsx"):
            self.assertIn(page, report["tiers"]["live"])

    def test_unresolved_empty(self):
        rows = self._rows("SELECT src, target FROM edges"
                          " WHERE status='unresolved'")
        self.assertEqual(rows, [])

    def test_agent_layer_roles(self):
        got = {r[0] for r in self._rows(
            "SELECT id FROM files WHERE role='agent'")}
        expected = {"CLAUDE.md", "src/app/CLAUDE.md",
                    ".claude/tools/observe.ts",
                    ".claude/skills/demo-skill/SKILL.md"}
        self.assertTrue(expected <= got, expected - got)

    def test_dotdir_script_edge_resolves(self):
        rows = self._rows(
            "SELECT src, target FROM edges WHERE src='package.json'"
            " AND dst='.claude/tools/observe.ts'"
            " AND status='resolved'")
        self.assertTrue(rows)
        self.assertEqual(rows[0][1], ".claude/tools/observe.ts")

    def test_agent_layer_not_in_dead_tiers(self):
        report = code_kg.dead_report(self.repo)
        all_tiered = [f for tier in report["tiers"].values() for f in tier]
        self.assertFalse([f for f in all_tiered
                          if f.startswith(".claude/")
                          or f.endswith("CLAUDE.md")])

    def test_agent_topology(self):
        con = code_kg.connect(self.repo)
        topo = code_kg.agent_topology(con)
        con.close()
        self.assertEqual(topo["instruction_dirs"], [".", "src/app"])
        self.assertEqual(topo["skills"],
                         [".claude/skills/demo-skill/SKILL.md"])

    def test_import_type_edge_kind(self):
        rows = self._rows(
            "SELECT kind FROM edges WHERE src='src/services/api.ts'"
            " AND dst='src/shared/types.ts'")
        self.assertEqual([r[0] for r in rows], ["import-type"])

    def test_nested_handlers_have_bounded_ranges(self):
        rows = self._rows(
            "SELECT name, line_start, line_end FROM symbols"
            " WHERE file_id='src/app/invoices/page.tsx'"
            " AND name LIKE 'handle%'")
        self.assertGreaterEqual(len(rows), 5, rows)
        for name, start, end in rows:
            self.assertLessEqual(end - start, 50, rows)

    def test_test_files_are_not_convention_entries(self):
        rows = self._rows(
            "SELECT file_id FROM entry_points WHERE kind='convention'")
        offenders = [r[0] for r in rows if ".test." in r[0]
                     or ".spec." in r[0]]
        self.assertEqual(offenders, [])
        present = self._rows("SELECT role FROM files WHERE"
                             " id='src/app/invoices/page.test.tsx'")
        self.assertEqual(present, [("test",)])

    def test_canned_queries(self):
        key = json.loads(
            (Path(__file__).resolve().parent / "fixture-nextapp-key.json")
            .read_text(encoding="utf-8"))
        for q in key["queries"]:
            text, top3 = (q["q"], q["top3"]) if isinstance(q, dict) else q
            r = code_kg.search(self.repo, text)
            top = [h["file"] for h in r["results"][:3]]
            self.assertIn(top3[0], top, (text, top))

    def test_importers_follow_barrel_reexport(self):
        con = code_kg.connect(self.repo)
        via = con.execute(
            "SELECT e2.src FROM edges e1 JOIN edges e2 ON e2.dst = e1.src"
            " WHERE e1.dst='src/components/Button.tsx'"
            " AND e1.kind='reexport'").fetchall()
        con.close()
        args = type("A", (), {"repo": str(self.repo),
                              "path": "src/components/Button.tsx",
                              "json": True})()
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code_kg.cmd_importers(args)
        payload = json.loads(buf.getvalue())
        vias = [r for r in payload if r.get("via")]
        self.assertTrue(any(r["src"] == "src/app/invoices/page.tsx"
                            for r in vias), payload)


class TestDataInventoryDjango(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp()
        cls.repo = Path(cls.tmpdir) / "repo"
        shutil.copytree(Path(__file__).resolve().parent / "fixture-django",
                        cls.repo)
        code_kg.ingest(cls.repo)
        cls.inv = code_kg.data_inventory(cls.repo)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_postgres_detected_with_evidence(self):
        store = self.inv["stores"].get("postgres")
        self.assertIsNotNone(store, self.inv["stores"])
        ev = " ".join(store["evidence"])
        self.assertIn("docker-compose.yml", ev)
        self.assertIn("requirements.txt", ev)

    def test_redis_detected(self):
        self.assertIn("redis", self.inv["stores"])

    def test_schema_grouped_under_postgres(self):
        store = self.inv["stores"]["postgres"]
        self.assertIn("core/models.py", store.get("model_files", []))
        self.assertIn("core/migrations", store.get("migration_dirs", []))


class TestDataInventoryAndInspectSqlite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp()
        cls.repo = Path(cls.tmpdir) / "repo"
        shutil.copytree(Path(__file__).resolve().parent / "fixture-nextapp",
                        cls.repo)
        import sqlite3 as sq
        db = sq.connect(cls.repo / "data" / "cache.sqlite3")
        db.execute("CREATE TABLE invoices (id INTEGER PRIMARY KEY,"
                   " total REAL)")
        db.execute("INSERT INTO invoices VALUES (1, 9.5), (2, 3.25)")
        db.commit()
        db.close()
        chroma = cls.repo / "data" / "vectors"
        chroma.mkdir()
        shutil.copy(cls.repo / "data" / "cache.sqlite3",
                    chroma / "chroma.sqlite3")
        code_kg.ingest(cls.repo)
        cls.inv = code_kg.data_inventory(cls.repo)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_sqlite_file_detected(self):
        store = self.inv["stores"].get("sqlite")
        self.assertIsNotNone(store, self.inv["stores"])
        ev = " ".join(store["evidence"])
        self.assertIn("data/cache.sqlite3", ev)
        self.assertIn("better-sqlite3", ev)

    def test_chroma_marker_detected(self):
        self.assertIn("chroma", self.inv["stores"])

    def test_data_files_inventoried(self):
        self.assertEqual(self.inv["data_files"].get("data", {}).get("csv"),
                         1)

    def test_inspect_reports_tables_readonly(self):
        target = self.repo / "data" / "cache.sqlite3"
        before = target.stat().st_mtime_ns
        report = code_kg.inspect_store(self.repo, "data/cache.sqlite3")
        self.assertEqual(before, target.stat().st_mtime_ns)
        tables = {t["name"]: t["rows"] for t in report["tables"]}
        self.assertEqual(tables, {"invoices": 2})

    def test_inspect_refuses_without_consent(self):
        args = type("A", (), {"repo": str(self.repo),
                              "inspect": "data/cache.sqlite3",
                              "yes": False, "json": False})()
        self.assertNotEqual(code_kg.cmd_data(args), 0)

    def test_inspect_refuses_non_sqlite(self):
        with self.assertRaises(SystemExit):
            code_kg.inspect_store(self.repo, "data/seed.csv")


class TestExcludedStatus(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.repo = Path(self.tmpdir)
        (self.repo / "uv.lock").write_text("# lock\n", encoding="utf-8")
        (self.repo / "app.py").write_text("x = 1\n", encoding="utf-8")
        (self.repo / "Dockerfile").write_text(
            "FROM python:3.12\nWORKDIR /app\nCOPY uv.lock .\n"
            "COPY app.py .\n", encoding="utf-8")
        code_kg.ingest(self.repo)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_policy_excluded_target_not_unresolved(self):
        con = code_kg.connect(self.repo)
        rows = con.execute("SELECT target, status FROM edges"
                           " WHERE src='Dockerfile'"
                           " AND target='uv.lock'").fetchall()
        unresolved = con.execute("SELECT count(*) FROM edges WHERE"
                                 " status='unresolved'").fetchone()[0]
        con.close()
        self.assertEqual(rows, [("uv.lock", "excluded")])
        self.assertEqual(unresolved, 0)


class TestStatsRender(unittest.TestCase):
    def test_stats_renders_text_without_json_flag(self):
        import io
        import contextlib
        tmpdir = tempfile.mkdtemp()
        try:
            repo = Path(tmpdir) / "repo"
            shutil.copytree(FIXTURE, repo)
            code_kg.ingest(repo)
            args = type("A", (), {"repo": str(repo), "json": False})()
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code_kg.cmd_stats(args)
            out = buf.getvalue()
            self.assertFalse(out.lstrip().startswith("{"), out[:80])
            self.assertIn("files", out)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestCanaryFollowups(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.repo = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_commented_urls_are_not_data_evidence(self):
        (self.repo / "settings.py").write_text(
            "DEBUG = True\n"
            '# CACHE_URL = "redis://localhost:6379/0"\n'
            '#ENGINE = "django.db.backends.mysql"\n', encoding="utf-8")
        code_kg.ingest(self.repo)
        inv = code_kg.data_inventory(self.repo)
        self.assertNotIn("redis", inv["stores"])
        self.assertNotIn("mysql", inv["stores"])

    def test_django_repo_detects_manage_test_not_pytest(self):
        (self.repo / "manage.py").write_text(
            "if __name__ == \"__main__\":\n    pass\n", encoding="utf-8")
        (self.repo / "tests").mkdir()
        cmd = code_kg.detect_test_command(self.repo,
                                          dict(code_kg.DEFAULT_CONFIG))
        self.assertEqual(cmd, ["python3", "-m", "coverage", "run",
                               "manage.py", "test"])

    def test_pytest_config_beats_manage_py(self):
        (self.repo / "manage.py").write_text("pass\n", encoding="utf-8")
        (self.repo / "pytest.ini").write_text("[pytest]\n",
                                              encoding="utf-8")
        cmd = code_kg.detect_test_command(self.repo,
                                          dict(code_kg.DEFAULT_CONFIG))
        self.assertEqual(cmd, ["python3", "-m", "coverage", "run", "-m",
                               "pytest", "-q"])

    def test_no_detection_error_names_npm_script(self):
        (self.repo / "package.json").write_text(
            json.dumps({"name": "x", "scripts": {"test": "vitest run"}}),
            encoding="utf-8")
        code_kg.ingest(self.repo)
        with self.assertRaises(SystemExit) as ctx:
            code_kg.coverage_run(self.repo, yes=True)
        self.assertIn("vitest run", str(ctx.exception))

    def test_ingest_render_includes_readout(self):
        import io
        import contextlib
        (self.repo / "settings.py").write_text(
            'DATABASES = {"default": {"ENGINE":'
            ' "django.db.backends.postgresql"}}\n', encoding="utf-8")
        args = type("A", (), {"repo": str(self.repo), "json": False})()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code_kg.cmd_ingest(args)
        self.assertIn("data stores: postgres", buf.getvalue())


class TestRustWorkspace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp()
        cls.repo = Path(cls.tmpdir)
        gs = cls.repo / "crates" / "globset"
        (gs / "src").mkdir(parents=True)
        (gs / "Cargo.toml").write_text(
            '[package]\nname = "globset"\nversion = "0.1.0"\n\n'
            '[dependencies]\nserde = "1"\n', encoding="utf-8")
        (gs / "src" / "lib.rs").write_text(
            "pub struct Glob;\n\npub fn parse(p: &str) -> Glob { Glob }\n",
            encoding="utf-8")
        facade = cls.repo / "crates" / "facade"
        (facade / "src").mkdir(parents=True)
        (facade / "Cargo.toml").write_text(
            '[package]\nname = "facade"\nversion = "0.1.0"\n',
            encoding="utf-8")
        (facade / "src" / "lib.rs").write_text(
            "pub extern crate globset as gs;\n", encoding="utf-8")
        core = cls.repo / "crates" / "core"
        core.mkdir(parents=True)
        (core / "Cargo.toml").write_text(
            '[package]\nname = "grep-core"\nversion = "0.1.0"\n\n'
            '[[bin]]\nname = "rg"\npath = "main.rs"\n', encoding="utf-8")
        (core / "main.rs").write_text(
            "mod report;\n\nuse globset::Glob;\nuse serde::Serialize;\n\n"
            "fn main() {\n    let _g: Glob = globset::parse(\"*\");\n}\n",
            encoding="utf-8")
        (core / "report.rs").write_text(
            "use facade::gs::Glob;\n\n"
            "pub fn describe(g: &Glob) -> String { String::new() }\n",
            encoding="utf-8")
        code_kg.ingest(cls.repo)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _rows(self, sql):
        con = code_kg.connect(self.repo)
        rows = con.execute(sql).fetchall()
        con.close()
        return rows

    def test_workspace_member_use_resolves(self):
        rows = self._rows(
            "SELECT dst, status FROM edges WHERE src='crates/core/main.rs'"
            " AND target LIKE 'globset%'")
        self.assertIn(("crates/globset/src/lib.rs", "resolved"), rows)

    def test_external_crate_is_external_not_unresolved(self):
        rows = self._rows(
            "SELECT status FROM edges WHERE src='crates/core/main.rs'"
            " AND target LIKE 'serde%'")
        self.assertEqual([r[0] for r in rows], ["external"])
        self.assertEqual(self._rows(
            "SELECT count(*) FROM edges WHERE status='unresolved'")[0][0],
            0)

    def test_workspace_main_is_entry_point(self):
        rows = self._rows(
            "SELECT file_id FROM entry_points WHERE kind='main-guard'")
        self.assertIn(("crates/core/main.rs",), rows)

    def test_lib_reachable_not_dead(self):
        report = code_kg.dead_report(self.repo)
        self.assertIn("crates/globset/src/lib.rs",
                      report["tiers"]["live"])
        self.assertEqual(report["tiers"]["unreachable"], [])

    def test_pub_extern_is_reexport_kind(self):
        rows = self._rows(
            "SELECT kind FROM edges WHERE src='crates/facade/src/lib.rs'"
            " AND dst='crates/globset/src/lib.rs'")
        self.assertEqual([r[0] for r in rows], ["reexport"])

    def test_importers_follow_rust_facade(self):
        import io
        import contextlib
        args = type("A", (), {"repo": str(self.repo),
                              "path": "crates/globset/src/lib.rs",
                              "json": True})()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code_kg.cmd_importers(args)
        payload = json.loads(buf.getvalue())
        vias = {r["src"]: r.get("via") for r in payload if r.get("via")}
        self.assertEqual(vias.get("crates/core/report.rs"),
                         "crates/facade/src/lib.rs")


class TestGoPackageCohesion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp()
        cls.repo = Path(cls.tmpdir)
        (cls.repo / "go.mod").write_text(
            "module example.com/tool\n\ngo 1.22\n", encoding="utf-8")
        (cls.repo / "main.go").write_text(
            'package main\n\nimport "example.com/tool/util"\n\n'
            "func main() {\n    util.Run()\n}\n", encoding="utf-8")
        util = cls.repo / "util"
        util.mkdir()
        (util / "run.go").write_text(
            "package util\n\nfunc Run() {}\n", encoding="utf-8")
        (util / "helpers.go").write_text(
            "package util\n\nfunc clamp(n int) int { return n }\n",
            encoding="utf-8")
        (util / "helpers_test.go").write_text(
            'package util\n\nimport "testing"\n\n'
            "func TestClamp(t *testing.T) {}\n", encoding="utf-8")
        code_kg.ingest(cls.repo)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_import_reaches_every_package_file(self):
        con = code_kg.connect(self.repo)
        dsts = {r[0] for r in con.execute(
            "SELECT dst FROM edges WHERE src='main.go'"
            " AND status='resolved'")}
        con.close()
        self.assertIn("util/run.go", dsts)
        self.assertIn("util/helpers.go", dsts)
        self.assertNotIn("util/helpers_test.go", dsts)

    def test_package_peers_not_dead(self):
        report = code_kg.dead_report(self.repo)
        self.assertIn("util/helpers.go", report["tiers"]["live"])
        self.assertEqual(report["tiers"]["unreachable"], [])


class TestSearchRelaxation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp()
        cls.repo = Path(cls.tmpdir) / "repo"
        cls.repo.mkdir()
        (cls.repo / "full.py").write_text(
            "def process_upload():\n"
            '    """alpha beta gamma delta."""\n'
            "    return 1\n", encoding="utf-8")
        (cls.repo / "partial.py").write_text(
            "def compress_images():\n"
            '    """alpha beta only."""\n'
            "    return 2\n", encoding="utf-8")
        (cls.repo / "bedrock_extraction.py").write_text(
            "def _build_media_block():\n"
            '    """Assemble the media block payload."""\n'
            "    return 3\n", encoding="utf-8")
        for i in range(3):
            (cls.repo / f"common{i}.py").write_text(
                f"def shared_thing_{i}():\n"
                '    """omega sigma shared."""\n'
                "    return 4\n", encoding="utf-8")
        code_kg.ingest(cls.repo)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_thin_rung_relaxes_and_labels(self):
        r = code_kg.search(self.repo, "alpha beta gamma delta")
        self.assertEqual(r["rung"], "all-terms")
        files = [h["file"] for h in r["results"]]
        self.assertEqual(files[0], "full.py")
        self.assertIn("partial.py", files)
        relaxed = [h for h in r["results"] if h.get("rung") == "any-term"]
        self.assertTrue(relaxed)
        self.assertNotIn("rung", r["results"][0])

    def test_path_tokens_reach_symbol_units(self):
        r = code_kg.search(self.repo, "extraction media block")
        top = [h.get("qualname", h.get("file")) for h in r["results"][:3]]
        self.assertIn("_build_media_block", top, r["results"])

    def test_wide_rung_does_not_relax(self):
        r = code_kg.search(self.repo, "omega sigma")
        self.assertFalse([h for h in r["results"] if "rung" in h])


class TestProfileAndEntryConfig(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.repo = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _cfg(self, cfg):
        kg = self.repo / ".code-kg"
        kg.mkdir(exist_ok=True)
        (kg / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

    def test_config_entry_point_globs_and_warning(self):
        (self.repo / "a").mkdir()
        (self.repo / "a" / "x.py").write_text("x = 1\n", encoding="utf-8")
        (self.repo / "b.py").write_text("y = 2\n", encoding="utf-8")
        self._cfg({"entry_points": ["a/*.py", "nope/*.py"]})
        counts = code_kg.ingest(self.repo)
        con = code_kg.connect(self.repo)
        got = {r[0] for r in con.execute(
            "SELECT file_id FROM entry_points WHERE kind='config'")}
        con.close()
        self.assertEqual(got, {"a/x.py"})
        self.assertTrue(any("nope/*.py" in w
                            for w in counts["entry_warnings"]))

    def test_profile_override_generic(self):
        (self.repo / "manage.py").write_text(
            "if __name__ == \"__main__\":\n    pass\n", encoding="utf-8")
        self._cfg({"profile": "generic"})
        counts = code_kg.ingest(self.repo)
        self.assertEqual(counts["profiles"], [])


class TestCoverageParsers(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.files = {"app/util.py", "app/helpers.py"}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_lcov(self):
        data = code_kg.parse_coverage_artifact(
            self.tmp, ARTIFACTS / "lcov.info", self.files)
        self.assertEqual(data["app/util.py"][4], 4)
        self.assertEqual(data["app/util.py"][10], 0)
        # Absolute path outside the repo matches by suffix.
        self.assertEqual(data["app/helpers.py"][1], 2)

    def test_coverage_py_json(self):
        art = self.tmp / "cov.json"
        art.write_text(json.dumps({
            "meta": {}, "files": {
                "app/util.py": {"executed_lines": [1, 4],
                                "missing_lines": [10]}}}))
        data = code_kg.parse_coverage_artifact(self.tmp, art, self.files)
        self.assertEqual(data["app/util.py"], {1: 1, 4: 1, 10: 0})

    def test_istanbul(self):
        art = self.tmp / "coverage-final.json"
        art.write_text(json.dumps({
            "app/util.py": {"path": "app/util.py",
                            "statementMap": {"0": {"start": {"line": 3}}},
                            "s": {"0": 7}}}))
        data = code_kg.parse_coverage_artifact(self.tmp, art, self.files)
        self.assertEqual(data["app/util.py"][3], 7)

    def test_unrecognized_exits(self):
        art = self.tmp / "junk.txt"
        art.write_text("not coverage at all")
        with self.assertRaises(SystemExit):
            code_kg.parse_coverage_artifact(self.tmp, art, self.files)


def _dump_graph(repo: Path) -> str:
    con = code_kg.connect(repo, must_exist=True)
    parts = []
    for table, order in (("files", "id"), ("symbols", "id"),
                         ("edges", "src, kind, target, line"),
                         ("entry_points", "file_id, kind, detail"),
                         ("ignored", "path")):
        rows = con.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall()
        parts.append(f"== {table} ==")
        parts.extend(repr(r) for r in rows)
    con.close()
    return "\n".join(parts)


class TestIngestBehavior(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp()
        cls.repo = Path(cls.tmpdir) / "repo"
        shutil.copytree(FIXTURE, cls.repo)
        cls.counts = code_kg.ingest(cls.repo)
        cls.con = code_kg.connect(cls.repo, must_exist=True)

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def edge(self, src, kind, target):
        return self.con.execute(
            "SELECT dst, status FROM edges WHERE src=? AND kind=? AND"
            " target=?", (src, kind, target)).fetchone()

    def test_bare_ingest_seeds_gitignore(self):
        gi = self.repo / ".code-kg" / ".gitignore"
        self.assertTrue(gi.exists())
        self.assertIn("code-kg.db", gi.read_text())

    def test_counts(self):
        self.assertEqual(self.counts["files"], 23)
        self.assertEqual(self.counts["parse_errors"], 0)
        self.assertGreaterEqual(self.counts["entry_points"], 7)

    def test_determinism(self):
        before = _dump_graph(self.repo)
        code_kg.ingest(self.repo)
        after = _dump_graph(self.repo)
        self.assertEqual(before, after)

    def test_python_symbols_and_methods(self):
        rows = dict(self.con.execute(
            "SELECT qualname, kind FROM symbols WHERE file_id='app/util.py'"))
        self.assertEqual(rows["summarize_zones"], "function")
        self.assertEqual(rows["ZoneLedger"], "class")
        self.assertEqual(rows["ZoneLedger.record"], "method")

    def test_python_import_edges(self):
        self.assertEqual(self.edge("app/main.py", "from-import", "app.util"),
                         ("app/util.py", "resolved"))
        self.assertEqual(self.edge("app/main.py", "import", "app.missing"),
                         (None, "unresolved"))
        self.assertEqual(self.edge("app/util.py", "from-import", ".helpers"),
                         ("app/helpers.py", "resolved"))

    def test_string_literal_path_ref(self):
        self.assertEqual(
            self.edge("app/main.py", "path-ref", "queries/report.sql"),
            ("queries/report.sql", "resolved"))

    def test_ts_alias_and_relative(self):
        self.assertEqual(self.edge("web/index.ts", "import", "./lib/api"),
                         ("web/lib/api.ts", "resolved"))
        self.assertEqual(self.edge("web/index.ts", "import", "@app/models"),
                         ("web/models.ts", "resolved"))

    def test_bash_source_and_exec(self):
        self.assertEqual(
            self.edge("scripts/deploy.sh", "source", "scripts/common.sh"),
            ("scripts/common.sh", "resolved"))
        self.assertEqual(
            self.edge("scripts/deploy.sh", "exec", "app/main.py")[1],
            "resolved")

    def test_workflow_uses(self):
        self.assertEqual(
            self.edge(".github/workflows/ci.yml", "uses",
                      "./.github/actions/setup"),
            (".github/actions/setup/action.yml", "resolved"))
        self.assertEqual(
            self.edge(".github/workflows/ci.yml", "uses",
                      "actions/checkout@v4"),
            (None, "external"))

    def test_terraform_module(self):
        self.assertEqual(self.edge("infra/main.tf", "module",
                                   "./modules/net"),
                         ("infra/modules/net/main.tf", "resolved"))

    def test_dockerfile_copy(self):
        self.assertEqual(
            self.edge("Dockerfile", "copy", "queries/report.sql"),
            ("queries/report.sql", "resolved"))

    def test_markdown_links_fence_aware(self):
        self.assertEqual(self.edge("README.md", "link", "app/main.py"),
                         ("app/main.py", "resolved"))
        fenced = self.con.execute(
            "SELECT count(*) FROM edges WHERE src='README.md' AND"
            " target LIKE '%orphan%'").fetchone()[0]
        self.assertEqual(fenced, 0)

    def test_sql_symbols(self):
        rows = dict(self.con.execute(
            "SELECT qualname, kind FROM symbols WHERE"
            " file_id='queries/report.sql'"))
        self.assertEqual(rows["zone_flow"], "table")
        self.assertEqual(rows["flow_summary"], "view")

    def test_entry_points(self):
        rows = {(f, k) for f, k, _ in self.con.execute(
            "SELECT file_id, kind, detail FROM entry_points")}
        self.assertIn(("app/main.py", "main-guard"), rows)
        self.assertIn(("scripts/deploy.sh", "shebang"), rows)
        self.assertIn(("Dockerfile", "dockerfile"), rows)
        self.assertIn((".github/workflows/ci.yml", "workflow"), rows)
        self.assertIn(("pyproject.toml", "script"), rows)
        self.assertIn(("package.json", "bin"), rows)

    def test_pyproject_script_resolves_module(self):
        self.assertEqual(self.edge("pyproject.toml", "import", "app.main"),
                         ("app/main.py", "resolved"))


class TestLivenessAndCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp()
        cls.repo = Path(cls.tmpdir) / "repo"
        shutil.copytree(FIXTURE, cls.repo)
        code_kg.ingest(cls.repo)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_dead_tiers(self):
        report = code_kg.dead_report(self.repo)
        # Dockerfile COPYs the app dir, so the orphan ships in the image
        # (weak evidence) while nothing ever executes it.
        self.assertIn("app/orphan.py", report["tiers"]["weak-only"])
        self.assertIn("app/only_tested.py", report["tiers"]["test-only"])
        self.assertIn("app/util.py", report["tiers"]["live"])
        self.assertIn("app/__init__.py", report["tiers"]["live"])
        self.assertNotIn("app/orphan.py", report["tiers"]["live"])

    def test_coverage_roundtrip(self):
        out = code_kg.coverage_ingest(self.repo, ARTIFACTS / "lcov.info",
                                      "test")
        self.assertEqual(out["files_matched"], 2)
        rep = code_kg.coverage_report(self.repo)
        util = [f for f in rep["files"] if f["file"] == "app/util.py"][0]
        self.assertEqual(util["pct"], 50.0)
        uncovered = {u["symbol"] for u in rep["uncovered_symbols"]}
        self.assertIn("app/util.py::ZoneLedger", uncovered)
        report = code_kg.dead_report(self.repo)
        self.assertTrue(report["coverage_present"])
        self.assertIn("web/index.ts", report["live_but_never_covered"])

    def test_coverage_survives_reingest(self):
        code_kg.coverage_ingest(self.repo, ARTIFACTS / "lcov.info", "test")
        code_kg.ingest(self.repo)
        rep = code_kg.coverage_report(self.repo)
        self.assertTrue(rep["files"])


class TestScanSafety(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.repo = Path(self.tmpdir) / "repo"
        shutil.copytree(FIXTURE, self.repo)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_symlink_escape_refused(self):
        outside = Path(self.tmpdir) / "secret.py"
        outside.write_text("PASSWORD = 'hunter2'\n")
        (self.repo / "app" / "leak.py").symlink_to(outside)
        code_kg.ingest(self.repo)
        con = code_kg.connect(self.repo, must_exist=True)
        self.assertIsNone(con.execute(
            "SELECT id FROM files WHERE id='app/leak.py'").fetchone())
        rule = con.execute(
            "SELECT rule FROM ignored WHERE path='app/leak.py'").fetchone()
        con.close()
        self.assertEqual(rule, ("symlink-or-escape",))

    def test_config_ignore(self):
        code_kg.kg_dir(self.repo).mkdir(exist_ok=True)
        code_kg.config_path(self.repo).write_text(json.dumps(
            {**code_kg.DEFAULT_CONFIG, "ignore": ["web/**"]}))
        code_kg.ingest(self.repo)
        con = code_kg.connect(self.repo, must_exist=True)
        n = con.execute("SELECT count(*) FROM files WHERE id LIKE"
                        " 'web/%'").fetchone()[0]
        rules = {r[0] for r in con.execute(
            "SELECT rule FROM ignored WHERE path LIKE 'web/%'")}
        con.close()
        self.assertEqual(n, 0)
        self.assertEqual(rules, {"config:web/**"})

    def test_drift_reingest(self):
        code_kg.ingest(self.repo)
        (self.repo / "app" / "fresh.py").write_text("def newcomer():\n"
                                                    "    return 1\n")
        result = code_kg.search(self.repo, "newcomer")
        hits = {h.get("symbol", "") for h in result["results"]}
        self.assertIn("app/fresh.py::newcomer", hits)


DEPS_FIXTURE = Path(__file__).resolve().parent / "fixture-deps"


class TestDepsIndexing(unittest.TestCase):
    """Dependency code is visible on request, firewalled by default."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.repo = Path(self.tmpdir) / "repo"
        shutil.copytree(DEPS_FIXTURE, self.repo)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def set_deps(self, mode: str) -> None:
        cfg_file = self.repo / ".code-kg" / "config.json"
        cfg = json.loads(cfg_file.read_text())
        cfg["deps"] = mode
        cfg_file.write_text(json.dumps(cfg, indent=2, sort_keys=True))

    def test_deps_none_keeps_current_behavior(self):
        self.set_deps("none")
        counts = code_kg.ingest(self.repo)
        self.assertEqual(counts["dep_files"], 0)
        con = code_kg.connect(self.repo, must_exist=True)
        row = con.execute(
            "SELECT dst, status FROM edges WHERE src='app.py' AND"
            " target='helperlib'").fetchone()
        con.close()
        self.assertEqual(row, (None, "external"))

    def test_referenced_deps_indexed_and_remapped(self):
        counts = code_kg.ingest(self.repo)
        self.assertGreater(counts["dep_files"], 0)
        con = code_kg.connect(self.repo, must_exist=True)
        init = ".venv/lib/python3.12/site-packages/helperlib/__init__.py"
        self.assertEqual(
            con.execute("SELECT dst, status FROM edges WHERE src='app.py'"
                        " AND target='helperlib'").fetchone(),
            (init, "dep"))
        self.assertEqual(
            con.execute("SELECT dst, status FROM edges WHERE src='app.py'"
                        " AND target='helperlib.core'").fetchone(),
            (init, "dep"))
        self.assertEqual(
            con.execute("SELECT dst, status FROM edges WHERE src='app.py'"
                        " AND target='missingpkg'").fetchone(),
            (None, "external"))
        self.assertEqual(
            con.execute("SELECT dst, status FROM edges WHERE src='index.js'"
                        " AND target='leftpad'").fetchone(),
            ("node_modules/leftpad/index.js", "dep"))
        origins = dict(con.execute(
            "SELECT origin, count(*) FROM files GROUP BY origin"))
        self.assertGreaterEqual(origins.get("dep", 0), 4)
        dep_symbols = {r[0] for r in con.execute(
            "SELECT qualname FROM symbols WHERE file_id LIKE '.venv/%'")}
        con.close()
        self.assertIn("Widget.grow", dep_symbols)
        self.assertIn("clamp", dep_symbols)

    def test_search_firewall(self):
        code_kg.ingest(self.repo)
        blocked = code_kg.search(self.repo, "xylophone_marker_token")
        self.assertEqual(blocked["results"], [])
        allowed = code_kg.search(self.repo, "xylophone_marker_token",
                                 include_deps=True)
        self.assertTrue(allowed["results"])

    def test_dep_edges_never_join_liveness(self):
        code_kg.ingest(self.repo)
        report = code_kg.dead_report(self.repo)
        all_tiers = [f for tier in report["tiers"].values() for f in tier]
        self.assertNotIn(
            ".venv/lib/python3.12/site-packages/helperlib/core.py",
            all_tiers)
        self.assertIn("app.py", report["tiers"]["live"])

    def test_deps_determinism(self):
        code_kg.ingest(self.repo)
        before = _dump_graph(self.repo)
        code_kg.ingest(self.repo)
        self.assertEqual(before, _dump_graph(self.repo))


RELAY = Path(__file__).resolve().parent / "fixture-relay"
RELAY_KEY = Path(__file__).resolve().parent / "fixture-relay-key.json"


class TestRelayAnswerKey(unittest.TestCase):
    """The 3k-LOC agentic fixture, validated against hand-authored ground
    truth: exact symbol inventory per file, required resolved edges, exact
    entry-point set, exact liveness tiers, exact unresolved worklist."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp()
        cls.repo = Path(cls.tmpdir) / "relay"
        shutil.copytree(RELAY, cls.repo,
                        ignore=shutil.ignore_patterns(".code-kg",
                                                      "__pycache__"))
        cls.key = json.loads(RELAY_KEY.read_text())
        code_kg.ingest(cls.repo)
        cls.con = code_kg.connect(cls.repo, must_exist=True)

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_symbol_inventory_exact(self):
        for fid, expected in self.key["symbols"].items():
            got = dict(self.con.execute(
                "SELECT qualname, kind FROM symbols WHERE file_id=?",
                (fid,)))
            self.assertEqual(got, expected, f"symbol set mismatch in {fid}")

    def test_no_parse_errors(self):
        rows = [r[0] for r in self.con.execute(
            "SELECT id FROM files WHERE parse_error != ''")]
        self.assertEqual(rows, [])

    def test_required_edges_resolved(self):
        for src, kind, target, dst in self.key["resolved_edges"]:
            row = self.con.execute(
                "SELECT dst, status FROM edges WHERE src=? AND kind=?"
                " AND target=?", (src, kind, target)).fetchone()
            self.assertIsNotNone(row, f"missing edge {src} -{kind}-> {target}")
            self.assertEqual(row, (dst, "resolved"),
                             f"edge {src} -{kind}-> {target}")

    def test_entry_points_exact(self):
        got = {(f, k) for f, k in self.con.execute(
            "SELECT DISTINCT file_id, kind FROM entry_points")}
        expected = {tuple(e) for e in self.key["entry_points"]}
        self.assertEqual(got, expected)

    def test_liveness_tiers_exact(self):
        report = code_kg.dead_report(self.repo)
        for tier, files in self.key["tiers"].items():
            self.assertEqual(report["tiers"][tier], sorted(files),
                             f"tier {tier}")

    def test_unresolved_exact(self):
        got = {(s, k, t) for s, k, t in self.con.execute(
            "SELECT src, kind, target FROM edges WHERE status IN"
            " ('unresolved','ambiguous')")}
        expected = {tuple(u) for u in self.key["unresolved"]}
        self.assertEqual(got, expected)


class TestCli(unittest.TestCase):
    """End to end through the actual CLI surface."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp()
        cls.repo = Path(cls.tmpdir) / "repo"
        shutil.copytree(FIXTURE, cls.repo)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def run_cli(self, *argv):
        return subprocess.run(
            [sys.executable, str(ENGINE), *argv],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})

    def test_workflow(self):
        out = self.run_cli("ingest", str(self.repo))
        self.assertEqual(out.returncode, 0, out.stderr)
        out = self.run_cli("search", str(self.repo), "clamp flow", "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        hits = json.loads(out.stdout)["results"]
        self.assertTrue(any(h.get("symbol", "").endswith("clamp_flow")
                            for h in hits))
        out = self.run_cli("dead", str(self.repo), "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("app/orphan.py",
                      json.loads(out.stdout)["tiers"]["weak-only"])
        out = self.run_cli("read", str(self.repo),
                           "app/helpers.py::clamp_flow")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("def clamp_flow", out.stdout)
        out = self.run_cli("coverage", str(self.repo), "run")
        self.assertEqual(out.returncode, 1)
        self.assertIn("--yes", out.stderr)

    def test_index_idempotent(self):
        self.run_cli("ingest", str(self.repo))
        a = self.run_cli("index", str(self.repo))
        b = self.run_cli("index", str(self.repo))
        self.assertEqual(a.returncode, 0, a.stderr)
        self.assertEqual(a.stdout, b.stdout)
        self.assertIn("app/orphan.py", a.stdout)


if __name__ == "__main__":
    unittest.main()
