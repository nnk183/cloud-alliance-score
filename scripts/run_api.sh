#!/usr/bin/env bash
# Launch the FastAPI server with uvicorn.
# Usage: ./scripts/run_api.sh [PORT]
set -euo pipefail

PORT="${1:-8000}"
cd "$(dirname "$0")/.."

exec uvicorn cloud_alliance_score.api:app \
  --app-dir src \
  --host 0.0.0.0 \
  --port "$PORT" \
  --reload
