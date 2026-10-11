"""Vault adapter over the repo's obsidian-kg engine.

The engine script is loaded as a module from skills/obsidian-kg/scripts/ (it has
no package wrapper). Every read goes through _fresh() so no endpoint can serve a
stale index; the engine re-ingests on manifest drift by itself.
"""

import importlib.util
import os
from pathlib import Path

from agents_app import config

# The one engine in the repo, three levels above this package; no second copy to drift.
_ENGINE_PATH = Path(__file__).resolve().parents[3] / "skills" / "obsidian-kg" / "scripts" / "obsidian_kg.py"

_spec = importlib.util.spec_from_file_location("obsidian_kg", _ENGINE_PATH)
engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine)


def _fresh(vault: Path) -> None:
    """ensure_fresh, but a vault with no database yet gets a first ingest
    instead of the engine's sys.exit."""
    if not engine.db_path(vault).exists():
        engine.ingest(vault)
    else:
        engine.ensure_fresh(vault)


def _visible(entry: Path) -> bool:
    return not entry.name.startswith(".") and entry.name != "vault-kg"


def fresh_connection(vault: Path | None = None):
    """A connection to a guaranteed-fresh index; caller closes it.
    Uses _fresh so a vault with no database gets a first ingest."""
    vault = vault or config.vault_path()
    _fresh(vault)
    return engine.connect(vault, must_exist=True)


def tree(vault: Path | None = None) -> dict:
    vault = vault or config.vault_path()

    def walk(directory: Path) -> dict:
        dirs, files = [], []
        for entry in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
            if not _visible(entry):
                continue
            if entry.is_dir():
                dirs.append(walk(entry))
            elif entry.is_file():
                files.append({"name": entry.name,
                              "path": str(entry.relative_to(vault))})
        rel = "" if directory == vault else str(directory.relative_to(vault))
        return {"name": directory.name, "path": rel, "dirs": dirs, "files": files}

    return walk(vault)


def file_text(path: str, vault: Path | None = None) -> str:
    """Raw file text. Lexical guard, not resolve(): vault-mount mirrors
    real directories and a resolve() check would break on them.

    Raises PermissionError on a guarded path, FileNotFoundError otherwise.
    """
    vault = vault or config.vault_path()
    if ".." in path or path.startswith("/") or "\\" in path:
        raise PermissionError(path)
    target = vault / path
    if not target.is_file():
        raise FileNotFoundError(path)
    return target.read_text()


def parity(vault: Path | None = None) -> list[str]:
    """Notes on disk that the engine's enumeration misses.

    Graph membership is vault-contents-minus-.kgignore; git is a
    publishing boundary, never a knowledge boundary. But the engine
    enumerates via git when the vault is inside a repo, which silently
    skips notes git hides: gitignored files, and anything inside a
    nested repo. Until that is fixed at the engine's source, this makes
    the drop loud instead of silent. Same walk filters as the engine's
    own non-git path (dot folders, SKIP_FOLDERS, vault-kg, symlinks),
    so every path reported here is one the graph WOULD serve if the
    enumeration could see it."""
    vault = vault or config.vault_path()
    seen = {p.resolve() for p in engine.walk_vault(vault)}
    missing = []
    for root, dirs, names in os.walk(vault):
        dirs[:] = [d for d in dirs
                   if d not in engine.SKIP_FOLDERS and not d.startswith(".")
                   and not (Path(root) == vault and d == engine.KG_DIR)]
        for name in names:
            if not name.endswith(".md"):
                continue
            path = Path(root) / name
            if path.is_symlink():
                continue
            if path.resolve() not in seen:
                missing.append(path.relative_to(vault).as_posix())
    return sorted(missing)


def stats(vault: Path | None = None) -> dict:
    vault = vault or config.vault_path()
    _fresh(vault)
    con = engine.connect(vault, must_exist=True)
    try:
        one = lambda sql: con.execute(sql).fetchone()[0]
        return {
            "files": one("SELECT COUNT(*) FROM notes"),
            "sections": one("SELECT COUNT(*) FROM sections"),
            "edges": one("SELECT COUNT(*) FROM edges"),
            "unresolved": one("SELECT COUNT(*) FROM edges WHERE status='unresolved'"),
            "tags": one("SELECT COUNT(*) FROM tags"),
            "missing_from_graph": parity(vault),
        }
    finally:
        con.close()


def reindex(vault: Path | None = None) -> dict:
    vault = vault or config.vault_path()
    engine.ingest(vault)
    return stats(vault)


def search(query: str, scope: str = "content",
           vault: Path | None = None) -> list[dict]:
    """Ranked hits, one shape for both scopes:
    {path, heading, section_id, snippet, score, rung}."""
    vault = vault or config.vault_path()
    if scope == "filename":
        return _search_filenames(query, vault)
    _fresh(vault)
    result = engine.search(vault, query, limit=20)
    return [{
        "path": hit["path"],
        "heading": hit["heading_path"],
        "section_id": hit["section_id"],
        "snippet": hit["snippet"],
        "score": hit["score"],
        "rung": result["rung"],
    } for hit in result["results"]]


def _search_filenames(query: str, vault: Path) -> list[dict]:
    """Every keyword must appear (case-insensitive) somewhere in the
    vault-relative path; matches in the basename rank first."""
    keywords = [k.lower() for k in query.split() if k]
    if not keywords:
        return []
    hits = []
    for entry in sorted(vault.rglob("*")):
        if not entry.is_file():
            continue
        rel = entry.relative_to(vault)
        if any(part.startswith(".") or part == "vault-kg" for part in rel.parts):
            continue
        low_path = str(rel).lower()
        if not all(k in low_path for k in keywords):
            continue
        low_base = rel.name.lower()
        in_base = sum(1 for k in keywords if k in low_base)
        hits.append({
            "path": str(rel),
            "heading": None,
            "section_id": None,
            "snippet": str(rel),
            "score": round(in_base / len(keywords), 4),
            "rung": None,
        })
    hits.sort(key=lambda h: (-h["score"], h["path"].count("/"), h["path"]))
    return hits[:50]
