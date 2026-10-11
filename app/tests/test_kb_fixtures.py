"""Adapter suite over the upstream fixture vaults. STORY-000022 (M2 tail).

Fixtures live in tests/fixtures/ (copied verbatim from
~/.agents/skills/obsidian-kg/tests/ at upstream sha 4eef625):
  fixture-vault/     9 md files; nesting (plans/, projects/inner/), a
                     .trash/Ghost.md the engine must skip
  adversarial-vault/ 15 md files; own .kgignore (drafts/) and a
                     vault-kg/vault-kg-config.md with ignore/profile rules
  kb-fixture-vault/  6 md files; knowledge-base/ subdir; known content
                     terms: "irrigation", "drip", "sprinkler"

Method: copy the fixture to tmp_path per test (shutil.copytree) and point
AGENTS_APP_VAULT at the copy - ingest writes vault-kg/ into the vault, and
the repo copies stay pristine. Stats counts are pinned from a real ingest and
each pinned number is commented with what it counts.
"""

import shutil
from pathlib import Path

import pytest
from asgi_client import TestClient

from agents_app import kb
from agents_app.app import create_app

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def vault_client(tmp_path, monkeypatch):
    """copy_fixture(name) -> (client, vault_copy_path)."""
    def copy_fixture(name: str):
        dst = tmp_path / name
        shutil.copytree(FIXTURES / name, dst)
        monkeypatch.setenv("AGENTS_APP_VAULT", str(dst))
        return TestClient(create_app()), dst
    return copy_fixture


# --- tree nesting (fixture-vault) ---

def test_tree_matches_fixture_structure(vault_client):
    client, _ = vault_client("fixture-vault")
    tree = client.get("/kb/tree").json()
    assert {d["name"] for d in tree["dirs"]} == {"archive", "plans", "projects"}
    assert {f["name"] for f in tree["files"]} == {"Home.md", "Scratch.md",
                                                 "Seed List.md"}
    projects = next(d for d in tree["dirs"] if d["name"] == "projects")
    inner = next(d for d in projects["dirs"] if d["name"] == "inner")
    assert inner["files"][0]["path"] == "projects/inner/Deep Note.md"


def test_tree_excludes_trash(vault_client):
    client, _ = vault_client("fixture-vault")
    body = client.get("/kb/tree").text
    assert "Ghost.md" not in body and ".trash" not in body


# --- file path guard (fixture-vault) ---

@pytest.mark.parametrize("path", ["../../../etc/passwd", "plans/../../x",
                                  "/etc/passwd"])
def test_file_guard_on_fixture_vault(vault_client, path):
    client, _ = vault_client("fixture-vault")
    assert client.get(f"/kb/file/{path}").status_code in (403, 404)


def test_file_serves_nested_fixture_note(vault_client):
    client, _ = vault_client("fixture-vault")
    r = client.get("/kb/file/projects/inner/Deep Note.md")
    assert r.status_code == 200
    assert r.text.strip()


# --- search pass-through (kb-fixture-vault) ---

def test_search_irrigation_hit_shape(vault_client):
    client, _ = vault_client("kb-fixture-vault")
    hits = client.get("/kb/search", params={"q": "irrigation"}).json()
    assert hits
    hit = hits[0]
    assert set(hit) == {"path", "heading", "section_id", "snippet", "score",
                        "rung"}
    assert hit["path"] == "knowledge-base/runbooks-irrigation-schedule.md"


def test_search_score_and_rung_are_engine_passthrough(vault_client):
    client, vault = vault_client("kb-fixture-vault")
    hits = client.get("/kb/search", params={"q": "irrigation"}).json()
    direct = kb.engine.search(vault, "irrigation", limit=20)
    assert [h["score"] for h in hits] == [d["score"] for d in direct["results"]]
    assert {h["rung"] for h in hits} == {direct["rung"]}


# --- stats pinned per vault ---

def test_stats_fixture_vault(vault_client):
    client, _ = vault_client("fixture-vault")
    # 8 files = 9 md minus .trash/Ghost.md (trash is always skipped)
    assert client.get("/kb/stats").json() == {
        "files": 8, "sections": 8, "edges": 12, "unresolved": 1, "tags": 8,
        "missing_from_graph": []}


def test_stats_adversarial_vault(vault_client):
    client, _ = vault_client("adversarial-vault")
    # 11 files = 15 md minus drafts/scratch.md (.kgignore), archive/
    # superseded.md (config ignore archive/**), private.md (frontmatter
    # kg-ignore: true), and vault-kg/vault-kg-config.md (engine dir)
    assert client.get("/kb/stats").json() == {
        "files": 11, "sections": 31, "edges": 7, "unresolved": 1, "tags": 2,
        "missing_from_graph": []}


def test_adversarial_kgignore_excludes_drafts(vault_client):
    client, vault = vault_client("adversarial-vault")
    client.get("/kb/stats")  # forces the first ingest
    con = kb.engine.connect(vault, must_exist=True)
    try:
        paths = [r[0] for r in con.execute("SELECT path FROM notes")]
    finally:
        con.close()
    assert not any(p.startswith("drafts/") for p in paths)
    assert not any(p.startswith("archive/") for p in paths)
    assert "private.md" not in paths


def test_stats_kb_fixture_vault(vault_client):
    client, _ = vault_client("kb-fixture-vault")
    # 6 files = all 6 md (index, log, 4 knowledge-base notes); nothing ignored
    assert client.get("/kb/stats").json() == {
        "files": 6, "sections": 6, "edges": 11, "unresolved": 1, "tags": 14,
        "missing_from_graph": []}


# --- reindex ---

def test_reindex_fixture_vault_shape_and_idempotence(vault_client):
    client, _ = vault_client("fixture-vault")
    first = client.post("/kb/reindex").json()
    assert set(first) == {"files", "sections", "edges", "unresolved", "tags",
                          "missing_from_graph"}
    assert client.post("/kb/reindex").json() == first
