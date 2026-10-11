"""Bounded BFS subgraph over the engine's edges table. STORY-000026/000027 (M3).

Contract (spec, HTTP API table):
  GET /kb/graph/subgraph?file=&heading=&depth=&max_nodes=&max_edges=&scope=
  -> {meta: {root, depth, capped, stats},
      elements: {nodes: [{data: {id, label, file, heading, tier, node_type}}],
                 edges: [{data: {id, source, target, type, weight}}]}}

Load-bearing details the HUD depends on:
  - node id = "node:" + urlencode(section_id); section ids contain '#' and
    spaces, so encode consistently here and in query params (spec risk 2).
  - data.file stays a PLAIN vault-relative path - kb-graph-hud.js matches on
    it to light nodes; encoding it breaks the HUD silently.
  - tier = first path segment of the note's vault-relative path
    (KNOWLEDGE-BASE gold, _RESEARCH grey, LEARNING violet, PROJECTS teal).
  - meta.capped tells the caller truncation happened rather than hiding it.

Scoped views (R34): scope= restricts the walk to a vault-subtree prefix.
Edges crossing the boundary are kept and flagged data.boundary: true; the
out-of-scope endpoint appears as a node but is never expanded. With no seed,
overview() returns the whole scope (caps honored) - the per-folder graph.

Nodes are sections. An outbound link connects the section it was written in
to the target note's entry (first) section; backlinks attach to the entry
section only, so in-degree never fans out across a whole note.
"""

import sqlite3
import urllib.parse


def tier_for_path(path: str) -> str:
    """First path segment = tier; files at the vault root get 'root'."""
    return path.split("/", 1)[0] if "/" in path else "root"


def _in_scope(note_id: str, scope: str) -> bool:
    return not scope or note_id == scope or note_id.startswith(scope + "/")


def _note_id(con: sqlite3.Connection, file: str) -> str | None:
    file = file.strip("/")
    stem = file[:-3] if file.endswith(".md") else file
    row = con.execute("SELECT id FROM notes WHERE id = ? OR path = ?",
                      (stem, file)).fetchone()
    return row[0] if row else None


def _entry_section(con: sqlite3.Connection, note_id: str) -> str:
    row = con.execute("SELECT id FROM sections WHERE note_id = ? "
                      "ORDER BY ord LIMIT 1", (note_id,)).fetchone()
    # A note with no headings still needs an addressable node.
    return row[0] if row else note_id + "#"


def seed_sections(con: sqlite3.Connection, file: str,
                  heading: str | None) -> list[str]:
    """Resolve file (+ optional heading) to section ids to BFS from.

    No heading: every section of the note. With heading: match on the
    heading_path leaf the way the HUD's normH does (substring tolerant).
    """
    note = _note_id(con, file)
    if note is None:
        return []
    rows = con.execute("SELECT id, heading_path FROM sections WHERE note_id = ? "
                       "ORDER BY ord", (note,)).fetchall()
    if heading:
        want = heading.strip().lower()
        return [sid for sid, hp in rows
                if want in hp.split(" > ")[-1].lower()]
    return [sid for sid, _ in rows] or [note + "#"]


class _Build:
    """Accumulates nodes/edges under caps; capped flips instead of raising."""

    def __init__(self, con: sqlite3.Connection, max_nodes: int, max_edges: int):
        self.con = con
        self.max_nodes, self.max_edges = max_nodes, max_edges
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.edge_ids: set[str] = set()
        self.capped = False

    def add_node(self, section_id: str) -> bool:
        if section_id in self.nodes:
            return True
        if len(self.nodes) >= self.max_nodes:
            self.capped = True
            return False
        note = section_id.split("#", 1)[0]
        row = self.con.execute(
            "SELECT s.heading, n.path FROM sections s JOIN notes n "
            "ON n.id = s.note_id WHERE s.id = ?", (section_id,)).fetchone()
        heading, path = row if row else ("", note + ".md")
        self.nodes[section_id] = {
            "id": "node:" + urllib.parse.quote(section_id, safe=""),
            "label": heading or path.rsplit("/", 1)[-1],
            "file": path,
            "heading": heading,
            "tier": tier_for_path(path),
            "node_type": "section",
        }
        return True

    def add_edge(self, src: str, dst: str, kind: str, boundary: bool) -> None:
        edge_id = f"{src}->{dst}"
        if edge_id in self.edge_ids:
            return
        if len(self.edges) >= self.max_edges:
            self.capped = True
            return
        if not (self.add_node(src) and self.add_node(dst)):
            return
        self.edge_ids.add(edge_id)
        data = {
            "id": "edge:" + urllib.parse.quote(edge_id, safe=""),
            "source": self.nodes[src]["id"],
            "target": self.nodes[dst]["id"],
            "type": kind,
            "weight": 1,
        }
        if boundary:
            data["boundary"] = True
        self.edges.append(data)

    def shape(self, root: str, depth: int) -> dict:
        return {
            "meta": {"root": root, "depth": depth, "capped": self.capped,
                     "stats": {"nodes": len(self.nodes),
                               "edges": len(self.edges)}},
            "elements": {"nodes": [{"data": d} for d in self.nodes.values()],
                         "edges": [{"data": d} for d in self.edges]},
        }


