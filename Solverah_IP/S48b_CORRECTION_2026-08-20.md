# S-48(b) — RETRACTION and corrected answer

2026-08-20, after Sebastian supplied `Ground_Truth_Roster_v2.1_FINAL`.
**This supersedes `S48b_CONFOUNDER_SPREAD_2026-08-20.md` as an answer to "how much stage/comp
spread does the ground-truth set need."** Parts of that document survive and are listed in §3;
the rest is withdrawn.

---

## 1. What I got wrong, and how

**I answered a question about a job the ground-truth set does not do.**

I simulated fitting the causal model's confounder weights (`w_stage`, `w_comp`) from a set of
N ground-truth companies, concluded comp spread was the binding constraint, and produced a
selection spec requiring ≥6 companies off the modal comp value. **The ground-truth set never
estimates those weights.**

`assemble_training_data.py` draws its company universe from outcomes:

```sql
FROM outcome_appeal oa JOIN recommendation r ON r.id = oa.recommendation_id
SELECT person_id, company_id, ... FROM outcome_experienced
```
```python
company_ids = sorted({c["company_id"] for c in candidates})
```

The companies that train `w_stage` and `w_comp` are **whatever companies real users are
recommended and give outcomes for.** Ground-truth membership (`is_ground_truth`) does not
enter it.

**The roster said so, in its own locked reasoning, and I had not read it:**

> "Stage skew accepted for v1... This does not hurt the exercise's two real jobs — rater
> agreement and LLM-extractor validation — because confounders (including stage) are stripped
> from the packets, so the roster's autonomy×stage correlation never reaches the scored
> material. The only thing the skew can't give us is a stage distribution, which we source
> from a separate, broader company sample later."

> "Stage / comp distributions are not derivable from this set (near-constant at 4–5 / 3) —
> sourced from a separate broader sample later, **by design**."

That is correct and it is the answer. The skew is deliberate, reasoned, and harmless to what
the set is for.

**This is the S-10 pattern from the decision queue a second time, and worse.** There, a right
recommendation rested on a wrong description of the artifact. Here the recommendation itself
was wrong. In both cases the fix was one file I had not opened. `check_state.py` cannot catch
either: it verifies claims that CITE an artifact, and "the ground-truth set needs comp spread"
cited nothing.

**It also should have been caught earlier by my own evidence.** The config comment I quoted as
corroboration — *"Replace with real distribution once ~15 companies are scored"* — sits on
`comp`'s **scale** (mean/sd for standardization), which is exactly the "separate broader
sample" the roster describes. I read it as corroborating a 15-20 ground-truth set. It is about
a different sample entirely.

---

## 2. Four factual corrections to STATE, all verified against the roster

| STATE / D-08 says | The roster says |
|---|---|
| **D-08: "P-05 stays in the ground-truth set — the only stage 1–2 company."** | **Doist is stage 3.** There are **zero** stage 1–2 companies in the roster. And Doist is not unique at stage 3 — **R/GA is also stage 3.** D-08's rationale is false on both counts. |
| "~78% stage-5" | **58%** (11 of 19) are stage 5. The 78% figure is real but belongs to **comp = 3** (15 of 19 = 78.9%). STATE fused two different statistics into one phrase. |
| comp skewed to 3 | True, and worse than assumed: comp ∈ {3,4,5} only. **Zero below-market companies.** Fifteen at 3, two at 4 (Twilio, Regeneron), two at 5 (Hudson River, Akuna). |
| "P-04 RGA" read as a reinsurer | **R/GA, the digital/creative agency** — stage 3, ~1,500 people, intuition/collective/invent/gentle. Not RGA Reinsurance. My placeholder had it as stage 5 finance; it is stage 3 "other (agency)". |

My placeholder values were wrong on **5 of 6** companies. The flag on them was warranted.

Actual values for the six already built: Oscar Health (4, 3) · Best Buy (5, 3) ·
Akuna (4, 5) · R/GA (3, 3) · Doist (3, 3) · Raymond James (5, 3).

**D-08 needs re-deciding, not re-wording.** It is a locked decision whose stated reason does
not survive contact with the artifact — the S-35 class exactly. Its *intent* (protect the low
end of the stage range) may still be worth keeping, but "the only stage 1–2 company" is not a
fact, and nothing in the current roster satisfies it.

---

## 3. What survives from the withdrawn analysis — and it matters more than what didn't

**(a) The clustering / overconfidence finding is real and lands on the PRODUCTION model.**
`assemble_training_data` emits one row per (person, company) pair; `stage_size` and `comp` are
company-level constants across those rows; `manager_quality` is declared `measurable: false`,
an admitted company-level unknown. So rows within a company are not independent. Measured:
64× the training rows improved the *reported* SE 8.4× and the *real* uncertainty only 2.2×,
with the overconfidence ratio growing from 1.6× to 6.2×. **The effective N for a confounder
weight is the number of distinct companies in the recommendation set, not the row count.**
This is the third appearance of the same error in this project (the seed/n pooled CI in §5,
per-cell pooling in the S-48 size sim) and it will land again at real training time unless the
fit accounts for company clustering.

