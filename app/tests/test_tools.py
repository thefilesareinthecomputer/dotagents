"""STORY-000036: the four KB tools and the filename arg contract."""

import pytest

from agents_app import tools

SCHEMAS = {schema["name"]: schema for schema in tools.TOOL_SCHEMAS}


# --- schemas ---

def test_four_tools_registered():
    assert set(SCHEMAS) == {"search_kb", "read_file", "graph_neighbors",
                            "list_folder"}


def test_file_taking_tools_declare_filename():
    for name in ("read_file", "graph_neighbors"):
        props = SCHEMAS[name]["input_schema"]["properties"]
        assert "filename" in props
        assert "filename" in SCHEMAS[name]["input_schema"]["required"]
        assert "path" not in props and "file" not in props


def test_search_and_folder_arg_names():
    assert "query" in SCHEMAS["search_kb"]["input_schema"]["properties"]
    assert "folder" in SCHEMAS["list_folder"]["input_schema"]["properties"]


def test_schemas_carry_name_description_input_schema():
    for schema in tools.TOOL_SCHEMAS:
        assert set(schema) == {"name", "description", "input_schema"}
        assert schema["input_schema"]["type"] == "object"


# --- execute ---

def test_read_file_returns_text_and_kb_file():
    out = tools.execute("read_file", {
        "filename": "KNOWLEDGE-BASE/VAULT-KNOWLEDGE-LIFECYCLE.md"})
    assert out["result"].startswith("---\n")
    assert out["kb_files"] == [{
        "path": "KNOWLEDGE-BASE/VAULT-KNOWLEDGE-LIFECYCLE.md",
        "score": 1.0}]


def test_read_file_heading_slices_section():
    filename = "KNOWLEDGE-BASE/VAULT-KNOWLEDGE-LIFECYCLE.md"
    whole = tools.execute("read_file", {"filename": filename})["result"]
    lines = [l for l in whole.splitlines() if l.startswith("## ")]
    assert len(lines) >= 2, "fixture note needs two h2s for this test"
    section = tools.execute("read_file", {
        "filename": filename, "heading": lines[0][3:]})["result"]
    assert section.startswith(lines[0])
    assert lines[1] not in section
    assert len(section) < len(whole)


@pytest.mark.parametrize("path", ["../../../etc/passwd", "a/../../x",
                                  "/etc/passwd"])
def test_read_file_rejects_traversal(path):
    with pytest.raises(PermissionError):
        tools.execute("read_file", {"filename": path})


@pytest.mark.parametrize("path", ["../../../etc/passwd", "/etc/passwd"])
def test_graph_neighbors_rejects_traversal(path):
    with pytest.raises(PermissionError):
        tools.execute("graph_neighbors", {"filename": path})


def test_search_kb_hits_and_kb_files():
    out = tools.execute("search_kb", {"query": "certification"})
    assert out["result"]
    assert out["info"]["hits"] == len(out["result"])
    assert out["kb_files"][0]["path"] == out["result"][0]["path"]
    assert out["kb_files"][0]["score"] == out["result"][0]["score"]


def test_graph_neighbors_returns_subgraph():
    out = tools.execute("graph_neighbors", {
        "filename": "KNOWLEDGE-BASE/VAULT-KNOWLEDGE-LIFECYCLE.md"})
    sub = out["result"]
    assert set(sub) == {"meta", "elements"}
    assert sub["elements"]["nodes"]
    assert out["info"] == sub["meta"]["stats"]


def test_list_folder_root_and_subfolder():
    root = tools.execute("list_folder", {"folder": ""})["result"]
    assert "KNOWLEDGE-BASE" in root["dirs"]
    kb_dir = tools.execute("list_folder", {"folder": "KNOWLEDGE-BASE"})["result"]
    assert "VAULT-KNOWLEDGE-LIFECYCLE.md" in kb_dir["files"]


def test_list_folder_missing_is_not_found():
    with pytest.raises(FileNotFoundError):
        tools.execute("list_folder", {"folder": "NOPE/NADA"})


def test_unknown_tool_raises():
    with pytest.raises(ValueError):
        tools.execute("frobnicate", {})
