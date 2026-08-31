#!/usr/bin/env bash
# sweep.sh - closing audit of this repo's inbox. Buckets every top-level message
# by what it still owes, so nothing rots unread or half-processed.
#
#   --repo PATH       repo to audit (default: .)
#   --root NAME       agent root to use (required only if the repo has >1)
#   --stale-days N    age at which an outstanding message is called stale (default 7)
#   --fix-stranded    move already-resolved/canceled top-level files into processed/
#
# Buckets, in the order they are printed:
#   OWES-REPLY  reply-needed: true and not closed  -> send the response, then mark
#   TRIAGE      unread, or no status at all        -> read it and act
#   ABANDONED   left in-progress                   -> finish it or mark canceled
#   STRANDED    closed but never moved             -> mechanical; --fix-stranded
#
# Exit 0 when the inbox is clean, 1 when anything is outstanding.
set -euo pipefail
SELF_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=lib.sh
source "$SELF_DIR/lib.sh"

repo="." root="" stale_days=7 fix=""
while [ $# -gt 0 ]; do
  case "$1" in
    --repo)        repo="$2"; shift 2;;
    --root)        root="$2"; shift 2;;
    --stale-days)  stale_days="$2"; shift 2;;
    --fix-stranded) fix=1; shift;;
    *) am_die 64 BAD_ARG "unknown argument: $1";;
  esac
done
case "$stale_days" in ''|*[!0-9]*) am_die 64 BAD_ARG "--stale-days must be a number";; esac

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
[ -d "$inbox" ] || { echo "(no inbox at $root/inbox - nothing to sweep)"; exit 0; }

# field VALUE from a file's front matter
field() { awk -v k="$1" 'NR==1&&$0=="---"{f=1;next} f&&$0=="---"{exit}
                          f&&$0 ~ "^"k":"{sub("^"k":[ ]*","");gsub(/^"|"$/,"");print;exit}' "$2"; }

# YYYYMMDD cutoff for staleness (BSD first, GNU fallback).
cutoff=$(date -u -v-"${stale_days}"d +%Y%m%d 2>/dev/null \
      || date -u -d "${stale_days} days ago" +%Y%m%d 2>/dev/null || echo 00000000)

owes=() triage=() abandoned=() stranded=()

shopt -s nullglob
for f in "$inbox"/*.md; do
  [ "$(basename "$f")" = HOW-TO-AGENT-MAIL.md ] && continue
  st=$(field status "$f"); rn=$(field reply-needed "$f")
  mid=$(field message-id "$f"); frm=$(field from "$f"); subj=$(field subject "$f")
  day=$(field date "$f"); day=${day:0:10}; day=${day//-/}
  case "$day" in ''|*[!0-9]*) day=00000000;; esac
  age=""; [ "$day" -lt "$cutoff" ] && age=" STALE(${day:0:4}-${day:4:2}-${day:6:2})"
  line=$(printf '%s  %s  %s%s' "${mid:-?}" "${frm:-?}" "${subj:-?}" "$age")

  case "$st" in
    resolved|canceled) stranded+=("$line|$f");;
    in-progress)       abandoned+=("$line");;
    *) if [ "$rn" = true ]; then owes+=("$line"); else triage+=("$line"); fi;;
  esac
done
shopt -u nullglob

show() {
  local label="$1" hint="$2"; shift 2
  [ "$#" -eq 0 ] && return 0
  printf '\n%s (%d) - %s\n' "$label" "$#" "$hint"
  local e; for e in "$@"; do printf '  %s\n' "${e%%|*}"; done
}

echo "# sweep (${root}/inbox)"
show OWES-REPLY "send the response, then mark resolved" ${owes+"${owes[@]}"}
show TRIAGE     "read it and act, then mark resolved"   ${triage+"${triage[@]}"}
show ABANDONED  "finish it, or mark canceled"           ${abandoned+"${abandoned[@]}"}
show STRANDED   "closed but never moved - rerun with --fix-stranded" ${stranded+"${stranded[@]}"}

if [ -n "$fix" ] && [ "${#stranded[@]}" -gt 0 ]; then
  printf '\n# fixing stranded\n'
  for e in "${stranded[@]}"; do
    f="${e#*|}"
    bash "$SELF_DIR/mark.sh" --file "$f" --status "$(field status "$f")"
  done
  stranded=()
fi

outstanding=$(( ${#owes[@]} + ${#triage[@]} + ${#abandoned[@]} + ${#stranded[@]} ))
if [ "$outstanding" -eq 0 ]; then
  printf '\nclean - nothing outstanding.\n'; exit 0
fi
printf '\n%d outstanding. The inbox is not clean.\n' "$outstanding"
exit 1
