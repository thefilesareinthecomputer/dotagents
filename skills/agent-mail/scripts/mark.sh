#!/usr/bin/env bash
# mark.sh - update a delivered message's status (atomic) and, when it is
# resolved/canceled, move it into a flat <inbox>/processed/.
#
#   --file PATH     the message file (in an inbox/ or inbox/processed/)
#   --status S      unread | in-progress | resolved | canceled
#
# Status is rewritten only inside the YAML front matter, via awk → temp → mv
# (atomic). A file with no parseable front-matter status surfaces an error -
# there is no sidecar.
set -euo pipefail
SELF_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=lib.sh
source "$SELF_DIR/lib.sh"

file="" status=""
while [ $# -gt 0 ]; do
  case "$1" in
    --file)   file="$2"; shift 2;;
    --status) status="$2"; shift 2;;
    *) am_die 64 BAD_ARG "unknown argument: $1";;
  esac
done

[ -n "$file" ] && [ -f "$file" ] || am_die 2 FILE_NOT_FOUND "no such message: $file"
case "$status" in
  unread|in-progress|resolved|canceled) ;;
  *) am_die 64 BAD_ARG "bad --status: $status (unread|in-progress|resolved|canceled)";;
esac

dir=$(cd "$(dirname "$file")" && pwd -P)
base=$(basename "$file")

# Atomic front-matter rewrite; exit 3 if no status line within the front matter.
tmp=$(mktemp "$dir/.tmp.XXXXXX")
trap 'rm -f "$tmp"' EXIT
if ! awk -v st="$status" '
      NR==1 && $0=="---" {infm=1; print; next}
      infm && $0=="---" {infm=0; print; next}
      infm && /^status:[[:space:]]/ && !done {print "status: " st; done=1; next}
      {print}
      END { if (!done) exit 3 }
    ' "$file" > "$tmp"; then
  am_die 5 MALFORMED "no status field in front matter of $file - not a valid agent-mail message"
fi
mv "$tmp" "$file"; trap - EXIT

# Resolved/canceled → move into flat processed/ (unless already there).
if [ "$status" = resolved ] || [ "$status" = canceled ]; then
  if [ "$(basename "$dir")" != processed ]; then
    proc="$dir/processed"; mkdir -p "$proc"
    mv "$file" "$proc/$base"
    printf '%s\n' "$proc/$base"
    exit 0
  fi
fi
printf '%s\n' "$file"
