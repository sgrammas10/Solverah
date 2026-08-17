# Assessment Items — Bias Review (v1-draft)

Reviewed `assessment_items.yaml` against its own stated failure mode (header comment, gate 2):
*"neither pole is the right one... a lean means the item smuggled in a socially-desirable
answer."* No pilot data exists yet, so this is a structural read, not an empirical one — real
bias-testing still requires running this on people and checking for skew. This is what should be
fixed *before* that pilot, so the pilot measures the items rather than re-discovering these.

Two kinds of problem, kept separate below: **desirability skew** (one option reads as the more
professionally-correct answer, regardless of the respondent's true disposition) and **structural
gaps** (the anti-straight-lining design isn't actually applied evenly).

---

## Finding 1 — two of six dimensions have zero reverse-keyed items

The header promises reverse-keying to break acquiescence/straight-lining, and 4 of 24 items are
tagged `# reverse-keyed`: `au4`, `pa4`, `co4`, `in4` — exactly one per dimension, for autonomy,
pace, collaboration, and innovation.

**Feedback and decision have none.** All four items in each of those two dimensions use the same
"which do you prefer" framing. A respondent who straight-lines (always picks the first-listed
option, or always picks whichever pole they think is expected) produces no internal contradiction
on feedback or decision the way they would on the other four dimensions — which directly weakens
the planned confidence measure (*"internal consistency of the items"*) specifically on these two,
and only these two.

**Fix:** write one reverse-keyed item each for feedback and decision, same pattern as the existing
four — a dissatisfaction/frustration framing rather than a preference framing. Draft:

* Feedback (reverse-keyed): *"You've found it hardest to work for managers who..."* — high pole:
  *"never told you where you stood until a formal review."* low pole: *"picked apart small things
  constantly, in front of the team."*
* Decision (reverse-keyed): *"You've been most frustrated on teams where..."* — high pole:
  *"decisions got made on gut feel with no way to check the reasoning."* low pole: *"every call got
  stalled waiting for a perfect dataset that never came."*

---

## Finding 2 — decision dimension skews toward the high (data) pole on every item, not just one

This is the dimension-wide problem, not a single-item one. Look at all four low/high pairs:

| Item | Low-pole option | High-pole option |
|---|---|---|
| de1 | "go with your read of the situation" | "hold until you can pull the numbers" |
| de2 | "judgment and experience" | "evidence and analysis" |
| de3 | "My gut says this is the move" | "Let's look at what the data shows" |
| de4 | "a compelling rationale from someone experienced" | "the underlying numbers to back it up" |

In most white-collar self-presentation, "evidence," "data," and "numbers" read as the more
rigorous, more defensible answer almost by default — independent of whether the respondent
actually works better on gut calls. This is the same failure the project has already named twice
elsewhere (patent counts as an innovation proxy, `comp` as raw dollars): a construct where one pole
carries social/professional prestige that has nothing to do with the trait being measured. Here it
shows up on the person side instead of the company side, which is new — worth flagging because it
means the risk isn't confined to company scoring.

**This is the single dimension most likely to show a strong empirical lean in a pilot**, and per
the doc's own gate 2, a strong lean means rewrite, not "people are just mostly data-driven."

**Fix direction:** reframe around speed-of-decision and information-sufficiency rather than
rigor-of-method, so neither option sounds like the responsible one. E.g. de2 becomes something like
low: *"you'd rather decide today on what you already know"* / high: *"you'd rather wait a day and
be sure."* Needs a real rewrite pass, not a patch — flagging the direction, not proposing final text
for all four without your sign-off.

**Secondary, smaller issue:** `de3` is the only item in the whole set phrased as quoted dialogue
("My gut says..." / "Let's look at...") rather than a behavioral scenario. Inconsistent format,
worth conforming to the rest even independent of the content fix.

---

## Finding 3 — three more single-item desirability skews, smaller than Finding 2 but real

* **`pa2`** (pace): low-pole option is *"protect the timeline and keep the quality bar."*
  "Quality bar" is a virtue term — it makes the *low-pace* pole sound like the conscientious
  choice, which will pull respondents toward it regardless of true pace preference. Reword to drop
  the quality-language: e.g. *"you'd rather push the deadline back a few days."*
* **`fb3`** (feedback): low-pole option is *"trusted you and stayed hands-off,"* high-pole is
  *"gave constant, unfiltered input."* "Trusted you" is strongly positive-valence and "unfiltered"
  mildly negative-valence (can read as tactless) — skews toward low. Reword the high-pole side to
  something equally positive, e.g. *"told you exactly where you stood, every time."*
* **`in1`** (innovation): high-pole option ("building something that didn't exist before") reads
  as more prestigious than low-pole ("making an existing thing run better"). This one is harder to
  fully neutralize — it's close to inherent to what the dimension measures — but worth being aware
  it's the dimension most likely to inherit the same marketing-prestige inflation problem already
  documented on the company-scoring side (Julie's patent argument, the ≤0.7 rule). If innovation
  shows a pilot lean, this item is the first place to look.

---

## Finding 4 — two items plausibly leak into a second dimension

Not a desirability problem, a confound risk — the same shape as the project's standing rule that
confounders must not double-count through a dimension score.

* **`au3`** (autonomy — making a call above your role) also taps risk tolerance / decision style.
  Someone could score low on decision (gut-driven) and still answer this one based on risk
  appetite rather than autonomy preference specifically.
* **`pa2`** (pace, also flagged above) bundles a pace preference with a quality-vs-speed values
  question — arguably closer to a conscientiousness trait than pace per se.

Not proposing removal — four items per dimension is already thin, per the model's own
non-overlap requirement — but worth watching in pilot data: if these two items correlate more with
a *different* dimension's score than their own, that's the tell.

---

## Not flagged, checked and fine

* The four existing reverse-keyed items (`au4`, `pa4`, `co4`, `in4`) are logically sound — the
  frustration framing correctly maps to the opposite-preference pole in each case, verified against
  `pole:` values, not just the comment tag.
* Options are reasonably matched in length/specificity across the set outside the cases above.
* `au1`, `au2`, `co1`, `co2`, `pa1`, `pa3`, `fb1`, `fb2`, `fb4`, `in2`, `in3`, `co3` read as
  genuinely balanced forced choices — no dominant socially-desirable option in either direction.

---

## Recommended order of work

1. Decision dimension rewrite (Finding 2) — highest-confidence prediction of a pilot lean, affects
   all four items.
2. Add the two missing reverse-keyed items (Finding 1) — feedback and decision.
3. `pa2` and `fb3` single-item rewrites (Finding 3).
4. Pilot on a small internal group before wider use, specifically watching: (a) per-item lean
   toward one pole approaching or exceeding what gate 2 would flag, (b) `au3`/`pa2` correlating
   with a dimension other than their own.

Nothing here has been changed in `assessment_items.yaml` — this is a review for sign-off, not an
applied edit, consistent with how the rubric anchors went through Sebastian's ratification before
being frozen.
