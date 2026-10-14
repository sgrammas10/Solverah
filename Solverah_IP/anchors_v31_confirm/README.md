# Rubric v3.1 confirm sheet

Julie's five rulings on anchors_v3 (`../ANCHORS_V3_JULIE_RESPONSE_2026-09-14.md`) have been
applied as `anchors_v3_1_PROPOSED.json`. This sheet asks her whether each one landed the
way she meant. **Nothing waits on her reply.**

| file | what it is |
|---|---|
| `confirm_sheet.html` | The instrument. Self-contained, offline. Seven items (five rulings, two changes she didn't rule on), each with yes / change this / I'd rather not say. Saves on every click; a half-finished sheet downloads fine. This is what gets sent. |
| `build_confirm_sheet.py` | Generates the page from `make_anchors_v3.V3_1_CHANGES`, the same list that writes the rubric file, so the two cannot drift. Rerun it after any change to that list. |
| `test_confirm_sheet.cjs` | jsdom checks: render, resume after reload, half-finished emit, storage blocked, download. |
| `test_build_confirm_sheet.py` | The sheet covers every change she is asked about, exactly once, and the file on disk is current. |

## Covering note (draft; edit it into your own voice)

> I applied your five rulings on the rubric. This is a short check that I got them right:
> seven questions, about 10 minutes, and it saves as you go, so stop whenever you like. The
> last two are changes I made that you didn't rule on. Send me the file it downloads,
> finished or not.

## Where her reply matters most

- **Ruling 3.** Decision's scale runs judgement to data. I read "a procedure governing
  decision-making is Decision evidence" as: score the procedure by what it makes the decision
  rest on (a required analysis points to data; escalation to a senior person's call points to
  judgement). Autonomy's own definition already includes "approval chains", so an approval
  layer can now be evidence for both dimensions, and the text says to cite it under both only
  when each definition is independently met. If she meant something else, that edit changes.
- **D1 and D2** are my inferences from ruling 4. Before them, the "Evidence over gut" gate told
  raters an "honest 0.5 at low confidence" was the safe answer, which is exactly what ruling
  4 separates out.

## After she replies

The download is `solverah_rubric_v31_julie.json`. Every answer names the change ids it covers
(`R1`, `R2a`...), which are the ids in `V3_1_CHANGES` and `ANCHORS_V3_1_CHANGELOG.md`. Apply
a "change this" by editing that entry and rerunning `make_anchors_v3.py`,
`make_anchors_docx.py` and `build_confirm_sheet.py`. Bump `V3_1_VERSION` if round-2 pages
have already been built from the old text: the page hash changes with it, which is the point.

    NODE_PATH=../ground_truth/rater_app/node_modules node test_confirm_sheet.cjs
