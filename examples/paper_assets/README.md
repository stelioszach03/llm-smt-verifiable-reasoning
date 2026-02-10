# Paper Assets

This directory stores artefacts that can be regenerated from evaluation runs.

## Generating Figures

```bash
cegvr eval --problems data/toy/problems.jsonl --out runs/toy
cegvr make-figures --runs runs/toy --out examples/paper_assets/figures
```

The figure command will produce:

- `cert_vs_budget.png`
- `iterations_hist.png`
- `latency_vs_accuracy.png`

## Generating Tables

```bash
cegvr make-tables --runs runs/toy --out examples/paper_assets/tables
```

This command writes:

- `main_results.csv`
- `ablations.csv`
- `latex/tables/table_main.tex`

The CSV files can be ingested by pandas, Excel, or LaTeX. The LaTeX snippet uses
`pgfplotstable` for easy inclusion in a paper. Regenerate these assets whenever
new evaluation runs are available.
