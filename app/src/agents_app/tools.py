"""The four KB tools for the Ollama lane. STORY-000036 (M4).

The Claude Code lane does NOT use these - a harness session brings its own
tools, and chat.py maps its vault-touching tool calls to kb_file events.
These schemas serve lanes that need native tool use (Ollama, and
eventually the stubbed OpenAI-compatible lane); ollama.tool_schemas()
converts them to Ollama's function-calling shape.

CONTRACT (do not rename): the file argument on read_file and graph_neighbors
is `filename` - kb-graph-hud.js's extractRoot() reads tool args by that exact
name to light graph nodes. `search_kb(query)`, `list_folder(folder)`.

Implementations delegate to kb.py (search/file_text/tree) and graph.py
(seed_sections/subgraph). execute() returns {result, info, kb_files}:
kb_files is the [{path, score}] list the lane emits as kb_file events -
read_file yields its file, search_kb its hits (spec: kb_file is "emitted
from read_file/search results; seeds the graph").

A filename outside vault/ raises (kb.file_text's lexical guard); the lane
converts the raise into an is_error tool_result rather than reading it.
"""

import re

from agents_app import graph, kb

_GRAPH_MAX_NODES = 40
_GRAPH_MAX_EDGES = 80

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "search_kb",
        "description": "Ranked full-text search over the vault. Returns "
                       "section hits with path, heading, snippet, and score.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search terms."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a vault file by its vault-relative path; an "
                       "optional heading returns only that section.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string",
                             "description": "Vault-relative file path."},
                "heading": {"type": "string",
                            "description": "Optional heading; returns only "
                                           "that section."},
            },
            "required": ["filename"],
        },
    },
    {
        "name": "graph_neighbors",
        "description": "Knowledge-graph neighborhood of a vault file "
                       "(optionally one section): nodes and typed edges.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string",
                             "description": "Vault-relative file path."},
                "heading": {"type": "string",
                            "description": "Optional heading to seed from."},
                "depth": {"type": "integer",
                          "description": "BFS depth, default 1."},
            },
            "required": ["filename"],
        },
    },
    {
        "name": "list_folder",
        "description": "Direct entries (subfolders and files) of a vault "
                       "folder; an empty folder means the vault root.",
        "input_schema": {
            "type": "object",
            "properties": {
                "folder": {"type": "string",
                           "description": "Vault-relative folder path; "
                                          "'' for the root."},
            },
            "required": ["folder"],
        },
    },
]


def execute(name: str, args: dict) -> dict:
    """Run one tool call; returns {result, info, kb_files}."""
    if name == "search_kb":
        return _search_kb(args["query"])
    if name == "read_file":
        return _read_file(args["filename"], args.get("heading", ""))
    if name == "graph_neighbors":
        return _graph_neighbors(args["filename"], args.get("heading", ""),
                                int(args.get("depth") or 1))
    if name == "list_folder":
        return _list_folder(args.get("folder", ""))
    raise ValueError(f"unknown tool: {name}")


def _search_kb(query: str) -> dict:
    hits = kb.search(query)
    return {
        "result": hits,
        "info": {"hits": len(hits)},
        "kb_files": [{"path": h["path"], "score": h["score"]} for h in hits],
    }


def _read_file(filename: str, heading: str) -> dict:
    text = kb.file_text(filename)
    if heading:
        text = _section(text, heading)
    return {
        "result": text,
        "info": {"chars": len(text)},
        "kb_files": [{"path": filename, "score": 1.0}],
    }


def _section(text: str, heading: str) -> str:
    """The heading's section: from its line to the next heading at the same
    or a higher level. Falls back to the whole file when absent."""
    want = heading.strip().lstrip("#").strip().lower()
    out: list[str] = []
    level = None
    for line in text.splitlines(keepends=True):
        m = re.match(r"(#{1,6})\s+(.*)", line)
        if m:
            if level is not None and len(m.group(1)) <= level:
                break
            if level is None and want in m.group(2).strip().lower():
                level = len(m.group(1))
        if level is not None:
            out.append(line)
    return "".join(out) if out else text


def _graph_neighbors(filename: str, heading: str, depth: int) -> dict:
    if ".." in filename or filename.startswith("/") or "\\" in filename:
        raise PermissionError(filename)
    con = kb.fresh_connection()
    try:
        seeds = graph.seed_sections(con, filename, heading or None)
        sub = graph.subgraph(con, seeds, depth,
                             _GRAPH_MAX_NODES, _GRAPH_MAX_EDGES)
    finally:
        con.close()
    return {
        "result": sub,
        "info": sub["meta"]["stats"],
        "kb_files": [],
    }


def _list_folder(folder: str) -> dict:
    node = kb.tree()
    for part in [p for p in folder.strip("/").split("/") if p]:
        match = next((d for d in node["dirs"] if d["name"] == part), None)
        if match is None:
            raise FileNotFoundError(folder)
        node = match
    entries = {
        "dirs": [d["name"] for d in node["dirs"]],
        "files": [f["name"] for f in node["files"]],
    }
    return {
        "result": entries,
        "info": {"entries": len(entries["dirs"]) + len(entries["files"])},
        "kb_files": [],
    }
