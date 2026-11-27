"""The shared core of the code-kg and markdown-kg engines.

Everything here is engine-neutral: the `.kg/` folder both engines keep under
a root, the `.kgignore` membership rule, git labels, terminal-safe printing,
the CLI runner, the FTS search ladder, the parse cache incremental ingest
reuses, the diff pairing passes, the graph algorithms and the `tree` view.
Each engine imports it from this repo's `lib/` folder, which is why their
SKILL.md files declare `metadata.ships: repo-lib`.

Stdlib only, and it runs on the python3 that stock macOS ships (3.9).
"""
from __future__ import annotations

import contextlib
import errno
import hashlib
import heapq
import hmac
import json
import os
import posixpath
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- the .kg/ folder ----------
KG_DIR = ".kg"     # shared by both engines; each file carries its engine's name
REBUILD_WAIT = 600  # seconds a read waits on another process's rebuild
# The files a .kg/ folder ships with, the same whichever engine writes them
# first. The .gitignore keeps the databases out of git and lets the configs
# and these docs in.
KG_FOLDER_FILES = {
    ".gitignore": (
        "# The knowledge-graph databases, their checkpoints and SQLite sidecars"
        " are local and rebuildable.\n"
        "# The configs and docs in this folder are committed.\n"
        "*.db*\n"),
    "README.md": (
        "# .kg\n\n"
        "This folder holds the knowledge graphs that the code-kg and"
        " markdown-kg agent skills build over this project.\n"
        "Either engine writes this README, `AGENTS.md`, `CLAUDE.md` and"
        " `.gitignore` when they are missing.\n\n"
        "| File | Engine | In git |\n"
        "| --- | --- | --- |\n"
        "| `code-kg-config.json` | code-kg | yes |\n"
        "| `markdown-kg-config.json` | markdown-kg | yes |\n"
        "| `*.db` files and their SQLite sidecars | either | no |\n"
        "| `README.md`, `AGENTS.md`, `CLAUDE.md`, `.gitignore` | both | yes |\n\n"
        "The databases hold the full text of every indexed file and rebuild"
        " from the tree, so `.gitignore` keeps them out of git.\n"
        "The configs hold this project's tuned settings, so they are"
        " committed with it.\n"
        "`.kgignore` at the project root excludes paths from both graphs, in"
        " gitignore syntax.\n\n"
        "## code-kg\n\n"
        "code-kg maps source code: imports, symbols, entry points, subsystems"
        " and data stores.\n"
        "`code-kg-config.json` declares source roots, entry points, import"
        " aliases and the test command, and `code-kg.db` holds the graph.\n\n"
        "## markdown-kg\n\n"
        "markdown-kg maps markdown notes by section: links, embeds,"
        " frontmatter and headings.\n"
        "`markdown-kg-config.json` declares note profiles, entities and"
        " markers, and `markdown-kg.db` holds the graph.\n"),
    "AGENTS.md": (
        "# .kg\n\n"
        "Rules for agents working in this folder; `README.md` describes its"
        " files.\n\n"
        "- Build and query the graphs with the code-kg and markdown-kg"
        " skills.\n"
        "- Never edit or commit a `.db` file. To rebuild a graph, run its"
        " skill's `ingest` on the project.\n"
        "- Edit a config as plain JSON and commit it with the change that"
        " needed it.\n"
        "- Put path exclusions in `.kgignore` at the project root, because"
        " both engines refuse a config with `ignore` rows.\n"
        "- Keep every file name here unchanged, because each engine finds its"
        " files by name.\n"),
    "CLAUDE.md": "@AGENTS.md\n",
}
# What .gitignore held before the configs were committed; a folder still
# holding it gets the current one.
OLD_GITIGNORE_SEED = ("# Local and rebuildable: knowledge-graph databases,"
                      " their checkpoints and configs.\n*\n")


def linked_store(root: Path, folder: Path, db: Path) -> str | None:
    """Why the engine's folder or database must not be used, or None. The
    tree being indexed is untrusted: a committed symlink at either name, or
    a folder that resolves outside the tree, would carry every write the
    engine makes to a place the planter chose."""
    for p in (folder, db):
        if p.is_symlink():
            return f"{p} is a symbolic link; refusing to write through it"
    try:
        if folder.exists() and not folder.resolve().is_relative_to(
                root.resolve()):
            return f"{folder} resolves outside {root}; refusing to use it"
    except (OSError, RuntimeError):
        return f"{folder} cannot be resolved; refusing to use it"
    return None


def seed_folder(folder: Path) -> None:
    """Write the engine's folder files that are missing: in .kg/ every file
    of KG_FOLDER_FILES, in a legacy folder its .gitignore only. A file
    already there is the project's own choice and is never rewritten, except
    a .gitignore still holding OLD_GITIGNORE_SEED, whose `*` would keep the
    configs out of git. O_EXCL and O_NOFOLLOW in one open: a link planted at
    a path, dangling or not, is never written through, with no gap between
    a check and the write."""
    def holds(path: Path, text: str) -> bool:
        return (path.is_file() and not path.is_symlink()
                and path.stat().st_size == len(text.encode("utf-8"))
                and path.read_text(encoding="utf-8", errors="replace") == text)

    names = KG_FOLDER_FILES if folder.name == KG_DIR else (".gitignore",)
    for name in names:
        path = folder / name
        if name == ".gitignore" and holds(path, OLD_GITIGNORE_SEED):
            path.unlink(missing_ok=True)
        # The pointer imports only the AGENTS.md the engines write, never
        # one a cloned repo planted.
        if name == "CLAUDE.md" and not holds(folder / "AGENTS.md",
                                             KG_FOLDER_FILES["AGENTS.md"]):
            continue
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | getattr(os, "O_NOFOLLOW", 0), 0o644)
        except OSError:
            continue
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(KG_FOLDER_FILES[name])


def config_json_text(cfg_file: Path) -> str:
    """The json text of a config file: the whole file, or the one fenced
    json block of a legacy markdown config. A legacy file with text but no
    json block is an error, because silently dropping its ignore rules would
    index what the corpus meant to keep out."""
    text = cfg_file.read_text(encoding="utf-8", errors="replace")
    if cfg_file.suffix == ".md" and text.strip():
        m = re.search(r"^```json\s*\n(.*?)\n```", text,
                      re.MULTILINE | re.DOTALL)
        if not m:
            sys.exit(f"error: {cfg_file} has no ```json block")
        return m.group(1)
    return text


