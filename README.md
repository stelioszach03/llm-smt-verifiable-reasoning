# LLM + SMT Verifiable Reasoning (CEGVR)

CEGVR now ships with two parallel execution paths:

- A **candidate-first linear paper pipeline** for the main Q1-style study.
- A preserved **trace-based compatibility/research layer** for toy, Sudoku, scheduling, and extension work.

The main paper protocol studies a five-method linear matrix:

- `one_shot`
- `multi_no_feedback`
- `multi_generic_feedback`
- `multi_unsat_core_feedback`
- `cd_vgs_core_rank`

The primary causal comparison is among the four compute-matched multi-round methods. The new flagship method, `cd_vgs_core_rank`, uses conflict-directed verifier-guided search over the same fixed `K * R` attempt budget. The linear benchmark is the main results section; Sudoku 4x4 is kept as appendix transfer evidence through the preserved trace layer.

## Requirements

- Python 3.11
- macOS with Homebrew for the bootstrap script
- a local OpenAI-compatible endpoint
- `llama.cpp` is the documented default backend

## Local Bootstrap

Create a local environment with the provided Mac bootstrap helper:

```bash
bash scripts/bootstrap_local_mac.sh .venv
source .venv/bin/activate
```

This installs Python 3.11 if needed, creates `.venv`, and installs the project in editable mode with dev dependencies.

## Local llama.cpp + Qwen

The paper path expects an OpenAI-compatible chat-completions endpoint. A typical local setup is:

```bash
llama-server \
  -m /path/to/qwen3.5-35b-a3b.gguf \
  --port 8000 \
  --ctx-size 8192
```

Then the default endpoint used by the CLI and `run_all.sh` is:

```text
http://127.0.0.1:8000/v1/chat/completions
```

The candidate-first paper path uses `enable_thinking=false` by default.

## One-Command Local Paper Run

Run the linear-first paper pipeline plus the Sudoku appendix experiment:

```bash
bash scripts/run_all.sh
```

Useful options:

```bash
bash scripts/run_all.sh --seeds 3 --max-rounds 4 --budget 4 --timeout-ms 1500
bash scripts/run_all.sh --llm-model qwen3.5-35b-a3b --llm-endpoint http://127.0.0.1:8000/v1/chat/completions
```

The script:

- bootstraps the local Python environment
- regenerates the linear dataset
- runs the 5-method candidate-first linear study
- runs a small Sudoku appendix transfer check on the preserved trace layer
- regenerates tables, figures, and LaTeX assets

The main paper path **fails closed** if the local endpoint is unavailable. There is no silent stub fallback for the linear paper study.

## Candidate-First Linear Pipeline

Run a single arm manually:

```bash
cegvr eval \
  --pipeline candidate \
  --arm cd_vgs_core_rank \
  --generator llm \
  --problems data/linear/problems.jsonl \
  --out runs/linear_main/cd_vgs_core_rank \
  --seeds 3 \
  --max-rounds 4 \
  --budget 4 \
  --timeout-ms 1500 \
  --llm-endpoint http://127.0.0.1:8000/v1/chat/completions \
  --llm-model qwen3.5-35b-a3b \
  --no-llm-enable-thinking
```

The candidate contract is:

```json
{
  "status": "sat",
  "assignment": {
    "x1": 3,
    "x2": 1
  }
}
```

or:

```json
{
  "status": "unsat"
}
```

The result JSONL now includes:

- `pipeline`
- `arm`
- `predicted_status`
- `verified_outcome`
- `failure_type`
- `solver_calls`
- `llm_attempts`
- `llm_latency_ms`
- `solver_latency_ms`
- token counts
- `problem_features`
- `feedback_source`
- `search_policy`
- `search_score`
- `repeat_failure_count`
- `core_variables`
- `variables_to_revise`
- `variables_to_keep_fixed`

## Legacy Trace Pipeline

The original trace-based architecture is still supported and remains the right entrypoint for compatibility and research extensions:

```bash
cegvr eval \
  --pipeline trace \
  --generator llm-sudoku \
  --problems data/sudoku4/problems.jsonl \
  --out runs/sudoku_appendix/feedback \
  --seeds 1 \
  --max-rounds 3 \
  --budget 1 \
  --timeout-ms 1500 \
  --llm-endpoint http://127.0.0.1:8000/v1/chat/completions \
  --llm-model qwen3.5-35b-a3b
```

Toy commands such as `cegvr gen-toy` and `cegvr solve-toy` are unchanged.

## Tables and Figures

Generate arm-level tables and plots from any run root:

```bash
cegvr summarize --runs runs/linear_main --table tables/linear/main_results.csv
cegvr make-tables --runs runs/linear_main --out examples/paper_assets/tables_linear
cegvr make-figures --runs runs/linear_main --out examples/paper_assets/figures_linear
```

The figure set is:

- `arm_verified_solve_rate.png`
- `convergence_by_round.png`
- `efficiency_frontier.png`

The table set is arm-centric and backed by:

- verified solve rate
- SAT certification rate
- UNSAT precision / recall
- solver calls per certified solve
- latency mean / p95
- repair gain vs one-shot
- paired McNemar and Wilcoxon comparisons across the compute-matched arms

## Dataset Generation

Regenerate the linear benchmark:

```bash
python scripts/build_linear_dataset.py --total 500 --sat-ratio 0.6 --seed 7
```

The regenerated dataset now carries difficulty metadata such as:

- `n_vars`
- `n_constraints`
- `constraint_to_var_ratio`
- `coeff_max_abs`
- `offline_solver_time_ms`
- `unsat_core_size`
- `difficulty_bin`

## Tests

Run the full test suite:

```bash
source .venv/bin/activate
pytest -q
```

The repo keeps regression coverage for both:

- the new candidate-side verifier and arm isolation logic
- the preserved trace repair loop and solver stack
