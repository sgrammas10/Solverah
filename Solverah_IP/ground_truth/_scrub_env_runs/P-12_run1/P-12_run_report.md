# Run report — P-12

**Packet scrubbed:** P-12 (`P-12_packet.txt`, build v4.11, model claude-opus-5, built
2026-09-17). Confirmed exactly one packet in `packets_raw/` (ignoring `.gitkeep`) before
starting.

**Method:** edited a copy of the raw file programmatically (Python string/regex
substitutions targeting only the exact identifier tokens named below), never retyped any
quote body. Every substitution was verified by an automated count check before being
applied (asserting the target string occurred exactly once at that location), and the
final output's quote bodies were diffed against the raw file's quote bodies
programmatically — 8 of 52 differ, exactly the 8 declared edits below, byte-identical
otherwise (including the one non-breaking hyphen in section A, preserved as U+2011).

## Self-check results (all 13)

1. `http` appears zero times in the output. **PASS** (0 occurrences, whole file).
2. The company name and its short form appear zero times outside a bracketed
   substitution. **PASS** ("Duke" / "Duke Energy" / "Duke Energy Corporation": 0
   occurrences anywhere in the output file, in or out of brackets — every instance was
   either removed from attribution or replaced with `[the company]`/`[The company]`).
3. Every review is referenced as `rev-NN`, same review always gets the same id.
   **PASS** (rev-01 through rev-15, each appearing exactly once, assigned in the section's
   own most-recent-first order; the source site gave no per-review URL to derive ids from,
   so ids were assigned positionally).
4. Every quote body is character-identical to the raw packet except where a bracketed
   declaration says otherwise, verified by diff not by reading. **PASS** — programmatic
   diff of all 52 quote bodies against the raw file found exactly 8 differences, all 8
   declared.
5. Every substitution is declared on its own excerpt line. **PASS** for quote-body edits
   (8/8 declared). Routine attribution stripping (company name + URL, per R1; named
   humans + the "illumination" brand in attribution, per R3/A5) is not separately declared
   line-by-line, consistent with R1's own worked example in the ruleset, which shows the
   "after" attribution with no bracket — declaring the baseline attribution transform on
   all 52 lines would be noise, not signal, and Rule Two's own examples (A4's "Executive
   Speaker series" and "Ethan said") are both quote-body edits, not attribution edits.
6. Excerpt count matches the raw packet, section by section. **PASS** — see table below.
7. Source typos still present and still misspelled. **PASS** — all five preserved
   verbatim: "Mico [sic]", "lie about to to [sic]", "ca ena [sic]", "Allt [sic]",
   "Mangerwas [sic]", plus the unmarked "porting" typo in the C excerpt.
8. `Remote` still literal wherever the raw packet had it. **N/A** — the string "Remote"
   does not occur anywhere in this packet (checked both cases); nothing to preserve.
9. Job titles and sector language untouched. **PASS** — spot-checked every job title
   (Work Management Specialist, Associate Customer Care Specialist, Customer Service, Gas
   fitter, Business Service Representative, Instrumentation Technician, Lead IT Security
   Analyst, Associate Distribution Dispatcher, drone pilot, operations supervisor, etc.)
   against the raw file; none were altered or softened.
10. The diff file exists and contains every changed line. **PASS** — `P-12_scrub_diff.txt`
    (raw line above, scrubbed line below) for all 52 changed section-1 excerpt lines, plus
    the header-block reformatting.
11. Both markers present and literal; header carries `build vX.Y`; scrub log sits after
    `########## END OF PACKET ##########`. **PASS** — verified programmatically
    (`########## SECTION 1` and `########## END OF PACKET ##########` both present
    literally; header contains "build v4.11"; the scrub log's first content line is at
    file line 158, two lines after the END OF PACKET marker at line 156).
12. Every excerpt bullet has a blank line directly above it. **PASS** — checked
    programmatically over every line in the output preceding a bullet; zero bullets
    lacked a blank line above them. The raw packet already had this property throughout
    (unlike the P-07 case the brief describes), so no section needed repair.
13. Per-section bullet table, counted vs. each section's own header count:

    | Section | Bullets counted | Header says | Result |
    |---|---|---|---|
    | A — Careers/Values | 8 | "5-8 excerpts" (cap 8) | match, at cap |
    | B — Employee Reviews | 15 | "12-15" | match |
    | C — Job Postings | 11 | "6-10 excerpts from 3+ open postings" | 11 counted against a stated ceiling of 10 — see note below |
    | D — First-Person Account | 8 | "yield: 8 passages from 3 sources" | match |
    | E — Recent News | 4 | "yield: 4" | match |
    | F — Human Capital Disclosure | 6 | "yield: 6" | match |

    Note on C: the section header's own range, "(6-10 excerpts from 3+ open postings,
    different functions)", caps at 10, and the actual count is 11 — one over that cap, the
    same shape of disagreement the brief's own P-07 example describes ("section E header
    declares two excerpts and the section holds four"). Per the brief, this is not fixed
    either way; it is recorded as a content defect (see `P-12_content_defects.txt`) and the
    header is reproduced verbatim above, unchanged.

## Judgment calls and things flagged rather than decided

All recorded in `P-12_content_defects.txt` (pre-flag vs. sweep disagreements) and in the
scrub log appended inside `P-12_packet_ANON.txt` (rule-by-rule counts and the reasoning
behind each judgment call: the header status field, the E2 spending figure, the E3 place
names, Harry Sideris's title, TICR, A8/A9/A7/the OPEN reviewer-re-id item, and the decision
to leave every date untouched). Not repeated here to avoid the two logs drifting apart —
see those files for the full reasoning.

## Residual re-identification risk (flagged, not resolved)

Section 4 is correct that section E is high-risk even after scrubbing: a six-state
electric-and-gas utility undergoing a regulator-approved combination of two Carolinas
subsidiaries effective 2027-01-01, spending at a large and accelerating pace on grid
capacity, is a narrow enough combination of facts that a rater already familiar with the
utility sector may place the company from E alone. No rule in the ruleset authorises
removing or vaguing the dates themselves (they are the load-bearing recency information
R1 is built to protect), so this was left as-is and is recorded here rather than resolved
unilaterally, per the brief's instruction not to resolve a ruleset gap on my own initiative
without saying so.

## Recognition flag

Enough company-authored language survived scrubbing (utility-sector job families, a
six-state footprint, a 10-K human-capital disclosure, a drone/lineworker storytelling
publication, an approved Carolinas-subsidiary combination) that the underlying company was
identifiable to me during this pass. Recording that here per the brief's instruction
("If you recognise the company, that is expected and is not a failure — record it... and
keep scoring from the evidence in front of you") — no company name, executive name, or
other identifier was searched for; recognition came from the evidence already in the
packet.

## Files produced

- `packets_out/P-12_packet_ANON.txt` — the de-identified, rater-facing packet plus its
  scrub log (log sits after `########## END OF PACKET ##########`).
- `packets_out/P-12_scrub_diff.txt` — raw line above, scrubbed line below, for every
  changed line.
- `packets_out/P-12_content_defects.txt` — pre-flag/sweep disagreements and a statement
  that no other content defects were found.
- `packets_out/P-12_run_report.md` — this file.

No stray intermediate files were left in `packets_out/`; working files were kept in this
session's own scratch directory on the device, outside the connected folder, and are not
part of the deliverable.
