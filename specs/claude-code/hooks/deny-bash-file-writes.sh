#!/usr/bin/env bash
# PreToolUse guard: DENIES Bash commands that author file content via the
# shell (redirects, tee, sed/perl -i, python write modes, heredoc-to-file).
# File content changes must go through the Write/Edit tools - they carry
# read-before-write enforcement, diff review, the ~/.claude folder guard,
# file-state tracking, and /rewind checkpointing. A shell write bypasses all
# of it, so it is blocked outright, not routed to a permission prompt.
#
# Companion to block-env-files.sh and ask-before-claude-folder-edits.sh.
# If a command legitimately needs a program's own output on disk, the agent
# must say so and the USER decides how to run it - the agent does not get a
# dialog to approve its own bypass.

input=$(cat)
tool=$(printf '%s' "$input" | jq -r '.tool_name // ""')
[ "$tool" = "Bash" ] || exit 0

cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // ""')
[ -z "$cmd" ] && exit 0

# Two scanning views of the command:
#
# RAW (quotes intact) - for interpreter code passed as argument strings,
# where the write call legitimately lives inside quotes:
#   python3 -c 'open("f","w")' / node -e 'fs.writeFileSync(...)'
#
# SHELL (only characters OUTSIDE shell quotes) - for shell-level write
# operators, which only act when unquoted. This is what lets innocent quoted
# text pass: git commit -m "recall 73 > 90" writes nothing.
# Accepted gap (habit-routing, not containment): a write nested entirely
# inside quotes, e.g. bash -c 'echo x > f' - the deny text forbids evasion.
#
# The SHELL view is built by a single-pass shell quote STATE MACHINE, not a
# blind s/'…'//;s/"…"// strip. The blind strip was unsound - it treated an
# apostrophe inside a double-quoted arg as a single-quote opener, and it did
# not honor backslash escapes, so real redirects between such tokens slipped
# through (echo "a'" > "b'"  and  echo \"a > b\"). The state machine emits a
# character only when it sits outside quotes and is not backslash-escaped, so
# those redirects survive into the view and are caught.
#
# It also strips heredoc BODIES first (keeping the command line and the
# <<WORD marker) so a '>' in heredoc DATA is not misread as a redirect, while
# a redirect ON the heredoc command line (cat > f <<EOF) is still caught, and
# heredoc-fed patch/apply is still detected via the <<-in-raw check below.
#
# Finally it scrubs harmless redirects: /dev/null sinks and fd-to-fd
# duplications (2>&1, >&2). Boundaries required so `/dev/nullish` and
# `>&123file` cannot smuggle a write past the scrub.
#
# One sanctioned lane, scrubbed last: a > or >> whose target is a literal path
# inside THIS session's scratchpad directory, which is disposable and sits
# outside every repo, so a write there has no diff to review and no /rewind
# state to lose. Program output and intermediates belong there; anything bound
# for a tracked file still goes through Write/Edit.
#
# The lane is anchored to <uid>/<slug>/<session-id>/scratchpad/, NOT to the
# /tmp/claude-<uid>/ tree at large. The wider tree is not disposable: the
# harness plants a sibling tasks/ directory full of symlinks pointing into
# ~/.claude/projects (342 of them on this station), so granting the tree would
# hand out truncate access to subagent transcripts inside the very folder
# ask-before-claude-folder-edits.sh guards - reachable by accident, not just by
# malice. Anchoring on the session id also stops one session from clobbering a
# concurrently running session's working files.
scratch_uid=$(id -u 2>/dev/null)
[ -z "$scratch_uid" ] && scratch_uid="no-such-uid"   # fail closed: never matches
scratch_sid=$(printf '%s' "$input" | jq -r '.session_id // ""')
[ -z "$scratch_sid" ] && scratch_sid="no-such-session"

