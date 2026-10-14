# Solverah | Product & Match Model Alignment (Julie, October 2026)

**What this file is.** A condensed transcription of Julie's working-draft brief,
"Solverah | Product & Match Model Alignment: Developer discussion brief and methodology
handoff, October 2026". The original is a PDF she shared in chat; it is not in the repo.
This is a faithful condensation, not her full text. Where wording matters, the PDF wins.

Sebastian's answers are recorded in `docs/PRODUCT_DECISIONS.md` §2, "The six-trait match
model" (2026-10-13). The response documents in this folder (00 to 06) answer the brief.

---

## 1. Core promise and loop

"Understand what's really going on in your career, and make a better decision about what
comes next."

Core loop: **ARRIVE, UNDERSTAND, CLARIFY, GUIDE, CONTINUE.** Matching is one capability.
It must not define or limit what Solverah can understand.

## 2. What Understanding™ must do

- Distinguish what is **known** (evidenced), what Solverah **thinks may be true**
  (tentative), and what it is **curious about** (open).
- Never express more confidence than the evidence supports.
- Distinguish stated preferences from underlying needs, non-negotiables, tolerances and
  changing circumstances.
- Let new evidence strengthen, weaken or revise an interpretation without overwriting
  earlier context.
- Challenge the story, not the person.
- Ask follow-up questions that distinguish between explanations.
- Know when to deepen and when to let an insight settle.

## 3. What Guidance™ must do

Give the strongest guidance that current understanding and evidence can responsibly
support. No more, no less. Next-step categories: **Decide, Investigate, Prepare, Explore,
Act, Don't Act Yet.** Guidance informs; it does not decide.

## 4. Conceptual architecture (conceptual, not a software design)

- **Reflection Engine / Authentic Intelligence™**: explores the person's experience
  through conversation.
- **Understanding™**: the evolving interpretation of the person.
- **CompanyLens™**: a grounded organisational picture built from source evidence, with
  its limits and confidence shown.
- **Match logic**: the person-environment relationship, including gaps and
  uncertainties.
- **Guidance / Next Best Step.**

## 5. On the developer's deck

The deck described: six traits scored 0 to 1; 24 forced-choice person items; AI-researched
company evidence scored on a rubric; expert-set gap penalties; an S-curve giving a
probability of "doing well" at one year.

**Retain:** endpoints are positions, not judgments; gathering and scoring are separate;
scores are backed by quotations and confidence; the person-side consistency check; the
plan to learn from outcomes.

**Questions:**
1. What is the outcome, and how is it defined?
2. Probability calibration. Is "perfect match = 80%" meaningful? An S-curve bounds the
   numbers; it does not validate them.
3. Six-trait coverage. What about values, trust, influence, management, sustainability?
4. Can four forced-choice items per trait separate enduring preference from tolerance,
   constraint or context?
5. Company-wide versus role, manager, team or location.
6. How are unknown and mixed evidence handled without a misleading midpoint?
7. What assumptions sit in the expert weights, and what would change them?
8. Before validation, should Solverah show a calibrated explanation plus uncertainty
   instead of a "chance"?

## 6. Recommended sequence

Scope, then outcomes and the data that would validate them, then the interfaces between
components, then what continues unchanged versus what needs validation. Only then
weighting and probability language.

## 7. Requested deliverables

1. A one-page architecture map of evidence, uncertainty, interpretation, match signals
   and guidance.
2. A written definition of each proposed outcome, including how it is observed and
   measured.
3. A boundary statement for the six traits.
4. A validation roadmap separating expert hypotheses, internal tests, and real-world
   predictive evidence.
5. Two or three fictional user journeys, including a case where strong performance does
   not imply sustainable fit.

**Working position:** keep the six-trait work moving as a candidate component. Withhold
approval of probability claims until outcome and calibration evidence exist.
