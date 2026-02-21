#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PATH="${1:-$ROOT/.venv}"

if [[ "$VENV_PATH" != /* ]]; then
  VENV_PATH="$ROOT/$VENV_PATH"
fi

if ! command -v python3.11 >/dev/null 2>&1; then
  if ! command -v brew >/dev/null 2>&1; then
    echo "python3.11 is required and Homebrew is not available." >&2
    exit 1
  fi
  echo "Installing python@3.11 via Homebrew"
  brew install python@3.11
fi

if [[ ! -d "$VENV_PATH" ]]; then
  echo "Creating virtual environment at $VENV_PATH"
  python3.11 -m venv "$VENV_PATH"
fi

# shellcheck disable=SC1091
source "$VENV_PATH/bin/activate"
python -m pip install --upgrade pip
python -m pip install -e "$ROOT[dev]"

echo "Bootstrap complete: $VENV_PATH"
