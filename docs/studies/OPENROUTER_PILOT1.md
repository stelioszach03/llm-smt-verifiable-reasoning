# Prospective OpenRouter pilot 1

This study plans **50 public synthetic problems × three requested seeds × five arms = 750 episodes**. It is separate from the previously proposed 7,500-episode sweep. Its primary endpoint is complete, solver-verified SAT assignments (30 problems × three repetitions per arm). The 20 UNSAT problems are reported separately: Z3 verifies infeasibility; an LLM claim is not an LLM-produced proof.

The exact matrix, source and dataset hashes, provider configuration, ordering and stopping rules are recorded in `openrouter-pilot1-frozen.json` before study inference. Selection takes the 30 SAT and 20 UNSAT IDs with smallest SHA-256 of `cegvr-pilot-v1|<problem_id>` from the unchanged 500-problem dataset. These public development data are not a new held-out benchmark. No training or fine-tuning is performed.

## Method

All arms use `openai/gpt-oss-20b` through `coreweave/fp4`, temperature 0.2, low reasoning effort and 2,048 maximum output tokens. Provider fallback is disabled; actual returned identity is checked. Requested seeds 17, 29 and 43 are deterministically combined with problem ID and candidate ordinal, without arm identity. Requested seeds do not guarantee hosted-model determinism or immutable weights.

The one-shot reference generates one candidate. Each of the other four arms may generate four batches of four candidates: no feedback, generic feedback, constraint-core feedback, and core-ranked feedback. All paid candidates are retained and accounted, including candidates generated before an earlier member of the same batch succeeds. Equal generation caps do not mean equal measured cost. Solver timeout is 1,500 ms per candidate.

Primary feedback withholds complete solver SAT witnesses. The model sees only problem variables, constraints and permitted prior-candidate feedback, never ground-truth labels, label-bearing task IDs or oracle assignments. CoreWeave does not implement JSON Schema `if`/`then`; the transport uses compatible shape constraints and the local strict validator enforces the complete SAT/UNSAT contract. Hidden reasoning is not parsed as an answer or stored.

A separate zero-LLM control checks all 500 problems directly with Z3 and tests the legacy always-UNSAT/then-copy-witness strategy. This exposes the solver-assistance confound instead of crediting the model for an oracle answer.

## Operational bounds and evidence

Eight isolated worker processes run on the existing portfolio VPS. The unchanged shared Forge research ledger accounts for every request. An additional **$3 ceiling** applies to this study; uncertain calls retain their conservative reservation. Credit-purchase fees are excluded from provider-reported inference cost. Only HTTP 429 is retried, at most twice after two/four seconds; all attempts count. Permanent request/access errors stop the study. There is no public paid endpoint.

A 45-minute deadline stops new request admission; in-flight requests drain within bounded transport timeouts. An outer systemd service limit is 50 minutes. Any unlaunched matrix cells remain missing. Failed or stopped episodes are retained; they are never rerun selectively or converted into successful replacements.

Each episode preserves request prompts/configuration, visible responses, HTTP failures, usage, conservative accounting, all generated candidates, solver history and final outcomes. Source/runtime hashes and the published protocol hash must match at launch. Analysis is written separately from immutable raw data. Run the offline analyzer with:

```sh
python scripts/analyze_openrouter_pilot.py /path/to/study --output /new/analysis-directory
```

Report SAT, UNSAT and mixed endpoints separately, including missing coverage, all actual calls/costs, token-measurement coverage and unused generated candidates. Paired task/seed comparisons are descriptive, with problem counts and no significance claim. Three repetitions are not three independent datasets. Negative or null findings remain in the report. Direct solving may outperform the LLM-assisted workflow; this narrow synthetic study cannot establish general reasoning or industrial utility.

## Compatibility preflight

Before freezing, three requests using the original conditional schema received HTTP 400. After removing unsupported server-side `if`/`then`, two tiny, non-study SAT/UNSAT requests returned valid visible JSON from the expected model/provider. An operator smoke fixture used strict `>` unsupported by the local verifier; its original failure was retained and its recorded UNSAT answer was checked offline using the equivalent integer `>= 6` constraint. No study task was evaluated or selected using these preflights. Their records and costs are separate from the primary study.

Official references: [OpenRouter provider controls](https://openrouter.ai/docs/guides/routing/provider-selection), [parameter semantics](https://openrouter.ai/docs/api_reference/parameters), [endpoint metadata](https://openrouter.ai/api/v1/models/openai/gpt-oss-20b/endpoints). The dated provider snapshot is retained alongside the freeze.
