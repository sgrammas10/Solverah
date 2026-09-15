# Scrub run report — P-10

**Packet scrubbed:** `P-10_packet.txt`, the only packet in `packets_raw/` (one file plus
`.gitkeep`; Rule Zero satisfied — one packet, this session, and no other packet, roster or
company list was read, asked for or offered).
**Ruleset applied:** `ANONYMIZATION_RULES_DRAFT.md` — R1–R8, A1–A9, JC-1–JC-4.
**Build version carried into the header:** v4.7 (taken from the raw packet's build record; not
invented).
**Outputs:** `P-10_packet_ANON.txt`, `P-10_scrub_diff.txt`, `P-10_content_defects.txt`,
`P-10_run_report.md`. Nothing else was written to `packets_out/`; intermediates were built in
the system temp directory and no log file was left in the scrub folder.

## Method

Section 1 was extracted from the raw packet and edited by literal substitution, each substitution
asserted against an expected occurrence count. **No quote body was retyped at any point**, so the
P-02/P-05 em-dash class of defect cannot have occurred here. Fidelity was then verified
mechanically rather than by reading: each of the 45 raw quote bodies had the declared
substitutions applied to it programmatically and was compared character-for-character against the
scrubbed quote body. 17 quote bodies were edited; 0 mismatched.

## Per-section bullet table (self-check 13)

| Section | Bullets counted | Header declares | Result |
|---|---|---|---|
| A. Careers / values page | 8 | `(5–8 excerpts)` | match (in range) |
| B. Employee reviews | 15 | `(12–15, one per line, most recent first)` | match (in range) |
| C. Job postings | 10 | `(6–10 excerpts from 3+ open postings, different functions)` | match (in range; 4 postings) |
| D. First-person account | 5 | `yield: 3 passages / 5 excerpt lines` | match |
| E. Recent news | 3 | `yield: 3 excerpts` | match |
| F. Human capital disclosure | 4 | `yield: 4 excerpts` | match |
| **Total** | **45** | raw packet: 45 | **match** |

No section header disagrees with its own section, so nothing had to be reproduced verbatim as a
count defect. No section shows zero bullets.

## Self-check — all thirteen

| # | Check | Result |
|---|---|---|
| 1 | `http` appears zero times in the output | **PASS** — 0 occurrences in the whole file, header and scrub log included |
| 2 | Company name and obvious short forms appear zero times outside a bracketed substitution | **PASS** — case-insensitive sweep for the name, its stem, the derived employee term and the ticker: 0 hits. Also swept and clear: every named human, every named publication, the acquired brand, the branded programme names, the review-site and filing hostnames, and every city name |
| 3 | Every review referenced as `rev-NN`, same review always the same id | **PASS** — 15 review lines, `rev-01`…`rev-15` in document order, all distinct, each used once |
| 4 | Every quote body character-identical except where a declaration on that line says otherwise — verified by diff, not by reading | **PASS** — 45 bodies checked programmatically, 17 edited, **0 mismatches**. Dash / quote-mark inventory across all quote bodies: em dash 1→1, en dash 2→2, curly apostrophe 2→2, ellipsis 6→6; hyphen 10→13, straight apostrophe 15→16 and curly double quotes 2→1 change only inside declared bracketed substitutions |
| 5 | Every substitution declared on its own excerpt line, not only in the log | **PASS** with one declared exception — see JC-a below. Every quote-body edit carries a line declaration (checked programmatically: edited-without-declaration = none), as does every R3 role substitution, every site token, every magnitude replacement and the recurrence note: 24 line declarations plus 2 declarations on non-excerpt blocks |
| 6 | Excerpt count matches the raw packet, section by section | **PASS** — A 8, B 15, C 10, D 5, E 3, F 4 in both |
| 7 | Source typos still present and still misspelled | **PASS** — all three `[sic]` markers intact across two reviews, and the unmarked source irregularities are intact too (a subject–verb disagreement carried into the R2 substitution, a missing apostrophe, a split compound) |
| 8 | `Remote` still literal wherever the raw packet had it | **PASS** — 8 × `location: Remote` and 1 × lower-case `"remote"` as displayed, all untouched |
| 9 | Job titles and sector language untouched | **PASS** — all 14 review job titles, all 4 posting function labels, both section D role descriptors and the sector phrase inside a section E quote body verified present and unmodified |
| 10 | Diff file exists and contains every changed line | **PASS** — `P-10_scrub_diff.txt`: a substitution table (every removed string and its replacement, plus the site/branded-name/posting/review token maps) and a line diff of 49 hunks, raw above scrubbed |
| 11 | Both markers literal, header carries `build vX.Y`, scrub log after `END OF PACKET` | **PASS** — `########## SECTION 1` opens the body, one literal `########## END OF PACKET ##########`, header carries `build v4.7`, scrub log begins after the end marker |
| 12 | Every excerpt bullet has a blank line directly above it | **PASS** — 45 of 45, checked by inspecting the preceding line, not by trusting the edit. The raw packet already satisfied Rule Three, unusually; the check was run against the output regardless |
| 13 | Per-section table, bullets versus the header's declared count | **PASS** — table above; all six sections agree |

