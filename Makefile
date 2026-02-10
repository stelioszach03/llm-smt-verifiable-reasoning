PYTHON ?= python3

.PHONY: install lint typecheck test cov format run-toy
.PHONY: paper allruns ablations robust latex clean-artifacts

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e .[dev]

lint:
	ruff check src tests
	ruff format --check src tests

format:
	black src tests
	ruff format src tests

typecheck:
	mypy --config-file mypy.ini src

test:
	PYTHONPATH=src pytest

cov:
	PYTHONPATH=src pytest --cov=cegvr --cov-report=term-missing

run-toy:
	cegvr show-config --config configs/default.yaml

paper:
	bash scripts/run_all.sh

allruns:
	cegvr eval --problems data/toy/problems.jsonl --out runs/toy --seeds 3 --max-rounds 5 --budget 2 --timeout-ms 2000

ablations:
	cegvr eval --problems data/toy/problems.jsonl --out runs/nosolver --no-solver ; \
	cegvr eval --problems data/toy/problems.jsonl --out runs/nogrammar --no-grammar ; \
	cegvr eval --problems data/toy/problems.jsonl --out runs/norepair --no-repair

robust:
	cegvr robustness --problems data/toy/problems.jsonl --out runs/robust --variants 3

latex:
	$(MAKE) -C examples/paper_assets/latex

clean-artifacts:
	rm -rf runs tables examples/paper_assets/figures examples/paper_assets/tables reports/case_studies.md
