# Solverah — developer entrypoints.
#
# One command per task, so onboarding is `make help` rather than reading CI
# config to find out how the project is actually run.
#
#   make help          list targets
#   make dev           full local stack (Postgres + Redis + Mailpit + MinIO + API)
#   make test          backend suite
#   make test-pg       backend suite against real Postgres  <-- the one that matters
#   make check         everything CI runs, locally

.DEFAULT_GOAL := help
COMPOSE := docker compose -f infra/docker/compose.yml
PYTHON  := python

# Matches the compose stack. Overridable: `make test-pg DATABASE_URL=...`
DATABASE_URL ?= postgresql://solverah:solverah@localhost:5432/solverah

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ------------------------------------------------------------------ local env
.PHONY: dev
dev: ## Start the full local stack
	$(COMPOSE) up --build

.PHONY: dev-deps
dev-deps: ## Start only backing services (run the API on the host)
	$(COMPOSE) up -d db redis mailpit minio

.PHONY: down
down: ## Stop the stack, keep volumes
	$(COMPOSE) down

.PHONY: clean
clean: ## Stop the stack and destroy all local data
	$(COMPOSE) down -v

.PHONY: logs
logs: ## Tail API logs
	$(COMPOSE) logs -f api

.PHONY: shell
shell: ## Shell inside the API container
	$(COMPOSE) exec api /bin/bash

.PHONY: psql
psql: ## Open psql against the local database
	$(COMPOSE) exec db psql -U solverah -d solverah

# --------------------------------------------------------------------- checks
.PHONY: test
test: ## Backend tests (SQLite — fast, but not what production runs)
	$(PYTHON) -m pytest -q

.PHONY: test-pg
test-pg: dev-deps ## Backend tests against real Postgres
	@echo "Waiting for Postgres..."
	@until $(COMPOSE) exec -T db pg_isready -U solverah -d solverah >/dev/null 2>&1; do sleep 1; done
	APP_ENV=testing DATABASE_URL="$(DATABASE_URL)" JWT_SECRET_KEY=test-secret \
	  $(PYTHON) -m pytest -q

.PHONY: cov
cov: ## Backend tests with a coverage report
	$(PYTHON) -m pytest --cov=. --cov-report=term-missing --cov-report=html

.PHONY: audit
audit: ## Dependency CVE audit (both ecosystems), same gate as CI
	$(PYTHON) -m pip_audit
	npm audit --omit=dev --audit-level=high

.PHONY: lint
lint: ## Frontend lint
	npm run lint

.PHONY: typecheck
typecheck: ## Frontend TypeScript check
	npx tsc --noEmit

.PHONY: test-web
test-web: ## Frontend tests
	npm test -- --run

.PHONY: check
check: test lint typecheck test-web audit ## Everything CI runs

# ----------------------------------------------------------------- migrations
.PHONY: migrate
migrate: ## Apply migrations
	flask db upgrade

.PHONY: migration
migration: ## Autogenerate a migration: make migration m="add users.status"
	@test -n "$(m)" || (echo "usage: make migration m=\"description\"" && exit 1)
	flask db migrate -m "$(m)"

.PHONY: migrate-check
migrate-check: ## Fail if models and migrations have drifted
	@flask db check && echo "models and migrations agree"

# --------------------------------------------------------------------- images
.PHONY: build
build: ## Build the production API image
	docker build -f infra/docker/Dockerfile.api -t solverah-api:local .
