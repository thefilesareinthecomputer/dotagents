#!/usr/bin/env bash
# Table-driven tests for the ask-clipboard-reads PreToolUse hook.
# Target: the repo's hooks/ask-clipboard-reads.sh by default; HOOK_UNDER_TEST points the
# run at a station copy such as ~/.claude/hooks/ask-clipboard-reads.sh.
# Run: bash tests/station-hooks/test-ask-clipboard-reads.sh
# Exit 0 = all green; nonzero = failures listed.
#
# Contract: a Bash command whose text reads the clipboard, or names a clipboard
# reader, is ASKED, since the clipboard may hold a password the user just copied.
# Writing the clipboard (pbcopy), the word "clipboard" alone, and every other tool
# are silent.
set -u

REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="${HOOK_UNDER_TEST:-$REPO/hooks/ask-clipboard-reads.sh}"
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

# ---- reads: ASK ---------------------------------------------------------------
check ask    "pbpaste"              "$(bash_payload 'pbpaste')"
check ask    "pbpaste-in-pipe"      "$(bash_payload 'pbpaste | wc -c')"
check ask    "pbpaste-substituted"  "$(bash_payload 'echo "$(pbpaste)"')"
check ask    "pbpaste-abs-path"     "$(bash_payload '/usr/bin/pbpaste -Prefer txt')"
check ask    "applescript-get"      "$(bash_payload "osascript -e 'get the clipboard'")"
check ask    "applescript-info"     "$(bash_payload "osascript -e 'clipboard info'")"
check ask    "applescript-caps"     "$(bash_payload "osascript -e 'return THE CLIPBOARD as text'")"
check ask    "jxa-nspasteboard"     "$(bash_payload "osascript -l JavaScript -e '\$.NSPasteboard.generalPasteboard'")"
check ask    "python-pyperclip"     "$(bash_payload 'python3 -c "import pyperclip; print(pyperclip.paste())"')"
check ask    "node-clipboardy"      "$(bash_payload 'node -e "require(\"clipboardy\").readSync()"')"
check ask    "linux-xclip"          "$(bash_payload 'xclip -selection clipboard -o')"
check ask    "linux-wl-paste"       "$(bash_payload 'wl-paste')"
check ask    "powershell"           "$(bash_payload 'pwsh -c Get-Clipboard')"

# ---- writes, mentions and other tools: SILENT -----------------------------------
check silent "pbcopy-write"         "$(bash_payload 'printf hi | pbcopy')"
check silent "word-clipboard"       "$(bash_payload 'echo copied to the system clipboard buffer list')"
check silent "plain-command"        "$(bash_payload 'ls -la')"
check silent "pbpastel-substring"   "$(bash_payload 'echo pbpastel')"
check silent "read-tool"            "$(jq -cn '{tool_name:"Read",tool_input:{file_path:"/tmp/pbpaste.txt"}}')"
check silent "garbage-input"        "not json"

echo "ask-clipboard-reads: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
