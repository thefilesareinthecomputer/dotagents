#!/usr/bin/env bash
# Claude Code status line - two lines.
# Line 1: [model] <cwd> ⎇ <git branch> <effort>
# Line 2: <context bar> <pct>% <used>/<window> ctx · $<cost> · session <5h%> · weekly <7d%>
# Input: statusLine JSON on stdin. Schema: https://code.claude.com/docs/en/statusline
# Every segment is optional and drops out when its field is absent (early
# session, no git repo, non-subscriber…). Rate-limit fields only appear after
# the first API response, so they degrade to "--" until then.

input=$(cat)

j() { printf '%s' "$input" | jq -r "$1 // empty"; }

reset=$'\033[0m'
bold=$'\033[1m'
dim=$'\033[2m'
green=$'\033[32m'
yellow=$'\033[33m'
red=$'\033[31m'
c_dir=$'\033[38;5;110m'      # steel blue
c_branch=$'\033[36m'         # cyan
c_effort=$'\033[38;5;244m'   # gray
c_cost=$'\033[38;5;137m'     # muted tan

# ── Line 1: identity ──
model=$(printf '%s' "$input" | jq -r '.model.display_name // .model.id // "?"')
l1="${dim}[${reset}${bold}${model}${reset}${dim}]${reset}"

# Working dir (basename).
cwd=$(j '.workspace.current_dir'); [ -z "$cwd" ] && cwd=$(j '.cwd')
[ -n "$cwd" ] && l1="$l1 ${c_dir}$(basename "$cwd")${reset}"

# Git branch (hidden outside a repo; short SHA on detached HEAD).
branch=""
if [ -n "$cwd" ] && [ -d "$cwd" ]; then
  branch=$(git -C "$cwd" --no-optional-locks branch --show-current 2>/dev/null)
  if [ -z "$branch" ] && git -C "$cwd" rev-parse --git-dir >/dev/null 2>&1; then
    branch=$(git -C "$cwd" rev-parse --short HEAD 2>/dev/null)
  fi
fi
[ -n "$branch" ] && l1="$l1 ${c_branch}⎇ ${branch}${reset}"

# Reasoning-effort level, when reported.
effort=$(j '.effort.level')
[ -n "$effort" ] && l1="$l1 ${c_effort}${effort}${reset}"

# ── Line 2: telemetry ──
ctx_pct=$(j '.context_window.used_percentage'); [ -z "$ctx_pct" ] && ctx_pct=0
ctx_pct_int=$(printf '%.0f' "$ctx_pct" 2>/dev/null || echo 0)
used_tok=$(j '.context_window.total_input_tokens')
ctx_size=$(j '.context_window.context_window_size')

# Bar color shifts green → yellow → red at 70% / 90%.
if   [ "$ctx_pct_int" -ge 90 ]; then ctx_color=$red
elif [ "$ctx_pct_int" -ge 70 ]; then ctx_color=$yellow
else                                 ctx_color=$green
fi

# Fixed-width bar of filled/empty blocks.
bar_width=16
filled=$(( ctx_pct_int * bar_width / 100 ))
[ "$filled" -gt "$bar_width" ] && filled=$bar_width
[ "$filled" -lt 0 ] && filled=0
bar=""; i=0
while [ "$i" -lt "$filled" ];    do bar="${bar}█"; i=$((i+1)); done
while [ "$i" -lt "$bar_width" ]; do bar="${bar}░"; i=$((i+1)); done

# Humanize a token count: 200000 -> 200k, 1000000 -> 1M.
hum() {
  local n="$1"
  if [ "$n" -ge 1000000 ] 2>/dev/null; then printf '%dM' $((n / 1000000))
  elif [ "$n" -ge 1000 ] 2>/dev/null;    then printf '%dk' $((n / 1000))
  else printf '%s' "$n"; fi
}

# Used/window token counts: "37k/200k ctx" (window-only when used is absent).
tok_seg=""
if [ -n "$used_tok" ] && [ -n "$ctx_size" ] && [ "$ctx_size" -gt 0 ] 2>/dev/null; then
  tok_seg=" ${dim}$(hum "$used_tok")/$(hum "$ctx_size") ctx${reset}"
elif [ -n "$ctx_size" ] && [ "$ctx_size" -gt 0 ] 2>/dev/null; then
  tok_seg=" ${dim}$(hum "$ctx_size") ctx${reset}"
fi

l2="${ctx_color}${bar} ${ctx_pct_int}%${reset}${tok_seg}"

# Session cost, when reported.
cost=$(j '.cost.total_cost_usd')
[ -n "$cost" ] && l2="$l2 ${dim}·${reset} ${c_cost}$(printf '$%.2f' "$cost")${reset}"

# Rate limits (session = 5h window, weekly = 7d window): "--" when absent,
# otherwise a colored integer pct (green < 75% < yellow < 90% < red).
fmt_rl() {
  local v="$1" n c
  if [ -z "$v" ]; then
    printf '%s--%s' "$dim" "$reset"
    return
  fi
  n=$(printf '%.0f' "$v" 2>/dev/null || echo 0)
  c=$green
  [ "$n" -ge 75 ] && c=$yellow
  [ "$n" -ge 90 ] && c=$red
  printf '%s%s%%%s' "$c" "$n" "$reset"
}
sess_h=$(fmt_rl "$(j '.rate_limits.five_hour.used_percentage')")
week_h=$(fmt_rl "$(j '.rate_limits.seven_day.used_percentage')")
l2="$l2 ${dim}· session${reset} ${sess_h} ${dim}· weekly${reset} ${week_h}"

printf '%s\n%s' "$l1" "$l2"
