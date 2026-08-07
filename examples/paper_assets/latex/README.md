# Write-up LaTeX Pack

> **`legacy_2025-10-11_llama3-8b.pdf` is a stale build and does not describe the
> current study.** It was compiled on 2025-10-11 from an earlier version of
> `main.tex` that ran a local llama.cpp **Llama 3 8B Instruct (Q4_K_M)** with
> `--max-rounds 3 --budget 1`, reports `certified_accuracy = 0.7`, and concludes
> that "certification remains comparable to one-shot baselines". The current
> `main.tex` describes the 5-arm candidate-first study instead. The file is kept
> under an explicit legacy name rather than deleted so the history is visible;
> do not cite its numbers. A current PDF cannot be built from a clean checkout
> because `tables/` is not tracked — see step 1 below.
>
> This is a **manuscript. It is not published and has not been peer-reviewed.**

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

- `main.tex`: top-level manuscript draft
- `legacy_2025-10-11_llama3-8b.pdf`: stale build, superseded — see the note above
- `sections/results.tex`: linear main results plus Sudoku appendix transfer section
- `tables_linear/table_main.tex`: auto-generated linear main table
- `tables_sudoku_appendix/table_main.tex`: auto-generated appendix table
- `Makefile`: LaTeX build helper
