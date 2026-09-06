# S-50 — anonymization ruleset: DECIDED 2026-08-20

Answers from Sebastian's partner (Julie), 2026-08-20. Supersedes the open version of this sheet.
Built by opening `ANONYMIZATION_RULES_DRAFT.md`, `SOURCE_CLASS_RULING.md` and
`ground_truth/anonymization/_STATE.md` rather than working from STATE's summary of them.

---

## S-50 as STATE describes it was ALREADY CLOSED

STATE records S-50 as "three anonymization ruleset decisions awaiting sign-off." **All three were
decided 2026-08-15** in `ANONYMIZATION_RULES_DRAFT.md` under *"Amendments from P-06 — DECIDED"*:

| STATE's S-50 item | Actual status |
|---|---|
| R6 extended to Section D | **A1.** R6 now reads *"strip identifying figures wherever they appear, in any section, replacing them with magnitude language."* |
| JC-1 / R4 collision | **A2.** Where they collide, **R4 wins on the branded token, JC-1 keeps the rest of the sentence.** Test: dimension signal per unit of fingerprint. |
| "a third deviation in P-06's scrub log" | **A3.** Not vague — the R8 question. R8 executes as a **rater-facing recurrence note, not a deletion.** |
| *(absent from STATE)* | **A4.** Every substitution is bracketed **on the excerpt line**, not only in the scrub log. |

**Root cause:** `_STATE.md` (mtime …8772667) was written first; the rules file (mtime …9778962)
was updated ~17 min later carrying the decisions. STATE has been reading the stale one — worsened
by the filename collision STATE itself flagged, a second `_STATE.md` in a subfolder.

**→ Close S-50 as written. The decisions below are the live set.**

---

## Q1 — Is an employee-bylined post on a company-run site "company-authored"?

**ANSWER: YES, company-authored/approved.**

**This CONFIRMS a standing ruling rather than creating one.** `SOURCE_CLASS_RULING.md`
(2026-08-15) already ruled it, with the same reasoning:

> **RULING on `disputed`: it counts as COMPANY-AUTHORED.**
> 1. It closes an evasion hole — otherwise any company manufactures non-company support by
>    starting a blog. *"A measurement that can be satisfied by the thing it is meant to detect is
>    not a measurement."*
> 2. Editorial control means selection; nothing critical survives the choice.
> 3. Consistency — v4.6 already bars employer responses to reviews from counting, same logic.

Already implemented in `build_rater_page.py::classify_source`; a page with an unclassified
excerpt **fails the build** rather than shipping a null.

### CORRECTION — ≤0.7 is NOT a cap, and P-05 does not "cap out"

`_STATE.md` frames this as *"no dimension in P-05 can exceed 0.7 and the packet caps out."*
**That framing is stale and wrong.** `SOURCE_CLASS_RULING.md`:

> **A MEASUREMENT, not an enforced ceiling.** Settled in 08-10 decision 3 and re-corrected in the
> 08-15 handoff: record one score per dimension plus a flag for whether non-company-authored
> evidence supports it. **Enforcing it as a cap was explicitly rejected** — it would compress
> every small private company toward the middle, the shrink-toward-0.5 failure through another
> door.

**Consequences — all benign:**
- **No rater action.** Raters score normally; the flag is computed downstream from `source_mix`,
  which they already record per dimension.
- **Nothing in round 1 is invalidated.** No retroactivity problem, no re-rating.
- **P-05 scores normally**, carrying `noncompany_support: false` on every dimension.

### The honest limit that travels with the ruling (already documented, do not lose)

P-05 has **zero** non-company excerpts — 12 company, 10 disputed, 1 researcher observation; its
Section B holds two employer *responses*, not reviews. Across the six, only the large/public
packets (P-01, P-02, P-04, P-06) can register non-company support at all. So:

> *"'This score has non-company support' will mostly mean 'this company is large or public,' not
> 'this score is well-evidenced.' The flag must be read conditional on which evidence types the
> packet could contain, never as a quality mark."*

**The ruling is deliberately reversible.** `disputed` stays a distinct recorded class in the rater
JSON and is folded into `company` only at analysis time — so once scores exist, check whether
disputed-supported dimensions behave like company-supported ones. If they behave like
non-company-supported ones instead, the ruling is wrong and can be reversed **without re-rating
anybody.** Do not collapse `disputed` at capture time; that throws the test away for no gain.

