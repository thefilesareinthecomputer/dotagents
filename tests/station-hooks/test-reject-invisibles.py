#!/usr/bin/env python3
"""Tests for the reject_invisibles.py PreToolUse hook.
Target: ~/.claude/hooks/reject_invisibles.py (seeded from SPEC-CLAUDE-CODE.md §8).
Run: python3 tests/station-hooks/test-reject-invisibles.py

Contract: invisible/non-standard characters in NEW content (Write content,
Edit new_string, MultiEdit edits[].new_string, NotebookEdit new_source) exit 2
with the codepoints on stderr; old_string is exempt; other tools, clean
content, and malformed stdin exit 0. Invisibles here are built from chr()
codepoints so this file itself stays clean under the very rule it tests.
"""

import json
import subprocess
import sys
from pathlib import Path

HOOK = Path.home() / ".claude" / "hooks" / "reject_invisibles.py"

ZWSP = chr(0x200B)   # zero width space (Cf)
NBSP = chr(0x00A0)   # no-break space (Zs)
BOM = chr(0xFEFF)    # byte order mark / zero width no-break (Cf)
RLO = chr(0x202E)    # right-to-left override (Cf, bidi)
SHY = chr(0x00AD)    # soft hyphen (Cf)
VS16 = chr(0xFE0F)   # variation selector-16 (explicit set)
HFILL = chr(0x3164)  # hangul filler (explicit set)
LSEP = chr(0x2028)   # line separator (Zl, explicit set)
EMSP = chr(0x2003)   # em space (Zs)
PUA = chr(0xE000)    # private use area (Co)
CGJ = chr(0x034F)    # combining grapheme joiner (explicit set)
ZWJ = chr(0x200D)    # zero width joiner (Cf)
VSS = chr(0xE0100)   # variation selector supplement (Mn, explicit set)
BRB = chr(0x2800)    # braille pattern blank (So, explicit set)

CASES = [
    # (name, payload-or-raw-stdin, expected exit)
    ("clean write", {"tool_name": "Write", "tool_input": {"content": "plain text\nwith tabs\tand CR\r\n"}}, 0),
    ("write zwsp", {"tool_name": "Write", "tool_input": {"content": "a" + ZWSP + "b"}}, 2),
    ("write nbsp", {"tool_name": "Write", "tool_input": {"content": "a" + NBSP + "b"}}, 2),
    ("write bom", {"tool_name": "Write", "tool_input": {"content": BOM + "hello"}}, 2),
    ("write bidi rlo", {"tool_name": "Write", "tool_input": {"content": "x" + RLO + "y"}}, 2),
    ("write soft hyphen", {"tool_name": "Write", "tool_input": {"content": "co" + SHY + "op"}}, 2),
    ("write variation selector", {"tool_name": "Write", "tool_input": {"content": "a" + VS16 + "b"}}, 2),
    ("write variation selector supplement", {"tool_name": "Write", "tool_input": {"content": "a" + VSS + "b"}}, 2),
    ("write braille blank", {"tool_name": "Write", "tool_input": {"content": "a" + BRB + "b"}}, 2),
    ("write hangul filler", {"tool_name": "Write", "tool_input": {"content": "a" + HFILL + "b"}}, 2),
    ("write line sep", {"tool_name": "Write", "tool_input": {"content": "a" + LSEP + "b"}}, 2),
    ("write em space", {"tool_name": "Write", "tool_input": {"content": "a" + EMSP + "b"}}, 2),
    ("write private use", {"tool_name": "Write", "tool_input": {"content": "a" + PUA + "b"}}, 2),
    ("write cgj", {"tool_name": "Write", "tool_input": {"content": "a" + CGJ + "b"}}, 2),
    ("edit dirty old_string exempt", {"tool_name": "Edit", "tool_input": {"old_string": "x" + ZWSP + "x", "new_string": "clean"}}, 0),
    ("edit dirty new_string", {"tool_name": "Edit", "tool_input": {"old_string": "x", "new_string": "z" + ZWJ + "w"}}, 2),
    ("notebook dirty", {"tool_name": "NotebookEdit", "tool_input": {"new_source": "a" + ZWSP + "b"}}, 2),
    ("multiedit dirty second edit", {"tool_name": "MultiEdit", "tool_input": {"edits": [
        {"old_string": "a", "new_string": "clean"},
        {"old_string": "b", "new_string": "z" + ZWSP + "w"}]}}, 2),
    ("multiedit dirty old_string exempt", {"tool_name": "MultiEdit", "tool_input": {"edits": [
        {"old_string": "a" + ZWSP + "a", "new_string": "clean"}]}}, 0),
    ("other tool ignored", {"tool_name": "Bash", "tool_input": {"command": "echo a" + ZWSP + "b"}}, 0),
    ("multibyte prose passes", {"tool_name": "Write", "tool_input": {"content": "cafe naive Chinese text passes"}}, 0),
    ("malformed stdin fails open", "not json", 0),
]


def run(payload) -> tuple[int, str]:
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    p = subprocess.run([sys.executable, str(HOOK)], input=stdin, capture_output=True, text=True)
    return p.returncode, p.stderr


def main() -> int:
    fails = 0
    for name, payload, want in CASES:
        code, err = run(payload)
        ok = code == want
        if code == 2 and "invisible" not in err:
            ok = False
        if not ok:
            fails += 1
        print(f"{'PASS' if ok else 'FAIL'}  {name}: exit {code} (want {want})")
    print(f"\n{len(CASES) - fails}/{len(CASES)} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
