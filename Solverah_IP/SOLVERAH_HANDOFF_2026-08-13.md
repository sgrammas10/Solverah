# Solverah — Session Handoff, 2026-08-13

**Topic: hardening the evidence-collector prompt against edge cases, and building P-02.**
Custom instruction to honor: be logical and future-thinking, do not be agreeable — push back.

This session is narrow. It did NOT touch the causal model, the rubric, the assessment items, the
scoring rule, the variance tests, or the Julie correction. It was entirely about the **Company
Culture Evidence Collector prompt** and the **P-02 Best Buy packet build**.

For everything else, the prior handoff still stands: `SOLVERAH_HANDOFF_2026-08-10.md`.

---

## Files created this session

| Path | What it is |
|---|---|
| `ground_truth/rubric/Company_Culture_Evidence_Collector_v4.4.md` | **New prompt version.** Supersedes v4.3. |
| `ground_truth/rubric/V43_DEFECTS_LOG.md` | **13 defects with evidence, plus every decision made and why.** Read this before touching v4.4. |
| `ground_truth/packets/P-02_best_buy/P-02_packet_IN_PROGRESS.txt` | **P-02, partially built.** Sections A and C complete, B half-sampled, D/E/F not started. |

Files that already existed and were only read: `Company_Culture_Evidence_Collector_v4.2.md` / `.docx`,
`v4.3.md` / `.docx`, `PACKET_FEASIBILITY_FINDING.md`, `SOURCE_AVAILABILITY.md`, the P-03, P-04 and
P-05 packets.

**Note:** `SOURCE_AVAILABILITY.md` is now partly wrong. It records Glassdoor as "Unusable — fetch
returns an empty body." That was corrected in v4.3 and refined again this session. Do not rely on it
for source routing; use v4.4's opening section.

---

## Decisions made this session — all binding

1. **Roster is 6 companies, and that is the FULL ground-truth set, not a pilot.**
   Consequence flagged and accepted: with 6 companies one packet is 17% of the calibration set, so
   spec drift between packets cannot average out.

2. **All six packets get rebuilt under the final prompt version before any rater sees them.**
   This is the plan of record. Packets built during the hardening phase are instrument tests, not
   calibration data.

