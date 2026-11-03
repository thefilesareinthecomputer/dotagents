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

echo "== sensitive content =="
R6=$(mkrepo sens .claude); mkdir -p "$R6/.claude/inbox"
fake="ghp_$(printf 'a%.0s' $(seq 36))"   # secret-shaped, built at run time, never real
S1="$TMP/s1.md"; printf 'the test key is %s\n' "$fake" > "$S1"
err=$(bash "$SEND" --to-repo "$R6" --from A --to B --subject x --body-file "$S1" 2>&1 >/dev/null); rc=$?
rc_is "secret in body refused" 9 "$rc"
printf '%s' "$err" | grep -q 'SENSITIVE_CONTENT' && ok "refusal names the token" || no "refusal names the token"
printf '%s' "$err" | grep -qF "$fake" && no "refusal never echoes the value" || ok "refusal never echoes the value"
n=$(find "$R6/.claude/inbox" -maxdepth 1 -name '*.md' | wc -l | tr -d ' ')
[ "$n" -eq 0 ] && ok "refused send writes nothing" || no "refused send writes nothing (got $n)"
at="@"; real_addr="chef.owner${at}gmail.com"   # assembled at run time, synthetic
bash "$SEND" --to-repo "$R6" --from A --to B --subject "ask $real_addr" --body-file "$B" >/dev/null 2>&1
rc_is "real-looking email in subject refused" 9 $?
S2="$TMP/s2.md"; printf 'log in as qa@example.com, fix in /Users/me/dev/app/views.py\n' > "$S2"
bash "$SEND" --to-repo "$R6" --from A --to B --subject x --body-file "$S2" >/dev/null 2>&1
rc_is "reserved example email and repo path allowed" 0 $?
S3="$TMP/s3.md"; printf 'values: {redacted-email}, {redacted-password}, price_xxxxxxxx; fixture editor@org-1.example.test and qa@example.com.\n' > "$S3"
bash "$SEND" --to-repo "$R6" --from A --to B --subject x --body-file "$S3" >/dev/null 2>&1
rc_is "redaction markers and all-x placeholders allowed" 0 $?
S5="$TMP/s5.md"; printf 'fixed in #53 and #1287; test caller (312) 555-0123 and 555-0199; signup prefix-1729000000@e2e-ab12cd.test\n' > "$S5"
bash "$SEND" --to-repo "$R6" --from A --to B --subject x --body-file "$S5" >/dev/null 2>&1
rc_is "PR refs, fictional 555 numbers and .test signups allowed" 0 $?
bash "$SEND" --to-repo "$R6" --from A --to B --subject "call (312) 867-5309" --body-file "$B" >/dev/null 2>&1
rc_is "real-shaped phone number refused" 9 $?
S4="$TMP/s4.md"; printf 'write to boss%smail.example.com.realcorp.io\n' "$at" > "$S4"
bash "$SEND" --to-repo "$R6" --from A --to B --subject x --body-file "$S4" >/dev/null 2>&1
rc_is "real domain behind an example label refused" 9 $?
for kx in "sk_live_$(printf 'a1B2%.0s' $(seq 6))_xxxx" "AKIA$(printf 'Q7%.0s' $(seq 8))_xxxx" "sk-proj-$(printf 'a1B2%.0s' $(seq 6))_xxxx"; do
  SK="$TMP/sk.md"; printf 'the key is %s\n' "$kx" > "$SK"
  bash "$SEND" --to-repo "$R6" --from A --to B --subject x --body-file "$SK" >/dev/null 2>&1
  rc_is "a key with an x-run suffix (${kx%%[0-9]*}...) is still refused" 9 $?
done
S6="$TMP/s6.md"; printf 'see STORY-%s and the hidden %b here\n' "583920" '\0342\0200\0256' > "$S6"
bash "$SEND" --to-repo "$R6" --from A --to B --subject x --body-file "$S6" >/dev/null 2>&1
rc_is "a real-shaped work item and a bidi override are refused" 9 $?
bash "$SEND" --to-repo "$R6" --from A --to B --subject "-dash subject" --body-file "$B" >/dev/null 2>&1
rc_is "subject starting with a dash still sends" 0 $?
err=$(AGENT_MAIL_SCANNER="$TMP/none.py" bash "$SEND" --to-repo "$R6" --from A --to B --subject x --body-file "$S1" 2>&1 >/dev/null); rc=$?
rc_is "no scanner installed -> sends" 0 "$rc"
printf '%s' "$err" | grep -q 'WARNING' && ok "no scanner -> warning" || no "no scanner -> warning"

echo "== home-relative from-repo =="
H="$TMP/home"; mkdir -p "$H/dev/sender/.claude/inbox" "$H/dev/peer/.claude/inbox"
out=$(HOME="$H" bash "$SEND" --to-repo "$H/dev/peer" --from-repo "$H/dev/sender" --from A --to B --subject x --body-file "$B" 2>/dev/null)
grep -q '^from-repo: "~/dev/sender"$' "$out" && ok "from-repo under home is written as ~/" || no "from-repo under home is written as ~/"
Hc=$(cd "$H" && pwd -P)
{ grep -qF "$H" "$out" || grep -qF "$Hc" "$out"; } && no "message never holds the home path" || ok "message never holds the home path"
reply=$(awk -F': ' '/^from-repo:/{gsub(/"/,"",$2); print $2; exit}' "$out")
HOME="$H" bash "$SEND" --to-repo "$reply" --from B --to A --subject re --type response --body-file "$B" >/dev/null 2>&1
rc_is "a ~/ from-repo resolves as a reply target" 0 $?
out=$(HOME="$H" bash "$SEND" --to-repo "$H/dev/peer" --from-repo "$R6" --from A --to B --subject x --body-file "$B" 2>/dev/null)
grep -qF "from-repo: \"$(cd "$R6" && pwd -P)\"" "$out" && ok "from-repo outside home stays absolute" || no "from-repo outside home stays absolute"

echo "----"; printf 'pass=%d fail=%d\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
