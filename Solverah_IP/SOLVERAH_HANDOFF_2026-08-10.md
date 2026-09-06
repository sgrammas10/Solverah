# Solverah — Session Handoff, 2026-08-10

**Topic: the six-dimension critique, four instrument decisions, and three rebuilds of the evidence prompt.**
Custom instruction to honor: be logical and future-thinking, do not be agreeable — push back.

This session did NOT touch the causal model, the priors, or the assessment items. It was about
(a) Julie's argument that the six dimensions can't track patterns, (b) four instrument decisions
that followed from it, and (c) building packets, which broke the evidence prompt twice and produced
one significant correction.

---

## What triggered this session

Julie proposed a layered architecture — evidence → signal → pattern → tension → environmental
interpretation → person↔environment match — and argued the six dimensions are too coarse to track
patterns.

**The response that stuck:** her chain is an extraction and presentation architecture; the six
dimensions are an inference interface. They aren't competitors. But she's right that if only six
scalars survive into the model, the tension layer is decorative — it can't move a prediction and no
outcome can falsify it. The fix is **more structure per dimension, not more dimensions.**

Rejected: adding dimensions (person-side item burden, non-overlap requirement, twelve coefficients
already with zero training rows, and scorer SD ~0.098 puts finer dimensions below the instrument's
resolution). Rejected: embeddings (needs thousands of labeled outcomes, uninterpretable, and
encodes industry/size/prestige so confounder adjustment becomes impossible — the same failure that
killed dollars-comp and patent counts, now the third instance).

**Framing to keep: storage ≠ features.** Store the full evidence graph with IDs; score six
dimensions from it; let the narrative layer read from the graph and cite evidence IDs per sentence
so the citation harness can audit prose the same way it audits scores.

---

## Four instrument decisions (locked)

**1. Five bands, not 0–1 continuous.** Midpoints 0.1 / 0.3 / 0.5 / 0.7 / 0.9. Band width 0.2 sits
above the ~0.098 noise floor; seven bands would encode sampling variance. Bands map to midpoints and
enter the model as the same 0–1 value — no code or DDL change. Two side benefits: the agreement
threshold becomes interpretable (same band / one apart / two apart) instead of an arbitrary 0.15,
and it fixes the false precision of comparing a coarse forced-choice person score against a
two-decimal company score.

**2. Dispersion: IN, as a three-level ordinal** (consistent / some variation / highly variable).
**Stored, not modeled in v1** — adding a coefficient means adding another unvalidated prior on top
of twelve. Record it so that when outcomes arrive you can test the real hypothesis: high-dispersion
companies should show wider outcome variance at the same predicted fit. Do NOT let dispersion pull
scores toward 0.5. Note the coupling: five bands creates a 0.5 middle band that is ambiguous
without dispersion — it conflates "genuinely balanced" with "depends who you ask".

**3. Declared vs. experienced: the CHEAP version.** One score per dimension plus a flag for whether
non-company-authored evidence supports it. The full three-register split (marketing / operational /
experiential) is correct in principle but costs 18 scores per company. A two-way declared/experienced
split was rejected because it misfiles job posts — company-authored, but the operations-heavy
postings are what pulled innovation *down* in the Wayfair run.
**The ≤0.7 rule stays a MEASUREMENT, not an enforced cap.** Enforcing it would compress every
small private company toward the middle — the shrink-toward-0.5 failure arriving through another
door. This decision became load-bearing later in the session, not merely cheap.

**4. Confidence = how much evidence in the packet bears DIRECTLY on that dimension.** Three levels.
Not layer count (tracks company type, not evidence quality). Not source agreement — that collides
with dispersion and would systematically under-confidence the most informative companies.
**High dispersion is a finding; low confidence is an absence.** A company where engineering reviews
describe high autonomy and sales reviews describe none is high-dispersion AND high-confidence.
v1 role: stored and surfaced in the interface as a hedge, kept OUT of the ranking math.

---

## Rater plan: keep Julie, control by citation

Sebastian proposed replacing Julie with two people who wouldn't recognise the companies. Pushed
back and he agreed:

