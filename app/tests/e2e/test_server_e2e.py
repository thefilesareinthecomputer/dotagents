"""End-to-end suite against a REAL server process (no TestClient).

Boots `uvicorn agents_app.app:create_app --factory` in a subprocess on an
ephemeral port - the same invocation `agents up` uses - pointed at the repo
vault and a tmp data dir, then exercises the HTTP surface over real sockets:
KB reads, graph subgraph, conversation CRUD, and the POST /chat SSE contract.

Test level: server e2e. The group and permissions e2e files share
conftest.py's real-server fixture.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

import pytest


def get_json(base: str, path: str):
    with urllib.request.urlopen(base + path, timeout=10) as response:
        return json.loads(response.read())


def post_json(base: str, path: str, body: dict | None = None):
    request = urllib.request.Request(
        base + path, method="POST",
        data=json.dumps(body or {}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, response.read()


def test_ui_is_served(server):
    with urllib.request.urlopen(server + "/", timeout=10) as response:
        html = response.read().decode()
    assert 'src="/ui/kb-graph-hud.js' in html
    # Load order is contract: the HUD's fetch monkey-patch must land first.
    assert html.index('src="/ui/kb-graph-hud.js') < html.index('src="/ui/app.js')


def test_kb_surface_over_real_sockets(server):
    tree = get_json(server, "/kb/tree")
    assert {d["name"] for d in tree["dirs"]} >= {"KNOWLEDGE-BASE", "_RESEARCH"}

    stats = get_json(server, "/kb/stats")
    assert stats["files"] > 0 and stats["sections"] > 0

    hits = get_json(server, "/kb/search?q=certification")
    assert hits and hits[0]["score"] > 0 and hits[0]["rung"]

    with urllib.request.urlopen(
            server + "/kb/file/" + urllib.parse.quote(hits[0]["path"]),
            timeout=10) as response:
        assert response.read()


def test_kb_file_guard_over_real_sockets(server):
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(server + "/kb/file/..%2F..%2Fetc%2Fpasswd",
                               timeout=10)
    assert err.value.code in (403, 404)


def test_graph_subgraph_and_scoped_overview(server):
    overview = get_json(server, "/kb/graph/subgraph?max_nodes=60&max_edges=120")
    assert overview["elements"]["nodes"]

    scoped = get_json(server, "/kb/graph/subgraph?scope=KNOWLEDGE-BASE"
                              "&max_nodes=60&max_edges=120")
    boundary = [e for e in scoped["elements"]["edges"]
                if e["data"].get("boundary")]
    in_scope = [n for n in scoped["elements"]["nodes"]
                if n["data"]["file"].startswith("KNOWLEDGE-BASE/")]
    assert in_scope
    for edge in boundary:
        assert edge["data"]["source"] and edge["data"]["target"]


def test_conversation_crud_and_chat_sse_contract(server):
    status, body = post_json(server, "/conversations")
    assert status == 200
    cid = json.loads(body)["id"]

    listing = get_json(server, "/conversations")
    assert any(t["id"] == cid for t in listing)

    # No harness CLI on the stripped PATH and no Ollama daemon: the chat
    # contract still holds - a real SSE stream that ends error then done,
    # never a silent close or a hang.
    status, raw = post_json(server, "/chat",
                            {"message": "hi", "conversation_id": cid})
    assert status == 200
    text = raw.decode()
    events = [line[7:] for line in text.splitlines()
              if line.startswith("event: ")]
    assert events[-1] == "done"
    assert "error" in events

    request = urllib.request.Request(server + f"/conversations/{cid}",
                                     method="DELETE")
    with urllib.request.urlopen(request, timeout=10) as response:
        assert response.status in (200, 204)
