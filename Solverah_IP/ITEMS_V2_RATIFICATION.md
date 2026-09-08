# assessment_items_v2 — Ratification Sheet

Companion to `assessment_items_v2_PROPOSED.yaml`. Mark each line `RATIFY` / `REDLINE: <what>`.
Nothing here is applied. `status: proposed` stays until every line below is marked.

---

## 0. What the funnel answer settles (§6 / open item 1a — CLOSED)

**Answer: signed-up user, self-profiling after account creation.** No employer present at fill
time. Paywall placement undecided and does not affect item design.

**What that closes.** The rung-4 frustration framing survives. There is no employer reading
"the managers you've found hardest to work for" while deciding whether to hire the respondent,
so the compression risk §6 was worried about — rung 4 systematically under-endorsed across all
six dimensions — does not fire. All six reverse-keyed items are safe on *that* ground.

**What it opens instead, and this is not smaller.** Self-profiling replaces one gaming incentive
with a different one. The candidate-mid-application user softens; the self-profiling user
*aspires*. They answer as the person who gets matched to the job they want, not the person they
are. That is precisely the threat design rule 3 was written against — "someone who wants to look
decisive endorses further down the list" — so the shuffle stops being a nice-to-have.

> **Consequence for the roadmap:** open item 2 (implement the presentation shuffle in the form
> renderer) moves from "ready to build once item text is stable" to **launch-blocking**. Right
> now rule 3 is declared in the YAML and enforced *against* the YAML by a gate that nothing
> consumes. If the form renderer ships without it, the ladder is displayed in difficulty order,
> a self-presenting respondent walks straight down it, and the internal-consistency confidence
> measure returns HIGH on the fabrication. Shipping items without the shuffle is worse than
> shipping v1, because v1 had no gradient to climb.

**Second axis still unanswered, and it is not the paywall question.** Whether the employer ever
sees an individual's six dimension scores is a *disclosure* decision, not a pricing one. If the
answer is "match result only," say so on the form itself — a stated no-disclosure line is the
cheapest single intervention available for honest responding, and it costs one sentence. If the
answer is "employer sees the scores," the aspirational-answering pressure above roughly doubles
and rung 4 needs re-examining after all. **Decide this; don't defer it into product.**

---

## 1. Cross-cutting decisions — these change item TEXT, so they come before the 24

### D1 — Four of six rung-4 items are unanswerable by users with no job history ★ NEW

The funnel answer created this. A signed-up user self-profiling on a *career* platform is
disproportionately a student, new grad, or career-changer. Rung 4 — the hardest rung, the one
that alone separates band 0.7 from band 0.9 — requires an employment history in four dimensions:

| item | premise | requires job history? |
|---|---|---|
| `au4v2` | "Jobs have frustrated you most when:" | **yes** |
| `pa4v2` | "the jobs that wore you down" | **yes** |
| `co4v2` | "roles that drained you" | **yes** |
| `fb4v2` | "The managers you've found hardest to work for" | **yes** |
| `in4v2` | "the situations that frustrated you most" | no — reads fine for coursework |
| `de4v2` | "teams you've been on" | no — reads fine for coursework |

A user with no prior job cannot honestly endorse *or* decline these. Whatever they do is noise
on the single most load-bearing rung, and it is noise concentrated in the segment that most needs
matching. Note the failure is asymmetric: an inapplicable rung-4 most likely gets declined, which
caps that user at 0.75 → band 0.7. The instrument would report that early-career users are
systematically more moderate than experienced ones on four of six dimensions. That is a
measurement artifact that would read as a finding about people.

`in4v2` and `de4v2` already show the fix: frame the retrospective around *situations* and *teams*
rather than *jobs*, *roles* and *managers*. Costs four sentences.

**Options:** (a) reword au4/pa4/co4/fb4 to situation-framing — cheap, and re-runs one probe file;
(b) accept and add an employment-history gate to the funnel, restricting the product's addressable
user; (c) accept and carry as a known artifact into pilot.

**Decision:** ______

---

### D2 — Option-length imbalance runs the same direction as the bias it was supposed to fix ★ NEW

The gate checks per-item length ratio ≤ 2.0. It does not check whether, *within a dimension*, the
longer option systematically sits on one pole. Longer options draw the eye and read as more
considered. Computed over the file (high-pole chars minus low-pole chars):

