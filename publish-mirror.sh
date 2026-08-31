#!/usr/bin/env bash
# Copy this repo's published set into a target clone.
#
# The holdback lives HERE, in the exclude list below, not only in the target's
# ignore file. An ignore rule stops a file being committed; it does not stop it
# being written into the target's working tree, where the next person to run
# `git add -f`, to copy the folder, or to grep it will find working state that
# was never meant to leave. Two independent mechanisms, and this is the first.
#
#   ./publish-mirror.sh                         # dry run against the default target
#   ./publish-mirror.sh --apply                 # copy
#   ./publish-mirror.sh <target-dir> --apply --prune
#
# --prune also deletes files in the target that no longer exist here, within the
# copied set only. Without it, a file deleted upstream lingers in the target.
#
# The target is still an argument, so this publishes to any mirror without being
# edited; the default only saves typing the usual one. What it names is a local
# directory, never a remote - this script carries no account, host or URL, so it
# makes no statement about where anything ends up published.

set -euo pipefail

# Working state and machine noise. Every entry is a holdback decision or a
# per-machine artifact; nothing here is ever published.
EXCLUDES=(
  # upstream-only working state
  "tasks/"
  "_RESEARCH/"
  # the target's own identity - never overwritten by a copy
  ".git/"
  ".gitignore"
  # per-device runtime views
  ".claude/"
  ".cursor/"
  "inbox/"
  "settings.local.json"
  "LEARNING/"
  # local build and editor artifacts
  "__archive/"
  "__pycache__/"
  "*.pyc"
  ".venv/"
  ".vscode/"
  ".idea/"
  "node_modules/"
  ".DS_Store"
  "._*"
  "*.log"
  "*.tmp"
  "*.bak"
  # secrets safety net - none of these should exist here, and none may travel
  ".env"
  ".env.*"
  "*.pem"
  "*.key"
  "*.p12"
  "*.pfx"
  "id_rsa*"
  ".envrc"
  "*credentials*"
)

# The second mechanism. These stop anything that reaches the target by a route
# this script cannot see - a manual copy, a stray file - from being committed.
# Only the two upstream working-state trees are required, because those are the
# ones whose absence actually publishes something; the rest of the seeded file is
# belt and braces already covered by EXCLUDES above.
REQUIRED_ANCHORS=("/tasks/" "/_RESEARCH/")

# Written into a target that has none. NOT written over one that exists: a
# target's ignore file is its own, and may carry rules this script knows nothing
# about. That exemption is also why a freshly cloned or rebuilt target arrives
# with no holdback at all, which is the gap this seeding closes.
seed_gitignore() {
  cat > "$1/.gitignore" <<'IGNORE'
# ---------------------------------------------------------------------------
# HOLDBACK ANCHORS - do not remove
#
# This repository is a one-way publication target. The upstream working state
# below is never published, and these entries are the second of two independent
# mechanisms that keep it out: the copy tool has its own exclude list, and these
# rules stop anything that arrives by another route from being committed.
#
# Verify before every publish, from inside this repo:
#   git check-ignore -v tasks/plan.md _RESEARCH/notes.md   # two matches expected
# ---------------------------------------------------------------------------
/tasks/
/_RESEARCH/
/.claude/
/__archive/

# macOS
.DS_Store
._*
.AppleDouble
.Spotlight-V100
.Trashes

# Editors
.vscode/
.idea/
*.swp
*.swo
*~

# Per-device runtime views
inbox/
settings.local.json
LEARNING/

# Build artifacts
__pycache__/
*.py[cod]
.venv/
node_modules/

# Databases built per-corpus, never committed
**/vault-kg/vault-kg.db
**/vault-kg/vault-kg.db-*
**/.code-kg/code-kg.db
**/.code-kg/code-kg.db-*
**/.code-kg/coverage-tmp.json

# Logs / temp / backups
*.log
*.tmp
*.bak

# Keys and credentials - never commit, in any repo
.env
.env.*
*.local
*.pem
*.key
*.p12
*.pfx
id_rsa*
.envrc
*credentials*
IGNORE
}

# Where the public mirror lives when no target is given. A mirror is a long-lived
# sibling of this repo rather than a one-off destination, so naming the usual one
# saves repeating it, and PUBLISH_MIRROR_TARGET overrides it on a station whose
# layout differs. An explicit argument still wins over both, which is what keeps
# this usable for a second mirror without editing anything.
DEFAULT_TARGET="${PUBLISH_MIRROR_TARGET:-$HOME/dev/dotagents-mirror}"

