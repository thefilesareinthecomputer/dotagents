#!/usr/bin/env python3
"""PostToolUse(Write|Edit) check for skill descriptions.

Fires after a write whose path is a SKILL.md and checks that file's frontmatter
description with skill-authoring's check_descriptions.py, so the rule lives in
one place: at most 800 characters (the house cap, inside the standard's 1024),
and no ': ' in a plain scalar. Both pass Claude Code silently and break stricter
harnesses, which is why an agent editing a skill never notices on its own.

A violation exits 2, which returns stderr to the agent so it is fixed now.
Footgun, verified: exit 1 is swallowed silently, so failures use 2.

Paths with a `tests` or `fixtures` component are skipped, because test fixtures
carry deliberately invalid skills. The checker is found at
~/.claude/skills/skill-authoring/scripts/check_descriptions.py, or at the path in
SKILL_DESCRIPTION_CHECKER. Stdlib only, no network. Fails OPEN: a missing checker
or any error in this hook exits 0, so a hook bug never blocks a write.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path


def checker_path() -> Path:
    override = os.environ.get("SKILL_DESCRIPTION_CHECKER")
    if override:
        return Path(override)
    return Path.home() / ".claude" / "skills" / "skill-authoring" / "scripts" / "check_descriptions.py"


def load_checker(path: Path):
    spec = importlib.util.spec_from_file_location("check_descriptions", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve the module through sys.modules
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    fp = (payload.get("tool_input") or {}).get("file_path", "")
    if not fp:
        return 0
    path = Path(fp)
    if path.name != "SKILL.md" or {"tests", "fixtures"} & set(path.parts) or not path.is_file():
        return 0

    checker = checker_path()
    if not checker.is_file():
        return 0
    cd = load_checker(checker)
    desc = cd.parse_description(path.read_text(encoding="utf-8", errors="replace"))
    found = cd.problems(desc)
    if not found:
        return 0

    length = len(desc.text) if desc.text is not None else 0
    print(
        f"skill-description [FAIL]: {path} - description is {length} characters; "
        f"{'; '.join(found)}. Trim it without dropping its trigger clauses, then confirm "
        f"with: python3 {checker} {path}",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # fail-open: a hook bug must never block a skill write
