#!/usr/bin/env bash
# Table-driven tests for the deny-bash-file-writes PreToolUse hook.
# Target: ~/.claude/hooks/deny-bash-file-writes.sh (per-machine, seeded from
# SPEC-CLAUDE-CODE.md §8). Run: bash tests/station-hooks/test-deny-bash-file-writes.sh
# Exit 0 = all green; nonzero = failures listed.
set -u

HOOK="${HOOK_UNDER_TEST:-$HOME/.claude/hooks/deny-bash-file-writes.sh}"
[ -f "$HOOK" ] || { echo "FATAL: hook not found at $HOOK"; exit 2; }

pass=0; fail=0

# The scratchpad lane is anchored to the session id the harness passes in, so
# every payload carries one. Fixed value: the tests assert lexical behavior.
SID="11111111-2222-3333-4444-555555555555"

# check <expected: deny|pass> <label> <command-string>
check() {
  local expected="$1" label="$2" cmd="$3"
  local payload decision
  payload=$(jq -cn --arg c "$cmd" --arg s "$SID" '{tool_name:"Bash",session_id:$s,tool_input:{command:$c}}')
  decision=$(printf '%s' "$payload" | bash "$HOOK" | jq -r '.hookSpecificOutput.permissionDecision // "pass"' 2>/dev/null)
  [ -z "$decision" ] && decision="pass"
  if [ "$decision" = "$expected" ]; then
    pass=$((pass+1))
  else
    fail=$((fail+1))
    echo "FAIL [$label] expected=$expected got=$decision :: $cmd"
  fi
}

# ---- must DENY: shell file-write forms -------------------------------------
check deny "redirect-create"     'cat > /tmp/x.md'
check deny "redirect-append"     'echo hi >> notes.md'
check deny "redirect-midpipe"    'grep foo bar.txt > out.txt'
check deny "ampersand-redirect"  'make &> build.log'
check deny "tee"                 'echo hi | tee file.txt'
check deny "tee-append"          'printf x | tee -a log.md'
check deny "sed-inplace"         'sed -i s/a/b/ file.md'
check deny "sed-inplace-bundled" 'sed -riE s/a/b/ file.md'
check deny "perl-inplace"        'perl -pi -e s/a/b/ f.md'
check deny "sed-inplace-tilde"   'sed -i~ s/a/b/ file.md'
check deny "sed-inplace-usuffix" 'sed -i_bak s/a/b/ file.md'
check deny "sed-inplace-digit"   'sed -i2 s/a/b/ file.md'
check deny "perl-inplace-tilde"  'perl -i~ -pe s/a/b/ f.md'
check deny "py-open-write"       'python3 -c '"'"'open("f","w").write("x")'"'"''
check deny "py-open-append"      'python3 -c '"'"'open("f","a").write("x")'"'"''
check deny "py-heredoc-open"     'python3 - <<EOF
open("f","w").write("x")
EOF'
check deny "py-write-text"       'python3 -c '"'"'from pathlib import Path; Path("f").write_text("x")'"'"''
check deny "py-heredoc-json-dump-to-open" 'python3 - <<EOF
import json
json.dump({}, open("s.json","w"))
EOF'
# hardening round (2026-07-12 security review): habit-tier evasions
check deny "gsed-inplace"        'gsed -i s/a/b/ file.md'
check deny "py-open-exclusive"   'python3 -c '"'"'open("f","x").write("1")'"'"''
check deny "node-writefilesync"  'node -e '"'"'require("fs").writeFileSync("f","x")'"'"''
check deny "node-appendfile"     'node -e '"'"'fs.appendFile("f","x",cb)'"'"''
check deny "git-apply-heredoc"   'git apply <<EOF
diff --git a/f b/f
EOF'
check deny "patch-heredoc"       'patch f.md <<EOF
@@ -1 +1 @@
EOF'
check deny "dd-of"               'echo hi | dd of=f.md'
check deny "truncate"            'truncate -s 0 f.md'
# scrub-boundary regressions: contrived names must not smuggle writes
check deny "dev-nullish"         'echo x > /dev/nullish'
check deny "fd-dup-glued-file"   'echo x >&123file'