class Store:
    """Where one engine keeps its files under a root. They live in the shared
    `.kg/` folder under the engine's own names, unless the root has one of
    the engine's legacy folders and no engine file in `.kg/`: then that
    folder is read and written in place, under its own names, until
    `migrate` moves it. Nothing ever creates a legacy folder."""

    def __init__(self, engine: str, noun: str,
                 legacy: dict[str, dict[str, str]]):
        self.engine = engine
        self.noun = noun                 # what a root is called in messages
        self.db = f"{engine}.db"
        self.prev_db = f"{engine}-prev.db"   # the checkpoint `diff` reads
        self.config = f"{engine}-config.json"
        self.legacy = legacy     # folder -> {current name: name there}, newest first
        self.dirs = (KG_DIR, *legacy)    # folders that are never corpus
        self._held: set = set()          # databases whose lock this holds

    def folder(self, root: Path) -> Path:
        """`.kg/` when it holds this engine's database or config, else the
        first legacy folder that exists, else `.kg/`, which is what a first
        write creates. The other engine shares `.kg/`, so the folder alone
        decides nothing."""
        current = root / KG_DIR
        if not any(os.path.lexists(current / n)
                   for n in (self.db, self.config)):
            for name in self.legacy:
                if (root / name).is_dir():
                    return root / name
        return current

    def _file(self, root: Path, name: str) -> Path:
        folder = self.folder(root)
        return folder / self.legacy.get(folder.name, {}).get(name, name)

    def db_path(self, root: Path) -> Path:
        return self._file(root, self.db)

    @contextlib.contextmanager
    def rebuild_lock(self, root: Path):
        """Hold this graph's rebuild lock, so one process rebuilds at a time
        and the rest wait instead of failing on a locked database. A wait
        says so once on stderr and ends at REBUILD_WAIT seconds. The lock
        file sits beside the database, under its `*.db*` ignore line; where
        the system or filesystem cannot lock, the rebuild runs unlocked."""
        try:
            import fcntl
        except ImportError:
            yield
            return
        db = self.db_path(root)
        if db in self._held:            # this process holds it already
            yield
            return
        # The same refusal every write makes, before the lock file exists.
        refused = linked_store(root, self.folder(root), db)
        if refused:
            sys.exit(f"error: {refused}")
        db.parent.mkdir(parents=True, exist_ok=True)
        if db.parent.name == KG_DIR:
            seed_folder(db.parent)      # its .gitignore covers the lock
        path = f"{db}.lock"
        try:
            # Read-only and non-blocking: a planted FIFO cannot stall the
            # open, and nothing is ever written to the file.
            fd = os.open(path, os.O_RDONLY | os.O_CREAT | os.O_NONBLOCK
                         | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except OSError as e:
            sys.exit(f"error: refusing lock file {path}: {e.strerror}")
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                sys.exit(f"error: refusing lock file {path}: not a file")
            deadline, told = time.monotonic() + REBUILD_WAIT, False
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if not told:
                        print(f"waiting for another rebuild of {db.name}",
                              file=sys.stderr)
                        told = True
                    if time.monotonic() > deadline:
                        sys.exit(f"error: another process has held {path}"
                                 f" for over {REBUILD_WAIT} s")
                    time.sleep(0.1)
                except OSError as e:
                    if e.errno not in (errno.ENOLCK, errno.EOPNOTSUPP):
                        raise
                    break
            self._held.add(db)
            yield
        finally:
            self._held.discard(db)
            os.close(fd)

    def refresh(self, root: Path, scan, fingerprint, rebuild) -> None:
        """Rebuild when the tree drifted from what the database recorded.
        A process that waited for another's rebuild walks again and checks
        before rebuilding, so concurrent reads after an edit rebuild once."""
        walked = scan(root)
        if self.recorded_manifest(root) == fingerprint(root, walked):
            return
        with self.rebuild_lock(root):
            walked = scan(root)
            if self.recorded_manifest(root) != fingerprint(root, walked):
                rebuild(root, walked)

    def prev_db_path(self, root: Path) -> Path:
        return self._file(root, self.prev_db)

    def config_path(self, root: Path) -> Path:
        return self._file(root, self.config)

    def connect(self, root: Path, schema: str, added_columns: dict,
                must_exist: bool = False) -> sqlite3.Connection:
        """The engine's database, with `schema` applied. The folder's files
        are seeded on first contact, not only by `init`, so the database is
        never committable however the folder came to exist.

        `added_columns` ({table: [(column, declaration)]}) are the columns a
        table gained after databases were already built. `CREATE TABLE IF
        NOT EXISTS` is a no-op on such a database, so the schema alone would
        leave it a column short and the next ingest would die on the insert.
        ALTER TABLE ADD COLUMN is cheap and non-destructive; the default
        stands until a re-ingest computes real values."""
        db = self.db_path(root)
        refused = linked_store(root, self.folder(root), db)
        if refused:
            sys.exit(f"error: {refused}")
        if must_exist and not db.exists():
            sys.exit(f"error: no database at {db} - run `ingest` on this"
                     f" {self.noun} first")
        db.parent.mkdir(parents=True, exist_ok=True)
        seed_folder(db.parent)
        con = sqlite3.connect(db)
        con.executescript(schema)
        for table, columns in added_columns.items():
            have = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
            for name, decl in columns:
                if have and name not in have:
                    con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
        con.commit()
        return con

    def recorded_manifest(self, root: Path) -> str | None:
        """The file-set fingerprint the last ingest recorded, read without
        writing. Every read command compares it with the tree's and
        re-ingests on drift: a tool whose correctness depends on the user
        remembering a step is wrong on the day it matters."""
        db = self.db_path(root)
        refused = linked_store(root, self.folder(root), db)
        if refused:
            sys.exit(f"error: {refused}")
        if not db.exists():
            sys.exit(f"error: no database at {db} - run `ingest` on this"
                     f" {self.noun} first")
        with contextlib.closing(ro_connect(str(db))) as con:
            try:
                row = con.execute(
                    "SELECT value FROM meta WHERE key='manifest'").fetchone()
            except sqlite3.DatabaseError:
                return None             # a database older than the meta table
        return row[0] if row else None

    def open_against(self, root: Path, against: str | None,
                     tables: tuple) -> tuple[str, sqlite3.Connection]:
        """The database `diff` compares the live one with, read-only: the
        checkpoint when `against` is None. Never opened through `connect`,
        which runs the schema script, a write, and the other side may be
        someone else's database. `tables` must all be in it."""
        if against is None:
            prev = self.prev_db_path(root)
            if not prev.exists():
                sys.exit(f"error: no checkpoint at {prev} - run `ingest"
                         f" <{self.noun}> --keep-previous` to create one")
            against = str(prev)
        elif not Path(against).is_file():
            sys.exit(f"error: --against {against} is not a file")
        con = ro_connect(against)
        try:
            have = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        except sqlite3.DatabaseError:
            have = set()
        if not set(tables) <= have:
            con.close()
            sys.exit(f"error: --against {against} is not a {self.engine} db"
                     f" (no {'/'.join(tables)} tables)")
        return against, con

    def migrate(self, root: Path) -> dict:
        """Move a legacy folder's files into .kg/ under the current names.
        The config's `ignore` rows go to the root's .kgignore first, each
        reason as a comment, so an interrupted run never leaves a database
        in .kg/ without its ignore rules. A config that is not plain json,
        or that lost its ignore rows, is rewritten as plain json with every
        other key kept; otherwise it moves as it is. The databases move
        rather than rebuild: they hold what no ingest recreates, such as
        coverage runs, session reads and recorded relations. The legacy
        folder is removed once only its .gitignore is left. Run it while no
        other command is using the graph."""
        old = self.folder(root)
        if old.name not in self.legacy:
            return {"from": None, "to": KG_DIR, "moved": [],
                    "removed": False, "left": []}
        new = root / KG_DIR
        names = self.legacy[old.name]
        for folder, db in ((old, old / names.get(self.db, self.db)),
                           (new, new / self.db), (root, root / ".kgignore")):
            refused = linked_store(root, folder, db)
            if refused:
                sys.exit(f"error: {refused}")
        cfg_src = old / names.get(self.config, self.config)
        data: dict = {}
        if cfg_src.is_file() and not cfg_src.is_symlink():
            text = config_json_text(cfg_src)
            try:
                data = json.loads(text) if text.strip() else {}
            except json.JSONDecodeError as e:
                sys.exit(f"error: {cfg_src} has invalid json: {e}")
            if not isinstance(data, dict):
                sys.exit(f"error: {cfg_src} must hold a json object")
        lines, dropped = [], []
        for row in data.pop("ignore", None) or []:
            row = row if isinstance(row, dict) else {"path": row}
            path = str(row.get("path", ""))
            # A row ignoring a legacy store folder itself is dead weight once
            # the store lives in .kg/ (legacy folders are never indexed), so
            # it is dropped and reported.
            if legacy_folder_row(path, self.legacy):
                dropped.append(path)
                continue
            reason = str(row.get("reason", "")).strip()
            lines += [f"# {reason}"] * bool(reason) + [path]
        rewrite = bool(lines or dropped) or cfg_src.suffix != ".json"
        moves = [(cfg_src, new / self.config)]
        moves += [(old / (names.get(n, n) + s), new / (n + s))
                  for n in (self.db, self.prev_db)
                  for s in ("", "-wal", "-shm", "-journal")]
        moves = [(src, dst) for src, dst in moves
                 if src.is_file() and not src.is_symlink()]
        for _, dst in moves:
            if os.path.lexists(dst):
                sys.exit(f"error: {dst} already exists; refusing to"
                         " overwrite it")
        moved = []
        if lines:
            append_kgignore(root, lines)
            moved.append([f"{cfg_src.relative_to(root).as_posix()} ignore"
                          " rows", ".kgignore"])
        new.mkdir(exist_ok=True)
        seed_folder(new)
        for src, dst in moves:
            if src == cfg_src and rewrite:
                fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                             | getattr(os, "O_NOFOLLOW", 0), 0o644)
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(json.dumps(data, indent=2, ensure_ascii=False,
                                        sort_keys=True) + "\n")
                src.unlink()
            else:
                os.replace(src, dst)
            moved.append([src.relative_to(root).as_posix(),
                          dst.relative_to(root).as_posix()])
        left = sorted(p.name for p in old.iterdir() if p.name != ".gitignore")
        if not left:
            (old / ".gitignore").unlink(missing_ok=True)
            old.rmdir()
        return {"from": old.name, "to": KG_DIR, "moved": moved,
                "dropped": dropped, "removed": not left, "left": left}


