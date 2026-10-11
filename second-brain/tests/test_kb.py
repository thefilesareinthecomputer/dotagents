import pytest
from asgi_client import TestClient

from second_brain.app import create_app

client = TestClient(create_app())


# --- tree (STORY-000014) ---

def test_tree_shape_and_tiers():
    tree = client.get("/kb/tree").json()
    assert set(tree) == {"name", "path", "dirs", "files"}
    top = {d["name"] for d in tree["dirs"]}
    assert {"KNOWLEDGE-BASE", "_RESEARCH", "LEARNING", "PROJECTS",
            "_TEMPLATES", "_NOTEBOOKLM", "_USER", "__archive"} <= top


def test_tree_excludes_vault_kg():
    body = client.get("/kb/tree").text
    assert "vault-kg" not in body


def test_tree_nests(tmp_path, monkeypatch):
    deep = tmp_path / "PROJECTS" / "sub" / "deeper"
    deep.mkdir(parents=True)
    (deep / "note.md").write_text("# hi\n")
    monkeypatch.setenv("SECOND_BRAIN_VAULT", str(tmp_path))
    tree = TestClient(create_app()).get("/kb/tree").json()
    projects = next(d for d in tree["dirs"] if d["name"] == "PROJECTS")
    sub = next(d for d in projects["dirs"] if d["name"] == "sub")
    deeper = next(d for d in sub["dirs"] if d["name"] == "deeper")
    assert deeper["files"][0]["path"] == "PROJECTS/sub/deeper/note.md"


# --- file / stats / reindex (STORY-000015) ---

def test_file_returns_raw_markdown():
    r = client.get("/kb/file/KNOWLEDGE-BASE/SECOND-BRAIN-KNOWLEDGE-LIFECYCLE.md")
    assert r.status_code == 200
    assert r.text.startswith("---\n")


@pytest.mark.parametrize("path", ["../../../etc/passwd", "a/../../secret", "/etc/passwd"])
def test_file_guard_blocks_traversal(path):
    assert client.get(f"/kb/file/{path}").status_code in (403, 404)


def test_file_missing_is_404():
    assert client.get("/kb/file/KNOWLEDGE-BASE/nope.md").status_code == 404


STATS_KEYS = {"files", "sections", "edges", "unresolved", "tags",
              "missing_from_graph"}


def test_stats_shape():
    stats = client.get("/kb/stats").json()
    assert set(stats) == STATS_KEYS
    assert stats["files"] > 0


def test_reindex_returns_stats_shape():
    r = client.post("/kb/reindex")
    assert r.status_code == 200
    assert set(r.json()) == STATS_KEYS


# --- graph parity (git is a publishing boundary, not a knowledge one) ---
#
# The engine enumerates by filesystem walk (fixed at source 2026-09-07;
# it used to ask git and silently dropped gitignored and nested-repo
# notes). parity() stays as the standing invariant check: any note on
# disk the enumeration misses is reported, so a regression is loud.

def _git(vault, *argv):
    import subprocess
    subprocess.run(["git", "-C", str(vault), "-c", "user.email=t@t",
                    "-c", "user.name=t", *argv],
                   check=True, capture_output=True)


def test_parity_clean_vault_reports_nothing(tmp_path):
    from second_brain import kb
    (tmp_path / "KNOWLEDGE-BASE").mkdir()
    (tmp_path / "KNOWLEDGE-BASE" / "note.md").write_text("# hi\n")
    assert kb.parity(tmp_path) == []


def test_gitignored_and_nested_repo_notes_are_enumerated(tmp_path):
    from second_brain import kb
    (tmp_path / "tracked.md").write_text("# tracked\n")
    (tmp_path / "private.md").write_text("# private\n")
    (tmp_path / ".gitignore").write_text("private.md\n")
    _git(tmp_path, "init")
    _git(tmp_path, "add", "tracked.md", ".gitignore")
    _git(tmp_path, "commit", "-m", "seed")
    nested = tmp_path / "PROJECTS" / "ref-repo"
    nested.mkdir(parents=True)
    (nested / "readme.md").write_text("# nested\n")
    _git(nested, "init")
    seen = {p.relative_to(tmp_path).as_posix()
            for p in kb.engine.walk_vault(tmp_path)}
    assert {"tracked.md", "private.md", "PROJECTS/ref-repo/readme.md"} <= seen
    assert kb.parity(tmp_path) == []


# --- search (STORY-000016 + R24 filename scope) ---

def test_search_content_hit_shape():
    hits = client.get("/kb/search", params={"q": "certification"}).json()
    assert hits
    hit = hits[0]
    assert set(hit) == {"path", "heading", "section_id", "snippet", "score", "rung"}
    assert hit["score"] > 0
    assert hit["rung"]


def test_search_no_match_is_empty_200():
    r = client.get("/kb/search", params={"q": "zzzznomatchxyzzy"})
    assert r.status_code == 200
    assert r.json() == []


def test_search_requires_q():
    assert client.get("/kb/search").status_code == 422


def test_search_bad_scope_is_422():
    assert client.get("/kb/search", params={"q": "x", "scope": "nope"}).status_code == 422


def test_search_filename_scope():
    hits = client.get("/kb/search",
                      params={"q": "knowledge lifecycle", "scope": "filename"}).json()
    assert hits
    assert hits[0]["path"] == "KNOWLEDGE-BASE/SECOND-BRAIN-KNOWLEDGE-LIFECYCLE.md"
    assert hits[0]["heading"] is None and hits[0]["rung"] is None
    assert hits[0]["snippet"] == hits[0]["path"]


def test_search_filename_requires_all_keywords():
    hits = client.get("/kb/search",
                      params={"q": "lifecycle zzznope", "scope": "filename"}).json()
    assert hits == []


def test_search_filename_basename_ranks_first(tmp_path, monkeypatch):
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alpha" / "other.md").write_text("x\n")
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "alpha.md").write_text("x\n")
    monkeypatch.setenv("SECOND_BRAIN_VAULT", str(tmp_path))
    hits = TestClient(create_app()).get(
        "/kb/search", params={"q": "alpha", "scope": "filename"}).json()
    assert [h["path"] for h in hits] == ["notes/alpha.md", "alpha/other.md"]
