# Solverah — Session Handoff, 2026-08-13 (second session of the day)

**Topic: shipping posture, seven binding decisions, P-02 finished, three packets corrected, the
collector prompt to v4.6, and a clean-room build environment.**
Custom instruction to honor: be logical and future-thinking, do not be agreeable — push back.

Supersedes nothing. Sits on top of `SOLVERAH_HANDOFF_2026-08-13.md` (v4.4 / P-02 start) and
`SOLVERAH_HANDOFF_2026-08-10.md` (six-dimension critique, four instrument decisions).

> **BEFORE ANYTHING ELSE — RE-SYNC PROJECT KNOWLEDGE.** The doc synced into the project under the
> name `SOLVERAH_HANDOFF_2026-08-13.md` actually contains the **08-07** session (variance tests).
> The real 08-13 handoff exists only in the repo. A session started from project knowledge alone
> will re-litigate settled decisions — it happened at the start of this one. Re-sync, and add this
> file plus `ground_truth/DECISIONS_2026-08-13b.md`.

---

## What changed the direction of this session

Sebastian relayed Julie's instruction: **build it out as well as possible and ship, even at 70–80%
accuracy, rather than loop on corrections for an unknown period trying to perfect something that
probably cannot be corrected without data we can't currently get.**

That reframed everything. Four of the seven decisions below **delete or bound** something. v4.2,
v4.3 and v4.4 each grew the prompt in response to a defect, and the instrument was accumulating
requirements faster than it was accumulating packets.

---

## Seven binding decisions

Full reasoning in `ground_truth/DECISIONS_2026-08-13b.md`. All implemented, not just recorded.

1. **The prompt freezes on the first packet that surfaces zero STRUCTURAL defects.** Structural =
   changes what evidence reaches Section 1, or how a section is scoped. Cosmetic defects are logged
   and do not reset the counter. On freeze, all six packets are rebuilt once and the set closes.
   The bar is deliberately weak — it exists to **terminate the loop**, not to certify anything.

2. **Per-title subratings removed, retroactively, from every packet.** Glassdoor demoted to an
   optional recency cross-check; Indeed is the only required review source.

3. **The achievability gate is now hard rule 9** — any percentage must be reachable at its stated n
   or it is struck. Not reconciled, not footnoted. Struck.

4. **Evaluative metrics barred from Section 1 as dimension evidence — hard rule 8.** Recommendation
   rate, CEO approval, outlook, star ratings, senior-management scores.

5. **Section D voice composition must be recorded**, with one bounded extra rung if D comes back
   all-executive, and stale non-executive material logged as found-and-rejected rather than absent.

6. **The level/role question is CLOSED.** Level does not enter the v1 model; it is captured as an
   ordinal and tested when outcomes exist. *Open item #1 from 08-10 is closed.*

7. **Packets are built in a clean context matching production** — fresh session outside the project,
   nothing else in the window, pinned and recorded model string.

---

## The finding that forced decisions 2, 3 and 4

**Three of the four would-recommend percentages in P-03 are arithmetically impossible at their
stated n** — including the 24% for Junior Trader, which was the sole support for the whole
dispersion/level finding. At n=16 the rate steps by 6.25 points; 24% is not one of them. Trader
(86% at n=32) and Quant Researcher (81% at n=11) fail too. P-04 fails on 53% at n=24. **P-05 also
carried one — 89% at n=29 — which nobody had ever checked.**

Systematic failure across three packets means the rate and the count use different denominators, so
the *difference* between two rates has no defined sample size and cannot be computed at all.

This is the identical defect caught on P-04 on 2026-08-10, which produced the rule. **The rule lived
only in a handoff, so it never propagated to P-03 or P-05.**

> **The lesson that matters more than the rule: a rule that lives only in a handoff is not a rule.**
> Anything that must fire on every packet belongs *in the prompt*. This is why v4.6 now carries a
> defect register (D1–D21) inside it.

### Construct, independent of the arithmetic

"Would recommend" and "senior management" are **evaluative** — how the writer feels. The six
dimensions are **descriptive** — what the environment is like. In the original P-03 table the two
orderings disagreed: Trader ranked third on satisfaction and first on work/life balance. Even sound
numbers of the wrong construct are not evidence.

### Selection, also independent

The Junior Trader bucket is enriched with people who washed out of an up-or-out seat; survivors get
promoted into the Trader bucket. Interns escape this, which is why they break the gradient at 4.0.
Modeling that table as a level effect imports a survivorship artifact as an environment property —
the same class of error as dollars-comp, patent counts and embeddings.

