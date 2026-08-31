#!/usr/bin/env bash
# Claude Code subagent status line: one rendered row per running background
# task / subagent, shown in the agent panel under the main status line.
# Renders: <status icon> <name> <elapsed> · <tokens> <trend> - <description>
# Input: JSON on stdin - {columns, tasks:[{id,name,type,status,description,
# label,startTime,tokenCount,tokenSamples,cwd}]}. startTime is unix ms.
# Output: one JSON line per row: {"id": "<task-id>", "content": "<ANSI text>"}.
# Schema: https://code.claude.com/docs/en/statusline (subagentStatusLine)

input=$(cat)

cols=$(printf '%s' "$input" | jq -r '.columns // 120')
now_ms=$(($(date +%s) * 1000))

reset=$'\033[0m'
dim=$'\033[2m'
green=$'\033[32m'
yellow=$'\033[33m'
red=$'\033[31m'
cyan=$'\033[36m'

# Humanize a token count: 1234 -> 1.2k, 1200000 -> 1.2M.
fmt_tok() {
  local t="$1"
  if [ "$t" -ge 1000000 ] 2>/dev/null; then
    printf '%d.%dM' $((t / 1000000)) $(((t % 1000000) / 100000))
  elif [ "$t" -ge 1000 ] 2>/dev/null; then
    printf '%d.%dk' $((t / 1000)) $(((t % 1000) / 100))
  else
    printf '%s' "$t"
  fi
}

# Humanize elapsed ms: 83000 -> 1m23s, 3700000 -> 1h1m.
fmt_elapsed() {
  local ms="$1" s m h
  s=$((ms / 1000))
  if [ "$s" -ge 3600 ]; then
    h=$((s / 3600)); m=$(((s % 3600) / 60)); printf '%dh%dm' "$h" "$m"
  elif [ "$s" -ge 60 ]; then
    m=$((s / 60)); printf '%dm%ds' "$m" $((s % 60))
  else
    printf '%ds' "$s"
  fi
}

printf '%s' "$input" | jq -c '.tasks[]?' | while IFS= read -r task; do
  id=$(printf '%s' "$task" | jq -r '.id // empty')
  [ -z "$id" ] && continue
  name=$(printf '%s' "$task" | jq -r '.label // .name // "agent"')
  status=$(printf '%s' "$task" | jq -r '.status // "running"')
  desc=$(printf '%s' "$task" | jq -r '.description // ""')
  start=$(printf '%s' "$task" | jq -r '.startTime // 0')
  tok=$(printf '%s' "$task" | jq -r '.tokenCount // 0')

  # Status icon + color.
  case "$status" in
    running) icon="●" color="$green" ;;
    idle)    icon="◐" color="$yellow" ;;
    done)    icon="✓" color="$dim" ;;
    error)   icon="✗" color="$red" ;;
    *)       icon="○" color="$dim" ;;
  esac

  # Elapsed since startTime (unix ms); hidden when startTime absent.
  elapsed=""
  if [ "$start" -gt 0 ] 2>/dev/null && [ "$now_ms" -gt "$start" ]; then
    elapsed=" $(fmt_elapsed $((now_ms - start)))"
  fi

  # Token usage with trend arrow from the last two samples.
  tok_seg=""
  if [ "$tok" -gt 0 ] 2>/dev/null; then
    trend=$(printf '%s' "$task" | jq -r \
      'if (.tokenSamples | length) >= 2 and .tokenSamples[-1] > .tokenSamples[-2] then "↑" else "" end')
    tok_seg=" · $(fmt_tok "$tok") tok${trend}"
  fi

  # Truncate the description so the row fits the panel width; the prefix
  # (icon + name + elapsed + tokens) is budgeted at ~40 visible chars.
  desc_seg=""
  if [ -n "$desc" ]; then
    max=$((cols - 40)); [ "$max" -lt 10 ] && max=10
    [ "${#desc}" -gt "$max" ] && desc="${desc:0:$((max - 1))}…"
    desc_seg=" ${dim}- ${desc}${reset}"
  fi

  content=$(printf '%s%s%s %s%s%s%s%s%s%s%s' \
    "$color" "$icon" "$reset" \
    "$cyan" "$name" "$reset" \
    "$dim" "$elapsed" "$tok_seg" "$reset" \
    "$desc_seg")

  jq -cn --arg id "$id" --arg c "$content" '{id:$id, content:$c}'
done
