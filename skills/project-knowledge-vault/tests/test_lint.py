"""Linter: a fresh seed is clean, and every gate fires against a mutation that violates it."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
SCAFFOLD = SKILL / "scripts" / "vault_scaffold.py"
LINT = SKILL / "scripts" / "vault_lint.py"


def seed(tmp_path: Path) -> Path:
    subprocess.run([sys.executable, str(SCAFFOLD), "--target", str(tmp_path), "--name", "T"], check=True, capture_output=True)
    return tmp_path / "PROJECTS" / "T"


def lint(vault: Path) -> tuple[int, list[dict]]:
    r = subprocess.run([sys.executable, str(LINT), str(vault), "--json"], capture_output=True, text=True)
    return r.returncode, json.loads(r.stdout)


def checks(findings: list[dict]) -> set[str]:
    return {f["check"] for f in findings}


def test_fresh_seed_is_clean(tmp_path: Path) -> None:
    code, findings = lint(seed(tmp_path))
    assert code == 0 and findings == []


def test_flat_fires_on_a_subdirectory_but_not_tooling(tmp_path: Path) -> None:
    v = seed(tmp_path)
    (v / "vault-kg").mkdir()
    (v / ".obsidian").mkdir()
    assert lint(v)[0] == 0
    (v / "raw").mkdir()
    code, findings = lint(v)
    assert code == 1 and checks(findings) == {"flat"}


def test_frontmatter_fires_on_a_note_without_type(tmp_path: Path) -> None:
    v = seed(tmp_path)
    (v / "notes-updates.md").write_text("# UPDATES\n\nno frontmatter\n")
    code, findings = lint(v)
    assert code == 1 and "frontmatter" in checks(findings)


def test_family_fires_on_a_wrong_type_value(tmp_path: Path) -> None:
    v = seed(tmp_path)
    p = v / "notes-chat.md"
    p.write_text(p.read_text().replace("type: chat_log", "type: note", 1))
    code, findings = lint(v)
    assert code == 1 and checks(findings) == {"family"}


def test_family_fires_on_an_unknown_prefix(tmp_path: Path) -> None:
    v = seed(tmp_path)
    (v / "scratch-ideas.md").write_text("---\ntype: note\n---\n# Ideas\n")
    code, findings = lint(v)
    assert code == 1 and checks(findings) == {"family"}


def test_reserved_fires_on_missing_log_and_frontmatter_on_index(tmp_path: Path) -> None:
    v = seed(tmp_path)
    (v / "log.md").unlink()
    p = v / "index.md"
    p.write_text(p.read_text().replace('okf_version: "0.2"', 'okf_version: "0.2"\ntitle: Front door', 1))
    code, findings = lint(v)
    assert code == 1 and checks(findings) == {"reserved"}
    assert len(findings) == 2


def test_filename_fires_on_uppercase_or_underscore(tmp_path: Path) -> None:
    v = seed(tmp_path)
    (v / "notes_Scratch.md").write_text("---\ntype: note\n---\n# x\n")
    code, findings = lint(v)
    assert code == 1 and "filename" in checks(findings)


def test_wikilink_fires_on_a_dangling_target(tmp_path: Path) -> None:
    v = seed(tmp_path)
    with (v / "notes-updates.md").open("a") as f:
        f.write("\nSee [[notes-nowhere]] for detail.\n")
    code, findings = lint(v)
    assert code == 1 and checks(findings) == {"wikilink"}


def test_wikilink_ignores_code_spans_fences_and_comments(tmp_path: Path) -> None:
    v = seed(tmp_path)
    with (v / "notes-updates.md").open("a") as f:
        f.write("\nA future note is `[[notes-later]]` until it lands.\n\n```\n[[notes-fenced]]\n```\n\n<!-- [[notes-commented]] -->\n")
    assert lint(v)[0] == 0


def test_anchor_fires_on_a_missing_heading(tmp_path: Path) -> None:
    v = seed(tmp_path)
    with (v / "notes-updates.md").open("a") as f:
        f.write("\nDecided in [[notes-meetings#YYYY-MM-DD-KICKOFF-INTERNAL]].\n")
    code, findings = lint(v)
    assert code == 1 and checks(findings) == {"anchor"}


def test_dated_fires_on_an_undated_notes_h2_but_not_the_register(tmp_path: Path) -> None:
    v = seed(tmp_path)
    assert lint(v)[0] == 0  # notes-questions has ## OPEN and ## ANSWERED and is exempt
    with (v / "notes-meetings.md").open("a") as f:
        f.write("\n## PREP: YYYY-MM-DD-REVIEW\n\ntalking points\n\n## Related\n\n- [[00-brd]] - the why\n")
    assert lint(v)[0] == 0  # the two allowed undated H2s
    with (v / "notes-chat.md").open("a") as f:
        f.write("\n## Kickoff thread\n\ntext\n")
    code, findings = lint(v)
    assert code == 1 and checks(findings) == {"dated"}


def test_dated_fires_on_log_out_of_order(tmp_path: Path) -> None:
    v = seed(tmp_path)
    (v / "log.md").write_text("# Change log\n\n## 2026-01-01\n\n- a\n\n## 2026-02-01\n\n- b\n")
    code, findings = lint(v)
    assert code == 1 and checks(findings) == {"dated"}


def test_board_fires_when_user_stories_restates_the_grammar(tmp_path: Path) -> None:
    v = seed(tmp_path)
    with (v / "user-stories.md").open("a") as f:
        f.write("\nEach item declares `- Parent: FEATURE-{id}` under its title.\n")
    code, findings = lint(v)
    assert code == 1 and checks(findings) == {"board"}


def test_placeholder_fires_only_beside_real_dates(tmp_path: Path) -> None:
    v = seed(tmp_path)
    p = v / "notes-updates.md"
    p.write_text(p.read_text().replace("date-created: YYYY-MM-DD", "date-created: 2026-03-01", 1))
    code, findings = lint(v)
    assert code == 1 and checks(findings) == {"placeholder"}
    assert all(f["file"] == "notes-updates.md" for f in findings)


@pytest.mark.skipif(getattr(os, "geteuid", lambda: 1)() == 0, reason="root can read an unreadable file")
def test_unreadable_file_fails_rather_than_passing_silently(tmp_path: Path) -> None:
    v = seed(tmp_path)
    p = v / "notes-updates.md"
    p.chmod(0)
    try:
        code, findings = lint(v)
    finally:
        p.chmod(0o644)
    assert code == 1 and "unreadable" in checks(findings)
