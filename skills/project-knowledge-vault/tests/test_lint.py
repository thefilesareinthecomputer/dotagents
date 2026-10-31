"""Linter: a fresh seed is clean, and every gate fires against a mutation that violates it."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCAFFOLD = SKILL / "scripts" / "vault_scaffold.py"
LINT = SKILL / "scripts" / "vault_lint.py"


def lint(vault: Path) -> tuple[int, list[dict]]:
    r = subprocess.run([sys.executable, str(LINT), str(vault), "--json"], capture_output=True, text=True)
    return r.returncode, json.loads(r.stdout)


def checks(findings: list[dict]) -> set[str]:
    return {f["check"] for f in findings}


class LintTest(unittest.TestCase):
    """Every test starts from a fresh seed in its own temporary folder."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        subprocess.run([sys.executable, str(SCAFFOLD), "--target", tmp.name, "--name", "T", "--no-graph"],
                       check=True, capture_output=True)
        self.v = Path(tmp.name) / "PROJECTS" / "T"

    def assertOnly(self, check: str, count: int | None = None) -> list[dict]:
        """The linter exits 1 and every finding is the named check."""
        code, findings = lint(self.v)
        self.assertEqual(code, 1)
        self.assertEqual(checks(findings), {check})
        if count is not None:
            self.assertEqual(len(findings), count)
        return findings

    def assertClean(self) -> None:
        self.assertEqual(lint(self.v)[0], 0)

    def test_fresh_seed_is_clean(self) -> None:
        code, findings = lint(self.v)
        self.assertEqual((code, findings), (0, []))

    def test_flat_fires_on_a_subdirectory_but_not_tooling(self) -> None:
        (self.v / "markdown-kg").mkdir()
        (self.v / "vault-kg").mkdir()
        (self.v / ".obsidian").mkdir()
        self.assertClean()
        (self.v / "raw").mkdir()
        self.assertOnly("flat")

    def test_frontmatter_fires_on_a_note_without_type(self) -> None:
        (self.v / "notes-updates.md").write_text("# UPDATES\n\nno frontmatter\n")
        code, findings = lint(self.v)
        self.assertEqual(code, 1)
        self.assertIn("frontmatter", checks(findings))

    def test_family_fires_on_a_wrong_type_value(self) -> None:
        p = self.v / "notes-email-notes.md"
        p.write_text(p.read_text().replace("type: email", "type: note", 1))
        self.assertOnly("family")

    def test_an_older_vault_with_split_chat_files_stays_clean(self) -> None:
        (self.v / "notes-general-notes.md").unlink()
        text = "---\ntype: chat_log\n---\n# CHAT-NOTES-CLIENT\n\n## 2026-01-02-ALL\n\nthread\n"
        (self.v / "notes-chat-notes-client.md").write_text(text)
        (self.v / "notes-chat-notes-internal.md").write_text(text.replace("CLIENT", "INTERNAL"))
        for name in ("notes-email-notes.md", "notes-learnings.md", "index.md", "log.md"):
            p = self.v / name
            p.write_text(p.read_text().replace("[[notes-general-notes]]", "[[notes-chat-notes-client]]")
                         .replace("[notes-general-notes](notes-general-notes.md)", "[notes-chat-notes-client](notes-chat-notes-client.md)")
                         .replace("## YYYY-MM-DD", "## 2026-01-01", 1 if name == "log.md" else 0))
        self.assertClean()

    def test_family_learns_the_alias_and_admits_its_unnumbered_notes(self) -> None:
        (self.v / "abc-glossary.md").write_text("---\ntype: glossary\n---\n# GLOSSARY\n")
        self.assertOnly("family")  # no abc-NN note yet, so abc is no alias
        (self.v / "abc-02-findings.md").write_text("---\ntype: reference\n---\n# FINDINGS\n")
        (self.v / "abc-decisions.md").write_text("---\ntype: ledger\n---\n# DECISIONS\n")
        self.assertClean()
        (self.v / "abc-topic.md").write_text("---\ntype: note\n---\n# TOPIC\n")
        self.assertOnly("family")
        (self.v / "abc-topic.md").unlink()
        (self.v / "2026-01-15-standup.md").write_text("---\ntype: reference\n---\n# S\n")
        (self.v / "2026-notes.md").write_text("---\ntype: reference\n---\n# N\n")
        code, findings = lint(self.v)
        self.assertEqual(code, 1)
        self.assertEqual({f["file"] for f in findings}, {"2026-01-15-standup.md", "2026-notes.md"})  # a date is no alias
        (self.v / "abc-02-findings.md").write_text("---\ntype: note\n---\n# FINDINGS\n")
        self.assertOnly("family")

    def test_family_fires_on_an_unknown_prefix(self) -> None:
        (self.v / "scratch-ideas.md").write_text("---\ntype: note\n---\n# Ideas\n")
        self.assertOnly("family")

    def test_reserved_fires_on_missing_log_and_frontmatter_on_index(self) -> None:
        (self.v / "log.md").unlink()
        p = self.v / "index.md"
        p.write_text('---\nokf_version: "0.2"\n---\n\n' + p.read_text())
        self.assertOnly("reserved", count=2)

    def test_seeded_reserved_files_carry_no_frontmatter(self) -> None:
        for name in ("index.md", "log.md"):
            self.assertFalse((self.v / name).read_text().startswith("---"), name)
        code, findings = lint(self.v)
        self.assertEqual(code, 0)
        self.assertNotIn("reserved", checks(findings))

    def test_filename_fires_on_uppercase_or_underscore(self) -> None:
        (self.v / "notes_Scratch.md").write_text("---\ntype: note\n---\n# x\n")
        code, findings = lint(self.v)
        self.assertEqual(code, 1)
        self.assertIn("filename", checks(findings))

    def test_wikilink_fires_on_a_dangling_target(self) -> None:
        with (self.v / "notes-updates.md").open("a") as f:
            f.write("\nSee [[notes-nowhere]] for detail.\n")
        self.assertOnly("wikilink")

    def test_wikilink_ignores_code_spans_fences_and_comments(self) -> None:
        with (self.v / "notes-updates.md").open("a") as f:
            f.write("\nA future note is `[[notes-later]]` until it lands.\n\n```\n[[notes-fenced]]\n```\n\n<!-- [[notes-commented]] -->\n")
        self.assertClean()

    def test_anchor_fires_on_a_missing_heading(self) -> None:
        with (self.v / "notes-updates.md").open("a") as f:
            f.write("\nDecided in [[notes-meeting-notes#YYYY-MM-DD-KICKOFF]].\n")
        self.assertOnly("anchor")

    def test_dated_fires_on_an_undated_notes_h2_but_not_the_register(self) -> None:
        with (self.v / "notes-questions.md").open("a") as f:
            f.write("\n## PLATFORM\n\n- **Which cluster?** Raised in passing.\n")
        self.assertClean()  # the register groups by topic and is exempt
        with (self.v / "notes-meeting-notes.md").open("a") as f:
            f.write("\n## PREP: YYYY-MM-DD-REVIEW\n\ntalking points\n\n## Related\n\n- [[00-brd]] - the why\n")
        self.assertClean()  # the allowed undated H2s
        with (self.v / "notes-learnings.md").open("a") as f:
            f.write("\n## YYYY-MM-DD - the deploy target moved\n\n### The target is blue\n\nfact\n")
        with (self.v / "notes-pr-reviews.md").open("a") as f:
            f.write("\n## PR-STORY-123-AB-YYYY-MM-DD\n\nreview\n")
        self.assertClean()  # a sweep headline and a story-keyed review
        with (self.v / "notes-updates.md").open("a") as f:
            f.write("\n## PR-STORY-456-CD-YYYY-MM-DD\n\nnot a review file\n")
        with (self.v / "notes-general-notes.md").open("a") as f:
            f.write("\n## Kickoff thread\n\ntext\n\n## YYYY-MM-DD kickoff\n\nno hyphen\n")
        self.assertOnly("dated", count=3)

    def test_dated_fires_on_log_out_of_order(self) -> None:
        (self.v / "log.md").write_text("# Change log\n\n## 2026-02-01\n\n- b\n\n## 2026-01-01\n\n- a\n\n## Build receipts\n\n- x\n")
        self.assertClean()  # an appendix after the last dated entry is allowed
        (self.v / "log.md").write_text("# Change log\n\n## Notes\n\n- n\n\n## 2026-01-01\n\n- a\n\n## 2026-02-01\n\n- b\n")
        self.assertOnly("dated", count=2)
        (self.v / "log.md").write_text("# Change log\n\n## Notes\n\n- n\n")
        self.assertOnly("dated")  # a log with no dated entry at all

    def test_board_fires_when_user_stories_restates_the_grammar(self) -> None:
        with (self.v / "user-stories.md").open("a") as f:
            f.write("\nEach item declares `- Parent: FEATURE-{id}` under its title.\n")
        self.assertOnly("board")

    def test_placeholder_fires_only_beside_real_dates(self) -> None:
        p = self.v / "notes-updates.md"
        p.write_text(p.read_text().replace("coverage_start: YYYY-MM-DD", "coverage_start: 2026-03-01", 1))
        findings = self.assertOnly("placeholder")
        # the dated note itself, and the seed's log heading, since the vault now carries real dates
        self.assertEqual({f["file"] for f in findings}, {"notes-updates.md", "log.md"})
        self.assertEqual([f["file"] for f in findings].count("log.md"), 1)

    def test_seeded_log_heading_flags_once_the_vault_carries_a_real_date(self) -> None:
        self.assertClean()  # a fresh seed has no real date anywhere
        with (self.v / "notes-learnings.md").open("a") as f:
            f.write("\n## 2026-03-01 - first sweep\n\n### A fact\n\ntext\n")
        findings = lint(self.v)[1]
        self.assertIn(("placeholder", "log.md"), {(f["check"], f["file"]) for f in findings})
        log = self.v / "log.md"
        log.write_text(log.read_text().replace("## YYYY-MM-DD", "## 2026-02-28", 1))
        self.assertNotIn("log.md", {f["file"] for f in lint(self.v)[1]})

    @unittest.skipIf(getattr(os, "geteuid", lambda: 1)() == 0, "root can read an unreadable file")
    def test_unreadable_file_fails_rather_than_passing_silently(self) -> None:
        p = self.v / "notes-updates.md"
        p.chmod(0)
        try:
            code, findings = lint(self.v)
        finally:
            p.chmod(0o644)
        self.assertEqual(code, 1)
        self.assertIn("unreadable", checks(findings))


if __name__ == "__main__":
    unittest.main()
