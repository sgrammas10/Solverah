-- One database per tool, because more than one of them drops the schema.
--
-- `tests/conftest.py` calls db.drop_all(); `Scripts/capture_contract.py` calls
-- DROP SCHEMA public CASCADE. Until 2026-08-27 both -- and `make test-pg` --
-- defaulted to the same `solverah` database as `make dev`, so any two of them at
-- once destroyed each other's tables mid-run. The failure did not say so: what
-- it produced was 132 collection errors naming `user_role`, the first enum
-- create_all emits and therefore the first object two racing processes collide
-- on, which read as a schema defect and cost hours.
--
-- These are created here so `make test-pg` works on a fresh stack. A second
-- concurrent lane is one more CREATE DATABASE plus these three extensions --
-- the refusal message in tests/conftest.py prints the exact statements.
--
-- The extensions are per-database, not per-cluster, so 01-extensions.sql running
-- against `solverah` does nothing for these two.

CREATE DATABASE solverah_test OWNER solverah;
CREATE DATABASE solverah_contract OWNER solverah;

\connect solverah_test
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;

\connect solverah_contract
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;
