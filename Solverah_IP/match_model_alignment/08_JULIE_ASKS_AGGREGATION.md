# Six quick questions: how evidence about a company adds up, and one of your numbers

**Status:** ready to send, 2026-10-14. A separate ask: it is not bundled with the
alignment response (00-06), the compounding-pairs draft or anything else. The email body
is `08_EMAIL_TO_JULIE.txt`.

**For Julie.** Thank you. Your rulings on the anchors are what CompanyLens is built on,
and these six questions are the last pieces we had to guess. Each one stands alone. Answer
one and stop, or skip any of them; whatever you answer is used. Each takes about a minute.
To answer, reply with the question number and a letter (for example "1B, 3A"). Add a word
of reasoning if you like, but you don't have to.

**What questions 1 to 5 are about.** For each company, research collects many separate
pieces of evidence (one review, one job posting, one news story). Each piece is scored on
its own against your anchors. These questions are about how those single scores are
combined into one read per trait: **known**, **mixed** (the evidence disagrees), or
**unknown** (not enough to say). Until you answer, the product runs on our best guess,
which is marked "provisional" in the code.

---

## Question 1. When does disagreement count as "mixed"?

Your ruling 5 said contradiction alone does not make a trait mixed: strength, recency and
amount decide whether one side wins. We need a line. Below, "6 v 2" means six pieces of
evidence point one way and two point the other. "Balanced" pieces sit in the middle.

**What we do today.** Mixed needs at least 2 pieces on the smaller side, and the smaller
side must be at least a quarter of all the pieces. That gives:

| Evidence | Today |
|---|---|
| 6 v 2 | mixed |
| 5 v 2, plus 3 balanced | known (the 5 side wins) |
| 4 v 2 | mixed |
| 3 v 3 | mixed |
| 2 v 2, plus 4 balanced | mixed |

One oddity you may want to rule on: adding balanced pieces can turn "mixed" into
"known" (6 v 2 is mixed, but 5 v 2 with 3 balanced is known).

**Options**
- **A.** Keep today's line.
- **B.** Stricter: mixed only when the smaller side is at least a third (so 6 v 2 becomes
  known; 4 v 2 and 3 v 3 stay mixed).
- **C.** Looser: two or more pieces on each side is always mixed, whatever the totals.
- **D.** Balanced pieces should not count in the totals (judge 5 v 2 + 3 balanced as 5 v 2).
- **E.** Not sure / skip.

*For us:* `MIXED_MIN_SIDE_COUNT` = 2, `MIXED_MIN_SIDE_FRACTION` = 0.25.

---

## Question 2. Should some evidence count more than other evidence?

**What we do today.** Every piece counts the same. The scorer records how clear-cut each
piece is (its confidence), but the total ignores it. Date only matters in two places: a
trait needs at least one independent piece from the last two years to be read at all,
and Question 4.

**Options**
- **A.** Keep it equal: one piece, one vote.
- **B.** Recent pieces (last two years) should count more.
- **C.** Clear, explicit pieces should count more than vague ones.
- **D.** Both B and C.
- **E.** Not sure / skip.

*For us:* `COUNT_CONFIDENCE_BASE`, `COUNT_CONFIDENCE_PER_ITEM`; no weighting in v1.

---

## Question 3. Can a company's own words ever make a trait "known"?

**What we do today.** No. A careers page, a job ad, a press release or a leader's interview
is the company describing itself. A trait is "known" only if at least one piece of
supporting evidence is independent: an employee's review or independent news reporting.
If everything comes from the company, the trait stays "unknown". The one exception is a job
posting the user pastes in, which is read as the company's own description of that one
role and is shown as such.

**Options**
- **A.** Keep it: the company's own words never make a trait known on their own.
- **B.** Allow it, but label it clearly as "the company's own description".
- **C.** Allow it only when several different company sources agree (for example the
  careers page, several job ads and a leader interview all say the same thing).
- **D.** Not sure / skip.

*For us:* `INDEPENDENT_SOURCE_TYPES` = employee reviews and news.

---

## Question 4. If recent evidence points one way and older evidence the other, follow the recent?

Example: reviews from the last two years describe a fast pace; reviews from before that
describe a steady one.

