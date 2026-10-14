# Run report — P-14

Scrubbed: P-14 (build v4.11, built 2026-09-29), scrubbed 2026-09-30. Exactly one packet was present in packets_raw; no other packet, handoff or repo file was visible. Company recognised trivially from the evidence itself (its own filings and pages); no search performed.

Output scope: header block + Section 1 through `END OF PACKET` + scrub log. Raw Sections 2, 3 and 4 (researcher QA, roster/confounder block, pre-flags) are build record and were not carried into the output. Section 4 was used only as a cross-check.

## Self-check
1. `http` count in output: 0 — PASS
2. Company name, brand, short forms, executive names, place names: 0 occurrences outside bracketed substitutions (grep on the output) — PASS
3. Reviews are rev-01..rev-15, one id each, in packet order — PASS
4. Quote bodies identical to raw except declared tokens — word-level diff run; 15 lines differ, all listed in the diff file — PASS
5. Every quote-body substitution declared on its own excerpt line — PASS
6. Excerpt count 50 raw / 50 output — PASS
7. Typos kept (`Mangers [sic]`, `anual [sic]`, `ans [sic]`, `their [sic]`, mid-word caps) — PASS
8. `Remote`: 4 raw / 4 output — PASS
9. Job titles and sector language untouched — PASS
10. Diff file exists with every changed line plus the removed-string mapping — PASS
11. Both markers literal; header carries `build v4.11`; log after END marker — PASS
12. Blank line above every excerpt bullet (checked by scanning the line above each) — PASS
13. Per-section bullets vs header: A 8 / header says 5–8 — within range; B 15 / 12–15 — within range; C 10 / 6–10 — within range; D 7 / yield 7 — match; E 4 / "3 counted + 1 tagged" — match; F 6 / yield 6 — match. No zero sections.

## Edit counts
Quote-body: 12 company-name substitutions, 4 named humans, 4 branded names, 1 place. Attributions: 50 lines rewritten (name and URL out), 15 review ids, 4 posting ids, 6 site tokens minted ([Site A] to [Site F]; mapping in the diff file). No figures needed R6/A1 treatment.

## Judgment calls
- Page, article and document titles in attributions removed with the URL (several contain the company name or a branded phrase). Class and date kept.
- Trade-press publication names replaced with `trade-press`; the 10-K attribution keeps form type, fiscal year and filing date only.
- Testimonial label on the page (name + tenure) rewritten to a bracketed company name with tenure kept, declared on the line. Tenure plus the removed name is not identifying on its own.
- F1 value framework: stripped the acronym and the company name inside "One ..." only, keeping the seven value names under JC-1/A2 (Empowerment and Entrepreneurial Spirit are direct autonomy and innovation evidence). Residue: the initials of the seven names still spell the stripped acronym. Section 4 suggested a fuller rewrite; not adopted because it removes the value names. Flagged for the operator.
- "Employee Pulse" survey name replaced with `[name stripped]` (A5).
- "Philippines", "PH" and "US" left in review bodies: work-mode and offshore-structure signal, country level, not a company fingerprint.
- ATS posting ids replaced per A8. The vendor name was not printed in the raw attributions (only in the URL host), so none appears.
- Reviewer titles and headlines untouched (A7, open reviewer-level re-identification item left alone). "Client LIAISON Manager" and "Quite Satisfying Case Management Employment" are near-unique strings; T2 exposure recorded.
- Recurrence notes (A3/A9): considered the section A clear-expectations line against the section F clear-expectations survey sentence and the values-framework/respect pair. One is aspiration and one is a survey result, and the values pair are not the same claim. No note added; operator may overrule.
- Distinctive company-authored phrases (JC-1) kept.

## Flagged rather than decided
See P-14_content_defects.txt: review ordering (CD-1), scope-note role mismatch (CD-2), pre-flag block misses and miscounts (CD-3, CD-4, CD-5).

## Format notes
Excerpt bullets keep the raw indentation (`   •`). The diff file's line-165 entry is only the trailing blank line trimmed before the END marker.
