.PHONY: help venv install install-dev run run-dev lint format fix test health plot clean-venv check

# --- config ---
HOST ?= 127.0.0.1
PORT ?= 8000
APP := geo_expression_service.main:app
GSE ?= GSE2034
GENES ?= TP53,BRCA1
PLOT_OUT ?= expression_plot.png
VENV_INSTALLED := .venv/.installed
VENV_DEV_INSTALLED := .venv/.dev-installed

# Python inside .venv (Linux WSL or Windows venv on /mnt/c/)
ifneq ($(wildcard .venv/bin/python),)
  PYTHON := .venv/bin/python
  PIP := .venv/bin/pip
else ifneq ($(wildcard .venv/Scripts/python.exe),)
  PYTHON := .venv/Scripts/python.exe
  PIP := .venv/Scripts/pip.exe
else
  PYTHON := python3
  PIP := pip3
endif

# System Python for creating .venv
ifeq ($(OS),Windows_NT)
  PY := python
else
  PY := python3
endif

.DEFAULT_GOAL := help

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

venv: ## Create .venv if missing
	@test -x .venv/bin/python -o -x .venv/Scripts/python.exe || $(PY) -m venv .venv

$(VENV_INSTALLED): pyproject.toml | venv
	$(PIP) install -e .
	@touch $@

$(VENV_DEV_INSTALLED): pyproject.toml | venv
	$(PIP) install -e ".[dev]"
	@touch $@

install: $(VENV_INSTALLED) ## Install runtime dependencies (editable)

install-dev: $(VENV_DEV_INSTALLED) ## Install dev dependencies (pytest, ruff, httpx2)

lint: $(VENV_DEV_INSTALLED) ## Run ruff linter
	$(PYTHON) -m ruff check geo_expression_service tests

format: $(VENV_DEV_INSTALLED) ## Format code with ruff
	$(PYTHON) -m ruff format geo_expression_service tests

fix: $(VENV_DEV_INSTALLED) ## Auto-fix ruff lint issues and format
	$(PYTHON) -m ruff check --fix geo_expression_service tests
	$(PYTHON) -m ruff format geo_expression_service tests

run: $(VENV_INSTALLED) ## Start API server
	$(PYTHON) -m uvicorn $(APP) --host $(HOST) --port $(PORT)

run-dev: $(VENV_INSTALLED) ## Start API server with auto-reload
	$(PYTHON) -m uvicorn $(APP) --host $(HOST) --port $(PORT) --reload

test: $(VENV_DEV_INSTALLED) ## Run unit tests
	$(PYTHON) -m pytest -v

check: lint test ## Lint and run tests

health: ## GET /health (server must be running)
	curl -s http://$(HOST):$(PORT)/health

plot: ## Save expression boxplot PNG (server must be running)
	curl -s --max-time 300 \
		"http://$(HOST):$(PORT)/expression?gse=$(GSE)&genes=$(GENES)" \
		| $(PYTHON) -c "import sys,json,base64; d=json.load(sys.stdin); open('$(PLOT_OUT)','wb').write(base64.b64decode(d['plot']['content'])); print('saved: $(PLOT_OUT)')"

clean-venv: ## Remove .venv
	rm -rf .venv
