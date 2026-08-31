#!/usr/bin/env bash
set -euo pipefail

source scripts/common.sh

announce "deploying"
python3 app/main.py
