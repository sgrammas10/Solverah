# Source classification and the ≤0.7 measurement — ruling and caveats

Decided 2026-08-15. Closes open question 5 from `SOLVERAH_HANDOFF_2026-08-15.md`.
Implemented in `build_rater_page.py::classify_source`. Read with `ANONYMIZATION_RULES_DRAFT.md`.

---

## What the ≤0.7 rule actually is

**A MEASUREMENT, not an enforced ceiling.** Settled in 08-10 decision 3 and re-corrected in the
08-15 handoff: record one score per dimension plus a flag for whether non-company-authored
evidence supports it. Enforcing it as a cap was explicitly rejected — it would compress every
small private company toward the middle, which is the shrink-toward-0.5 failure through another
door.

Everything below is about making that flag *recorded* rather than *inferred*.

---

## The four source classes

Every excerpt in every rater page is tagged at build time. A page containing an unclassified
excerpt **fails the build** rather than shipping a null.

| class | what it is | counts as non-company support? |
|---|---|---|
| `company` | careers copy, code of conduct, job postings, 10-K Item 1, employer responses to reviews, executives speaking in any venue | no |
| `noncompany` | employee reviews, independent trade or business press | **yes** |
| `disputed` | employee-bylined writing on a company-run outlet — engineering blogs, newsrooms, culture magazines | **no** — see ruling |
| `researcher` | the builder recording dated absence as evidence (P-05 section C) | never, in either direction |

---

## RULING on `disputed`: it counts as COMPANY-AUTHORED

**Reasoning, in order of strength:**

1. **It closes an evasion hole.** If employee bylines on a company-run site counted as
   independent support, any company could manufacture non-company support across all six
   dimensions by starting a blog. A measurement that can be satisfied by the thing it is meant
   to detect is not a measurement.
2. **Editorial control means selection.** The company chooses what appears. Nothing critical
   survives the choice, so the material cannot function as corroboration of the company's own
   claims — which is precisely what the triangulation principle requires of a second source.
3. **Consistency with a decision already in the instrument.** v4.6 tags employer responses to
   reviews as `[employer response]` and bars them from counting as non-company support, for the
   same editorial-control reason. Same logic, same answer.

**The qualification that must travel with the ruling:**

The filter is on **valence, not on descriptive content**, and the six dimensions are descriptive
rather than evaluative (08-13b, construct distinction). A company suppresses "management here is
terrible." It does not suppress "we work asynchronously and I go days without a synchronous
meeting" — it publishes that proudly, and that sentence is real evidence on collaboration and
pace. So this material is not worthless and should not be discarded from packets. It is
**topic-selected**: they publish the async post, not the nine-meetings-today post. The right
reason to call it company-authored is selection over *which true things get told*, not falsity.

---

## CONSEQUENCE, accepted knowingly: the flag is partly a size proxy

Under this ruling, across the six ground-truth packets:

```
P-01  A:CCCCCCCC B:NNNNNNNNNNNNNNN C:CCCCCCCCCC D:DDD    E:NNN  F:CCCCCC
P-02  A:CCCCCCCC B:NNNNNNNNNNNNNNN C:CCCCCCCCCC D:DDDDC  E:NNNN F:CCCCCC
P-03  A:CCCCCCCC B:NNNNNNNNNNNNNNN C:CCCCCCCCCCCCCC
P-04  A:CCCCCCCC B:NNNNNNNNNNNNNNN C:CCCCCCCCCCCCCCCC    D:NNN  E:NNN
P-05  A:CCCCCCCC B:CC              C:R          D:DDDDDDDDDDCC
P-06  A:CCCCCCCC B:NNNNNNNNNNNNNNN C:CCCCCCCCCC D:NNDD   E:NNN  F:CCCCCC

C = company   N = non-company   D = disputed   R = researcher observation
```

**P-05 has ZERO non-company-authored excerpts.** Twelve company, ten disputed, one researcher
observation. Its section B holds two employer *responses*, not reviews. It therefore cannot
register non-company support on any dimension, at all. P-03 has no D, E or F section to draw on.

The four packets that *can* register support — P-01, P-02, P-04, P-06 — are the large or public
ones, because those are the companies with fifteen reviews and trade-press coverage.

**So "this score has non-company support" will mostly mean "this company is large or public,"
not "this score is well-evidenced."** That is the same range-restriction shape already documented
against layer count in the 08-07 handoff: evidence availability tracks company type. The flag must
be read conditional on which evidence types the packet could contain, never as a quality mark.
Reading it unconditionally would import company size into dimension scoring through a side door —
the same failure as dollars-comp, patent counts and embeddings.

---

## IMPLEMENTATION: rule at analysis time, record at capture time

`disputed` stays a **distinct recorded class** in the rater JSON. It is not collapsed into
`company` when the file is written. Each dimension carries:

```json
"source_mix": {"company": 2, "noncompany": 0, "disputed": 1, "researcher": 0},
"noncompany_support": false,
"excerpts_cited": ["A3", "D1", "F2"]
```

Fold `disputed` into `company` when computing the flag downstream. Costs nothing, and it keeps
the ruling **testable**: once scores exist, check whether disputed-supported dimensions behave
like company-supported ones. If they do, the reasoning above is validated rather than assumed. If
they behave like non-company-supported ones instead, the ruling is wrong and can be reversed
without re-rating anybody. Baking the ruling into capture would throw that away for no gain.
