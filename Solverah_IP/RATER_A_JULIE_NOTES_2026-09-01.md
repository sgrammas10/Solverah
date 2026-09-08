# Rater A (Julie) — Round 1 Notes, Pulled and Organized

**Date:** 2026-09-01
**Source:** `ground_truth/rater_app/returned/round1/P-0{1-6}_raterA.json`, all six committed 2026-08-17 through 2026-08-29.
**Why this is a separate document from the S-15 agreement analysis:** Julie's *scores* are the weakest of the three raters' to build on as ground truth — see the reasoning below — but her *notes* are a distinct, valuable signal that has nothing to do with anchor wording. This document pulls that signal out on its own rather than letting it get lost inside a scoring-agreement writeup.

---

## 0. Why her scores specifically are not the thing to build on

Recorded for completeness, since the temptation to treat "the person who took it seriously" as ground truth is natural and worth resisting on the evidence, not just on the D-12(b) authorship rule:

- **Systematically harsher.** Mean band 1.83 vs. Carolynn's 2.31 and George's 2.22 — a full band lower, consistently, not just on a few cells.
- **Doesn't reproduce the one place round 1 shows real agreement.** On the 7 cells where Carolynn and George land on the same band, Julie matches exactly on only 3. On the other 4 she's a full band off, always harsher.
- **Not blind on identity, on half the set.** She recognized or suspected the real company on 3 of 6 packets (detail below) — Carolynn and George recognized zero. Once a rater knows the company, they're scoring what they know, not what's in the packet.
- **Not blind on authorship** (D-12(b), already tracked in STATE) — she wrote `anchors.json`, so her own reading of her own wording doesn't test whether an independent reader finds it ambiguous.

None of this makes her judgment bad — her notes below are sharper and more specific than either blind rater's. It means her numbers aren't a safe substitute for what round 1 was actually designed to produce (independent blind agreement), and averaging toward her or treating her as a tiebreaker would import her severity bias and her outside knowledge into "ground truth."

**One data-quality footnote before anything else:** `duration_seconds` is not a usable effort proxy for her sessions the way it is for Carolynn's and George's. P-03 shows 777,173 seconds (~9 days) — that's a session left open across more than a week (started 08-19, submitted 08-28, with the packet's own scores clustering into two commit bursts four days apart), not continuous engagement. P-06 similarly spans ~23 hours wall-clock. Carolynn and George's sessions were all same-day or overnight. Don't compare raw durations across raters without accounting for this.

---

## 1. Recognition / contamination log

| Packet | Company (per roster) | Recognition | Her words |
|---|---|---|---|
| P-01 | Oscar Health | **suspect** | "Oscar Health - I have recruited from this company" |
| P-02 | Best Buy | **yes** | "Only retail big box tech company... I believe this company is Best Buy. What gave it away for me was the retail, electronics big box and several other statements around CEO (Best Buy was a former client of mine)." |
| P-03 | Akuna Capital | **suspect** | "trading on their own capital - narrowed down but not sure which company." |
| P-04, P-05, P-06 | R/GA, Doist, Raymond James | no | — |

Half the set. Worth cross-referencing against D-09 (blindness is procedural, recognition is recorded as data) and the standing Wayfair recognition note in §5 of STATE — this is now the second and third documented recognition events from her specifically, on top of that one.

---

## 2. Segment / role coverage — the same gap she found independently, twice

She raised this on P-02 (Best Buy) without any prompting from S-51, which already tracks exactly this concern from the researcher side:

- **Autonomy:** "the examples cited here are too narrow in scope and don't cover the corporate side of the business. Job postings cited are mainly field (retail / shipping / delivery / tech support) — we really need to be sure that all are considered when building the LLM"
- **Pace:** "I would like to have seen more reviews from other areas of the business than retail."
- **Feedback:** "The intern experience in the reviews is very different from a permanent employee. Interns don't carry the responsibilities of a typical permanent employee. We will need to ensure that there is a healthy balance of type of employee, positions, departments."

This is the P-02/Best Buy over-representation-of-retail-floor-experience finding that Julie's *review* already surfaced (recorded in STATE as the D-22 caveat) — but here it's showing up independently in her *rater* notes too, on the same packet, from the scoring side rather than the QA side. Two independent passes landing on the same defect is a stronger signal than either alone. S-51's open item 1 (scope-labeling heterogeneous packets) is directly what this argues for.

She raised a milder version of the same thing on P-03/Akuna ("concerned that we may not be capturing enough info for support roles") and P-06 ("does not clarify if this is for all employees, bank employees, etc — need to ensure LLM is trained to look at all types and levels of positions").

---

## 3. Evidence staleness — one general complaint, one specific and checkable defect

**General**, repeated across packets: P-03 ("most employee reviews are old (2019, 2022, 2023)"), P-04 ("one employee review however it is 6 years ago").

**Specific and falsifiable — this one deserves an actual check against the P-04 packet file, not just filing as opinion.** On P-04/R-GA, innovation note:

> "The reviews are hard to rely upon because the company was sold in 2025. **SECOND REVIEW SOURCE HOLDS CURRENT REVIEWS FOR THIS COMPANY THAT ARE NOT QUOTED HERE. Its newest is dated 26 June 2026.** Section B's collection rules restrict verbatim review text to the source used below. Why?"

