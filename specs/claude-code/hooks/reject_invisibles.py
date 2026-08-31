#!/usr/bin/env python3
"""PreToolUse hook: reject invisible / non-standard characters in NEW content.

Checks only what the model is writing (Write content, Edit new_string,
MultiEdit edits[].new_string, NotebookEdit new_source). old_string is exempt
by design: matching existing file bytes requires reproducing whatever is
already there.

Allowed whitespace: space, tab, LF, CR. Everything else that renders as
nothing or as a look-alike space is rejected: NBSP, soft hyphen, zero-widths,
bidi controls, BOM, word joiners, line/paragraph separators, exotic Unicode
spaces, variation selectors, interlinear annotation marks, private use.

Exit 2 blocks the tool call and feeds stderr back to the model.
"""
import json
import sys
import unicodedata

ALLOWED_WS = {'\t', '\n', '\r', ' '}
# Codepoint escapes only: literal invisibles in this file would trip the rule
# this hook enforces. Mn oddballs (CGJ, Khmer inherent vowels, Mongolian and
# variation selectors incl. the supplement plane), the blank braille filler,
# Lo Hangul fillers, and Zl/Zp line separators; the Cf/Co/Zs/Cc classes are
# caught by category below.
EXPLICIT = (
    {chr(c) for c in (0x034F, 0x17B4, 0x17B5, 0x115F, 0x1160,
                      0x3164, 0xFFA0, 0x2028, 0x2029, 0x2800)}
    | {chr(c) for c in range(0x180B, 0x180F)}
    | {chr(c) for c in range(0xFE00, 0xFE10)}
    | {chr(c) for c in range(0xE0100, 0xE01F0)}
)


def bad_chars(text):
    hits = {}
    for i, ch in enumerate(text):
        if ch in ALLOWED_WS:
            continue
        cat = unicodedata.category(ch)
        if (ch in EXPLICIT
                or cat in ('Cf', 'Co', 'Cc')
                or (cat == 'Zs' and ch != ' ')):
            hits.setdefault(f'U+{ord(ch):04X}', []).append(i)
    return hits


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    ti = payload.get('tool_input', {}) or {}
    tool = payload.get('tool_name', '')
    if tool == 'Write':
        text = ti.get('content', '')
    elif tool == 'Edit':
        text = ti.get('new_string', '')
    elif tool == 'NotebookEdit':
        text = ti.get('new_source', '')
    elif tool == 'MultiEdit':
        edits = ti.get('edits', [])
        text = '\n'.join(e.get('new_string', '') for e in edits
                         if isinstance(e, dict)) if isinstance(edits, list) else ''
    else:
        return 0
    if not isinstance(text, str):
        return 0
    hits = bad_chars(text)
    if not hits:
        return 0
    detail = '; '.join(
        f'{cp} at offset(s) {", ".join(map(str, pos[:5]))}'
        f'{" ..." if len(pos) > 5 else ""}'
        for cp, pos in sorted(hits.items()))
    print(f'invisible/non-standard characters rejected in new content: '
          f'{detail}. Replace each with a plain space or remove it; '
          f'old_string matching is exempt, new content is not.',
          file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main())