# ---- must PASS: legitimate read/exec forms ----------------------------------
check pass "git-status"        'git status'
check pass "git-log"           'rtk git log --oneline -5'
check pass "git-commit"        'git commit -m "docs: update counts"'
check pass "stderr-null"       'ls -la 2>/dev/null'
check pass "stdout-null-dup"   'pytest -q > /dev/null 2>&1'
check pass "py-read-json"      'python3 -c '"'"'import json; print(json.load(open("s.json")))'"'"''
check pass "py-json-tool"      'python3 -m json.tool evals.json'
check pass "py-unittest"       'python3 -m unittest discover -s tests'
check pass "sed-read-only"     'sed -n 3p SKILL.md'
check pass "sed-read-dashword-path" 'sed -n 1,15p skills/ai-engineering/resources/link-ledger.md'
check pass "sed-read-dashi-filename" 'sed -n 3p bar-input.txt'
check pass "sed-expression"    'sed -E "s;foo;bar;" file.md'
check pass "grep"              'grep -rn pattern skills/'
check pass "jq-read"           'jq -r .name package.json'
check pass "find"              'find . -name "*.md"'
check pass "chmod"             'chmod +x script.sh'
# programs that write files at RUNTIME must pass - the hook guards inline
# content authoring, not tool execution (non-constriction guarantee)
check pass "engine-writes-db"  'python3 skills/obsidian-kg/scripts/obsidian_kg.py ingest ~/vault'
check pass "git-apply-file"    'git apply fix.patch'
check pass "node-read"         'node -e '"'"'console.log(require("./package.json").name)'"'"''
check pass "gsed-read"         'gsed -n 3p file.md'
check pass "sqlite-insert"     'sqlite3 graph.db "INSERT INTO notes VALUES (1)"'
check pass "npm-install"       'npm install --save-dev vitest'
check pass "file-relocation"   'mv tasks/plan.md tasks/plan-old.md'
check pass "recursive-copy"    'cp -R skills/obsidian-kg /tmp/kb-copy'
check pass "git-mv"            'git mv HANDOFF.md tasks/todo.md'
check pass "mkdir"             'mkdir -p tests/station-hooks'

# ---- quote-awareness: innocent quoted text must PASS (the git-commit fix) --
check pass "quoted-gt-commit"    'git commit -m "recall 73 > 90"'
check pass "quoted-pattern-word" 'git commit -m "guard catches dd of= and tee"'
check pass "quoted-grep-gt"      'grep -n "=>" src/app.ts'
check pass "echo-quoted-arrow"   'echo "a -> b > c" | head -1'
# multi-line quoted strings are ONE quoted span (line-based stripping bug)
check pass "multiline-quoted-commit" 'git commit -m "feat: guard hardening

covers sed/gsed/perl -i (bundled flags), dd of=, tee, truncate
and output redirection > with steering text"'
# real writes still deny when the operator is outside quotes
check deny "quoted-msg-real-write" 'echo "innocent text" > f.md'
check deny "multiline-msg-then-write" 'git commit -m "line one
line two" && echo done > status.md'

# ---- quote SOUNDNESS: unsound-stripper bypasses must DENY (2026-07-12) -------
# The old s/'"'"'…'"'"'//;s/"…"// strip mis-parsed these and let the redirect slip.
# 1) apostrophes inside two double-quoted args form a phantom single-quote span
#    that swallowed the real redirect between them.
check deny "apostrophe-phantom-span" $'echo "a\'" > "b\'"'
# 2) backslash-escaped quotes: \" is a literal ", not a quote boundary; the
#    real redirect sits OUTSIDE quotes.
check deny "escaped-quote-redirect" 'echo \"a > b\"'
# 3) <> read-write open creates/truncates a file (left of > is <, boundary miss)
check deny "readwrite-redirect" 'cat 0<>f.md'

# ---- quote SOUNDNESS: legitimate forms these fixes must still PASS -----------
# heredoc BODY text containing > is data (fed to a pipe), not a redirect
check pass "heredoc-body-gt" 'cat <<EOF | wc -l
score 5 > 3 wins
EOF'
# an escaped > is a literal character, not a redirect (writes nothing)
check pass "escaped-literal-gt" 'echo \> literal-arrow'
# process substitution is not a file write
check pass "procsub-diff" 'diff <(sort a.txt) <(sort b.txt)'
# a redirect ON the heredoc command line is still a real write → DENY
check deny "heredoc-cmdline-redirect" 'cat > out.md <<EOF
body line
EOF'

