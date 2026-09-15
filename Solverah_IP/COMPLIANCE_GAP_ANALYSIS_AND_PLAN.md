# Solverah — Compliance Gap Analysis & Remediation Plan

**Date:** 2026-08-20. Companion to `SOFTWARE_STANDARDS_COMPLIANCE_REFERENCE.md` (section references `Ref §n` point there).
**Audited:** the `Solverah` repo as connected today (app.py @ 146KB / 38 routes, model.py, security.py, frontend `src/`, CI workflows, dependency manifests). Evidence cites file:line.
**Scope per Sebastian:** US-only launch; payments planned soon after; no employers on the platform for the first several iterations (company side = generated profiles).

**Not legal advice.** This is an engineering-grade gap map to take to a lawyer, not a substitute for one.

---

## 0. The honest top-line

Three things dominate everything else in this list:

1. **The legal-document layer does not exist.** No privacy policy, no terms of service. The footer link is `href="#"` (`prelaunchlandingpage.tsx:495`), registration has no terms acceptance at all (`Register.tsx` — zero matches for terms/privacy), and the intake flow **requires** `privacy_consent` (`app.py:1325`, `app.py:2783`) — consent to a document that doesn't exist. That last one is worse than having no consent: it's a recorded representation with nothing behind it.
2. **A user cannot delete their data, and nothing says how long you keep it.** There is no delete-account endpoint (zero matches across all 38 routes), no data-export endpoint, no retention rules for resumes in R2, `IntakeSubmission` PII, or `AuditLog` IP/user-agent rows. And **D-16 (append-only, never overwritten) is on a collision course with deletion rights** — see GAP-03.
3. **The marketing copy makes promises the data flows don't keep.** "Private by Default — your data is yours, shared only with your consent" (`prelaunchlandingpage.tsx:138`) — while resume text, name, work history, and education go to OpenAI/Groq in agent-chat context (`app.py:411–470`) with no disclosure anywhere. Under FTC §5, the gap between what you say and what you do *is* the violation (Ref §1). This is the same claim-vs-practice discipline as D-10 ("de-identified, never anonymized") — applied to the product surface instead of the methods documents.

The good news: because there are **zero users**, every one of these is cheap to fix now and expensive to fix later. Retrofitting deletion into an append-only schema with real user rows would be a migration project; today it's a design decision.

**What does NOT apply yet — deliberately out of scope:** GDPR/UK GDPR/EAA (US-only launch — but see GAP-19 on geo-scoping), PCI DSS (no payments yet — enters at Phase 3), HIPAA/FERPA/GLBA (no regulated-sector data), FedRAMP/CMMC (no government sales), NYC LL144 / Illinois HB 3773 / Colorado AI Act duties (those attach to **employers and employment agencies using** AEDTs — with no employers on the platform, no employment decision is being made about anyone; see GAP-08 for the trigger that changes this), DSA/DMA/OSA (no EU/UK), SOC 2 (no enterprise buyers yet — Phase 3).

---

## 1. What is already in good shape (so it doesn't get re-litigated)

