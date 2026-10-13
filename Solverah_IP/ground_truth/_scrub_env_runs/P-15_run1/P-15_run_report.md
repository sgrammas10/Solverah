# P-15 run report

Packet scrubbed: **P-15** (build v4.11, claude-opus-5, built 2026-09-30). One packet in packets_raw; single session; nothing else in the folder beyond brief, ruleset, README.

Sections 2-4 of the raw packet (QA, roster, pre-flags) were NOT carried into the output (the rater-facing file is section 1 only). The raw file has no scrub-header block, so the header was written fresh per the brief.

## Self-check

 1. PASS — "http" occurrences in packet: 0
 2. PASS — name/short forms (Hudson River Trading, HRT, Hudson River) outside bracket substitutions: 0; extra identifier sweep hits: none
 3. PASS — review ids rev-01, rev-02, rev-03, rev-04, rev-05 — each used once, in packet order; raw review URLs: 5, all removed
 4. PASS — 31 bullets: quote bodies compared after collapsing the declared substitution tokens; all character-identical otherwise (dashes, curly quotes, spacing, typos)
 5. PASS — every bullet whose quote body changed carries a bracketed declaration on its own line; undeclared: 0
 6. PASS — excerpt counts raw vs scrubbed by section: {'A': 8, 'B': 5, 'C': 10, 'D': 4, 'E': 4} vs {'A': 8, 'B': 5, 'C': 10, 'D': 4, 'E': 4}
 7. PASS — preserved typos present: As focus on the software, learn(take on a mentor), 8quarter pay outs, can't think if any cons
 8. PASS — "Remote" occurrences raw 0 / scrubbed 0 (the packet carries none; nothing to preserve or break)
 9. PASS — job titles and sector language untouched (titles checked: People Operations Specialist, Systems Administrator, Quantitative researcher, Junior algo developer, Trading algo developer, Algo Software Engineers, Research Engineer)
10. PASS — diff written: 32 changed lines (of 120 section-1 lines)
11. PASS — both markers literal and single; header has "build v4.11"; scrub log placed after END marker
12. PASS — bullets without a blank line directly above: 0 []
13. PASS — per-section table in run report; total 31 bullets

### Check 13 table

- A: 8 bullets / header says "5-8 excerpts" — match
- B: 5 bullets / header says "12-15, most recent first" — SHORT (declared shortfall; see content defects)
- C: 10 bullets / header says "6-10 excerpts from 3+ open postings, different functions" — match
- D: 4 bullets / header says "yield: 4 passages from 1 source · ladder fully attempted" — match
- E: 4 bullets / header says "yield: 4 · searches logged: 4" — match
- F: 0 bullets / header says "yield: 0" — match (private company, N/A)

## Pre-flag block vs. my sweep (build defects, direction: the block under-flagged)
- Short form "Hudson River" (possessive, E excerpt 3 quote body) not flagged; only "Hudson River Trading" and "HRT" are.
- Surname-only "Dunning" appears twice in E quote bodies; the block flags the full name only.
- Descriptor text "AI & Machine Learning at HRT" in section A attributions not flagged.
- Publication names (eFinancialCareers, Hedgeweek) in section E attributions not flagged; R3 wants publication class only.
- The section 1 scope paragraph names "New York"; the location flag covers only section B attributions.
- Block does not reach: tenure figure in D note and attribution (see below).
- Direction opposite (flag pointing at nothing in section 1): "HRTer(s)", "HRT AI Labs/HAIL", "Inside@HRT", "Modern Health", Slack/Jira etc., repo names, "THINK / TRUST / TINKER / TRADE" as a four-word set (only the TRUST tile appears). No harm.

## Judgment calls and flags (decided or deferred)
1. "[The head of AI research]" used for surname-only mentions in E (R3, role kept); full-name mention became "[name stripped], head of AI research". Role is signal.
2. Publication names removed from E attributions -> "trade press" (R3 publication class). Not a quote-body edit.
3. Recurrence note (A3/A9) added to D excerpt 1: "pod"/silo claim also in C research-engineering posting (excerpt 3). Judgment; other near-repeats (non-siloed in C1 and C9; A-section collaboration lines) are within one section and left unannotated.
4. A5 left alone: "Algo", "Platform", "AE/AD/RE" inside quotes - removing them removes the claim.
5. Flagged, not decided (R6/A1 stretch): D author tenure "approx. 13 years" (note and attribution) and B note's "119 reviews"/"one day old" on the second review site. Both are rater-useful signal; tenure plus blog could narrow to a person. Left as written. Reviewer-level re-identification OPEN item applies: each B entry pairs a title, a site token and a date.
6. ATS vendor name (Greenhouse) appears only in URLs in section 1, so it was removed with them; A8 would have kept it had it been printed as text.
7. Review headlines: the three fragment headlines are kept verbatim (A7); exposure recorded.
8. The recognition: company identified from the evidence (a named quantitative trading firm); expected per brief, nothing searched.
9. Section 1 attribution lines in A/C/D/E keep `accessed`/`retrieved` notes exactly as raw.
