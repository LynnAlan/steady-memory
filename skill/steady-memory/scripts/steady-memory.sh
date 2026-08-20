#!/usr/bin/env sh
set -eu

STEADY_PYTHON_BIN="${STEADY_PYTHON:-python3}"
exec "$STEADY_PYTHON_BIN" -m steady_memory "$@"