usage() {
  echo "usage: $0 [target-dir] [--apply] [--prune]" >&2
  echo "       target defaults to \$PUBLISH_MIRROR_TARGET, else $DEFAULT_TARGET" >&2
  exit 2
}

TARGET=""
APPLY=0
PRUNE=0
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    --prune) PRUNE=1 ;;
    -h|--help) usage ;;
    -*) echo "unknown flag: $arg" >&2; usage ;;
    *)
      [ -z "$TARGET" ] || { echo "only one target may be given" >&2; usage; }
      TARGET="$arg"
      ;;
  esac
done
[ -n "$TARGET" ] || TARGET="$DEFAULT_TARGET"

SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The source must be this repo, so a stray invocation from elsewhere cannot
# publish an unrelated directory.
[ -d "$SOURCE/skills" ] && [ -f "$SOURCE/AGENTS.md" ] || {
  echo "error: $SOURCE does not look like this repo (no skills/ and AGENTS.md)" >&2
  exit 1
}

[ -d "$TARGET" ] || { echo "error: target does not exist: $TARGET" >&2; exit 1; }
TARGET="$(cd "$TARGET" && pwd)"

[ "$SOURCE" != "$TARGET" ] || { echo "error: target is the source" >&2; exit 1; }

# The target must be a git repo: git is what makes a bad copy recoverable.
git -C "$TARGET" rev-parse --git-dir >/dev/null 2>&1 || {
  echo "error: target is not a git repository: $TARGET" >&2
  exit 1
}

# A dirty target means a copy would bury changes that are not committed anywhere.
# A repo with no commits at all is the exception: everything in it is untracked by
# definition, so the guard would refuse exactly the rebuild case it is not meant to
# catch, and there is no history for a copy to bury.
if git -C "$TARGET" rev-parse --verify --quiet HEAD >/dev/null 2>&1; then
  if [ -n "$(git -C "$TARGET" status --porcelain)" ]; then
    echo "error: target has uncommitted changes - commit or discard them first:" >&2
    git -C "$TARGET" status --short >&2
    exit 1
  fi
else
  echo "note: target has no commits yet - treating it as a fresh mirror"
fi

# Seed or verify the holdback BEFORE copying, so a target without a live net is
# never written into. Seeding happens only under --apply; a dry run says what it
# would do and changes nothing.
if [ ! -f "$TARGET/.gitignore" ]; then
  if [ "$APPLY" -eq 1 ]; then
    seed_gitignore "$TARGET"
    echo "seeded $TARGET/.gitignore - a target with no ignore file has no holdback"
  else
    echo "would seed $TARGET/.gitignore - the target has none, so it has no holdback"
  fi
fi

if [ -f "$TARGET/.gitignore" ]; then
  missing=()
  for anchor in "${REQUIRED_ANCHORS[@]}"; do
    grep -qxF "$anchor" "$TARGET/.gitignore" || missing+=("$anchor")
  done
  if [ ${#missing[@]} -gt 0 ]; then
    echo "error: target's .gitignore is missing holdback anchors: ${missing[*]}" >&2
    echo "       Without them, working state that reaches the target by any route" >&2
    echo "       this script cannot see becomes committable. Add each on its own" >&2
    echo "       line to $TARGET/.gitignore, then re-run." >&2
    exit 1
  fi
fi

RSYNC_ARGS=(-a --itemize-changes)
for pattern in "${EXCLUDES[@]}"; do
  RSYNC_ARGS+=(--exclude="$pattern")
done
[ "$PRUNE" -eq 1 ] && RSYNC_ARGS+=(--delete)
[ "$APPLY" -eq 1 ] || RSYNC_ARGS+=(--dry-run)

echo "source: $SOURCE"
echo "target: $TARGET"
echo "mode:   $([ "$APPLY" -eq 1 ] && echo apply || echo "DRY RUN") $([ "$PRUNE" -eq 1 ] && echo "+ prune" || true)"
echo

rsync "${RSYNC_ARGS[@]}" "$SOURCE/" "$TARGET/"

echo
if [ "$APPLY" -eq 1 ]; then
  echo "copied. Verify before committing in the target:"
  echo "  git -C \"$TARGET\" status --short"
  echo "  git -C \"$TARGET\" diff --cached --name-only | grep -E '^(tasks|_RESEARCH)/'   # must be empty"
else
  echo "dry run only. Re-run with --apply to copy."
fi
