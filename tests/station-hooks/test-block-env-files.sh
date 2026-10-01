#!/usr/bin/env bash
# Table-driven tests for the block-env-files PreToolUse hook.
# Target: ~/.claude/hooks/block-env-files.sh (per-machine, seeded from
# SPEC-CLAUDE-CODE.md §8). Run: bash tests/station-hooks/test-block-env-files.sh
# Exit 0 = all green; nonzero = failures listed.
#
# Contract: a file tool naming a dotenv file is DENIED; a Bash command that
# mentions one is ASKED, because the text may be a commit message, a pattern or
# a string literal rather than an access; the committed non-secret variants and
# everything else are silent.
set -u

HOOK="${HOOK_UNDER_TEST:-$HOME/.claude/hooks/block-env-files.sh}"
[ -f "$HOOK" ] || { echo "FATAL: hook not found at $HOOK"; exit 2; }
command -v jq >/dev/null 2>&1 || { echo "FATAL: jq required"; exit 2; }

pass=0; fail=0

# outcome(): the permissionDecision, or "silent" when the hook says nothing.
outcome() {
  local out
  out="$(printf '%s' "$1" | bash "$HOOK" 2>/dev/null)"
  [ -z "$out" ] && { echo "silent"; return; }
  printf '%s' "$out" | jq -r '.hookSpecificOutput.permissionDecision // "?"' 2>/dev/null
}

check() {
  local expected="$1" label="$2" payload="$3"
  local got; got="$(outcome "$payload")"
  if [ "$got" = "$expected" ]; then pass=$((pass+1));
  else fail=$((fail+1)); echo "FAIL [$label] expected=$expected got=$got"; fi
}

bash_payload() { jq -cn --arg c "$1" '{tool_name:"Bash",tool_input:{command:$c}}'; }
file_payload() { jq -cn --arg t "$1" --arg f "$2" '{tool_name:$t,tool_input:{file_path:$f}}'; }

# ---- file tools: DENY on the file itself ------------------------------------
check deny   "read-dotenv"        "$(file_payload Read /repo/.env)"
check deny   "edit-dotenv-local"  "$(file_payload Edit /repo/.env.local)"
check deny   "write-dotenv-prod"  "$(file_payload Write /repo/.env.production)"

# ---- file tools: the committed non-secret variants are silent ---------------
check silent "read-example"       "$(file_payload Read /repo/.env.example)"
check silent "read-sample"        "$(file_payload Read /repo/.env.sample)"
check silent "read-envrc"         "$(file_payload Read /repo/.envrc)"
check silent "read-environment"   "$(file_payload Read /repo/.environment.md)"
check deny   "grep-glob-dotenv"    '{"tool_name":"Grep","tool_input":{"pattern":"KEY","path":"config","glob":".env*"}}'

# ---- Bash: ASK, never deny - the text may not be an access ------------------
check ask    "bash-cat"           "$(bash_payload 'cat .env')"
check ask    "bash-cp-nested"     "$(bash_payload 'cp config/.env.local /tmp/x')"
check ask    "bash-commit-msg"    "$(bash_payload 'git commit -m "docs: mention .env handling"')"
check ask    "bash-string-literal" "$(bash_payload "python3 -c \"print('.env')\"")"

# ---- Bash: silent ----------------------------------------------------------
check silent "bash-example"       "$(bash_payload 'cat .env.example')"
check silent "bash-process-env"   "$(bash_payload 'grep -rn process.env src/')"
check silent "bash-plain"         "$(bash_payload 'git status --short')"

# ---- other tools and garbage: silent ---------------------------------------
check silent "agent-tool"         '{"tool_name":"Agent","tool_input":{"prompt":"read .env"}}'
check silent "garbage-payload"    'not even json'

echo
echo "block-env-files: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
