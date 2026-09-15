# Solverah — AI Governance Notes: RMF Mapping, Content Rules, Claims Audit

**Created 2026-08-20. Covers GAP-08 (RMF mapping), GAP-14 (quotes vs scores), GAP-02 (claims audit). Three short sections, one file, because they share one purpose: keeping what Solverah says aligned with what it does.**

---

## 1. NIST AI RMF mapping — where Solverah's existing practice already lands

Purpose: make the validation work legible to lawyers, I-O reviewers, and future enterprise buyers without inventing new process. **This maps existing artifacts; it does not create obligations.**

| RMF function | Solverah practice that satisfies it | Artifact |
|---|---|---|
| **GOVERN** | Locked-decision register with amendment discipline; agent operating policy with red-line authority limits; decision queue for human sign-off | STATE.md §4 (D-01…D-22), AGENT_OPERATING_POLICY.md |
| **MAP** | Explicit construct definitions (6 dimensions, poles, rubric anchors); documented scope limits (v1 = one company one score, D-22; candidate-facing only, D-01); known-limitation register (S-09 construct mismatch, attenuation ≈0.63) | assessment_items_v2.yaml, anchors.json, STATE §5 |
| **MEASURE** | Pre-registered analyses before data arrives (S-17/S-18); seed/dispersion discipline at the point numbers are produced (D-21); inter-rater agreement instrumentation (S-15, three-way dispersion); re-identification testing; mutation-tested verification suites | PREREGISTRATION_2026-08-19, seed_discipline.py, rater_agreement.py, reid CSV |
| **MANAGE** | Confidence grading on every score (D-17) with binding semantics (never read as gaming/honesty); refusal-over-degradation contract rule (D-07); external expert review sought pre-launch (S-05 I-O brief) | score_person_side.py, IO_REVIEW_BRIEF.md |

Gap the mapping exposes (file as future item, not now): once N≥300 respondent data exists, add a **proxy-for-protected-class check** to the S-17 correlation analysis — preference dimensions should be shown not to function as proxies. Pre-registered like everything else.

---

## 2. Quotes vs. scores — the product rule for company content (GAP-14)

**Rule:** derived scores, model outputs, and paraphrase may appear in the product. **Verbatim third-party quotes stay in the research layer** (packets, rater materials) and never render in user-facing company profiles.

Why: a score is a fact Solverah computed and owns. A quoted review is someone else's copyrighted text, often sourced under platform ToS that prohibit republication. Internal research use and public display are different legal postures; the pipeline must not blur them.

Enforcement: applies to `company.profile_json`, culture narratives, and any future company surface. When building the match-surface UI (launch-blocker item 7), add a check that rendered company content contains no packet-quote text.

---

## 3. Marketing-claims audit (GAP-02) — landing/prelaunch copy vs. practice

| Claim (location) | Status | Action taken / proposed |
|---|---|---|
| "Private by Default — your data is yours, shared only with your consent" (prelaunch stats row) | **Was false as worded** — resume/profile flow to LLM providers without a consent surface | **Edited in this change set** to: "Private by design — never sold, never shown to employers." Both halves are true and enforced (D-01 test suite; no data sales). |
| "Privacy Policy" footer link → `#` | Was a dead link | **Wired to /privacy** (real page) |
| "Context before automation …" and similar positioning copy | Opinion/positioning — fine | None |
| Any future claim of "predicts job success/performance" | **Do not make** until UGESP-grade criterion validity exists | Standing rule; revisit post-S-17/S-18 with real outcome data |
| "De-identified" vs "anonymized" | D-10 already governs | Keep applying to all public copy |

**Standing rule going forward:** every marketing claim about data or accuracy must name the artifact that makes it true (the D-01 suite, the policy section, the pre-registration). A claim with no artifact is the S-35 failure mode pointed at the public.
