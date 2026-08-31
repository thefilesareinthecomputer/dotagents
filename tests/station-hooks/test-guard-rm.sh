#!/usr/bin/env bash
# Table-driven tests for the guard-rm PreToolUse hook.
# Target: ~/.claude/hooks/guard-rm.sh (per-machine, seeded from SPEC-CLAUDE-CODE.md
# §8). Run: bash tests/station-hooks/test-guard-rm.sh
# Exit 0 = all green; nonzero = failures listed.
#
# Tiers: deny = catastrophic/irreversible wipe (agent cannot self-approve);
#        ask  = recursive or glob delete (routes to the user, steer to mv);
#        pass = routine single-file removal (low blast radius).
set -u

HOOK="${HOOK_UNDER_TEST:-$HOME/.claude/hooks/guard-rm.sh}"
[ -f "$HOOK" ] || { echo "FATAL: hook not found at $HOOK"; exit 2; }

pass=0; fail=0

check() {
  local expected="$1" label="$2" cmd="$3"
  local payload decision
  payload=$(jq -cn --arg c "$cmd" '{tool_name:"Bash",tool_input:{command:$c}}')
  decision=$(printf '%s' "$payload" | bash "$HOOK" | jq -r '.hookSpecificOutput.permissionDecision // "pass"' 2>/dev/null)
  [ -z "$decision" ] && decision="pass"
  if [ "$decision" = "$expected" ]; then
    pass=$((pass+1))
  else
    fail=$((fail+1))
    echo "FAIL [$label] expected=$expected got=$decision :: $cmd"
  fi
}

# ---- must DENY: catastrophic / irreversible recursive wipes -----------------
check deny "rf-root"            'rm -rf /'
check deny "rf-root-glob"       'rm -rf /*'
check deny "rf-home-tilde"      'rm -rf ~'
check deny "rf-home-slash"      'rm -rf ~/'
check deny "rf-home-var"        'rm -rf $HOME'
check deny "rf-home-braces"     'rm -rf ${HOME}'
check deny "rf-cwd-dot"         'rm -rf .'
check deny "rf-cwd-dotslash"    'rm -rf ./'
check deny "rf-parent"          'rm -rf ..'
check deny "fr-git"             'rm -fr .git'
check deny "rf-root-space-foot" 'rm -rf / tmp'
check deny "midchain-home"      'cd /tmp && rm -rf ~'
check deny "long-recursive-home" 'rm --recursive --force ~'
check deny "sudo-root"          'sudo rm -rf /'
check deny "cmdsub-root"        'echo $(rm -rf /)'
check deny "brace-group-git"    '{ rm -rf .git; }'
# a QUOTED catastrophic target must still DENY - quoting a home/root wipe does
# not make it safe (the target is hidden from the unquoted view, so the
# catastrophic check reads a quote-stripped view of a confirmed-real rm).
check deny "quoted-home-var"    'rm -rf "$HOME"'
check deny "quoted-home-braces" 'rm -rf "${HOME}"'
check deny "quoted-root"        'rm -rf "/"'
check deny "quoted-home-chain"  'cd /tmp && rm -rf "$HOME"'
check deny "singlequoted-home"  "rm -rf '/'"
# path arithmetic that RESOLVES to a root/home ancestor must DENY (normpath)
check deny "climb-home-var"     'rm -rf $HOME/../..'
check deny "climb-quoted-home"  'rm -rf "$HOME"/../..'
check deny "climb-tilde"        'rm -rf ~/../..'
check deny "delete-home-parent" "rm -rf $(dirname "$HOME")"
# ...but a real subdir reached THROUGH .. must NOT be mistaken for a wipe
check ask  "subdir-via-dotdot"  'rm -rf $HOME/projects/../old-cache'

# ---- must ASK: recursive or glob deletes (real, but route to the user) ------
check ask "rf-node-modules"  'rm -rf node_modules'
check ask "rf-build-dir"     'rm -rf build/'
check ask "r-subtree"        'rm -r ~/projects/old-thing'
check ask "glob-logs"        'rm *.log'
check ask "glob-suffix"      'rm foo*'
check ask "rf-relative-dir"  'rm -rf ./dist'
check ask "glob-bracket"     'rm file[0-9].txt'
check ask "find-exec-rm"     'find . -name "*.tmp" -exec rm -rf {} +'
check ask "xargs-rm"         'find . -name "*.pyc" | xargs rm -f'

# ---- must PASS: routine, low-blast removals & non-rm commands ----------------
check pass "single-file"     'rm foo.txt'
check pass "single-tmp"      'rm /tmp/scratch.log'
check pass "force-single"    'rm -f stale.lock'
check pass "interactive"     'rm -i notes.md'
check pass "two-explicit"    'rm a.txt b.txt'
check pass "not-rm-word"     'npm run rm-stuff'
check pass "rm-substring"    'echo alarm clock'
check pass "quoted-rm-text"  'git commit -m "rm -rf / is dangerous"'
check pass "quoted-in-echo"  'echo "rm -rf ~"'
check pass "no-rm"           'git status'
check pass "rmdir-empty"     'rmdir emptydir'

# ---- non-Bash tools pass through untouched ----------------------------------
out=$(printf '{"tool_name":"Read","tool_input":{"file_path":"/tmp/x"}}' | bash "$HOOK")
if [ -z "$out" ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL [non-bash-passthrough] got: $out"; fi

# ---- deny output is valid harness JSON --------------------------------------
out=$(printf '{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}' | bash "$HOOK")
if printf '%s' "$out" | jq -e '.hookSpecificOutput.permissionDecision == "deny" and (.hookSpecificOutput.permissionDecisionReason | length > 0)' >/dev/null; then
  pass=$((pass+1))
else
  fail=$((fail+1)); echo "FAIL [deny-json-shape] $out"
fi

echo "----"
echo "passed=$pass failed=$fail"
[ "$fail" -eq 0 ]
