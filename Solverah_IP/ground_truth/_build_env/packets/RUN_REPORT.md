# RUN REPORT — P-11 Regeneron

**Run date:** 2026-09-08 (scheduled, unattended)
**Collector prompt version used:** v4.10 (`Company_Culture_Evidence_Collector_v4.10.md` — the only
v*.md present in the build folder, so no stale-copy risk on this run)
**Model:** claude-opus-5 (session-configured identifier; serving model cannot be confirmed from
inside the session)
**Pre-flight:** `packets/` was EMPTY before the build. Build folder contained only BUILD_BRIEF.md,
the single collector prompt, README.txt, the two lists and the empty `packets/` directory. No
handoff, decisions file, defect log or other company's packet was present, offered or read.

## Company taken

Topmost non-comment line of `to_be_researched.txt`: **`P-11    Regeneron`**.

**Remaining on `to_be_researched.txt` after this run:** one line — `P-12    Duke Energy`.

## Packet

**Path:** `packets/P-11_regeneron/P-11_packet.txt` (59,531 bytes)

**Section-by-section excerpt counts** (verified programmatically against the blank-line-delimited
bullet rule from v4.9, which is what the citation harness parses):

| Section | Excerpts | Minimum | Status |
|---|---|---|---|
| A. Careers / values | 7 | 5 (max 8) | PASS |
| B. Employee reviews | 15 | 12 (target 15) | PASS |
| C. Job postings | 11 | 6, from 3+ postings | PASS — 4 postings, 4 functions |
| D. First-person | 4 (from 3 sources) | attempt only | yielded |
| E. Recent news | 2 | attempt only, target 2 | yielded |
| F. Human capital | 6 | attempt only, target 3 (max 6) | yielded |
| **Total** | **45** | | |

**Parse check:** all 45 excerpt bullets are preceded by a blank line — 0 stacked bullets. Section 1
contains 0 pointers into Sections 2/3/4. Both checks were run as a script rather than by eye.

**Other gates:** B recency 15/15 within the 24-month gate; median review age 5.6 months; C outside
engineering 3/1; D ladder 7/7 rungs logged; achievability gate run, 0 percentages anywhere in the
packet; no C exemption claimed (603 open roles rendered).

## Could not retrieve, and what was done instead

1. **FY2025 10-K Item 1 Human Capital — plain fetch failed, renderer succeeded.** The filing is a
   single 3.1MB document and the plain-fetch route truncated at the same point (start of Government
   Regulation) on the FY2025 10-K, the FY2024 10-K and the Annual Report PDF wrapper — three routes,
   systematic, not incidental. The JS renderer returned all 594,386 characters and the section was
   extracted complete. **Section F would have been recorded as NOT ACCESSIBLE under a single-method
   build.** This is defect D13 firing exactly as the register predicts.
2. **Times Union coverage of the Saratoga expansion — `ROBOTS_DISALLOWED`.** Not retrieved by any
   means. Classified as *existed but could not be reached*, not as an absence.
3. **Rome Sentinel coverage of the same event — HTTP 429.** Also *could not be reached*. A third
   outlet covering the same event (FingerLakes1.com) was reachable and was used, so section E did
   not lose the event.
4. **Code of Business Conduct and Ethics (D ladder rung 1) — found, current, deliberately not
   quoted.** The PDF contains real working-practice language, but it could only be read through the
   summarising plain-fetch layer, and the renderer exposes no text for PDFs. Given item 1 in the
   defect list below, unverifiable quotes were withheld rather than shipped.
5. **Conference talk (rung 7) — exists but is future-dated (2026-10-20) and login-gated.** Not
   signed in, per the parity rule.
6. **Press profile (rung 6) — found and rejected on age (2018-01-16).** Recorded as
   found-and-rejected rather than absent.

## Defects I noticed in my own build

**STRUCTURAL — 1. The plain-fetch retrieval layer fabricated quotation marks.** Asked for direct
quotations from the Pharmaceutical Executive article, it returned a clause wrapped in quote marks
and attributed to the named CEO. The rendered page contains that clause in *reported speech, with no
quotation marks anywhere*. It is the reporter's sentence. Shipped, it would have been a fabricated
verbatim quote attributed to a named living executive, and it would have passed a URL-level
fact-check by anyone not looking specifically for the quotation marks. **Every Section 1 excerpt was
consequently re-retrieved through the renderer and confirmed character-for-character.** A milder form
of the same failure hit the job postings: bullet lists came back verbatim, overview paragraphs were
silently rewritten, and several bullets lost their closing clauses. This is a property of the
environment rather than of the prompt, but it is structural because it changes what reaches Section 1.

**STRUCTURAL — 2. Two passes over the same review page disagreed about truncation.** Pass one showed
no truncation markers; pass two reported an expansion control on 12 of 21 reviews. The renderer
settled it (7 of the 15 used = 46.7%, which crosses B7's one-third threshold and triggered a NOTE TO
RATER). Had the first pass been trusted, the packet would have asserted zero truncation and omitted
the note.

**STRUCTURAL — 3. The renderer was NOT bot-walled on the review aggregator.** v4.10 states
plainly that "review and job aggregators are server-rendered and aggressively bot-defended" and that
"the renderer gets redirected to a sign-in wall". On this company it returned the full review page
including the literal `...Show more` markers — which is what made defect 2 resolvable. The guidance
is a useful prior, not a rule, and a builder who follows it as written will not attempt the renderer
on an aggregator and will lose the truncation measurement.

**COSMETIC — 4. Hard rules 3 and 7 cannot both be satisfied for an undated first-party page.** Rule 3
requires a date on every excerpt; rule 7 forbids hiding age. The careers culture page and its two
named testimonials publish no date by either retrieval method. I dated them by access date and marked
them as such. The prompt does not say whether "date" means publication or access date for undated
first-party pages, and section A depends on such pages in essentially every build.

**COSMETIC — 5. Section D's yield unit is ambiguous.** D asks for "3 substantive passages" but the
audit line reads "D passages: ___". I took two passages from one article plus two testimonials and
reported it as "4 passages from 3 sources" rather than choosing silently between 3 and 4.

**COSMETIC — 6. The double-counting rule needed a judgment call.** One URL supplies six of seven A
excerpts *and* both named testimonials used in D. The prompt's rule bars counting the *same* text
twice; these are distinct blocks on a shared page. I counted them separately and recorded the
decision in 2c/D3 rather than resolving it verbally.

**COSMETIC — 7. Posting dates on this careers site are template metadata.** Two unrelated
requisitions both reported "Published July 15, 2022; last modified April 29, 2024". No posting date
is used anywhere in the packet; postings are dated by confirmed-open-on date.

**Note on the freeze rule:** this build surfaced three defects I classified as STRUCTURAL, so it does
**not** trigger the freeze. Where genuinely torn I called it structural, per the brief.

## List updates — both confirmed done, in the required order

1. **Packet written to disk first** and verified present (59,531 bytes) before either list was touched.
2. **`to_be_scrubbed.txt`** — appended: `P-11	Regeneron	researched 2026-09-08 (v4.10)` ✅
3. **`to_be_researched.txt`** — line `P-11    Regeneron` removed, and only then ✅

Verified after the fact: `to_be_scrubbed.txt` contains exactly one P-11 line; `to_be_researched.txt`
contains no P-11 line and retains `P-12    Duke Energy`.

---

**One company built. Open a fresh session for the next.**
