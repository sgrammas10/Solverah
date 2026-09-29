# Company culture rating: round 2 instructions

Round 2 · rubric v3.1 (`v3.1-PROPOSED-2026-09-29`, page anchors `3e270b206116`) · issued 2026-09-29

For **Sebastian (rater D)**, who rates every round-2 packet, and **Julie (rater A)**, who rates two
per group. The round-1 instructions (`RATER_INSTRUCTIONS.md`) stay as the record of what round 1
was told. Most of it still holds, and this file says where round 2 differs. The design is in
`Solverah_IP/analysis_s58/PREREG_ROUND2_2026-09-29.md`, addendum A1.

Each file is a self-contained web page: the evidence about one company and the scoring form, side
by side. Open it in a browser. Your answers save in the page as you go, so you can close it and
come back. Budget about 40 minutes a packet.

---

## What is new in round 2

**You can record "insufficient evidence" instead of a score.** Every dimension now has a sixth
option under the five bands. Use it when the packet genuinely cannot characterise the company on
that dimension. It asks for no confidence, and quotes are optional.

- **It is not 0.5.** 0.5 means the evidence you have supports a mixed or balanced position.
  Insufficient evidence means there is not enough to say either way.
- **Contradictory evidence is not automatically 0.5 either.** If one side clearly outweighs the
  other on strength, recency, relevance or amount, score toward it.
- **Do not use it to avoid a hard call.** If the packet does bear on the dimension, give the band
  and let the confidence answer say how thin it is.

The rubric text itself changed in a few places (Feedback's lowest band; where "raising concerns"
belongs; when a decision procedure counts as Decision evidence). **Read the dimension text on the
page, not your memory of it.**

---

## The rules

1. **Do not search for anything.** Same as round 1. The page asks, so answer honestly.
2. **Recognition is expected; answer it honestly.** Sebastian, you will recognise every packet,
   so say so every time. Then score from the evidence in front of you, **not from what you know
   about the company or why it was picked.**
3. **One packet per sitting, no going back.** Each dimension locks when you commit it, and the
   packet locks when you submit. Never have two packets open at once, and don't compare companies
   with each other. Score against the scale.
4. **Work alone, and don't talk about the overlap packets.** Julie's two packets are also
   Sebastian's. Please **don't discuss those packets, your scores or your reasoning with each
   other**, before or after, until both files are in. Two readings that compared notes become one
   reading with two names, and nothing afterwards can detect or undo that.
5. **Read the whole packet before you score anything.**

### Sebastian only (rater D)

6. **While rating, don't open** the roster, `_build_env/to_be_researched.txt`, `PIPELINE_LOG.md`,
   or anything else that records why a company was chosen or which pole it was expected to show.
   You picked these companies for pole coverage. The point of this rule is that your score comes
   from the packet, not from that expectation. It can't be checked, so it rests on you.
7. **Don't look at any LLM output for a packet until you have submitted it.** The LLM is not run
   on a packet until your submission for it exists, and the analysis checks the timestamps.
8. **Work in this order** (drawn at random: `random.Random(20260930).shuffle` over P-07..P-12):

   | 1st | 2nd | 3rd | 4th | 5th | 6th | then |
   |---|---|---|---|---|---|---|
   | P-07 | P-11 | P-09 | P-08 | P-12 | P-10 | P-13 once it is in `anonymization/` |

### Julie only (rater A)

Two packets, **P-11 then P-10**, one per sitting, whenever suits you. A half-finished sitting is
fine: the page keeps your place.

---

## Citations, confidence, and the source line

Unchanged from round 1:
- select passages and never type them;
- confidence is about the evidence, not about you;
- the page records where each passage came from.

For a scored dimension, at least one citation is still required. For insufficient evidence it is
optional. If you do cite something, cite what shows the packet can't support a score.

---

## Getting your answers back

On submit the page saves `solverah_P-XX_raterD.json` (or `_raterA`) to your Downloads folder.

- **Julie:** send the file to Sebastian.
- **Sebastian:** put the file in `Solverah_IP/ground_truth/rater_app/returned/round2/`.
- If the automatic save doesn't happen, use **Download result file** or **Copy to clipboard** on
  the same screen.
- **Don't clear browser data** until the file is safely placed.
- **A red banner** means the browser isn't saving progress. Finish that packet in one sitting.

## If something goes wrong

If a page is lost mid-packet, say which one and it will be reissued. A re-rated packet is fine as
long as it is recorded. Anything confusing (an anchor that fits nothing, a contradictory section)
goes in the free-text note at the end. Those notes are how the rubric improves.
