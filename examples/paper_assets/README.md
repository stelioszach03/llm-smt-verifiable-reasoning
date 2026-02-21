# Paper Assets

The paper assets are now aligned to the linear-first candidate study and the Sudoku appendix transfer run.

## Linear Main Assets

Generate from the 5-method candidate study:

```bash
cegvr summarize --runs runs/linear_main --table tables/linear/main_results.csv
cegvr make-tables --runs runs/linear_main --out examples/paper_assets/tables_linear
cegvr make-figures --runs runs/linear_main --out examples/paper_assets/figures_linear
```

Main linear figures:

- `arm_verified_solve_rate.png`
- `convergence_by_round.png`
- `efficiency_frontier.png`

Main linear tables:

- `main_results.csv`
- `ablations.csv`
- `difficulty_breakdown.csv`
- `latex/tables_linear/table_main.tex`

## Sudoku Appendix Assets

Generate from the preserved trace-layer appendix run:

```bash
cegvr summarize --runs runs/sudoku_appendix --table tables/sudoku_appendix_results.csv
cegvr make-tables --runs runs/sudoku_appendix --out examples/paper_assets/tables_sudoku_appendix
cegvr make-figures --runs runs/sudoku_appendix --out examples/paper_assets/figures_sudoku_appendix
```

These appendix outputs are descriptive transfer evidence only; the main claims remain tied to the linear candidate-first study.
