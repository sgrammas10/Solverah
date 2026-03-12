# Solverah LLM Architecture

## Overview

Solverah uses a **two-model, sequential AI pipeline** to match candidates with companies and generate personalized Career Intelligence Briefs. The two models are independent — they are never merged into a single blended score.

| Model | Answers | Runs |
|-------|---------|------|
| **Model 2 — Culture Fit** | *Which companies align with who this person is?* | First |
| **Model 1 — Skills Fit** | *Which roles at those companies can they get on paper?* | Second |

This reflects Solverah's core philosophy: **culture fit drives discovery, skills fit drives qualification.**

---

## Pipeline Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                       SOLVERAH MATCHING PIPELINE                           │
│                                                                            │
│  USER INPUTS                                                               │
│  ┌──────────────┐         ┌───────────────────────────┐                    │
│  │  Resume      │         │  Career & Culture Quizzes │                    │
│  │  (PDF/DOCX)  │         │  (career + "Your Future   │                    │
│  │              │         │   Your Way" quiz)         │                    │
│  └──────┬───────┘         └──────────────┬────────────┘                    │
│         │                               │                                  │
│  ┌──────▼───────┐         ┌──────────────▼────────────┐                    │
│  │  Resume      │         │  Quiz Insight Engine      │                    │
│  │  Parser      │         │  (GPT-4o-mini)            │                    │
│  └──────┬───────┘         └──────────────┬────────────┘                    │
│         │                               │                                  │
│  ┌──────▼───────────────────────────────▼────────────┐                     │
│  │              USER UNIFIED PROFILE                  │                     │
│  │  ┌────────────────────────┬──────────────────────┐ │                     │
│  │  │  Skills Profile        │  Culture Profile     │ │                     │
│  │  │  {skills, experience,  │  {archetype,         │ │                     │
│  │  │   education, certs,    │   6-axis dimensions, │ │                     │
│  │  │   clearance}           │   career_prefs}      │ │                     │
│  │  └────────────────────────┴──────────────────────┘ │                     │
│  └────────────────────────────────────────────────────┘                     │
│                                                                             │
│  ════════════════════════════════════════════════════════════════════════   │
│  STEP 1 — COMPANY DISCOVERY  (Model 2: Culture Fit)                         │
│  ════════════════════════════════════════════════════════════════════════   │
│                                                                             │
│  User Culture Profile ──────────────────────────────────────────────────►  │
│                                          ┌──────────────────────────────┐  │
│  Company Profile DB  ──────────────────► │  MODEL 2: Culture / Values   │  │
│  (6-axis dims per company)               │  Fit Model                   │  │
│                                          │                              │  │
│                                          │  Per company:                │  │
│                                          │  • Fit Matrix (6 axes)       │  │
│                                          │  • Archetype alignment       │  │
│                                          │  • Environment compatibility │  │
│                                          │  → Culture Fit Score (X.X/10)│  │
│                                          └──────────────────┬───────────┘  │
│                                                             │               │
│                                    Recommended Companies (ranked by         │
│                                    culture fit, threshold ≥ 7.0/10)        │
│                                                             │               │
│  ════════════════════════════════════════════════════════════════════════   │
│  STEP 2 — ROLE QUALIFICATION  (Model 1: Skills / Paper Fit)                 │
│  ════════════════════════════════════════════════════════════════════════   │
│                                                             │               │
│  User Skills Profile ───────────────────────────────────►  │               │
│                               ┌─────────────────────────◄──┘               │
│  Job Descriptions at  ──────► │  MODEL 1: Skills / Paper Fit Model         │
│  recommended companies        │                                            │
│                               │  Per role at each recommended company:     │
│                               │  • Skills overlap %                        │
│                               │  • Experience gap analysis                 │
│                               │  • Missing skills list                     │
│                               │  → Tier: Strong Match / Reachable / Stretch│
│                               └──────────────────┬─────────────────────────│
│                                                  │                          │
│  ════════════════════════════════════════════════════════════════════════   │
│  STEP 3 — CAREER INTELLIGENCE BRIEF GENERATION                              │
│  ════════════════════════════════════════════════════════════════════════   │
│                                                                             │
│  Culture Fit data + Role Qualification data + Company Profile               │
│       │                                                                     │
│  ┌────▼──────────────────────────────────────────────────────────────┐      │
│  │  LLM Brief Generator (GPT-4o or Claude)                          │      │
│  │  → Draft Career Intelligence Brief                               │      │
│  │  → Solverah human review queue                                   │      │
│  │  → Approved → delivered to user dashboard                        │      │
│  └───────────────────────────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Model 2: Culture / Values Fit

### What It Does
Scores how well a candidate's personality, work preferences, and values align with a company's culture. This is the **primary discovery engine** — it answers "where does this person belong?"

### The Fit Matrix — 6 Dimensions

| Dimension | Low End | High End |
|-----------|---------|----------|
| **Empathy** | Task-first, results-driven | People-first, relationship-driven |
| **Creative Drive** | Process preference, operational | Innovation appetite, idea-generating |
| **Adaptability** | Structured, predictable environments | Comfort with ambiguity and rapid change |
| **Futuristic** | Execution-focused, present-oriented | Vision-oriented, strategy-thinking |
| **Harmony** | High-energy, competitive environments | Collaborative, calm work preference |
| **Data Orientation** | Instinct-led, qualitative | Analytical rigor, metrics-driven |

Each dimension is scored 0.0–1.0 for both the user and the company. Similarity is computed per axis and averaged to produce the final Culture Fit Score (X.X / 10).

**Fit Matrix Labels:**
| Score | Label |
|-------|-------|
| ≥ 0.85 | Excellent |
| ≥ 0.65 | Strong |
| ≥ 0.45 | Moderate |
| < 0.45 | Low |

### User Culture Profile Schema
Extracted from quiz results in `User.profile_data.quizInsights` → stored in `user_culture_profiles` table.

```json
{
  "archetype": "Harmonious Storybuilder",
  "dimension_scores": {
    "empathy": 0.9,
    "creative_drive": 0.8,
    "adaptability": 0.85,
    "futuristic": 0.7,
    "harmony": 0.75,
    "data_orientation": 0.5
  },
  "career_preferences": {
    "pace": "moderate-to-fast",
    "environment": "collaborative",
    "growth_focus": "creative"
  }
}
```

### Company Culture Profile Schema
Stored in `company_profiles` table. Seeded manually by the Solverah team, enriched automatically.

```json
{
  "company_id": "uuid",
  "name": "Charlotte Tilbury",
  "industry": "Luxury Beauty",
  "size": "medium-large",
  "hq": "London, UK",
  "ownership": "Puig (acquired 2020)",
  "culture_dimensions": {
    "empathy": 0.7,
    "creative_drive": 0.9,
    "adaptability": 0.85,
    "futuristic": 0.75,
    "harmony": 0.5,
    "data_orientation": 0.6
  },
  "culture_narrative": "Fast-paced, glamour-driven brand culture with high creative expectations...",
  "core_values": ["glamour", "empowerment", "creativity", "artistry"],
  "work_environment": "demanding, creative, high-energy",
  "pace": "fast",
  "tools_tech": ["Google BigQuery", "Looker", "Emarsys", "Magento Commerce"],
  "career_paths": ["Brand Marketing Coordinator", "Senior Product Marketing Manager"],
  "key_contacts": [
    {"name": "Lisa Lesman", "role": "Marketing Leader US", "linkedin": "linkedin.com/in/lisa-lesman-6b905b7"}
  ],
  "data_source": "manual",
  "last_updated": "2026-03-12T00:00:00Z"
}
```

### Matching Algorithm
```python
def compute_culture_score(user_profile, company_profile):
    dims = ["empathy", "creative_drive", "adaptability", "futuristic", "harmony", "data_orientation"]
    dim_scores = {}
    for d in dims:
        similarity = 1 - abs(user_profile.dimension_scores[d] - company_profile.culture_dimensions[d])
        dim_scores[d] = similarity
    base_score = mean(dim_scores.values())
    # Bonus for pace + environment compatibility
    pace_bonus = 0.05 if pace_compatible(user_profile, company_profile) else 0
    final = min(base_score + pace_bonus, 1.0)
    return round(final * 10, 1), dim_scores   # returns (X.X, {dim: score})
```

### Training & Improvement
- **Bootstrap**: Manually rate 50–100 (user, company) pairs by Solverah team
- **Model type**: Weighted cosine similarity initially; upgrade to fine-tuned embedding model as data grows
- **Signal loop**: Track which recommended companies users engage with → implicit positive/negative signal

---

## Company Profile Data Sources

```
HYBRID APPROACH

Manual Seed
    Solverah team creates profiles via admin UI
    Culture dimension sliders + narrative editor
    data_source: "manual"

Auto-Enrichment (nightly scheduler)
    → Scrape LinkedIn company pages (size, industry, about section)
    → Extract Glassdoor review keyword frequencies → culture signals
    → Ingest new job postings → run JD parsing pipeline → update tools, roles
    data_source: "enriched", last_enriched_at: <timestamp>
```

---

## Model 1: Skills / Paper Fit

### What It Does
Within the culture-matched companies from Model 2, scores each open role against the user's resume. Returns a qualification **tier**, not a score that competes with culture alignment.

### Output Tiers

| Tier | Skills Overlap | Experience | Meaning |
|------|---------------|------------|---------|
| **Strong Match** | ≥ 80% | Meets requirement | Apply now — strong on paper |
| **Reachable** | 60–79% | Minor gap (≤ 1 yr) | Competitive with right framing |
| **Stretch** | 40–59% | Notable gaps | Aspirational — target in 12–18 months |

### Architecture (extends existing code)

```
compare_profiles() [compare.py]          SentenceTransformer [profile2model.py]
      │                                          │
      │  Structured features:                    │  Semantic similarity:
      │  • skills overlap ratio                  │  • user profile text
      │  • experience gap (years)                │  • JD text
      │  • education match (bool)                │  • cosine similarity score
      │  • certifications overlap                │
      └──────────────────────────┬───────────────┘
                                 │
                    Lightweight ensemble model
                    (XGBoost or small MLP)
                                 │
                         0–100 numeric score
                                 │
                      Map to tier (Strong/Reachable/Stretch)
                                 │
                    {tier, score, skills_overlap, missing_skills[],
                     experience_gap, gap_analysis_narrative}
```

### Skills Matching Weights (current `compare.py`)
| Factor | Weight |
|--------|--------|
| Skills overlap | 50% |
| Years of experience | 20% |
| Certifications | 10% |
| Education | 10% |
| Clearance / work auth | 10% |

### Training Data Strategy
- **Bootstrap**: Auto-label all (user profile, JD) pairs in `zensearchData/job_postings.csv` using existing `compare_profiles()` output
- **Ground truth**: Manually label 500–1000 pairs (recruiter-rated matches)
- **Improvement loop**: User application outcomes (accepted / rejected) feed score calibration; `ResumeParseCorrection` table feeds parser retraining
- **Model output location**: `LLM/skills_match_model/`

---

## Career Intelligence Brief

### Structure (based on existing hand-crafted examples)

| Section | Source |
|---------|--------|
| Company Overview | `company_profiles` table |
| Culture & Values | `company_profiles.culture_narrative` + employee voice |
| Fit Matrix Table | Model 2 output — 6 dimensions with labels + explanations |
| Culture Fit Score | Model 2 output (X.X / 10) + archetype label |
| Qualified Roles | Model 1 output — roles tiered as Strong / Reachable / Stretch |
| Action Plan | LLM-generated — 5 steps tailored to user + this company |
| How to Engage | LLM-generated — social, community, content strategy |
| Key Contacts | `company_profiles.key_contacts` with LinkedIn URLs |

### Generation Prompt Structure

```
SYSTEM:
You are Solverah's Career Intelligence engine. Generate a Career Intelligence Brief
that reads like expert human career coaching — specific, warm, and actionable.
Never use generic language. Reference actual company campaigns, values, and culture.
Use the candidate's real skills, archetype, and gap analysis.

USER:
Candidate: {name}
Target Roles: {target_roles}

CULTURE FIT:
  Score: {culture_score}/10
  Archetype: {archetype}
  Fit Matrix: {fit_matrix}           ← 6 dimensions with labels
  Alignment Highlights: {highlights}
  Development Areas: {development_areas}

SKILLS QUALIFICATION:
  {role_title}: {tier} ({overlap}% overlap, missing: {missing_skills})
  ...per role at this company...

COMPANY: {company_profile_json}
CANDIDATE: {user_profile_json}

Generate the full Career Intelligence Brief.
```

### Review & Delivery Workflow

```
1. Culture Fit Score ≥ 7.0/10
       ↓
2. LLM generates draft brief
       ↓
3. Stored in career_intelligence_briefs (status: "draft")
       ↓
4. Solverah reviewer notified
       ↓
5. Reviewer edits in admin dashboard → approves
       ↓
6. status: "approved" → delivered to user dashboard
       ↓
7. User reads brief, downloads PDF
```

---

## Database Schema

### New Tables

#### `company_profiles`
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| name | VARCHAR | |
| industry | VARCHAR | |
| size | VARCHAR | startup/small/medium/large/enterprise |
| hq | VARCHAR | |
| ownership | VARCHAR | |
| culture_narrative | TEXT | |
| core_values | JSON | string array |
| culture_dimensions | JSON | {empathy, creative_drive, adaptability, futuristic, harmony, data_orientation} |
| work_environment | VARCHAR | |
| pace | VARCHAR | slow/moderate/fast/very-fast |
| tools_tech | JSON | string array |
| career_paths | JSON | string array |
| key_contacts | JSON | array of {name, role, linkedin} |
| roles_hiring_for | JSON | string array |
| data_source | VARCHAR | "manual" / "enriched" / "auto" |
| enrichment_status | VARCHAR | |
| last_enriched_at | TIMESTAMP | |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

#### `user_culture_profiles`
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID FK → users | |
| archetype | VARCHAR | e.g., "Harmonious Storybuilder" |
| dimension_scores | JSON | {empathy, creative_drive, adaptability, futuristic, harmony, data_orientation} |
| career_preferences | JSON | {pace, environment, growth_focus} |
| raw_quiz_data | JSON | original quiz insight payload |
| computed_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

#### `culture_matches`
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID FK | |
| company_profile_id | UUID FK | |
| culture_score | FLOAT | 0.0–10.0 |
| fit_matrix | JSON | {dim: {score, label}} |
| alignment_highlights | JSON | top 2 dimension names |
| development_areas | JSON | bottom 1–2 dimension names |
| created_at | TIMESTAMP | |

#### `company_job_matches`
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID FK | |
| company_profile_id | UUID FK | |
| culture_match_id | UUID FK | |
| job_id | VARCHAR | from job_postings.csv or job DB |
| role_title | VARCHAR | |
| tier | VARCHAR | "strong_match" / "reachable" / "stretch" |
| skills_score | FLOAT | 0–100 |
| skills_breakdown | JSON | {skills, experience, education, certs, clearance} |
| missing_skills | JSON | string array |
| gap_narrative | TEXT | LLM-generated gap analysis |
| created_at | TIMESTAMP | |

#### `career_intelligence_briefs`
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID FK | |
| company_profile_id | UUID FK | |
| culture_match_id | UUID FK | |
| status | VARCHAR | "draft" / "in_review" / "approved" / "delivered" |
| llm_model | VARCHAR | e.g., "gpt-4o", "claude-opus-4-6" |
| draft_content | TEXT | LLM-generated |
| reviewed_content | TEXT | Human-edited version |
| reviewer_id | UUID FK → users | |
| reviewed_at | TIMESTAMP | |
| delivered_at | TIMESTAMP | |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

#### `company_enrichment_jobs`
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| company_profile_id | UUID FK | |
| status | VARCHAR | "queued" / "running" / "complete" / "failed" |
| sources_attempted | JSON | list of sources tried |
| results_summary | JSON | what was updated |
| error_log | TEXT | |
| started_at | TIMESTAMP | |
| completed_at | TIMESTAMP | |

---

## API Endpoints (New)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/match/culture` | POST | Run Model 2 — returns culture fit scores for all companies above threshold |
| `/api/match/skills` | POST | Run Model 1 — returns tiered qualification for roles at given company |
| `/api/briefs` | GET | List user's Career Intelligence Briefs |
| `/api/briefs/:id` | GET | Get single brief |
| `/api/admin/briefs` | GET | Admin: list all drafts for review |
| `/api/admin/briefs/:id/approve` | POST | Admin: approve brief, trigger delivery |
| `/api/admin/companies` | GET/POST | Admin: list / create company profiles |
| `/api/admin/companies/:id` | GET/PUT | Admin: view / edit company profile |

---

## Key Files

### To Create
| File | Purpose |
|------|---------|
| `job_descr_LLM/matching/culture_matcher.py` | Model 2 matching logic |
| `LLM/skills_match_model.py` | Model 1 upgraded from `old_LLM/profile2model.py` |
| `brief_generator/generator.py` | Career Intelligence Brief generation service |
| `brief_generator/prompts.py` | LLM prompt templates |
| `src/pages/AdminBriefReview.tsx` | Admin review dashboard |
| `src/pages/CareerIntelligenceBrief.tsx` | User-facing brief viewer |
| `src/components/FitScoreCard.tsx` | Culture + skills score display component |

### To Modify
| File | Change |
|------|--------|
| `model.py` | Add 5 new DB models |
| `migrations/versions/` | New Alembic migration for all new tables |
| `job_descr_LLM/matching/compare.py` | Extend `compare_profiles()` feature vector |
| `app.py` | Add new API routes; update `/api/recommendations` to be culture-gated |

### Existing Code to Reuse
| File | Reuse |
|------|-------|
| `job_descr_LLM/matching/compare.py` | `compare_profiles()` for skills features |
| `job_descr_LLM/jd_input_pipeline/schema.py` | `JobDescriptionOutput` as JD schema |
| `job_descr_LLM/user_input_pipeline/resume_parser.py` | User skills profile extraction |
| `old_LLM/profile2model.py` | SentenceTransformer embedding approach |
| `app.py:1237–1349` | LLM API call pattern for brief generator |
| `model.py` `ResumeParseCorrection` | Feeds skills model retraining loop |

---

## Implementation Phases

### Phase 1 — Foundation (Weeks 1–3)
- DB schema: all new tables + Alembic migration
- Admin UI: company profile creator with culture dimension inputs
- `UserCultureProfileExtractor`: parse quiz insights → `user_culture_profiles`
- Seed 10–20 company profiles manually (beauty/CPG brands to start)

### Phase 2 — Model 2: Culture Fit (Weeks 3–6)
- `CultureMatcher` class: cosine similarity across 6 axes
- Quiz archetype → dimension score mapping
- `POST /api/match/culture` endpoint
- Culture results on user dashboard

### Phase 3 — Model 1: Skills Fit Upgrade (Weeks 6–8)
- Extend `compare_profiles()` feature vector
- Training data pipeline from existing job postings
- Fine-tune SentenceTransformer regression head
- `POST /api/match/skills` endpoint with tiered output
- `/api/recommendations` now runs only against culture-matched companies

### Phase 4 — Career Intelligence Brief Generator (Weeks 8–11)
- Prompt design and iteration
- `BriefGenerator` service class
- Admin review dashboard
- User-facing brief viewer + PDF export
- Auto-trigger when culture score ≥ 7.0

### Phase 5 — Enrichment Pipeline (Weeks 11–15)
- `EnrichmentService`: LinkedIn + Glassdoor scraping
- Culture signal extraction from job postings
- Nightly enrichment scheduler
- Admin enrichment status view

---

## Validation

| Test | Expected Result |
|------|----------------|
| George DeNardo archetype vs. Sol de Janeiro company profile | Culture score ~8.5/10 (matches hand-crafted brief) |
| George's resume vs. Sol de Janeiro marketing coordinator JD | "Reachable" tier (early career, some overlap) |
| Pipeline ordering | Sol de Janeiro and Charlotte Tilbury appear in culture-matched companies before skills model runs |
| Brief generation | Auto-generated brief for George × Charlotte Tilbury matches narrative specificity of hand-crafted version |
| Review workflow | Admin edits draft → approves → brief visible on user dashboard |
