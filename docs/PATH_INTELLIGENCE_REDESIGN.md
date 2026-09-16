# Path Intelligence redesign — corpus retrieval + deep fit on click

**Created 2026-09-16.** Proposed after Sebastian's judgement that the current
scorer is "practically useless" — the retrieval is expensive and the scoring is
inaccurate — and after the production OOM of 2026-09-15 traced part of its cause
to the same code path.

**Scope.** How Path Intelligence finds and ranks occupations. *Not* the O*NET
backbone decision itself (`PRODUCT_DECISIONS.md` §1, Sebastian 2026-09-10:
**keep as backbone** — this document assumes that and changes only how the data
is used), and *not* the causal Bayesian model lane (`BUILD_PLAN.md` workstream E),
which scores person↔condition fit rather than person↔occupation retrieval.

**How to read it.** §0 says what is decided and what is not. Nothing here is
built. Numbers marked **measured** were produced on 2026-09-16 by the method in
§7; everything else is an estimate and says so.

---

## 0. Status

| Item | Status |
|---|---|
| Overall direction (title/document-vector retrieval, three intent paths) | Sebastian's own proposal, 2026-09-16 — **direction agreed**, spec unbuilt |
| Corpus artifact stored as a `.npy` in S3 | **Decided** — Sebastian, 2026-09-16 |
| Everything in §2.3, §3, §5 | ⚑ **Proposed by agent, unsigned.** Recommendations with rationale, not settled facts |
| Any code change | **None made.** No file in `backend/` or `solverah/` has been touched |

⚑ marks a design call that needs Sebastian before it is built, following the
`BUILD_PLAN.md` §0.2 convention.

---

## 1. Why

### 1.1 The accuracy problem is structural, not a tuning problem

`get_skills_profile()` returns O*NET's **Skills** taxonomy — element IDs like
`2.A.1.b` "Active Listening" (see the fixture at `tests/test_onet_client.py:170`).
That taxonomy is a **fixed ~35-element list, and every occupation in O*NET has
all 35**. Only the *importance number* differs between occupations. The same is
true of Work Activities (~41, fixed).

`_build_role_profile()` (`backend/services/path_scoring.py:339`) composes each
candidate's profile from:

- hot technology names — **genuinely discriminating** ("Python", "Docker")
- generic skills above importance 50 — **the same ~15–20 abstract names for
  every candidate in the pool**

`_compute_centroid_score()` then cosine-compares the user's concrete skills
against the **centroid** of that mixture. Averaging "Python" and "React" against
a centroid dominated by "Critical Thinking / Active Listening / Reading
Comprehension" yields numerically similar scores for nearly every candidate.

**The majority of the compared vocabulary is constant across the entire candidate
set.** No reweighting of `skills_w` / `zone_w` / `style_w` / `role_w` fixes that,
because the discriminating signal is being averaged away before the weights are
applied. This is why the output does not feel responsive to the user's actual
skills.

A second, self-documented symptom: the SOC prefix allow-list at
`path_scoring.py:154` exists because *"searching 'Data Scientists' returns
Bioinformatics Scientists, Political Scientists, Atmospheric Scientists"* — a
hand-written patch over surface-form title matching.

### 1.2 The cost problem is fan-out, not the loop

The current search does **not** iterate all of O*NET. It is a funnel
(`_gather_candidates`, `path_scoring.py:1132`):

1. `get_job_family_occupations(current_code[:2] + "-0000")`, `end=100` — one call
   returning the user's own SOC family. This is the bulk of the pool.
2. One LLM call → 5–7 occupation titles → one `search_occupations()` call per
   term, **keeping only `results[0]`** and discarding the rest of each result list.
3. `_filter_candidate_pool()` prunes by SOC prefix and research exclusions.

Net pool: roughly **30–80 occupations** (estimate; the client docstring at
`onet_client.py:366` notes the largest family, `15-0000`, has ~38).

The expense is what happens next. `_fetch_candidate_data` makes **3–4 O*NET HTTP
calls per candidate** (zone, skills profile, hot tech, work activities), 8 in
flight via `ThreadPoolExecutor`. At ~40 candidates that is **~160 O*NET requests
per cold run**, to rank ~40 items and display 10.

