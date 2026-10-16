#!/usr/bin/env python3
"""Tests for scripts/seed.py: table validation, each merger, the verbs end to
end in a temp home, idempotence, the not-installed skip and the agreement of
every specs/<harness>/seed.json row with that spec's Seeding table.
Run: python3 -m unittest discover -s skills/agent-cc-configs-sync/tests -v
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SCRIPT = HERE.parent / "scripts" / "seed.py"

spec = importlib.util.spec_from_file_location("seed", SCRIPT)
seed = importlib.util.module_from_spec(spec)
sys.modules["seed"] = seed
spec.loader.exec_module(seed)


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args, "--repo", str(REPO)],
                          text=True, capture_output=True)


class TableValidation(unittest.TestCase):
    def table(self, rows, harness="codex"):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        repo = Path(d)
        (repo / "specs" / harness).mkdir(parents=True)
        (repo / "specs" / harness / "seed.json").write_text(json.dumps({"schema": 1, "harness": harness, "rows": rows}))
        return repo

    def test_unknown_shape_rejected(self):
        with self.assertRaisesRegex(seed.SeedError, "six shapes"):
            seed.load_table(self.table([{"element": "x", "shape": "MERGE", "path": "~/a"}]), "codex")

    def test_absolute_station_path_rejected(self):
        with self.assertRaisesRegex(seed.SeedError, "portable"):
            seed.load_table(self.table([{"element": "x", "shape": "NATIVE", "path": "/Users/someone/a"}]), "codex")

    def test_fragment_needs_keys(self):
        with self.assertRaisesRegex(seed.SeedError, "keys"):
            seed.load_table(self.table([{"element": "x", "shape": "FRAGMENT", "path": "~/a", "format": "json"}]), "codex")

    def test_flat_formats_reject_dotted_keys(self):
        with self.assertRaisesRegex(seed.SeedError, "no dots"):
            seed.load_table(self.table([{"element": "x", "shape": "FRAGMENT", "path": "~/a", "format": "profile",
                                         "keys": {"A.B": 1}}]), "codex")

    def test_missing_source_rejected(self):
        with self.assertRaisesRegex(seed.SeedError, "missing seed file"):
            seed.load_table(self.table([{"element": "x", "shape": "COPY", "path": "~/a", "source": "specs/nope"}]), "codex")

    def test_wrong_harness_rejected(self):
        with self.assertRaisesRegex(seed.SeedError, "schema 1"):
            seed.load_table(self.table([], harness="codex"), "pi") if False else None
            repo = self.table([])
            (repo / "specs" / "pi").mkdir()
            shutil.copy(repo / "specs" / "codex" / "seed.json", repo / "specs" / "pi" / "seed.json")
            seed.load_table(repo, "pi")

    def test_every_shipped_table_loads(self):
        for h in [r.harness for r in seed.harness_probe.ROWS]:
            self.assertTrue(seed.load_table(REPO, h), h)


class JsonMerge(unittest.TestCase):
    def test_nested_path_set_and_indent_kept(self):
        out, ch = seed.merge_json('{\n    "a": 1,\n    "env": {"X": "1"}\n}\n', {"env.Y": "2", "a": 1})
        self.assertEqual(ch, ['env.Y = "2"'])
        self.assertEqual(json.loads(out), {"a": 1, "env": {"X": "1", "Y": "2"}})
        self.assertIn('\n    "a"', out)
        self.assertTrue(out.endswith("\n"))

    def test_no_trailing_newline_preserved(self):
        out, _ = seed.merge_json('{"a": 1}', {"b": 2})
        self.assertFalse(out.endswith("\n"))

    def test_flat_key_is_literal(self):
        out, ch = seed.merge_json_flat("{}", {"chat.useClaudeMdFile": True})
        self.assertEqual(json.loads(out), {"chat.useClaudeMdFile": True})
        self.assertEqual(ch, ["chat.useClaudeMdFile = true"])

    def test_parity_reports_no_change(self):
        _, ch = seed.merge_json('{"disableRemoteControl": true}', {"disableRemoteControl": True})
        self.assertEqual(ch, [])

    def test_was_value_named(self):
        _, ch = seed.merge_json('{"autoUpdatesChannel": "latest"}', {"autoUpdatesChannel": "stable"})
        self.assertEqual(ch, ['autoUpdatesChannel = "stable" (was "latest")'])

    def test_entries_pointer(self):
        out, ch = seed.merge_json_entries("", "/x/skills")
        self.assertEqual(json.loads(out), {"entries": [{"path": "/x/skills"}]})
        same, ch2 = seed.merge_json_entries(out, "/x/skills")
        self.assertEqual((same, ch2), (out, []))
        out3, ch3 = seed.merge_json_entries('{"entries": [{"path": "/other"}], "inherits": []}', "/x/skills")
        self.assertEqual(json.loads(out3)["entries"], [{"path": "/other"}, {"path": "/x/skills"}])
        self.assertEqual(json.loads(out3)["inherits"], [])


class TomlMerge(unittest.TestCase):
    KEYS = {"analytics.enabled": False, "features.daemon_auto_start": False}

    def test_existing_key_replaced_in_place(self):
        src = 'model = "x"\n\n[analytics]\nenabled = true\n\n[features]\ndaemon_auto_start = true\nmemories = false\n'
        out, ch = seed.merge_toml(src, self.KEYS)
        self.assertEqual(out, 'model = "x"\n\n[analytics]\nenabled = false\n\n[features]\ndaemon_auto_start = false\nmemories = false\n')
        self.assertEqual(ch, ["analytics.enabled = false (was true)", "features.daemon_auto_start = false (was true)"])

    def test_key_inserted_into_existing_table(self):
        out, _ = seed.merge_toml('[features]\nmemories = false\n', {"features.daemon_auto_start": False})
        self.assertEqual(out, '[features]\ndaemon_auto_start = false\nmemories = false\n')

    def test_missing_table_appended(self):
        out, _ = seed.merge_toml('model = "x"\n[profiles.a]\nanalytics = "no"\n', {"analytics.enabled": False})
        self.assertTrue(out.endswith('\n[analytics]\nenabled = false\n'))
        self.assertIn('[profiles.a]\nanalytics = "no"\n', out)

    def test_same_leaf_in_other_table_untouched(self):
        src = '[profiles.a]\nenabled = true\n'
        out, _ = seed.merge_toml(src, {"analytics.enabled": False})
        self.assertIn('[profiles.a]\nenabled = true\n', out)
        self.assertIn('[analytics]\nenabled = false\n', out)

    def test_root_dotted_key_replaced(self):
        out, _ = seed.merge_toml('analytics.enabled = true\nfeatures.memories = true\n', self.KEYS)
        self.assertEqual(out, 'analytics.enabled = false\nfeatures.memories = true\nfeatures.daemon_auto_start = false\n')

    def test_parity_no_change(self):
        _, ch = seed.merge_toml('[analytics]\nenabled = false\n[features]\ndaemon_auto_start = false\n', self.KEYS)
        self.assertEqual(ch, [])

    def test_unparseable_station_file_refused(self):
        with self.assertRaisesRegex(seed.SeedError, "does not parse"):
            seed.merge_toml('[analytics\nenabled = true\n', self.KEYS)

    def test_string_value_quoted(self):
        out, _ = seed.merge_toml("", {"otel.metrics_exporter": "none"})
        self.assertEqual(out, '[otel]\nmetrics_exporter = "none"\n')


class FlatMerges(unittest.TestCase):
    def test_yaml_replace_and_fold_duplicates(self):
        src = 'GOOSE_MODEL: x\nGOOSE_TELEMETRY_ENABLED: true\nother: 1\nGOOSE_TELEMETRY_ENABLED: true\n'
        out, ch = seed.merge_yaml_flat(src, {"GOOSE_TELEMETRY_ENABLED": False})
        self.assertEqual(out, 'GOOSE_MODEL: x\nGOOSE_TELEMETRY_ENABLED: false\nother: 1\n')
        self.assertEqual(ch, ["GOOSE_TELEMETRY_ENABLED: false (was true)"])

    def test_yaml_append_when_absent(self):
        out, _ = seed.merge_yaml_flat("GOOSE_MODEL: x", {"GOOSE_TELEMETRY_ENABLED": False})
        self.assertEqual(out, "GOOSE_MODEL: x\nGOOSE_TELEMETRY_ENABLED: false\n")

    def test_yaml_single_correct_key_is_parity(self):
        _, ch = seed.merge_yaml_flat("GOOSE_TELEMETRY_ENABLED: false\n", {"GOOSE_TELEMETRY_ENABLED": False})
        self.assertEqual(ch, [])

    def test_profile_append_and_replace(self):
        out, ch = seed.merge_profile("export PATH=/x\n", {"PI_TELEMETRY": 0})
        self.assertEqual(out, "export PATH=/x\nexport PI_TELEMETRY=0\n")
        out2, ch2 = seed.merge_profile(out.replace("=0", "=1"), {"PI_TELEMETRY": 0})
        self.assertEqual(out2, out)
        self.assertEqual(ch2, ["export PI_TELEMETRY=0 (was 1)"])
        _, ch3 = seed.merge_profile(out, {"PI_TELEMETRY": 0})
        self.assertEqual(ch3, [])

    def test_profile_value_needing_quotes_refused(self):
        with self.assertRaises(seed.SeedError):
            seed.merge_profile("", {"X": "a b"})


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home)
        # sync-skills.sh reads $HOME/.agents, so the fake home gets a tiny repo view
        (self.home / ".agents" / "skills" / "demo").mkdir(parents=True)
        (self.home / ".agents" / "skills" / "demo" / "SKILL.md").write_text("---\nname: demo\ndescription: d\n---\n")
        (self.home / ".agents" / "agents").mkdir()
        (self.home / ".agents" / "commands").mkdir()
        self.home_arg = ["--home", str(self.home)]

    def test_plan_writes_nothing(self):
        r = run("plan", "--harness", "antigravity", "--force", *self.home_arg)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("absent, write pointer", r.stdout)
        self.assertFalse((self.home / ".gemini").exists())

    def test_antigravity_pointer_written_once(self):
        r = run("apply", "--harness", "antigravity", "--force", *self.home_arg)
        self.assertEqual(r.returncode, 0, r.stderr)
        p = self.home / ".gemini" / "config" / "skills.json"
        self.assertEqual(json.loads(p.read_text()), {"entries": [{"path": str((REPO / "skills").resolve())}]})
        r2 = run("apply", "--harness", "antigravity", "--force", *self.home_arg)
        self.assertNotIn("wrote", r2.stdout)
        self.assertIn("names", r2.stdout)

    def test_pointer_present_and_different_is_never_overwritten(self):
        (self.home / ".claude").mkdir()
        (self.home / ".claude" / "CLAUDE.md").write_text("# mine\n")
        r = run("apply", "--harness", "claude-code", "--force", "--element", "Rules", *self.home_arg)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("never overwritten", r.stdout)
        self.assertEqual((self.home / ".claude" / "CLAUDE.md").read_text(), "# mine\n")

    def test_claude_code_full_apply_then_idempotent(self):
        (self.home / ".claude").mkdir()
        (self.home / ".claude" / "settings.json").write_text('{\n  "model": "opus",\n  "autoUpdatesChannel": "stable"\n}\n')
        (self.home / ".claude" / "statusline.sh").write_text("old\n")
        r = run("apply", "--harness", "claude-code", "--force", *self.home_arg)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertTrue((self.home / ".claude" / "skills" / "demo").is_symlink())
        self.assertEqual((self.home / ".claude" / "CLAUDE.md").read_text(),
                         (REPO / "specs/claude-code/CLAUDE.md.example").read_text())
        s = json.loads((self.home / ".claude" / "settings.json").read_text())
        self.assertEqual(s["model"], "opus")                       # station-owned key kept
        self.assertEqual(s["autoUpdatesChannel"], "latest")        # seeded key won
        self.assertIs(s["disableRemoteControl"], True)
        self.assertEqual(s["env"]["DISABLE_TELEMETRY"], "1")
        self.assertIn("hooks", s)                                  # seed_hooks ran after the fragment
        self.assertEqual((self.home / ".claude" / "statusline.sh").read_text(),
                         (REPO / "specs/claude-code/statusline.sh").read_text())
        self.assertTrue((self.home / ".claude" / "keybindings.json").is_file())
        r2 = run("apply", "--harness", "claude-code", "--force", *self.home_arg)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertNotIn("wrote", r2.stdout)
        self.assertIn("in parity", r2.stdout)

    def test_codex_toml_fragment(self):
        (self.home / ".codex").mkdir()
        (self.home / ".codex" / "config.toml").write_text('model = "gpt"\n\n[features]\nmemories = false\n\n[projects."/x"]\ntrust_level = "trusted"\n')
        r = run("apply", "--harness", "codex", "--force", "--element", "Privacy and hygiene", *self.home_arg)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        import tomllib
        t = tomllib.loads((self.home / ".codex" / "config.toml").read_text())
        self.assertEqual(t["projects"]["/x"]["trust_level"], "trusted")
        self.assertEqual(t["features"], {"memories": False, "daemon_auto_start": False})
        self.assertEqual(t["analytics"], {"enabled": False})
        self.assertEqual(t["otel"], {"metrics_exporter": "none"})
        self.assertEqual(t["memories"], {"disable_on_external_context": True})

    def test_if_present_fragment_skipped_when_file_absent(self):
        repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, repo)
        (repo / "specs" / "copilot").mkdir(parents=True)
        (repo / "specs" / "copilot" / "seed.json").write_text(json.dumps({"schema": 1, "harness": "copilot", "rows": [
            {"element": "Rules, IDE", "shape": "FRAGMENT", "path": "~/ide/settings.json", "format": "json-flat",
             "if_present": True, "keys": {"chat.useClaudeMdFile": True}}]}))
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = seed.seed_harness("copilot", self.home, repo, True, [], True)
        self.assertEqual(rc, 0, buf.getvalue())
        self.assertIn("not present, skipped", buf.getvalue())
        self.assertFalse((self.home / "ide").exists())

    def test_broken_station_file_reports_and_continues(self):
        (self.home / ".cursor").mkdir()
        (self.home / ".cursor" / "cli-config.json").write_text("{not json")
        r = run("plan", "--harness", "cursor", "--force", *self.home_arg)
        self.assertEqual(r.returncode, 1)
        self.assertIn("error    Remote control", r.stdout)
        self.assertIn("native   Skills", r.stdout)

    def test_not_installed_is_skipped(self):
        seed.WHICH = lambda b: None
        try:
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = seed.seed_harness("goose", self.home, REPO, True, [], False)
        finally:
            seed.WHICH = shutil.which
        self.assertEqual(rc, 0)
        self.assertIn("not installed", buf.getvalue())
        self.assertFalse((self.home / ".config").exists())

    def test_config_home_alone_counts_as_installed(self):
        (self.home / ".config" / "goose").mkdir(parents=True)
        (self.home / ".config" / "goose" / "config.yaml").write_text("GOOSE_MODEL: x\n")
        seed.WHICH = lambda b: None
        try:
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = seed.seed_harness("goose", self.home, REPO, True, [], False)
        finally:
            seed.WHICH = shutil.which
        self.assertEqual(rc, 0, buf.getvalue())
        self.assertEqual((self.home / ".config" / "goose" / "config.yaml").read_text(),
                         "GOOSE_MODEL: x\nGOOSE_TELEMETRY_ENABLED: false\n")

    def test_unknown_harness_errors(self):
        r = run("plan", "--harness", "nope", *self.home_arg)
        self.assertEqual(r.returncode, 1)
        self.assertIn("unknown harness", r.stderr)


class StationStateIsNeverLostSilently(unittest.TestCase):
    """Review fixes: whole-value writes name what they drop, deny lists only
    grow, a symlinked station file is written through, --key narrows a row,
    --force refuses `all`, and a file is backed up once before it changes."""

    def test_plan_names_station_only_entries_a_whole_value_write_drops(self):
        cur = json.dumps({"env": {"A": "1", "LOCAL": "x"}, "enabledPlugins": {"p@m": True, "q@m": True}})
        _, ch = seed.merge_json(cur, {"env": {"A": "1"}, "enabledPlugins": {"p@m": True}})
        self.assertIn("env = object of 1 keys (was object of 2 keys); drops station-only LOCAL", ch)
        self.assertIn("enabledPlugins = object of 1 keys (was object of 2 keys); drops station-only q@m", ch)

    def test_station_deny_rules_survive_as_a_union(self):
        cur = json.dumps({"permissions": {"allow": ["Read(a)"], "deny": ["Read(secret)", "Bash(rm *)"]}})
        out, ch = seed.merge_json(cur, {"permissions": {"allow": ["Read(a)", "Read(b)"], "deny": ["Read(secret)"]}})
        self.assertEqual(json.loads(out)["permissions"]["deny"], ["Read(secret)", "Bash(rm *)"])
        self.assertEqual(json.loads(out)["permissions"]["allow"], ["Read(a)", "Read(b)"])
        self.assertNotIn("drops", ch[0])

    def test_station_ask_rules_survive_and_a_seed_without_the_list_counts_as_empty(self):
        cur = json.dumps({"permissions": {"ask": ["Bash(git push *)"], "deny": ["Read(secret)"]}})
        out, _ = seed.merge_json(cur, {"permissions": {"allow": ["Read(a)"]}})
        self.assertEqual(json.loads(out)["permissions"], {"allow": ["Read(a)"], "deny": ["Read(secret)"], "ask": ["Bash(git push *)"]})

    def test_key_without_element_runs_fragment_rows_only(self):
        home = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, home)
        (home / ".claude").mkdir()
        (home / ".claude" / "statusline.sh").write_text("mine\n")
        r = run("apply", "--harness", "claude-code", "--force", "--key", "autoUpdatesChannel", "--home", str(home))
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual((home / ".claude" / "statusline.sh").read_text(), "mine\n")   # COPY row did not run
        self.assertFalse((home / ".claude" / "CLAUDE.md").exists())                    # POINTER row did not run
        self.assertEqual(json.loads((home / ".claude" / "settings.json").read_text()), {"autoUpdatesChannel": "latest"})

    def test_json_fragment_diff_shows_seeded_keys_only(self):
        home = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, home)
        (home / ".cursor").mkdir()
        (home / ".cursor" / "cli-config.json").write_text(json.dumps({"authInfo": {"token": "SECRETVALUE"}, "privacyCache": {"ghostMode": False}}))
        r = run("plan", "--harness", "cursor", "--force", "--home", str(home))
        self.assertIn("ghostMode", r.stdout)
        self.assertNotIn("SECRETVALUE", r.stdout)

    def test_symlink_edges_are_refused_and_shown(self):
        home = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, home)
        outside = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, outside)
        (outside / "zshrc").write_text("")
        (home / ".zshrc").symlink_to(outside / "zshrc")
        with self.assertRaisesRegex(seed.SeedError, "outside the home"):
            seed.write_text_atomic(home / ".zshrc", "x", home)
        (home / "dangling").symlink_to(home / "nowhere")
        with self.assertRaisesRegex(seed.SeedError, "does not resolve"):
            seed.write_text_atomic(home / "dangling", "x", home)
        (home / ".codex").mkdir()
        (home / "real.toml").write_text("")
        (home / ".codex" / "config.toml").symlink_to(home / "real.toml")
        r = run("plan", "--harness", "codex", "--force", "--element", "Privacy and hygiene", "--home", str(home))
        self.assertIn("is a symlink; writes go through it", r.stdout)

    def test_backup_never_writes_through_a_planted_symlink(self):
        d = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, d)
        f = d / "config.toml"; f.write_text("a = 1\n")
        victim = d / "victim"; victim.write_text("keep\n")
        (d / ("config.toml" + seed.BACKUP_SUFFIX)).symlink_to(victim)
        seed.write_text_atomic(f, "a = 2\n", d)
        self.assertEqual(victim.read_text(), "keep\n")
        self.assertEqual((d / ("config.toml" + seed.BACKUP_SUFFIX)).read_text(), "a = 1\n")

    def test_symlinked_station_file_is_written_through(self):
        d = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, d)
        real = d / "dotfiles" / "zshrc"; real.parent.mkdir(); real.write_text("export PATH=/x\n")
        link = d / ".zshrc"; link.symlink_to(real)
        note = seed.write_text_atomic(link, "export PATH=/x\nexport PI_TELEMETRY=0\n", d)
        self.assertTrue(link.is_symlink())
        self.assertEqual(real.read_text(), "export PATH=/x\nexport PI_TELEMETRY=0\n")
        self.assertIn(str(real), note)
        self.assertEqual((real.with_name("zshrc" + seed.BACKUP_SUFFIX)).read_text(), "export PATH=/x\n")
        self.assertEqual([p.name for p in real.parent.iterdir() if "seed-tmp" in p.name], [])

    def test_key_filter_narrows_a_fragment_row(self):
        home = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, home)
        (home / ".claude").mkdir()
        (home / ".claude" / "settings.json").write_text('{"autoUpdatesChannel": "stable", "attribution": {"commit": "x"}}')
        r = run("apply", "--harness", "claude-code", "--force", "--element", "Permissions and settings",
                "--key", "autoUpdatesChannel", "--home", str(home))
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        s = json.loads((home / ".claude" / "settings.json").read_text())
        self.assertEqual(s["autoUpdatesChannel"], "latest")
        self.assertEqual(s["attribution"], {"commit": "x"})          # not named, not touched
        self.assertNotIn("disableRemoteControl", s)
        r2 = run("plan", "--harness", "claude-code", "--force", "--element", "Permissions and settings",
                 "--key", "nope", "--home", str(home))
        self.assertEqual(r2.returncode, 1)
        self.assertIn("does not seed: nope", r2.stdout)

    def test_force_with_all_is_refused(self):
        r = run("plan", "--harness", "all", "--force", "--home", tempfile.gettempdir())
        self.assertEqual(r.returncode, 2)
        self.assertIn("--force takes one harness", r.stderr)

    def test_apply_shows_the_diff_it_writes(self):
        home = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, home)
        (home / ".codex").mkdir()
        (home / ".codex" / "config.toml").write_text('[analytics]\nenabled = true\n')
        r = run("apply", "--harness", "codex", "--force", "--element", "Privacy and hygiene", "--home", str(home))
        self.assertIn("-enabled = true", r.stdout)
        self.assertIn("+enabled = false", r.stdout)
        self.assertTrue((home / ".codex" / ("config.toml" + seed.BACKUP_SUFFIX)).is_file())

    def test_profile_keys_must_be_shell_names(self):
        d = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, d)
        (d / "specs" / "pi").mkdir(parents=True)
        (d / "specs" / "pi" / "seed.json").write_text(json.dumps({"schema": 1, "harness": "pi", "rows": [
            {"element": "x", "shape": "FRAGMENT", "path": "~/.zshrc", "format": "profile", "keys": {"A-B": 0}}]}))
        with self.assertRaisesRegex(seed.SeedError, "shell variable names"):
            seed.load_table(d, "pi")

    def test_source_and_target_stay_inside_the_repo(self):
        d = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, d)
        (d / "specs" / "pi").mkdir(parents=True)
        for row in ({"element": "x", "shape": "POINTER", "path": "~/a", "format": "json-entries", "target": "../elsewhere"},
                    {"element": "x", "shape": "COPY", "path": "~/a", "source": "/etc/passwd"},
                    {"element": "x", "shape": "NATIVE", "path": "~/../root"}):
            (d / "specs" / "pi" / "seed.json").write_text(json.dumps({"schema": 1, "harness": "pi", "rows": [row]}))
            with self.assertRaises(seed.SeedError, msg=str(row)):
                seed.load_table(d, "pi")


class TablesAgreeWithSpecs(unittest.TestCase):
    """Every seed.json row names an element the spec's Seeding table carries with
    the same shape, so the machine-readable table cannot drift from the prose."""

    def seeding_rows(self, harness):
        text = next((REPO / "specs" / harness).glob("SPEC-*.md")).read_text()
        m = re.search(r"^#{2,3} Seeding\n(.*?)(?=^#{2,3} |\Z)", text, re.S | re.M)
        self.assertIsNotNone(m, f"{harness}: no Seeding section")
        rows = {}
        for line in m.group(1).splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2 and cells[0] not in ("Element", "---"):
                rows[cells[0].casefold()] = cells[1].strip("`").split("`")[0].strip()
        return rows

    def test_each_row_matches(self):
        for h in [r.harness for r in seed.harness_probe.ROWS]:
            table = self.seeding_rows(h)
            for row in seed.load_table(REPO, h):
                for name in [row["element"], *row.get("also", [])]:
                    self.assertIn(name.casefold(), table, f"{h}: {name} not in the spec's Seeding table")
                    self.assertEqual(table[name.casefold()], row["shape"], f"{h}: {name} shape differs")


if __name__ == "__main__":
    unittest.main()
