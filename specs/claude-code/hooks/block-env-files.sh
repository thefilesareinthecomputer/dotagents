#!/usr/bin/env bash
# PreToolUse guard: blocks Read/Edit/Write/Bash/Grep/Glob from touching .env files.
#
# .env files routinely hold secrets (API keys, DB creds, tokens). This hook denies
# the tool call and hands the model a clear instruction to STOP and talk to the user
# instead of working around the block. The conventional non-secret variants
# (.env.example, .env.sample, .env.template, .env.dist, .env.defaults) are allowed.
#
# Companion to the permissions.deny rules in settings.json. The deny rules are the
# declarative first line; this hook adds the Bash coverage (deny rules can't pattern
# match arbitrary shell commands) and the human-readable "ask the user" guidance.

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
for word in $cleaned; do
  b=$(basename "$word" 2>/dev/null) || continue
  case "$b" in
    .env|.env.*)
      case "$b" in
        .env.example|.env.sample|.env.template|.env.dist|.env.defaults|.env.example.*) ;;
        *) is_blocked=1; hit="$b" ;;
      esac
      ;;
  esac
done

if [ "$is_blocked" -eq 1 ]; then
  reason="Blocked: this ${tool} call targets a protected .env file (${hit}), which may hold secrets (API keys, credentials, tokens). Do NOT retry via another tool or shell trick. Stop and talk to the user: (1) if you need a specific config value, ask them to paste just that value; (2) if they genuinely want you to read or modify the .env file, ask them to confirm so they can approve it explicitly; (3) if you only need variable names/shape, suggest a committed .env.example instead. Surface this to the user rather than working around it."
  jq -n --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  exit 0
fi

exit 0
