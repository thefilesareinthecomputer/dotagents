#!/usr/bin/env bash
# PreToolUse guard: keeps Read/Edit/Write/Grep/Glob and Bash away from .env files.
#
# .env files routinely hold secrets (API keys, DB creds, tokens). A file tool that
# names one is denied, with a clear instruction to STOP and talk to the user instead
# of working around the block. A Bash command that mentions one raises a permission
# prompt instead, because the text may be a commit message, a grep pattern or a
# string literal rather than an access: the user approves a mention and denies a
# read. The conventional non-secret variants (.env.example, .env.sample,
# .env.template, .env.dist, .env.defaults) are allowed everywhere.
#
# Companion to the permissions.deny rules in settings.json. The deny rules are the
# declarative first line; this hook adds the Bash coverage (deny rules can't pattern
# match arbitrary shell commands) and the human-readable "ask the user" guidance.
# Needs jq; a missing jq denies the call instead of allowing it (see _require.sh).

. "$(dirname "$0")/_require.sh" 2>/dev/null || { printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"hook preamble missing: _require.sh. This guard cannot evaluate the call, so it refuses."}}\n'; exit 0; }
require_deps jq

input=$(cat)
tool=$(printf '%s' "$input" | jq -r '.tool_name // ""')

# Collect candidate path-ish tokens based on which tool fired.
# Update/Create are the terminal UI labels for Edit/Write - matched so the
# guard survives a future harness rename toward those names.
case "$tool" in
  Read|Edit|Write|MultiEdit|NotebookEdit|Update|Create)
    candidates=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.notebook_path // ""')
    ;;
  Glob)
    candidates=$(printf '%s' "$input" | jq -r '[.tool_input.path // "", .tool_input.pattern // ""] | join(" ")')
    ;;
  Grep)
    candidates=$(printf '%s' "$input" | jq -r '[.tool_input.path // "", .tool_input.glob // "", .tool_input.pattern // ""] | join(" ")')
    ;;
  Bash)
    candidates=$(printf '%s' "$input" | jq -r '.tool_input.command // ""')
    ;;
  *)
    exit 0
    ;;
esac

# Strip quotes, then split on whitespace and common shell separators so each
# path-ish token can be basename-checked. basename keeps ".environment" etc. from
# matching, since only ".env" and ".env.<suffix>" basenames trip the guard.
cleaned=$(printf '%s' "$candidates" | tr -d "\"'" | tr '=|;:,()&<>' ' ')

is_blocked=0
hit=""
# set -f keeps a glob token such as .env* literal instead of expanding it against
# the hook's own working directory; a glob over dotenv files is a hit too.
set -f
for word in $cleaned; do
  b=$(basename "$word" 2>/dev/null) || continue
  case "$b" in
    .env|.env.*|.env[*?[]*)
      case "$b" in
        .env.example|.env.sample|.env.template|.env.dist|.env.defaults|.env.example.*) ;;
        *) is_blocked=1; hit="$b" ;;
      esac
      ;;
  esac
done
set +f

if [ "$is_blocked" -eq 1 ]; then
  # A file tool names its target exactly, so a hit is a real access: deny.
  # A Bash command only mentions the token somewhere in its text - a commit
  # message, a grep pattern, a string literal - so the user decides: ask.
  if [ "$tool" = "Bash" ]; then
    reason="This Bash command mentions a protected .env file (${hit}), which may hold secrets. Approve only if the command does not read, copy or print its contents; a mention in a commit message, pattern or string literal is fine. If the agent needs a value from it, deny and have it ask you for just that value."
    jq -n --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"ask",permissionDecisionReason:$r}}'
    exit 0
  fi
  reason="Blocked: this ${tool} call targets a protected .env file (${hit}), which may hold secrets (API keys, credentials, tokens). Do NOT retry via another tool or shell trick. Stop and talk to the user: (1) if you need a specific config value, ask them to paste just that value; (2) if they genuinely want you to read or modify the .env file, ask them to confirm so they can approve it explicitly; (3) if you only need variable names/shape, suggest a committed .env.example instead. Surface this to the user rather than working around it."
  jq -n --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  exit 0
fi

exit 0
