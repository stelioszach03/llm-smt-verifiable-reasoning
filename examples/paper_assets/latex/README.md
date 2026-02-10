# Paper Asset LaTeX Pack

This directory contains a minimal skeleton for integrating the automatically
generated tables and figures into a paper draft.

## Structure
- `main.tex` – top-level entry point (simple article template).
- `sections/results.tex` – plugs in `tables/table_main.tex` and the PNG figures
  under `../figures/`.
- `tables/table_main.tex` – auto-generated via `cegvr make-tables`.
- `Makefile` – builds `main.pdf` with `pdflatex`.

## Workflow
1. Run the analytics pipeline:
   ```bash
   cegvr eval --problems data/toy/problems.jsonl --out runs/toy
   cegvr make-figures --runs runs/toy --out examples/paper_assets/figures
   cegvr make-tables --runs runs/toy --out examples/paper_assets/tables
   ```
2. Inspect the generated CSV/PNG files; replace placeholders in `main.tex`
   (abstract, introduction, method, conclusion) with your content.
3. Build the PDF:
   ```bash
   make
   ```
4. Clean auxiliary files if needed:
   ```bash
   make clean
   ```

That’s it – the LaTeX pack stays synced with the CLI-generated assets.
