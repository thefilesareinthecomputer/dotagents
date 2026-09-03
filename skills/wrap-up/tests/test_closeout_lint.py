#!/usr/bin/env python3
"""Tests for closeout_lint.py - stdlib only.

    python3 -m unittest discover skills/wrap-up/tests

The positive fixtures are real defects that a model-based review had to spend a
pass on: a shell block referencing a variable copied in from another skill, an
ordered list numbered against the wrong base, a count claim standing above the
wrong number of bullets. Each one is the shape it was found in.

The quiet tests matter as much. A closeout sweep that fires on ordinary prose
gets skipped within a week, and a skipped gate protects nothing - so the repo's
own tree is a fixture, and so is every near-miss that must not fire.

The last class of test is about honesty: the judgment findings from the same
review are here as negative fixtures, asserting the linter stays silent on them.
It cannot read a sentence for truth, and a suite that pretended otherwise would
license skipping the reviewer.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "closeout_lint.py"
REPO_ROOT = SCRIPT.resolve().parents[3]

ZWSP = chr(0x200B)
VS16 = chr(0xFE0F)             # VARIATION SELECTOR-16 - the scanner's WARN class

# Built from parts on purpose. A literal station path or address in this file
# would be a finding in the repo's own tree, and the sweep would flag its own
# test suite forever.
STATION_PATH = "/Users/" + "jdoe" + "/dev/thing"
STATION_EMAIL = "jane.doe" + "@" + "somewhere.io"


def run(*args: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    return proc.returncode, proc.stdout


class LintCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def write(self, name: str, content: str) -> str:
        path = self.dir / name
        path.write_text(content, encoding="utf-8")
        return str(path)

    def lint(self, content: str, name: str = "SKILL.md") -> tuple[int, str]:
        return run(self.write(name, content))

    def rules(self, content: str, name: str = "SKILL.md") -> list[str]:
        code, out = run("--json", self.write(name, content))
        return [f["rule"] for f in json.loads(out)["findings"]]


class TestUndefinedShellVars(LintCase):
    def test_catches_variable_no_block_assigns(self) -> None:
        code, out = self.lint(
            "## Step 2\n\n```bash\n"
            'bash "$SKILL_DIR/scripts/inbox.sh" --repo .\n'
            "```\n"
        )
        self.assertEqual(code, 1)
        self.assertIn("undefined-shell-var", out)
        self.assertIn("$SKILL_DIR", out)

    def test_quiet_when_assigned_in_the_same_block(self) -> None:
        code, out = self.lint(
            "```bash\n"
            'SKILL_DIR="$HOME/.agents/skills/agent-mail"\n'
            'bash "$SKILL_DIR/scripts/inbox.sh" --repo .\n'
            "```\n"
        )
        self.assertEqual(code, 0, out)

    def test_quiet_when_assigned_in_an_earlier_block(self) -> None:
        code, out = self.lint(
            "```bash\nOUT=/tmp/x\n```\n\nProse between.\n\n```bash\ncat \"$OUT\"\n```\n"
        )
        self.assertEqual(code, 0, out)

    def test_quiet_on_ambient_and_positional_vars(self) -> None:
        code, out = self.lint(
            "```bash\ncd \"$HOME/.agents\" && echo \"$1 $? ${PWD}\"\n```\n"
        )
        self.assertEqual(code, 0, out)

    def test_quiet_on_awk_field_syntax(self) -> None:
        code, out = self.lint("```bash\ngit log | awk '{print $2, $NF}'\n```\n")
        self.assertEqual(code, 0, out)

    def test_ignores_non_shell_blocks(self) -> None:
        code, out = self.lint("```python\nprint(f\"${MISSING}\")\n```\n")
        self.assertEqual(code, 0, out)


class TestOrdinals(LintCase):
    def test_catches_list_numbered_against_the_wrong_base(self) -> None:
        code, out = self.lint(
            "## Why this order\n\n"
            "1. Fetch before anything.\n"
            "2. Security review first.\n"
            "3. Inbox before reflect.\n\n"
            "## Step 0 - Assess\n\n## Step 1 - Security review\n\n## Step 2 - Inbox\n"
        )
        self.assertEqual(code, 1)
        self.assertIn("ordinal-mismatch", out)

    def test_catches_non_contiguous_numbering(self) -> None:
        self.assertIn("ordinal-mismatch", self.rules("1. one\n2. two\n2. two again\n"))

    def test_quiet_when_list_matches_its_headings(self) -> None:
        code, out = self.lint(
            "## Why this order\n\n"
            "0. Fetch before anything.\n"
            "1. Security review first.\n"
            "2. Inbox before reflect.\n\n"
            "## Step 0 - Assess\n\n## Step 1 - Security review\n\n## Step 2 - Inbox\n"
        )
        self.assertEqual(code, 0, out)

    def test_quiet_on_lazy_numbering(self) -> None:
        code, out = self.lint("1. first\n1. second\n1. third\n")
        self.assertEqual(code, 0, out)

    def test_quiet_on_multi_line_items(self) -> None:
        code, out = self.lint(
            "1. First item.\n   Continued on another line.\n\n"
            "2. Second item.\n   Also continued.\n"
        )
        self.assertEqual(code, 0, out)


class TestCounts(LintCase):
    def test_catches_claim_above_the_wrong_number_of_bullets(self) -> None:
        code, out = self.lint(
            "Three rules that matter here specifically:\n\n"
            "- first\n- second\n- third\n- fourth\n"
        )
        self.assertEqual(code, 1)
        self.assertIn("count-mismatch", out)
        self.assertIn("4 follow", out)

    def test_catches_claim_above_a_table(self) -> None:
        self.assertIn("count-mismatch", self.rules(
            "Three shapes cover nearly everything:\n\n"
            "| Shape | Meaning |\n|---|---|\n| A | x |\n| B | y |\n"
        ))

    def test_quiet_when_the_count_is_right(self) -> None:
        code, out = self.lint(
            "Four rules that matter here specifically:\n\n"
            "- first\n- second\n- third\n- fourth\n"
        )
        self.assertEqual(code, 0, out)

    def test_nested_bullets_do_not_count(self) -> None:
        code, out = self.lint(
            "Two outcomes:\n\n- first\n  - detail\n  - more detail\n- second\n"
        )
        self.assertEqual(code, 0, out)

    def test_quiet_when_one_number_on_the_line_is_right(self) -> None:
        code, out = self.lint(
            "The chain loads six skill bodies totaling 12 sections:\n\n"
            "- a\n- b\n- c\n- d\n- e\n- f\n"
        )
        self.assertEqual(code, 0, out)

    def test_quiet_when_prose_follows_rather_than_a_list(self) -> None:
        code, out = self.lint(
            "Two things this step catches:\n\nSecrets, and station constants.\n"
        )
        self.assertEqual(code, 0, out)


class TestStationPaths(LintCase):
    def test_catches_absolute_home_directory(self) -> None:
        code, out = self.lint(f"Run it from `{STATION_PATH}`.\n")
        self.assertEqual(code, 1)
        self.assertIn("station-path", out)

    def test_catches_email_address(self) -> None:
        self.assertIn("station-path", self.rules(f"Contact: {STATION_EMAIL}\n"))

    def test_quiet_on_neutral_placeholders(self) -> None:
        code, out = self.lint(
            "For example `/Users/me/code/app` or `/home/user/x`, mail nobody@example.com.\n"
        )
        self.assertEqual(code, 0, out)

    def test_quiet_on_reserved_fixture_domains(self) -> None:
        code, out = self.lint("The factory builds `buyer@example.test` rows.\n")
        self.assertEqual(code, 0, out)

    def test_quiet_on_home_relative_paths(self) -> None:
        code, out = self.lint("Skills live in `~/.agents/skills` and `$HOME/.claude`.\n")
        self.assertEqual(code, 0, out)


class TestIdentifiers(LintCase):
    """The negative cases are the point. Every value below has been flagged by a
    scan at some stage and cost a session an argument, so each one is pinned as a
    fixture: a gate that cries wolf on its own placeholders gets muted, and a
    muted gate is worse than no gate."""

    # Fabricated, and belonging to no board anywhere. It has to be a value the
    # suppressor does NOT filter, or this positive case would pass vacuously. It
    # is joined to its prefix at runtime because the station's write-time hook
    # refuses a prefixed literal in this tree - the same reason test_board.py
    # does it - not to hide anything from the sweep.
    UNSUPPRESSED_ID = "510001"

    def test_catches_a_tracker_shaped_identifier(self) -> None:
        body = "Split " + "STORY-" + self.UNSUPPRESSED_ID + " into three.\n"
        self.assertIn("work-item-id", self.rules(body))
        # A candidate, so it surfaces without failing an ordinary run; --strict is
        # where the caller asks for it to block.
        self.assertEqual(self.lint(body)[0], 0)
        self.assertEqual(run("--strict", self.write("STRICT.md", body))[0], 1)

    def test_quiet_on_zero_sequence_placeholder(self) -> None:
        code, out = self.lint("The scaffolder emits STORY-" + "000001" + ".\n")
        self.assertEqual(code, 0, out)

    def test_quiet_on_repdigit_and_sequential_stand_ins(self) -> None:
        code, out = self.lint(
            "Fixtures use STORY-" + "777777" + ", STORY-" + "123456"
            + " and STORY-" + "654321" + ".\n")
        self.assertEqual(code, 0, out)

    def test_quiet_on_nnnn_placeholder(self) -> None:
        code, out = self.lint("Gap-filled items take STORY-NNNN01.\n")
        self.assertEqual(code, 0, out)

    def test_quiet_on_public_format_acronyms(self) -> None:
        # OKF is Google's public Open Knowledge Format, not a private alias, and
        # has been mistaken for one more than once.
        code, out = self.lint("The OKF bundle feeds the KG, per the OKF spec.\n")
        self.assertEqual(code, 0, out)

    def test_live_credential_prefixes_fail_unconditionally(self) -> None:
        # Split so this fixture does not trip the sweep on its own file. The
        # unconditional-FAIL path is the load-bearing half of the credential
        # check, so it is pinned rather than left to a manual probe.
        for token in ("AKIA" + "IOSFODNN7EXAMPLE",
                      "ghp_" + "a" * 36,
                      "sk-ant-api03-" + "b" * 40):
            with self.subTest(token=token[:8]):
                body = f"key = {token}\n"
                self.assertIn("credential-shape", self.rules(body))
                self.assertEqual(self.lint(body)[0], 1)

    def test_indented_encrypted_pem_still_fails(self) -> None:
        body = (
            "  -----BEGIN RSA PRIVATE KEY-----\n"
            "  Proc-Type: 4,ENCRYPTED\n"
            "  DEK-Info: AES-128-CBC,0123456789ABCDEF\n"
            "\n"
            "  MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQ\n"
        )
        self.assertEqual(self.lint(body)[0], 1)

    def test_credential_marker_alone_is_a_warning_not_a_failure(self) -> None:
        code, out = self.lint("The fixture asserts on `BEGIN PRIVATE KEY`.\n")
        self.assertEqual(code, 0, out)
        self.assertIn("credential-shape", self.rules(
            "The fixture asserts on `BEGIN PRIVATE KEY`.\n"))


class TestCrossReferences(LintCase):
    def test_catches_broken_markdown_link(self) -> None:
        code, out = self.lint("See [the checklist](references/nope.md) for details.\n")
        self.assertEqual(code, 1)
        self.assertIn("dead-xref", out)

    def test_quiet_on_links_that_resolve(self) -> None:
        (self.dir / "references").mkdir()
        (self.dir / "references" / "real.md").write_text("# real\n", encoding="utf-8")
        code, out = self.lint("See [it](references/real.md).\n")
        self.assertEqual(code, 0, out)

    def test_quiet_on_external_links(self) -> None:
        code, out = self.lint("See [the standard](https://agentskills.io) and [top](#top).\n")
        self.assertEqual(code, 0, out)

    def test_quiet_on_documented_link_syntax(self) -> None:
        code, out = self.lint("Write it as [display text](url) or [alt](path.md).\n")
        self.assertEqual(code, 0, out)

    def test_quiet_on_paths_belonging_to_another_repo(self) -> None:
        code, out = self.lint(
            "The tool reads `target/manifest.json` and `.obsidian/app.json` in the "
            "project it is pointed at, and every `tasks/SPEC-*.md` here.\n"
        )
        self.assertEqual(code, 0, out)


class TestDelegatedScanner(LintCase):
    def test_catches_invisible_unicode(self) -> None:
        code, out = self.lint(f"del{ZWSP}ete everything\n")
        self.assertEqual(code, 1)
        self.assertIn("invisible-unicode", out)

    def test_scanner_is_where_this_script_expects_it(self) -> None:
        scanner = (REPO_ROOT / "skills" / "my-security-review-checklist"
                   / "scripts" / "unicode_smuggle_check.py")
        self.assertTrue(scanner.is_file(), f"delegation target missing: {scanner}")

    def test_warn_severity_passes_through_without_failing(self) -> None:
        content = f"status: check{VS16}\n"
        code, out = self.lint(content)
        self.assertEqual(code, 0)
        self.assertIn("WARN", out)
        self.assertEqual(run("--strict", self.write("other.md", content))[0], 1)


class TestTiering(LintCase):
    def tier(self, *paths: str) -> dict:
        code, out = run("--tier", "--json", *paths)
        self.assertEqual(code, 0, out)
        return json.loads(out)

    def test_prose_is_tier_b(self) -> None:
        self.assertEqual(self.tier(self.write("SPEC.md", "# spec\n"))["tier"], "B")

    def test_a_script_is_tier_a(self) -> None:
        self.assertEqual(self.tier(self.write("sync.sh", "echo hi\n"))["tier"], "A")

    def test_a_subagent_definition_is_tier_a(self) -> None:
        (self.dir / "agents").mkdir()
        (self.dir / "agents" / "reader.md").write_text("---\nname: reader\n---\n",
                                                       encoding="utf-8")
        result = self.tier(str(self.dir / "agents" / "reader.md"))
        self.assertEqual(result["tier"], "A")

    def test_harness_settings_are_tier_a(self) -> None:
        self.assertEqual(self.tier(self.write("settings.local.json", "{}\n"))["tier"], "A")

    def test_one_executable_file_lifts_the_whole_diff(self) -> None:
        result = self.tier(self.write("notes.md", "# notes\n"),
                           self.write("hook.py", "print(1)\n"))
        self.assertEqual(result["tier"], "A")
        self.assertEqual(len(result["deciders"]), 1)

    def test_a_shell_block_in_prose_is_named_without_lifting_the_tier(self) -> None:
        path = self.write("SKILL.md", "# skill\n\n```bash\ngh api repos/$r\n```\n")
        result = self.tier(path)
        self.assertEqual(result["tier"], "B")
        self.assertEqual(len(result["command_files"]), 1)

    def test_prose_without_a_shell_block_names_nothing(self) -> None:
        path = self.write("SKILL.md", "# skill\n\n```json\n{\"a\": 1}\n```\n")
        result = self.tier(path)
        self.assertEqual(result["tier"], "B")
        self.assertEqual(result["command_files"], [])

    def test_an_executable_file_is_not_double_counted(self) -> None:
        result = self.tier(self.write("sync.sh", "echo hi\n"))
        self.assertEqual(result["tier"], "A")
        self.assertEqual(result["command_files"], [])

    def test_the_tier_is_announced_in_the_default_output(self) -> None:
        code, out = self.lint("# clean prose\n")
        self.assertEqual(code, 0)
        self.assertIn("tier: B", out)

    def test_tier_only_does_not_gate(self) -> None:
        path = self.write("SKILL.md", f"Run from `{STATION_PATH}`.\n")
        code, out = run("--tier", path)
        self.assertEqual(code, 0)
        self.assertNotIn("station-path", out)


class TestStaysQuiet(LintCase):
    CHAIN = ("wrap-up", "notes", "reflect", "repo-device-sync", "agent-mail",
             "my-security-review-checklist")

    def test_the_chains_own_skills_are_clean(self) -> None:
        code, out = run(*[str(REPO_ROOT / "skills" / name) for name in self.CHAIN])
        self.assertEqual(code, 0, out)

    def test_ordinary_prose_is_silent(self) -> None:
        code, out = self.lint(
            "# Notes\n\nThe sweep reads the tree, then reports. Nothing else.\n"
        )
        self.assertEqual(code, 0, out)
        self.assertIn("clean", out)


class TestDoesNotClaimJudgment(LintCase):
    """The reviewer's half of the work, asserted as out of reach.

    Both fixtures are real findings from the same review. Neither is decidable
    without reading for meaning, and the linter must not imply it checked them.
    """

    def test_silent_on_a_sentence_contradicting_a_table_below_it(self) -> None:
        code, out = self.lint(
            "Every row below is byte-for-byte identical to its source.\n\n"
            "| Element | Shape |\n|---|---|\n| settings | FRAGMENT, ten keys |\n"
        )
        self.assertEqual(code, 0, out)

    def test_silent_on_a_false_capability_claim(self) -> None:
        code, out = self.lint("This reviewer is read-only and holds no shell access.\n")
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
