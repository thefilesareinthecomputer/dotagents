#!/usr/bin/env bash
# sync-skills.sh - assemble ~/.claude as a per-device VIEW of the synced global set (~/.agents):
#   * skills/   : one leaf symlink per skill dir (a dir containing SKILL.md)
#   * agents/   : one leaf symlink per *.md subagent
#   * commands/ : one leaf symlink per *.md slash command
#   ...alongside any device-local real entries you create directly under ~/.claude.
#
# Source of truth = ~/.agents (sync THIS across computers).
# ~/.claude/{skills,agents,commands} are real, per-device dirs (do NOT sync them).
#
# Idempotent and non-destructive to locals:
#   - never clobbers a real local entry that shares a name with a global
#   - refreshes existing global symlinks (in case a target path changed)
#   - prunes dangling symlinks (globals that were removed upstream)
#
# Usage:  bash ~/.agents/sync-skills.sh [--dry-run]
#         bash ~/.agents/sync-skills.sh --cursor <repo> [--dry-run]
#
# --cursor <repo> plants project-level .cursor/agents/ symlinks in that repo for
# the Cursor CLI, which loads subagents ONLY from the project level (user-level
# ~/.cursor/agents and the documented ~/.claude/agents compatibility path do not
# load in the CLI; verified by invocation probes 2026-08-27 on build 2026.08.25).
set -euo pipefail

AGENTS_ROOT="${HOME}/.agents"
CLAUDE_ROOT="${HOME}/.claude"
DRY=""; CURSOR_REPO=""; LINK_ABS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --cursor) shift; CURSOR_REPO="${1:?--cursor needs a repo path}" ;;
    *) echo "usage: sync-skills.sh [--dry-run] [--cursor <repo>]" >&2; exit 2 ;;
  esac
  shift
done

run() { if [ -n "$DRY" ]; then echo "DRY: $*"; else "$@"; fi; }

# Refuse the old parent-level symlink setup (e.g. ~/.claude/skills -> ~/.agents/skills).
assert_real_dir() {
  local d="$1"
  if [ -L "$d" ]; then
    echo "error: $d is a symlink (old parent-level setup)." >&2
    echo "       Convert it first:  rm \"$d\" && mkdir -p \"$d\"" >&2
    echo "       (rm on a symlink removes only the link; the source is untouched.)" >&2
    exit 1
  fi
}

# Prune dangling symlinks (links whose target no longer exists).
prune_dangling() {
  local d="$1"
  [ -d "$d" ] || return 0
  for entry in "$d"/*; do
    [ -e "$entry" ] || [ -L "$entry" ] || continue
    if [ -L "$entry" ] && [ ! -e "$entry" ]; then
      echo "prune dangling : $(basename "$entry")"
      run rm "$entry"
    fi
  done
}

# Resolve the symlink target to write. RELATIVE when the two roots are siblings
# (the normal ~/.agents + ~/.claude layout), so the links carry no absolute path:
# ~/.claude is itself a git repo that tracks these pointers for visibility, and an
# absolute target would bake this machine's home directory into that history and
# clone in dangling on any other. Falls back to absolute if the roots are not
# siblings, where no fixed relative prefix is correct.
rel_target() {
  local src="$1"
  if [ -z "$LINK_ABS" ] && [ "$(dirname "$AGENTS_ROOT")" = "$(dirname "$CLAUDE_ROOT")" ]; then
    printf '../../%s/%s' "$(basename "$AGENTS_ROOT")" "${src#"$AGENTS_ROOT"/}"
  else
    printf '%s' "$src"
  fi
}

# Create/refresh one leaf symlink, never clobbering a real local entry.
link_one() {
  local src="$1" dest="$2" name target
  name="$(basename "$dest")"; target="$(rel_target "$src")"
  if [ -L "$dest" ]; then
    run ln -sfn "$target" "$dest"; echo "link (refresh): $name"
  elif [ -e "$dest" ]; then
    echo "skip local     : $name (real local entry present - keeping yours)"
  else
    run ln -s "$target" "$dest"; echo "link global    : $name"
  fi
}

# Link each global SKILL dir (a dir containing SKILL.md), preserving local overrides.
sync_skill_dirs() {
  local global="$1" local_dir="$2"
  [ -d "$global" ] || { echo "(no $global - skipping)"; return 0; }
  assert_real_dir "$local_dir"
  run mkdir -p "$local_dir"
  prune_dangling "$local_dir"
  for src in "$global"/*/; do
    src="${src%/}"
    [ -f "$src/SKILL.md" ] || continue          # only real skills
    link_one "$src" "$local_dir/$(basename "$src")"
  done
}

