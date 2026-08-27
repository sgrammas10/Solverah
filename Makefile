# Solverah — developer entrypoints.
#
# One command per task, so onboarding is `make help` rather than reading CI
# config to find out how the project is actually run.
#
#   make help          list targets
#   make dev           full local stack (Postgres + Redis + Mailpit + MinIO + API)
#   make test          backend suite (fast; uses your .env)
#   make test-ci       the SQLite CI job (no .env) -- early signal, NOT the gate
#   make test-pg       the Postgres CI job  <-- the gate; run before pushing
#   make check         everything CI runs, locally
#   make db-snapshot   pre-migration database snapshot (Phase 2 rollback)
#
# `test` and `test-ci` differ, and the difference is the point. app.py calls
# load_dotenv(), so `make test` on a developer machine has every variable in
# .env available; the runner has five and no .env. A test that reaches code
# reading anything else is green here and red there. `test-ci` and `test-pg`
# both set SOLVERAH_IGNORE_DOTENV=1 so they agree with the runner.
#
# `test-ci` and `test-pg` differ too, and that difference is newer. CI grew a
# second backend job on 2026-08-27: Postgres is the gate, SQLite is fast
# non-gating signal. Where the two disagree, Postgres is right -- so `check`
# runs `test-pg`. The move cost 8 test failures on day one, every one a foreign
# key SQLite had never enforced.

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
test: ## Backend tests (SQLite, your .env — fast inner loop)
	$(PYTHON) -m pytest -q

.PHONY: test-ci
test-ci: ## Backend tests exactly as CI runs them (ignores your .env)
	APP_ENV=testing \
	DATABASE_URL=sqlite:///test.db \
	JWT_SECRET_KEY=test-secret \
	JWT_COOKIE_SECURE=false \
	JWT_COOKIE_SAMESITE=Lax \
	SOLVERAH_IGNORE_DOTENV=1 \
	  $(PYTHON) -m pytest --tb=short -q

.PHONY: test-pg
test-pg: dev-deps ## Backend tests against real Postgres — reproduces the CI gate
	@echo "Waiting for Postgres..."
	@until $(COMPOSE) exec -T db pg_isready -U solverah -d solverah >/dev/null 2>&1; do sleep 1; done
	APP_ENV=testing \
	DATABASE_URL="$(DATABASE_URL)" \
	JWT_SECRET_KEY=test-secret \
	JWT_COOKIE_SECURE=false \
	JWT_COOKIE_SAMESITE=Lax \
	SOLVERAH_IGNORE_DOTENV=1 \
	  $(PYTHON) -m pytest --tb=short -q

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
check: test-pg lint typecheck test-web audit ## Everything CI runs

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

# ---------------------------------------------------------------- db rollback
# Phase 2 is the first phase whose rollback is a database restore rather than a
# redeploy (docs/RUNBOOK_DATABASE_ROLLBACK.md). These make that path executable
# rather than a paragraph someone reads during an incident.
#
# Both act on $DATABASE_URL, so they target whatever your environment points at.

.PHONY: db-snapshot
db-snapshot: ## Snapshot $DATABASE_URL into backups/ (run before every migration)
	@test -n "$$DATABASE_URL" || (echo "DATABASE_URL is not set" && exit 1)
	@mkdir -p backups
	@out=backups/solverah-$$(date -u +%Y%m%dT%H%M%SZ).dump; \
	  pg_dump "$$DATABASE_URL" -Fc --no-owner --no-acl -f "$$out" && \
	  pg_restore --list "$$out" >/dev/null && \
	  echo "snapshot: $$out ($$(wc -c < $$out) bytes; archive reads back cleanly)"

.PHONY: db-restore
db-restore: ## Restore IN PLACE: make db-restore SNAPSHOT=backups/x.dump CONFIRM=yes
	@test -n "$$DATABASE_URL" || (echo "DATABASE_URL is not set" && exit 1)
	@test -n "$(SNAPSHOT)" || (echo "usage: make db-restore SNAPSHOT=backups/....dump CONFIRM=yes" && exit 1)
	@test -f "$(SNAPSHOT)" || (echo "no such snapshot: $(SNAPSHOT)" && exit 1)
	@# --clean drops every object it is about to recreate, against whatever
	@# DATABASE_URL currently names. CONFIRM is here so a stale exported URL in
	@# somebody's shell cannot turn a reflex into an outage.
	@test "$(CONFIRM)" = "yes" || ( \
	  echo "Refusing without CONFIRM=yes." && \
	  echo "This DROPS and recreates every object in $(SNAPSHOT), on host:" && \
	  echo "  $$(echo $$DATABASE_URL | sed -e 's|.*@||' -e 's|?.*||')" && \
	  exit 1)
	pg_restore --clean --if-exists --no-owner --no-acl -d "$$DATABASE_URL" "$(SNAPSHOT)"
	@echo "restored $(SNAPSHOT) -- now redeploy the API on the pre-migration commit"

# --------------------------------------------------------------------- images
.PHONY: build
build: ## Build the production API image
	docker build -f infra/docker/Dockerfile.api -t solverah-api:local .
