# P-13 run report

Packet scrubbed: P-13 (one raw packet present in packets_raw; none other). Build v4.11, built 2026-09-28. Scrubbed 2026-09-29 by scheduled run. Files: P-13_packet_ANON.txt, P-13_scrub_diff.txt, P-13_content_defects.txt, this report.

## Self-check results
1. `http` occurrences in output: 0. PASS
2. Company name and short forms (plus executive, technician and reporter names) outside brackets: 0. PASS
3. 16 distinct rev-NN ids, one per review, stable; employer response keyed "reply to rev-04". PASS
4. Quote bodies compared to raw by character diff: every difference is a declared R2, R3 or A5 substitution. PASS
5. Every body substitution and every minted place token is declared on its own excerpt line. PASS
6. 55 excerpt bullets in raw, 55 in output. PASS
7. All seven preserved typos still present. PASS
8. "Remote" literal: raw section 1 has no capitalised "Remote"; lowercase "remote" left as-is. PASS
9. All non-bullet lines identical to raw; titles and sector language untouched. PASS
10. Diff file written with every changed line, the minted-token map and posting-id map. PASS
11. Both markers literal, header carries `build v4.11`, scrub log after END marker. PASS
12. Blank line above every bullet: 0 exceptions; 55 blocks parse as bullets. PASS
13. Per-section table (bullets / header declares):
   - A: 8 / 5-8 range: within range
   - B: 17 / 12-15 range: exceeds (16 reviews + 1 employer response); header reproduced, defect CD-4
   - C: 12 / 6-10 range: exceeds; header reproduced, defect CD-4
   - D: 8 / yield 8: match
   - E: 4 / yield 4: match
   - F: 6 / yield 6: match
   Total 55.

## Judgment calls
- Sections 2-4 of the raw packet (researcher QA, roster block, pre-flags) are not carried; they sit between the SECTION 1 marker's body and the END marker in the raw file and are labelled remove-before-packet. Section 1 is carried unchanged apart from edits.
- Employer response bullet: its URL replaced with "reply to rev-04" (it answers the Driver Leader review).
- The reviews' non-resolving location string was tokenised like the real places (R5); the note on that line that the fields do not resolve is kept verbatim.
- A named customer abbreviation in a review body rewritten as "[name stripped]" under A5. The ruleset copy has no separate named-clients rule although the README mentions one; flagging in case the repo version differs.
- Section E bylines and publication names reduced to "trade press" (R3, JC-2 reasoning).
- Executive quotes: role labels used ("[the executive]", "[the chief executive]", "[the outgoing chief executive]"); the technician's first name became "[the technician]".

## Flagged, not decided
- A section A excerpt describes the company as more than a fleet-colour phrase. That phrase is the strongest fingerprint left in the packet, but the ruleset has no rule for colours and removal would edit a distinctive self-description (JC-1). Left as written.
- "operating center" facility vocabulary (three review bodies) left as written; not a branded name under A5.
- Location field reading "Jet set" left: not a place.
- Reviewer-level re-identification (headlines, typos, site token, date) left per the OPEN item; T2 exposure recorded per A7 and R7.
- No A9 recurrence notes: no company-voice claim restated across sections found. Closest pairs are thematic (safety, career growth), not restatements.
- Recognition: the company is recognisable from the evidence; no search was run.
