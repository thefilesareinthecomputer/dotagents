#!/usr/bin/env bash
# PreToolUse guard (matcher Bash): intercepts destructive `rm` before it runs.
# Shell `rm` bypasses /rewind checkpointing and diff review the same way shell
# writes do (see deny-bash-file-writes.sh), and a recursive rm of the wrong
# root is unrecoverable. Two tiers:
#
#   DENY - catastrophic, irreversible recursive wipes the agent must never do
#          on its own: recursive rm targeting /, ~, $HOME, . (cwd), .., or
#          .git. Denied outright; the agent does not get to self-approve.
#   ASK  - a real but plausibly-legitimate destructive delete (recursive dir
#          removal, or a glob). Routed to the user, with steering toward the
#          house convention: mv the target into an __archive/ folder instead.
#
# Routine low-blast removals (a single named file, no -r, no glob) PASS - the
# guard targets the dangerous habit, not every rm. Companion to
# block-env-files.sh / ask-before-claude-folder-edits.sh / deny-bash-file-writes.sh.
# Requires jq + perl (both §2 station deps); fails open if absent.

input=$(cat)
tool=$(printf '%s' "$input" | jq -r '.tool_name // ""')
[ "$tool" = "Bash" ] || exit 0

cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // ""')
[ -z "$cmd" ] && exit 0