Then `_batch_embed` embeds every text Phase B will need across *all* candidates
at once.

**Two structural notes on the funnel itself:** the job-family primary means a
user is mostly shown occupations from the family they are already in — which is
defensible for `stay_in_field` and actively wrong for `fresh_start`. And the
keyword supplement throws away all but the first result of every search it pays
for.

### 1.3 This is also the production OOM

`_EMBED_CACHE` (`path_scoring.py:146`) is a process-global `OrderedDict[str,
list[float]]` capped at 10,000 **entries**, not by memory.

**Measured:** a 1536-dim `text-embedding-3-small` vector stored as a plain Python
`list[float]` costs **48.58 KB**, so a full cache is **474.4 MB per worker**.
`gunicorn.conf.py` pins `workers = 3` and the cache is per-process, giving a
theoretical ceiling of **1.42 GB against a 512 MB dyno**.

The link to this redesign: a single cold scoring run adds several hundred vectors
(estimate: 300–700 unique texts after dedup, since the ~35 generic skills and ~41
work activities dedup to near-constant totals while hot-tech names and titles
vary). That is **~15–35 MB of permanently resident memory per distinct user
scored**. The cache does not fill over weeks; it fills over dozens of runs.

Two aggravating factors found while tracing this, both worth recording because
neither is obvious from the cache code:

- `max_requests = 2000 / jitter = 200` was added to `gunicorn.conf.py` after the
  **2026-09-08** production death as a bound on exactly this class of leak. It is
  **inert at current traffic** — recycling only fires after ~2000 requests *per
  worker*, which a low-traffic service never reaches. The cache fills once and
  stays. That is the flat 8-hour plateau on the 2026-09-15 Render graph, rather
  than the sawtooth recycling was meant to produce.
- `preload_app` is deliberately unset (the file explains why: it needs a
  `post_fork` disposing the SQLAlchemy engine). So pandas/numpy/scikit-learn load
  once per worker. **Measured:** 72.2 MB of *traced Python heap* for that import
  — true RSS is higher, since C-extension allocations sit outside Python's
  allocator, which is why the file's own estimate says ~150 MB. At 3 workers the
  baseline is a large fraction of the dyno **before any cache exists**.

**The redesign in §2 replaces the unbounded cache with a fixed ~6 MB matrix.**
That is a structural removal of the leak, not a mitigation. See §4 for why the
interim cache fix should still ship first anyway.

---

## 2. The architecture

Two tiers with completely different cost profiles: **cheap retrieval over a
precomputed corpus**, then **expensive analysis of one occupation, deferred until
the user clicks it**.

### 2.1 The corpus index

Build **one vector per O*NET occupation**, offline, ahead of time.

**The corpus is small enough that this is nearly free.** `get_job_families()`
enumerates all ~23 SOC families and `get_job_family_occupations()` enumerates
each, so the **entire catalog is reachable in ~23 API calls** and totals roughly
1,000 occupations (~900–1,100 depending on taxonomy version).

    ~1,016 occupations x 1536 dims x 4 bytes (float32) = ~6 MB

**Consequences of that number, which are the whole reason this design works:**

- **No vector database is required.** Brute-force exact cosine over the full
  corpus is a single `matrix @ query` — ~1.5M FLOPs, sub-millisecond. An ANN
  index would trade exactness for a speedup that is not needed. pgvector becomes
  worth revisiting only if the corpus grows ~100x, which O*NET will not.
  (This is a *third* potential use of vectors, distinct from the two weighed in
  `PRODUCT_DECISIONS.md` — occupation **retrieval**, not person↔condition fit
  scoring. That earlier verdict does not automatically apply here.)
- **Storage: a `.npy` artifact in S3** — *decided, Sebastian 2026-09-16*.
  Versioned, no schema migration, no new infra cost, loaded at boot. Two files:
  the `float32` matrix and a JSON sidecar mapping row index → O*NET code.
- Loading it costs ~6 MB per worker, ~18 MB across three.

**Embed a role document, not a bare title.** This is the single most important
detail in this document.