# ---- scratchpad lane: > and >> into THIS session's scratchpad PASS ----------
# (2026-07-28) That one directory is disposable and outside every repo, so a
# write there has no diff to review and no /rewind state to lose.
SP="/private/tmp/claude-$(id -u)/-proj-slug/$SID/scratchpad"
SP_SHORT="/tmp/claude-$(id -u)/-proj-slug/$SID/scratchpad"
check pass "scratch-redirect"      "python3 eval.py > $SP/results.json"
check pass "scratch-append"        "echo probe >> $SP/log.txt"
check pass "scratch-no-private"    "pytest -q > $SP_SHORT/run.log"
check pass "scratch-with-fd-dup"   "ollama serve > $SP/ollama.log 2>&1"
check pass "scratch-stderr-fd"     "python3 eval.py > $SP/out.json 2> $SP/err.log"
check pass "scratch-amp-redirect"  "make &> $SP/build.log"
check pass "scratch-then-pipe"     "sort urls.txt > $SP/u.txt; wc -l $SP/u.txt"
check pass "scratch-nested-dir"    "python3 eval.py > $SP/runs/2026/out.json"
# ---- lane boundaries: the harness owns the rest of the tree, so it DENIES ----
# tasks/ is a sibling of scratchpad/ and is full of harness-planted symlinks
# into ~/.claude/projects; granting the tree would grant those. Anchoring on
# <session-id>/scratchpad/ is what keeps the lane honest.
check deny "scratch-sibling-tasks" "echo x > $(dirname "$SP")/tasks/a732068d8cdeb8b81.output"
check deny "scratch-session-root"  "echo x > $(dirname "$SP")/f.json"
check deny "scratch-other-session" "echo x > /private/tmp/claude-$(id -u)/-proj-slug/99999999-0000-0000-0000-000000000000/scratchpad/f.json"
check deny "scratch-slug-traversal" "echo x > /private/tmp/claude-$(id -u)/-proj/$SID/scratchpad/../tasks/f.output"
check deny "scratch-traversal"     "echo x > $SP/../../../../../$HOME/.agents/f.md"
check deny "scratch-wrong-uid"     "echo x > /tmp/claude-999999/-proj-slug/$SID/scratchpad/f"
check deny "scratch-prefix-glued"  "echo x > /tmp/claude-$(id -u)x/-proj-slug/$SID/scratchpad/f"
check deny "scratch-plain-tmp"     'echo x > /tmp/slop_test_out.txt'
check deny "scratch-var-target"    'echo x > $SP/f.json'
check deny "scratch-quoted-target" "echo x > \"$SP/f.json\""
check deny "scratch-cmdsub-target" "echo x > $SP/\$(whoami).json"
check deny "scratch-colon-target"  "echo x > $SP/a:b.json"
check deny "scratch-tilde-target"  "echo x > $SP/~backup.json"
check deny "scratch-readwrite"     "cat 0<>$SP/f.md"
check deny "scratch-tee"           "echo x | tee $SP/f.txt"
check deny "scratch-sed-inplace"   "sed -i s/a/b/ $SP/f.md"
check deny "scratch-dd-of"         "echo x | dd of=$SP/f.md"
check deny "scratch-py-open"       "python3 -c 'open(\"$SP/f\",\"w\").write(\"x\")'"
check deny "scratch-lane-then-repo" "python3 eval.py > $SP/ok.json && echo done > status.md"
check deny "scratch-lane-then-repo-nl" "python3 eval.py > $SP/ok.json
echo done > status.md"
# a payload with no session_id gets the unmatchable sentinel: lane closed
out=$(jq -cn --arg c "echo x > $SP/f.json" '{tool_name:"Bash",tool_input:{command:$c}}' | bash "$HOOK")
if printf '%s' "$out" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1; then
  pass=$((pass+1))
else
  fail=$((fail+1)); echo "FAIL [scratch-no-session-id] expected deny, got: $out"
fi

# ---- non-Bash tools pass through untouched ----------------------------------
out=$(printf '{"tool_name":"Read","tool_input":{"file_path":"/tmp/x"}}' | bash "$HOOK")
if [ -z "$out" ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL [non-bash-passthrough] expected empty output, got: $out"; fi

# ---- deny output is valid harness JSON --------------------------------------
out=$(printf '{"tool_name":"Bash","tool_input":{"command":"cat > x"}}' | bash "$HOOK")
if printf '%s' "$out" | jq -e '.hookSpecificOutput.permissionDecision == "deny" and (.hookSpecificOutput.permissionDecisionReason | length > 0)' >/dev/null; then
  pass=$((pass+1))
else
  fail=$((fail+1)); echo "FAIL [deny-json-shape] $out"
fi

echo "----"
echo "passed=$pass failed=$fail"
[ "$fail" -eq 0 ]
