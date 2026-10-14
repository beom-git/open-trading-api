#!/usr/bin/env bash
# Restriction is inherited by backend auth and every KIS request.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export KIS_PAPER_ONLY=1
exec bash "$SCRIPT_DIR/start.sh"