## Judgment calls

**JC-a — Rule Two applied to every edit a rater could not otherwise see, not to all 45 lines.**
R1's output is self-declaring: `company-authored`, `rev-07` and `[posting 3]` are visibly
substitutions, and the uniform R1 treatment is stated once in the header block instead. Every
edit that is *not* visible as an edit — every quote-body change, every named human replaced by a
role, every site token, every magnitude replacement, the recurrence note — carries its own
bracketed declaration on its line. Repeating the R1 strip 45 times would have buried the 24
declarations A4 was written to surface. Recorded as a judgment call rather than made silently.

**JC-b — the two named internal values got distinct tokens, and one token is reused across
sections.** `[named value A]` and `[named value B]` are two different values; per A6's
reuse-the-existing-token instruction, the value appearing in both section A and section C carries
the same token in both places.

**JC-c — which figures are "identifying".** Figures about the **company** were replaced with
magnitude language per R6/A1: two revenue-scale figures in a section E quote body (the source
packet's own pre-flag block flagged these and explicitly deferred them to this pass) and an
employer headcount band in two places. Figures about the **evidence base** were kept — review
counts, review ages, the truncated share, the ratio between the two review populations. They are
the packet's apparatus, not company figures, and they are the rater's only calibration for how
thin section B is; R6/A1 names headcount, dollar and percentage figures about the company.

**JC-d — small in-body figures left alone.** A tenure figure, a recency figure and a rhetorical
"100 projects" stay. None is a company metric, none is a one-query identification, and each is
dimension evidence inside its own sentence.

**JC-e — one named internal team inside a section B review was left in place.** A5 extends R4 to
branded names, and its test is whether the clause survives the rewrite. This is a descriptive
function label rather than a coined brand, it is the specific thing the reviewer's complaint is
about, and removing it would take function signal with it. Left alone and recorded, rather than
extended to on this pass's own initiative.

**JC-f — a widely used third-party meeting tool named in a section D quote body was kept.** It is
used by a large share of all employers and is retrieval-irrelevant; it is not a company
fingerprint. The same reasoning A8 gives for keeping an ATS vendor name.

**JC-g — the dangling cross-reference in a section B location field.** That field had to be edited
under R5 anyway. Rather than leave a pointer to a build-record section the rater never sees, the
pointer was replaced with what it pointed at, so the rater keeps the warning. Recorded as CD-5 so
the build gets fixed rather than the symptom.

## Flagged, not decided — for the ruleset owner

**FL-1 — does R5/A6 reach country scale?** A city-scale place inside a section D quote body was
tokenised and a token minted for it (`[Site E]`). The country named in the same sentence was left
literal, because the packet's own scope declaration states that same country as a coverage
boundary — "its non-US operations are barely represented" — and tokenising it there would destroy
the scope note while tokenising only the in-body instance produces exactly the split-consistency
A6 warns against. The ruleset does not say whether R5 reaches country scale, so this pass applied
it at site scale and stopped. **This needs a decision before the next packet with an
international first-person passage.**

**FL-2 — R8/A9 borderline.** One section F excerpt and one section A excerpt both assert employee
empowerment, in different words and at different levels of generality. It is not clearly one claim
in two costumes, so no recurrence note was attached; the note went only where the recurrence is
explicit. Whoever tightens A9 should decide whether its test is claim identity or thematic
overlap — as written, "reproduced by another company-authored source" admits both readings.

**FL-3 — reviewer-level re-identification (the ruleset's OPEN section) applies to this packet.**
Several review headlines are distinctive and sit beside a site token and a date. Per that section
this pass left them alone and records the exposure here. Note the timing: the OPEN section says
any forward-only rule would apply "from P-10, or from P-07 with two re-scrubs". **This is P-10,
and the rule does not exist yet** — so P-10 has been scrubbed without it, and if the rule is
written now, P-10 is already on the wrong side of the line it names.

**FL-4 — A7 exposure, recorded as A7 requires.** Review headlines are kept verbatim and are
exact-match searchable, as are the three preserved source typos under R7. Both are T2 exposure
and are handled by the no-search instruction and the submit-time question, not by editing.

**FL-5 — build-side gap, restating A6's own finding.** The Section 4 pre-flag block again did not
reach past section B: the place inside the section D quote body carried no token and one had to be
minted. Extending the pre-flag block across every section is what stops the scrubber minting at
all. This packet also shows a second, worse failure of the same block — see CD-1 — which is an
argument for verifying the block against a full-text sweep in the build, not only in the scrub.

## Recognition

This pass did place the company from the evidence in front of it. The brief says that is expected
and harmless, so it is recorded here as a flag and the identity is not written down in this file
or in the rater-facing packet. Nothing was searched for, and nothing outside the three files in
this folder was read.

## Content defects

Five recorded in `P-10_content_defects.txt`; none corrected. CD-1 is the one to act on — the
anonymization pre-flag block that the scrub pass is told to read is materially wrong about where
the identifiers are.
