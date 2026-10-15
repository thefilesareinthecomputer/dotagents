#!/usr/bin/env python3
"""File-type handling for the sanitize engine.

Each file type is parsed so the scrubber sees the text a reader would see: JSON is
parsed and every key and string value scrubbed, so a term behind a \\uXXXX escape is
found; CSV goes cell by cell; a Word document is a zip whose word/*.xml parts are
scrubbed text node by text node and rezipped with every other part byte-identical.
Plain text and code are scrubbed whole. PDFs and binaries are skipped and named in
the report. Stdlib only; nothing here prints text.
"""

from __future__ import annotations

import csv
import html
import io
import json
import re
import zipfile
from pathlib import PurePath
from typing import Callable

Scrub = Callable[[str, dict], str]
Field = Callable[[str, str, dict], str]   # (key, value, counts) -> value, for a value a parser split from its key

TEXT_EXT = {
    ".txt", ".md", ".markdown", ".rst", ".log", ".py", ".js", ".ts", ".tsx", ".jsx", ".sh", ".zsh",
    ".bash", ".rb", ".go", ".rs", ".java", ".kt", ".swift", ".c", ".h", ".cpp", ".hpp", ".cs", ".php",
    ".sql", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env", ".html", ".htm", ".css", ".scss",
    ".xml", ".svg", ".tex", ".org", ".adoc", ".mdx", ".vue", ".lua", ".pl", ".r", ".m", ".ps1", ".bat",
    ".gitignore", ".dockerfile", ".properties", ".graphql", ".proto",
}
JSON_EXT = {".json", ".ipynb", ".geojson"}
JSONL_EXT = {".jsonl", ".ndjson"}
CSV_EXT = {".csv", ".tsv"}
DOCX_EXT = {".docx"}
PDF_EXT = {".pdf"}
BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".tif", ".tiff", ".heic",
    ".mp3", ".mp4", ".mov", ".m4a", ".wav", ".avi", ".mkv", ".webm",
    ".zip", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".tar", ".rar", ".dmg", ".pkg",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".pyc", ".so", ".dylib", ".dll", ".exe", ".bin", ".o", ".a", ".class", ".jar",
    ".sqlite", ".db", ".parquet", ".feather", ".npy", ".npz", ".pt", ".gguf", ".safetensors",
    ".doc", ".xls", ".xlsx", ".ppt", ".pptx", ".pages", ".numbers", ".key",
}

SNIFF_BYTES = 8192


def classify(name: str, head: bytes) -> str:
    """One of text, json, jsonl, csv, docx, pdf, binary. Unknown extensions are sniffed:
    a NUL byte or undecodable UTF-8 in the first bytes means binary."""
    ext = PurePath(name).suffix.lower()
    if ext in TEXT_EXT:
        return "text"
    if ext in JSON_EXT:
        return "json"
    if ext in JSONL_EXT:
        return "jsonl"
    if ext in CSV_EXT:
        return "csv"
    if ext in DOCX_EXT:
        return "docx"
    if ext in PDF_EXT:
        return "pdf"
    if ext in BINARY_EXT:
        return "binary"
    return "text" if looks_like_text(head) else "binary"


def looks_like_text(head: bytes) -> bool:
    sample = head[:SNIFF_BYTES]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        # A multibyte character cut at the sample edge is not a binary file.
        try:
            sample[:-3].decode("utf-8")
        except UnicodeDecodeError:
            return False
    return True


def _decode(data: bytes) -> str | None:
    if b"\x00" in data[:SNIFF_BYTES]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


# ---------------------------------------------------------------- per type


def _text(data: bytes, scrub: Scrub, counts: dict) -> bytes | None:
    text = _decode(data)
    if text is None:
        return None
    return scrub(text, counts).encode("utf-8")


def _walk_json(value, scrub: Scrub, counts: dict, field: Field | None = None):
    if isinstance(value, str):
        return scrub(value, counts)
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            ck = scrub(k, counts) if isinstance(k, str) else k
            # a string value keeps its key's context, so a credential under a key-like name is judged as one
            out[ck] = field(k, v, counts) if field and isinstance(k, str) and isinstance(v, str) else _walk_json(v, scrub, counts, field)
        return out
    if isinstance(value, list):
        return [_walk_json(v, scrub, counts, field) for v in value]
    return value


class _DuplicateKey(Exception):
    pass


def _pairs_hook(pairs):
    keys = [k for k, _ in pairs]
    if len(set(keys)) != len(keys):
        raise _DuplicateKey()
    return dict(pairs)


