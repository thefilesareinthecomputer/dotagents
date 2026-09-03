"""Compatibility with the skills that read or write a project vault.

sprint-board owns user-stories.md; obsidian-kg reads the vault as a graph root. Each test
is the whole coupling to that skill: a divergence fails here rather than months later.
The okf-vault check runs only when OKF_VAULT_BUILD names a build output, because the
build lives in another repo.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
SKILLS = SKILL.parent
SCAFFOLD = SKILL / "scripts" / "vault_scaffold.py"
LINT = SKILL / "scripts" / "vault_lint.py"
BOARD_SCAFFOLD = SKILLS / "sprint-board" / "scripts" / "board_scaffold.py"
BOARD_LINT = SKILLS / "sprint-board" / "scripts" / "board_lint.py"
KG = SKILLS / "obsidian-kg" / "scripts" / "obsidian_kg.py"
PROFILES = SKILL / "templates" / "vault-kg-profiles.md"


def seed(tmp_path: Path) -> Path:
    subprocess.run([sys.executable, str(SCAFFOLD), "--target", str(tmp_path), "--name", "T"], check=True, capture_output=True)
    return tmp_path / "PROJECTS" / "T"


def run(*args: str | Path, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, cwd=cwd)


@pytest.mark.skipif(not BOARD_LINT.exists(), reason="sprint-board not installed beside this skill")
def test_sprint_board_scaffold_appended_to_the_seed_lints_clean(tmp_path: Path) -> None:
    v = seed(tmp_path)
    spine = tmp_path / "spine.json"
    spine.write_text(json.dumps({"epics": [{"title": "Ship the widget", "features": [
        {"title": "Assemble the widget", "stories": [{"title": "Cut the parts"}]}]}]}))
    board = run(BOARD_SCAFFOLD, spine)
    assert board.returncode == 0, board.stderr
    p = v / "user-stories.md"
    p.write_text(p.read_text() + "\n---\n\n" + board.stdout)
    # A fresh scaffold carries template bodies the author still has to write, which
    # board_lint reports as residue by design. The vault's responsibility is the
    # structure, so no structural finding may appear.
    result = run(BOARD_LINT, p, "--json")
    codes = {f["code"] for f in json.loads(result.stdout)["findings"]}
    structural = {"no-items", "heading-level", "bad-id-form", "missing-block", "bad-parent", "unknown-parent"}
    assert not (codes & structural), codes
    # the appended board must not trip the vault linter either
    assert run(LINT, v).returncode == 0


@pytest.mark.skipif(not KG.exists(), reason="obsidian-kg not installed beside this skill")
def test_obsidian_kg_ingest_resolves_edges_dates_and_supersession(tmp_path: Path) -> None:
    v = seed(tmp_path)
    (v / "notes-meetings.md").write_text(
        "---\ntype: meeting_note\ntitle: notes-meetings\ndate-created: 2026-01-01\n---\n\n# MEETING-NOTES\n\n"
        "## 2026-02-01-STANDUP-INTERNAL\n\nThe deploy target moved to the blue cluster after the outage review.\n\n"
        "### DECISIONS\n\n- 2026-02-01 - deploy target is the blue cluster - supersedes 2026-01-01 kickoff, capacity\n\n"
        "## 2026-01-01-KICKOFF-INTERNAL\n\nThe deploy target is the green cluster for the first release.\n\n"
        "**SUPERSEDED**: 2026-02-01 [[notes-meetings#2026-02-01-STANDUP-INTERNAL]]\n\n"
        "### DECISIONS\n\n- 2026-01-01 - deploy target is the green cluster - first release\n")
    (v / "notes-learnings.md").write_text(
        "---\ntype: note\ntitle: notes-learnings\ndate-created: 2026-02-01\n---\n\n# LEARNINGS\n\n## 2026-02-01\n\n"
        "### The deploy target is the blue cluster\n\nSettled at [[notes-meetings#2026-02-01-STANDUP-INTERNAL]] after the outage review.\n")
    (v / "notes-questions.md").write_text(
        "---\ntype: note\ntitle: notes-questions\n---\n\n# QUESTIONS\n\n## OPEN\n\n## ANSWERED\n")
    lint = run(LINT, v)
    assert lint.returncode == 0, lint.stdout

    ingest = run(KG, "ingest", v)
    assert ingest.returncode == 0, ingest.stderr
    m = re.search(r"edges: (\d+) resolved, (\d+) unresolved, (\d+) ambiguous", ingest.stdout)
    assert m and int(m.group(1)) > 0 and m.group(2) == "0" and m.group(3) == "0", ingest.stdout

    unresolved = run(KG, "links", v, "--unresolved")
    assert "no outbound links" in unresolved.stdout or unresolved.stdout.strip() == "", unresolved.stdout

    # the profile snippet is valid JSON and applies without an ingest error
    block = re.search(r"```json\n(.*?)```", PROFILES.read_text(), re.S)
    assert block
    config = json.loads(block.group(1))
    (v / "vault-kg" / "vault-kg-config.md").write_text("# vault-kg-config\n\n```json\n" + json.dumps(config, indent=2) + "\n```\n")
    ingest = run(KG, "ingest", v)
    assert ingest.returncode == 0, ingest.stderr + ingest.stdout

    sections = run(KG, "sections", v, "notes-meetings", "--json")
    assert sections.returncode == 0, sections.stderr
    rows = json.loads(sections.stdout)
    kickoff = next((r for r in rows if r["heading_path"].endswith("KICKOFF-INTERNAL")), None)
    standup = next((r for r in rows if r["heading_path"].endswith("STANDUP-INTERNAL")), None)
    assert kickoff and standup, sections.stdout
    assert kickoff["slot"] == "superseded", kickoff
    assert standup["doc_date"].startswith("2026-02-01"), standup

    search = run(KG, "search", v, "deploy target cluster", "--json")
    assert search.returncode == 0, search.stderr
    ids = [h["section_id"] for h in json.loads(search.stdout)["results"]]
    first_meeting = next((i for i in ids if i.startswith("notes-meetings#")), "")
    assert "STANDUP" in first_meeting, ids


@pytest.mark.skipif(not os.environ.get("OKF_VAULT_BUILD"), reason="OKF_VAULT_BUILD not set")
def test_okf_vault_build_conforms() -> None:
    build = Path(os.environ["OKF_VAULT_BUILD"])
    result = run(LINT, build)
    assert result.returncode == 0, result.stdout
