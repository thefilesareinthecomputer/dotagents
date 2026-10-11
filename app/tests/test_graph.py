"""Subgraph endpoint tests. STORY-000026/000027 + R34 scoped views (M3).

A tiny deterministic vault per test: a two-note canon cluster and a project
note citing into it, so BFS, caps, encoding, scope, and boundary edges are
all observable without depending on the seed vault's content.
"""

import urllib.parse

import pytest
from asgi_client import TestClient

from agents_app import graph
from agents_app.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    kb_dir = tmp_path / "KNOWLEDGE-BASE"
    proj = tmp_path / "PROJECTS" / "P1"
    kb_dir.mkdir()
    proj.mkdir(parents=True)
    # The engine folds subsections under WORD_FLOOR (25 words) into their
    # parent, so the child section needs a real paragraph to exist.
    detail = " ".join(["word"] * 30)
    (kb_dir / "CANON.md").write_text(
        f"# Canon\n\nLinks [[CANON-TWO]].\n\n## Detail\n\n{detail}\n")
    (kb_dir / "CANON-TWO.md").write_text("# Canon Two\n\nBody.\n")
    (proj / "PROJ-NOTE.md").write_text("# Proj\n\nUses [[CANON]].\n")
    monkeypatch.setenv("AGENTS_APP_VAULT", str(tmp_path))
    return TestClient(create_app())


def _get(client, **params):
    r = client.get("/kb/graph/subgraph", params=params)
    assert r.status_code == 200
    return r.json()


def _files(body):
    return {n["data"]["file"] for n in body["elements"]["nodes"]}


# --- seeded BFS (STORY-000026) ---

def test_seeded_bfs_reaches_linked_notes(client):
    body = _get(client, file="PROJECTS/P1/PROJ-NOTE.md", depth=2)
    files = _files(body)
    assert {"PROJECTS/P1/PROJ-NOTE.md", "KNOWLEDGE-BASE/CANON.md",
            "KNOWLEDGE-BASE/CANON-TWO.md"} <= files
    assert body["meta"]["capped"] is False
    assert body["meta"]["stats"]["nodes"] == len(body["elements"]["nodes"])


def test_tiers_come_from_first_path_segment(client):
    body = _get(client, file="PROJECTS/P1/PROJ-NOTE.md", depth=1)
    tiers = {n["data"]["file"]: n["data"]["tier"]
             for n in body["elements"]["nodes"]}
    assert tiers["PROJECTS/P1/PROJ-NOTE.md"] == "PROJECTS"
    assert tiers["KNOWLEDGE-BASE/CANON.md"] == "KNOWLEDGE-BASE"


def test_depth_zero_returns_only_seeds(client):
    body = _get(client, file="KNOWLEDGE-BASE/CANON.md", depth=0)
    assert _files(body) == {"KNOWLEDGE-BASE/CANON.md"}
    assert body["elements"]["edges"] == []


def test_caps_set_capped_honestly(client):
    body = _get(client, file="PROJECTS/P1/PROJ-NOTE.md", depth=2, max_nodes=1)
    assert body["meta"]["capped"] is True
    assert len(body["elements"]["nodes"]) <= 1


def test_unknown_file_returns_empty_elements(client):
    body = _get(client, file="KNOWLEDGE-BASE/NOPE.md", depth=2)
    assert body["elements"] == {"nodes": [], "edges": []}


# --- id encoding (STORY-000027) ---

def test_node_ids_encode_section_ids(client):
    body = _get(client, file="KNOWLEDGE-BASE/CANON-TWO.md", depth=0)
    node = body["elements"]["nodes"][0]["data"]
    assert node["id"].startswith("node:")
    encoded = node["id"][5:]
    assert "#" not in encoded and " " not in encoded
    assert urllib.parse.unquote(encoded) == "KNOWLEDGE-BASE/CANON-TWO#Canon Two"
    assert node["file"] == "KNOWLEDGE-BASE/CANON-TWO.md"  # plain, not encoded


def test_heading_with_space_resolves_url_encoded(client):
    body = _get(client, file="KNOWLEDGE-BASE/CANON-TWO.md",
                heading="Canon Two", depth=0)
    assert len(body["elements"]["nodes"]) == 1


def test_heading_narrows_to_one_section(client):
    body = _get(client, file="KNOWLEDGE-BASE/CANON.md", heading="Detail",
                depth=0)
    headings = {n["data"]["heading"] for n in body["elements"]["nodes"]}
    assert headings == {"Detail"}


def test_tier_for_root_files():
    assert graph.tier_for_path("README.md") == "root"
    assert graph.tier_for_path("LEARNING/x.md") == "LEARNING"


# --- scoped views (R34) ---

def test_scope_keeps_boundary_edge_but_does_not_expand(client):
    body = _get(client, file="PROJECTS/P1/PROJ-NOTE.md", depth=2,
                scope="PROJECTS/P1")
    files = _files(body)
    assert "KNOWLEDGE-BASE/CANON.md" in files       # boundary node rendered
    assert "KNOWLEDGE-BASE/CANON-TWO.md" not in files  # never expanded
    boundary = [e["data"] for e in body["elements"]["edges"]
                if e["data"].get("boundary")]
    assert len(boundary) == 1


def test_scope_overview_returns_the_folder_graph(client):
    body = _get(client, scope="KNOWLEDGE-BASE")
    files = _files(body)
    assert {"KNOWLEDGE-BASE/CANON.md", "KNOWLEDGE-BASE/CANON-TWO.md"} <= files
    in_scope_edges = [e["data"] for e in body["elements"]["edges"]
                      if not e["data"].get("boundary")]
    assert in_scope_edges, "canon-internal edge expected"
    inbound = [e["data"] for e in body["elements"]["edges"]
               if e["data"].get("boundary")]
    assert inbound, "project's citation into canon should appear flagged"
    assert "PROJECTS/P1/PROJ-NOTE.md" in files


def test_whole_vault_overview_with_no_scope(client):
    body = _get(client)
    assert len(_files(body)) >= 3
    assert body["meta"]["root"] == "vault"
