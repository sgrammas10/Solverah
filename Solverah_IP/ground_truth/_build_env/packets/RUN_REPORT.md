status  : COMPLETE
company : P-14  Crawford & Company   (started 2026-09-29 12:31 UTC, finished 2026-09-29 13:15 UTC)

## Selection

Took the topmost non-comment line of `to_be_researched.txt`: `P-14	Crawford & Company`.
Nobody named a company — this was a scheduled run with no operator awake — so the top line was
taken without asking, per the brief.

Remaining on `to_be_researched.txt` after this run, in order:
P-15 Hudson River Trading · P-16 Smartsheet · P-17 HCA Healthcare · P-18 Fifth Third Bank ·
P-19 Centene.

## Pre-flight

`packets/` was EMPTY at 12:30 UTC — verified with a recursive listing before anything else was
read. The harvest had cleared the previous night's P-13 packet. The connected folder held only
`BUILD_BRIEF.md`, one collector prompt, `README.txt`, `to_be_researched.txt`,
`to_be_scrubbed.txt` and the empty `packets/`. No other packet, handoff, decisions file or defect
log was present or read.

## Packet

Path            : `packets/P-14_crawford_and_company/P-14_packet.txt`  (87,718 bytes)
Collector       : `Company_Culture_Evidence_Collector_v4.11.md` — the only `v*.md` file in the
                  folder, read in full including the defect register (D1–D30) and the change
                  history.
Terminal marker : present as the last line (`########## END OF PACKET ##########`), as v4.11 now
                  requires.

Section-by-section excerpt counts, counted the way the citation harness counts them — a bullet is
only found when a blank line precedes it — by re-parsing the finished file:

| section | parsed excerpts | prompt minimum / target |
|---|---|---|
| A. careers / values | 8 | min 5, max 8 — AT CAP |
| B. employee reviews | 15 | min 12, target 15 — AT TARGET |
| C. job postings | 10 | min 6, target 10 — AT TARGET (4 postings, 4 distinct functions, min 3/1) |
| D. first-person | 7 (from 5 sources) | target 3 — 2.3x target |
| E. recent news | 4 (3 counted + 1 tagged company-authored) | target 2, max 4 — AT CAP |
| F. human capital | 6 | target 3, max 6 — AT CAP |
| **total** | **50** | |

All 50 parse. Nothing is lost to the stacked-bullet defect (v4.9 / D-item on P-08). Verified
programmatically, not by eye.

Every gate in the required-to-yield audit passed. 15 of 15 reviews sit inside the 24-month gate.

## What could not be retrieved, and what was done instead

Distinguishing the three cases the brief asks to be kept apart:

**EXISTED BUT COULD NOT BE REACHED**
- Glassdoor's date-sorted review listing. Plain fetch was refused by robots.txt; the renderer was
  bot-walled to a Cloudflare interstitial within two minutes of the renderer working fine on
  Indeed. Both halves of defect D13 in one source. Worked around: the UNSORTED Glassdoor reviews
  path *is* allowed by robots and returned the newest review date (2026-07-05) and a count by
  plain fetch, which is all the optional recency cross-check needs. Nothing from Glassdoor
  entered Section 1 and the plain-fetch-only status is flagged in 2f.
- Glassdoor's work-life-balance subscore — not retrievable by either method, so cross-site
  work/life divergence could not be recorded this build. Said so in 2f rather than leaving the
  line blank.
- The company's global code of business conduct. PDF only; the renderer exposes no text for PDFs
  and no HTML rendition exists. Nothing was load-bearing in it, so option two of v4.11's
  three-option fallback was taken: recorded as *found but not quotably retrievable*, quoted
  nowhere. Same outcome the prompt records for P-11, reached the same way.
- `sec.gov/cgi-bin/browse-edgar` — dead, as the register says, but by a different failure mode
  (robots refusal, not an empty document). Logged as a cosmetic defect. Worked around with the
  route the prompt prescribes: resolve the document URL by search, fetch the archive document
  directly. That worked first try.

**EXISTED BUT WAS STALE**
- The public repository organisation at the obvious handle: one repository, last touched
  2017-03-13, no bio, no public members — so it also cannot be confirmed as the subject rather
  than a name collision. Recorded as found-but-stale-and-unconfirmed, not as absent.
- The blog's employee-spotlight strand carries 2018-dated items, surfaced only via the site's
  "related posts" rails. Rejected on age and recorded as rejected, per D0(3) — "the company
  publishes exactly this material and some of it is eight years old" is a different finding from
  "no employee stories exist". The strand also carries current items, which is what yielded.

**DID NOT EXIST**
- No public employee handbook, manual or "how we work" documentation, after a navigation survey
  of the About and all four careers pages plus two searches.
