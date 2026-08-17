-- ============================================================================
-- scorer_run + citation storage -- PROPOSED, NOT APPLIED (S1-6).
-- ----------------------------------------------------------------------------
-- Extends schema.sql. Not run against any database; this is the proposal S1-6
-- asks for, matching schema.sql's own conventions (dimensions/confounders as
-- rows, versioned + timestamped derived data).
-- ============================================================================

-- Sprint doc correction #2: schema.sql's `model_run` versions the PyMC FIT
-- (model_version, dimension_set_version, priors_version). Reusing it for the LLM
-- scorer would fuse two unrelated versioning axes -- the scorer changes when a
-- vendor ships an update; the Bayesian model changes when priors or dimensions
-- change; they must be independently queryable. Separate table.
CREATE TABLE scorer_run (
    id                  BIGSERIAL PRIMARY KEY,
    model               TEXT NOT NULL,          -- exact pinned snapshot string,
                                                 -- e.g. 'gpt-5.5-2026-04-23' -- NEVER an alias
    temperature         NUMERIC,                 -- requested value
    temperature_honored BOOLEAN NOT NULL,        -- FALSE if the API rejected/ignored it --
                                                 -- near-zero variance from an ignored
                                                 -- temperature is not the same finding as
                                                 -- near-zero variance from a better model
                                                 -- (SPRINT_SCORER_PIPELINE_01.md design constraints)
    reasoning_effort    TEXT,                    -- null for non-reasoning models
    rubric_version      TEXT NOT NULL,           -- anchors.json's rubric_version,
                                                 -- e.g. 'v1-frozen-2026-08-15'
    packet_version      TEXT NOT NULL,           -- collector-prompt build version parsed
                                                 -- from the packet header, e.g. 'v4.6'
    run_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes               TEXT
);

-- company_dimension_score already exists in schema.sql with `source` = scraped |
-- researched | declared. This FK is populated only when source = 'scraped' (i.e.
-- LLM-produced), so a given company score can be traced to the exact scorer_run
-- that produced it -- same reasoning as stamping model_run on every PyMC-derived row.
-- Nullable: 'researched' (human ground-truth) and 'declared' rows have no scorer_run.
ALTER TABLE company_dimension_score
    ADD COLUMN scorer_run_id BIGINT REFERENCES scorer_run(id);

-- One row per evidence_quote per dimension score. This is new: nothing in schema.sql
-- had anywhere to put the per-quote citation-verification result, because nothing
-- produced evidence_quotes before this sprint (S1-1). `matched` + `matched_excerpt_id`
-- + `source_tag` are the citation verifier's (S1-5) output, not the model's self-report
-- -- see scorer_pipeline.py's module docstring for why source classification is
-- computed downstream from the packet's addressable excerpts rather than trusted from
-- the model. An UNMATCHED quote is still recorded, not discarded -- "every pipeline
-- stage returns proof of what it attempted, not just what it produced" (design
-- constraints, SPRINT_SCORER_PIPELINE_01.md) -- a quote that fails to verify is exactly
-- the failure mode this table exists to make visible.
CREATE TABLE dimension_score_citation (
    id                       BIGSERIAL PRIMARY KEY,
    company_dimension_score_id BIGINT NOT NULL REFERENCES company_dimension_score(id),
    quote_text               TEXT NOT NULL,       -- verbatim as emitted by the model
    matched                  BOOLEAN NOT NULL,    -- did the normalized quote string-match
                                                   -- an excerpt in the packet
    matched_excerpt_id       TEXT,                -- e.g. 'A3' -- null if matched = FALSE
    source_tag               TEXT,                -- company | noncompany | disputed |
                                                   -- researcher -- null if matched = FALSE,
                                                   -- since an unverified quote has no
                                                   -- known provenance to report
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_citation_score ON dimension_score_citation(company_dimension_score_id);

-- The <=0.7 measurement (08-10 decision 3: a score above 0.7 should have at least
-- one non-company-authored source behind it; MEASUREMENT, not an enforced cap) can
-- now be computed as a real query instead of trusted from a rater's manual flag:
--
--   SELECT cds.id, cds.dimension_key, cds.score,
--          bool_or(dsc.source_tag = 'noncompany' AND dsc.matched) AS noncompany_support
--   FROM company_dimension_score cds
--   LEFT JOIN dimension_score_citation dsc ON dsc.company_dimension_score_id = cds.id
--   WHERE cds.source = 'scraped'
--   GROUP BY cds.id, cds.dimension_key, cds.score;
--
-- Matches scorer_pipeline.py's noncompany_support() function exactly, which is the
-- point -- the SQL and the Python should never be allowed to compute this differently.