| dimension | per item | mean | items where high pole is longer |
|---|---|---|---|
| autonomy | −15, −39, +21, −1 | **−8.5** | 1 / 4 |
| pace | −10, +16, −22, +7 | −2.2 | 2 / 4 |
| collaboration | −20, +10, −4, −9 | −5.8 | 1 / 4 |
| feedback | +19, −27, 0, +8 | 0.0 | 2 / 4 |
| innovation | +10, −4, +5, +25 | +9.0 | 3 / 4 |
| **decision** | **+36**, +18, −8, +15 | **+15.2** | **3 / 4** |

**Decision is the finding.** Bias review finding 2 was that decision skewed to the data pole on
every item. The rewrite fixed that semantically — both poles are now a kind of evidence, and the
argument in the YAML header is sound. But the data pole is still the longer, more elaborated
option in three of four items, by an average of 15 characters, and by 36 on `de1v2`. The exact
defect the rewrite was written to close is still present, one channel down, in the layer nobody
checked. Autonomy leans the other way (−8.5), driven by `au2v2`'s −39.

This is the same shape as §3 and §4 of the 8/18 handoff: structural, invisible to a careful read
of the item text, caught only by computing over the file. Which is the argument for adding it to
`check_assessment_items.py` as a per-dimension balance rule (warn at |mean| > 10 chars, or
require ≥1 and ≤3 of the four items to have the longer option on the high pole) rather than
fixing these six by hand and rediscovering it in v3.

**Options:** (a) rebalance decision + autonomy text and add the per-dimension gate rule;
(b) add the gate rule only, carry the current imbalance as measured and known; (c) no action.

**Decision:** ______

---

### D3 — The feedback ladder grades two different variables, and that breaks Guttman

Declared grading variable: "exposure — privacy and delay." That is two variables, and the ladder
switches between them mid-climb:

| rung | graded by |
|---|---|
| `fb1v2` 0.3 | **delay** — next 1:1 vs. as soon as noticed |
| `fb2v2` 0.5 | **delay** — after they've looked properly vs. straight away |
| `fb3v2` 0.7 | **audience** — privately after vs. in the room |
| `fb4v2` 0.9 | both |

Guttman prefix-endorsement assumes one ordered dimension. "Tell me immediately, but not in front
of the team" is a common and entirely coherent preference — and it endorses rungs 1 and 2 while
declining rung 3. Under `mean_pole` that scores 0.5. Under the confidence measure it reads as an
*inconsistency*, i.e. low confidence, on a respondent who answered honestly and coherently.

The other five dimensions are single-variable and monotone; I checked each. Feedback is the only
one that switches. Either drop audience and grade fb3 by delay too (loses the most distinctive
item in the set), or drop delay and grade fb1/fb2 by audience, or accept that feedback will
produce structured Guttman violations in pilot and instrument for it deliberately.

**Recommendation:** the third. Keep it, and pre-register the prediction that feedback shows an
excess of the {1,2,¬3,¬4} pattern. If it appears, that is a real finding about a two-factor
feedback construct and worth more than a clean ladder. If it doesn't, the worry was unfounded.
Either way you learn something. But **decide it now**, because "we'll see in pilot" without a
pre-registered prediction is how a real signal gets read as measurement error.

**Decision:** ______

---

### D4 — The autonomy stakes ladder has a gap at rung 3

Grading variable is stakes/scope. The rungs read: routine task → low-risk project → *tight
deadline, no set process* → high-stakes. Rung 3 is not a step up in **stakes**; it is a step up
in **ambiguity**. The ladder's declared variable does not actually order rungs 2 and 3.

This is the same item the handoff already carries as the `au3v2` dimension leak (open item 16),
but the leak is worse than "watch it in pilot": if rung 3 grades a different variable than rungs
1, 2 and 4, autonomy's Guttman ordering is not guaranteed even in principle, and autonomy is the
one ladder with a probe behind it — meaning the POC's clean 5/5 PASS was demonstrating internal
coherence of a ladder whose middle rung is off-axis. The probe cannot detect this; it validates
against the same annotation that encodes the error.

Carrying it deliberately is defensible. Carrying it while treating the autonomy POC as the
evidence that the ladder design works is not.

