#!/usr/bin/env bash
# send.sh - deliver one markdown message into a peer repo's <agent-root>/inbox/.
#
# Guard flow (writes NOTHING until all checks pass):
#   repo missing            -> REPO_NOT_FOUND   (2)
#   no recognized root       -> NOT_AGENT_REPO   (6)   .claude/.agents/.cursor
#   >1 root, no --root       -> AMBIGUOUS_ROOT   (7)   + report
#   --root names absent dir  -> ROOT_NOT_PRESENT (8)
#   root present, no inbox/   -> NO_INBOX         (4)   unless --create-inbox
#   ok                        -> exit 0, prints written path
set -euo pipefail
SELF_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=lib.sh
source "$SELF_DIR/lib.sh"
TPL_DIR=$(cd "$SELF_DIR/../templates" && pwd -P)

to_repo="" from_repo="$PWD" from="" to="" subject="" type="fyi"
in_reply_to="" reply_needed="false" body_file="" root="" create_inbox="" inspect=""

while [ $# -gt 0 ]; do
  case "$1" in
    --to-repo)      to_repo="$2"; shift 2;;
    --from)         from="$2"; shift 2;;
    --from-repo)    from_repo="$2"; shift 2;;
    --to)           to="$2"; shift 2;;
    --subject)      subject="$2"; shift 2;;
    --type)         type="$2"; shift 2;;
    --in-reply-to)  in_reply_to="$2"; shift 2;;
    --body-file)    body_file="$2"; shift 2;;
    --root)         root="$2"; shift 2;;
    --reply-needed) reply_needed="true"; shift;;
    --create-inbox) create_inbox=1; shift;;
    --inspect)      inspect=1; shift;;
    *) am_die 64 BAD_ARG "unknown argument: $1";;
  esac
done

[ -n "$to_repo" ] || am_die 64 BAD_ARG "--to-repo is required"
repo=$(am_canon "$to_repo") || true
[ -n "$repo" ] && [ -d "$repo" ] || am_die 2 REPO_NOT_FOUND "no such repo: $to_repo"

# --inspect: just report the roots and exit.
if [ -n "$inspect" ]; then
  echo "agent roots in $repo:"; am_root_report "$repo"; exit 0
fi

# Root resolution.
found=()
while IFS= read -r _r; do [ -n "$_r" ] && found+=("$_r"); done < <(am_detect_roots "$repo")
if [ -n "$root" ]; then
  [ -d "$repo/$root" ] || am_die 8 ROOT_NOT_PRESENT "--root $root not present in $repo"
elif [ "${#found[@]}" -eq 0 ]; then
  am_die 6 NOT_AGENT_REPO "none of ${AM_ROOTS[*]} exist in $repo - back off and ask the user"
elif [ "${#found[@]}" -gt 1 ]; then
  { echo "AMBIGUOUS_ROOT: multiple agent roots in $repo - ask the user which to use (--root):"
    am_root_report "$repo"; } >&2
  exit 7
else
  root="${found[0]}"
fi

# Refuse a symlinked root (don't follow into who-knows-where).
[ -L "$repo/$root" ] && am_die 8 ROOT_NOT_PRESENT "$root is a symlink in $repo - refusing"
inbox="$repo/$root/inbox"

if [ ! -d "$inbox" ]; then
  [ -n "$create_inbox" ] || am_die 4 NO_INBOX \
    "$root/inbox/ does not exist in $repo - confirm with the user, then rerun with --create-inbox"
  mkdir -p "$inbox"
  cp "$TPL_DIR/inbox-guide.md" "$inbox/HOW-TO-AGENT-MAIL.md"
fi

# Validate inputs.
case "$type" in request|response|handoff|fyi) ;; *) am_die 64 BAD_ARG "bad --type: $type";; esac
[ "$type" = response ] && reply_needed="false"   # anti-ping-pong
[ -n "$subject" ] || am_die 64 BAD_ARG "--subject is required"
[ -n "$from" ] || from=$(basename "$from_repo")
[ -n "$to" ]   || to=$(basename "$repo")
am_valid_name "$from" || am_die 64 BAD_ARG "bad --from name: $from"
am_valid_name "$to"   || am_die 64 BAD_ARG "bad --to name: $to"
from_repo_c=$(am_canon "$from_repo" 2>/dev/null || printf '%s' "$from_repo")
subj_y=$(am_yaml_escape "$subject") || exit $?    # propagate INVALID_FIELD out of the subshell

# Body: explicit file, else the type template as a skeleton.
body_src="$body_file"; [ -n "$body_src" ] || body_src="$TPL_DIR/${type}.md"
[ -f "$body_src" ] || am_die 64 BAD_ARG "body source not found: $body_src"

# Atomic, race-safe create: render per attempt, ln() fails if the dest exists.
slug=$(am_slug "$subject"); [ -n "$slug" ] || slug="message"
ts=$(am_now_ts); iso=$(am_now_iso); seq=$(am_seed_seq "$inbox" "$ts")
tmp=$(mktemp "$inbox/.tmp.XXXXXX")
trap 'rm -f "$tmp"' EXIT

while :; do
  [ "$seq" -le 999 ] || am_die 75 ID_EXHAUSTED "too many messages this second"
  mid=$(printf '%s-%03d' "$ts" "$seq")
  {
    printf -- '---\n'
    printf 'v: 1\n'
    printf 'message-id: %s\n' "$mid"
    printf 'in-reply-to: %s\n' "${in_reply_to:-\"\"}"
    printf 'date: %s\n' "$iso"
    printf 'from: %s\n' "$from"
    printf 'from-repo: %s\n' "$(am_yaml_escape "$from_repo_c")"
    printf 'to: [%s]\n' "$to"
    printf 'subject: %s\n' "$subj_y"
    printf 'type: %s\n' "$type"
    printf 'reply-needed: %s\n' "$reply_needed"
    printf 'status: unread\n'
    printf -- '---\n\n'
    cat "$body_src"
  } > "$tmp"
  dest="$inbox/${mid}__${slug}.md"
  if ln "$tmp" "$dest" 2>/dev/null; then
    rm -f "$tmp"; trap - EXIT
    printf '%s\n' "$dest"
    exit 0
  fi
  seq=$((seq + 1))   # lost the race on this id - bump and retry
done
