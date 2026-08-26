-- Extensions the target schema depends on (docs/ARCHITECTURE.md, Part 4).
-- Run once at first container start, before any migration.
--
--   citext   : case-insensitive email uniqueness without a LOWER() index
--   pg_trgm  : trigram index for skill-label search
--   vector   : 8-dim culture vectors with an HNSW index, replacing the
--              load-every-company-and-score-in-Python scan
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;