**Decision:** ______

---

## 2. The 24 items

Verified mechanically and correct, no action: **key balance is exactly 2 A-high / 2 B-high in all
six dimensions**; four items per dimension throughout; strictly increasing 0.3/0.5/0.7/0.9;
exactly one reverse-keyed item per dimension and it is always rung 4; six distinct grading
variables.

Flags below are item-level only — cross-cutting issues live in §1 and are not repeated per item.

### AUTONOMY — grading: stakes / scope

| # | id | rung | flag |
|---|---|---|---|
| 1 | `au1v2` | 0.3 | clean |
| 2 | `au2v2` | 0.5 | **length ratio 2.00, worst in set, longer option is the LOW pole** (D2). Trimming option A to "Get your approach reviewed first, even though the risk is low." → 1.33 and costs one probe re-run |
| 3 | `au3v2` | 0.7 | **off-axis rung** (D4) + carried dimension leak; tell in pilot is correlating with decision rather than autonomy |
| 4 | `au4v2` | 0.9 | requires job history (D1); otherwise clean, poles balanced at 157/156 chars |

1. `au1v2` — **RATIFY / REDLINE:** ______
2. `au2v2` — **RATIFY / REDLINE:** ______
3. `au3v2` — **RATIFY / REDLINE:** ______
4. `au4v2` — **RATIFY / REDLINE:** ______

### PACE — grading: duration sustained

| # | id | rung | flag |
|---|---|---|---|
| 5 | `pa1v2` | 0.3 | clean. Duration ladder (afternoon → week → months → career) is the cleanest monotone climb in the file |
| 6 | `pa2v2` | 0.5 | clean; quality language successfully gone |
| 7 | `pa3v2` | 0.7 | **construct slip:** high pole is "settled into it and stopped noticing" — that is *habituation*, not *preference*. A slow-pace person who adapted endorses it truthfully. Suggest "Have found you work better at that tempo than the old one" or similar preference framing |
| 8 | `pa4v2` | 0.9 | requires job history (D1). Both poles are real frustrations — best-constructed reverse-key in the set |

5. `pa1v2` — **RATIFY / REDLINE:** ______
6. `pa2v2` — **RATIFY / REDLINE:** ______
7. `pa3v2` — **RATIFY / REDLINE:** ______
8. `pa4v2` — **RATIFY / REDLINE:** ______

### COLLABORATION — grading: coordination cost

| # | id | rung | flag |
|---|---|---|---|
| 9 | `co1v2` | 0.3 | **grades a different variable:** rung 1 is *help-seeking when stuck*; rungs 2–4 are *coordination cost*. A collective-preferring person can still sit with a problem; a solo person can ask fast to save time. Suggest reframing to a small recurring coordination cost rather than a stuck-moment |
| 10 | `co2v2` | 0.5 | clean |
| 11 | `co3v2` | 0.7 | clean; shortest options in the file, no length lean |
| 12 | `co4v2` | 0.9 | requires job history (D1); keying is correct (A = high pole = isolation frustrates the collective type) |

9. `co1v2` — **RATIFY / REDLINE:** ______
10. `co2v2` — **RATIFY / REDLINE:** ______
11. `co3v2` — **RATIFY / REDLINE:** ______
12. `co4v2` — **RATIFY / REDLINE:** ______

### FEEDBACK — grading: exposure

| # | id | rung | flag |
|---|---|---|---|
| 13 | `fb1v2` | 0.3 | grades delay only (D3) |
| 14 | `fb2v2` | 0.5 | grades delay only (D3). Minor: low pole says "can give you the whole picture at once" — completeness is a mild virtue term, the one surviving instance of the valence problem finding 3 was written to remove |
| 15 | `fb3v2` | 0.7 | grades audience (D3). Best-balanced item in the file at 68/68 chars |
| 16 | `fb4v2` | 0.9 | requires job history (D1) |

13. `fb1v2` — **RATIFY / REDLINE:** ______
14. `fb2v2` — **RATIFY / REDLINE:** ______
15. `fb3v2` — **RATIFY / REDLINE:** ______
16. `fb4v2` — **RATIFY / REDLINE:** ______

### INNOVATION — grading: sunk investment