# Link each global *.md file (subagents, commands), preserving local overrides.
sync_md_files() {
  local global="$1" local_dir="$2"
  [ -d "$global" ] || { echo "(no $global - skipping)"; return 0; }
  assert_real_dir "$local_dir"
  run mkdir -p "$local_dir"
  prune_dangling "$local_dir"
  for src in "$global"/*.md; do
    [ -f "$src" ] || continue                   # tolerate empty dir
    link_one "$src" "$local_dir/$(basename "$src")"
  done
}

# Plant project-level .cursor/agents/ in one repo for the Cursor CLI. Links are
# absolute (the repo's location and depth are arbitrary, so no fixed relative
# prefix is correct), which means the planted dir must never be committed. The
# repo is not ours: entries git tracks are never touched, pruning is confined
# to our own dangling links (targets inside ~/.agents), and the ignore net is
# ensured BEFORE planting via .git/info/exclude, which is repo-local and never
# committed. Claude-format subagent files load in Cursor as-is.
sync_cursor_project() {
  local repo="$1" top dest entry name src
  top="$(git -C "$repo" rev-parse --show-toplevel 2>/dev/null)" \
    || { echo "error: $repo is not a git repo" >&2; exit 1; }
  repo="$top"
  dest="$repo/.cursor/agents"
  LINK_ABS=1
  assert_real_dir "$repo/.cursor"
  assert_real_dir "$dest"
  if ! git -C "$repo" check-ignore -q .cursor/agents/probe.md 2>/dev/null; then
    if [ -n "$DRY" ]; then
      echo "DRY: append .cursor/agents/ to $repo/.git/info/exclude"
    else
      printf '.cursor/agents/\n' >> "$repo/.git/info/exclude"
      echo "note: added .cursor/agents/ to .git/info/exclude (absolute-path links must never be committed)"
    fi
  fi
  run mkdir -p "$dest"
  for entry in "$dest"/*; do
    [ -L "$entry" ] || continue
    case "$(readlink "$entry")" in "$AGENTS_ROOT"/*) ;; *) continue ;; esac
    [ -e "$entry" ] && continue
    if git -C "$repo" ls-files --error-unmatch -- "${entry#"$repo"/}" >/dev/null 2>&1; then
      continue
    fi
    echo "prune dangling : $(basename "$entry")"
    run rm "$entry"
  done
  for src in "$AGENTS_ROOT"/agents/*.md; do
    [ -f "$src" ] || continue
    name="$(basename "$src")"
    if git -C "$repo" ls-files --error-unmatch -- ".cursor/agents/$name" >/dev/null 2>&1; then
      echo "skip tracked   : $name (committed in the repo - leaving it)"
      continue
    fi
    link_one "$src" "$dest/$name"
  done
}

[ -d "$AGENTS_ROOT/skills" ] || { echo "error: $AGENTS_ROOT/skills not found (is your global set synced here?)" >&2; exit 1; }

if [ -n "$CURSOR_REPO" ]; then
  echo "== cursor project agents ($CURSOR_REPO) =="
  sync_cursor_project "$CURSOR_REPO"
  echo "done. $CURSOR_REPO/.cursor/agents now mixes global symlinks + local real entries."
  exit 0
fi

echo "== skills =="
sync_skill_dirs "$AGENTS_ROOT/skills"   "$CLAUDE_ROOT/skills"
# The skills tree is published, so its folder rules follow it into the view:
# an agent editing through ~/.claude/skills/<name>/ lands in the published repo
# via the symlink, and the rules file is what tells it so. Loose .md files are
# safe here because a skill is a directory with SKILL.md - unlike agents/ and
# commands/, where a loose file registers as a definition, so those two trees
# get no rules files.
for rules in AGENTS.md CLAUDE.md; do
  [ -f "$AGENTS_ROOT/skills/$rules" ] && \
    link_one "$AGENTS_ROOT/skills/$rules" "$CLAUDE_ROOT/skills/$rules"
done
echo "== agents =="
sync_md_files   "$AGENTS_ROOT/agents"   "$CLAUDE_ROOT/agents"
echo "== commands =="
sync_md_files   "$AGENTS_ROOT/commands" "$CLAUDE_ROOT/commands"

echo "done. ~/.claude/{skills,agents,commands} now mix global symlinks + local real entries."
