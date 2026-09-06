# anchors_v3 — what changed, and what I need from you

**File:** `anchors_v3_PROPOSED.json`
**What it is:** a proposed replacement for the scoring rubric you wrote. Nothing is adopted. The
frozen `anchors.json` that round 1 was scored against is untouched and stays untouched.

---

## The honest part first

**None of this can be checked, and you are the only reviewer it will get.**

Round 1 was the test. There will not be a round 2 — Carolynn and George gave more time than either
of us expected and I am not asking them again, and there is no budget for paid raters. You can't be
the blind check on your own wording. So there is no independent human pass left.

The obvious fallback was the LLM extractor: change the anchors, see if its scores move. That was run
today, twice.

- Rewriting the **Decision** guardrail moved its score on **zero of six** packets. Identical numbers
  before and after.
- Rewriting **Feedback** — including the band text itself, a stronger change — moved about six cells
  by one band, against nine cells that already wander between two runs of the *identical* input. Less
  movement than the model's own noise.

Then the reason became clear, and it's the important finding. Measuring which excerpts got cited
under two different dimensions, **you and George both collide most often between Collaboration and
Feedback** — four shared passages each, the top pair for both of you. **The extractor never makes
that mistake, under either version of the rubric.** Its own worst confusion is Decision/Pace, which
neither of you shows.

So the machine can't test this fix, because it doesn't have the problem the fix is for. **That leaves
your judgement, with nothing behind it.** I'd rather say that plainly than hand you a file implying
it's been verified.

---

## What changed and why

**Five of the six dimensions changed. Pace is untouched.** The companion document,
`anchors_v3_rubric.docx`, has the full rubric with every changed field marked and the previous
wording beneath it — read that one to check exact text. This section covers the two changes that
need reasoning rather than reading.

- **Autonomy** — guardrail extended (Collaboration boundary).
- **Collaboration** — 0.1 and 0.3 band text, where-to-look, and a new Feedback boundary.
- **Feedback** — 0.1 and 0.3 band text, where-to-look, guardrail. *Explained below.*
- **Innovation** — 0.1 and 0.3 band text, where-to-look, and a new Autonomy boundary.
- **Decision** — guardrail, where-to-look, and **the 0.5 band**. *Explained below.*

### Feedback — the substantive change

Round 1's Feedback citations were mostly about supportiveness: "never retaliate," "coworkers care
about your growth," "comfortable coming forward," "constant support." Across 24 citations from
Carolynn and George only 2–3 were about how critique is actually delivered.

My first read was that both raters had drifted off-axis. **That was wrong, and the rubric text is
why.** The frozen 0.1 band reads:

> "Feedback is occasional and softened. **Harmony valued, conflict avoided, supportive or nurturing
> framing.**"

Supportiveness is written into the bottom band as part of its definition — and there is no
counterpart at the top. The 0.9 band is pure axis: "radical candor, constant unfiltered input,
critique and debate are the default." So warmth evidence had a home at one end of the scale and
nowhere else, which means it could only ever push a score **down**. Anyone citing "they're
supportive here" was following the rubric, not misreading it.

| band | was | now |
|---|---|---|
| 0.1 | Feedback is occasional and softened. Harmony valued, conflict avoided, supportive or nurturing framing. | Feedback is occasional and softened. Critique, when it comes, is cushioned or indirect, and open disagreement is rare in the evidence. |
| 0.3 | Feedback mostly on cycles, delivered with care. Directness is the exception. | Feedback arrives mainly on a fixed cycle and is delivered diplomatically. Directness is the exception. |

The guardrail now says warmth is **orthogonal** to this axis and appears at both poles — a caring
company can give feedback constantly and bluntly; a cold one can give it rarely and vaguely.

Collaboration and Feedback are also the pair you and George confuse most, and neither dimension said
a word about the other. Both now do: **how often people talk to each other, and how good the working
relationships are, is Collaboration (team density) or nothing — Feedback needs a statement about
critique**, how bluntly it's delivered or how often.

### Decision's 0.5 band — aimed at the worst result in the round

Decision was the only dimension where Carolynn and George agreed on **none** of the six packets, and
they sat further apart there than anywhere else. The 0.5 band now says what it is for:

> "Both judgement and data carry weight depending on the call. **Use this band when different parts
> of the packet point to different poles — that is what it exists for. Do not resolve a genuine
> conflict in the evidence by picking the quote you find most persuasive; that is exactly the kind of
> read that produces spread between raters.**"

This is the one edit written directly at a measured failure rather than at a wording problem. It is
also untested — like everything else here.

### Collaboration, Innovation, Autonomy

Band and guardrail edits from the earlier round of bleed-fixing. These are the only changes in the
file with a measured A/B behind them: on matched vignettes, Collaboration's bleed went 5/5 → 0/5 and
Innovation's 5/5 → 2/5. Worth a read but not a decision.

---

## What I actually need from you

**1. Feedback's low bands.** Is "critique is cushioned or indirect, open disagreement is rare" the
same culture you meant by the old wording — or did removing the warmth language remove something
real? You may think the warmth belonged there. If so I'd rather know that than have you approve a
change you're lukewarm on, because the whole point of the rewrite is that warmth and critique-style
are separable, and if they aren't, the fix is wrong.

**2. The Collaboration/Feedback line.** Is it drawn where you'd draw it? Specifically: a company
where people raise concerns freely and managers listen — is that Collaboration evidence, Feedback
evidence, both, or neither? Your answer sets the rule.

**3. Decision's guardrail — does it over-exclude?** It tells a rater that "following procedures" and
"ownership" are Autonomy signals, not Decision. I think that's right, but a heavily-processed
approval chain *can* be genuinely evidence about how decisions get made. Is the exclusion too blunt?

**4. Optional, and a different question.** The rater app requires a score on every dimension. The
lowest confidence band means "almost nothing in the packet bears on this dimension" — but you still
have to commit a number. **Should there be a way to skip a dimension entirely?** You're the only
person who has both written this rubric and sat through scoring six packets against it.

---

## What round 1 actually produced

Worth saying, since you did the work. Your free-text notes were the most useful output of the whole
round — sharper and more specific than anything else that came back. Three things came directly from
them:

- The **segment-coverage gap** on P-02, which you found from the scoring side and which independently
  confirmed a defect found separately from the research side. Two passes landing on the same problem.
- The **P-04 stale-review claim**, which was checked against the packet today. You were right that
  current reviews existed and weren't used. It turned out to be a deliberate collection rule rather
  than a build mistake, and that rule had already been fixed thirteen days after P-04 was built.
- The **quarantine idea and the company-stability question**, both of which were worked through today
  and turned into recorded decisions.

The wording problem in Feedback's 0.1 band is the kind of thing that is close to invisible until
36 real scores exist to show it. It took the round to find it.
