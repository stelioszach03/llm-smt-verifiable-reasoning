# Paper Asset LaTeX Pack

This LaTeX pack is synced to the current implementation:

- main results: linear-first candidate pipeline
- appendix transfer evidence: Sudoku 4x4 on the preserved trace layer

## Workflow

1. Run the local paper pipeline:

   ```bash
   bash scripts/run_all.sh
   ```

2. Or regenerate the linear assets manually:

   ```bash
   cegvr summarize --runs runs/linear_main --table tables/linear/main_results.csv
   cegvr make-tables --runs runs/linear_main --out examples/paper_assets/tables_linear --latex examples/paper_assets/latex/tables_linear
   cegvr make-figures --runs runs/linear_main --out examples/paper_assets/figures_linear
   ```

3. Build the PDF:

   ```bash
   make
   ```

## Structure

- `main.tex`: top-level paper draft
- `sections/results.tex`: linear main results plus Sudoku appendix transfer section
- `tables_linear/table_main.tex`: auto-generated linear main table
- `tables_sudoku_appendix/table_main.tex`: auto-generated appendix table
- `Makefile`: LaTeX build helper