- No long-form press profile with direct employee or executive quotes beyond the trade interview
  already credited to ladder rung 4. Searches returned company-profile databases, review sites
  and an encyclopedia entry — none of which is reporting and none of which may be quoted.
- No published conference talk, session or transcript. The company maintains current event pages,
  but they describe *exhibiting*: "Crawford is exhibiting at the NAMIC Claims Conference". Rung
  found, current, yields nothing — a third distinct outcome, recorded as such.
- No layoff, site-closure or return-to-office event in twelve months, across five logged searches
  with different phrasings.

One retrieval finding worth carrying forward, because it is the reverse of what the prompt's prior
predicts: **the renderer was not walled on the review aggregator at all.** It returned every review
page in full, including the literal `...Show more` markers, which is the only reason truncation
could be measured. Plain fetch also worked, and the two methods agreed on the review list, dates,
titles and locations. Two independent renderer passes over the same page were byte-equivalent
including every truncation marker — unlike P-11 (D28), the two passes agreed. And on the one source
where plain fetch and the renderer could be compared sentence-for-sentence (the 10-K human-capital
section), plain fetch's rendition matched the rendered text except for a dropped trademark symbol
and normalised apostrophes. **No fabricated quotation marks on this build.** That is a negative
result on D26, not a refutation of it: the renderer was still the confirming route for all 50
excerpts.

## Defects noticed in this build

Four structural, five cosmetic. Full text with reasoning is in the packet's Step 5 list; the
headlines:

STRUCTURAL
1. B0 has no rule for a review that may belong to the SUBJECT but sits on a third party's pooled
   profile — the mirror image of D23. Found one: a 2026-08-19 "Property Adjuster — Remote" review
   on a profile otherwise belonging to an Illinois mechanical contractor. Had it been collectable
   it would have been the second-newest review in the merged set. Excluded and recorded.
2. B0's "collect from all entities" and B2's "company-wide" frame give no test for whether a
   subsidiary brand's profile is an entity OF the company. Reading it inclusively put 7 of the 15
   reviews in Section 1 and moved the oldest review used forward by five months. Reading it
   narrowly would have produced a different, older section B that still passed every gate.
3. D0's two voice categories cannot classify what this ladder yielded — unsigned corporate voice,
   unsigned practitioner voice, and company-written third-person profiles of named non-executive
   employees. The 2a audit line has two boxes; the number that goes in them is a judgment the
   packet cannot show, so a four-way split was recorded alongside it.
4. Section A's required source publishes the company's core value framework as an IMAGE, and the
   prompt has no instruction for dimension-bearing content that exists only as non-text. The
   framework was recoverable only because the 10-K spells it out — i.e. via section F, which
   exists only for public companies. A private company with the same site design would have this
   recorded as absent.

COSMETIC
5. Indeed's `fcountry=US` parameter is inert on these profiles — filtered and unfiltered pages
   returned identical sets including a Chile review. B2c hands the builder that URL as if it
   filtered.
6. `browse-edgar`'s failure mode differs from the register's description (robots refusal vs empty
   document).
7. The renderer's element-search tool truncates node text at ~100 characters, so v4.11's
   phrase-by-phrase renderer confirmation cannot be done that way on a large document; the
   renderer's full page text had to be extracted instead. Called cosmetic because it changed no
   evidence, but flagged as a judgment.
8. Section E's company-authored rule does not say how to treat a company statement quoted inside
   independent reporting. Tagged and not counted; another builder could reasonably count it.
9. Section C's "do NOT quote or report job titles as a group" is ambiguous about single titles.
   Function labels only were used.

The freeze does not trigger: four structural defects.

## Decisions made without asking, per Step 3

Recorded here as well as in the packet, because each is a place the prompt did not decide:
the entity set treated as "the company" (defect 2); excluding the confirmed off-company review
and taking the next in date order (D23, applied as written); retaining-but-not-collecting the
possibly-subject review on a third party's profile (defect 1); the D voice classification
(defect 3); four job postings rather than the minimum three; and mapping the industry bucket,
which is flagged in Section 3 as a genuine mapping problem rather than resolved.

## List updates — both confirmed done, in the required order

1. `to_be_scrubbed.txt` — APPENDED, first:
   `P-14	Crawford & Company	researched 2026-09-29 (v4.11)`
   (tab-delimited, matching the P-13 line's convention; verified with `cat -A`)
2. `to_be_researched.txt` — the `P-14	Crawford & Company` line REMOVED, second, and verified
   absent afterwards. The five later entries are intact and unreordered.

Both steps ran only after the packet file was confirmed on disk at its final size.

The comment block above the removed line still refers to "P-13/P-14 above" and is now stale in
that respect. It was left untouched: the brief says to remove the company's line, and rewriting
the operator's own hand-maintained commentary is not this task's job. Worth a human's eye.
