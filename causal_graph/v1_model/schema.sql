-- ============================================================================
-- Solverah data schema (PostgreSQL)
-- ----------------------------------------------------------------------------
-- Design principles (carried over from the model):
--   1. Dimensions & confounders are ROWS, not columns. Adding one is an INSERT,
--      never a migration -- mirrors the config-driven model.
--   2. Every derived score is VERSIONED (scoring-key / model version) and
--      time-stamped, so re-scoring or retraining never destroys history.
--   3. Company scores carry SOURCE + CONFIDENCE. "scraped" can be upgraded to
--      "declared" in-place (same row shape) -- this is the cold-start wedge ->
--      first-party moat path, and the confidence feeds the model's uncertainty.
--   4. The two outcomes are SEPARATE tables: appeal (fast, biased) vs.
--      experienced fit (slow, true). Never conflate them.
--   5. Recommendations record what was SHOWN (incl. exploration), so you can
--      break the feedback loop and see the selection (collider) that formed.
-- ============================================================================

-- ---- enums -----------------------------------------------------------------
CREATE TYPE score_source   AS ENUM ('scraped', 'researched', 'declared');
CREATE TYPE rec_channel    AS ENUM ('onsite', 'email');
CREATE TYPE funnel_action  AS ENUM
    ('viewed', 'saved', 'passed', 'applied', 'interviewed',
     'offered', 'hired', 'accepted', 'declined');

