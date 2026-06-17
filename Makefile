# Cloud Alliance Score — one-command workflows.
.DEFAULT_GOAL := help
.PHONY: help setup install env test lint typecheck score api ui clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: install env ## Install deps (with dev+ui extras) and create .env

install: ## Install the package with dev + ui extras
	python -m pip install -e ".[dev,ui]"

env: ## Create .env from the template if missing
	@test -f .env || (cp .env.example .env && echo "Created .env — add your API keys.")

test: ## Run the test suite
	python -m pytest -q

lint: ## Lint with ruff
	ruff check src tests

typecheck: ## Type-check with mypy
	mypy src

score: ## Score a company: make score COMPANY="Stripe"
	python scripts/score_cli.py "$(COMPANY)" $(if $(CONTEXT),--context "$(CONTEXT)",)

api: ## Run the FastAPI server (port 8000)
	./scripts/run_api.sh

ui: ## Run the Streamlit UI
	streamlit run app/streamlit_app.py

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info \
		src/*.egg-info .cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
