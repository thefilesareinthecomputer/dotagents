#!/usr/bin/env bash
# run.sh - acceptance tests for agent-mail. Uses throwaway repos under a temp dir;
# never touches a real agent root. Exits 0 only if every assertion passes.
set -uo pipefail   # NOT -e: we deliberately drive error paths
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
SCRIPTS="$HERE/../scripts"
SEND="$SCRIPTS/send.sh"; MARK="$SCRIPTS/mark.sh"; INBOX="$SCRIPTS/inbox.sh"; SWEEP="$SCRIPTS/sweep.sh"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
ok(){ pass=$((pass+1)); printf '  PASS  %s\n' "$1"; }
no(){ fail=$((fail+1)); printf '  FAIL  %s\n' "$1"; }
rc_is(){ if [ "$2" = "$3" ]; then ok "$1 (rc=$3)"; else no "$1 (want $2 got $3)"; fi; }
mkrepo(){ local d="$TMP/$1"; mkdir -p "$d"; shift; for r in "$@"; do mkdir -p "$d/$r"; done; printf '%s' "$d"; }
B="$TMP/body.md"; printf 'hello body\n' > "$B"

echo "== guard flow =="
bash "$SEND" --to-repo "$TMP/nope" --subject x --body-file "$B" >/dev/null 2>&1; rc_is "missing repo" 2 $?
R=$(mkrepo plain); bash "$SEND" --to-repo "$R" --subject x --body-file "$B" >/dev/null 2>&1; rc_is "no agent root" 6 $?
R=$(mkrepo single .cursor); bash "$SEND" --to-repo "$R" --subject x --body-file "$B" >/dev/null 2>&1; rc_is "root but no inbox" 4 $?

echo "== create-inbox + delivery =="
out=$(bash "$SEND" --to-repo "$R" --from A --to B --subject "Hi There" --type request --create-inbox --body-file "$B" 2>/dev/null); rc=$?
rc_is "create-inbox delivers" 0 "$rc"
[ -f "$R/.cursor/inbox/HOW-TO-AGENT-MAIL.md" ] && ok "guide written on create" || no "guide written on create"
[ -n "$out" ] && [ -f "$out" ] && ok "message file exists" || no "message file exists"
mid=$(awk -F': ' '/^message-id:/{print $2; exit}' "$out")
case "$(basename "$out")" in "$mid"__*) ok "filename prefix == message-id";; *) no "filename prefix == message-id";; esac
grep -q '^status: unread$' "$out" && ok "envelope status unread" || no "envelope status unread"
grep -q '^v: 1$' "$out" && ok "schema version present" || no "schema version present"

echo "== ambiguous / explicit root =="
R2=$(mkrepo multi .claude .cursor)
bash "$SEND" --to-repo "$R2" --subject x --body-file "$B" >/dev/null 2>&1; rc_is "ambiguous root" 7 $?
rep=$(bash "$SEND" --to-repo "$R2" --subject x --body-file "$B" 2>&1)
{ printf '%s' "$rep" | grep -q '.claude' && printf '%s' "$rep" | grep -q '.cursor'; } && ok "report names both roots" || no "report names both roots"
bash "$SEND" --to-repo "$R2" --root .claude --subject x --body-file "$B" >/dev/null 2>&1; rc_is "explicit root -> no inbox" 4 $?
bash "$SEND" --to-repo "$R2" --root .agents --subject x --body-file "$B" >/dev/null 2>&1; rc_is "explicit absent root" 8 $?

echo "== path safety =="
R3=$(mkrepo symre); ln -s "$TMP" "$R3/.claude"
bash "$SEND" --to-repo "$R3" --subject x --body-file "$B" >/dev/null 2>&1; rc_is "symlinked root refused" 8 $?

echo "== race / uniqueness =="
R4=$(mkrepo race .claude); mkdir -p "$R4/.claude/inbox"
for i in 1 2 3; do bash "$SEND" --to-repo "$R4" --from A --to B --subject "same subj" --body-file "$B" >/dev/null 2>&1; done
n=$(find "$R4/.claude/inbox" -maxdepth 1 -name '*.md' | wc -l | tr -d ' ')
[ "$n" -eq 3 ] && ok "3 sends -> 3 distinct files (no clobber)" || no "3 sends -> 3 files (got $n)"

echo "== YAML safety =="
out=$(bash "$SEND" --to-repo "$R4" --from A --to B --subject 'weird "quote" and --- dashes' --body-file "$B" 2>/dev/null); rc=$?
rc_is "quotes/dashes in subject deliver" 0 "$rc"
[ -n "$out" ] && grep -q '^status: unread$' "$out" && ok "envelope parseable after quotes" || no "envelope parseable after quotes"
bash "$SEND" --to-repo "$R4" --from A --to B --subject "$(printf 'a\nb')" --body-file "$B" >/dev/null 2>&1; rc_is "newline subject rejected" 9 $?

