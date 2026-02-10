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

  --seeds <int>        Number of random seeds (default: 3)
  --max-rounds <int>   Maximum rounds per seed (default: 5)
  --budget <int>       Certification budget (default: 2)
  --timeout-ms <int>   Timeout per attempt in milliseconds (default: 2000)
  --venv <path>        Virtual environment directory (default: .venv)
  --clean              Remove existing generated artifacts before running
  --skip-tests         Skip running test and coverage suites
  --skip-ablations     Skip ablation experiments
  --skip-robustness    Skip robustness evaluation
  --skip-latex         Skip LaTeX build
  -h, --help           Show this help and exit
EOF
}

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"

if [[ -n "$GIT_ROOT" && -f "$GIT_ROOT/pyproject.toml" ]]; then
  ROOT="$GIT_ROOT"
else
  ROOT="$SCRIPT_ROOT"
fi

cd "$ROOT"

SEEDS=3
MAX_ROUNDS=5
BUDGET=2
TIMEOUT_MS=2000
CLEAN=0
SKIP_TESTS=0
SKIP_ABLATIONS=0
SKIP_ROBUSTNESS=0
SKIP_LATEX=0
VENV_PATH=".venv"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --seeds)
      [[ $# -ge 2 ]] || abort "--seeds requires a value"
      SEEDS="$2"
      shift 2
      ;;
    --max-rounds)
      [[ $# -ge 2 ]] || abort "--max-rounds requires a value"
      MAX_ROUNDS="$2"
      shift 2
      ;;
    --budget)
      [[ $# -ge 2 ]] || abort "--budget requires a value"
      BUDGET="$2"
      shift 2
      ;;
    --timeout-ms)
      [[ $# -ge 2 ]] || abort "--timeout-ms requires a value"
      TIMEOUT_MS="$2"
      shift 2
      ;;
    --venv)
      [[ $# -ge 2 ]] || abort "--venv requires a value"
      VENV_PATH="$2"
      shift 2
      ;;
    --clean)
      CLEAN=1
      shift
      ;;
    --skip-tests)
      SKIP_TESTS=1
      shift
      ;;
    --skip-ablations)
      SKIP_ABLATIONS=1
      shift
      ;;
    --skip-robustness)
      SKIP_ROBUSTNESS=1
      shift
      ;;
    --skip-latex)
      SKIP_LATEX=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      abort "Unknown argument: $1"
      ;;
  esac
done

if [[ "$VENV_PATH" = /* ]]; then
  VENV_DIR="$VENV_PATH"
else
  VENV_DIR="$ROOT/$VENV_PATH"
fi

if [[ $CLEAN -eq 1 ]]; then
  log "Cleaning previous artifacts"
  rm -rf "$ROOT/runs" "$ROOT/tables" \
    "$ROOT/examples/paper_assets/figures" \
    "$ROOT/examples/paper_assets/tables" \
    "$ROOT/reports/case_studies.md"
fi

log "Step A: Environment setup"
log "Preparing directories"
mkdir -p "$ROOT/runs" "$ROOT/tables" "$ROOT/reports" \
  "$ROOT/examples/paper_assets/figures" \
  "$ROOT/examples/paper_assets/tables"

log "Using virtual environment at $VENV_DIR"
if [[ ! -d "$VENV_DIR" ]]; then
  log "Creating virtual environment"
  python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

log "Upgrading pip"
python -m pip install --upgrade pip >/dev/null

log "Installing project dependencies via make install"
make install

log "Installing pre-commit hooks"
if ! command -v pre-commit >/dev/null 2>&1; then
  log "pre-commit not found; installing"
  python -m pip install pre-commit
fi
pre-commit install

if [[ $SKIP_TESTS -eq 0 ]]; then
  log "Running test suite"
  make test

  log "Running coverage suite"
  if ! make cov; then
    log "WARNING: Coverage command reported issues (continuing anyway)"
  fi
else
  log "Skipping tests and coverage as requested"
fi

log "Sanity check: cegvr --help"
cegvr --help >/dev/null

log "Step B: Toy dataset sanity checks"
cegvr data-stats --path data/toy/problems.jsonl
cegvr gen-toy --n 10 --out data/toy/generated.jsonl

  log "Step C: Main evaluation"
  cegvr eval \
    --problems data/toy/problems.jsonl \
    --out runs/toy \
    --seeds "$SEEDS" \
    --max-rounds "$MAX_ROUNDS" \
    --budget "$BUDGET" \
    --timeout-ms "$TIMEOUT_MS"

log "Summarizing evaluation results"
cegvr summarize --runs runs/toy --table tables/main_results.csv

log "Step D: Generating tables and figures (toy only)"
cegvr make-tables --runs runs/toy --out examples/paper_assets/tables
  cegvr make-figures --runs runs/toy --out examples/paper_assets/figures

VARIANTS=(toy)

if [[ $SKIP_ABLATIONS -eq 0 ]]; then
  log "Step E: Running ablations"
  cegvr eval --problems data/toy/problems.jsonl --out runs/nosolver --no-solver
  VARIANTS+=(nosolver)

  cegvr eval --problems data/toy/problems.jsonl --out runs/nogrammar --no-grammar
  VARIANTS+=(nogrammar)

  cegvr eval --problems data/toy/problems.jsonl --out runs/norepair --no-repair
  VARIANTS+=(norepair)

  COMBINED_RUNS="$ROOT/runs/_combined"
  log "Combining run artifacts for ablation summaries at $COMBINED_RUNS"
  rm -rf "$COMBINED_RUNS"
  mkdir -p "$COMBINED_RUNS"

  for variant in "${VARIANTS[@]}"; do
    VARIANT_DIR="$ROOT/runs/$variant"
    if [[ ! -d "$VARIANT_DIR" ]]; then
      continue
    fi
    shopt -s nullglob
    for run_file in "$VARIANT_DIR"/seed_*.jsonl; do
      base="$(basename "$run_file")"
      cp "$run_file" "$COMBINED_RUNS/seed_${variant}_${base}"
    done
    shopt -u nullglob
  done

  log "Regenerating tables and figures with ablation runs"
  cegvr make-tables --runs "$COMBINED_RUNS" --out examples/paper_assets/tables
  cegvr make-figures --runs "$COMBINED_RUNS" --out examples/paper_assets/figures
else
  log "Skipping ablations as requested"
fi

if [[ $SKIP_ROBUSTNESS -eq 0 ]]; then
  log "Step F: Robustness evaluation"
  cegvr robustness --problems data/toy/problems.jsonl --out runs/robust --variants 3
else
  log "Skipping robustness evaluation as requested"
fi

# --- Linear (LLM) evaluation and assets ---
log "Step G: Linear dataset (SMT-LIB) preparation"
if [[ ! -f data/linear/problems.jsonl ]]; then
  if [[ -f "$HOME/datasets/linear_smt.zip" ]]; then
    python scripts/convert_linear_smt.py --archive "$HOME/datasets/linear_smt.zip" --output data/linear/problems.jsonl || true
  else
    log "linear_smt.zip not found (expected at ~/datasets). Using existing data/linear if present."
  fi
fi

log "Step H: Linear dataset evaluation with LLM (if server available)"
LLM_ENDPOINT="http://127.0.0.1:8000/v1/chat/completions"
if curl -s --max-time 2 "$LLM_ENDPOINT" >/dev/null; then
  log "Detected local LLM server at $LLM_ENDPOINT"
  cegvr eval \
    --problems data/linear/problems.jsonl \
    --out runs/linear_llm_llm \
    --seeds 1 \
    --max-rounds 3 \
    --budget 1 \
    --timeout-ms 1500 \
    --generator llm \
    --llm-endpoint "$LLM_ENDPOINT" \
    --llm-model llama-3-8b-instruct || true
else
  log "LLM server not reachable; falling back to stub generator for linear set"
  cegvr eval --problems data/linear/problems.jsonl --out runs/linear --seeds 1 --max-rounds 1 --budget 1 --timeout-ms 1500 || true
fi

log "Step I: Linear dataset tables/figures"
mkdir -p tables/linear
# Summarize whichever run exists
if [[ -d runs/linear_llm_llm ]]; then
  cegvr summarize --runs runs/linear_llm_llm --table tables/linear/main_results.csv || true
  cegvr make-figures --runs runs/linear_llm_llm --out examples/paper_assets/figures_linear || true
elif [[ -d runs/linear ]]; then
  cegvr summarize --runs runs/linear --table tables/linear/main_results.csv || true
  cegvr make-figures --runs runs/linear --out examples/paper_assets/figures_linear || true
fi

log "Step G: Exporting case studies"
cegvr export-cases --runs runs/toy --out reports/case_studies.md --n 4

if [[ $SKIP_LATEX -eq 0 ]]; then
  log "Step H: Building LaTeX assets"
  make -C examples/paper_assets/latex
else
  log "Skipping LaTeX build as requested"
fi

SUMMARY_PATHS=()

shopt -s nullglob
prefix="$ROOT/"
for run_path in "$ROOT"/runs/*; do
  relative_path=${run_path#$prefix}
  SUMMARY_PATHS+=("$relative_path")
done
shopt -u nullglob

if [[ ${#SUMMARY_PATHS[@]} -eq 0 ]]; then
  SUMMARY_PATHS+=("runs/")
fi

SUMMARY_PATHS+=(
  "tables/main_results.csv"
  "tables/linear/main_results.csv"
  "examples/paper_assets/tables"
  "examples/paper_assets/figures_linear"
  "examples/paper_assets/figures"
  "reports/case_studies.md"
)

if [[ $SKIP_LATEX -eq 0 ]]; then
  SUMMARY_PATHS+=("examples/paper_assets/latex/main.pdf")
else
  log "LaTeX artifacts skipped; rerun without --skip-latex to build PDF"
fi

log "Pipeline complete. Summary of generated artifacts:"
for summary_path in "${SUMMARY_PATHS[@]}"; do
  printf '  - %s\n' "$summary_path"
done

log "Done"
