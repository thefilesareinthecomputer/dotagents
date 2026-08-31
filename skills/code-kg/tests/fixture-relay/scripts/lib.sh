announce() {
  echo "==> $1" >&2
}

require_binary() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required binary: $1" >&2
    exit 1
  fi
}
