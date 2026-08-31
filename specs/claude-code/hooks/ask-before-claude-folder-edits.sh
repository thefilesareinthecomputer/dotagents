#!/usr/bin/env bash
# PreToolUse guard: forces an "ask" permission prompt before any file-modifying
# tool (Write/Edit/MultiEdit/NotebookEdit) touches a file inside the global
# ~/.claude config folder.
#
# This folder holds settings.json, hooks, statusline, CLAUDE.md, skills, and
# other config that silently changes how every session behaves. An accidental
# edit here has blast radius far beyond the one file. This hook does NOT block;
# it routes the call to a confirmation prompt so the user can review first.
#
# The hook only enforces the prompt. Stating the intended change and its
# implications (to this file and nearby files: imports, refs, paths, deps) is
# the agent's job and is requested in the reason text below.
#
# Companion to block-env-files.sh. Files OUTSIDE ~/.claude are untouched (exit 0
# = no decision = normal permission flow).

input=$(cat)
tool=$(printf '%s' "$input" | jq -r '.tool_name // ""')

# Update/Create are the terminal UI labels for Edit/Write; matched here so a
# future harness rename toward those names keeps the guard live (see the
# "Right Tool for File Operations" rule in the global CLAUDE.md).
case "$tool" in
  Write|Edit|MultiEdit|NotebookEdit|Update|Create) ;;
  *) exit 0 ;;
esac

path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.notebook_path // ""')
[ -z "$path" ] && exit 0

cwd=$(printf '%s' "$input" | jq -r '.cwd // ""')

# Expand a leading ~ and resolve relative paths against the tool's cwd so the
# prefix check sees an absolute path.
case "$path" in
  "~"|"~/"*) path="${HOME}${path#\~}" ;;
esac
case "$path" in
  /*) ;;
  *) [ -n "$cwd" ] && path="${cwd%/}/${path}" ;;
esac

# Collapse . and .. LEXICALLY so a traversal path can't slip past the prefix
# check (~/Documents/../.claude/settings.json must normalize to
# ~/.claude/settings.json). normpath, NOT realpath - resolving symlinks would
# DROP protection for files reached through a link inside ~/.claude (e.g.
# ~/.claude/skills → ~/.agents/skills), whereas we want any ~/.claude/* path
# guarded. Relies on python3 (a §2 station dep); if absent, falls through to
# the raw prefix check (an ask guard, not a hard boundary).
if command -v python3 >/dev/null 2>&1; then
  norm=$(python3 -c 'import os,sys; print(os.path.normpath(sys.argv[1]))' "$path" 2>/dev/null)
  [ -n "$norm" ] && path="$norm"
fi

target="${HOME}/.claude"

case "$path" in
  "$target"|"$target"/*)
    reason="This ${tool} targets a file inside the global ~/.claude config folder (${path}), which controls how every Claude Code session behaves - a change here can ripple well beyond this one file. Before approving, the agent should have stated: (1) the exact intended change, and (2) its implications to this file and any files 'near' it - imports, references, file paths, deps, and other hooks/settings that read it. If that wasn't made clear, deny and ask for it."
    jq -n --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"ask",permissionDecisionReason:$r}}'
    exit 0
    ;;
esac

exit 0
