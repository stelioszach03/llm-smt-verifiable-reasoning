# CEGVR

An LLM proposes a candidate solution to a constraint problem; Z3 either certifies it or returns an unsat-core. The study asks whether feeding that core back beats simply retrying the same number of times under an identical compute budget.

**[Live demo](https://stelioszach.com/demos/smt-verify/)**

[![CI](https://github.com/stelioszach03/llm-smt-verifiable-reasoning/actions/workflows/ci.yml/badge.svg)](https://github.com/stelioszach03/llm-smt-verifiable-reasoning/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-f59e0b?style=flat-square)](LICENSE)

Solo research project. **Manuscript only — not published, not peer-reviewed, not submitted.**

## Results

**The aggregate result tables from the full sweep are not in this repository, so the headline numbers cannot be verified from a clean checkout. They are therefore not printed here.** `/runs/` and `/tables/` were gitignored while the study ran, and the sweep executed on a Colab A100 whose tables were written to Google Drive. `.gitignore` now tracks `tables/**/*.csv`, so the next run commits its own evidence. Until then, treat any arm-level number quoted elsewhere as unverified.

What is verifiable from this repository today:

| Claim | Value | Evidence |
|---|---|---|
| Benchmark size | 500 linear-arithmetic problems | [`data/linear/problems.jsonl`](data/linear/problems.jsonl) — 500 lines |
| Evaluation runs in the full sweep | 500 × 3 seeds × 5 arms = 7,500 | [`scripts/run_all.sh`](scripts/run_all.sh) — `SEEDS=3`, 5 arms |
| Budget parameters | `--max-rounds 4 --budget 4 --timeout-ms 1500` | `scripts/run_all.sh` L35–38 |
| Statistical tests implemented | paired McNemar, Wilcoxon signed-rank | [`src/cegvr/tables/`](src/cegvr/tables/) |
| Test suite | 51 tests pass in 1.2 s | `PYTHONPATH=src pytest -q` |

The five arms (`one_shot`, `multi_no_feedback`, `multi_generic_feedback`, `multi_unsat_core_feedback`, `cd_vgs_core_rank`) share the same `K`, `R`, solver timeout, parsing rules and generation settings — only the feedback carried forward differs, so a win cannot be explained by "it just tried harder". [`index.html`](index.html) is committed but its numbers are hard-coded in a JS array, not read from a tracked artifact — same caveat.

## Run

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

PYTHONPATH=src pytest -q         # 51 passed in 1.2 s

cegvr eval --problems data/toy/problems.jsonl --out runs/toy \
  --seeds 1 --max-rounds 3 --budget 2 --timeout-ms 1500 --generator stub
cegvr summarize --runs runs/toy --table tables/toy/main_results.csv
```

The stub generator emits deliberately wrong candidates, so the smoke run certifies 0% — it exercises the loop, the Z3 bridge and aggregation, not model quality. Reproducing the real study needs a local OpenAI-compatible endpoint serving **Qwen3-30B-A3B** (a Mixture-of-Experts model with ~3 B active parameters, not a dense 30 B) on an A100 80 GB, then `bash scripts/run_all.sh`. The CLI default string `qwen3.5-35b-a3b` is only a label forwarded to the serving process; it does not name a released model.

## Limitations

- **The headline numbers are not reproducible offline.** No aggregate CSV is committed, so verifying any arm-level result requires re-running the sweep against a live endpoint.
- The candidate pipeline requires an LLM; the stub generator only implements the trace pipeline. There is no offline path to meaningful arm-level results.
- One model, one benchmark family — synthetic linear-arithmetic feasibility problems. Nothing shows the finding transfers to other model families or real constraint problems.
- UNSAT instances in this generator are trivially detectable, so UNSAT recall saturates and carries no signal; the informative quantity is SAT certification rate.
- The transfer sets are tiny — Sudoku 4×4 (6 problems), Latin-5 (4), scheduling (1). Appendix evidence, not a second benchmark.
- No human and no frontier-model baseline; the comparison is internal to the five arms.
- [`examples/paper_assets/latex/legacy_2025-10-11_llama3-8b.pdf`](examples/paper_assets/latex/legacy_2025-10-11_llama3-8b.pdf) is a superseded build describing a different, earlier experiment (llama.cpp Llama 3 8B, `certified_accuracy = 0.7`). It is kept under an explicit legacy filename. **Do not cite its numbers as current.**

## License

MIT — see [LICENSE](LICENSE).
