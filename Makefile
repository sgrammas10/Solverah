# Solverah — developer entrypoints.
#
# One command per task, so onboarding is `make help` rather than reading CI
# config to find out how the project is actually run.
#
#   make help          list targets
#   make dev           full local stack (Postgres + Redis + Mailpit + MinIO + API)
#   make test          backend suite against the local database, using your .env
#   make test-pg       the CI job exactly (no .env)  <-- the gate; run before pushing
#   make check         everything CI runs, locally
#   make db-snapshot   pre-migration database snapshot (Phase 2 rollback)
#
# `test` and `test-pg` differ, and the difference is the point. app.py calls
# load_dotenv(), so `make test` on a developer machine has every variable in
# .env available; the runner has five and no .env. A test that reaches code
# reading anything else is green here and red there. `test-pg` sets
# SOLVERAH_IGNORE_DOTENV=1 so it agrees with the runner, which is why it is the
# one `check` runs and the one to run before pushing.
#
# There was a `test-ci` here, pairing with a SQLite CI job. Both are gone as of
# 2026-08-27 (Phase 2a): the Part 4.3 profile tables cannot be created on SQLite,
# so the job could not reach a test. Reasoning in .github/workflows/tests.yml.
# Both targets now need the compose database -- `make dev-deps` starts it.

.DEFAULT_GOAL := help
COMPOSE := docker compose -f infra/docker/compose.yml
PYTHON  := python

# `solverah_test`, not the `solverah` that `make dev` runs on, and this is a
# gate rather than a preference. `test-pg` runs a suite that calls db.drop_all();
# until 2026-08-27 it defaulted to the same database as the dev stack and as
# `python -m Scripts.capture_contract`, so any two of the three at once destroyed
# each other's tables mid-run. The failure that produced said nothing about
# sharing -- it was 132 collection errors naming `user_role` -- so the split is
# the fix and tests/conftest.py's claim guard is what catches the rest.
#
# Created by infra/docker/initdb/02-lane-databases.sql on the stack's first
# start. Keep in step with TEST_DATABASE_URL in tests/conftest.py.
#
# Port 5433, not 5432 -- the compose stack publishes there because a native
# Windows Postgres service shadows 5432 on at least one machine. Reasoning in
# infra/docker/compose.yml.
# Overridable: `make test-pg DATABASE_URL=...`
DATABASE_URL ?= postgresql://solverah:solverah@localhost:5433/solverah_test

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
test: ## Backend tests against the local database, using your .env (fast inner loop)
	$(PYTHON) -m pytest -q

.PHONY: test-pg
test-pg: dev-deps ## Backend tests exactly as CI runs them — reproduces the gate
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
