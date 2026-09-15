# Priors elicitation — the expert hypothesis, asked for asynchronously

`priors.yaml` says of itself: *"PLACEHOLDER weights... Replace with expert-elicited values
later."* `solverah_model_config.yaml` says *"Numbers (priors) live in priors.yaml — swap
that file when the expert delivers real values."* This folder is how that swap gets its
numbers without needing the expert in a room for two hours.

## What's here

| file | what it is |
|---|---|
| `priors_elicitation.html` | The instrument. Self-contained, offline, saves to the browser as she goes. This is the thing that gets emailed. |
| `FOR_JULIE.md` | Draft covering note. **Not sent** — edit into your own voice. |
| `convert_priors_response.py` | Her returned JSON → `priors_elicited.yaml` + a plain-language report. Stdlib only. |
| `test_priors_elicitation.cjs` | jsdom test over the form, in the style of `rater_app/test_rater_page.js`. Writes `captured_payload.json` — real form output, for running the converter against. |

## The loop

```
# after she sends the file back
python convert_priors_response.py solverah_priors_julie.json
```

That writes `priors_elicited.yaml` beside the input and prints what she actually said in
plain language — which mismatch she thinks is most costly, which direction of being wrong
is survivable on each dimension, and how far apart her two answers to the repeated
question were.

**It does not touch `causal_graph/v1_model/priors.yaml`.** Adopting the values is a
deliberate copy. Keep the placeholder file when you do — the difference between the two
*is* the expert contribution, and you will want to be able to show it.

## How twelve questions become twelve parameters

The model's predictor is `z = intercept + Σ(mag·|g| + dir·g) + Σ(w·conf)`, and a
pole-against-opposite-pole mismatch is always `|g| = 0.8` — because a person's ladder
value snaps onto `COMPANY_LATTICE` first (`match_core.closest_achievable`), and that
lattice runs 0.1 to 0.9. So the two scenarios per dimension give two equations in two
unknowns:

```
z_above = intercept + 0.8·mag + 0.8·dir     (person high, role low)
z_below = intercept + 0.8·mag − 0.8·dir     (person low, role high)
```

Exactly determined, no fitting, no degrees of freedom to hide in. The baseline question
("someone who genuinely fits — how many in ten?") supplies the intercept and the
reference point every other answer is measured against.

`sd` comes from her stated confidence, or from a plausible range if she gave one. Those
mappings are the one place in the pipeline where a number isn't traceable to something
she said — they're named as constants at the top of the converter, with the reasoning,
so they can be argued with.

## Verified, not assumed

`NODE_PATH=../ground_truth/rater_app/node_modules node test_priors_elicitation.cjs` — 32
checks over the page: it renders, answers survive a close-and-reopen, it stays usable when
the browser blocks storage, a half-finished sitting still emits, and — the seam that
matters — the JSON it produces is keyed exactly as the converter reads it. Two real defects
came out of writing it: a declined dimension used to hold the progress bar below 100%
forever, quietly punishing the abstention the design depends on; and `.js` here is parsed
as an ES module now that Solverah_IP sits inside a repo whose `package.json` sets
`"type": "module"`, hence `.cjs`.

The converter round-trips every parameter back to a probability before writing anything
and exits non-zero if the recovery doesn't reproduce her answers. Separately, the emitted
YAML was loaded through the real `match_core` — `load` → `weights_from_priors` →
`point_p_fit` — on a synthetic response, and reproduced all ten stated probabilities plus
the baseline to within 1.7e-07. If the algebra here ever drifts from
`outcome_logit`, both checks fail loudly rather than quietly writing plausible weights.

## Design choices worth knowing

- **Dimension order is deliberately not the model's order,** and every dimension gets its
  own vignette with a different person and role. Round 1 produced a packet where one
  holistic impression was pasted into all six dimension notes and the six scores stopped
  being six independent reads. This is the cheap structural defence against a repeat.
- **A repeated question sits after the fourth dimension,** reworded, unflagged. Its delta
  is the only available read on the noise floor under a single expert's numbers — there is
  no second expert to compare against. The report prints it.
- **Abstention is a first-class answer.** "I'd rather not put a number on this" keeps the
  neutral placeholder for that dimension at a wide `sd`, which tells the model to let
  outcome data speak there. It is not a missing value and does not need chasing.
- **No pole is described as the good one.** The instructions say so explicitly, and the
  vignettes were written to keep evaluative language off both ends — the failure mode the
  anchors hit when warmth got written into feedback's low band with no counterpart at the
  high end.
- **`industry` is not elicited per level.** Five levels is a lot of judgement for a
  confounder nothing yet consumes; she's asked only whether it matters at all, and her
  answer widens or tightens the prior rather than moving its mean.

## What this does not do

It does not touch the anchors question, which is separate and still hers. It does not
produce a *validated* model — these are one expert's priors, which is exactly what the
design calls for at this stage and exactly what `cbm_notes.txt` step 1 describes. The
values stop being guesses only when step 4 has outcome data to pull them, and that still
depends on solving the post-placement signal.
