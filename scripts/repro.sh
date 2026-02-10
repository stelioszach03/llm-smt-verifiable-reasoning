#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

python -m pip install --upgrade pip
python -m pip install -e .[dev]

pytest

cegvr eval --problems data/toy/problems.jsonl --out runs/toy
cegvr make-figures --runs runs/toy --out examples/paper_assets/figures
cegvr make-tables --runs runs/toy --out examples/paper_assets/tables