**What we do today.** If at least 3 independent recent pieces agree, we report the trait as
known in the recent direction, with a note that it changed recently. With fewer, we
report it as mixed and still say the split follows time.

**Options**
- **A.** Keep today's rule (follow the recent side once it has 3 independent pieces).
- **B.** Always follow the recent side when the split follows time, however few pieces.
- **C.** Never: show it as mixed, with both sides, and let the user judge.
- **D.** Follow the recent side, but only with more recent evidence than 3 pieces.
- **E.** Not sure / skip.

*For us:* `TIME_SPLIT_KNOWN_MIN_INDEPENDENT_RECENT` = 3.

---

## Question 5. Can one piece of evidence be scored on bands written for a whole company?

Your anchors describe a whole company: the top Pace band, for example, describes urgency
and quick turnarounds as the way the company works. Today we score each review or posting on its own against those same bands, then
average. So one review that reads "Clearly fast" counts as a full "Clearly fast" vote.

**What we do today.** Yes, every piece is scored on the full scale, and nothing is capped.
One very fast review among several middling ones moves the average as far as the
arithmetic says.

**Options**
- **A.** Yes, keep scoring each piece on the full scale.
- **B.** Yes, but one piece on its own should only reach "leans" (not "clearly") unless
  other pieces back it up.
- **C.** No: the bands only make sense for a body of evidence. Score groups of evidence
  together, as the rating packets did.
- **D.** Not sure / skip.

*For us:* no clamp in v1. Option C is what our proposed concordance study would test
(item-by-item scoring compared with whole-packet scores on the rating packets), which needs
a cost go.

---

## Question 6. Is innovation really direction-neutral?

This one is different: it is about one of your own numbers, not about evidence. It stands
alone like the others.

On your priors form you gave **5 in 10** still doing well for both directions on
Innovation: someone who wants to invent, in a role that mostly refines what exists, and
someone who prefers to refine, in a role that mostly invents. Every other trait got two
different numbers. Our sensitivity test found this is one of the few numbers that changes
what people see: if the answers were closer to **6.5 versus 3.5**, about a third of people
would see a different ordering of companies.

**Options**
- **A.** They really are equal: keep 5 and 5.
- **B.** Wanting to invent in a role that mostly refines is the harder one (it should be
  lower than 5).
- **C.** Preferring to refine in a role that mostly invents is the harder one (it should be
  lower than 5).
- **D.** It depends too much on the person to say / not sure / skip.

If you pick B or C and have numbers in mind, add them (for example "B, 4 and 6"). If you
don't, we will propose numbers back to you in one line.

*For us:* `innovation.dir` in `priors.yaml` = 0 (from 5/5);
`07_SENSITIVITY_RESULTS.md` probe +-0.87. Not in `constants.py`: an answer here is a
`priors.yaml` change, made by matching-model with its why and date.

---

**After you answer.** Each answer changes one setting. For questions 1 to 5, the version
stamp on every company read changes with it, so a read made under the old setting is never
mixed up with a new one. Nothing else in your earlier rulings or the anchors changes.

---

## For us (not sent)

- Where each answer lands: `solverah/services/company_research/constants.py`, the line
  marked "PROVISIONAL -- awaiting Julie ask N", then bump `AGGREGATION_VERSION`. That file
  is matching-model's, so its owner makes the change; research-ground-truth relays the answer.
- Question 1 options in rule form. A: `count >= 2 and fraction >= 0.25`. B: fraction >= 1/3.
  C: `count >= 2` alone. D: the fraction's denominator excludes items scored exactly 0.5.
- Question 2 B/C/D need a weighting design (how much more) before code. If she picks one,
  propose numbers back to her as a single follow-up, not a new form.
- Question 6 was added 2026-10-14 from matching-model's sensitivity run (07). Unlike 1-5
  it changes `priors.yaml`, not `constants.py`; per the lane rule an anchor/prior change is a
  pre-registration conversation with matching-model and Sebastian before anything is fitted.
  The blind-rater pairs test the same question independently (fit_pairs contrast K11).
- Question 5 C conflicts with the per-item architecture Sebastian chose on 2026-10-13. If she
  picks it, that is a decision for Sebastian, not a constant change.
