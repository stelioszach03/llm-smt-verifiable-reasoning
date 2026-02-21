#!/usr/bin/env bash
set -Eeuo pipefail

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

abort() {
  printf '[%s] ERROR: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: run_all.sh [options]

  --seeds <int>          Number of random seeds (default: 3)
  --max-rounds <int>     Max rounds for the multi-round linear study arms (default: 4)
  --budget <int>         Candidates per round for the multi-round linear study arms (default: 4)
  --timeout-ms <int>     Solver timeout per candidate (default: 1500)
  --llm-endpoint <url>   OpenAI-compatible local endpoint (default: http://127.0.0.1:8000/v1/chat/completions)
  --llm-model <id>       Model identifier (default: qwen3.5-35b-a3b)
  --venv <path>          Virtual environment directory (default: .venv)
  --clean                Remove generated runs/tables/figures before running
  --skip-tests           Skip the pytest suite
  --skip-latex           Skip LaTeX build
  -h, --help             Show this help and exit
EOF
}

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$SCRIPT_ROOT"
cd "$ROOT"

SEEDS=3
MAX_ROUNDS=4
BUDGET=4
TIMEOUT_MS=1500
LLM_ENDPOINT="http://127.0.0.1:8000/v1/chat/completions"
LLM_MODEL="qwen3.5-35b-a3b"
VENV_PATH=".venv"
CLEAN=0
SKIP_TESTS=0
SKIP_LATEX=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --seeds) SEEDS="$2"; shift 2 ;;
    --max-rounds) MAX_ROUNDS="$2"; shift 2 ;;
    --budget) BUDGET="$2"; shift 2 ;;
    --timeout-ms) TIMEOUT_MS="$2"; shift 2 ;;
    --llm-endpoint) LLM_ENDPOINT="$2"; shift 2 ;;
    --llm-model) LLM_MODEL="$2"; shift 2 ;;
    --venv) VENV_PATH="$2"; shift 2 ;;
    --clean) CLEAN=1; shift ;;
    --skip-tests) SKIP_TESTS=1; shift ;;
    --skip-latex) SKIP_LATEX=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) abort "Unknown argument: $1" ;;
  esac
done

