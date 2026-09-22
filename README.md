# CEGVR — LLM candidates with SMT verification

An experimental toolkit for testing whether solver feedback helps a language model propose valid solutions to formal constraint problems. A generator proposes a candidate; Z3 checks the encoded constraints; a repair loop can return structured feedback for another attempt.

**Status:** research prototype. Included write-ups are unpublished drafts. There is no verified headline performance result in this checkout.

## What can be checked here

- A tracked synthetic linear-arithmetic dataset of 500 problems.
- Candidate-first and trace-based pipelines, five comparison arms, solver budgets and local OpenAI-compatible generator adapters.
- Offline stub runs, unit/property tests, aggregation and paired-test implementations.
- Tiny Sudoku, Latin-square and scheduling examples for exercising adapters.

`scripts/run_all.sh` specifies a planned matrix of 500 problems × three seeds × five arms. A script specifying 7,500 evaluations is not evidence they completed. The full sweep's aggregate CSVs and raw records are absent. Do not quote arm-level performance, statistical significance or superiority from historical prose or the former hard-coded demo values.

The one-shot arm is a single-attempt reference. Multi-round arms have configured round/candidate caps; equal caps are not a measurement of equal wall-clock or token cost. Solver verification only establishes the supplied formal constraints, not the correctness of a natural-language problem interpretation.

## Offline quick start

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
cegvr eval --problems data/toy/problems.jsonl --out runs/toy \
  --seeds 1 --max-rounds 3 --budget 2 --timeout-ms 1500 --generator stub
cegvr summarize --runs runs/toy --table tables/toy/main_results.csv
```

The stub exercises parsing, verification and reporting. Its result is not an LLM benchmark. No provider key or model download is required for this check.

For model experiments, run an OpenAI-compatible server under your control and explicitly pass its endpoint and **actual served model ID**. CLI defaults are configuration strings, not evidence of a loaded or evaluated model. Review `bash scripts/run_all.sh --help` before launching the full sweep; it can train no model itself but makes many inference calls and writes output datasets/artifacts.

## Limits

- Missing aggregate sweep artifacts prevent verification of previous headline results.
- Synthetic linear feasibility is narrow; tiny transfer sets do not establish general reasoning ability.
- UNSAT instances in the supplied generator are simple; aggregate solve rate alone can hide weak SAT assignment performance.
- A solver timeout is unknown, not a proof of infeasibility. Model output is untrusted input.
- The linear adapter rejects malformed provider JSON and nonfinite assignments; tests use mocks, not a live model service.
- The [legacy PDF](examples/paper_assets/latex/legacy_2025-10-11_llama3-8b.pdf) describes a different experiment and is retained only as historical material. It is not evidence for the current pipeline.

[MIT license](LICENSE).
