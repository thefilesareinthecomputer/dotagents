#!/usr/bin/env python3
"""The release verifier for the sanitize engine: a second, parser-free pass over a
written copy that fails closed.

The engine parses files as structure, and every gap in a parser is a gap in the copy. This
pass shares none of that: it reads each file as bytes, decodes the whole thing as text,
opens a zip container and does the same to every member, and runs the matchers (secret
shapes, custom shapes, the term list on raw and normalized text, the per-run terms and
patterns) over that flat text and over every path. Any hit is a failure. Any part it could
not decode is a failure too, unless the caller says binaries were copied on purpose.

Counts and paths only; no value is ever printed. Stdlib only.
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import normalize as nz  # noqa: E402
import sanitize as sz  # noqa: E402

ZIP_EXT = {".docx", ".zip", ".xlsx", ".pptx", ".jar", ".ipynb.zip"}
MEDIA_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".tif", ".tiff", ".emf", ".wmf",
             ".mp3", ".mp4", ".mov", ".wav", ".woff", ".woff2", ".ttf", ".otf"}


def _decode(data: bytes) -> str | None:
    if b"\x00" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def flat_hits(text: str, opts: "sz.Options") -> dict:
    """Class counts for every matcher over one flat text, with nothing replaced."""
    counts: dict = {}
    for regex in sz.SECRET_PATTERNS:
        n = len(regex.findall(text))
        if n:
            counts["secret"] = counts.get("secret", 0) + n
    for cls, _, regex in sz.CUSTOM_CHECKS:
        n = len(regex.findall(text))
        if n:
            counts[cls] = counts.get(cls, 0) + n
    for s, e, decoded in nz.encoded_runs(text):
        if any(r.search(decoded) for r in sz.SECRET_PATTERNS) or any(r.search(decoded) for _, _, r in sz.CUSTOM_CHECKS):
            counts["encoded"] = counts.get("encoded", 0) + 1
    for cls, terms in (("term", opts.terms), ("ban", opts.extra_terms)):
        if not terms:
            continue
        raw = sum(len(sz.term_pattern(t).findall(text)) for t in terms)
        norm = len(nz.normalized_hits(text, terms))
        enc = len(nz.encoded_hits(text, lambda d: sz._raw_term_hit(d, terms) or bool(nz.normalized_hits(d, terms))))
        for key, n in ((cls, raw), (f"{cls}-normalized", norm), (f"{cls}-encoded", enc)):
            if n:
                counts[key] = counts.get(key, 0) + n
    for pat in opts.extra_patterns:
        n = len(sz.re.findall(pat, text))
        if n:
            counts["pattern"] = counts.get("pattern", 0) + n
    return counts


def _placeholder_free(text: str) -> str:
    """The engine's own placeholders are not hits: `[TERM]` is what a hit becomes."""
    for ph in (sz.SECRET, sz.TERM, "[EMAIL]", "[PHONE]", "[HOME]", "[ROLE]", "[CATALOG]", "[PATTERN]"):
        text = text.replace(ph, "")   # removed, not spaced: a space before `-plan.md` would read as a `-p` password flag
    return text


def verify_tree(root: Path, opts: "sz.Options", allow_binary: bool = False, skip_names: tuple = ()) -> dict:
    """{ok, files, hits: [{path, classes}], uninspected: [{path, why}]} over every file under
    root (or root itself when it is a file)."""
    import filetypes as ft
    entries = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file() or p.is_symlink())
    hits, uninspected, n = [], [], 0

    def shown(rel: str) -> str:
        """A path that is itself a hit is never printed raw: it goes through the engine first."""
        return opts.scrub(rel, {})

    for p in entries:
        rel = str(p.relative_to(root)) if root.is_dir() else p.name
        if p.name in skip_names:
            continue
        n += 1
        if p.is_symlink():
            uninspected.append({"path": shown(rel), "why": "link"})
            continue
        counts = flat_hits(_placeholder_free(rel), opts)
        path_hit = bool(counts)
        try:
            data = p.read_bytes()
        except OSError:
            uninspected.append({"path": shown(rel), "why": "unreadable"})
            continue
        texts: list[tuple[str, str]] = []
        if p.suffix.lower() in ZIP_EXT or data[:2] == b"PK":
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    if sum(i.file_size for i in z.infolist()) > ft.DOCX_MAX_INFLATED:
                        uninspected.append({"path": shown(rel), "why": "too-large"})
                        continue
                    for info in z.infolist():
                        if info.is_dir():
                            continue
                        # a member's name is a path too
                        for k, v in flat_hits(_placeholder_free(info.filename), opts).items():
                            counts[k] = counts.get(k, 0) + v
                            path_hit = True
                        member = _decode(z.read(info.filename))
                        if member is None:
                            if allow_binary or Path(info.filename).suffix.lower() in MEDIA_EXT:
                                continue
                            uninspected.append({"path": shown(f"{rel}!{info.filename}"), "why": "undecodable"})
                        else:
                            texts.append((info.filename, member))
            except zipfile.BadZipFile:
                uninspected.append({"path": shown(rel), "why": "bad-zip"})
        else:
            text = _decode(data)
            if text is None:
                if not allow_binary:
                    uninspected.append({"path": shown(rel), "why": "undecodable"})
            else:
                texts.append((rel, text))
        for _, text in texts:
            for k, v in flat_hits(_placeholder_free(text), opts).items():
                counts[k] = counts.get(k, 0) + v
        if counts:
            hits.append({"path": shown(rel), "path_hit": path_hit, "classes": dict(sorted(counts.items()))})
    return {"ok": not hits and not uninspected, "files": n, "hits": hits, "uninspected": uninspected}
