# ============================================================
# Agentic-JobApply-Companion — Makefile
# ============================================================
# Common commands for development workflow.
# Usage: make <target>
# ============================================================

.PHONY: help setup install install-dev test lint typecheck format run intake status review clean

# Default target
help: ## Show this help message
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ---- Setup ----

setup: ## Full setup: create venv, install deps, install Playwright browsers
	python3 -m venv venv
	. venv/bin/activate && pip install --upgrade pip
	. venv/bin/activate && pip install -r requirements-dev.txt
	. venv/bin/activate && playwright install chromium
	@echo "\n✅ Setup complete. Activate venv with: source venv/bin/activate"

install: ## Install core dependencies only
	. venv/bin/activate && pip install -r requirements.txt

install-dev: ## Install core + dev/test dependencies
	. venv/bin/activate && pip install -r requirements-dev.txt

# ---- Quality ----

test: ## Run all tests
	. venv/bin/activate && python -m pytest tests/ -v --tb=short

test-cov: ## Run tests with coverage report
	. venv/bin/activate && python -m pytest tests/ -v --tb=short --cov=backend --cov-report=term-missing

lint: ## Run linter (ruff) and type checker (mypy)
	. venv/bin/activate && python -m ruff check .
	. venv/bin/activate && python -m mypy backend/ --ignore-missing-imports

format: ## Auto-format code with ruff
	. venv/bin/activate && python -m ruff format .
	. venv/bin/activate && python -m ruff check --fix .

typecheck: ## Run mypy type checker only
	. venv/bin/activate && python -m mypy backend/ --ignore-missing-imports

# ---- Application ----

run: ## Run the main application pipeline (scrape + match + apply cycle)
	. venv/bin/activate && python main.py run

intake: ## First-time setup: parse resume and build candidate profile
	. venv/bin/activate && python main.py intake

status: ## Show recent application activity and stats
	. venv/bin/activate && python main.py status

review: ## Review pending applications awaiting human approval
	. venv/bin/activate && python main.py review

profile: ## View/edit candidate profile
	. venv/bin/activate && python manage_profile.py view

# ---- Maintenance ----

clean: ## Remove build artifacts, caches, and temp files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -f .coverage
