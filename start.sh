#!/usr/bin/env sh
set -eu

REPO_DIR="${REPO_DIR:-/app}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

cd "$REPO_DIR"

if ! command -v git >/dev/null 2>&1; then
  echo "git is required but not installed."
  exit 1
fi

if [ ! -d ".git" ]; then
  echo "No .git directory found in $REPO_DIR."
  exit 1
fi

git pull --ff-only

PYTHON_BIN="python"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
fi

cd backend
exec "$PYTHON_BIN" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