---

## Packet state — every packet moved

| | Before today | Now |
|---|---|---|
| P-01 Oscar Health | folder empty, missing | **still empty.** A partial was built and quarantined — see below |
| P-02 Best Buy | A + C done, B half, D/E/F not started | **all sections complete**, blocked only on Glassdoor |
| P-03 Akuna | numeric layer + dispersion claim | **numeric layer struck, dispersion block withdrawn in place** |
| P-04 R/GA | numeric layer, internally contradictory | **numeric layer struck.** Still internally contradictory |
| P-05 Doist | partial, carried a failing % | **failing figure struck.** Still partial |
| P-06 Raymond James | not started | not started |

**Verbatim review text, dates, titles and URLs are byte-identical before and after the strip on
P-03 and P-04 — verified by diff, not assumed.**

The P-03 dispersion block was **withdrawn in place, not deleted**. It now shows the arithmetic that
killed it, states what survives (the reviewer's own words about desk and team variation; the
high-dispersion reading), and records the level ruling. Anyone reading that packet cold sees the
correction rather than the claim.

### P-02 — what it established

* **Section F works on first use anywhere.** Figure-stripping cost one paragraph (benefits, almost
  entirely numeric) and left training/development/culture prose intact.
* **The EDGAR blocker is solved.** `browse-edgar` is dead at every variant including `&output=atom`;
  `data.sec.gov/submissions` truncates mid-array. Working route: resolve the document URL, then
  fetch `/Archives/edgar/data/<CIK>/<accession>/<doc>.htm` directly. **Confirmed again on P-01.**
* **The Indeed per-title subrating trap is settled** — four titles spanning a 9× range in review
  count return byte-identical company-wide numbers. Now confirmed on a third company.
* **The D4 count contradiction is intermittent**, not systematic — 1 of 4 titles, off by one.
* **Section D came back 100% executive voice.** The newsroom carries exactly the right
  non-executive material and all of it is 2018–2020. Found and rejected on age, not absent.
* **Section F is uniquely hard to anonymize** — identifying content and dimension-bearing content
  are the *same sentences*. Rule that works: rewrite the proper noun, keep the clause.

---

## P-01 broke v4.5 on its first section — SD-1

v4.5 was written this session and **never had a clean-room run. No packet was built under it.**

**Stratifying Section B by job title systematically selects stale evidence.**

| | newest review |
|---|---|
| largest title bucket, Member Services Rep (15 reviews) | **2024-01-24** — zero of 15 inside the 24-month gate |
| same company, company-wide | **2026-04-13** — all of page 1 inside the gate |

The company is not stale. The title filter is. Three mechanisms:

1. **Recent reviews are frequently posted with NO job title** ("Anonymous"). They belong to no
   bucket and are invisible to a title-stratified sample.
2. **Recent reviews use long-tail title strings** the index normalises away — "Insurance Operations
   Claims Processor", "Complex Case Manager", "UM", lower-case variants.
3. **Large buckets are large because they are OLD.** A mass-hiring role from six years ago
   accumulates reviews; roles the company hires for now have not.

A v4.5-conformant Section B would have described Oscar circa 2016–2018. The company-wide stream
describes 2025–2026 — layoffs, remote work, micromanagement, a nurse-scope regulatory concern.

**Why it never appeared before:** P-02 had 39,859 reviews against 85,000 employees, so every bucket
was continuously replenished and the two frames agreed. **The title frame works only when review
volume is high AND the role mix is stable, and it fails silently** — counts agree, buckets look
healthy, only the dates give it away.

Choosing P-01 over P-06 as the freeze candidate was worth it. P-06 was predicted to resemble P-02,
which v4.5 was already hardened against — it would probably have passed and certified nothing.

---

## v4.6 — the current prompt

`ground_truth/rubric/Company_Culture_Evidence_Collector_v4.6.md`

1. **Section B's frame is RECENCY, not job title.** Sample company-wide newest-first; record each
   review's title as metadata; **report** the resulting function mix rather than imposing one. The
   title index is still collected — it is how the P-02 "corporate evidence does not exist" finding
   was made — but it is not the frame. On P-01 the recency frame delivers *broader* function
   coverage than stratification would have.
2. **Untitled reviews are collected** with `title: not stated` (B2a).
3. **Employer responses are tagged `[employer response]`** (B2b), never counted as employee reviews
   or as non-company-authored support. One is present in the P-01 stream, dated 2021.