3. **George is off the exercise entirely.** He has stopped scoring. The v1-vs-rebuilt-packet merge
   problem from the 08-10 handoff (open item #4) is therefore closed — no sunk rater scores to
   protect, so packets can be rebuilt freely.

4. **Prompt is revised as failures surface, not frozen.** Deliberate: the six companies were
   selected to cover edge cases, so per-company revision is spec-hardening, not drift.

5. **Section B uses both review sites, split by role.** Indeed supplies verbatim review TEXT;
   Glassdoor supplies per-title SUBRATINGS (numbers only, never quoted into Section 1) plus a
   recency cross-check. Neither site is "the frame" — the job-title list is.

6. **Scope is recorded, the scoring unit does not change.** *(This one was decided, then reversed
   the same day — read the reasoning in the defects log under D6 before revisiting it.)* The packet
   still describes the company. A scope block records which population each section's evidence
   actually came from, as metadata, like the recognition Y/N flag.

7. **Production WILL render JavaScript** (headless browser). Ground truth is therefore built with a
   renderer too, preserving parity. **But see D13 — this was immediately qualified.**

8. **Anonymous-equivalent content only.** Never sign in to reach a source. Content only reachable
   while authenticated makes ground truth richer than production can reproduce — the parity
   violation running backwards, and harder to catch because the packet simply looks good.

---

## What changed in v4.4 — the short version

Full changelog is in the prompt's appendix; full evidence is in the defects log.

* **Section B rewritten** around the Indeed/Glassdoor split (D1), with the correct title-index route
  (D3), a warning that Glassdoor's `KO` URL segment is a *keyword* filter and not a job-title filter
  (D2), count-handling that assumes contradiction at every scale (D4), truncation reframed as a
  length-based selection effect (D7), and the duplicate B2/B3/B4 rule numbering fixed (D8).
* **Section F added** — 10-K Item 1 Human Capital (D5). Decided into packets on 2026-08-10, never
  written into any prompt version. Unnoticed because every company built before P-02 was private.
* **Hard rule 8 and the scope block at 2g** — record which population each section describes (D6).
* **Two retrieval methods, chosen per source**, in the prompt's opening requirements (D12, D13).
* **Section A gained a five-step fallback chain** it never had (D12).

---

## The thirteen defects — one line each

Detail and evidence in `V43_DEFECTS_LOG.md`. D1–D9 are v4.3 defects; D10–D13 were found while
building under v4.4.

| # | Defect |
|---|---|
| D1 | The two review sites are complementary, not substitutable. v4.3 picked the wrong one for text. |
| D2 | v4.3's Glassdoor URL pattern is the keyword filter, not the job-title filter. |
| D3 | Glassdoor's "top reviewed jobs" block truncates on a large company; the real index is on Indeed. |
| D4 | Counts contradict themselves *within a single page*, on both sites, at every sample size. |
| D5 | No 10-K Human Capital section existed, despite being decided in on 2026-08-10. |
| D6 | The "sample one title outside the core function" rule inverts on a large retailer. |
| D7 | Truncation is systematic, not incidental — a length-based selection effect. |
| D8 | Duplicate rule numbering in Section B (two each of B2, B3, B4). |
| D9 | Sections A and F describe a wider population than B — a consequence of the D6 resolution. |
| D10 | The same job title appears in two function categories with different counts and ratings. |
| D11 | Category labels are not function labels ("Software Development" is mostly in-store tech support). |
| D12 | **Section A is [YIELD] with no fallback chain, and its primary route is JS-gated.** |
| D13 | **The renderer is not strictly better than plain fetch — they reach different sources.** |

**D13 is the one that will bite an unwary successor.** Minutes after the renderer successfully
retrieved Section A from a page plain fetch could not touch, the same renderer was **bot-walled to a
sign-in page** on an Indeed job posting that plain fetch had returned in full moments earlier
(`from=bot-detection-anonymous` in the redirect). Rule:

* **Renderer** → JS-gated first-party sites (careers, values, culture, handbooks, blogs, the ATS).
* **Plain fetch** → review and job aggregators (Indeed, Glassdoor). Server-rendered and aggressively
  bot-defended; a renderer gains nothing and gets walled.
* Try both before recording any absence. Never sign in.

---

## Empirical finding that settled the scope question

From Indeed's `/cmp/Best-Buy/job-titles` index — the single most useful artifact found this session,
and the reason it is now step 1 of Section B:

| Title | Reviews |
|---|---|
| Sales Associate | 4,801 |
| Customer Service Representative | 3,454 |
| Sales Consultant | 2,497 |
| Technical Support Specialist | 1,042 |
| **Software Engineer** | **5** |
| **Product Manager** | **4** |
| **Data Analyst** | **3** |
| **Financial Analyst** | **3** |

For an employer of 85,000+ people, the entire corporate and technology organisation is in single
digits. **Sub-unit scoping was never available for this company — a corporate packet cannot be built
because the corporate evidence does not exist.** That is the empirical basis for decision 6, and it
is stronger than the argument originally given for it.

A rejected proposal worth not re-litigating: sampling 2–3 reviews from *every* title to "cover the
whole company." It over-samples 5-review strata at 60% against 0.06% for the largest, manufactures a
company that is half software engineers, injects `stage_size` through the dimension scores where the
confounder adjustment cannot strip it out, and would pull `Physician (1)`, `Pilot (1)` and
`Garden Nursery Worker (3)` into a Best Buy packet. Full reasoning is in the chat and summarised in
the defects log under D6.

---

## P-02 Best Buy — exact state

File: `ground_truth/packets/P-02_best_buy/P-02_packet_IN_PROGRESS.txt`

| Section | State |
|---|---|
| **A. Careers / values** | **COMPLETE** — 8 excerpts. Required the renderer. |
| **B. Employee reviews** | **PARTIAL** — 16 reviews across **2 of 4** planned titles. |
| **C. Job postings** | **COMPLETE** — 22 excerpts, 3 postings, 3 functions. |
| **D. First-person account** | **NOT STARTED** — ladder 0/7 rungs. |
| **E. Recent news** | **NOT STARTED** — 0 searches logged. |
| **F. Human capital (10-K)** | **NOT STARTED** — company is public, section applies. |
| 2b evidence coverage | Deferred until B, D, E, F are in. |
| 2c ladder checklist | Not started. |
| Section 3 roster/confounder | Stub only. |
| Section 4 anonymization | Partial notes only. |

### To finish P-02, in order

1. **Two more review titles.** Sales Associate (4,801 — the largest, untouched) and one
   customer-service title. Route:
   `indeed.com/cmp/Best-Buy/reviews?fjobtitle=<Title>&fcountry=US&sort=date` — **plain fetch, not
   the renderer.** ~20 reviews render per fetch, newest first.
2. **Glassdoor per-title subrating blocks** for all four sampled titles — numbers only, never quotes.
   Employer ID is **97**. **Check every URL for a `KO` segment first** (D2).
3. **Glassdoor recency cross-check** — OUTSTANDING and important. This is the specific check that
   caught the P-03/P-04 staleness artifact. Indeed's newest company-wide review is 2026-08-12, so
   this company is unlikely to show the same failure, but the check must be run and recorded.
4. **Section F** — the 10-K. `sec.gov/cgi-bin/browse-edgar?...` returned an empty document; use a
   different EDGAR route. Quote Item 1 Human Capital only. **Strip every headcount, dollar figure
   and percentage.** No earnings calls, financials, proxy tables or patent filings.
5. **Section D ladder** — all seven rungs, each logged with URL and outcome. The company's
   corporate/newsroom domain (`corporate.bestbuy.com`) is server-rendered and has a live news
   archive; the careers domain needs the renderer.
6. **Section E** — minimum two news searches with different phrasings, queries logged. Note a
   structural event already surfaced: a new CFO was appointed, announced 2026-08 on the corporate
   newsroom. Record its date in the vintage block per rule E.
7. Complete 2b, 2c, section 3, section 4, and the one-line scope declaration.

### Known-good routes for P-02 (verified this session)

```
RENDERER REQUIRED:
  jobs.bestbuy.com/bby?id=item_detail&content=culture     → Section A, rich
PLAIN FETCH:
  indeed.com/cmp/Best-Buy/job-titles                      → full title index + counts + ratings
  indeed.com/cmp/Best-Buy/reviews?fjobtitle=<T>&fcountry=US&sort=date  → ~20 reviews/fetch
  indeed.com/viewjob?jk=<id>                              → full posting body
  corporate.bestbuy.com/                                  → newsroom, culture copy, CR&S report
  glassdoor.com/Overview/Working-at-Best-Buy-EI_IE97.11,19.htm
BAD ROUTES — do not retry, they are logged as dead:
  jobs.bestbuy.com/bby?id=search_jobs&spa=1               → 404 even when rendered
  bestbuy.com/corporate/careers/culture                   → empty
  corporate.bestbuy.com/working-at-best-buy/              → empty
  indeed.com/cmp/Best-Buy/browse-reviews                  → returns LOCATIONS, not job titles
  sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=BBY  → empty
```

---

## Other packets — state, unchanged this session

* **P-01 Oscar Health — MISSING.** The folder `packets/P-01_oscar_health/` is **empty**. The v4.1
  changelog says a P-01 build happened, but no packet file exists in the repo. Either it lives in an
  earlier chat session or it was never saved. **Sebastian to check.** If unrecoverable it is a
  from-scratch build — public company, so Section F applies, and healthcare adds a
  member-services-vs-engineering split the prompt has not seen.
* **P-03 Akuna** — complete, built under v4.1 + amendment with Section B rebuilt under v4.3.
* **P-04 R/GA** — **internally contradictory and untouched this session.** Header says v4.2; Section
  B carries a v4.3 correction notice and a stratified rebuild; the yield audit still shows
  `B within 24 months: 0/15 FAIL`, which the Section B correction withdrew. Needs reconciling.
* **P-05 Doist** — partial. Section A and the C exemption only. Its own listed blocker stands: the
  first-person library has no dates on the index, so every candidate must be opened and dated
  individually before anything enters the packet.
* **P-06 Raymond James** — not started. Public, finance; expect the advisor-vs-corporate split to be
  the same shape as P-02's store-vs-corporate one.

---

## Predictions for the remaining builds — worth testing rather than trusting

* **P-06 and P-01 will both reproduce D6/D9.** Financial advisors and member-services agents will
  dominate their review populations the way store staff dominate P-02's.
* **Section F is untested.** P-02 will be the first packet ever to contain it. Expect the
  figure-stripping rule to be the awkward part — much Human Capital prose is built around metrics.
* **The C exemption has only been tested on a true positive** (P-05, genuinely not hiring). It has
  never been tested on a company that looks not-hiring but is not.
* **Expect at least one more prompt version.** Issues surfaced on every company built so far, and
  P-01 and P-06 are both types the prompt has never seen. Budget the final rebuild pass rather than
  hoping it is unnecessary.

---

## Untouched from the 2026-08-10 handoff

None of the following moved this session, and all remain open:

1. Re-run Test 2 (scorer variance) on a stronger model against the pre-registered bar.
2. Re-run Test 1 (blind vs. identified) properly at n=5 per condition.
3. Julie's reply on the primary-source split and the proposed 0.7 scoring rule.
4. **The correction owed to Julie** — the email asserting prior leakage from the confidence pattern
   overclaims; Test 2 undercuts it. Lead with the two out-of-packet phrases instead.
5. Define what confidence means before rater numbers land.
6. Build the citation-verification harness.
7. Bias-test the 24 assessment items; write `assemble_training_data(db)`.

---

## Framings that survived pushback this session

* **A packet is sub-unit-scoped either way.** Scoring "the company" silently means scoring whoever
  posts reviews. Recording the scope makes an accidental property visible; it does not create one.
* **Evidence is the binding constraint, not storage.** Role-conditioned company profiles are cheap to
  store and impossible to populate — 5 reviews cannot support a software-engineering score. This is
  why role/team matching was deferred to v2, and today's counts confirm that deferral was right.
* **Dispersion and role-conditioning are different things.** Dispersion is a company attribute
  ("experience varies here"). Role-conditioning is a different entity, one row per (company,
  function). Dispersion cannot produce the second from the first.
* **An empty or implausible response is not an absence.** Five variants of this error are now on
  record: `/insights`, the JS-gated careers page, the Glassdoor listing, the `Loading...` shell, and
  — the subtlest — a bot-detection sign-in wall that reads as a legitimate access requirement.
* **The instrument must not be confused with the finding.** P-03 and P-04's "reviews are years stale"
  was an artifact of the source. Ask what the tool would show if the claim were false, before
  recording the claim.
