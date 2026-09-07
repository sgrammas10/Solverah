# RUN REPORT — scrub of P-09

**Packet scrubbed:** P-09 — and only P-09. `packets_raw/` held exactly one file,
`P-09_packet.txt` (plus `.gitkeep`), which is the correct single-packet state under Rule
Zero. No other packet was opened, and nothing outside this folder was read. The connected
folder contains only `SCRUB_BRIEF.md`, `ANONYMIZATION_RULES_DRAFT.md`, `README.txt`,
`packets_raw/` and `packets_out/` — the three things the brief says should be visible.
No search of any kind was run.

**Date:** 2026-09-07 · **Ruleset:** `ANONYMIZATION_RULES_DRAFT.md` as copied into this
folder, signed off 2026-08-15 and amended 2026-09-07 (A5, A6, A7 present, so the copy is
current as of the P-07 round).

**Source build:** v4.7, model `claude-opus-5`, built 2026-08-27.

**Recognition flag:** yes — the company is identifiable from the evidence, and was
identified while reading. Expected and harmless per Rule Zero; recorded here and nowhere
else. Nothing was looked up.

**Method:** the scrub ran as a patch over the raw file — a script of exact string
replacements, each asserting its own occurrence count and failing the run on a mismatch.
No quote body was retyped at any point, which is the mechanism that produced the P-02/P-05
em-dash defect. Every declaration and every blank-line check was then verified
mechanically against the raw file, not by reading.

**Files written to `packets_out/`:**

- `P-09_packet_ANON.txt` — the de-identified packet, scrub log after the END OF PACKET marker
- `P-09_scrub_diff.txt` — 46 changed lines, raw above scrubbed
- `P-09_content_defects.txt` — 2 recorded, 0 fixed
- `P-09_run_report.md` — this file

---

## Self-check 13 — per-section bullet table

| Section | Bullets counted | Header declares | Result |
|---|---|---|---|
| A. Careers / values | 8 | 5–8 excerpts | match (in range, at the top of it) |
| B. Employee reviews | 15 | 12–15 | match (in range, at the top of it) |
| C. Job postings | 10 | 6–10 excerpts from 3+ postings | match (in range; 5 postings, 5 functions) |
| D. First-person account | 4 | yield: 4 | match |
| E. Recent news | 3 | yield: 3 | match |
| F. Human capital | 4 | yield: 4 | match |
| **Total** | **44** | — | **44 in raw, 44 in scrubbed** |

No section undercounts or overcounts its own header, so no header defect of the P-07 kind
arises here. No section is empty and the whole-packet total is well clear of single
digits, so Rule Three is not silently failing.

## Self-check — all thirteen, with results

1. **`http` appears zero times.** PASS — 0 occurrences, case-insensitive, across the whole
   output. 44 URLs removed (15 replaced by `rev-NN`, 29 deleted). One non-URL `HTTP 403`
   in a retrieval note was rewritten to "a 403 error" so the check passes under a
   case-insensitive reading; declared in the log as JC-e.
2. **Company name and short forms appear zero times outside a bracketed substitution.**
   PASS — 0 occurrences of the name, its one-word short form, or its ticker, case-
   insensitive, in the whole output including the header and the log. Raw section 1
   carried 66.
3. **Every review referenced as `rev-NN`, same review always the same id.** PASS —
   15 references, 15 distinct ids, exactly `rev-01`…`rev-15`, assigned newest-first in
   the order the reviews appear. Each review appears once, so no id is reused or split.
   Zero residual review-site URLs.
4. **Every quote body character-identical except where its line declares otherwise.**
   PASS, verified by diff, not by reading. For all 44 excerpts the quote-body region was
   extracted from both files; the six lines carrying a declared body edit had their
   declared substitutions reversed programmatically; all 44 then compared byte-identical
   to the raw. 0 mismatches. Dashes, quote marks, the `...` ellipsis in D excerpt 4,
   spacing, wrapping, capitalisation and every misspelling are untouched.
5. **Every substitution declared on its own excerpt line.** PASS — 10 bracketed
   declarations written onto excerpt lines: all 6 lines with a quote-body edit, plus the 4
   lines whose attribution edit resolves to plain prose rather than a visible bracket
   (the R3 role substitutions and the R4/A5 podcast rewrite). Attribution substitutions
   that resolve to a bracketed token — `[the company]`, `[Site A]`…`[Site G]`,
   `[posting 1]`…`[posting 5]`, `rev-NN` — declare themselves on the line by being
   brackets. The log records everything as well, but the line declarations are the ones
   that count.
6. **Excerpt count matches section by section.** PASS — see the table above. 44 in, 44
   out, no section changed. The one recurrence handled under A3 got a note, not a
   deletion.
7. **Source typos still present and still misspelled.** PASS — all five survive verbatim:
   `certfication [sic]`, `minumum [sic]`, `arent [sic]`, `there [sic]`, and the incomplete
   final clause `...the toxic environment they.` The lowercase `las` in that same review's
   city name went with the R5/A6 site token, which is noted on the line.
8. **`Remote` still literal wherever the raw had it.** PASS, vacuously — `Remote` appears
   0 times in the raw packet's section 1 and 0 times in the output. Every review location
   is either a named place (tokenised) or the literal `not stated` (preserved as
   `not stated`, per R5).
9. **Job titles and sector language untouched.** PASS — no job title, function label or
   sector word was altered anywhere, including the four titles Section 4 flags as close to
   unique in the source site's index, the eyewear- and optical-specific vocabulary
   throughout B and C, and the 10-K's own list of employee categories in F. Industry is
   not scrubbed and no title was softened.
