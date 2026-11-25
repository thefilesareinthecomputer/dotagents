# lib/

Python modules that more than one skill imports, so the shared code exists once.
Today that is `kg_core.py`, the core of the code-kg and markdown-kg engines.

- A module lands here only when two or more skills need the same code. Code one skill uses stays in that skill's `scripts/`.
- A skill that imports from here declares it in its SKILL.md frontmatter: `metadata.ships: repo-lib`, and a `compatibility` line naming the module. The marker matches the imports, and an importer never redefines a name the module exports.
- A skill finds this folder from its own real path (`Path(__file__).resolve().parents[3] / "lib"`) and exits with a message naming the missing module when it is absent.
- A module never takes a stdlib or third-party module's name: importers put `lib/` first on `sys.path`, so it would shadow that module.
- Modules are stdlib only and run on the python3 that stock macOS ships (3.9). A `str | None` annotation needs `from __future__ import annotations`, a 3.10+ keyword such as `Path.write_text(newline=...)` is out, and a 3.11 module such as `tomllib` is imported inside a `try` that degrades.
- Each module has its tests in `tests/`, run with `python3 -m unittest discover -s lib/tests`. The importing skills' suites cover how they use it.
