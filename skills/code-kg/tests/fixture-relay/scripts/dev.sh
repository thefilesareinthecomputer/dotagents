#!/usr/bin/env bash
# Local dev loop: api on one port, static web on another.
set -euo pipefail

source scripts/lib.sh

require_binary python3

export RELAY_LOG_LEVEL=debug

python3 -m relay.cli serve --port 8420 &
API_PID=$!
trap 'kill $API_PID' EXIT

announce "api on :8420, web on :8421"
python3 -m http.server 8421 --directory web/public