**(b) Zero spread produces a confidently wrong coefficient.** With comp constant, the estimate
was perfectly stable (SD 0.000) and the bias equalled the entire true weight. This now applies
to the **served company population**, not the roster: if real recommendations concentrate on
at-market employers, `w_comp` will be unidentified and every seed will agree on the wrong
answer. Worth a guard at training time rather than a discovery afterwards.

**(c) The separate broader sample the roster defers to has never been specified.** The roster
says stage/comp distributions come from it; the config says replace comp's scale once ~15
companies are scored; nothing anywhere says what that sample is, who builds it, or when.
**That is a real untracked gap** — and it is the thing my analysis was accidentally about.
It deserves its own item.

Retracted outright: the ≥6-off-mode comp requirement, "comp is the binding constraint",
the |corr(stage,comp)| ≤ 0.20 rule, and `s48b_set_designer.py`'s premise (R1–R4).

---

## 4. The actual answer: what the remaining 9-14 need

The set's jobs are rater agreement and LLM-extractor validation. What matters is **dimension
pole coverage** — does each pole have enough independent anchors that a scored value at that
pole is trustworthy. That is what the roster's own coverage check (its §"Coverage check") is
for, and it is where the six are genuinely thin.

**Pole coverage of the six already built:**

| pole | in the six | n | |
|---|---|---|---|
| autonomy low | Best Buy | 1 | **single anchor** |
| autonomy high | Doist, Akuna | 2 | |
| pace steady | Doist | 1 | **single anchor** |
| pace fast | Akuna, Oscar | 2 | |
| collaboration solo/async | Doist | 1 | **single anchor** |
| collaboration collective | Best Buy, R/GA | 2 | |
| feedback gentle | R/GA, Best Buy, Doist | 3 | |
| feedback blunt | Akuna | 1 | **single anchor** |
| innovation optimize | Best Buy | 1 | **single anchor** |
| innovation invent | R/GA, Oscar | 2 | |
| decision intuition | Raymond James, R/GA | 2 | |
| decision data | Akuna, Oscar | 2 | |

**Five of twelve poles rest on one company, and two companies carry two poles each:**

- **Best Buy** — autonomy low, innovation optimize
- **Doist** — pace steady, collaboration solo/async
- **Akuna** — feedback blunt

**This is a concentration risk the roster already half-anticipated.** Its known limits flag
blunt feedback as resting on two same-archetype anchors and solo collaboration on two
remote-tech anchors — at 19. **In the six, both are down to one.** And `_STATE.md` separately
records **Doist as the weakest scrub** of the six: if that packet has to be rebuilt or dropped,
two poles go with it.

**Priority order for the remaining slots, from this table:**

1. **A second blunt-feedback anchor that is not a prop shop.** Hudson River Trading is the
   roster's other blunt anchor but is the same archetype, so it does not diversify — the
   roster's own note says to watch for a natural non-finance blunt read, naming **Wayfair** and
   **Cummins** as candidates. Both are already on the roster. Highest-value single addition.
2. **A second solo/async collaboration anchor.** Roster's only other one is **DigitalOcean**,
   also remote-tech — thin, and the roster says so. A non-remote-tech solo anchor would be worth
   more than a second remote one.
3. **Second anchors for autonomy-low, pace-steady, innovation-optimize.** Cheap: the roster's
   incumbents (Fifth Third, Hartford, HCA, Centene, Duke, Cummins) supply all three at once, and
   several of them serve two or three poles each.
4. **Break the Doist and Best Buy double-duty.** Whatever else is chosen, no pole should be left
   depending on a company whose packet is already flagged as the weakest.

**Stage and comp spread are not selection criteria for this set.** They are researcher-recorded
on the roster, stripped from packets, and never reach the scored material — per the roster's own
locked decision. Choose on pole coverage and on archetype diversity within a pole.

---

## 5. What I would still check before acting

- **Is P-04 R/GA or a reinsurer?** STATE writes `P-04_rga`; the roster's #18 is R/GA the agency
  and there is no reinsurer on it. The packet directory name should settle it in seconds, and
  it changes that row's pole assignments (agency = intuition/collective/invent/gentle).
- **The pole assignments above are the roster's *expected* leans**, written before scoring.
  Round 1's returned JSONs are the first real measurement of where these companies actually sit.
  If a company lands off its expected pole, this coverage table changes — so treat it as a
  selection heuristic now and re-derive it once the JSONs are in.
