# Round 2: the plan, step by step

Written 2026-10-01 for Sebastian. The rules behind each step are in
`PREREG_ROUND2_2026-09-29.md` (addenda A1 and A2). This file is the to-do list.

**Where things stand:**
- Rubric v3.1 is frozen for round 2 (hash `3e270b206116`).
- Pages are built for P-07..P-13.
- P-14..P-19 are still in the pipeline.
- Nobody has rated anything yet.

---

## 1. You rate (start now)

- [ ] Rate in this order, **one packet per sitting**: P-07, P-11, P-09, P-08, P-12, P-10, P-13.
- [ ] Use the pages in `ground_truth/rater_app/out/round2/P-XX_raterD.html`.
- [ ] After each one, move the downloaded `solverah_P-XX_raterD.json` into
      `ground_truth/rater_app/returned/round2/`.

While rating:
- No roster, no `to_be_researched.txt`, no `PIPELINE_LOG.md`.
- No LLM output for a packet until you have submitted it.
- Answer the recognition question honestly ("recognised" is expected).
- Score from the packet, not from why you picked the company.

## 2. The LLM scores each packet you've finished (needs your go, it costs money)

- [ ] Tell Claude which packets you've submitted. Claude runs the dry run, which spends nothing:
      `python causal_graph/run_round2_scoring.py P-07 P-11 ...`
- [ ] Claude quotes the call count (3 per packet) and the dollar cost, and waits for your go.
- [ ] Then the live run:
      `SOLVERAH_ALLOW_LIVE_CALLS=1 python causal_graph/run_round2_scoring.py P-07 ... --live`
- The runner refuses any packet you haven't submitted, any packet whose file changed since you
  rated it, and any packet that fails the scrub check.

## 3. Each new packet as it arrives (P-14..P-19)

When the harvest moves a packet into `ground_truth/anonymization/`:

- [ ] Add its company name(s) to `ROUND2_COMPANIES` in `causal_graph/run_round2_scoring.py`.
- [ ] Run `python Solverah_IP/ground_truth/rater_app/build_round2_pages.py`. It checks the scrub
      first, then builds your page and Julie's numbered page.
- [ ] Before you rate any of P-14..P-19, draw your order for them and record it as a dated line
      in the prereg. (Ask Claude, so it is drawn by seed and not chosen.)

## 4. Send Julie her bundle (once all packets are built)

- [ ] Edit `out/round2/NOTE_FOR_JULIE.txt` into your own words. It is a draft that says:
      do as many as you like, in the numbered order, stop whenever.
- [ ] Send the whole `out/round2/for_julie/` folder.
- [ ] Send `Solverah_IP/anchors_v31_confirm/confirm_sheet.html` **last**: in the same email
      marked "after you're done", or separately when she says she's finished.
- [ ] When her result files come back, put them in `returned/round2/` **without opening them**.
- [ ] Don't discuss any packet with her until round 2 is closed.

## 5. After all rating is done

- [ ] **Only now** open the roster and export each company's expected pole per dimension
      (P-07..P-19) into a `poles.json`. This feeds the check for whether your scores leaned
      toward your selection expectations.
- [ ] Load the LLM results into the local lane database. It refuses anything that is not a
      local `solverah_gt*` database, and you should never point it at `.env`:
      `python -m Scripts.ingest_round2_scores --database-url postgresql://solverah:solverah@localhost:5433/solverah_gt2 --dry-run`
      then the same command again without `--dry-run`.
- [ ] Run the analysis:
      `python Solverah_IP/analysis_s58/round2_analysis.py --returned Solverah_IP/ground_truth/rater_app/returned/round2 --llm Solverah_IP/analysis_s58/results/round2 --expected-poles poles.json --out round2_report.json`
- [ ] Read the verdict. **INCONCLUSIVE is the expected result** with a small overlap, and it does
      not mean the LLM failed. Also check:
      - whether Julie's completed packets were "a random prefix" or "partly self-selected";
      - the floor-bias reading;
      - the selection-expectation check;
      - the cells two or more bands apart, which a human reads before anything is called noise.

## 6. Then

- [ ] **Julie's confirm-sheet answers:** any "change this" becomes rubric v3.2 for round 3.
      Round 2's numbers are never mixed with round 3's.
- [ ] **Calibration:** the harness refuses to fit until 15 or more packets have your reading,
      and round 2 alone won't reach that. No mapping ships from round 2.
- [ ] **Never** rescore P-01..P-06, and never edit `rater_app/anchors.json`.