A 2–3 word job title is dominated by one token, so title-only similarity
reproduces the exact "Data Scientists → Political Scientists" failure that the
SOC allow-list at `path_scoring.py:154` was hand-written to suppress — the hack
would still be needed. Instead compose, per occupation:

    title + O*NET description + top tasks + hot technologies

~200–400 tokens of real content. Same one vector, same ~6 MB, same build cost —
but similarity now reflects *what the job involves* rather than what it is called.
This is also what fixes §1.1: the comparison target stops being a centroid
dominated by 35 constants.

**Keep the two sides symmetric.** Comparing a user's short title against long
role documents distorts cosine. Resolve the user to an O*NET code first
(`_resolve_current_zone` already does this) and use **that occupation's own
corpus vector** as the query — document-to-document.

**Build cost** (estimate): ~1,016 docs x ~300 tokens ≈ 305k tokens of
`text-embedding-3-small` ≈ **under one cent**, run offline. One gap to close:
`Occupation` is currently just `code` + `title` (`onet_client.py:88`), so the
corpus builder needs one or two new client methods for description and tasks.

**Refresh:** O*NET content changes quarterly. The builder should be a CLI command
in the `flask` group, in the same shape as the Scenario A crons
(`RUNBOOK_SCENARIO_A_CRON.md`), so a refresh is a scheduled job rather than a
manual laptop run.

### 2.2 Tier 1 — retrieval

One dot product against the corpus matrix, plus the per-path logic in §3. No
O*NET calls, no OpenAI calls except embedding the user's own query text.

Hard filters applied at this tier, not as soft weights:

- **Job Zone feasibility.** Zone is education/training required, and it is
  already fetched today. Recommending a career that needs years of licensure to
  someone unwilling to do it is worse than recommending nothing.
- **SOC exclusions**, where a path calls for them (§3.3).

### 2.3 Tier 2 — deep fit, on click ⚑

*Sebastian's addition, 2026-09-16.* The shortlist is cheap; the full fit analysis
runs **only for an occupation the user clicks**.

This is retrieve-then-rerank with the rerank deferred to an expression of
interest. Two benefits beyond speed:

- **The analysis gets better, not merely rarer.** Budget currently spread thin
  across ~40 candidates is spent on the one the user cares about — enough for
  tasks, the full tech stack, and an LLM-written gap explanation.
- **It is fast enough to stay synchronous.** One occupation is ~3–4 O*NET calls,
  all `_OCC_CACHE`-backed; roughly 500 ms–1 s warm (estimate). No job/poll pair
  needed, unlike `POST /me/path-suggestion-jobs` today.

Two things this tier needs:

- A **rate limit**, since it is a per-click provider spend — matching the limit
  already on `POST /me/path-suggestion-jobs`.
- A decision on **result storage** — see §5.

---

## 3. The three intent paths

`move_intent` already exists and already branches the scorer
(`_ROLE_WEIGHT_BY_INTENT`, `path_scoring.py:128`). This gives each branch a
retrieval strategy instead of a weight tweak.

### 3.1 `stay_in_field` — nearest neighbours

Anchor = the user's resolved occupation vector. Top-K by cosine, exclude self.

Worth noting that the code already asks for exactly this. `path_scoring.py:1166`:
*"Replace this block with `get_related_occupations(current_code)` when O*NET adds
that endpoint; it will produce a tighter, skills-similarity-based pool."* This
builds that endpoint rather than waiting on O*NET.

### 3.2 `adjacent` — interactive elicitation ⚑

*Sebastian's proposal, 2026-09-16: show a few positions, let the user say whether
each is interesting or too similar, and let the backend learn what they want.*

The intuition is right, and it decomposes into **two separate signals** — which
matters, because building only the first is the obvious mistake:

- **"Too similar" is a radius signal.** It means *exclude everything above
  cosine r*. So candidates are sampled from an **annulus** around the anchor —
  `r_min < cos(anchor, x) < r_max` — and a "too similar" answer raises `r_min`.
  This is the "circle" intuition, and it is valid.
- **"Interesting" is a direction signal.** Two occupations equidistant from the
  anchor can lie in opposite directions. What a click teaches is not *how far*
  but *which way* — and in 1536 dimensions there is a great deal of "which way".

The standard algorithm for combining them is **Rocchio relevance feedback**
(classic IR, a few lines of numpy):

    q' = alpha * q  +  beta * mean(liked)  -  gamma * mean(disliked)