10. **Diff file exists and contains every changed line.** PASS — `P-09_scrub_diff.txt`,
    46 changed lines, raw above scrubbed, generated from the two files rather than written
    by hand.
11. **Markers literal, header carries `build vX.Y`, log after the END marker.** PASS —
    `########## SECTION 1 — EVIDENCE PACKET (the only part the raters see) ##########`
    reproduced exactly from the raw, `########## END OF PACKET ##########` present exactly
    once and literal, header block before SECTION 1 carrying the literal `build v4.7`
    (carried from the raw build record's `prompt version : v4.7`, not invented), and the
    scrub log placed entirely after the END OF PACKET marker. All six section markers read
    `--- A. ` … `--- F. ` unchanged, and every excerpt line still begins with `•`.
12. **Blank line directly above every excerpt bullet.** PASS — checked by inspecting the
    line above each of the 44 bullets in the output: 0 bullets share a block with anything
    above them. **Zero blank lines had to be inserted** — the raw packet already separates
    every bullet from its section header, its group headers and its neighbours. P-09 does
    not carry the P-07 defect, and the harness should parse 44 of 44 from the raw as well
    as from the scrubbed file. Verified rather than assumed, because this is the check that
    catches a section going invisible.
13. **Per-section table, bullets versus declared count.** PASS — table above, all six
    sections match, no discrepancy to record as a content defect.

**Result: 13 of 13 pass. No check had to be re-run after a fix. No ruleset conflict was
encountered that required stopping.**

---

## Judgment calls made

Full reasoning is in the scrub log inside the packet; summarised here for the pipeline
record.

- **JC-a — ATS posting identifiers tokenised.** Section 4 flags the five posting ids and
  the ATS hostname as direct re-identifiers and hands them to this step. R1 clears them
  from the URLs but they are also printed in plain text, and one is a distinctive
  exact-match string. **This is an extension of a rule to a case it does not cover**, taken
  deliberately and declared: the ids became `[posting 1]`…`[posting 5]`, on the same
  reasoning R1 gives for `rev-NN` — five distinct postings across five functions stays
  visible, the searchable string does not. The ATS vendor name was kept (a vendor thousands
  of employers use, and retrieval-method signal); the identifying hostname left with the
  URL. **Worth promoting to a rule** — every packet built from an ATS will hit this.
- **JC-b — R8/A3 extended from A↔F to A↔D.** D excerpt 2 restates A excerpt 6 in different
  words and quotes A excerpt 5's core value inside its own parenthesis. R8 is written
  against the A↔F boundary; its purpose — false triangulation inside the company-authored
  layer — is fully present here, and A, D-corporate-voice and F are all company-authored.
  A3's execution used: recurrence note on the second occurrence, nothing deleted.
  **Also worth promoting**: the corporate-voice material that fills section D on this
  packet is company-authored by any reading, and R8 as written does not reach it.
- **JC-c — the review headline keeps the A7 treatment and takes the R2 substitution.**
  A7 says keep headlines; R2 says substitute the company name inside a quote rather than
  delete it. Both applied, declared on the line.
- **JC-d — publication names reduced to class**, extending R3's byline rule to the outlet
  itself in the two cases where no byline was printed.
- **JC-e — one non-URL `HTTP` token rewritten** in a retrieval note so self-check 1 passes
  case-insensitively. Not a de-identification edit; declared because it is an edit.
- **Sections 2–5 dropped.** Section 1 alone is the rater-facing packet. Section 1's own
  marker says so, sections 2 and 3 are labelled REMOVE / NEVER IN THE PACKET, and the
  citation harness scores everything between the two markers. Sections 3 and 4 name the
  company outright.

## Flagged rather than decided

- **Reviewer-level re-identification.** Section 4 flags four review job titles as close to
  unique in the source site's own title index — two appear there exactly once — and each
  sits beside a site token and a date. That identifies a *reviewer*, not the company. No
  rule covers it, and the ruleset's industry finding positively forbids softening job
  titles, so nothing was changed. This needs a ruleset decision: either the titles stand
  and the exposure is accepted the way A7 accepts headline exposure, or the pre-flag block
  should stop flagging them.
- **A6 minting did not fire, and that is worth recording.** A6 was written because P-07's
  pre-flag block did not reach past section B. P-09's does reach the one in-body place
  name it needed to — the city inside the B rev-11 quote body already had a token from its
  own attribution, so the token was reused and none was minted. The build-side fix A6 calls
  for (extending the pre-flag block across every section) is still outstanding, but this
  packet did not need it.
- **T2 exposure carried, per R7 and A7.** Six exact-match searchable strings survive into
  the rater packet by rule: five preserved source typos and one review headline. Recorded,
  as both rules require, not removed.
- **Two content defects recorded, none fixed** — see `P-09_content_defects.txt`. CD-1:
  Section 1 is not self-contained; two attributions say "see fidelity note" and two section
  headers assert coverage whose evidence lives in the removed QA sections. CD-2: section E
  counts a company-authored SEC earnings release in its yield alongside two press excerpts
  — correctly disclosed on the line, but the build's own note of it (defect C-2) sits in a
  section nobody downstream reads.

## Note for the harvest

Nothing in this folder names any company other than the one in P-09, and this report names
none at all. `packets_raw/` should be emptied and the ruleset re-copied from the repo
before the next round, per README.txt.
