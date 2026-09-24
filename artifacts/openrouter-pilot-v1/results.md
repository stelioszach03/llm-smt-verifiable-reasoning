# CEGVR OpenRouter pilot - recorded results

Coverage: **750 / 750** frozen episodes; study status: **complete**.

Descriptive hash-selected pilot from an already public synthetic dataset. STOP/error episodes are observed unsuccessful executions; unlaunched cells remain missing. Paired summaries use shared observed problem/seed identities only, with no independent-seed, causal or significance claim. Certificates concern formal constraints, not natural-language semantics or LLM proof construction. Exact solver witnesses are withheld from primary feedback.

A post-freeze operational admission-window extension is disclosed separately from the original protocol; this is not an unchanged preregistered execution. The original task matrix and endpoint definition remain identifiable. Complete matrix coverage means a record exists for every cell, not that every episode ended normally. Stopped/error episodes are operationally unsuccessful and retained in the observed certification rate under this execution; their unsuccessful status is not attributed to model quality.

Recorded statuses: complete=739, stopped=11, error=0. The observed certificate rate includes operational stops/errors and does not isolate model quality.

No population confidence interval or statistical-significance claim is reported. Missing metrics remain unmeasured, not zero.

## Post-freeze operational extension

Original admission window: 2700 seconds; additional admission window: 3600 seconds.

Published amendment reference: https://github.com/stelioszach03/llm-smt-verifiable-reasoning/commit/b057c46452dc0082c51359f210d88b26022ef496.

Amendment SHA-256: `c919cc21b18a887c40eb18a2cf76db234f483b154283b5f796322f68e7c0cc56`.

This operational change is disclosed after the original freeze; it is not described as unchanged preregistration. Old stopped/error records remain visible. No replacement of the primary denominator or model-quality claim is made.

## Primary: valid SAT assignments

| Arm | Observed / planned | Certified | Observed rate | Stopped / error | Accounted cost / observed | Provider calls |
|---|---:|---:|---:|---:|---:|---:|
| one_shot | 90/90 | 37 | 41.1% | 0/0 | $0.000226 | 90 |
| multi_no_feedback | 90/90 | 55 | 61.1% | 3/0 | $0.002298 | 823 |
| multi_generic_feedback | 90/90 | 52 | 57.8% | 3/0 | $0.002288 | 837 |
| multi_unsat_core_feedback | 90/90 | 50 | 55.6% | 3/0 | $0.002324 | 848 |
| cd_vgs_core_rank | 90/90 | 55 | 61.1% | 2/0 | $0.002278 | 835 |

## Secondary: solver-certified UNSAT claims

| Arm | Observed / planned | Certified | Observed rate | Stopped / error | Accounted cost / observed | Provider calls |
|---|---:|---:|---:|---:|---:|---:|
| one_shot | 60/60 | 59 | 98.3% | 0/0 | $0.000030 | 60 |
| multi_no_feedback | 60/60 | 60 | 100.0% | 0/0 | $0.000077 | 240 |
| multi_generic_feedback | 60/60 | 60 | 100.0% | 0/0 | $0.000077 | 240 |
| multi_unsat_core_feedback | 60/60 | 60 | 100.0% | 0/0 | $0.000077 | 240 |
| cd_vgs_core_rank | 60/60 | 60 | 100.0% | 0/0 | $0.000077 | 240 |

## Secondary: fixed-mixture overall certification

| Arm | Observed / planned | Certified | Observed rate | Stopped / error | Accounted cost / observed | Provider calls |
|---|---:|---:|---:|---:|---:|---:|
| one_shot | 150/150 | 96 | 64.0% | 0/0 | $0.000148 | 150 |
| multi_no_feedback | 150/150 | 115 | 76.7% | 3/0 | $0.001409 | 1063 |
| multi_generic_feedback | 150/150 | 112 | 74.7% | 3/0 | $0.001404 | 1077 |
| multi_unsat_core_feedback | 150/150 | 110 | 73.3% | 3/0 | $0.001425 | 1088 |
| cd_vgs_core_rank | 150/150 | 115 | 76.7% | 2/0 | $0.001398 | 1075 |

All launched stopped/error episodes remain in observed denominators. An observed rate from a partial matrix is not a completed-study rate. Solver-only and witness-copy controls are separately retained in analysis.json and are not pooled with model arms.

Accounted cost minus the known provider-reported cost subtotal. This margin combines per-call rounding up to micro-USD and any retained reservations for calls with unknown cost; it is not an estimate of unconfirmed charges. Unknown provider cost remains null.

Outcome usage_complete covers generated proposals only. Complete provider-attempt token totals additionally require one recorded HTTP call per generated proposal; retries/extra calls make that total null unless independently reconstructed. Known generated-token subtotals remain separate and exclude discarded transport attempts.

Provider-reported known cost subtotals, accounting margins, uncertain call counts, missing token usage, unused generated candidates and paired common-observation counts are explicit in analysis.json. Three requested seeds are repeated executions of the same problems, not three independent datasets. Exact seeds are requested, not proof of provider determinism.
