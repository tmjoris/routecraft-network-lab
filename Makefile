# Common developer and lab tasks. Run `make help` for the list.
VENV ?= .venv
PY := $(VENV)/bin/python
BIN := $(VENV)/bin

.DEFAULT_GOAL := help
.PHONY: help install lint format typecheck test check lab-up lab-test lab-down

help: ## show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

$(PY):
	python3 -m venv $(VENV)

install: $(PY) ## create .venv and install routecraft with dev tools
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e '.[dev]'

lint: ## ruff lint and format check
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

format: ## apply ruff fixes and formatting
	$(BIN)/ruff check --fix .
	$(BIN)/ruff format .

typecheck: ## mypy (strict)
	$(BIN)/mypy

test: ## unit and lab-config tests with coverage (no Docker needed)
	$(BIN)/pytest --cov

check: lint typecheck test ## everything CI runs without Docker

lab-up: ## start the FRRouting lab and wait for convergence
	lab/labctl up

lab-test: ## run the end-to-end tests against the running lab
	$(BIN)/pytest -m lab -v

lab-down: ## stop the lab
	lab/labctl down
