"""File tool: read files and list directories under a confined root.

Every path is resolved and checked against the root before any read; a
symlink pointing outside is refused the same as a `..` escape.
"""
from __future__ import annotations

import os
from pathlib import Path

from relay.errors import ToolFailed
from relay.tools.registry import tool

_READ_CAP = 100_000
_LIST_CAP = 500


def _confine(root: str, relative: str) -> Path:
    base = Path(root).resolve()
    candidate = (base / relative).resolve()
    if not candidate.is_relative_to(base):
        raise ToolFailed("file", f"path escapes root: {relative!r}",
                         retryable=False)
    return candidate


@tool("read_file", "Read one text file under the workspace root",
      timeout_s=10, tags=("local", "read"))
def read_file(path: str, root: str = ".") -> str:
    target = _confine(root, path)
    if target.is_symlink():
        raise ToolFailed("file", f"symlink refused: {path!r}",
                         retryable=False)
    if not target.is_file():
        raise ToolFailed("file", f"not a file: {path!r}", retryable=False)
    text = target.read_text(encoding="utf-8", errors="replace")
    if len(text) > _READ_CAP:
        return text[:_READ_CAP] + f"\n[TRUNCATED at {_READ_CAP} chars]"
    return text


@tool("list_dir", "List a directory under the workspace root",
      timeout_s=10, tags=("local", "read"))
def list_dir(path: str = ".", root: str = ".") -> str:
    target = _confine(root, path)
    if not target.is_dir():
        raise ToolFailed("file", f"not a directory: {path!r}",
                         retryable=False)
    lines: list[str] = []
    for i, name in enumerate(sorted(os.listdir(target))):
        if i >= _LIST_CAP:
            lines.append(f"[TRUNCATED at {_LIST_CAP} entries]")
            break
        kind = "dir" if (target / name).is_dir() else "file"
        lines.append(f"{kind}\t{name}")
    return "\n".join(lines) or "(empty)"
