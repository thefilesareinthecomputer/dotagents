announce() {
  echo "==> $1"
}

retry_thrice() {
  for _ in 1 2 3; do
    "$@" && return 0
  done
  return 1
}