* Selecting for ignorance selects for low judgment; two naive raters can agree because they misread
  the same way, and the Agreement tab can't tell that from a well-specified anchor.
* It breaks the LLM validation — if the humans read worse than the model, the comparison measures
  the raters.
* It removes the expert from the instrument she has to fix.
* **It doesn't generalise.** A production scraper always knows the company. A control requiring an
  ignorant rater has no production analogue.

**Decision: drop the blindness claim entirely. Every score must cite the verbatim packet quote it
rests on; recognition Y/N stays as recorded data. Same string-match harness then checks humans and
the LLM.** Rater B is still needed — one rater's scores remain indistinguishable from that rater's
lens. George stopped over packet thinness, which v4.x addresses, so asking him back is the natural
move rather than recruiting.

---

## Roster: the six stand

P-01 Oscar Health · P-02 Best Buy · P-03 Akuna Capital · P-04 R/GA · P-05 Doist · P-06 Raymond James

Picked at random and they span all twelve poles. Industry hits all five levels; stage runs 2–5, a
real improvement on the 19-set's 78% stage-5 skew.

* **The blunt-feedback gap may have closed by accident.** Prop trading is direct without being a
  culture legend — the PnL delivers the feedback.
* **Concentration risk:** Doist carries three anchors alone (autonomy-high, pace-low,
  collaboration-solo) and Akuna carries three. At 19 companies anchors were redundant; at 6 they're
  single points of failure.
* **Oscar Health anchors nothing** — it's mid on everything. Keep it: with the 0.5 band and
  dispersion both new, you need one genuinely middling company to test whether raters use them.

**P-05 Doist has ZERO open roles** — verified against the careers page plus Glassdoor and LinkedIn.
Decision: **Section C drops to attempt-only when a company genuinely isn't hiring**, because job
postings exist for *hiring* companies, not all companies. Guarded against abuse — see below.

---

## The evidence prompt: v4.1 → v4.2 → v4.3

### v4.2 — after building P-03 and P-04

1. **Sections split into required-to-YIELD (A, B, C) and required-to-ATTEMPT (D, E).** D and E
   availability tracks ownership, size and press profile, not how a company works. Gating on their
   yield systematically fails small private companies — which correlates with `stage_size`, a
   confounder already in the model. Everyone works the same ladder; only the pass condition differs.
2. Entity check added to Section B.
3. **Staleness gate made general** — it previously applied only to ladder rung 2, which is how a
   2017 leadership interview reached the P-03 packet.
4. Review-recency line in the yield audit, plus a **researcher-computed vintage block** (2f).
   Facts, not judgments — rater time is the scarce resource.
5. Ladder rung 7 added: conference talks. Honest note — it returned nothing for P-03.
6. Truncation, duplicate and preserved-typo handling. Machine-written aggregator summaries banned.
   Every posting must be opened individually: on P-04 an aggregator listed six roles as recent,
   four were opened, **three were already closed**, each saying so only on its own page.
7. Greenhouse **list API** added to the C fallback chain — it fetched cleanly when the board page,
   embed board and detail API all returned empty, and answers open/closed directly.

### v4.3 — after testing the review sources properly

**This version exists because v4.2 was built on a false premise and produced two packets with wrong
headline findings.**

Glassdoor's whole-company listing returns an empty document, and that was recorded as "Glassdoor
unusable". It is not. Permalinks render — v4.1 already said so — and **job-title-filtered review
pages render fully, newest-first, three per page, with predictable pagination**. Section B had been
built entirely from Indeed, which held **22 reviews for P-03 against ~150 on Glassdoor, and 34 for
P-04 against 768.**

Both packets had concluded the companies' reviews were years stale. P-04's told the rater in bold
that every structural event postdated the review set. Glassdoor holds 2026 reviews for both,
including a P-04 tech director's titled "3 Layoffs in a Year?".

**Changes:**
1. **Section B is sampled stratified by job title, newest-first within each title.** Deterministic,
   paginated, selects on nothing but date inside a bucket — so the no-curation rule holds — and
   stratified by function, which is what dispersion needs.