Each round both widens the ring and rotates the query toward what they liked.

**Probe selection matters as much as the update rule.** Showing the top-K
produces all "too similar" and teaches nothing; showing random produces all
irrelevant and teaches nothing. Stratify across the distance band and enforce
diversity among the probes — **MMR** (maximal marginal relevance) is the usual
tool. ~6–8 well-spread probes is enough to locate someone.

**Two product constraints, both following the same principle the expert-input
flows follow — any elicitation must survive being abandoned:**

- **One screen.** Not a wizard.
- **Valid half-finished.** Zero answers must still yield a sensible default (the
  ring at a fixed `r_min`). A flow that blocks results until complete will be
  abandoned and produce nothing.

### 3.3 `fresh_start` — diverse seed, same loop ⚑

Sebastian had no starting point for this one. Proposed:

**The trap to avoid first: distance from the current job is not a positive
signal.** "Far from software engineering" includes Logging Worker and Meat
Packer. The current code already fell into this — the `fresh_start` branch leans
on zone delta, and the comment at `path_scoring.py:1355` admits *"every zone+1
role in the candidate pool scores identically on this term regardless of
relevance"*, which is why the `_ZONE_DAMPENING_FRESH_START = 0.6` patch exists.
Do not rebuild that.

**The reframe: someone leaving their field wants to leave the *domain*, not their
*capabilities*.** Drop the occupation anchor; keep everything else about them.

- **Transferable-skill floor.** Retrieve on the user's *skills* document,
  constrained to a different SOC major group. "Same capabilities, different
  field" — which is what makes a change feasible rather than aspirational.
- **Feasibility as a hard filter** (§2.2), not a soft weight.
- **Behavioral profile as the primary query.** `_build_behavioral_profile`
  already composes `archetype` / `focus_type` / `work_style_tags` and is already
  embedded today — but capped at `style_w = 0.25`. With no occupation anchor it
  is the only remaining signal about what the person actually wants, and should
  be **dominant** rather than a side term.
  ⚠ *Scope check:* this means the existing behavioral profile only. The
  core→8-dimension culture-preferences mapping is a **different** thing and was
  explicitly **skipped** for launch (`BUILD_PLAN.md` ⚑3, Sebastian 2026-09-08).
  Nothing here reopens that.

**Then seed the same loop as §3.2 from a different starting point.** Instead of
an annulus around an anchor, seed with a **maximally diverse spanning set**:
k-means over the corpus (k ≈ 8–10), take the real occupation nearest each
centroid, filtered by the two constraints above. That covers the space of what is
plausible for this person, and their reactions Rocchio the query toward a region.

This is the standard cold-start recommender answer, and the payoff is
architectural: **§3.2 and §3.3 become one implementation with two initializers** —
same probe selection, same update rule, different seed.

---

## 4. Sequencing

**The interim cache fix should still ship first, before any of this.**

This redesign removes `_EMBED_CACHE` eventually, but it is multi-chunk work and
production is at risk now. The low-risk, code-only fix — bound the cache by
memory footprint or store vectors compactly, and sweep `_OCC_CACHE`'s expired
entries — is hours, not weeks, and is independently correct.

**Measured** alternatives to `list[float]`, for that interim fix:

| storage | per entry | at the 10k cap |
|---|---|---|
| `list[float]` (current) | 48.58 KB | 474.4 MB |
| `array.array('f')` | 6.62 KB | 64.7 MB |
| numpy `float32` | 7.05 KB | 68.9 MB |
| packed `bytes` | 6.18 KB | 60.4 MB |

A **7.3x** reduction from storage alone, before any cap change. `float32`
precision loss is negligible for cosine similarity.

Separately, `_OCC_CACHE` (`onet_client.py:38`) is worse than "no size cap":
`_occ_cache_get` returns `None` on expiry but **never deletes the expired entry**,
and `_occ_cache_set` never sweeps. That is precisely the "leak wearing a TTL's
clothing" pattern that `agent_service.py:73` names and fixes for itself — the
lesson was written down but never applied here.