def subgraph(con: sqlite3.Connection, seed_ids: list[str], depth: int,
             max_nodes: int, max_edges: int, scope: str = "") -> dict:
    """Bounded BFS over the edges table from seed sections.

    Returns the Cytoscape-shaped dict the HUD consumes; `capped` in meta
    tells the caller truncation happened rather than hiding it.
    """
    scope = (scope or "").strip("/")
    build = _Build(con, max_nodes, max_edges)
    frontier: list[str] = []
    for sid in seed_ids:
        if build.add_node(sid):
            frontier.append(sid)

    for _ in range(max(depth, 0)):
        next_frontier: list[str] = []
        for sid in frontier:
            note = sid.split("#", 1)[0]
            if not _in_scope(note, scope):
                continue  # boundary nodes render but never expand
            for dst, kind in con.execute(
                    "SELECT dst, kind FROM edges WHERE section_id = ? "
                    "AND status = 'resolved'", (sid,)):
                target = _entry_section(con, dst)
                fresh = target not in build.nodes
                build.add_edge(sid, target, kind, not _in_scope(dst, scope))
                if fresh and target in build.nodes:
                    next_frontier.append(target)
            if sid == _entry_section(con, note):
                for src_section, kind, src in con.execute(
                        "SELECT section_id, kind, src FROM edges "
                        "WHERE dst = ? AND status = 'resolved'", (note,)):
                    fresh = src_section not in build.nodes
                    build.add_edge(src_section, sid, kind,
                                   not _in_scope(src, scope))
                    if fresh and src_section in build.nodes:
                        next_frontier.append(src_section)
        frontier = next_frontier

    return build.shape(seed_ids[0] if seed_ids else scope, depth)


def overview(con: sqlite3.Connection, scope: str,
             max_nodes: int, max_edges: int) -> dict:
    """The whole scope as a graph (R34): every section in the subtree up to
    the caps, edges among them, and boundary edges kept but flagged."""
    scope = (scope or "").strip("/")
    build = _Build(con, max_nodes, max_edges)
    like = (scope + "/%") if scope else "%"
    for (sid,) in con.execute(
            "SELECT id FROM sections WHERE note_id = ? OR note_id LIKE ? "
            "ORDER BY note_id, ord", (scope, like)):
        build.add_node(sid)
    for sid in list(build.nodes):
        note = sid.split("#", 1)[0]
        if not _in_scope(note, scope):
            continue
        for dst, kind in con.execute(
                "SELECT dst, kind FROM edges WHERE section_id = ? "
                "AND status = 'resolved'", (sid,)):
            build.add_edge(sid, _entry_section(con, dst), kind,
                           not _in_scope(dst, scope))
    if scope:  # inbound boundary edges: who outside the scope cites it
        notes = {sid.split("#", 1)[0] for sid in build.nodes}
        for note in sorted(notes):
            if not _in_scope(note, scope):
                continue
            for src_section, kind, src in con.execute(
                    "SELECT section_id, kind, src FROM edges "
                    "WHERE dst = ? AND status = 'resolved'", (note,)):
                if not _in_scope(src, scope):
                    build.add_edge(src_section, _entry_section(con, note),
                                   kind, True)
    return build.shape(scope or "vault", 0)
