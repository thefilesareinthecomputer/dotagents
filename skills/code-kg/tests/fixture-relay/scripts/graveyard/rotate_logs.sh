# Retired in 0.2 when telemetry moved to stderr JSON. Kept "just in case",
# referenced by nothing - the fixture's true unreachable file.
rotate() {
  local dir="$1"
  find "$dir" -name '*.log' -mtime +7 -delete
}

rotate /var/log/relay
