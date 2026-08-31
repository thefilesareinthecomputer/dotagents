#!/usr/bin/env bash
# Build and tag a release image. CI calls this; humans rarely should.
set -euo pipefail

source scripts/lib.sh

require_binary docker
require_binary git

VERSION=$(git describe --tags --always)
announce "building relay:${VERSION}"

docker build -t "relay:${VERSION}" .
announce "built relay:${VERSION}"
