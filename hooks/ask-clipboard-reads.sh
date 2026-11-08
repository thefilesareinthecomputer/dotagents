#!/usr/bin/env bash
# PreToolUse guard: asks before a Bash command reads the clipboard.
#
# The clipboard often holds whatever the user copied last: a password from a
# password manager, a token, a private message. An agent that runs pbpaste, or
# AppleScript's `the clipboard`, reads it without the user knowing. A command whose
# text names a clipboard reader raises a permission prompt rather than a denial,
# because the text may be a commit message, a grep pattern or a string literal
# rather than a read: the user approves a mention and denies a read. Writing the
# clipboard (pbcopy) is silent.
#
# Matches by text, so it catches the plain routes and not a deliberately hidden
# one. macOS's own control is System Settings > Privacy & Security > Paste from
# Other Apps, set per app, which covers every program a terminal starts.
# Needs jq; a missing jq denies the call instead of allowing it (see _require.sh).

. "$(dirname "$0")/_require.sh" 2>/dev/null || { printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"hook preamble missing: _require.sh. This guard cannot evaluate the call, so it refuses."}}\n'; exit 0; }
require_deps jq

input=$(cat)
tool=$(printf '%s' "$input" | jq -r '.tool_name // ""' 2>/dev/null)
[ "$tool" = "Bash" ] || exit 0

# macOS (pbpaste, AppleScript, AppKit), Python and Node libraries, Linux and Windows readers.
readers='\bpbpaste\b|\bthe clipboard\b|\bclipboard info\b|NSPasteboard|\bpyperclip\b|\bclipboardy\b|\bxclip\b|\bxsel\b|\bwl-paste\b|Get-Clipboard'
hit=$(printf '%s' "$input" | jq -r '.tool_input.command // ""' | grep -Eio "$readers" | head -n 1)
[ -n "$hit" ] || exit 0

reason="This Bash command reads the clipboard (${hit}), which may hold a password or token you copied. Approve only if you expect the agent to read what you copied; a mention in a commit message, pattern or string literal is fine. If the agent needs something from the clipboard, deny and paste just that text into the chat."
jq -n --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"ask",permissionDecisionReason:$r}}'
exit 0
