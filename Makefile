# Compuertas de calidad del proyecto.
#
# Estos mismos targets los invoca el CI, para que los comandos no puedan
# divergir entre una maquina y el pipeline. Si el comando anda aca, anda alla.
#
# En local las herramientas se toman del virtualenv del proyecto. En CI, que
# instala en el Python del runner y no crea un venv, se usan las del PATH.

VENV    := .venv
ifneq ($(wildcard $(VENV)/bin/python),)
  BIN   := $(VENV)/bin/
else
  BIN   :=
endif

PY      := $(BIN)python
PIP     := $(BIN)pip
RUFF    := $(BIN)ruff
MYPY    := $(BIN)mypy
PYTEST  := $(PY) -m pytest

SRC     := app.py router.py doc_selector.py groq_client.py pdf_utils.py tabla_utils.py ingesta.py bm25.py historial.py resumen.py
PATHS   := $(SRC) scripts tests evaluacion

.DEFAULT_GOAL := help
.PHONY: help venv install install-e2e run test test-cov test-e2e lint format format-check typecheck check clean

help: ## Muestra los comandos disponibles
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

venv: ## Crea el virtualenv si no existe
	@test -d $(VENV) || python3 -m venv $(VENV)

install: venv ## Instala las dependencias de ejecucion y de desarrollo
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

install-e2e: install ## Instala el Chromium que maneja Playwright
	$(VENV)/bin/playwright install --with-deps chromium

run: ## Levanta la app en local
	$(VENV)/bin/streamlit run app.py

test: ## Corre los tests unitarios (sin los de punta a punta)
	$(PYTEST)

test-cov: ## Corre los tests unitarios con informe de cobertura
	$(PYTEST) --cov --cov-report=term-missing --cov-report=xml

test-e2e: ## Corre los tests de punta a punta contra un navegador real
	$(PYTEST) -m e2e

lint: ## Reporta violaciones de estilo
	$(RUFF) check $(PATHS)

format: ## Reescribe los archivos al formato canonico y corrige lo seguro
	$(RUFF) format $(PATHS)
	$(RUFF) check --fix $(PATHS)

format-check: ## Falla si algun archivo no tiene el formato canonico
	$(RUFF) format --check $(PATHS)

typecheck: ## Verifica los tipos de forma estatica
	$(MYPY) $(SRC) scripts

check: lint format-check typecheck test ## Corre todas las compuertas que corre el CI

clean: ## Borra artefactos de build, cache y cobertura
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -not -path "./$(VENV)/*" -exec rm -rf {} +
