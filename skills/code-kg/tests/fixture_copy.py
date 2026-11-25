"""Copy a fixture tree for a test, with its engine config written at copy
time. A fixture's config sits beside it as `<fixture>.config.json`, not in
the tree's own `.kg/` folder, so the repo can ignore every `.kg/` with no
exception for tests.

Dependency manifests that name real packages are written at copy time too,
from GENERATED below. Dependency scanners read every committed manifest as a
real app's and flag its pinned versions, though nothing installs a fixture.
The engine reads only the dependency names; the versions are inert."""
import shutil
from pathlib import Path

# fixture name -> {relative path: exact file text}. The text is byte-identical
# to the file the fixture used to commit, so golden content hashes hold.
GENERATED = {
    "fixture-nextapp": {
        "package.json": (
            '{\n'
            '  "name": "fixture-nextapp",\n'
            '  "private": true,\n'
            '  "version": "0.1.0",\n'
            '  "scripts": {\n'
            '    "dev": "next dev",\n'
            '    "build": "next build",\n'
            '    "start": "next start",\n'
            '    "test": "vitest run",\n'
            '    "observe": "npx tsx .claude/tools/observe.ts"\n'
            '  },\n'
            '  "imports": {\n'
            '    "#lib/*": "./src/lib/*"\n'
            '  },\n'
            '  "dependencies": {\n'
            '    "next": "15.0.0",\n'
            '    "react": "19.0.0",\n'
            '    "react-dom": "19.0.0",\n'
            '    "better-sqlite3": "11.0.0"\n'
            '  },\n'
            '  "devDependencies": {\n'
            '    "tsx": "4.0.0",\n'
            '    "typescript": "5.5.0",\n'
            '    "vitest": "2.0.0",\n'
            '    "@types/react": "19.0.0",\n'
            '    "@types/node": "22.0.0"\n'
            '  }\n'
            '}\n'),
    },
}


def copy_fixture(src: Path, dst: Path) -> Path:
    # A `.kg/` (or legacy `.code-kg/`) left in the fixture by running the
    # engine on it directly is ignored by git, so it is never copied: the
    # sibling config is the only engine state a test starts with.
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".kg", ".code-kg"))
    for rel, text in GENERATED.get(src.name, {}).items():
        # open() rather than write_text(newline=...), which needs Python 3.10+.
        with open(dst / rel, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    cfg = src.parent / f"{src.name}.config.json"
    if cfg.is_file():
        (dst / ".kg").mkdir()
        shutil.copyfile(cfg, dst / ".kg" / "code-kg-config.json")
    return dst
