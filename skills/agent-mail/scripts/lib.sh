#!/usr/bin/env bash
# lib.sh - shared helpers for agent-mail. Sourced by send.sh / mark.sh / inbox.sh.
# Targets darwin/BSD userland: BSD `stat -f`, `date -u`, `awk` (never `sed -i`).

AM_ROOTS=(.claude .agents .cursor)   # recognized agent-tooling roots

# am_die EXIT TOKEN MESSAGE - emit a machine token + human message on stderr, exit.
am_die() { printf '%s: %s\n' "$2" "$3" >&2; exit "$1"; }

# am_now_ts  -> YYYYMMDDHHMMSS (UTC)        am_now_iso -> ISO-8601 UTC
am_now_ts()  { date -u +%Y%m%d%H%M%S; }
am_now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# am_canon DIR - canonical absolute path of an existing directory (resolves .., symlinks).
am_canon() { ( cd "$1" 2>/dev/null && pwd -P ); }

# am_valid_name NAME - agent/recipient names: alnum, dash, underscore, dot only.
am_valid_name() { case "$1" in ''|*[!A-Za-z0-9._-]*) return 1;; *) return 0;; esac; }

# am_yaml_escape STR - print a YAML-safe double-quoted scalar; reject control chars.
am_yaml_escape() {
  local s="$1"
  # Reject control chars (C0 0x00-0x1F + DEL 0x7F) - newlines/CR/tab break the
  # envelope. Keep ONLY control bytes via tr, then test; the trailing `printf X`
  # sentinel stops $() from stripping a lone-newline residue. High bytes (UTF-8)
  # are intentionally allowed, so Unicode subjects survive.
  if [ "$(printf '%s' "$s" | LC_ALL=C tr -dc '\000-\037\177'; printf X)" != X ]; then
    am_die 9 INVALID_FIELD "value contains control characters / newlines"
  fi
  s="${s//\\/\\\\}"   # escape backslashes first
  s="${s//\"/\\\"}"   # then double-quotes
  printf '"%s"' "$s"
}

# am_slug STR - lowercase kebab slug, alnum only, max 40 chars.
am_slug() {
  printf '%s' "$1" \
    | LC_ALL=C tr '[:upper:]' '[:lower:]' \
    | LC_ALL=C tr -c 'a-z0-9' '-' \
    | sed -E 's/-+/-/g; s/^-//; s/-$//' \
    | cut -c1-40
}

# am_detect_roots REPO - echo each recognized root that exists (one per line).
am_detect_roots() {
  local r
  for r in "${AM_ROOTS[@]}"; do [ -d "$1/$r" ] && printf '%s\n' "$r"; done
}

# am_root_report REPO - human report of every present root: inbox?, contents, recency.
am_root_report() {
  local repo="$1" r dir count newest nm
  while IFS= read -r r; do
    [ -n "$r" ] || continue
    dir="$repo/$r"
    count=$(find "$dir" -type f 2>/dev/null | wc -l | tr -d ' ')
    nm=$([ -d "$dir/inbox" ] && echo yes || echo no)
    newest=$(find "$dir" -type f -print0 2>/dev/null \
             | xargs -0 stat -f '%m %N' 2>/dev/null | sort -rn | head -1)
    printf '  %-8s  inbox:%-3s  files:%-4s' "$r" "$nm" "$count"
    if [ -n "$newest" ]; then
      printf '  newest: %s (%s)\n' \
        "$(printf '%s' "$newest" | cut -d' ' -f2-)" \
        "$(date -r "$(printf '%s' "$newest" | cut -d' ' -f1)" -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)"
    else
      printf '  (empty)\n'
    fi
  done < <(am_detect_roots "$repo")
  echo "  note: recency is a weak hint - git/cp/rsync rewrite mtimes."
}

# am_seed_seq INBOX TS - seed NNN: (count of files already using TS) + 1.
am_seed_seq() {
  local inbox="$1" ts="$2" n=0 f
  shopt -s nullglob
  for f in "$inbox/${ts}-"*.md "$inbox/processed/${ts}-"*.md; do n=$((n+1)); done
  shopt -u nullglob
  echo $((n+1))
}
