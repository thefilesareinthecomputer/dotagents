#!/usr/bin/env bash
set -euo pipefail

python3 manage.py migrate --noinput
exec python3 manage.py runserver 0.0.0.0:8000