if [[ "$VENV_PATH" != /* ]]; then
  VENV_PATH="$ROOT/$VENV_PATH"
fi

if [[ $CLEAN -eq 1 ]]; then
  log "Cleaning previous generated artifacts"
  rm -rf "$ROOT/runs" "$ROOT/tables" \
    "$ROOT/examples/paper_assets/figures_linear" \
    "$ROOT/examples/paper_assets/figures_sudoku_appendix" \
    "$ROOT/examples/paper_assets/tables_linear" \
    "$ROOT/examples/paper_assets/tables_sudoku_appendix"
fi

mkdir -p "$ROOT/runs" "$ROOT/tables" \
  "$ROOT/examples/paper_assets/figures_linear" \
  "$ROOT/examples/paper_assets/figures_sudoku_appendix" \
  "$ROOT/examples/paper_assets/tables_linear" \
  "$ROOT/examples/paper_assets/tables_sudoku_appendix"

log "Bootstrapping local Python environment"
bash "$ROOT/scripts/bootstrap_local_mac.sh" "$VENV_PATH"
# shellcheck disable=SC1091
source "$VENV_PATH/bin/activate"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

if [[ $SKIP_TESTS -eq 0 ]]; then
  log "Running test suite"
  make test
else
  log "Skipping tests"
fi

log "Checking local llama.cpp/Qwen endpoint"
if ! curl -s --max-time 2 "$LLM_ENDPOINT" >/dev/null; then
  abort "Local endpoint not reachable at $LLM_ENDPOINT. Start llama.cpp with your Qwen model first."
fi

log "Rebuilding linear benchmark dataset"
python "$ROOT/scripts/build_linear_dataset.py" --total 500 --sat-ratio 0.6 --seed 7 --output "$ROOT/data/linear/problems.jsonl"

LINEAR_RUN_ROOT="$ROOT/runs/linear_main"
mkdir -p "$LINEAR_RUN_ROOT"
ARMS=(
  "one_shot"
  "multi_no_feedback"
  "multi_generic_feedback"
  "multi_unsat_core_feedback"
  "cd_vgs_core_rank"
)

log "Running linear candidate-first paper matrix"
for arm in "${ARMS[@]}"; do
  arm_out="$LINEAR_RUN_ROOT/$arm"
  mkdir -p "$arm_out"
  log "Arm: $arm"
  cegvr eval \
    --pipeline candidate \
    --arm "$arm" \
    --generator llm \
    --problems "$ROOT/data/linear/problems.jsonl" \
    --out "$arm_out" \
    --seeds "$SEEDS" \
    --max-rounds "$MAX_ROUNDS" \
    --budget "$BUDGET" \
    --timeout-ms "$TIMEOUT_MS" \
    --llm-endpoint "$LLM_ENDPOINT" \
    --llm-model "$LLM_MODEL" \
    --no-llm-enable-thinking
done

log "Summarizing and plotting linear paper results"
mkdir -p "$ROOT/tables/linear"
cegvr summarize --runs "$LINEAR_RUN_ROOT" --table "$ROOT/tables/linear/main_results.csv"
cegvr make-tables --runs "$LINEAR_RUN_ROOT" --out "$ROOT/examples/paper_assets/tables_linear" --latex "$ROOT/examples/paper_assets/latex/tables_linear"
cegvr make-figures --runs "$LINEAR_RUN_ROOT" --out "$ROOT/examples/paper_assets/figures_linear"

log "Running Sudoku appendix transfer evidence on the preserved trace layer"
SUDOKU_RUN_ROOT="$ROOT/runs/sudoku_appendix"
mkdir -p "$SUDOKU_RUN_ROOT"
cegvr eval \
  --pipeline trace \
  --generator llm-sudoku \
  --problems "$ROOT/data/sudoku4/problems.jsonl" \
  --out "$SUDOKU_RUN_ROOT/one_shot" \
  --seeds 1 \
  --max-rounds 1 \
  --budget 1 \
  --timeout-ms "$TIMEOUT_MS" \
  --llm-endpoint "$LLM_ENDPOINT" \
  --llm-model "$LLM_MODEL"
cegvr eval \
  --pipeline trace \
  --generator llm-sudoku \
  --problems "$ROOT/data/sudoku4/problems.jsonl" \
  --out "$SUDOKU_RUN_ROOT/feedback" \
  --seeds 1 \
  --max-rounds 3 \
  --budget 1 \
  --timeout-ms "$TIMEOUT_MS" \
  --llm-endpoint "$LLM_ENDPOINT" \
  --llm-model "$LLM_MODEL"
cegvr summarize --runs "$SUDOKU_RUN_ROOT" --table "$ROOT/tables/sudoku_appendix_results.csv"
cegvr make-tables --runs "$SUDOKU_RUN_ROOT" --out "$ROOT/examples/paper_assets/tables_sudoku_appendix" --latex "$ROOT/examples/paper_assets/latex/tables_sudoku_appendix"
cegvr make-figures --runs "$SUDOKU_RUN_ROOT" --out "$ROOT/examples/paper_assets/figures_sudoku_appendix"

if [[ $SKIP_LATEX -eq 0 ]]; then
  log "Building LaTeX paper assets"
  make -C "$ROOT/examples/paper_assets/latex"
else
  log "Skipping LaTeX build"
fi

log "Pipeline complete"
printf '  - %s\n' \
  "runs/linear_main" \
  "runs/sudoku_appendix" \
  "tables/linear/main_results.csv" \
  "tables/sudoku_appendix_results.csv" \
  "examples/paper_assets/tables_linear" \
  "examples/paper_assets/figures_linear" \
  "examples/paper_assets/tables_sudoku_appendix" \
  "examples/paper_assets/figures_sudoku_appendix"