def legacy_folder_row(path: str, legacy: dict) -> bool:
    """True when an ignore row names a legacy store folder itself, in any of
    the forms a config writes it: `vault-kg`, `/vault-kg/`, `./vault-kg/**`. A long
    row is kept unjudged, since keeping a row is the safe failure."""
    path = path.strip()
    if len(path) > 256:
        return False
    m = re.fullmatch(r"(?:\./|/)*([^/*]+)(?:/\*{1,2})*/*", path)
    return bool(m) and m.group(1) in legacy


def render_migrate(p: dict) -> int:
    """Text for `migrate`."""
    if p["from"] is None:
        print(f"migrate: nothing to move; the graph is in {KG_DIR}/"
              " already, or not built yet")
        return 0
    for path in p.get("dropped", []):
        print(f"dropped ignore row {path}: it names a legacy store folder,"
              " which is never indexed")
    for src, dst in p["moved"]:
        print(f"moved {src} -> {dst}")
    print(f"removed {p['from']}/" if p["removed"] else
          f"left {p['from']}/ in place, holding: {', '.join(p['left'])}")
    return 0


def write_checkpoint(live: Path, prev: Path) -> None:
    """`live` copied to `prev` through a temp file this call creates and an
    atomic rename. A planted symlink or hardlink at either name is replaced,
    never written through, and a crash never leaves half a checkpoint."""
    fd, tmp = tempfile.mkstemp(dir=str(prev.parent),
                               prefix=prev.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as out, live.open("rb") as src:
            shutil.copyfileobj(src, out)
        os.replace(tmp, prev)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def ro_connect(path: str) -> sqlite3.Connection:
    """Open a db read-only, with the path percent-encoded into the URI. Bare
    concatenation would let a path containing '?' end the URI early and
    smuggle its own query parameters, `mode=rwc` among them."""
    quoted = urllib.parse.quote(str(Path(path).resolve()))
    return sqlite3.connect(f"file:{quoted}?mode=ro", uri=True)


# ---------- terminal safety ----------
# What prose output never passes through as-is, as codepoint ranges: C0 and C1
# controls (newline and tab excepted), then every character that renders as
# nothing or reorders what is displayed - soft hyphen and fillers, bidi marks,
# zero-width characters, line and paragraph separators, bidi overrides and
# isolates, invisible operators, the TAG plane and the variation-selector
# supplement. The ranges follow the `sanitize` skill's invisible-codepoint
# table. Numbers, so this file never holds one of the characters.
UNSAFE_RANGES = (
    (0x00, 0x08), (0x0B, 0x1F), (0x7F, 0x9F),
    (0xAD, 0xAD), (0x34F, 0x34F), (0x61C, 0x61C), (0x115F, 0x1160),
    (0x17B4, 0x17B5), (0x180B, 0x180F), (0x200B, 0x200F), (0x2028, 0x202E),
    (0x2060, 0x206F), (0x2800, 0x2800), (0x3164, 0x3164), (0xFE00, 0xFE0F),
    (0xFEFF, 0xFEFF), (0xFFA0, 0xFFA0), (0xFFF9, 0xFFFB),
    (0xE0000, 0xE007F), (0xE0100, 0xE01EF))
UNSAFE_RE = re.compile("[" + "".join(
    re.escape(chr(a)) + ("" if a == b else "-" + re.escape(chr(b)))
    for a, b in UNSAFE_RANGES) + "]")
_ZWJ, _EMOJI_VS, _KEYCAP = chr(0x200D), chr(0xFE0F), chr(0x20E3)
_PICTOGRAPH_RANGES = ((0x2190, 0x21FF), (0x2300, 0x23FF), (0x25A0, 0x27BF),
                      (0x2B00, 0x2BFF), (0x1F000, 0x1FAFF))
_PICTOGRAPH_SINGLES = frozenset((0xA9, 0xAE, 0x203C, 0x2049, 0x2122, 0x2139,
                                 0x3030, 0x303D, 0x3297, 0x3299))


def _pictograph(ch: str) -> bool:
    if not ch:
        return False
    cp = ord(ch)
    return cp in _PICTOGRAPH_SINGLES or any(
        a <= cp <= b for a, b in _PICTOGRAPH_RANGES)


def _visible(m: re.Match) -> str:
    """The escaped form of one unsafe character, or the character itself in
    the two places an emoji sequence needs one: a variation selector straight
    after a pictograph (or before a keycap), and a joiner between two."""
    c = m.group()
    text, i = m.string, m.start()
    before = text[i - 1:i]
    if 0xFE00 <= ord(c) <= 0xFE0F:
        # One selector per pictograph: a run of them is a byte channel.
        if _pictograph(before) or (c == _EMOJI_VS
                                   and text[i + 1:i + 2] == _KEYCAP):
            return c
    elif c == _ZWJ:
        if before == _EMOJI_VS:
            before = text[i - 2:i - 1]
        if _pictograph(before) and _pictograph(text[i + 1:i + 2]):
            return c
    shown = repr(c)[1:-1]
    if shown != c:
        return shown
    return f"\\u{ord(c):04x}" if ord(c) < 0x10000 else f"\\U{ord(c):08x}"


def term_safe(text: str) -> str:
    """Corpus-derived text about to be printed for a human: control
    characters and invisible or reordering characters become their escaped
    form, so an ANSI sequence in a file name, a config value or a source
    line cannot rewrite what the terminal shows, and a run of text nobody can
    see cannot ride along. Newline and tab stay. The corpus and the database
    keep the text as written; this touches only what is printed."""
    return UNSAFE_RE.sub(_visible, text)


def emit(args, payload, render) -> int:
    """Every command speaks json on demand and prose otherwise. The json path
    is for a parser: json.dumps escapes C0 controls but, with ensure_ascii
    off, passes C1 through, so pipe it to a parser, not a screen. Prose goes
    out behind the SafeStream `run_cli` installs."""
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    return render(payload)


class SafeStream:
    """A stdout or stderr that passes everything through `term_safe`.
    `run_cli` puts every command of both engines behind it, so no renderer,
    present or future, has to remember to."""

    def __init__(self, real):
        self._real = real

    def write(self, s):
        return self._real.write(term_safe(s))

    def flush(self):
        return self._real.flush()

    def __getattr__(self, name):
        return getattr(self._real, name)


def run_cli(args) -> int:
    """Run the parsed command `args.fn` behind SafeStream. Both engines'
    `main` ends here."""
    out, err = sys.stdout, sys.stderr
    # stderr is always read by a person: warnings, consent text, and every
    # error message. stdout is too, unless json was asked for - that output
    # is for a parser and json.dumps escapes control characters itself.
    sys.stderr = SafeStream(err)
    if not getattr(args, "json", False):
        sys.stdout = SafeStream(out)
    try:
        rc = args.fn(args)
        out.flush()
        return rc
    except SystemExit as e:
        if isinstance(e.code, str):
            # The interpreter prints this after the streams are restored.
            raise SystemExit(term_safe(e.code)) from None
        raise
    except BrokenPipeError:
        # The reader stopped early (`| head`). Point stdout at devnull so
        # the interpreter's last flush cannot raise again, and exit quietly.
        os.dup2(os.open(os.devnull, os.O_WRONLY), out.fileno())
        return 1
    finally:
        sys.stdout, sys.stderr = out, err


def print_capped(items: list, limit: int | None, fmt=str) -> None:
    """Print each item indented, at most `limit` of them, then how many were
    cut. A negative or None limit prints all: slicing with a negative would
    drop items from the end while the count claimed more were hidden."""
    lim = None if limit is None or limit < 0 else limit
    for item in items[:lim]:
        print(f"  {fmt(item)}")
    if lim is not None and len(items) > lim:
        print(f"  TRUNCATED: {len(items) - lim} more")


# ---------- glob matching (linear time; patterns are untrusted input) ----------
GLOB_MAX_LEN = 500


def _match_segment(name: str, pat: str) -> bool:
    """Wildcard match within one path segment: `*` any run, `?` one character.

    Two pointers with a remembered star position. A regex of chained `[^/]*`
    reads more naturally and is the reason this function exists: it backtracks
    exponentially, and `*a*a*a*a*a*a*a*a*a*a*b` against one ordinary filename
    measured over a minute. Patterns come from files inside the indexed tree,
    so that is a denial of service anybody who hands over a corpus can
    trigger. This runs in time proportional to the two lengths, always.
    """
    n = p = mark = 0
    star = -1
    while n < len(name):
        if p < len(pat) and pat[p] in ("?", name[n]):
            n += 1
            p += 1
        elif p < len(pat) and pat[p] == "*":
            star = p
            mark = n
            p += 1
        elif star >= 0:
            p = star + 1
            mark += 1
            n = mark
        else:
            return False
    while p < len(pat) and pat[p] == "*":
        p += 1
    return p == len(pat)


def _match_segments(parts: list[str], pats: list[str]) -> bool:
    """The same trick one level up, with `**` spanning whole segments."""
    n = p = mark = 0
    star = -1
    while n < len(parts):
        if p < len(pats) and pats[p] == "**":
            star = p
            mark = n
            p += 1
        elif p < len(pats) and _match_segment(parts[n], pats[p]):
            n += 1
            p += 1
        elif star >= 0:
            p = star + 1
            mark += 1
            n = mark
        else:
            return False
    while p < len(pats) and pats[p] == "**":
        p += 1
    return p == len(pats)


def glob_match(rel_path: str, pattern: str) -> bool:
    """Glob with `**` meaning any number of path segments."""
    if len(pattern) > GLOB_MAX_LEN:
        return False
    pattern = pattern.strip()
    if pattern.startswith("./"):
        pattern = pattern[2:]
    pattern = pattern.strip("/")
    if not pattern:
        return False
    parts = rel_path.split("/")
    pats = pattern.split("/")
    if _match_segments(parts, pats):
        return True
    # A bare pattern with no slash also matches by basename or any dir part,
    # the way .gitignore reads `dist` or `*.min.js`.
    if len(pats) == 1:
        return any(_match_segment(part, pats[0]) for part in parts)
    return False


# ---------- membership: .kgignore ----------
# The one membership rule both engines share. A file is in the graph unless a
# rule in a .kgignore at or below the graph root excludes it. Git's ignore
# files are not read: what git leaves out of a commit, gitignored notes and
# .env files among them, the graph may still need to know. Rules above the
# root are never read, so a tree indexes the same everywhere.
IGNORE_FILES = (".kgignore",)
IGNORE_LINES_MAX = 5000


def read_ignore_rules(folder: Path, base: str) -> list[tuple]:
    """The rules in `folder`'s ignore files, in git's syntax: `#` comments,
    `!` negation, a trailing `/` for folders only, and a leading or inner `/`
    anchoring the pattern to `folder`, whose path from the root is `base`.
    Patterns match with `*`, `?` and `**`, never a regex."""
    rules = []
    for name in IGNORE_FILES:
        f = folder / name
        if f.is_symlink() or not f.is_file():
            continue
        src = f"{base}/{name}" if base else name
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        for raw in lines[:IGNORE_LINES_MAX]:
            line = raw.rstrip()
            if not line or line.startswith("#") or len(line) > GLOB_MAX_LEN:
                continue
            neg = line.startswith("!")
            line = line[1:] if neg or line.startswith("\\") else line
            dirs_only = line.endswith("/")
            line = line.rstrip("/")
            anchored = "/" in line
            pats = [p for p in line.split("/") if p]
            if pats:
                rules.append((base, pats, neg, dirs_only, anchored,
                              f"{src}: {raw.strip()}"))
    return rules


def ignored_by(rel: str, is_dir: bool, rules: list[tuple]) -> str | None:
    """The rule that ignores `rel`, or None: the last matching rule decides,
    as in git. The walk never enters an ignored folder, so a rule only has to
    match the path itself."""
    hit = None
    for base, pats, neg, dirs_only, anchored, src in rules:
        if dirs_only and not is_dir:
            continue
        if base and not rel.startswith(base + "/"):
            continue
        sub = rel[len(base) + 1:] if base else rel
        if (_match_segments(sub.split("/"), pats) if anchored
                else _match_segment(sub.rsplit("/", 1)[-1], pats[0])):
            hit = None if neg else src
    return hit


def walk_tree(root: Path, skip_dir, list_ignored: bool = False) \
        -> tuple[list[Path], list[tuple[str, str]]]:
    """Every file under `root` no ignore rule excludes, and (path, rule) for
    what one does. `skip_dir(rel)` names folders never entered at all. An
    ignored folder is one row, unless `list_ignored` walks it to report each
    file inside under the rule that ignored the folder."""
    files, ignored = [], []
    state = {root: read_ignore_rules(root, "")}   # rules, or the folder's rule
    for d, dirs, names in os.walk(root):
        here = Path(d)
        rules = state.pop(here, [])
        prefix = "" if here == root else here.relative_to(root).as_posix() + "/"
        keep = []
        for name in sorted(dirs):
            rel = prefix + name
            if skip_dir(rel):
                continue
            why = rules if isinstance(rules, str) else ignored_by(rel, True, rules)
            if why and not list_ignored:
                ignored.append((rel + "/", why))
                continue
            state[here / name] = why or rules + read_ignore_rules(here / name, rel)
            keep.append(name)
        dirs[:] = keep
        for name in sorted(names):
            rel = prefix + name
            why = rules if isinstance(rules, str) else ignored_by(rel, False, rules)
            if why:
                ignored.append((rel, why))
            else:
                files.append(here / name)
    return files, ignored


def append_kgignore(root: Path, lines: list[str]) -> None:
    """Add `lines` to the end of the root's .kgignore, creating it, never
    through a link."""
    # Windows has no O_NOFOLLOW, so the link check happens before the open there.
    if not hasattr(os, "O_NOFOLLOW") and (root / ".kgignore").is_symlink():
        raise OSError(f"refusing to write through a link: {root / '.kgignore'}")
    fd = os.open(root / ".kgignore", os.O_RDWR | os.O_CREAT | os.O_APPEND
                 | getattr(os, "O_NOFOLLOW", 0), 0o644)
    with os.fdopen(fd, "a+", encoding="utf-8", newline="\n") as fh:
        fh.seek(0)
        lead = "\n" if fh.read()[-1:] not in ("", "\n") else ""
        fh.write(lead + "\n".join(lines) + "\n")


def path_filter(con: sqlite3.Connection, pattern: str | None,
                column: str) -> str:
    """SQL keeping only rows whose `column` matches the `--path` glob, or ''.
    It runs inside the query, before any row cap."""
    if not pattern:
        return ""
    con.create_function("kg_path_match", 1,
                        lambda p: glob_match(p or "", pattern),
                        deterministic=True)
    return f" AND kg_path_match({column})"


# ---------- git labels ----------
GIT_STATES = ("tracked", "untracked", "ignored", "none")


def git_status(root: Path, rels: list[str]) -> dict[str, str]:
    """Each path's git status under `root`: tracked, untracked or ignored,
    or none for all of them outside a work tree or without git. It labels
    files for `--git` and never decides membership. Two read-only calls per
    ingest, with `core.fsmonitor=` because a tree is untrusted content and
    its config must never run a command here."""
    base = ["git", "-c", "core.fsmonitor=", "--no-optional-locks",
            "-C", str(root)]
    try:
        tracked = subprocess.run(base + ["ls-files", "-z", "--cached"],
                                 capture_output=True, timeout=60)
        if tracked.returncode != 0:
            return dict.fromkeys(rels, "none")
        ignored = subprocess.run(base + ["check-ignore", "-z", "--stdin"],
                                 input="\0".join(rels).encode(
                                     "utf-8", "surrogateescape"),
                                 capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return dict.fromkeys(rels, "none")
    have = set(tracked.stdout.decode("utf-8", "replace").split("\0"))
    ign = set(ignored.stdout.decode("utf-8", "replace").split("\0"))
    return {r: "tracked" if r in have else "ignored" if r in ign
            else "untracked" for r in rels}


def git_ls_files(root: Path) -> set[str] | None:
    """The repo-relative paths git tracks under the work tree at `root`, or
    None outside a work tree or without git. One read-only call, with
    `core.fsmonitor=` for the reason `git_status` gives."""
    try:
        r = subprocess.run(["git", "-c", "core.fsmonitor=",
                            "--no-optional-locks", "-C", str(root),
                            "ls-files", "-z", "--cached"],
                           capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return {p for p in r.stdout.decode("utf-8", "replace").split("\0") if p}


def line_starts(text: str) -> list[int]:
    """The offset each line of a text starts at, for `bisect`: the number
    of starts at or before an offset is its 1-indexed line."""
    return [0] + [m.end() for m in re.finditer("\n", text)]


# ---------- search ----------
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_'-]*")


def tokenize(question: str, stopwords) -> tuple[list[str], list[str]]:
    """The quoted phrases of a question, and its other words lowercased,
    deduplicated in order, with `stopwords` and one-letter words dropped."""
    phrases = re.findall(r'"([^"]+)"', question)
    rest = re.sub(r'"[^"]*"', " ", question)
    terms = [t.lower() for t in WORD_RE.findall(rest)]
    terms = [t for t in terms if t not in stopwords and len(t) > 1]
    return phrases, list(dict.fromkeys(terms))


def fts_escape(term: str) -> str:
    return '"' + term.replace('"', '""') + '"'


def search_rungs(phrases: list[str], terms: list[str]) -> list[tuple[str, str]]:
    """The ladder: exact phrase, then all-terms AND, then OR. The first rung
    that returns hits wins - a lower rung never dilutes a higher one."""
    rungs = []
    if phrases:
        rungs.append(("phrase", " AND ".join(fts_escape(p) for p in phrases)))
    if phrases and terms:
        rungs.append(("phrase+terms",
                      " AND ".join(fts_escape(p) for p in phrases + terms)))
    if terms:
        rungs.append(("all-terms", " AND ".join(fts_escape(t) for t in terms)))
        if len(terms) > 1:
            rungs.append(("any-term", " OR ".join(fts_escape(t) for t in terms)))
    return rungs


def est_tokens(text: str) -> int:
    """Token estimate for budgeting. Deliberately crude and deliberately high:
    over-estimating keeps a pack inside its budget."""
    return max(1, len(text) // 3)


# Doc rank for capped lists: fixed names, never a config pattern.
PRIMARY_DOCS = ("README.md", "SKILL.md", "AGENTS.md", "CLAUDE.md")
ARCHIVE_DIRS = ("archive", "archived", "_archive", "completed", "old",
                "deprecated")


def doc_rank(path: str) -> int:
    """0 for a primary doc, 2 for an archived one, 1 otherwise: the order a
    capped list of doc rows is cut in."""
    parts = path.lower().split("/")
    if any(p in ARCHIVE_DIRS for p in parts[:-1]):
        return 2
    base = path.rsplit("/", 1)[-1]
    return 0 if base in PRIMARY_DOCS or base.startswith("SPEC") else 1


# ---------- parse cache: what an incremental ingest reuses ----------
def _json_enc(value):
    """JSON keeps lists but not tuples; a tuple is tagged so it comes back a tuple."""
    if isinstance(value, tuple):
        return {"__t": [_json_enc(v) for v in value]}
    if isinstance(value, list):
        return [_json_enc(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_enc(v) for k, v in value.items()}
    return value


def _json_dec(text: str):
    """The value `_json_enc` stored. Tagged tuples come back as the parser
    builds each object, so decoding never walks the value a second time."""
    return json.loads(text, object_hook=lambda d: tuple(d["__t"])
                      if d.keys() == {"__t"} else d)


def engine_fingerprint(engine_file: str, namespace: dict) -> str:
    """An engine's source and this module's, the Python version and the
    current value of every upper-case constant in the engine's namespace (a
    test or a flag may lower a cap): whatever can change what an ingest
    produces from the same files and config."""
    def stable(v):
        # Sets iterate in hash order, which changes per process; sort them.
        if isinstance(v, (set, frozenset)):
            return repr(sorted(map(stable, v)))
        if isinstance(v, dict):
            return repr(sorted((stable(k), stable(x)) for k, x in v.items()))
        if isinstance(v, (list, tuple)):
            return repr([stable(x) for x in v])
        # A function's repr carries its address, which changes every run.
        return re.sub(r" at 0x[0-9a-fA-F]+", "", repr(v))
    # A snapshot: another thread may set a module global while this runs.
    constants = sorted((k, stable(v)) for k, v in list(namespace.items())
                       if k.isupper() and isinstance(
                           v, (int, float, str, tuple, list, set, frozenset, dict)))
    return hashlib.sha256(
        Path(engine_file).read_bytes() + Path(__file__).read_bytes()
        + sys.version.encode() + repr(constants).encode()).hexdigest()


def _station_salt() -> bytes | None:
    """32 random bytes kept in this station's user state folder, outside every
    corpus, created on first use; None when the folder cannot be written, which
    turns the parse cache off rather than leaving its keys guessable."""
    base = (Path(os.environ["LOCALAPPDATA"]) if os.name == "nt" and os.environ.get("LOCALAPPDATA")
            else Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"))
    path = base / "kg" / "cache-salt"
    try:
        data = path.read_bytes()
        if len(data) == 32:
            return data
    except OSError:
        pass
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(os.urandom(32))
    except FileExistsError:
        pass                    # another process created it first; read theirs
    except OSError:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return data if len(data) == 32 else None


class ParseCache:
    """Results of the pure per-file work, kept in the graph's own database
    between ingests so an unchanged file is never parsed again. The key is
    the engine fingerprint, a station salt and the inputs, so any engine
    change starts cold. Values are JSON, never pickle: the database can
    arrive with a synced corpus. A value that does not survive the JSON round
    trip exactly is computed every time and never stored. Keys not used by an
    ingest are dropped at its end, so the cache holds one generation."""

    _source = None

    def __init__(self, con: sqlite3.Connection, fingerprint: str):
        con.execute("CREATE TABLE IF NOT EXISTS parse_cache("
                    "key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        if ParseCache._source is None:
            # The station salt keeps the keys unguessable: a db that arrives with
            # a synced corpus can carry planted rows, and without it anyone who
            # can write the corpus could compute a key and have its value trusted.
            ParseCache._source = _station_salt()
        self.off = ParseCache._source is None
        self.con, self.used, self.new = con, set(), []
        if not self.off:
            self._engine = hashlib.sha256(
                ParseCache._source + fingerprint.encode()).hexdigest()

    def get(self, name: str, key_parts: list, compute, pack=None, unpack=None,
            fresh=None):
        """`compute()` through the cache. `pack` shrinks a value before it is stored
        and `unpack` restores it; a value is stored only when unpacking the stored
        form gives back exactly what `compute()` returned. `fresh(value)` false
        means a stored value's other inputs changed, and it is recomputed."""
        if self.off:
            return compute()
        pack = pack or (lambda v: v)
        unpack = unpack or (lambda v: v)
        key = hashlib.sha256(json.dumps([self._engine, name, key_parts],
                                        sort_keys=True).encode()).hexdigest()
        self.used.add(key)
        row = self.con.execute("SELECT value FROM parse_cache WHERE key = ?",
                               (key,)).fetchone()
        if row is not None:
            try:
                value = unpack(_json_dec(row[0]))
                if fresh is None or fresh(value):
                    return value
            except Exception:           # any unreadable value is recomputed, never trusted
                pass
        value = compute()
        try:
            blob = json.dumps(_json_enc(pack(value)))
            if unpack(_json_dec(blob)) == value:
                self.new.append((key, blob))
        except (TypeError, ValueError, KeyError):
            pass
        return value

    def flush(self) -> None:
        if self.off:
            self.con.execute("DELETE FROM parse_cache")
            return
        self.con.executemany("INSERT OR REPLACE INTO parse_cache(key, value)"
                             " VALUES (?,?)", self.new)
        self.con.execute("CREATE TEMP TABLE IF NOT EXISTS used_keys(key TEXT PRIMARY KEY)")
        self.con.execute("DELETE FROM used_keys")
        self.con.executemany("INSERT OR IGNORE INTO used_keys(key) VALUES (?)",
                             [(k,) for k in self.used])
        self.con.execute("DELETE FROM parse_cache WHERE key NOT IN (SELECT key FROM used_keys)")


def seal(text: str) -> str | None:
    """`text` bound to this machine by an HMAC under the station salt, so
    what a database built elsewhere, or planted, records never matches what
    this machine computes. None when the salt is unavailable."""
    if ParseCache._source is None:
        ParseCache._source = _station_salt()
    salt = ParseCache._source
    return hmac.new(salt, text.encode(), hashlib.sha256).hexdigest() \
        if salt else None


# ---------- diff ----------
def classify_units(old: dict, new: dict) -> dict:
    """The diff passes both engines run over units keyed by id, each a tuple
    (id, group, hash, stripped, label): group is the note or file, hash the
    whole unit's, stripped the hash below its title line (a heading, a
    `def` line), or None when nothing is left there to pair on. Passes, in
    order: exact (same id, same hash); ordinal shift (same group, same id
    without its ~n, same hash), both unchanged; edited (same id); renamed
    (same group, same stripped hash); moved (same stripped hash). Leftovers
    are added and removed. Pairs form count-for-count in id order, so
    duplicates never pair many-to-one."""
    unchanged = 0
    old_left = dict(old)
    new_left: dict = {}
    for uid, row in new.items():
        other = old_left.get(uid)
        if other is not None and other[2] == row[2]:
            del old_left[uid]
            unchanged += 1
        else:
            new_left[uid] = row

    def pair(key_of):
        pairs = []
        old_by: dict = {}
        for uid in sorted(old_left):
            key = key_of(old_left[uid])
            if key is not None:
                old_by.setdefault(key, []).append(uid)
        for uid in sorted(new_left):
            key = key_of(new_left[uid])
            cands = old_by.get(key) if key is not None else None
            if cands:
                pairs.append((old_left.pop(cands.pop(0)), new_left.pop(uid)))
        return sorted(pairs, key=lambda p: p[1][0])

    unchanged += len(pair(lambda r: (r[1], re.sub(r"~\d+$", "", r[0]),
                                     r[2])))
    edited = pair(lambda r: r[0])
    renamed = pair(lambda r: None if r[3] is None else (r[1], r[3]))
    moved = pair(lambda r: r[3])
    return {"unchanged": unchanged, "edited": edited, "renamed": renamed,
            "moved": moved,
            "added": [new_left[u] for u in sorted(new_left)],
            "removed": [old_left[u] for u in sorted(old_left)]}


def unit_diff(old: dict, new: dict, id_key: str, label_key: str) -> dict:
    """`classify_units` as `diff` rows: a lone unit as {id_key, label_key},
    a pair as from and to of both."""
    c = classify_units(old, new)

    def entry(r):
        return {id_key: r[0], label_key: r[4]}

    def pair(p):
        o, n = p
        return {"from_id": o[0], "to_id": n[0], f"from_{label_key}": o[4],
                f"to_{label_key}": n[4]}

    return {"added": [entry(r) for r in c["added"]],
            "removed": [entry(r) for r in c["removed"]],
            "edited": [pair(p) for p in c["edited"]],
            "renamed": [pair(p) for p in c["renamed"]],
            "moved": [pair(p) for p in c["moved"]],
            "unchanged": c["unchanged"]}


def changed_keys(new: dict, old: dict) -> dict:
    """The keys added, removed, and kept with a different value."""
    return {"added": sorted(new.keys() - old.keys()),
            "removed": sorted(old.keys() - new.keys()),
            "edited": sorted(k for k in new.keys() & old.keys()
                             if new[k] != old[k])}


# ---------- the other engine ----------
# Each engine reaches the other as a sibling skill folder and through its
# command line only: `--json` out, never its database file, so a schema
# change on one side cannot break a read on the other.
SIBLING_TIMEOUT = 120


def run_sibling(cli: Path, name: str, argv: tuple,
                 flags: tuple = ()) -> tuple[object, str]:
    """One read command of the engine at `cli`: (parsed answer, '') or
    (None, one line saying why there is none). That engine refreshes its own
    database first when its tree has changed. `--` ends the options, because
    the paths that follow come from corpus text; `flags` go before it."""
    if not cli.is_file():
        return None, f"the {name} skill is not installed beside this one"
    try:
        r = subprocess.run(
            [sys.executable, str(cli), argv[0], "--json", *flags, "--",
             *argv[1:]], capture_output=True, encoding="utf-8",
            errors="replace", timeout=SIBLING_TIMEOUT,
            env={**os.environ, "PYTHONUTF8": "1"})
        if r.returncode == 0:
            return json.loads(r.stdout), ""
        why = (r.stderr.strip().splitlines() or ["no output"])[-1][:300]
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        why = type(e).__name__
    return None, f"{name} {argv[0]}: {why}"


# ---------- recorded relations ----------
# A relation an agent recorded lives in `extractions`, never wiped by an
# ingest; two that disagree raise a row in `conflicts`.
def retire_relation(con: sqlite3.Connection, rid: int) -> dict:
    """The exit route for a wrong judgment row. The never-delete rule holds:
    the row keeps its evidence with status 'retired', sticky across ingests,
    but it leaves traversal, the default listing and the duplicate and
    conflict checks, and its open conflicts close."""
    row = con.execute("SELECT status FROM extractions WHERE id=? AND"
                      " kind='relation'", (rid,)).fetchone()
    if row is None:
        sys.exit(f"error: no recorded relation #{rid}")
    con.execute("UPDATE extractions SET status='retired' WHERE id=?", (rid,))
    con.execute("UPDATE conflicts SET state='cold' WHERE kind='relation'"
                " AND (a_extraction=? OR b_extraction=?)", (rid, rid))
    con.commit()
    return {"id": rid, "was": row[0], "status": "retired"}


def resolve_conflict(con: sqlite3.Connection, seq: int,
                     resolution: str) -> dict:
    """Record the ruling on a relation conflict and close it. The rows it
    names stay as they are: retiring the losing relation is a separate,
    deliberate act."""
    resolution = resolution.strip()
    if not resolution:
        sys.exit("error: a resolution must say something")
    if con.execute("SELECT 1 FROM conflicts WHERE seq=? AND kind='relation'",
                   (seq,)).fetchone() is None:
        sys.exit(f"error: no relation conflict #{seq}")
    con.execute("UPDATE conflicts SET resolution=?, state='cold'"
                " WHERE seq=?", (resolution, seq))
    con.commit()
    return {"seq": seq, "state": "cold", "resolution": resolution}


def relation_ruling(args, open_db) -> int | None:
    """`relations --retire ID` or `relations --resolve SEQ TEXT` against the
    connection `open_db()` returns, or None when the call is a listing."""
    if args.retire is None and args.resolve is None:
        return None
    with contextlib.closing(open_db()) as con:
        if args.retire is not None:
            return emit(args, retire_relation(con, args.retire),
                        lambda p: print(f"#{p['id']}: {p['was']} -> retired")
                        or 0)
        seq, text = args.resolve
        try:
            seq = int(seq)
        except ValueError:
            sys.exit(f"error: conflict seq must be a number, got {seq!r}")
        return emit(args, resolve_conflict(con, seq, text),
                    lambda p: print(f"conflict #{p['seq']} closed:"
                                    f" {p['resolution']}") or 0)


# ---------- graph ----------
def bfs_path(adj: dict, a: str, b: str) -> list[str] | None:
    """The shortest path from `a` to `b` over `adj` ({node: neighbor ids}),
    or None when `b` is out of reach. Neighbors are visited in sorted order,
    so a tie breaks the same way on every run."""
    if a == b:
        return [a]
    prev = {a: a}
    frontier = [a]
    while frontier:
        nxt = []
        for node in frontier:
            for other in sorted(adj.get(node, ())):
                if other in prev:
                    continue
                prev[other] = node
                if other == b:
                    chain = [b]
                    while chain[-1] != a:
                        chain.append(prev[chain[-1]])
                    return chain[::-1]
                nxt.append(other)
        frontier = nxt
    return None


RELATED_DAMPING = 0.85
RELATED_MAX_ITER = 100
RELATED_TOLERANCE = 1e-10


def rank_from(graph: dict, seed: str, limit: int) -> dict:
    """Personalized PageRank from `seed` over an undirected weighted graph
    ({node: {other: weight}}), on the part of it the seed reaches. A walker
    starts on the seed, follows edges in proportion to their weight, and at
    every step returns to the seed with probability 1 - damping; a node's
    score is the share of time spent on it. Fixed damping, sorted
    iteration: the same graph always gives the same ranking. `limit` 0 or
    less returns every node."""
    hops = {seed: 0}
    frontier = [seed]
    while frontier:
        nxt = []
        for node in frontier:
            for other in sorted(graph.get(node, {})):
                if other not in hops:
                    hops[other] = hops[node] + 1
                    nxt.append(other)
        frontier = nxt
    nodes = sorted(hops)
    out_weight = {n: sum(graph[n].values()) for n in nodes}
    score = {n: 0.0 for n in nodes}
    score[seed] = 1.0
    iterations = 0
    for iterations in range(1, RELATED_MAX_ITER + 1):
        nxt_score = {n: 0.0 for n in nodes}
        for n in nodes:
            if not score[n]:
                continue
            share = RELATED_DAMPING * score[n] / out_weight[n]
            for other, w in graph[n].items():
                nxt_score[other] += share * w
        nxt_score[seed] += 1.0 - RELATED_DAMPING
        delta = sum(abs(nxt_score[n] - score[n]) for n in nodes)
        score = nxt_score
        if delta < RELATED_TOLERANCE:
            break
    ranked = sorted(((round(score[n], 6), n) for n in nodes if n != seed),
                    key=lambda r: (-r[0], r[1]))
    shown = ranked if limit <= 0 else ranked[:limit]
    return {"damping": RELATED_DAMPING, "iterations": iterations,
            "nodes": len(nodes),
            "status": ("COMPLETE" if len(shown) == len(ranked)
                       else f"TRUNCATED {len(shown)} of {len(ranked)}"),
            "related": [{"id": n, "score": s, "hops": hops[n]}
                        for s, n in shown]}


def greedy_modularity(adj: dict, deg: dict, m: float) -> dict[str, int]:
    """Clauset-Newman-Moore: every node starts alone, then repeatedly merge
    the connected pair with the largest modularity gain until no merge
    improves the partition. Chosen over label propagation because it is
    deterministic without tie-breaking tricks and optimizes a stated
    objective, so the modularity score reported beside it means something.

    Merge candidates live in a heap with lazy invalidation - a popped entry
    whose gain no longer matches the current graph is recomputed and pushed
    back rather than trusted. Inter-community weight is a neighbor map per
    community, so a merge touches the absorbed community's neighbors and
    nothing else; scanning one table of every link on every merge is what
    made large graphs take minutes. The groups are the same either way, and
    a test holds this version to the first one on random graphs."""
    if m <= 0:
        return {}
    ids = {n: i for i, n in enumerate(sorted(adj))}
    members = {i: {n} for n, i in ids.items()}
    tot = {ids[n]: deg[n] for n in adj}
    nbr: dict[int, dict[int, float]] = {i: {} for i in members}
    for a, nbrs in adj.items():
        for b, w in nbrs.items():
            if a != b:
                nbr[ids[a]][ids[b]] = w

    def gain(ca: int, cb: int) -> float:
        return (nbr[ca].get(cb, 0.0) / m
                - (tot[ca] * tot[cb]) / (2.0 * m * m))

    heap = [(-gain(a, b), a, b) for a in nbr for b in nbr[a] if a < b]
    heapq.heapify(heap)
    # The heap never holds the same entry twice. Every merge queues an entry
    # per neighbor, and without this a hub with n neighbors piles up n
    # copies of each, all popped and re-queued one by one: cubic work on a
    # plain star, which is one module every other file imports.
    queued = set(heap)

    def queue(entry: tuple) -> None:
        if entry not in queued:
            queued.add(entry)
            heapq.heappush(heap, entry)

    while heap:
        entry = heapq.heappop(heap)
        queued.discard(entry)
        negdq, ca, cb = entry
        if ca not in members or cb not in members:
            continue
        if cb not in nbr[ca]:
            continue
        fresh = gain(ca, cb)
        if abs(fresh - (-negdq)) > 1e-12:
            queue((-fresh, ca, cb))
            continue
        if fresh <= 1e-12:
            break  # no remaining merge improves Q; the heap is max-first
        keep, drop = (ca, cb) if ca < cb else (cb, ca)
        # The smaller set is poured into the larger, whichever id survives.
        big, small = members.pop(keep), members.pop(drop)
        if len(big) < len(small):
            big, small = small, big
        big |= small
        members[keep] = big
        tot[keep] += tot.pop(drop)
        # Rewire every link that touched the absorbed community.
        for other, w in nbr.pop(drop).items():
            del nbr[other][drop]
            if other != keep:
                nbr[keep][other] = nbr[keep].get(other, 0.0) + w
                nbr[other][keep] = nbr[keep][other]
        for other in nbr[keep]:
            queue((-gain(keep, other), keep, other))
    owner = {n: cid for cid, group in members.items() for n in group}
    return {n: owner[n] for n in sorted(adj)}


# ---------- tree ----------
TREE_LIMIT = 200       # folders, and files, `tree` prints unless told


def tree_payload(rows: list, root: Path, folder: str, depth: int,
                 files: bool, absolute: bool, limit: int) -> dict:
    """`tree` from file rows ({path, language, ext, ...}; language None for
    a file no parser reads): direct and recursive counts by folder, with
    languages and the extensions of unread files. `depth` 1 is the folder
    alone, 0 every level; `limit` 0 or less shows all."""
    def key(path: str) -> tuple:
        return tuple(path.split("/")) if path else ()

    def cut(items: list) -> tuple:
        if limit > 0 and len(items) > limit:
            return items[:limit], f"TRUNCATED {limit} of {len(items)}"
        return items, "COMPLETE"

    folder = posixpath.normpath(folder.replace("\\", "/")).strip("/")
    folder = "" if folder == "." else folder
    rows = [r for r in rows if not folder
            or r["path"].startswith(folder + "/")]
    if folder and not rows:
        sys.exit(f"error: no files under {folder!r} - `tree` with no folder"
                 " lists them all")
    base = len(key(folder))
    tally: dict = {}
    for r in rows:
        chain = [posixpath.dirname(r["path"])]
        while len(key(chain[-1])) > base:
            chain.append(posixpath.dirname(chain[-1]))
        for i, f in enumerate(chain):
            t = tally.setdefault(f, {"path": f, "files": 0, "total": 0,
                                     "languages": {}, "other": {}})
            t["files"] += i == 0
            t["total"] += 1
            group, name = ("languages", r["language"]) if r["language"] \
                else ("other", r["ext"] or "(none)")
            t[group][name] = t[group].get(name, 0) + 1
    shown = [t for t in sorted(tally.values(), key=lambda t: key(t["path"]))
             if depth <= 0 or len(key(t["path"])) - base < depth]
    folders, status = cut(shown)
    payload = {"root": str(root.resolve()), "folder": folder,
               "folders": folders, "status": status}
    if files:
        keep = {t["path"] for t in shown}
        listed = sorted((dict(r) for r in rows
                         if posixpath.dirname(r["path"]) in keep),
                        key=lambda r: key(r["path"]))
        for r in listed if absolute else ():
            r["absolute"] = str(root.resolve().joinpath(
                *r["path"].split("/")))
        payload["files"], payload["files_status"] = cut(listed)
    return payload


def other_file_rows(con: sqlite3.Connection) -> list[dict]:
    """The files no parser reads, from `other_files`, as `tree` rows."""
    return [{"path": p, "language": None, "ext": ext, "size": size,
             "reason": reason}
            for p, ext, size, reason in con.execute(
                "SELECT path, ext, size, reason FROM other_files")]


def tree_command(args, root: Path, rows: list) -> int:
    """`tree` over every file row an engine has: what it parsed and what it
    only listed."""
    payload = tree_payload(rows, root, args.folder or "", args.depth,
                           args.files, args.absolute, args.limit)
    return emit(args, payload, render_tree)


def render_tree(p: dict) -> int:
    """Text for `tree`."""
    def counts(d: dict) -> str:
        return ", ".join(f"{k} {v}" for k, v in sorted(d.items()))

    def depth(path: str) -> int:
        return len(path.split("/")) if path else 0

    print(p["root"])
    by_folder: dict = {}
    for r in p.get("files", []):
        by_folder.setdefault(posixpath.dirname(r["path"]), []).append(r)
    for t in p["folders"]:
        pad = "  " * (depth(t["path"]) - depth(p["folder"]))
        parts = [counts(t["languages"])] if t["languages"] else []
        if t["other"]:
            parts.append(f"other {sum(t['other'].values())}"
                         f" ({counts(t['other'])})")
        print(f"{pad}{t['path'] + '/' if t['path'] else './'}"
              f"  {t['total']} files: {', '.join(parts)}")
        for r in by_folder.get(t["path"], []):
            what = (f"{r['language']}, {r['lines']} lines"
                    if r["language"] else f"({r['reason']})")
            print(f"{pad}  {r.get('absolute', r['path'])}  {what}")
    for k in ("status", "files_status"):
        if p.get(k, "COMPLETE") != "COMPLETE":
            print(f"{k.replace('_', ' ')}: {p[k]}; --limit 0 for all")
    return 0
