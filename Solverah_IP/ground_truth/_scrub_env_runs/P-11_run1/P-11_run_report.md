# Run report — P-11

**Packet scrubbed:** P-11 (the single packet present in `packets_raw/` this session; no other
packet was seen, read, or requested).
**Ruleset applied:** `ANONYMIZATION_RULES_DRAFT.md`, signed off 2026-08-15, amended through
the P-09 amendments (A8, A9), 2026-09-07.
**Scrubbed:** 2026-09-16.
**Outputs written:** `P-11_packet_ANON.txt`, `P-11_scrub_diff.txt`, `P-11_content_defects.txt`,
this file.

## Per-section bullet table (self-check 13)

| Section | Bullets counted | Header declares | Result |
|---|---|---|---|
| A — Careers/values | 7 | 5–8 excerpts | match (within range) |
| B — Employee reviews | 15 | 12–15 | match (at ceiling) |
| C — Job postings | 11 | 6–10 excerpts | **mismatch — exceeds declared range by 1.** Not corrected; recorded in content-defects file #8, header reproduced verbatim. |
| D — First-person account | 4 | yield: 4 passages | match |
| E — Recent news | 2 | yield: 2 | match |
| F — Human capital disclosure | 6 | yield: 6 | match |
| **Total** | **45** | — | 45 preserved from raw packet exactly, no excerpt added or dropped |

## Self-check results (all 13, run against the final scrubbed packet)

1. `http` appears zero times in the output. **PASS** (verified programmatically).
2. The company's name and short forms appear zero times outside a bracketed substitution.
   **PASS** — zero raw occurrences of "Regeneron"/"regeneron" anywhere in the scrubbed packet,
   verified programmatically over the full assembled file (packet + log).
3. Every review is referenced as `rev-NN`, same review always gets the same id. **PASS** — 15
   reviews, rev-01 through rev-15, each assigned once, by date order (most recent first, matching
   the raw packet's own order), no reuse.
4. Every quote body is character-identical to the raw packet except where a bracketed
   declaration on that line says otherwise. **PASS**, verified by diff (not by reading): every
   excerpt line was diffed programmatically against the raw packet's corresponding line, quote
   span isolated from the attribution span, and only the 12 excerpts listed as changed in
   `P-11_scrub_diff.txt` show any character difference inside the quote itself; all 12 carry a
   bracketed declaration.
5. Every substitution is declared on its own excerpt line, not only in the log. **PASS** — see
   the scrub log's rule-by-rule counts; every one of the 12 quote-body edits, the 4 source-tag
   value-name edits, and the 8 attribution-only location-token edits carries its own bracketed
   declaration on the excerpt line, in addition to being summarised in the log.
6. Excerpt count matches the raw packet, section by section. **PASS** — see table above (one
   section's *header* disagrees with its own count, which is a build defect, not a scrub
   miscount — see content-defects #8).
7. Source typos are still present and still misspelled. **PASS** — none of the typo-bearing
   lines were among the 12 lines with quote-body edits; verified by diff that those lines are
   byte-identical to the raw packet.
8. `Remote` is still literal wherever the raw packet had it. **N/A** — the word "Remote" (as a
   location/work-mode value) does not occur anywhere in this packet's Section 1, so there is
   nothing to preserve. Recorded rather than silently skipped.
9. Job titles and sector language are untouched. **PASS** — no job title, department name, or
   industry term was edited; the only lexical edits inside quote bodies are the twelve listed
   above (company name, one branded/internal term rewrite, one internal-team rewrite, one
   location token, two figures).
10. The diff file exists and contains every changed line. **PASS** — `P-11_scrub_diff.txt`
    contains all 45 excerpt lines that differ from the raw packet (every excerpt lost its URL at
    minimum under R1), raw above scrubbed, plus the minted-token map.
11. Both markers present and literal, header carries `build vX.Y`, scrub log sits after
    `########## END OF PACKET ##########`. **PASS**, verified programmatically: the header
    contains the literal string `build v4.10`; the section marker and end marker are byte-
    identical to the raw packet's own marker lines; the scrub log begins after the end marker.
12. Every excerpt bullet has a blank line directly above it. **PASS**, verified programmatically
    line-by-line over the assembled Section 1 text — zero violations, in the raw packet already
    and preserved through every edit.
13. Per-section table: see above. One disagreement found (Section C), reported rather than
    corrected, per instruction.

## Judgment calls made (also logged in the packet's own scrub log)

- Figures that are not headcount/dollar/percentage (E1's "six major therapeutic areas," D3's
  "3.5 months," "six years of experience") were left as signal, not treated as R6 figures.
- State-level geography ("New York") was kept literal as population/dispersion context, distinct
  from the city/site-level strings that were tokenised.
- Third-party/industry-standard names (the J.P. Morgan Healthcare Conference; SOPs, GxP) were
  kept as retrieval-method/industry signal, not company fingerprints.
- "Safety Sciences Strategy" (C11) was de-branded under R4/A5 even though Section 4 never
  flagged it — applying an existing rule to a pre-flag miss, not extending a rule to a new case.

## Things flagged rather than decided

- Nothing required stopping — no ruleset conflict was encountered on this packet, and no
  decision beyond the judgment calls above was needed. The eight items above item are pre-flag
  block accuracy problems in the raw packet/build, not open scrub decisions; they are recorded
  in `P-11_content_defects.txt` per the brief's instruction to report where sweep and block
  disagree, and were not corrected in the packet itself.
- The reviewer-level re-identification question left OPEN in the ruleset (P-09's near-unique
  review titles) does not arise in this packet: none of P-11's Section-1 excerpts print a review
  headline/title field at all (the Indeed source used here yields body text only), so there is
  nothing on that axis to flag.

## Rule Zero

Exactly one packet (P-11) was present in `packets_raw/` this session and exactly one was
scrubbed. No other packet was opened, requested, or referenced.