echo "== response anti-ping-pong =="
out=$(bash "$SEND" --to-repo "$R4" --from A --to B --subject resp --type response --reply-needed --body-file "$B" 2>/dev/null)
grep -q '^reply-needed: false$' "$out" && ok "response forces reply-needed false" || no "response forces reply-needed false"

echo "== mark / archive =="
msg=$(find "$R4/.claude/inbox" -maxdepth 1 -name '*.md' | head -1)
bash "$MARK" --file "$msg" --status in-progress >/dev/null 2>&1; rc_is "mark in-progress" 0 $?
grep -q '^status: in-progress$' "$msg" && ok "status updated in place" || no "status updated in place"
[ -f "$msg" ] && ok "in-progress stays top level" || no "in-progress stays top level"
dest=$(bash "$MARK" --file "$msg" --status resolved 2>/dev/null); rc=$?
rc_is "mark resolved" 0 "$rc"
case "$dest" in */processed/*) ok "resolved moved to processed";; *) no "resolved moved to processed ($dest)";; esac
{ [ -f "$dest" ] && grep -q '^status: resolved$' "$dest"; } && ok "resolved status persisted" || no "resolved status persisted"
[ ! -f "$msg" ] && ok "original removed from top level" || no "original removed from top level"
bad="$TMP/bad.md"; printf 'not a message\n' > "$bad"
bash "$MARK" --file "$bad" --status resolved >/dev/null 2>&1; rc_is "malformed rejected (no sidecar)" 5 $?
[ ! -f "$bad.status" ] && ok "no sidecar created" || no "no sidecar created"

echo "== inbox listing =="
out=$(bash "$INBOX" --repo "$R4" 2>/dev/null); rc_is "inbox list runs" 0 $?

echo "== sweep =="
R5=$(mkrepo sweep .claude); mkdir -p "$R5/.claude/inbox"
bash "$SWEEP" --repo "$R5" >/dev/null 2>&1; rc_is "empty inbox is clean" 0 $?
o=$(bash "$SEND" --to-repo "$R5" --from A --to B --subject owes --type request --reply-needed --body-file "$B" 2>/dev/null)
t=$(bash "$SEND" --to-repo "$R5" --from A --to B --subject triage --type fyi --body-file "$B" 2>/dev/null)
a=$(bash "$SEND" --to-repo "$R5" --from A --to B --subject aband --type fyi --body-file "$B" 2>/dev/null)
bash "$MARK" --file "$a" --status in-progress >/dev/null 2>&1
out=$(bash "$SWEEP" --repo "$R5" 2>/dev/null); rc=$?
rc_is "outstanding mail -> rc 1" 1 "$rc"
printf '%s' "$out" | grep -q 'OWES-REPLY (1)'  && ok "reply-needed lands in OWES-REPLY"  || no "reply-needed lands in OWES-REPLY"
printf '%s' "$out" | grep -q 'TRIAGE (1)'      && ok "unread lands in TRIAGE"            || no "unread lands in TRIAGE"
printf '%s' "$out" | grep -q 'ABANDONED (1)'   && ok "in-progress lands in ABANDONED"    || no "in-progress lands in ABANDONED"
# a hand-edited status that never moved is STRANDED, and --fix-stranded files it
s=$(bash "$SEND" --to-repo "$R5" --from A --to B --subject strand --type fyi --body-file "$B" 2>/dev/null)
awk '{sub(/^status: unread$/,"status: resolved")}1' "$s" > "$s.x" && mv "$s.x" "$s"
out=$(bash "$SWEEP" --repo "$R5" 2>/dev/null)
printf '%s' "$out" | grep -q 'STRANDED (1)' && ok "hand-closed message is STRANDED" || no "hand-closed message is STRANDED"
bash "$SWEEP" --repo "$R5" --fix-stranded >/dev/null 2>&1
{ [ ! -f "$s" ] && [ -f "$R5/.claude/inbox/processed/$(basename "$s")" ]; } && ok "--fix-stranded files it" || no "--fix-stranded files it"
out=$(bash "$SWEEP" --repo "$R5" 2>/dev/null)
printf '%s' "$out" | grep -q 'STRANDED' && no "STRANDED cleared after fix" || ok "STRANDED cleared after fix"
# clearing every bucket leaves a clean inbox
for m in "$o" "$t" "$a"; do bash "$MARK" --file "$m" --status resolved >/dev/null 2>&1; done
bash "$SWEEP" --repo "$R5" >/dev/null 2>&1; rc_is "all closed -> clean" 0 $?
bash "$SWEEP" --repo "$R5" --stale-days x >/dev/null 2>&1; rc_is "bad --stale-days rejected" 64 $?

echo "----"; printf 'pass=%d fail=%d\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
