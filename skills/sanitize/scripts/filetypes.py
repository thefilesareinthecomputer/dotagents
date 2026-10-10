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


def _walk_json(value, scrub: Scrub, counts: dict):
    if isinstance(value, str):
        return scrub(value, counts)
    if isinstance(value, dict):
        return {scrub(k, counts) if isinstance(k, str) else k: _walk_json(v, scrub, counts) for k, v in value.items()}
    if isinstance(value, list):
        return [_walk_json(v, scrub, counts) for v in value]
    return value


def _json_text(text: str, scrub: Scrub, counts: dict) -> str | None:
    try:
        value = json.loads(text)
    except ValueError:
        return None
    indent = 2 if "\n" in text.strip() else None
    return json.dumps(_walk_json(value, scrub, counts), ensure_ascii=False, indent=indent)


def _json(data: bytes, scrub: Scrub, counts: dict) -> bytes | None:
    text = _decode(data)
    if text is None:
        return None
    out = _json_text(text, scrub, counts)
    if out is None:
        return scrub(text, counts).encode("utf-8")
    return (out + ("\n" if text.endswith("\n") else "")).encode("utf-8")


def _jsonl(data: bytes, scrub: Scrub, counts: dict) -> bytes | None:
    text = _decode(data)
    if text is None:
        return None
    lines = []
    for line in text.split("\n"):
        if not line.strip():
            lines.append(line)
            continue
        out = _json_text(line, scrub, counts)
        lines.append(out if out is not None else scrub(line, counts))
    return "\n".join(lines).encode("utf-8")


def _csv(name: str, data: bytes, scrub: Scrub, counts: dict) -> bytes | None:
    text = _decode(data)
    if text is None:
        return None
    delimiter = "\t" if PurePath(name).suffix.lower() == ".tsv" else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=delimiter, lineterminator="\n")
    for row in rows:
        writer.writerow([scrub(cell, counts) for cell in row])
    return buf.getvalue().encode("utf-8")


XML_TEXT_NODE = re.compile(r">([^<]+)<")
WORD_PARTS = re.compile(r"^word/(document|header\d*|footer\d*|footnotes|endnotes|comments|commentsExtended)\.xml$")


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


def sanitize_bytes(name: str, data: bytes, scrub: Scrub, counts: dict) -> tuple[bytes | None, str | None]:
    """(sanitized bytes, None) for a handled file, or (None, why) when it is skipped:
    why is 'pdf' or 'binary'. counts is tallied by class as scrub reports."""
    kind = classify(name, data[:SNIFF_BYTES])
    if kind == "pdf":
        return None, "pdf"
    if kind == "binary":
        return None, "binary"
    if kind == "json":
        out = _json(data, scrub, counts)
    elif kind == "jsonl":
        out = _jsonl(data, scrub, counts)
    elif kind == "csv":
        out = _csv(name, data, scrub, counts)
    elif kind == "docx":
        out = _docx(data, scrub, counts)
    else:
        out = _text(data, scrub, counts)
    if out is None:
        return None, "binary"
    return out, None