**Also unresolved and cheap to check:** whether Celery actually runs eager in
production. `config.py:411` is `celery_eager_default = is_testing or not
celery_broker_url`, and `celery_broker_url` falls back to `REDIS_URL`
(`config.py:390`). If `REDIS_URL` is set, eager is **off** — and with no
`type: worker` service, queued jobs would go to Redis and be consumed by nobody.
`queue.py` logs `celery_configured` with `"eager": <bool>` at every boot; one
grep of Render's logs settles it. It decides whether the problem is "heavy jobs
run in the web process" or "heavy jobs never run at all", which are different
bugs with different fixes.

The separate `type: worker` Render service proposal is **not** in this document —
it is an infra/cost decision needing Sebastian's sign-off and manual provisioning,
and is tracked separately.

---

## 5. Open decisions ⚑

| # | Question | Notes |
|---|---|---|
| 1 | Does this **replace** `path_scoring.py` or sit beside it? | Recommend replace-and-tombstone, following the Phase 3c precedent. Two scorers means two things to keep correct. |
| 2 | Is the Tier-2 deep fit **stored** per `(user, occupation)` or recomputed? | Decides whether a new table and migration are needed. Recommend stored with invalidation on profile write, mirroring `path_cache`'s `invalidate` discipline. |
| 3 | Where does the §3.2 elicitation **live in the flow**? | Product/UX question. First visit only, or re-runnable? Blocking or skippable? |
| 4 | Corpus **refresh cadence** and trigger | Recommend a `flask` CLI command + Render cron, matching Scenario A. |
| 5 | Does the shortlist still need the **SOC allow-list** once documents replace titles? | Probably not — it is a patch over title-surface matching. Should be tested, not assumed, and removed only with evidence. |
| 6 | What happens when a user's title **resolves to no O*NET code**? | Today it falls back to broad-category search. §3.1 needs an anchor; the fallback should be the §3.3 seed, not an error. This is the live ACC-4 failure from the 2026-09-15 walk. |

---

## 6. What this does not solve

Recorded so it is not assumed away later.

- **It does not validate that O*NET is the right taxonomy.** It makes the O*NET
  data cheaper and sharper to use. Whether occupation-level matching is what
  users want is `PRODUCT_DECISIONS.md`'s question, answered 2026-09-10 as
  "backbone, keep".
- **It does not make retrieval *correct*, only *better*.** Embedding similarity
  over role documents is a heuristic. There is no ground truth here and no
  evaluation set — see below.
- **There is no offline evaluation harness.** Today, "is this ranking good"
  is answered by a person reading results. With a ~1,000-row corpus that is
  fixable — a small labelled set of (profile → acceptable occupations) pairs
  would turn tuning into measurement instead of argument. Worth its own chunk;
  without it, §3's weights are opinion.
- **It does not touch the causal Bayesian model lane.** Different question,
  different scorer, gated on Julie's priors.

---

## 7. Measurements behind this document

Everything marked **measured** was produced 2026-09-16 with `tracemalloc` on
Python 3.11 (`Desktop/solverah-venv311`, outside the repo per the guard-test
rule), filling an `OrderedDict` exactly as `_batch_embed` fills `_EMBED_CACHE`:
10,000 entries, 1536 dims, string keys of realistic length. The scientific-stack
figure is the traced heap delta of `import pandas, numpy, sklearn`.

`tracemalloc` measures Python-allocated memory only; true RSS is higher because
C-extension allocations fall outside Python's allocator. Every figure here is
therefore a **floor**, not a ceiling.

Not measured, and worth measuring before the interim fix is called done: actual
dyno RSS under load, and the real per-run unique-text count against live O*NET
(§1.3's 300–700 is an estimate from the taxonomy's shape).

---

## Related

- `docs/PRODUCT_DECISIONS.md` — O*NET as backbone; the career-development spine
- `docs/BUILD_PLAN.md` — ⚑3 (culture-preferences mapping skipped); workstream E
- `docs/USER_SCENARIOS.md` — S16.11 (the dead gate, confirmed live 2026-09-15)
  and the ACC-4 / S22 walk where the OOM surfaced
- `gunicorn.conf.py` — the 2026-09-08 incident, worker recycling, `preload_app`
- `backend/services/path_scoring.py` — the code this replaces
