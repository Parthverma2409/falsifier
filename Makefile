PYTHON := .venv/bin/python

.PHONY: install test lint clean probe check

install:
	test -d .venv || uv venv --python 3.12 .venv
	uv pip install --python $(PYTHON) -e ".[dev]"

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

clean:
	rm -rf .pytest_cache .ruff_cache build dist *.egg-info
	find . -path ./.venv -prune -o -type d -name __pycache__ -exec rm -rf {} +

probe:
	$(PYTHON) scripts/probe.py

check:
	$(PYTHON) scripts/check_token_factory.py --no-chat
	$(PYTHON) scripts/sandbox_check.py