raw="$cmd"
shellview=$(printf '%s' "$cmd" | perl -0777 -ne '
  my $s = $_;
  # (1) remove heredoc bodies: <<WORD / <<-WORD / <<"WORD" / <<\x27WORD\x27.
  # Keep group 1 (the command line up to and including its newline) and the
  # <<WORD marker; drop the body and the terminator line.
  $s =~ s/(<<-?[ \t]*(["\x27]?)([A-Za-z_]\w*)\2[^\n]*\n)(.*?)(\n[ \t]*\3\b[^\n]*)/$1/gs;
  # (2) emit only unquoted, unescaped characters (shell quoting state machine).
  my $SQ = chr(39); my $DQ = chr(34); my $BS = chr(92);
  my @o; my $n = length($s); my $i = 0; my $st = 0;  # st: 0 normal, 1 single, 2 double
  while ($i < $n) {
    my $c = substr($s, $i, 1);
    if ($st == 0) {
      if    ($c eq $BS) { $i += 2; next; }           # escape: next char is literal
      elsif ($c eq $SQ) { $st = 1; $i++; next; }
      elsif ($c eq $DQ) { $st = 2; $i++; next; }
      else { push @o, $c; $i++; next; }
    } elsif ($st == 1) {                             # single quotes: literal, no escapes
      $st = 0 if $c eq $SQ; $i++; next;
    } else {                                         # double quotes: \ escapes next
      if ($c eq $BS) { $i += 2; next; }
      $st = 0 if $c eq $DQ; $i++; next;
    }
  }
  print join("", @o);
' \
  | sed -E 's;[0-9]*>{1,2}[[:space:]]*/dev/null([[:space:]&|;]|$);\1;g' \
  | sed -E 's;[0-9]*>&[0-9]+([^0-9A-Za-z_./-]|$);\1;g' \
  | SCRATCH_UID="$scratch_uid" SCRATCH_SID="$scratch_sid" perl -0777 -pe '
      # Scrub redirects into this session scratchpad (the sanctioned lane).
      # The target charset excludes $ ` ~ quotes and whitespace, so no expansion
      # or command substitution can hide inside an allowed path - what this
      # matches is what the shell will open. A quoted target is already absent
      # from this view (the state machine dropped it), so it still denies; that
      # is deliberate, not a gap. Any ".." in the path keeps the redirect, so
      # traversal out of the scratchpad denies. The (?<![<]) guard keeps <>
      # read-write opens out of the lane, so check 1b below still sees them.
      s{(?<![<])(?:\d*|&)>{1,2}[ \t]*((?:/private)?/tmp/claude-\Q$ENV{SCRATCH_UID}\E/[A-Za-z0-9._-]+/\Q$ENV{SCRATCH_SID}\E/scratchpad/[A-Za-z0-9._/-]+)(?=[ \t&|;)\n]|\z)}
       {index($1, "..") >= 0 ? $& : ""}ge;
    ')

hit=""
# --- SHELL view: unquoted shell-level writers ---
# 1. Remaining > or >> redirect (writes/truncates a file)
if printf '%s' "$shellview" | grep -qE '(^|[^<>])>{1,2}[^>]'; then
  hit="output redirection (> / >>)"
# 1b. <> read-write open (creates/truncates; the > is preceded by <, so the
#     main redirect pattern's boundary misses it)
elif printf '%s' "$shellview" | grep -qE '<>'; then
  hit="read-write redirect (<>)"
# 2. tee (writes its stdin to files)
elif printf '%s' "$shellview" | grep -qE '(^|[|&;[:space:]])tee([[:space:]]|$)'; then
  hit="tee"
# 3. in-place editors (bundled flags like -pi count; gsed = GNU sed)
elif printf '%s' "$shellview" | grep -qE '(^|[|&;[:space:]])(sed|gsed|perl)[^|;&]*[[:space:]](-[a-zA-Z]*i[^|;&[:space:]]*|--in-place(=[^|;&[:space:]]*)?)([[:space:]]|$)'; then
  hit="in-place edit (sed/gsed/perl -i)"
# 4. inline patch application (heredoc-authored diffs bypass Edit review)
elif printf '%s' "$shellview" | grep -qE '(^|[|&;[:space:]])(git[[:space:]]+apply|patch)([[:space:]]|$)' \
  && printf '%s' "$raw" | grep -q '<<'; then
  hit="inline patch (git apply/patch fed by heredoc)"
# 5. raw writers
elif printf '%s' "$shellview" | grep -qE '(^|[|&;[:space:]])dd[[:space:]][^|;&]*of='; then
  hit="dd of="
elif printf '%s' "$shellview" | grep -qE '(^|[|&;[:space:]])truncate([[:space:]]|$)'; then
  hit="truncate"
# --- RAW view: interpreter one-liners and heredoc bodies ---
# 6. python file-write: open() with write/append/exclusive-create mode
elif printf '%s' "$raw" | grep -qE "open\([^)]*['\"](w|a|x|r\+|w\+|a\+|x\+|wb|ab|xb)"; then
  hit="python open() in write mode"
# 7. pathlib writes
elif printf '%s' "$raw" | grep -qE '\.write_text\(|\.write_bytes\('; then
  hit="pathlib write_text/write_bytes"
# 8. node fs writes
elif printf '%s' "$raw" | grep -qE '(writeFile|appendFile)(Sync)?[[:space:]]*\('; then
  hit="node fs write (writeFile/appendFile)"
fi

[ -z "$hit" ] && exit 0

reason="Blocked: this Bash command writes file content via the shell (${hit}). File content changes go through the Write/Edit tools ONLY - they carry diff review, the ~/.claude folder guard, file-state tracking, and /rewind checkpointing; shell writes bypass all of them. Do NOT rephrase the command to evade this. Reformulate: author the content with Write/Edit, or read program output from stdout instead of a file. Program output and intermediates may be redirected to a literal path inside the session scratchpad (/tmp/claude-<uid>/...) - unquoted, absolute, no variables, no '..'; copying that output into a tracked path afterwards is the same violation as writing there directly. If a program's own output genuinely must land on a tracked path, tell the user what and why, and let them run it."
jq -n --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
exit 0