# Unquoted view via a shell quote state machine (identical quoting rules to
# deny-bash-file-writes.sh): emit only characters OUTSIDE quotes and not
# backslash-escaped. This makes `echo "rm -rf /"` inert (the rm is quoted) and
# reads unquoted targets literally (rm -rf $HOME keeps "$HOME"; rm -rf "$HOME"
# has its target stripped and so falls to ASK, never a silent pass).
shellview=$(printf '%s' "$cmd" | perl -0777 -ne '
  my $s = $_;
  my $SQ = chr(39); my $DQ = chr(34); my $BS = chr(92);
  my @o; my $n = length($s); my $i = 0; my $st = 0;  # 0 normal, 1 single, 2 double
  while ($i < $n) {
    my $c = substr($s, $i, 1);
    if ($st == 0) {
      if    ($c eq $BS) { $i += 2; next; }
      elsif ($c eq $SQ) { $st = 1; $i++; next; }
      elsif ($c eq $DQ) { $st = 2; $i++; next; }
      else { push @o, $c; $i++; next; }
    } elsif ($st == 1) {
      $st = 0 if $c eq $SQ; $i++; next;
    } else {
      if ($c eq $BS) { $i += 2; next; }
      $st = 0 if $c eq $DQ; $i++; next;
    }
  }
  print join("", @o);
')

# Collect the argument text of every real `rm` command word (from the rm up to
# the next unquoted separator), so flags/targets of OTHER commands in a chain
# do not trip the guard. The rm may be introduced by a separator (start, | & ;
# ( ) { } newline backtick) OR by a command wrapper that runs it (sudo,
# command, env, xargs, time, nice) OR by find's -exec/-execdir. Matches rm,
# /bin/rm, /usr/bin/rm. `rm-stuff`, `alarm`, `run rm-foo` do NOT match (no
# separator/wrapper before the rm word).
rmargs=$(printf '%s' "$shellview" | perl -0777 -ne '
  my @segs;
  while (/(?:^|[|&;(){}\n`]|\b(?:sudo|command|env|xargs|time|nice)\b|-exec(?:dir)?\b)[ \t]*(?:\/(?:usr\/)?bin\/)?rm\b([^|&;()\n]*)/g) {
    push @segs, $1;
  }
  print join(" ", @segs);
')

# No real rm command word → nothing to guard.
[ -z "$(printf '%s' "$rmargs" | tr -d '[:space:]')" ] && exit 0

recursive=0
if printf '%s' "$rmargs" | grep -qE '(^|[[:space:]])-[a-zA-Z]*[rR]' \
  || printf '%s' "$rmargs" | grep -qE '(^|[[:space:]])--recursive([[:space:]]|$)'; then
  recursive=1
fi

glob=0
printf '%s' "$rmargs" | grep -qE '[*?]|\[[^]]*\]' && glob=1

# Dynamic target: rm fed by find -exec or xargs deletes an unbounded, not-yet-
# visible set of paths - destructive enough to route to the user even when the
# command line itself shows no -r/glob (e.g. `find … | xargs rm -f`).
dynamic=0
printf '%s' "$shellview" | grep -qE '(xargs[^|&;]*[[:space:]]rm([[:space:]]|$))|(-exec(dir)?[[:space:]]+(sudo[[:space:]]+)?rm([[:space:]]|$))' && dynamic=1

# Catastrophic targets (only decisive together with recursion): filesystem
# root, home, current/parent dir, or the git dir.
#
# These are scanned on a quote-CHARACTER-stripped view of the rm args, not the
# quote-stripped-CONTENT shellview: quoting a doomsday target must NOT soften
# the verdict - `rm -rf "$HOME"` is exactly as fatal as `rm -rf $HOME`, so the
# quotes are peeled off (`"$HOME"` -> $HOME, `"/"` -> /) and the target is
# still caught. This only runs after `recursive` (from the quote-aware
# shellview) has confirmed a REAL rm command word, so `echo "rm -rf ~"` never
# reaches here (its rm is inside quotes, so shellview shows no rm at all).
catargs=$(printf '%s' "$cmd" | tr -d '\42\47' | perl -0777 -ne '
  my @segs;
  while (/(?:^|[|&;(){}\n`]|\b(?:sudo|command|env|xargs|time|nice)\b|-exec(?:dir)?\b)[ \t]*(?:\/(?:usr\/)?bin\/)?rm\b([^|&;()\n]*)/g) {
    push @segs, $1;
  }
  print join(" ", @segs);
')

catastrophic=0
if printf '%s' "$catargs" | grep -qE '(^|[[:space:]])/([[:space:]]|$)' \
  || printf '%s' "$catargs" | grep -qE '(^|[[:space:]])/\*' \
  || printf '%s' "$catargs" | grep -qE '(^|[[:space:]])~/?([[:space:]]|$)' \
  || printf '%s' "$catargs" | grep -qE '(^|[[:space:]])\$\{?HOME\}?/?([[:space:]]|$)' \
  || printf '%s' "$catargs" | grep -qE '(^|[[:space:]])\.\.?/?([[:space:]]|$)' \
  || printf '%s' "$catargs" | grep -qE '(^|[[:space:]])\.git([[:space:]/]|$)'; then
  catastrophic=1
fi

# Path-arithmetic climb: a home/root-anchored target that RESOLVES (via ..) to
# the home dir, an ancestor of it, or / is a wipe in disguise (rm -rf
# $HOME/../.. -> /). normpath collapses the .. so we compare the real
# destination - and, crucially, this does NOT flag a genuine subdir reached
# through .. (rm -rf $HOME/projects/../old -> $HOME/old, left as ASK). Only
# absolute / ~ / $HOME-anchored tokens are resolved (relative paths need a cwd
# we don't trust). python3 is a §2 dep; if absent, the lexical checks above
# still stand and a climb simply falls to ASK.
if [ "$catastrophic" -eq 0 ] && command -v python3 >/dev/null 2>&1; then
  if printf '%s' "$catargs" | python3 -c '
import os, sys, shlex
home = os.path.expanduser("~")
data = sys.stdin.read()
try:
    toks = shlex.split(data)
except Exception:
    toks = data.split()
hit = False
for t in toks:
    if t.startswith("-"):
        continue
    x = t.replace("${HOME}", home).replace("$HOME", home)
    if x == "~" or x.startswith("~/"):
        x = home + x[1:]
    if not x.startswith("/"):
        continue
    n = os.path.normpath(x)
    if n == "/" or n == home or home.startswith(n + "/"):
        hit = True
        break
sys.exit(0 if hit else 1)
'; then
    catastrophic=1
  fi
fi

if [ "$recursive" -eq 1 ] && [ "$catastrophic" -eq 1 ]; then
  reason="Blocked: this is a recursive rm targeting a filesystem/home root, the current directory, or .git - an irreversible wipe with blast radius far beyond one file, and it bypasses /rewind entirely. This is never a safe agent action. Do NOT rephrase to evade it. If a specific directory genuinely must go, name it explicitly (not /, ~, \$HOME, ., or .git) and hand the exact command to the user to run."
  jq -n --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  exit 0
fi

if [ "$recursive" -eq 1 ] || [ "$glob" -eq 1 ] || [ "$dynamic" -eq 1 ]; then
  reason="This rm deletes recursively, by glob, or over a find/xargs set - destructive, and it bypasses /rewind checkpointing (a shell delete is not recoverable the way a Write/Edit is). Prefer the reversible path: mv the target into an __archive/ folder. If it truly must be deleted, confirm the exact paths first - a glob, -r, or find/xargs can match more than intended."
  jq -n --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"ask",permissionDecisionReason:$r}}'
  exit 0
fi

exit 0
