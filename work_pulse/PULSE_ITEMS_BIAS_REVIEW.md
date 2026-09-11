# Pulse check-in items — Bias Review (B-1)

Light-weight review of `work_pulse/pulse_items.py` (five dimension items + the
`experienced` outcome item), in the tradition of `SITUATION_ITEMS_BIAS_REVIEW.md` but
scoped to what a recurring, 60-second instrument actually needs — not a re-run of that
document's nine findings. No pilot data exists; this is what should be fixed *before*
one exists, same caveat as the sibling review.

---

## 1. Leading wording

Every stem was checked against the rater-rubric standard already applied to
`situation_items.py`: does the question itself suggest which answer is the "right" one?

None of the five dimension stems name a villain or a virtue. "How well could you focus
without interruption this week?" does not presuppose interruption happened; "How
sustainable did this week's workload feel?" does not presuppose strain. Compare this
against a rejected draft of the `environmental_friction` item — an earlier phrasing,
**"How much did your environment get in the way this week?"** — which was replaced by
**"How much did your surroundings help you do good work?"** for exactly this reason:
"get in the way" frames friction as the default expectation and a "no friction" answer
as the surprise, which pulls responses toward reporting friction that isn't there. The
shipped wording is symmetric: it can be answered honestly at either end without the
question itself nudging the respondent toward one.

`experienced`'s wording is fixed by BUILD_PLAN B-1 verbatim ("this week, how well is
work working for you?") and was not altered — it is deliberately the one evaluative
item, asked last, the same reasoning `situation_items.EXPERIENCED_ITEM` documents.

## 2. The recognition dimension's social-desirability pull

`recognition_friction` is the item most exposed to this problem, for two reasons that
compound: admitting your work goes unnoticed can read as admitting you aren't good
enough to be noticed (a face-threat that pulls answers upward, toward "noticed"), and
wanting recognition at all carries a mild professional stigma ("good work speaks for
itself") that pulls in the same direction for a different reason.

The mitigation actually taken: the item is worded **behaviourally** — "How much of your
work got real notice this week?" — rather than **emotionally** — a rejected draft read
"How valued did you feel this week?" A behavioural question asks the respondent to
recall an observable fact (did anyone comment on, credit, or act on your work) rather
than to report and simultaneously judge a feeling, which is one fewer layer for social
desirability to act on. **This reduces the pull; it does not remove it.** A respondent
still chooses what counts as "real notice," and a respondent uncomfortable reporting low
recognition can still round up. The pilot should watch for `recognition_friction`
sitting suspiciously close to the scale's ceiling population-wide compared to the other
four dimensions — that pattern is what this residual pull would produce.

## 3. Anti-nag: no item may imply that checking in more often, or reporting a problem,
   is virtuous

This is a direct product-decision constraint (PRODUCT_DECISIONS.md §2, "The Pulse ships
thin": "silence is treated as data rather than as something to chase the user about"),
not a generic bias category, and it was checked explicitly rather than inherited from
the situation-items review, which has no analogue to it (a one-time instrument has no
cadence to moralize about).

Two wording temptations were checked for and avoided:

* **No item's framing rewards a low score.** A stem like "How much has been getting in
  the way lately?" invites a respondent to prove they are paying attention to their own
  wellbeing by finding something to report. Every shipped stem can be answered at its
  best-case anchor with no sense of having under-reported or under-participated.
* **Nothing in the item bank references check-in frequency, streaks, or the act of
  checking in at all.** The five-dimension, round-robin design (`dimensions_for_checkin`)
  and the cadence/anti-nag mechanics belong to B-2, not to this module, and none of that
  logic's existence is hinted at in any stem — a respondent completing a check-in has no
  way to infer from the wording alone whether skipping it would have been noticed or
  minded.

## 4. The 60-second budget is a proxy, stated honestly

`STEM_MAX_LENGTH` (70 characters) and the single-clause rule are the only levers this
module has over completion time — nothing here can measure how long a real respondent
actually takes. Two things push in the instrument's favour that a raw character count
does not capture: only the two scale endpoints are worded (no five-way option list to
read, unlike `situation_items.py`), and a respondent answers at most three dimension
items plus `experienced` per check-in, never all five. Both are structural, not
wording choices, and neither is provable without pilot timing data. If a pilot shows
real completion times exceeding 60 seconds, the fix is almost certainly item *count*
(`ITEMS_PER_CHECKIN`) rather than further wording trims — the stems are already near the
floor a single clause allows.

## 5. Consistent polarity is a deliberate trade, not an oversight

Every item in this bank scores 5 as the good end, unlike `situation_items.py`'s
anchor-order alternation (see `pulse_items.py`'s module docstring for the full
reasoning). The cost: a straight-lining respondent lands every dimension at whatever
value they pick, with no midpoint-forcing property to catch them. The trade was made
anyway because a recurring 60-second check-in that alternated scale direction would ask
a returning user to re-orient on every single visit, which is a worse failure mode for
*this* instrument than the one it accepts — a straight-lined Pulse week reads as
"nothing changed," which is close to true of most weeks, rather than as a confidently
wrong diagnosis. This is the same reasoning `situation_items.py`'s Finding 1 applies in
the opposite direction for a different instrument shape; the two should not be
reconciled into one rule.

---

**Not reviewed here, on purpose:** `pulse_events`' event-type vocabulary and free-text
note are not opinion items and carry no anchor or leading-wording risk in the sense this
review covers — a user names what happened, not how they feel about it.
