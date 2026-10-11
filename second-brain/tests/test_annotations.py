"""Annotation feature coverage for the bundled engine. STORY-000023 (M2 tail).

The engine's annotations lane is newly added upstream and untested there;
this file is the coverage we owe back (send via agent-mail when green -
that delivery is part of the story's DoD, R11/R20).

Markers: one passing case each for NOTE, ANCHOR, SUPERSEDED, FOLLOW-UP,
CLARIFY, DERIVED-FROM, EVENT, authored as `**MARKER**: payload` lines in a
tmp vault and asserted as rows in the annotations table after ingest.
ANCHOR also biases search scoring (engine ANCHOR_BOOST) - the row's
existence is asserted here; scoring behavior belongs to upstream's suite.

Masking case (the upstream hardening this must cover): a marker line
inside Obsidian %% %% comment delimiters is masked by _comment_mask and
stored in NO row.

Uses kb.engine directly (engine.ingest on a tmp vault, then the
annotations table via engine.connect). No HTTP surface involved.
"""

import pytest

from second_brain import kb

engine = kb.engine


def ingest_note(tmp_path, text: str) -> list[tuple]:
    """Write one note, ingest, return annotations rows
    (marker, payload, target, date)."""
    (tmp_path / "note.md").write_text(text)
    engine.ingest(tmp_path)
    con = engine.connect(tmp_path, must_exist=True)
    try:
        return con.execute(
            "SELECT marker, payload, target, date FROM annotations"
            " ORDER BY line").fetchall()
    finally:
        con.close()


@pytest.mark.parametrize("marker", ["NOTE", "ANCHOR", "SUPERSEDED",
                                    "FOLLOW-UP", "CLARIFY", "DERIVED-FROM",
                                    "EVENT"])
def test_core_marker_lands_a_row(tmp_path, marker):
    rows = ingest_note(tmp_path,
                       f"# Title\n\nBody prose here.\n\n**{marker}**: payload text\n")
    assert rows == [(marker, "payload text", "", "")]


def test_derived_from_extracts_wikilink_target(tmp_path):
    rows = ingest_note(tmp_path,
                       "# Title\n\n**DERIVED-FROM**: see [[Source Note|src]]\n")
    assert rows == [("DERIVED-FROM", "see [[Source Note|src]]",
                     "Source Note", "")]


def test_event_extracts_leading_iso_date(tmp_path):
    rows = ingest_note(tmp_path,
                       "# Title\n\n**EVENT**: 2026-06-15 season review\n")
    assert rows == [("EVENT", "2026-06-15 season review", "", "2026-06-15")]


def test_percent_comment_masks_marker(tmp_path):
    rows = ingest_note(tmp_path,
                       "# Title\n\n%%\n**NOTE**: invisible in rendered view\n%%\n"
                       "\n**NOTE**: visible\n")
    assert rows == [("NOTE", "visible", "", "")]


def test_html_comment_masks_marker(tmp_path):
    rows = ingest_note(tmp_path,
                       "# Title\n\n<!--\n**NOTE**: hidden\n-->\n")
    assert rows == []


def test_unregistered_token_is_candidate_not_row(tmp_path):
    (tmp_path / "note.md").write_text("# Title\n\n**TYPO-MARK**: oops\n")
    engine.ingest(tmp_path)
    con = engine.connect(tmp_path, must_exist=True)
    try:
        assert con.execute("SELECT COUNT(*) FROM annotations").fetchone()[0] == 0
        cands = con.execute(
            "SELECT token, kind FROM annotation_candidates").fetchall()
    finally:
        con.close()
    assert ("TYPO-MARK", "unregistered") in cands
