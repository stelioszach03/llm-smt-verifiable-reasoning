# CEGVR — does solver feedback actually help an LLM, or is it just more retries?

An LLM proposes a candidate solution to a constraint problem; Z3 either certifies it or
returns an unsat-core. The experiment asks whether feeding that unsat-core back is
better than simply retrying the same number of times.

[![CI](https://github.com/stelioszach03/llm-smt-verifiable-reasoning/actions/workflows/ci.yml/badge.svg)](https://github.com/stelioszach03/llm-smt-verifiable-reasoning/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-f59e0b?style=flat-square)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square)](https://www.python.org/)

Solo research project by Stelios Zacharioudakis.
**Manuscript only — not published, not peer-reviewed, not submitted.**

---

## The experimental design (this is the point of the repo)

Five arms share an **identical compute budget** — same `K` candidates per round, same `R`
rounds, same solver timeout, same parsing rules, same generation settings. The only thing
that varies is *what feedback is carried forward*:

| # | Arm | What it gets |
|---|---|---|
| 1 | `one_shot` | one attempt — repair-gain reference point |
| 2 | `multi_no_feedback` | budget-matched retries, independent sampling |
| 3 | `multi_generic_feedback` | + a generic "your previous answer was wrong" hint |
| 4 | `multi_unsat_core_feedback` | + the Z3 unsat-core rendered as a natural-language hint |
| 5 | `cd_vgs_core_rank` | same budget, redistributed by conflict-directed search + CoreRank |

Arms 2–5 are the causal comparison. Arm 1 exists only to measure how much repair buys at all.
Because the budget is matched, a win for arm 4 or 5 cannot be explained by "it just tried harder".

## Results

**The aggregate result tables from the full run are not in this repository, so the headline
numbers cannot be verified from a clean checkout. They are therefore not printed here.**

`/runs/` and `/tables/` were gitignored while the study was run, and the sweep was executed on
a Colab A100 whose run logs and aggregate tables were written to Google Drive. `.gitignore` has been
changed so that `tables/**/*.csv` is now tracked — the next run commits its own evidence
automatically. Until then, treat every arm-level number quoted elsewhere (site, slides, CV)
as unverified.

What **is** verifiable from this repository today:

| Claim | Value | Evidence in this repo |
|---|---|---|
| Benchmark size | 500 linear-arithmetic problems | [`data/linear/problems.jsonl`](data/linear/problems.jsonl) — 500 lines |
| Evaluation runs in the full sweep | 500 × 3 seeds × 5 arms = **7,500** | [`scripts/run_all.sh`](scripts/run_all.sh) — `SEEDS=3`, `ARMS=(5)` |
| Budget parameters | `--max-rounds 4 --budget 4 --timeout-ms 1500` | [`scripts/run_all.sh`](scripts/run_all.sh) L35–38 |
| Statistical tests implemented | paired McNemar (solved-within-budget), Wilcoxon signed-rank (latency, solver calls) | [`src/cegvr/tables/`](src/cegvr/tables/), [`examples/paper_assets/latex/sections/results.tex`](examples/paper_assets/latex/sections/results.tex) |
| Test suite | **51 tests pass** in 1.1 s | `PYTHONPATH=src pytest -q` |
| Type checking | clean over 44 source files | `mypy --config-file mypy.ini src` |
| Robustness deltas | coefficient scaling / constraint permutation / variable relabeling | [`fig_robustness.png`](fig_robustness.png), [`src/cegvr/robustness/`](src/cegvr/robustness/) |

An interactive results page ([`index.html`](index.html)) is committed, but its numbers are
hard-coded into a JavaScript array rather than read from a tracked artifact — same caveat.

### Stale build in the repo

[`examples/paper_assets/latex/legacy_2025-10-11_llama3-8b.pdf`](examples/paper_assets/latex/legacy_2025-10-11_llama3-8b.pdf)
is a **superseded** build from 2025-10-11. It describes a different, earlier experiment
(local llama.cpp Llama 3 8B Instruct Q4_K_M, `--max-rounds 3 --budget 1`), reports
`certified_accuracy = 0.7`, and concludes that certification stays comparable to one-shot
baselines. It is kept under an explicit legacy filename so the history is visible.
**Do not cite its numbers as current.** The current `main.tex` describes the 5-arm study.

## Quickstart — verified on macOS 15 / Python 3.11

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

PYTHONPATH=src pytest -q                    # 51 passed in ~1 s
```

A full end-to-end smoke run on the toy dataset, no GPU and no LLM required
(**~3.5 s**, uses the stub generator on the trace pipeline):

```bash
cegvr eval --problems data/toy/problems.jsonl --out runs/toy \
  --seeds 1 --max-rounds 3 --budget 2 --timeout-ms 1500 --generator stub
cegvr summarize --runs runs/toy --table tables/toy/main_results.csv
```

The stub generator emits deliberately wrong candidates, so this run certifies 0 % — it
exercises the loop, the Z3 bridge and the aggregation path, not model quality.

## Reproducing the real study

Requires a local OpenAI-compatible chat-completions endpoint. The study used
**Qwen3-30B-A3B** (a Mixture-of-Experts model with ~3 B active parameters, not a dense 30 B)
served locally, on an A100 80 GB.

> Note on the model identifier: the CLI default is the string `qwen3.5-35b-a3b`, which is
> only a label forwarded to the serving process — it does not name a released model. The
> weights actually served were `Qwen/Qwen3-30B-A3B`. The default string is left unchanged
> so old commands still reproduce, but the model to quote is Qwen3-30B-A3B.

```bash
llama-server -m /path/to/qwen3-30b-a3b.gguf --port 8000 --ctx-size 8192

bash scripts/run_all.sh          # 5 arms × 3 seeds × 500 problems, then tables + figures
```

Single arm:

```bash
cegvr eval --pipeline candidate --arm cd_vgs_core_rank --generator llm \
  --problems data/linear/problems.jsonl --out runs/linear_main/cd_vgs_core_rank \
  --seeds 3 --max-rounds 4 --budget 4 --timeout-ms 1500 \
  --llm-endpoint http://127.0.0.1:8000/v1/chat/completions \
  --llm-model qwen3-30b-a3b --no-llm-enable-thinking
```

If the endpoint is unreachable the CLI now **aborts with exit code 3** instead of writing a
run in which every candidate is recorded as a schema failure — that silent all-zero run was
indistinguishable from a real measurement.

## What this does not do

- **The headline numbers are not reproducible offline.** No aggregate CSV is committed yet,
  so verifying any arm-level result requires re-running the sweep against a live endpoint.
- **The candidate pipeline requires an LLM.** `--pipeline candidate --generator stub` is
  rejected; the stub generator only implements the trace pipeline. There is no offline path
  that produces meaningful arm-level results.
- **One model, one benchmark family.** Everything was measured on Qwen3-30B-A3B over
  synthetic linear-arithmetic feasibility problems generated by
  `scripts/build_linear_dataset.py`. Nothing here shows the finding transfers to other model
  families, to natural-language reasoning, or to real-world constraint problems.
- **UNSAT instances are easy in this benchmark.** The generator emits problems whose UNSAT
  half is trivially detectable, so UNSAT recall saturates and carries no signal. The
  informative quantity is the SAT certification rate.
- **The transfer sets are tiny** — Sudoku 4×4 (6 problems), Latin-5 (4), scheduling (1).
  They are descriptive appendix evidence, not a second benchmark.
- **No human baseline, no frontier-model baseline.** The comparison is internal to the five
  arms.
- Latency numbers include local serving overhead and are not comparable across machines.

## How it works

```
problem (JSONL)
      │
      ▼
  prompt  ──►  local LLM  ──►  JSON candidate  ──►  grammar/schema check
                                                          │
                                                          ▼
                                                     Z3 encoder
                                                          │
                                        ┌─────────────────┴──────────────────┐
                                     certified                          unsat-core
                                        │                                    │
                                       done                    rendered as NL hint,
                                                               ranked by CoreRank,
                                                               fed into next round
```

The generator returns either `{"status":"sat","assignment":{...}}` or `{"status":"unsat"}`.
Nothing is trusted: Z3 decides.

## Repo layout

```
src/cegvr/
├── cli.py             # Typer CLI
├── candidate/         # candidate-first repair loop + verifier (the main study)
├── engine/            # legacy trace-based repair loop (appendix transfer)
├── generation/        # prompts, providers, llama.cpp adapters, JSON guard
├── smt/               # Z3 encoder + runner
├── grammar/           # strict JSON-schema validation of candidates
├── eval/              # run harness + aggregation
├── tables/ plots/ report/
└── robustness/        # perturbation families + delta computation

data/linear/problems.jsonl     # 500-problem benchmark (committed)
scripts/run_all.sh             # full sweep: dataset → 5 arms → tables → figures → LaTeX
examples/paper_assets/         # LaTeX manuscript source + generated figures
tests/                         # 18 files, incl. Hypothesis property tests
```

9,021 lines of Python. `Dockerfile` and `.devcontainer/` are provided; CI runs ruff, mypy
and pytest on every push.

## License

MIT — see [`LICENSE`](LICENSE).
