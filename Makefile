# AgriPredict — developer entry points.
#
#   make            # same as `make run`: start everything
#   make setup      # install both Python envs and the frontend packages
#   make test       # all four suites
#   make help       # everything else
#
# These wrap commands documented in docs/installation/README.md and
# scripts/dev.py; they do not reimplement anything.

SHELL := /bin/bash
.DEFAULT_GOAL := run

# Interpreter discovery, in the same order scripts/dev.py uses: a venv in the
# repository, then one beside the checkout (common in sandboxes and CI images),
# then the system interpreter.
PY ?= python3
BACKEND_PY := $(firstword $(wildcard \
	$(CURDIR)/.venv/bin/python \
	$(CURDIR)/.venv/Scripts/python.exe \
	$(CURDIR)/../.venv/bin/python \
	$(CURDIR)/../.venv/Scripts/python.exe))
ifeq ($(BACKEND_PY),)
BACKEND_PY := $(PY)
endif

FRONTEND := frontend
BACKEND := backend
ML := ml

.PHONY: help run setup setup-backend setup-ml setup-frontend seed test test-backend \
        test-database test-ml test-frontend test-e2e lint audit clean ports api ml \
        bundle check contract

help: ## Show this help
	@echo ""
	@echo "  AgriPredict"
	@echo ""
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "    \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  New here? Run:  make setup   then   make"
	@echo ""

run: ## Start the ML service and the API (one command, seeded, health-gated)
	@$(BACKEND_PY) scripts/dev.py --python $(BACKEND_PY)

api: ## Start only the API (forecasts use the baseline)
	@$(BACKEND_PY) scripts/dev.py --python $(BACKEND_PY) --no-ml

ml: ## Start only the ML service
	@cd $(ML) && PYTHONPATH=. $(BACKEND_PY) -m uvicorn inference.service:app --host 0.0.0.0 --port 8001

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
setup: setup-backend setup-ml setup-frontend ## Install every dependency
	@echo ""
	@echo "  Setup complete. Start the stack with:  make"
	@echo ""

setup-backend: ## Create .venv and install the backend dependencies
	@test -d .venv || $(PY) -m venv .venv
	@.venv/bin/python -m pip install --upgrade pip --quiet
	@.venv/bin/python -m pip install -r $(BACKEND)/requirements.txt --quiet
	@.venv/bin/python -m pip install pytest pytest-cov --quiet
	@echo "  backend  ready (.venv)"

setup-ml: ## Install the ML dependencies into the same .venv
	@test -d .venv || $(PY) -m venv .venv
	@.venv/bin/python -m pip install -r $(ML)/requirements.txt --quiet
	@echo "  ml       ready (.venv)"

setup-frontend: ## Install the React Native packages
	@cd $(FRONTEND) && npm install --no-audit --no-fund --loglevel=error
	@echo "  frontend ready (node_modules)"

seed: ## Create the schema and seed reference data + demo prices
	@cd $(BACKEND) && DATABASE_URL="sqlite:///./agripredict.db" PYTHONPATH=. \
		$(BACKEND_PY) scripts/seed_demo_prices.py --days 400

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
test: test-database test-backend test-ml test-frontend ## Run every offline suite

test-backend: ## Backend unit, API and security tests
	@cd $(BACKEND) && PYTHONPATH=. $(BACKEND_PY) -m pytest -q

test-database: ## Schema, parity and constraint tests
	@cd database && $(BACKEND_PY) -m pytest tests -q

test-ml: ## Preprocessing, model and service tests
	@cd $(ML) && PYTHONPATH=. $(BACKEND_PY) -m pytest tests -q

test-frontend: ## React Native unit tests
	@cd $(FRONTEND) && npx jest --silent

test-e2e: ## Acceptance walk-through (needs `make` running in another terminal)
	@$(BACKEND_PY) scripts/e2e_scenario.py

lint: ## Lint the frontend
	@cd $(FRONTEND) && npx eslint src tests index.js --max-warnings 5

audit: ## Check both dependency trees for known advisories
	@.venv/bin/python -m pip_audit -r $(BACKEND)/requirements.txt || true
	@cd $(FRONTEND) && npm audit --omit=dev

contract: ## Regenerate the frontend's frozen API fixture
	@$(BACKEND_PY) scripts/regen_api_contract.py

bundle: ## Compile the Android release bundle (not an APK)
	@cd $(FRONTEND) && npx react-native bundle --platform android --dev false \
		--entry-file index.js --bundle-output /tmp/agripredict.bundle \
		--assets-dest /tmp/agripredict-assets
	@ls -l /tmp/agripredict.bundle | awk '{print "  bundle: " $$5 " bytes"}'

# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------
ports: ## Show what is listening on the service ports
	@ss -ltn 2>/dev/null | grep -E ':8000|:8001' || echo "  8000 and 8001 are free"

clean: ## Remove generated reports and caches (keeps the database)
	@rm -rf $(BACKEND)/generated_reports .pytest_cache $(BACKEND)/.pytest_cache
	@find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "  cleaned (database kept; delete $(BACKEND)/agripredict.db to reset)"
