#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec uv run "$REPO/tools/build-semantic-bridge-2.1.226.py" "$@"