2. **Per-title subratings captured**, with a mandatory validation step (below).
3. **Cross-site rating divergence recorded, never reconciled.** P-03 scored 4.2 on work-life balance
   on one site and 3.1 on the other.
4. Interview write-ups excluded and logged; job titles normalised before bucketing; bucket counts
   never quoted as population sizes.

---

## THE FAILURE THAT REPEATED THREE TIMES — the most important lesson here

**An empty response was read as an absence.** Three separate sections, same error:

| Section | Guessed | Reality |
|---|---|---|
| C (P-04) | careers page rendered no roles → assumed none | 21 open roles on the ATS |
| D (P-04) | `/insights` returned empty → "no blog" | blog lives at `/news`, entirely current |
| B (both) | Glassdoor listing returned empty → "unusable" | 768 reviews behind title filters |

Proof-of-absence rules now apply to **every** source class in v4.3, including ones an earlier
version of the prompt already explained how to reach. Before declaring anything absent: survey the
site's own navigation, and confirm on independent sources.

The Doist Section C exemption is guarded the same way — it requires an **affirmative zero** (a
rendered, empty role list, not silence) confirmed on **two independent sources**, with the full
fallback chain worked anyway.

---

## THE DISPERSION RESULT (P-03) — and what it does to the model

Same company, same period, five job titles:

| | Trader | SoftDev | QuantRes | TradIntern | JuniorTrader |
|---|---|---|---|---|---|
| Overall | 4.2 | 4.4 | 4.3 | 4.0 | **3.7** |
| Would recommend | 86% | 91% | 81% | — | **24%** |
| Senior management | 4.6 | 3.9 | 3.9 | 4.0 | **2.8** |
| Work/life balance | 4.7 | 4.5 | 4.1 | 3.0 | 3.6 |

A 1.8-point spread on senior management and 67 points on recommendation rate, inside one firm.
**The split is not a clean seniority gradient** — Trading Interns score 4.0, *above* Junior Traders.
Four of five titles cluster 4.0–4.4; one population sits alone at the bottom. Whatever is happening
is specific to the first permanent trading seat.

A reviewer states the thesis directly: work-life balance "can vary significantly depending on team
and market conditions", mentorship "can depend heavily on the specific desk, manager, and business
priorities", and project ownership "can also be limited depending on the team". Within-company
variance on three dimensions, first-person, from inside the packet.

**CONSEQUENCE FOR THE MODEL — unresolved, needs a decision.** v1 scores a company and matches a
person to that company. If the largest within-company variance is a LEVEL effect, a single company
score isn't merely imprecise for an early-career candidate — it is wrong in a predictable
direction, because the score is built mostly from more senior voices. Role and level matching was
deferred to v2 on the grounds that the data doesn't exist. **This data exists, it is free, and it
arrives attached to every review.**

---

## Rating blocks must be validated (P-04)

P-03's per-title ratings looked internally consistent. P-04's are demonstrably not:

* **Designer** — headline 4.7, "0% would recommend", and all six categories exactly 1.0. The three
  rendered reviews scored 5.0, 4.0, 1.0.
* **Senior Software Engineer** — "99% would recommend" from 14 reviews. Impossible; values step by
  ~7.1%.
* **Creative Director** — 89% from 28 checks out (25/28), but "99% approve of CEO" fails again at a
  different sample size.

**Three checks before recording any block:** every percentage achievable at that n; headline
consistent with the six categories; both consistent with the rendered reviews.
**Observed prior:** the six category ratings are more often sound than the recommend / CEO-approval
/ outlook percentages. Treat percentages as unreliable by default. The value "99%" appeared twice at
sample sizes where it is impossible — likely a display artifact.
**Ignore CEO approval entirely** unless the named executive is confirmed current — the site still
names one replaced three years and one ownership change earlier.

---

## Packet status