- **Password + auth hygiene:** bcrypt hashing, login lockout (`MAX_LOGIN_ATTEMPTS`/`LOCKOUT_MINUTES`), OTP flows, JWT in HttpOnly cookies with CSRF protection on state-changing methods (`app.py:277–279`), no default secret — hard fail if `JWT_SECRET_KEY` unset (`app.py:255`), D-05 honored.
- **Transport security:** Talisman with `force_https`, full HSTS (max-age 1y, subdomains, preload) in production (`app.py:236–246`).
- **Rate limiting** on all auth endpoints (3–5/min) plus global defaults (`security.py`).
- **D-01 as an enforced control:** `test_employer_visibility.py` as a reachability allowlist is exactly the kind of technical measure privacy regulators mean by "data protection by design." It's a compliance asset — say so in diligence.
- **De-identification discipline** (D-10 language rule, re-identification testing) — ahead of most startups.
- **`AuditLog` table exists** with actor/action/IP/UA (`model.py:91–101`) — the skeleton of breach forensics.
- **Transactional-only email** (`email_utils.py` — verification, reset, notifications; no marketing sends) — CAN-SPAM clean today.
- **Presigned direct-to-R2 uploads** — resume bytes never transit your server; good scope reduction.
- **Dependency licenses:** the Python and npm dependency sets are permissive (MIT/BSD/Apache; psycopg2's LGPL is fine as used). No AGPL/SSPL traps found. Two *ToS* problems hide in the dependency list — GAP-13/14 — but no *license* problems.

---

## 2. Gap register

Severity: **BLOCKER** (fix before publicity) · **HIGH** (fix at launch or within 30 days) · **MED** (90 days) · **TRIGGER** (dormant until a named event — the trigger is part of the finding).

### Legal documents & truthful representation

**GAP-01 · BLOCKER · No privacy policy or terms of service.** (Ref §1, §7)
Evidence: `href="#"` footer link; no policy page/route anywhere in `src/pages`; registration collects email+password+name with no acceptance step.
Why it's not optional even at zero scale: **CalOPPA** requires a conspicuous privacy policy for any commercial site collecting personal info from California residents — no user-count threshold. FTC §5 covers everyone. And you are *already* collecting: early-access emails (`/api/early-access-request`), full intake PII incl. phone/LinkedIn/resume (`IntakeSubmission`, `model.py:176–193`).
Fix: privacy policy (what's collected, why, who it's shared with — **naming the subprocessor categories: LLM providers, email, hosting, storage**, retention, rights, contact), ToS (eligibility 18+, acceptable use, disclaimers — including that insights/matches are **informational career guidance, not hiring decisions or guarantees**, arbitration/venue per counsel), acceptance checkbox on register + intake, real footer links. The `privacy_consent` boolean finally gets an object.

**GAP-02 · BLOCKER · Marketing claims vs. actual data flows.** (Ref §1 — FTC §5)
Evidence: "Private by Default … shared only with your consent" (`prelaunchlandingpage.tsx:138`) vs. `_build_agent_context` shipping name, summary, skills, experience, education, and raw resume text to OpenAI (`app.py:411–470`), plus Groq as a second LLM path (`app.py:393–399`).
Fix is two-sided: **(a)** disclose LLM subprocessors in the privacy policy and in-context ("your profile and resume are used to generate this" near agent chat); **(b)** audit every marketing string on the landing/prelaunch pages against reality — the D-10 exercise, product-wide. Also verify + record each provider's API data-use terms (OpenAI API: no training on API data by default; **confirm the equivalent for Groq and set zero-retention options where offered**) in a vendor register (GAP-11).

**GAP-03 · BLOCKER · No user data deletion or export; D-16 collision.** (Ref §1)
Evidence: no delete route; no export route; resumes persist in R2 with no lifecycle; `IntakeSubmission` rows for people who **never became users** (abandoned intakes) persist indefinitely.
The design conflict: **D-16 says raw responses are append-only, never overwritten.** Deletion rights (CCPA-style, and plain user expectation) require erasure or true de-identification on request. These reconcile — D-16 governs *scoring integrity* (no silent edits), not *rights erasure* — but that reconciliation must be **decided and written**, not improvised later: e.g., account deletion nulls the `user_id` linkage and purges PII/resume/profile while retaining de-identified response rows for research, OR hard-deletes everything. Both are defensible; pick one.
Fix: `/api/account/delete` (auth'd, confirmation step) covering: User row, profile_data, R2 resume objects, IntakeSubmission, UserIntake, AssessmentResponse/PersonDimensionScore (per the decision above), audit-log PII after N days. Export = JSON dump of the same. **File the D-16 reconciliation in the decision queue — it amends a locked decision, which is Sebastian's call, not an implementation detail.**

**GAP-04 · BLOCKER · No retention schedule.** (Ref §1)
Evidence: nothing expires — abandoned intakes, early-access submissions (emailed to info@ — so PII also lives in the inbox), audit-log IP addresses, LLM debug artifacts (`llm_debug.txt`, `scoring_debug.txt` — check for real user data in repo-committed debug files).
Fix: a one-page retention schedule (abandoned intakes 90 days; audit-log IP/UA 12 months; resumes = life of account; early-access list until launch + N months) + a scheduled cleanup job. Cheap now; also shrinks breach blast radius, which is the argument that convinces engineers.

**GAP-05 · HIGH · No age gate / minors posture.** (Ref §1 — COPPA; §8)
Evidence: zero matches for birth/age/minor across registration and app.py.
A career platform is not child-directed (COPPA risk is low) but a 16-year-old *can* sign up today and nothing says they can't. Fix: 18+ (or 16+) eligibility in ToS + an attestation checkbox at registration. One line of law-triggering surface removed.

### Security regulation & posture

**GAP-06 · BLOCKER · No incident-response/breach plan.** (Ref §1 — 50-state breach laws; §2)
Breach-notification laws bind at **any** size, and you hold exactly the data classes they cover (emails + auth credentials; resumes). There is no IR document.
Fix: one page — severity tiers, who does what (a company of ~1 still needs the list: isolate, rotate secrets, assess scope via AuditLog, notify affected users + AGs per state timelines, counsel's number), where logs live (Render/Vercel retention — check and record it). Pair with: **secret-rotation runbook** (JWT key, R2 keys, API keys — note D-39's "don't rotate mid-form" constraint), and resolve **S-42** (prod values in local `.env` — the "script against prod believing it's dev" failure mode is itself an incident class).

**GAP-07 · HIGH · Security-posture gaps below the headline layer.** (Ref §2, §3)
(a) **Rate-limit storage is `memory://`** (`security.py`) — with multiple gunicorn workers, each worker counts separately and counters reset on every deploy; the credential-stuffing protection is weaker than it reads. Move to Redis/Postgres-backed storage, or accept + document.
(b) **CSP is `default-src` only** (`app.py:238–240`) — adequate baseline (no `unsafe-inline`), but add explicit `script-src`, `frame-ancestors`, `object-src 'none'` for the API responses, and note the *frontend* on Vercel serves its own headers — Talisman does not cover it. Set CSP/headers in `vercel.json` too (currently rewrites only).
(c) **JWT access tokens live 1h with no refresh mechanism visible** — fine security-wise, but confirm the UX story, and confirm logout revocation semantics (cookie clear only = token valid until expiry; acceptable at 1h, write it down).
(d) **No dependency scanning in CI** — `tests.yml` runs tests only. Add `pip-audit` + `npm audit --audit-level=high` + Dependabot. This is the cheapest real security control you're missing, and (Ref §3) SBOM/supply-chain hygiene is where customer questionnaires start.
(e) **PII in logs:** `user.email` interpolated into error logs (`app.py:1813,1849,1963`) — switch to user IDs; Render log retention then matters less.
(f) **Debug/scratch files with possible real data committed to the repo** (`llm_debug.txt`, `scoring_debug.txt`, `zensearchData/`, `Filtered_Data/`, stray `.docx` specs) — audit once, gitignore the patterns, purge history if anything sensitive (S-41's `_to_delete` discipline, applied to data).

### AI & employment-decision exposure

**GAP-08 · HIGH (posture) + TRIGGER (obligations) · The employment-AI regime attaches at employer onboarding — prepare the evidence file now.** (Ref §4, §11)
Current honest read: WorkPulse + the match are **candidate-facing career guidance** — the person sees their own fit information; no employer sees anything (D-01); no employment decision is made or assisted. NYC LL144, Illinois HB 3773, Colorado's AI Act (postponed anyway), and EEOC disparate-impact doctrine regulate **employers/agencies making decisions about people** — not this, yet.
Three tripwires, each converting this from "not applicable" to "fully applicable":
1. **Employers join and see match results** → Solverah plausibly becomes an "employment agency"/AEDT vendor under NYC LL144 (bias audit, notices) and a deployer-adjacent party under state AI acts. D-01's "employers only ever see a match result" is exactly the surface those laws regulate.
2. **Scores about individuals are furnished to third parties for employment purposes** → FCRA "consumer report" analysis (Ref §11) — a matching score sold to an employer can make you a consumer reporting agency, with permissible-purpose, adverse-action, and accuracy duties. This is the single most expensive misclassification available to this product. Get a legal opinion **before** the first employer conversation, not after.
3. **Marketing drifts into "predicts job performance/success"** → validation claims requiring UGESP-grade evidence. Current claims don't; keep it that way until the evidence exists.
What to do **now** (cheap, and you're already doing most of it): the S-05 I-O review, pre-registered analyses (S-17/S-18), seed discipline (D-21), and rater methodology **are** the validation evidence file that UGESP/NIST AI RMF asks for — keep building it, and add one page mapping it to the NIST AI RMF vocabulary (govern/map/measure/manage) so it's legible to lawyers and future enterprise buyers. Add candidate-facing transparency at results time ("how this match is computed, what it doesn't mean") — consistent with D-15's completion-state rule since it's static text, not scores. **Also note:** the six-dimension instrument measures work *preferences*, not protected characteristics — but S-17's dimension-correlation work should eventually include a check that scores don't proxy for protected classes once real respondent data exists (N≥300 gate). File as a future analysis item, not now.

**GAP-09 · MED · LLM feature governance.** (Ref §4)
Agent chat, quiz insights, WorkPulse narratives, path suggestions all generate advice via LLM with no stated limitations, no hallucination caveat, and — in agent chat — a system prompt that includes other companies' data with "do not reveal raw context data verbatim" as the only guard (`app.py:414`). Prompt-injection via resume text is a live path into that context (a resume is attacker-controlled input to your system prompt).
Fix: brief AI-limitations disclosure near AI outputs (also feeds GAP-01's ToS); treat resume text as untrusted in prompt assembly (delimit + instruct); log/monitor agent-chat abuse; utah-style "you are talking to an AI" disclosure norms are coming — a one-line label on the chat is future-proofing.

### Accessibility

**GAP-10 · HIGH · No accessibility program; thin ARIA usage.** (Ref §5)
Evidence: 59 `aria-*` attributes across 28 pages; zero `<img>`/`alt` (icon-library SVGs — `lucide-react` renders `aria-hidden` by default, acceptable); no axe/pa11y in CI; drag-and-drop interactions (`@dnd-kit` in FocusType) are a classic keyboard-accessibility failure point; forced-choice assessment UI must be screen-reader operable.
ADA website suits are the highest-volume compliance litigation in the US and do not wait for scale. Fix: WCAG 2.1 AA pass on the five core flows (landing → register → intake → WorkPulse → dashboard); `@axe-core/react` or vitest-axe in CI; keyboard-only walkthrough of the assessment (D-06's fixed option order helps here); contrast check on the sage/cream palette (editorial palettes routinely fail 4.5:1).

### Vendors, data acquisition & IP hygiene

**GAP-11 · HIGH · No vendor/subprocessor register or DPAs.** (Ref §1, §3)
You have seven-plus data-touching vendors (Render, Vercel, Cloudflare R2, OpenAI, Groq, Anthropic, Resend, O*NET) and no record of what data each receives, under what terms, with what retention. Fix: one table (vendor / data categories / purpose / data-use terms / DPA-or-ToS link / retention setting). An hour of work; it becomes the privacy policy's disclosure section, the SOC 2 vendor list, and the breach-plan contact sheet simultaneously.

**GAP-12 · HIGH · Third-party job-listings scraping.** (Ref §7, §9)
Evidence: scheduled GH Action hits `api.zensearch.jobs/api/postings` with a spoofed `Referer: https://zensearch.jobs/` every 2 days and commits results to the repo (`zensearch.yml`, `Scripts/zensearch/zensearch.js:145–151`).
The spoofed referer is the tell — it means access is not on their intended terms. If this data feeds product recommendations, contractual/ToS exposure sits under a user-facing feature. Fix: read ZenSearch's terms; get permission or an API agreement, or replace the source (official job-board APIs, employer feeds); stop committing scraped data to the repo either way.

**GAP-13 · MED · `@vitalets/google-translate-api`.** (Ref §9)
An unofficial scraper of Google Translate's web endpoint, imported in `Scene4/Scene5/LandingNav`. It violates Google's ToS and breaks without notice. Replace with an official translation API or drop the feature — decide based on whether translation is actually load-bearing.

**GAP-14 · MED · Company-evidence sourcing terms.** (Ref §9)
The ground-truth packets quote third-party reviews/press under source-class rules — fine as internal research. The tripwire: **displaying** quoted third-party content (reviews, Glassdoor-class material) in the product's company profiles is a different copyright/ToS posture than using it internally to derive a score. The score itself (a fact you computed) is clean; republishing the quotes is not automatically. Rule of thumb to adopt: derived scores and paraphrase in-product; verbatim quotes stay in the research layer.

**GAP-15 · MED · Corporate/IP formalities.** (Ref §9)
Outside the repo but blocking everything legal: confirm entity formation + IP assignment into the company (sole founder ≠ automatic; and any contributor — the intern-onboarding doc implies one existed — needs an IP assignment on file), trademark search + filing for "Solverah" (also "WorkPulse" — a crowded namespace worth checking before publicity bakes it in), repo LICENSE decision (it's proprietary — say so in the repo), copyright notices. The IP-planner workstream owns the inventions; this item is the *container* they're assigned to.

### Dormant regimes with named triggers

**GAP-16 · TRIGGER (user thresholds) · State comprehensive privacy laws.** Most bind at 35k–100k+ residents or revenue thresholds; at 10s–100s of users none bind (Texas's broad law exempts SBA small businesses except its sensitive-data-sale consent rule). **Do the rights machinery now anyway (GAP-01/03/04)** — the thresholds arrive without announcing themselves, and the append-only schema makes late retrofit expensive. Re-check at every 10× user growth.

**GAP-17 · TRIGGER (payments) · PCI, tax, subscriptions.** (Ref §3, §7) At first paid plan: tokenized processor (Stripe-class) → SAQ-A scope; never touch PANs; sales-tax registration per economic nexus (SaaS taxability is state-by-state); auto-renewal laws (CA's is the strictest: clear disclosure, one-click cancel); refund terms in ToS.

**GAP-18 · TRIGGER (marketing sends) · CAN-SPAM.** First non-transactional email: unsubscribe link, postal address, honest subject lines. List hygiene from the early-access table (they opted into *interest*, not a newsletter — one-time "we launched" is defensible; recurring marketing needs its own consent).

**GAP-19 · TRIGGER (non-US users) · GDPR et al.** Nothing geo-gates signup today, so "US-only" is an intention, not a fact. Cheapest honest posture: ToS states the service is offered to US residents; don't market abroad; revisit before any EU marketing (which flips on GDPR incl. Art. 22 automated-decision rights — directly implicating the match). Actively blocking EU IPs is not required for the intended-market argument, but write the intention down.

**GAP-20 · TRIGGER (enterprise/employer sales) · SOC 2 + ISO 42001.** (Ref §3, §4) First enterprise security questionnaire will ask for SOC 2 Type II (6+ month lead time including observation window). Don't start the audit now; do keep the practices that make it cheap later: access control, CI, dependency scanning (GAP-07d), vendor register (GAP-11), IR plan (GAP-06) — all of which you're building anyway. ISO 42001 is the emerging ask for AI vendors; the validation evidence file (GAP-08) is most of its substance.

---

## 3. Remediation plan

Effort estimates assume Sebastian + Claude-assisted drafting; legal review where marked ⚖ is a real lawyer, once, on finished drafts — cheaper than open-ended consultation.

### Phase 0 — before publicity (the launch gate) · ~3–5 working days total
Order matters: 1 → 2 unblock everything user-facing; 3–4 are schema-adjacent and should land **before the S-07 migration is applied**, which is the cheapest moment (same reasoning as S-51 OPEN 2).

| # | Action | Gaps closed | Effort |
|---|---|---|---|
| 0.1 | Draft privacy policy + ToS (18+ eligibility, AI-limitations language, US-residents scope line, subprocessor disclosure). ⚖ review both | 01, 02, 05, 09, 19 | 1–1.5 d draft + review |
| 0.2 | Vendor/subprocessor register; verify OpenAI/Groq/Anthropic/Resend data-use terms; set zero-retention flags where offered | 11, 02 | 0.5 d |
| 0.3 | **Decide the D-16/deletion reconciliation (decision queue)**, then build `/api/account/delete` + `/api/account/export`, incl. R2 object deletion and IntakeSubmission purge | 03 | 1 d |
| 0.4 | Retention schedule (one page) + cleanup job for abandoned intakes and aged audit rows | 04 | 0.5 d |
| 0.5 | Wire acceptance: register + intake checkboxes bind to real documents; fix footer links; align every landing-page claim with actual practice | 01, 02 | 0.5 d |
| 0.6 | Incident-response one-pager + secret-rotation runbook; resolve S-42 while in there | 06 | 0.5 d |
| 0.7 | PII out of logs (IDs not emails); one-time audit of committed debug/data files | 07e, 07f | 2 h |

### Phase 1 — at launch / first 30 days · ~2–3 days
| # | Action | Gaps | Effort |
|---|---|---|---|
| 1.1 | WCAG 2.1 AA pass on the five core flows; axe in CI; keyboard-only assessment walkthrough; palette contrast check | 10 | 1–2 d |
| 1.2 | CI security: pip-audit + npm audit + Dependabot | 07d | 2 h |
| 1.3 | Rate-limiter backing store → Redis/Postgres; CSP hardening incl. Vercel headers | 07a, 07b | 0.5 d |
| 1.4 | Candidate-facing "how matches work / what they don't mean" static page; AI label on agent chat; resume text treated as untrusted input in prompt assembly | 08, 09 | 0.5 d |
| 1.5 | Resolve ZenSearch sourcing (permission, replacement, or removal); stop committing scraped data | 12 | 0.5 d + outreach |

### Phase 2 — first 90 days · ~2 days + external processes
| # | Action | Gaps | Effort |
|---|---|---|---|
| 2.1 | Entity/IP-assignment/trademark sweep ("Solverah", "WorkPulse") ⚖ | 15 | mostly counsel |
| 2.2 | Replace/drop unofficial translate dependency | 13 | 2 h–0.5 d |
| 2.3 | Quotes-vs-scores product rule for company profiles (derived scores in-product; verbatim quotes research-only) — write it into the packet/product pipeline docs | 14 | 2 h |
| 2.4 | NIST AI RMF one-page mapping of the existing validation evidence (S-05 brief, pre-registrations, D-21, rater method) | 08, 20 | 0.5 d |
| 2.5 | Marketing-email readiness if the "we launched" send is planned (unsubscribe, address, consent posture) | 18 | 2 h |

### Phase 3 — event-triggered (do NOT do early; watch the tripwires)
| Trigger | Actions | Gaps |
|---|---|---|
| First paid plan | Stripe-class processor (SAQ-A), sales-tax nexus review, auto-renew/cancel UX ⚖ | 17 |
| First employer conversation | **FCRA opinion ⚖ before any score reaches an employer**; NYC LL144/employment-agency analysis; bias-audit plan; revisit D-01 surface as the regulated surface | 08 |
| ~10× user growth (repeat each 10×) | State privacy-law threshold re-check; GPC/opt-out mechanics if thresholds near | 16 |
| Any EU/UK marketing intent | GDPR program incl. Art. 22 analysis of the match | 19 |
| First enterprise questionnaire | SOC 2 readiness assessment → Type I → Type II; ISO 42001 evaluation | 20 |

---

## 4. Decision-queue items surfaced by this audit (Sebastian's calls, not implementation details)

1. **D-16 vs deletion rights** — retain de-identified response rows on account deletion, or hard-delete? (Phase 0.3 blocks on this.)
2. **Age floor** — 18+ or 16+? (18+ is simpler; 16+ only if there's a product reason.)
3. **ZenSearch** — pursue permission, replace, or drop? (Phase 1.5.)
4. **Translation feature** — is it load-bearing enough to pay for an official API?
5. **US-residents scope statement** in ToS — confirm the US-only intention as written policy.
6. **Timing** — Phase 0 items 0.3/0.4 are cheapest before the S-07 migration applies; that migration is currently gated on the deploy freeze (S-34). Sequencing those three is a STATE-level call.

---

## 5. Sources for the legal claims relied on above

- CalOPPA privacy-policy requirement (no user threshold): California Bus. & Prof. Code §22575 — [Osano, US data-privacy laws guide](https://www.osano.com/us-data-privacy-laws)
- State privacy-law applicability thresholds: [MultiState 2026 tracker](https://www.multistate.us/insider/2026/2/4/all-of-the-comprehensive-privacy-laws-that-take-effect-in-2026)
- Employment-AI laws attach to employers/agencies (NYC LL144, IL HB 3773, CO SB 205 status): [Seyfarth AI legal roundup](https://www.seyfarth.com/news-insights/artificial-intelligence-legal-roundup-colorado-postpones-implementation-of-ai-law-as-california-finalizes-new-employment-discrimination-regulations-and-illinois-disclosure-law-set-to-take-effect.html), [K&L Gates 2026 AI employment landscape](https://www.klgates.com/thought-leadership/Navigating-the-AI-Employment-Landscape-in-2026-Considerations-and-Best-Practices-for-Employers-2-2-2026)
- ADA web-accessibility litigation exposure and WCAG benchmark: [Accessibility.Works 2026 standards](https://www.accessibility.works/blog/wcag-ada-website-compliance-standards-requirements/)
- FCRA consumer-report scope for algorithmic scores: 15 U.S.C. §1681a(d) (analysis flag — get counsel's opinion at the employer tripwire)
