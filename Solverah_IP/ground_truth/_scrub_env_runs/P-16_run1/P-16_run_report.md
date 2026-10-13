# P-16 run report

**Packet scrubbed:** P-16 (exactly one raw packet present: `P-16_packet.txt`). Scheduled, unattended run. Ruleset read in full (R1-R8, A1-A9, JC-1-4, OPEN section). Folder held only the brief, ruleset, README and one packet. No other packet seen.

**Output:** `P-16_packet_ANON.txt`, `P-16_scrub_diff.txt` (carries removed strings + token mapping), `P-16_content_defects.txt`, this report.

**Structure decision.** Only Section 1 (the rater-facing part) is carried into the output, plus the new header and the END marker. Raw Sections 2-5 (QA, roster, pre-flags, defect report) are build-side, say "NEVER IN THE PACKET", and name the company throughout; they are not carried. Raw BUILD RECORD replaced by the header block. Nothing inside Section 1 was reordered.

**Recognition:** company identified from the evidence (expected, harmless). Not searched.

## Self-check
1. `http` count in output: **0** — pass
2. Company name / GeekWire: **0** outside brackets — pass
3. rev-01 … rev-15, one id per review, stable — pass
4. Quote bodies identical to raw except declared edits — pass (reverse-substitution check plus read of every changed line in the diff)
5. Every body substitution declared on its excerpt line (attribution-level substitutions also declared) — pass
6. Excerpt count 44 in / 44 out — pass
7. Typos kept ("to it quota", "uncertainly", unclosed quotation, markdown characters, Spanish review) — pass
8. `Remote` literal: 6 in raw, 6 in output — pass
9. Job titles / sector language untouched — pass
10. Diff file exists, every changed line — pass
11. Markers literal, header carries `build v4.11`, log after END marker — pass
12. Blank line above every bullet (44/44) — pass
13. Per-section table:
   - A: 8 bullets / header says 5–8 — match
   - B: 15 / 12–15 — match
   - C: 10 / 6–10 — match
   - D: 7 / 7 — match
   - E: 4 / header says 3 independent + 1 tagged — match
   - F: 0 / 0 — match

## Judgment calls
- **JC-A, R6/A1 on "85% of the Fortune 500":** treated as an identifying figure and replaced with "a large majority". It is also a verbatim self-description that JC-1 would keep. Flagging because the ruleset does not name this case; reverse by restoring the figure if you decide JC-1 wins.
- **R4/A5, Hub Champion / Volunteer Champion:** branded programme names rewritten to `[programme name stripped]`; the attribution role for the testimonial was likewise stripped. Clause survives.
- **Left alone (third-party tools):** Salesforce, MEDDICC, Outreach. Used by thousands of employers; stripping Salesforce/MEDDICC would take the claim with it (A5 test). Same trade as ATS vendor names.
- **Left alone (signal):** "Employee Resource Groups (ERGs)" and "eight"; "mob programming", "collective code ownership", "psychologically safe retrospectives"; Manxue passage's "pushing past limits" (soft echo of a value name, clause is the claim); "less than 20% hitting quota, average org attainment under 50%" in a review (reviewer's own figures, already approximate).
- **Left alone (dated facts):** Section F text "taken private in January 2025" and the review/NOTE references to acquisition, layoffs and a September 2026 leadership change. Not covered by any rule; they are strong context but also identifying in combination. Flagging for a ruleset decision.
- **R3 publication class:** GeekWire reduced to "trade press" along with the bylines.
- **R5 tokens minted (5):** [Site A]-[Site E]. No pre-flag tokens existed. Mapping is in the diff only.
- **Recurrence notes (A3/A9): none attached.** Section C's three mob-programming/ownership excerpts all come from one posting, so I did not treat them as a second company source. Section A↔D overlap on community/connection is thematic, not a restated claim.
- **Review headlines (A7):** none are printed in this packet, so nothing to keep or strip.
- **R7 exposure:** the Spanish review and the two [sic] phrases are exact-match searchable (T2 exposure, kept per R7).
- **OPEN reviewer-level re-identification:** Heredia (Spanish) review is a single non-English review plus a site token plus a date; left alone and flagged per the OPEN section.

## Flagged, not decided
- Pre-flag block errors CD-1 to CD-8 (see defects file); CD-3 (Varun named inside a quote body, listed as "not quoted") is the serious one.
- Ruleset gap: dates of structural events (take-private, layoffs, CEO change) and the Fortune-500 style figures.
