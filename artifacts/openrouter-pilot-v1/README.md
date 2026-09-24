# Recorded candidate-verification pilot — 24 September 2026

**750 recorded cells, 739 completed executions, 11 deadline stops.** This is a 50-task × three-requested-seed × five-arm pilot, not the proposed 7,500-episode full study. Stopped episodes remain in the observed denominators; complete matrix coverage does not mean every episode finished normally or produced a correct answer.

## Finding

Core-ranked repair and repeated generation without feedback both certified **55/90 SAT candidates (61.1%)**. Their paired comparison has six wins in each direction and 78 ties. This pilot establishes neither an advantage nor statistical equivalence. Direct Z3 matched all **500/500** source-problem labels without model calls; the legacy always-UNSAT/then-copy-witness control also certified all 500. The LLM-assisted workflow has not demonstrated practical value over direct solving on these already formalized problems.

| Arm | SAT certificates / 90 | UNSAT certificates / 60 | Deadline stops |
|---|---:|---:|---:|
| One shot | 37 | 59 | 0 |
| Repeated generation, no feedback | 55 | 60 | 3 |
| Generic feedback | 52 | 60 | 3 |
| Conflict feedback | 50 | 60 | 3 |
| Core-ranked repair | 55 | 60 | 2 |

SAT assignment validity is the primary endpoint. UNSAT certification means Z3 checked infeasibility, not that the model supplied a proof. One-shot has a smaller generation allowance; equal multi-round caps do not imply equal actual cost. All source tasks were public synthetic development data. No confidence interval, significance, broad reasoning or clinical claim is made.

![SAT validity and accounted API cost](figures/sat-success-versus-cost.png)

## Cost and complete transport evidence

There were **4,453 recorded HTTP attempts**. Of these, 4,448 have measured provider usage and five have unknown usage after transport failures.

| Accounting component | USD |
|---|---:|
| Provider-reported known cost | 0.86185320 |
| Known rounding up to micro-USD | 0.00219380 |
| Retained uncertain reservations | 0.00348800 |
| **Conservative accounted total** | **0.86753500** |

The known token subtotal is **8,482,490** (2,408,705 prompt + 6,073,785 completion). The all-call total remains unknown for five calls. The 11 stopped episodes retain 83 measured calls and 217,186 tokens in their journals; these are recovered by the independent transport report even though no completed repair outcome exists. Provider cost reports are not invoices and exclude credit-purchase fees and VPS costs.

The [full transport reconciliation](transport-reconciliation.json) checks every request/response pair and separates rounding from uncertain reserves. The [primary analysis](analysis.json), [episode table](episodes.csv), [generated report](results.md), [direct-solver controls](direct_solver.json), [runtime environment](environment.json), and [figure hashes](figures/figure-provenance.json) remain separate from raw evidence.

## Frozen settings and operational amendment

The unchanged model was `openai/gpt-oss-20b`, pinned to CoreWeave/fp4, temperature 0.2, low reasoning effort, 2,048 maximum output tokens. Requested seeds were 17, 29 and 43. Multi-round arms allowed four rounds of four candidates; one-shot allowed one. Full solver SAT witnesses were withheld from primary feedback. The locally strict candidate contract rejects malformed types; all paid batch outputs are retained even when an earlier candidate succeeds.

The [original protocol](protocol.json) was published before study inference. Its 45-minute admission window recorded 379 cells. A [separate public operational amendment](../../docs/studies/OPENROUTER_PILOT1_AMENDMENT.md) allowed one additional 60-minute window for the 371 unlaunched cells, with the same original runtime, model parameters, task order and cumulative $3 cap. No existing failed or stopped episode was retried. This is an amended execution, not unchanged preregistration. Both wave manifests and prior evidence hashes are retained. No additional tail run occurred.

Evaluation runtime: `dc7b9de89f3a507705b259c870af82eda763621f`. Later analysis and typing-only commits do not replace that frozen runtime. A provider/quantization pin does not pin an immutable hosted weight revision, and requested seeds do not guarantee deterministic hosted outputs. See [provenance](provenance.json), [protocol](../../docs/studies/OPENROUTER_PILOT1.md), and [operational manifest](manifest.json).

## Raw archive and offline replay

[Download the complete raw archive](https://github.com/stelioszach03/llm-smt-verifiable-reasoning/releases/download/openrouter-pilot-v1/pilot1-final.tar.gz) (1,234,917 bytes; SHA-256 `e4045552a34163290be183f9475d7bbb4888f14dc9a4d048e6b3cf530a47f08f`). It contains 1,511 files with synthetic prompts, visible outputs, feedback, all generated candidates, usage and manifests. Authentication headers, credentials and hidden reasoning are excluded. All 758 original first-wave episode files were preserved byte-for-byte.

After verifying and extracting the archive into a fresh directory, analysis needs no credentials, model downloads or paid inference:

```sh
python scripts/analyze_openrouter_pilot.py /path/to/raw --output /new/analysis
python scripts/reconcile_pilot_transport.py /path/to/raw --output /new/transport.json \
  --source-archive /path/to/pilot1-final.tar.gz \
  --expected-archive-sha256 e4045552a34163290be183f9475d7bbb4888f14dc9a4d048e6b3cf530a47f08f
python scripts/plot_openrouter_pilot.py /new/analysis/analysis.json --output /new/figures
```

Use the repository's Python environment; dependencies are declared in `pyproject.toml`, with the measured operator environment pinned in `requirements-study.txt`. Do not overwrite raw data or selectively rerun failed cases. The public website is a separate deterministic verifier demo, maintained in the portfolio repository.