---

## Q2 — JC-2: does Section E stay?

**ANSWER: KEEP.** Matches the recommendation on file (*"I lean keep, scrubbed hard"*).

**No rework:** P-01 and P-04 both already retain Section E. Write into v4.7.

Rationale preserved for both live instances: **P-01** — layoffs and reorganisation bear directly
on pace and autonomy, several reviews reference exactly that, and Section E corroborates them
*from a non-company-authored source*, which is what the ≤0.7 measurement is for. **P-04** — every
Section B review predates the ownership change, so Section E is the key to reading Section B at all.

**Accepted cost:** both carry non-trivial re-identification risk (P-04's holding-company sale to PE
plus an AI-studio acquisition places it instantly for anyone who reads ad trade press). Per D-09
this is handled by recording recognition as data, not by scrubbing further.

---

## Q3 — JC-3: does the scrubbed packet become the canonical artifact?

**ANSWER: YES.**

The scrubbed file becomes **`P-0X_packet_RATER.txt`** — versioned, and **never edited once a rater
has opened it.** The raw packet becomes a build record.

**Rationale (from the file):** the citation-verification harness only works if humans and the LLM
score **the same bytes.**

**This is the only one of the six with mechanical work attached:**
1. Rename `P-0X_packet_ANON.txt` → `P-0X_packet_RATER.txt`.
2. Update what "the packet" refers to in every other document — including the S-49 build
   instructions for the new companies.
3. Lands naturally with the v4.7 rebuild, which was already going to replace the packet text while
   *"the rater pages regenerate unchanged."*
4. **Do not rename under the 18 rater HTML files already generated for round 1** — they were built
   from the v4.6 anon files and three raters are mid-round against them.

---

## Q4 — Named clients

**ANSWER: do NOT name specific clients.** Substitute a generic descriptor.

**No rework:** P-04 already applied a generic descriptor as a one-off. This ratifies it as a rule.
Write into v4.7 — it will recur on any agency, consultancy or vendor.

---

## Q5 — Third-party tool names

**ANSWER: retain by default; generalise when the combination is identifying.**

**The good outcome: this makes both prior calls correct rather than forcing a rework.**
- **P-03** retained third-party developer tool names → correct, they were non-identifying there.
- **P-05** generalised them → correct, because *"the combination of framework names, platform and
  blog voice narrows it much further."*

The file recorded this as an unresolved inconsistency (*"pick one rule for v4.7"*). It was not an
inconsistency — it was an unstated conditional. Write the conditional into v4.7.

---

## Q6 — JC-4: scope declaration naming the sector

**ANSWER: keep as written.** No change, no rework.

Consistent with the ruleset's own finding that **industry is not scrubbable and should not be
attempted** — *"it does not hold for `industry`, which is inferable from any real packet and is
adjusted for in the model anyway. Stop treating it as a leak."*

---

## Net effect

| | rework of existing packets | v4.7 rule text needed |
|---|---|---|
| Q1 | none — confirms standing ruling | none (already in `SOURCE_CLASS_RULING.md`) |
| Q2 | none | yes |
| Q3 | rename + doc updates | yes |
| Q4 | none | yes |
| Q5 | none | yes |
| Q6 | none | none |

**Five of six require no packet rework.** The v4.7 rebuild absorbs the rule text; Q3's rename
rides the same rebuild.

---

## Still open, tracked nowhere, from the same files

1. **P-02 and P-05's anon files were retyped rather than edited**, silently converting ASCII
   hyphens to em dashes inside quote bodies. **Three quotes will fail citation verification on
   punctuation** unless the harness normalises dashes and smart quotes as well as whitespace.
   A wholesale retype is also the uncontrolled edit to the instrument the ruleset warns against —
   visible only because the 2026-08-15 audit ran.
2. **P-06's source packet contains a quote that does not exist in Section 1** — *"written from
   memory."* Two further Section 4 defects: a review count stated as six where the correct count
   is eight, and an attribution title contradicting the role the reviewer names in their own body
   text. **A fabricated quote in a source packet is exactly what the real-time verification habit
   is meant to catch**, and it got past it once.