-- ---- registries (mirror the YAML config; give FKs something to point at) ----
CREATE TABLE dimension (
    key         TEXT PRIMARY KEY,              -- 'autonomy', 'pace', ...
    label       TEXT NOT NULL,
    active      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE confounder (
    key         TEXT PRIMARY KEY,              -- 'stage_size', 'comp', 'industry'
    label       TEXT NOT NULL,
    kind        TEXT NOT NULL,                 -- 'continuous' | 'categorical'
    measurable  BOOLEAN NOT NULL DEFAULT TRUE,
    active      BOOLEAN NOT NULL DEFAULT TRUE
);

-- ============================================================================
-- PERSON SIDE  (measured on truth via the assessment)
-- ============================================================================
CREATE TABLE person (
    id          BIGSERIAL PRIMARY KEY,
    email       TEXT UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Raw assessment answers -- keep them so scores can be RE-derived when the
-- scoring key changes (never overwrite raw responses).
CREATE TABLE assessment_response (
    id            BIGSERIAL PRIMARY KEY,
    person_id     BIGINT NOT NULL REFERENCES person(id),
    item_id       TEXT   NOT NULL,             -- question id in the item bank
    choice        TEXT   NOT NULL,             -- selected option
    form_version  TEXT   NOT NULL,             -- which item set they took
    answered_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_response_person ON assessment_response(person_id);

-- Derived 0..1 score per person per dimension. One row per (person, dim,
-- scoring_key_version). `confidence` = internal-consistency of the items.
CREATE TABLE person_dimension_score (
    id                  BIGSERIAL PRIMARY KEY,
    person_id           BIGINT NOT NULL REFERENCES person(id),
    dimension_key       TEXT   NOT NULL REFERENCES dimension(key),
    score               NUMERIC(4,3) NOT NULL CHECK (score BETWEEN 0 AND 1),
    confidence          NUMERIC(4,3) CHECK (confidence BETWEEN 0 AND 1),
    scoring_key_version TEXT   NOT NULL,
    scored_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (person_id, dimension_key, scoring_key_version)
);
CREATE INDEX ix_pscore_person ON person_dimension_score(person_id);

-- ============================================================================
-- COMPANY SIDE  (scraped/researched now, declared later -- same rows)
-- ============================================================================
CREATE TABLE company (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    domain      TEXT UNIQUE,                   -- natural key for dedupe
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Per company per dimension. SOURCE + CONFIDENCE are the whole point:
--   scraped/researched  -> low-ish confidence (a guess)
--   declared            -> confidence ~1.0 (ground truth from the company)
-- `is_ground_truth` flags companies you can calibrate the scraped model against.
CREATE TABLE company_dimension_score (
    id              BIGSERIAL PRIMARY KEY,
    company_id      BIGINT NOT NULL REFERENCES company(id),
    dimension_key   TEXT   NOT NULL REFERENCES dimension(key),
    score           NUMERIC(4,3) NOT NULL CHECK (score BETWEEN 0 AND 1),
    source          score_source NOT NULL,
    confidence      NUMERIC(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    is_ground_truth BOOLEAN NOT NULL DEFAULT FALSE,
    as_of           DATE   NOT NULL,           -- culture goes stale; date it
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company_id, dimension_key, source, as_of)
);
CREATE INDEX ix_cscore_company ON company_dimension_score(company_id);

-- Confounder values per company. Generic value columns so a new confounder
-- (continuous OR categorical) is an INSERT, not a migration.
CREATE TABLE company_confounder_value (
    id              BIGSERIAL PRIMARY KEY,
    company_id      BIGINT NOT NULL REFERENCES company(id),
    confounder_key  TEXT   NOT NULL REFERENCES confounder(key),
    value_num       NUMERIC,                   -- for continuous (raw, unscaled)
    value_cat       TEXT,                      -- for categorical (level label)
    source          score_source NOT NULL,
    confidence      NUMERIC(4,3) CHECK (confidence BETWEEN 0 AND 1),
    as_of           DATE   NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company_id, confounder_key, source, as_of),
    CHECK (value_num IS NOT NULL OR value_cat IS NOT NULL)
);
CREATE INDEX ix_conf_company ON company_confounder_value(company_id);

-- value_num encoding per continuous confounder (stored RAW / unscaled; the
-- model standardizes via the `scale` in solverah_model_config.yaml). value_num
-- is generic, so the DB does NOT range-check these -- the loader
-- (assemble_training_data) and the workbook dropdowns are the only guardrail.
--   'stage_size' : integer 1..5  (1 seed .. 5 enterprise; keep headcount too)
--   'comp'       : integer 1..5  MARKET-RELATIVE pay posture, NOT dollars
--                  (1 well below .. 3 at market .. 5 well above, vs. talent-
--                  market peers for comparable roles). Key stays 'comp'; the
--                  workbook column label 'comp_vs_market' is the same thing.
--   'industry'   : categorical -> uses value_cat (tech|finance|healthcare|retail|other)

-- ============================================================================
-- RECOMMENDATIONS + FUNNEL  (what was shown, what they did)
-- ============================================================================
-- One row per (person, company) surfaced. Stores the model's prediction AND
-- its uncertainty band, plus is_exploration so you can break the feedback loop
-- and later do off-policy analysis.
CREATE TABLE recommendation (
    id              BIGSERIAL PRIMARY KEY,
    person_id       BIGINT NOT NULL REFERENCES person(id),
    company_id      BIGINT NOT NULL REFERENCES company(id),
    model_run_id    BIGINT,                    -- FK added after model_run exists
    p_fit           NUMERIC(4,3),              -- predicted P(fit=yes)
    p_fit_low       NUMERIC(4,3),              -- credible-interval bounds
    p_fit_high      NUMERIC(4,3),
    rank            INT,                        -- position in the shown list
    is_exploration  BOOLEAN NOT NULL DEFAULT FALSE,
    channel         rec_channel NOT NULL DEFAULT 'onsite',
    shown_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_rec_person ON recommendation(person_id);
CREATE INDEX ix_rec_company ON recommendation(company_id);

-- The behavioral signal + the funnel. "A match formed" (hired+accepted) is the
-- collider you're conditioned on -- capturing the full funnel lets you SEE and
-- later model that selection instead of being silently biased by it.
CREATE TABLE rec_action (
    id                BIGSERIAL PRIMARY KEY,
    recommendation_id BIGINT NOT NULL REFERENCES recommendation(id),
    action            funnel_action NOT NULL,
    acted_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_action_rec ON rec_action(recommendation_id);

-- ============================================================================
-- OUTCOMES  (kept separate on purpose)
-- ============================================================================
-- APPEAL: fast, abundant, but measures "looks like a fit" -- biased toward
-- appearance. Collected on recommendations (incl. ones not pursued).
CREATE TABLE outcome_appeal (
    id                BIGSERIAL PRIMARY KEY,
    recommendation_id BIGINT NOT NULL REFERENCES recommendation(id),
    fit_yes           BOOLEAN NOT NULL,        -- "did this fit what you wanted?"
    channel           rec_channel NOT NULL,
    responded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (recommendation_id)
);

-- EXPERIENCED: slow, scarce, but the TRUE label. Only exists for placements.
-- This is what you eventually train the model's outcome node on.
CREATE TABLE outcome_experienced (
    id                BIGSERIAL PRIMARY KEY,
    person_id         BIGINT NOT NULL REFERENCES person(id),
    company_id        BIGINT NOT NULL REFERENCES company(id),
    recommendation_id BIGINT REFERENCES recommendation(id),
    started_at        DATE,                    -- when they joined
    checkin_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    working_scale     SMALLINT NOT NULL CHECK (working_scale BETWEEN 1 AND 5),
                                               -- ordinal fit rating (1=bad .. 5=great).
                                               -- model outcome node = OrderedLogistic,
                                               -- NOT Bernoulli, when training on this.
    source            TEXT                     -- survey | inferred(tenure) | ...
);
CREATE INDEX ix_exp_person ON outcome_experienced(person_id);

-- ============================================================================
-- MODEL RUNS  (reproducibility + serve predictions from posterior means)
-- ============================================================================
CREATE TABLE model_run (
    id                   BIGSERIAL PRIMARY KEY,
    model_version        TEXT NOT NULL,
    dimension_set_version TEXT NOT NULL,        -- which dims were active
    priors_version       TEXT NOT NULL,
    n_rows               INT,                   -- training rows used
    trained_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes                TEXT
);

-- Snapshot of the fitted posterior, one row per weight. Lets you serve a fast
-- point prediction (from `mean`) without re-sampling, and track how beliefs
-- move as data arrives (compare across model_runs = your recovery curve, live).
CREATE TABLE weight_posterior (
    id            BIGSERIAL PRIMARY KEY,
    model_run_id  BIGINT NOT NULL REFERENCES model_run(id),
    weight_name   TEXT   NOT NULL,             -- 'pace_mag', 'w_comp', 'intercept'
    mean          NUMERIC NOT NULL,
    sd            NUMERIC NOT NULL,
    UNIQUE (model_run_id, weight_name)
);

-- deferred FK (model_run is defined after recommendation)
ALTER TABLE recommendation
    ADD CONSTRAINT fk_rec_model_run
    FOREIGN KEY (model_run_id) REFERENCES model_run(id);