| # | id | rung | flag |
|---|---|---|---|
| 17 | `in1v2` | 0.3 | clean |
| 18 | `in2v2` | 0.5 | clean |
| 19 | `in3v2` | 0.7 | minor: "Push to try the new approach **anyway**" — "anyway" carries a faint charge of stubbornness on the high pole, the residue of the prestige skew inverted. Drop the word |
| 20 | `in4v2` | 0.9 | **job-history-safe already** — "situations," not "jobs." This is the template for D1's fix. High pole +25 chars (D2) |

17. `in1v2` — **RATIFY / REDLINE:** ______
18. `in2v2` — **RATIFY / REDLINE:** ______
19. `in3v2` — **RATIFY / REDLINE:** ______
20. `in4v2` — **RATIFY / REDLINE:** ______

### DECISION — grading: novelty

The rewrite's core argument holds: both poles are a genuine kind of evidence, the novelty axis is
correctly ordered (as situations get more unprecedented, pattern-recognition gets objectively
weaker, so insisting on measurement is progressively more distinctive), and rejecting the bias
review's speed/sufficiency suggestion was right — that axis is stakes wearing a different hat, and
sharing it with autonomy would have manufactured exactly the correlation design rule 1 exists to
prevent. **The semantics are sound. The length channel is not** — see D2.

| # | id | rung | flag |
|---|---|---|---|
| 21 | `de1v2` | 0.3 | **+36 chars on the high (data) pole, the largest imbalance in the file** (D2). Low pole is 57 chars and reads terse next to it |
| 22 | `de2v2` | 0.5 | +18 chars high (D2) |
| 23 | `de3v2` | 0.7 | **internal contradiction:** the premise is "genuinely new — nobody on the team has faced it," but the low pole is "reason it out from what you know about how situations like this tend to behave." The item asserts there are no situations like this, then offers relying on situations like this. Rewrite the low pole toward reasoning from first principles / structural analogy rather than prior instances |
| 24 | `de4v2` | 0.9 | **job-history-safe** — "teams you've been on" works for coursework. +15 chars high (D2) |

21. `de1v2` — **RATIFY / REDLINE:** ______
22. `de2v2` — **RATIFY / REDLINE:** ______
23. `de3v2` — **RATIFY / REDLINE:** ______
24. `de4v2` — **RATIFY / REDLINE:** ______

---

## 3. Summary — what actually needs your decision

Sixteen of 24 items are clean at the item level and I would ratify them as written. The work is
in eight items and four cross-cutting calls:

| | items touched | cost if fixed now | cost if fixed later |
|---|---|---|---|
| **D1** job history on rung 4 | au4, pa4, co4, fb4 | 4 sentences + 1 probe re-run | discovered in pilot as a fake finding about early-career moderation |
| **D2** length balance | de1, de2, de4, au2 + gate rule | 4 edits + ~20 lines of gate | rediscovered in v3 |
| **D3** feedback two-axis | structural, fb1–fb4 | one pre-registered prediction | a real two-factor result read as noise |
| **D4** autonomy rung 3 off-axis | au3 | probe re-run, or explicit carry | the POC's 5/5 PASS keeps being cited as evidence the design works |
| item-level | pa3, co1, in3, de3, fb2 | wording | pilot noise |

**Everything except D3 is cheap now and expensive after the probe vignettes are written**, because
the probe files encode item wording. That is the same argument §6 made about ratifying before
building vignettes, one level in: ratify the *wording* before you spend five ladders' worth of
API calls encoding it.

**Order I'd suggest:** answer D1–D4 → apply the resulting text edits → re-run
`check_assessment_items.py` → then walk the 24 individually, which will go fast because most of
the disagreement will already be resolved.

---

## 4. One thing NOT on this sheet that outranks it

Open item 20 — five sessions carrying it. Two lawyers and Julie are holding packets described to
them as anonymized, and anonymization does not prevent re-identification for 5 of 6 companies.
The cheap version is not fixing the anonymization; it is one email correcting what the raters were
told. It has now outlasted two complete redesigns of other parts of this system, and unlike
everything above it involves other people's reliance on a claim that is not currently true.

Related: open item 12, notify George / RATER_B — five minutes, blocks items 13 and 14, and was
raised four times on 8/18 alone without action.