4. **A DEFECT REGISTER, D1–D21, lives in the prompt**, each with the packet that found it.
5. Shipping posture, freeze rule and build-environment rule at the top.

---

## Clean-room build infrastructure — new, and the reason nothing ships from a working session

`ground_truth/BUILD_BRIEF.md` — what a builder reads. Rule Zero: **one company per session**, then
stop and refuse. Loads the collector prompt itself, saves the packet with a BUILD RECORD stamp,
self-reports defects classified structural/cosmetic, hands back. Handles both filesystem and
no-filesystem modes. **Verified to leak no prior-build findings.**

`ground_truth/RUN_CARD.md` — operator guide. **Not for a builder** — contains the P-01 answer key.

`ground_truth/_build_env/` — isolated folder holding only the brief, the current prompt and an empty
`packets/`. Connect *only this* for structural rather than instructed isolation. **Its failure mode
is a stale prompt copy** — re-copy the newest collector and delete the old one before each round.

`ground_truth/_quarantine_not_ground_truth/P-01_CONTAMINATED_do_not_use_as_ground_truth.txt` — the
P-01 partial built in this session, header-stamped, never to be fed to a builder. Useful afterwards
as an answer key.

**Do not build inside the Solverah IP Planner project.** A new chat inside it inherits custom
instructions, knowledge docs and `memory.md` automatically — worse than a stray paste because it
arrives silently.

**Sebastian's chosen mode for the freeze run:** clean chat, no folder, both files attached (or the
collector prompt pasted directly, which is the closest thing to production).

---

## Honest status

**Zero clean-room packets exist.** P-02 was finished, and P-01 started, inside a session that
already knew every defect from P-03, P-04 and P-05. Both are sound as *evidence* — real, sourced,
dated quotes. Neither is a clean test *of the prompt*, because the builder knew what to look for.

That reads like a step backwards. The alternative was six packets built on an instrument nobody had
tested in the environment it has to run in.

**Distinction worth keeping:** hardening runs may be contextual — knowing the last five defects is
how you find the sixth. But the freeze packet and the final rebuild must be clean-room. **A freeze
certified by a builder who knew in advance what to look for certifies the builder, not the prompt.**

---

## Open / next

1. **Build P-01 clean-room against v4.6.** Freeze candidate. Then classify its defects.
2. **If zero structural → v4.6 freezes**, rebuild all six clean-room, close the set, then onboard
   Rater B. Sebastian says finding a second rater is not a problem; the constraint is **timing** —
   starting one pre-freeze puts their scores on a different instrument, which is what made George's
   unmergeable.
3. **P-02's two Glassdoor items** — per-title subratings are now moot (removed), but the **recency
   cross-check** is still outstanding and it is the check that caught the P-03/P-04 artifact.
4. **P-04 is still internally contradictory** — header says v4.2, Section B carries a v4.3
   correction, and the yield audit still shows a `0/15 FAIL` that the correction withdrew.
5. **P-05 Doist** — first-person library still undated; each candidate must be opened individually.
6. Carried and untouched: re-run the scorer variance test on a stronger model; re-run the blind /
   identified test at n=5 per condition; build the citation-verification harness; bias-test the 24
   assessment items; write `assemble_training_data(db)`.
7. **Julie is unblocked, deliberately.** No permission is being sought on the primary-source split
   or the 0.7 rule. The correction owed on the confidence claim is still worth sending, but it is
   not blocking anything.

---

## Framings that survived pushback this session

* **A rule that lives only in a handoff is not a rule.** Three packets shipped impossible
  percentages because the gate sat in a document nobody re-read. Rules that must fire every time
  belong in the prompt.
* **Uniform absence beats uneven presence.** A missing layer in all six packets is workable; a layer
  present in three and missing in three cannot be merged.
* **Descriptive vs evaluative is a construct distinction, not a reliability one** — and it is the
  stronger objection. Sound numbers of the wrong construct are still not evidence.
* **Evidence availability is the binding constraint, not storage.** Role- and level-conditional
  cells are cheap to store and impossible to populate.
* **The title frame fails silently.** Counts agree, buckets look healthy, and only the dates reveal
  it. Assume any frame can fail this way and look for the tell.
* **A freeze certified by a builder who knew what to look for certifies the builder.**
* **A clean build with an empty defect list is a suspicious result, not a good one.**
* **Folder access is not contamination. Folder *contents* are.**
* Ship at 70–80% and iterate. The remaining error cannot be removed with data that exists today.