def _json_text(text: str, scrub: Scrub, counts: dict, field: Field | None = None) -> str | None:
    """The document re-serialized with every key and string value scrubbed, or None when it
    is not JSON or holds a duplicate key. A parse keeps only the last of duplicate keys, so
    the earlier value would never be scanned and the original would pass a tree scan; such a
    file is counted (json_duplicate_key) and scrubbed as text, which sees every value."""
    try:
        value = json.loads(text, object_pairs_hook=_pairs_hook)
    except ValueError:
        return None
    except _DuplicateKey:
        counts["json_duplicate_key"] = counts.get("json_duplicate_key", 0) + 1
        return None
    indent = 2 if "\n" in text.strip() else None
    return json.dumps(_walk_json(value, scrub, counts, field), ensure_ascii=False, indent=indent)


def _json(data: bytes, scrub: Scrub, counts: dict, field: Field | None = None) -> bytes | None:
    text = _decode(data)
    if text is None:
        return None
    out = _json_text(text, scrub, counts, field)
    if out is None:
        return scrub(text, counts).encode("utf-8")
    return (out + ("\n" if text.endswith("\n") else "")).encode("utf-8")


def _jsonl(data: bytes, scrub: Scrub, counts: dict, field: Field | None = None) -> bytes | None:
    text = _decode(data)
    if text is None:
        return None
    lines = []
    for line in text.split("\n"):
        if not line.strip():
            lines.append(line)
            continue
        out = _json_text(line, scrub, counts, field)
        lines.append(out if out is not None else scrub(line, counts))
    return "\n".join(lines).encode("utf-8")


def _csv(name: str, data: bytes, scrub: Scrub, counts: dict, field: Field | None = None) -> bytes | None:
    text = _decode(data)
    if text is None:
        return None
    delimiter = "\t" if PurePath(name).suffix.lower() == ".tsv" else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=delimiter, lineterminator="\n")
    header = rows[0] if rows else []
    for i, row in enumerate(rows):
        if i == 0 or not field:
            writer.writerow([scrub(cell, counts) for cell in row])
        else:
            # the header names each column, so a cell is judged under its column's name
            writer.writerow([field(header[j], cell, counts) if j < len(header) else scrub(cell, counts)
                             for j, cell in enumerate(row)])
    return buf.getvalue().encode("utf-8")


XML_TEXT_NODE = re.compile(r">([^<]+)<")
WORD_PARTS = re.compile(r"^(?:word/(?:document|header\d*|footer\d*|footnotes|endnotes|comments|commentsExtended)|docProps/(?:core|app|custom))\.xml$")
DOCX_MAX_INFLATED = 64 * 1024 * 1024   # a zip whose parts inflate past this is not read


def _scrub_xml(xml: str, scrub: Scrub, counts: dict) -> str:
    def repl(m):
        inner = html.unescape(m.group(1))
        out = scrub(inner, counts)
        if out == inner:
            return m.group(0)
        return ">" + html.escape(out, quote=True) + "<"
    return XML_TEXT_NODE.sub(repl, xml)


def _docx(data: bytes, scrub: Scrub, counts: dict) -> bytes | None:
    try:
        src = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return None
    if sum(info.file_size for info in src.infolist()) > DOCX_MAX_INFLATED:
        src.close()
        return "too-large"
    buf = io.BytesIO()
    with src, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            payload = src.read(info.filename)
            if WORD_PARTS.match(info.filename):
                text = _decode(payload)
                if text is not None:
                    payload = _scrub_xml(text, scrub, counts).encode("utf-8")
            dst.writestr(info.filename, payload)
    return buf.getvalue()


def sanitize_bytes(name: str, data: bytes, scrub: Scrub, counts: dict, field: Field | None = None,
                   docx: bool = False) -> tuple[bytes | None, str | None]:
    """(sanitized bytes, None) for a handled file, or (None, why) when it is skipped:
    why is 'pdf', 'binary', 'docx', 'too-large' or 'undecodable'. counts is tallied by
    class as scrub reports. `field`, when given, judges a string value a parser split from
    its key (JSON members, CSV columns). A Word file is skipped unless `docx` is set: the
    text-node pass misses attributes, CDATA and a term split across runs, so it is opt-in."""
    kind = classify(name, data[:SNIFF_BYTES])
    if kind == "pdf":
        return None, "pdf"
    if kind == "binary":
        return None, "binary"
    if kind == "docx" and not docx:
        return None, "docx"
    if kind == "json":
        out = _json(data, scrub, counts, field)
    elif kind == "jsonl":
        out = _jsonl(data, scrub, counts, field)
    elif kind == "csv":
        out = _csv(name, data, scrub, counts, field)
    elif kind == "docx":
        out = _docx(data, scrub, counts)
        if out == "too-large":
            return None, "too-large"
    else:
        out = _text(data, scrub, counts)
    if out is None:
        # a text-bearing type that did not decode is not inspected, which is a different fact
        # from a known binary type
        return None, "undecodable" if kind != "docx" else "binary"
    return out, None