| | Status | Notes |
|---|---|---|
| P-01 Oscar Health | Built under v4.1 by Julie | Section B needs rebuilding under v4.3 |
| P-02 Best Buy | Not started | Should be the easiest — huge current review volume |
| P-03 Akuna Capital | **COMPLETE** | A/B/C pass; D and E worked, zero yield, logged |
| P-04 R/GA | Near complete | D7 conference talk found, in-date, text not yet retrieved |
| P-05 Doist | Partial | A done; C exemption validated; D blocked on undated articles |
| P-06 Raymond James | Not started | |

**Source availability, established:** Indeed renders whole-company newest-first with job title and
location. Glassdoor renders permalinks and title-filtered pages, never the whole-company listing.
Reddit is blocked outright. Built In carries full posting bodies. Greenhouse list API works.

---

## Three D-section failure modes — all distinct, all worth recording

* **P-03** — no publication at all. Private trading firm: no blog, no handbook, empty repo org, a
  nine-year-old leadership interview, no press in 12 months.
* **P-04** — publication current and abundant, but client-facing market commentary on a gated
  lead-capture platform. Nothing about the company's own working practice.
* **P-05** — publication abundant and squarely on working practice, but the index carries no dates
  and part of the library sits on a secondary domain with 2022–2023 markers.

**An abundant, on-topic, first-person library is not automatically usable evidence.**

---

## Framings that survived pushback this session

* Storage ≠ features. Store the evidence graph; score six dimensions from it.
* More structure per dimension beats more dimensions — extraction-side only, doesn't touch the
  assessment, adds no coefficients that need outcome data.
* High dispersion is a finding; low confidence is an absence. Never conflate them.
* Sections are required-to-yield or required-to-attempt. Availability of a source class is often a
  property of the company, not of research effort.
* An empty response is not an absence. Survey navigation, confirm independently, then declare.
* Anonymisation is a test instrument, not a production control. Citation verification is what
  survives a scraper that always knows the company.
* Excluding hard cases from calibration means discovering the failure in production, where you
  can't see it. (Sebastian's argument, and the right one.)

---

## Open / next

1. **Decide the level/role question.** The P-03 dispersion result says a company-level score may be
   systematically wrong for early-career candidates. This is the biggest open item and it is a
   model question, not a packet question.
2. **P-05 Doist**: date the six D candidates, run the stratified sample against employer 1102553
   (expect very thin buckets — the hardest test of the frame on a small company), probe ATS routes
   to complete the C chain, Section E.
3. **P-04**: second retrieval pass on the D7 conference talk. It is the most promising D source
   located and only a search-result paraphrase exists so far.
4. **P-01 Oscar Health**: rebuild Section B under v4.3.
5. **P-02 and P-06**: build from scratch under v4.3.
6. **Rubric to v3**: fold in five bands, dispersion ordinal, confidence definition and three levels,
   per-dimension verbatim citation field, recognition Y/N, non-company-source support flag. Remove
   all "blind" language.
7. **Scale-cost caveat, unresolved.** Stratified sampling costs roughly one fetch per job title per
   company. Fine for six packets; tens of thousands of requests at production scale, against a site
   that refuses to serve its own listing pages. The ground-truth packets may end up richer than a
   production scraper can reproduce — which would mean calibrating the extractor against input it
   never sees. Same objection Sebastian raised in July about hand-researching filings, arriving from
   the other direction.
8. Untouched and unblocked: bias-test the 24 assessment items; write
   `assemble_training_data(db) -> (person, env, conf, outcome)`; re-run the scorer variance test on
   a stronger model; build the citation-verification harness.

---

## Files produced this session

```
Solverah_IP/ground_truth/
  SOURCE_AVAILABILITY.md              which sources fetch, which don't, and the traps
  PACKET_FEASIBILITY_FINDING.md       packet richness tracks company type, not culture
  rubric/
    Company_Culture_Evidence_Collector_v4.2.{md,docx}
    Company_Culture_Evidence_Collector_v4.3.{md,docx}   ← current
  packets/
    P-03_akuna_capital/P-03_packet.txt        COMPLETE
    P-04_rga/P-04_packet.txt                  near complete
    P-05_doist/P-05_packet_PARTIAL.txt        partial
```
