#!/usr/bin/env bash
# inbox.sh - list this repo's unread mail (top-level <root>/inbox/*.md).
#
#   --repo PATH   repo to inspect (default: .)
#   --root NAME   agent root to use (required only if the repo has >1)
#   --all         also list processed/ messages
#
# Prints one line per message: STATUS  message-id  from→to  subject
set -euo pipefail
SELF_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=lib.sh
source "$SELF_DIR/lib.sh"

repo="." root="" all=""
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) repo="$2"; shift 2;;
    --root) root="$2"; shift 2;;
    --all)  all=1; shift;;
    *) am_die 64 BAD_ARG "unknown argument: $1";;
  esac
done

repo=$(am_canon "$repo") || am_die 2 REPO_NOT_FOUND "no such repo"
found=()
while IFS= read -r _r; do [ -n "$_r" ] && found+=("$_r"); done < <(am_detect_roots "$repo")
if [ -n "$root" ]; then
  [ -d "$repo/$root" ] || am_die 8 ROOT_NOT_PRESENT "--root $root not present"
elif [ "${#found[@]}" -eq 1 ]; then
  root="${found[0]}"
elif [ "${#found[@]}" -eq 0 ]; then
  am_die 6 NOT_AGENT_REPO "no agent root in $repo"
else
  am_die 7 AMBIGUOUS_ROOT "multiple roots (${found[*]}) - pass --root"
fi

inbox="$repo/$root/inbox"
[ -d "$inbox" ] || { echo "(no inbox at $root/inbox - no mail)"; exit 0; }

# field VALUE from a file's front matter
field() { awk -v k="$1" 'NR==1&&$0=="---"{f=1;next} f&&$0=="---"{exit}
                          f&&$0 ~ "^"k":"{sub("^"k":[ ]*","");gsub(/^"|"$/,"");print;exit}' "$2"; }

list() {
  local f st mid frm to subj n=0
  shopt -s nullglob
  for f in "$1"/*.md; do
    [ "$(basename "$f")" = HOW-TO-AGENT-MAIL.md ] && continue
    n=$((n+1))
    st=$(field status "$f"); mid=$(field message-id "$f")
    frm=$(field from "$f"); to=$(field to "$f"); subj=$(field subject "$f")
    printf '%-12s %s  %s→%s  %s\n' "${st:-?}" "${mid:-?}" "${frm:-?}" "${to:-?}" "${subj:-?}"
  done
  shopt -u nullglob
  return "$n"
}

echo "# unread (${root}/inbox)"
list "$inbox" || true
if [ -n "$all" ] && [ -d "$inbox/processed" ]; then
  echo "# processed"
  list "$inbox/processed" || true
fi
