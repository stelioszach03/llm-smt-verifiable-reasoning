LATEX=pdflatex
LATEX_FLAGS=-interaction=nonstopmode -halt-on-error

all: main.pdf

main.pdf: main.tex sections/results.tex tables/table_main.tex
	$(LATEX) $(LATEX_FLAGS) main.tex
	$(LATEX) $(LATEX_FLAGS) main.tex

clean:
	rm -f *.aux *.log *.bbl *.blg *.out *.toc *.pdf

.PHONY: all clean
