# Evaluation protocol and report templates

No completed five-arm model study is available in this checkout. The planned
500-problem, three-seed, five-arm sweep totals 7,500 evaluations; a script and
report template are not evidence that it ran. The former PDF and result images
were removed from the current branch because the underlying records needed to
verify them are unavailable. Historical files remain in Git history.

Before launching a model study, fix the dataset hash, actual served model,
provider/engine version, decoding parameters, seeds, time/token/cost limits and
failure handling. Equal round/candidate caps do not establish equal realized
compute cost. Run the offline stub and parser/verifier tests first. The full
`scripts/run_all.sh` pipeline makes inference requests and is not a smoke test.

After a real run, retain per-problem records with actual model outputs, solver
outcomes, repair steps, errors, usage and elapsed time. Derive every table and
figure from those records. Report SAT assignment and UNSAT outcomes separately,
include timeouts/invalid outputs, and keep exploratory transfer tasks distinct
from the primary comparison.

Example artifact commands, **only after the corresponding runs exist**:

```bash
cegvr summarize --runs runs/linear_main --table tables/linear/main_results.csv
cegvr make-tables --runs runs/linear_main --out examples/paper_assets/tables_linear
cegvr make-figures --runs runs/linear_main --out examples/paper_assets/figures_linear
```

The LaTeX directory is a protocol template with an explicit results-pending
section. A compiled template must not be presented as a research result.