This is a direct claim that the packet-builder had access to review evidence as recent as June 2026 and didn't use it, instead quoting a review from six years earlier, because of a collection-rule restriction to a single source. If true, this is the same failure class SOLVERAH_HANDOFF_2026-08-10 documented and thought it had fixed with v4.3's stratified, newest-first sampling (the "empty response read as absence" failure, and the Glassdoor-vs-Indeed staleness gap that produced two wrong headline findings). P-04 predates v4.3/v4.6-era fixes in its original build. Worth pulling the actual P-04 packet and checking: does a second, fresher review source exist and go unused? This is one grep away from confirmed or refuted, and it's the kind of thing that should get checked before the packet is trusted further, not filed as a rater's impression.

---

## 4. Missing source classes — the same list, four separate times

She named this explicitly and consistently, unprompted, across P-01, P-03, and P-06:

> Reddit, Substack, GitHub, Wayback Machine (archive.org), layoffs.fyi, WARN notices, Wall Street Oasis, teamblind.com

This is a rater asking for exactly the kind of source diversification that S-57 already worries about from the other direction (can a production scraper afford what the ground-truth builder does) — she's asking the opposite question: even the ground-truth builder's rich, multi-source research is missing entire categories of employee-voice evidence (anonymous/adversarial sources like Blind and Reddit specifically, which is where a lot of unfiltered culture signal actually lives) and public-record signals (WARN notices, layoffs.fyi) that don't require going through the company's own controlled channels at all.

---

## 5. A possible 7th signal, not one of the six dimensions

Two separate notes point at the same idea from different angles — company stability/health as something Solverah users would want visibility into, independent of the culture-fit dimensions:

- P-01 free_note: "It would be good to see warn notices (layoffs) and member decline. (If this is Oscar, they rely heavily on the ACA enrollment)."
- P-02 decision note: "Major exec changes may reflect chaos, instability, etc. I believe this is important for solverah users to have a view of this and **wondering if this is a dimension or not?**"

She's not describing an anchor-wording problem on the `decision` dimension — she's asking whether company stability belongs as its own axis, or as an auxiliary signal alongside the six-dimension fit score, rather than being force-fit into `decision` or `innovation`. This is a product/model-scope question, not a rubric-fix question, and it's worth treating as its own open item rather than trying to resolve it by rewording an anchor.

---

## 6. P-05 / Doist — the sharpest finding in the set, and a live example of a known risk

Three things are tangled together here and worth separating:

**(a) A real contradiction she caught that the packet itself didn't flag.** Pace note: "The job postings contradict each other — one states you never go radio silent, yet the next one says no one is expected to respond to messages immediately." Two company-authored value statements, in the same packet, saying opposite things about responsiveness norms. That's a legitimate packet-quality catch, independent of anything about anonymization or source class.

**(b) A concrete product idea.** She proposed, in her own words, a **"quarantine" mechanism for companies whose own evidence self-contradicts or reads as too-good-to-be-true** — repeated verbatim across all six dimension notes: *"This actually feels like a scam company... At this point, I would not want Solverah to proceed. We need to have some sort of 'Quarantine' for companies that appear to be scams."* This is a trust/safety feature idea that doesn't obviously fall under the existing person-side or company-side model IP — it's closer to a fraud/legitimacy gate sitting in front of the matching pipeline. Worth a line in `IP_ASSET_REGISTER.md` as a candidate feature if you want it tracked as IP; I haven't added it myself since that's a deliberate call, not a side effect of pulling notes.

**(c) A methodological flaw this packet demonstrates live, not just describes.** Look at what she actually did: the same "scam company" sentence, nearly verbatim, is pasted into the note field for all six dimensions, and **every single dimension's confidence sits at 0.1 — the lowest band, on all six.** That means P-05's six scores aren't six independent dimension reads; they're one holistic impression ("this smells wrong") copy-pasted across the rubric. This is exactly the cost the 2026-08-15 design doc accepted deliberately when it built one-impression-per-packet scoring: *"a single overall impression will correlate the six scores, so a wide gap between raters cannot be cleanly attributed to anchor ambiguity rather than to one rater's read of the whole company."* P-05 is the cleanest possible demonstration of that risk landing in real data. **Recommendation: treat Julie's P-05 scores as one low-confidence data point about the packet, not six independent ones**, when this feeds into anything downstream.

---

## 7. Bottom line

The notes are worth building off of. The scores are not — not because she didn't take it seriously (she clearly did, more than the other two), but because "took it seriously" and "was blind" are different properties, and round 1 only got the second one from Carolynn and George. What her engagement bought you is sharper, more specific critique than either blind rater produced (neither Carolynn nor George left a note longer than a sentence on almost anything), landing on real, checkable issues: a segment-coverage gap that independently corroborates S-51, a specific stale-review claim on P-04 worth verifying directly, a source-class gap list, a possible 7th signal for company stability, and one genuinely new product idea (the quarantine gate) plus a live demonstration of the single-impression-correlation risk the scoring design already knew about.

None of this resolves the S-15 finding from the previous analysis — Decision is still the worst-agreeing dimension, B and C are still uncorrelated, and that still needs anchors_v3 attention regardless of what Julie's notes say. This document is additive, not a replacement.
