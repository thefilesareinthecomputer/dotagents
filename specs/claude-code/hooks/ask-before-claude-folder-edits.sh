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
# Needs jq (payload parsing) and python3 (path normalization). A missing
# dependency denies the call instead of allowing it; see _require.sh.

. "$(dirname "$0")/_require.sh" 2>/dev/null || { printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"hook preamble missing: _require.sh. This guard cannot evaluate the call, so it refuses."}}\n'; exit 0; }
require_deps jq python3

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
# guarded. python3 is required above, so the normalized path is always used.
norm=$(python3 -c 'import os,sys; print(os.path.normpath(sys.argv[1]))' "$path" 2>/dev/null)
[ -n "$norm" ] && path="$norm"

target="${HOME}/.claude"

case "$path" in
  "$target"|"$target"/*)
    # A second-brain seat (BRAIN_SEAT in its env) is headless: an ask
    # would be a silent deny nobody can attribute. Deny with a prefix the
    # spawner parses; global config changes are the user's own turn.
    if [ -n "${BRAIN_SEAT:-}" ]; then
      reason="brain-gate: claude-folder: seat ${BRAIN_SEAT} may not modify ${path} inside the global ~/.claude config folder; a headless seat cannot answer the prompt this would raise. The user changes global config in their own turn."
      jq -n --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
      exit 0
    fi
    reason="This ${tool} targets a file inside the global ~/.claude config folder (${path}), which controls how every Claude Code session behaves - a change here can ripple well beyond this one file. Before approving, the agent should have stated: (1) the exact intended change, and (2) its implications to this file and any files 'near' it - imports, references, file paths, deps, and other hooks/settings that read it. If that wasn't made clear, deny and ask for it."
    jq -n --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"ask",permissionDecisionReason:$r}}'
    exit 0
    ;;
  */.claude/settings.json|*/.claude/settings.local.json)
    # A repo's own permission file. A repo-wide Edit allow would otherwise
    # let a session grant itself more, so the prompt is raised here; a seat
    # is denied outright with the same parseable prefix as above.
    if [ -n "${BRAIN_SEAT:-}" ]; then
      reason="brain-gate: claude-folder: seat ${BRAIN_SEAT} may not modify ${path}; permission files change only in the user's own turn."
      jq -n --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
      exit 0
    fi
    reason="This ${tool} targets a repository permission file (${path}). A change here widens or narrows what every session in that repo may do without asking, including headless seats. Approve only if the agent has stated the exact rule being added or removed and why the rule is as narrow as the workflow permits."
    jq -n --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"ask",permissionDecisionReason:$r}}'
    exit 0
    ;;
esac

exit 0
