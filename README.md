# CEGVR — Counterexample-Grounded Verifiable Reasoning

A candidate-first LLM + SMT protocol for verifiable reasoning under strict
feedback-granularity control. A local LLM proposes a structured candidate
(either a full satisfying assignment or an UNSAT claim), and Z3 either
certifies it or returns an unsat-core that becomes natural-language hints
for the next round.

**Central question:** not *whether* an LLM can emit a candidate, but whether
**solver-grounded feedback** measurably improves verified performance over
mere repeated attempts under matched compute budgets.

- 📄 Working paper: `examples/paper_assets/latex/main.pdf`
- 🔬 Live page: <https://stelioszach.com/llm-smt-verifiable-reasoning/>
- 🧪 Python 3.11 · Z3 · llama.cpp · Qwen 3.5-35B
- 📦 One-command local paper pipeline

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.11-blue.svg)](./pyproject.toml)
[![Solver](https://img.shields.io/badge/solver-Z3-8b2f20.svg)](https://github.com/Z3Prover/z3)

---

## What's inside

CEGVR ships two parallel execution paths:

- A **candidate-first linear pipeline** — the main Q1-style study.
- A preserved **trace-based compatibility layer** — retained for Sudoku,
  scheduling, and extension work (appendix transfer evidence).

The main paper protocol studies a **five-method linear matrix**:

| # | Method                     | Role                                                                 |
|---|----------------------------|----------------------------------------------------------------------|
| 1 | `one_shot`                 | Single attempt. Retained as a *repair-gain* reference point.         |
| 2 | `multi_no_feedback`        | Compute-matched retries, independent sampling. No feedback carried.  |
| 3 | `multi_generic_feedback`   | Same budget + a generic "your prior answer was wrong" hint.          |
| 4 | `multi_unsat_core_feedback`| Same budget + the unsat-core as a natural-language hint.             |
| 5 | `cd_vgs_core_rank` 🏆       | **Flagship.** Conflict-directed verifier-guided search with CoreRank.|

The primary causal comparison is among the four compute-matched multi-round
methods, which share identical `K`, `R`, timeouts, parsing rules, and
generation settings. Retry baselines differ **only** in carried-forward
verifier feedback; `cd_vgs_core_rank` redistributes the same `K × R` budget
via conflict-directed search and unsat-core ranking.

## Requirements

- Python 3.11
- macOS with Homebrew (for the bootstrap script) — Linux also supported
- A local OpenAI-compatible endpoint (llama.cpp is the documented default)

## Local bootstrap

```bash
bash scripts/bootstrap_local_mac.sh .venv
source .venv/bin/activate
```

This installs Python 3.11 if needed, creates `.venv`, and installs the
project in editable mode with dev dependencies.

## Serve Qwen locally (llama.cpp)

The paper path expects an OpenAI-compatible chat-completions endpoint:

```bash
llama-server \
  -m /path/to/qwen3.5-35b-a3b.gguf \
  --port 8000 \
  --ctx-size 8192
```

The default endpoint used by the CLI and `run_all.sh` is
`http://127.0.0.1:8000/v1/chat/completions`. The candidate-first path uses
`enable_thinking=false` by default.

## One-command paper run

```bash
bash scripts/run_all.sh
```

Useful options:

```bash
bash scripts/run_all.sh --seeds 3 --max-rounds 4 --budget 4 --timeout-ms 1500
bash scripts/run_all.sh \
  --llm-model qwen3.5-35b-a3b \
  --llm-endpoint http://127.0.0.1:8000/v1/chat/completions
```

The script:

- bootstraps the local Python environment
- regenerates the linear dataset
- runs the 5-method candidate-first linear study
- runs a small Sudoku 4×4 appendix transfer check (trace layer)
- regenerates tables, figures, and LaTeX assets (and the PDF)

The main paper path **fails closed** if the local endpoint is unavailable.
There is no silent stub fallback for the linear paper study.

## Run a single arm

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

### Candidate contract

The generator returns either a full satisfying assignment:

```json
{ "status": "sat", "assignment": { "x1": 3, "x2": 1 } }
```

or an UNSAT claim:

```json
{ "status": "unsat" }
```

### Result schema

Per-problem JSONL rows expose:

- `pipeline`, `arm`, `predicted_status`, `verified_outcome`, `failure_type`
- `solver_calls`, `llm_attempts`, `llm_latency_ms`, `solver_latency_ms`
- token counts, `problem_features`
- `feedback_source`, `search_policy`, `search_score`, `repeat_failure_count`
- `core_variables`, `variables_to_revise`, `variables_to_keep_fixed`

## Legacy trace pipeline

The original trace-based architecture is still supported and remains the
right entry point for compatibility and research extensions:

```bash
cegvr eval \
  --pipeline trace \
  --generator llm-sudoku \
  --problems data/sudoku4/problems.jsonl \
  --out runs/sudoku_appendix/feedback \
  --seeds 1 --max-rounds 3 --budget 1 --timeout-ms 1500 \
  --llm-endpoint http://127.0.0.1:8000/v1/chat/completions \
  --llm-model qwen3.5-35b-a3b
```

Toy commands like `cegvr gen-toy` and `cegvr solve-toy` are unchanged.

## Tables and figures

Generate arm-level tables and plots from any run root:

```bash
cegvr summarize   --runs runs/linear_main --table tables/linear/main_results.csv
cegvr make-tables --runs runs/linear_main --out examples/paper_assets/tables_linear
cegvr make-figures --runs runs/linear_main --out examples/paper_assets/figures_linear
```

The figure set:

- `arm_verified_solve_rate.png`
- `convergence_by_round.png`
- `efficiency_frontier.png`

Arm-centric tables backed by:

- verified solve rate
- SAT certification rate
- UNSAT precision / recall
- solver calls per certified solve
- latency mean / p95
- repair gain vs `one_shot`
- paired McNemar and Wilcoxon comparisons across the compute-matched arms

## Dataset generation

Regenerate the linear benchmark:

```bash
python scripts/build_linear_dataset.py --total 500 --sat-ratio 0.6 --seed 7
```

Each record carries difficulty metadata: `n_vars`, `n_constraints`,
`constraint_to_var_ratio`, `coeff_max_abs`, `offline_solver_time_ms`,
`unsat_core_size`, `difficulty_bin`.

## Tests

```bash
source .venv/bin/activate
pytest -q
```

The repo keeps regression coverage for:

- the candidate-side verifier and arm isolation logic
- the preserved trace repair loop and solver stack
- property-based tests over linear constraints (Hypothesis)

## Project layout

```
src/cegvr/
├── cli.py                # Typer CLI entry point
├── config.py             # AppConfig + YAML loader
├── candidate/            # candidate-first repair + verifier
├── engine/               # trace-based repair + metrics
├── generation/           # prompts, providers, llama.cpp adapters
├── smt/                  # Z3 encoder + runner
├── grammar/              # strict JSON-schema validation
├── eval/                 # run harness + aggregation
├── plots/ tables/ report/
├── robustness/           # perturbation runner + deltas
└── utils/

scripts/                  # dataset gen + run_all.sh
examples/paper_assets/    # LaTeX + figures + tables
tests/                    # pytest suite
```

## License

MIT — see [`LICENSE`](./LICENSE). Part of the **Aegis** portfolio suite:

- [Graph Fraud GNN](https://stelioszach.com/aegis-graph-fraud-gnn/) — GNN-based payment fraud
- [NYC Subway Anomaly](https://stelioszach.com/nyc-subway-anomaly/) — streaming anomaly detection
- [AML Graph Investigator](https://stelioszach.com/aegis-graph-aml/) — graph-native AML case explainer
- [DeID Privacy Studio](https://stelioszach.com/aegis-deid/) — policy-governed PHI/PII redaction
- **CEGVR** — this repo (No. 05)

Authored by **Stelios Zacharioudakis** — CS, NKUA Athens.
