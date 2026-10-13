status  : COMPLETE
company : P-17  HCA Healthcare   (started 2026-10-03 ~23:15 UTC, finished 2026-10-04 ~01:10 UTC)

---

QUEUE
  Took the topmost non-comment line of to_be_researched.txt: "P-17  HCA Healthcare".
  Remaining on that list after this run: P-18 Fifth Third Bank, P-19 Centene.
  Gate: packets/ was EMPTY at the start of the run. Checked and confirmed before anything else.

  Clock note: the two shells in this environment disagreed about the date at start of run (one
  reported 2026-10-03 12:15, the other 2026-10-04 00:48 UTC). The authoritative session date is
  2026-10-04 and every access date in the packet uses it.

COLLECTOR VERSION
  v4.11 (Company_Culture_Evidence_Collector_v4.11.md). Exactly one v*.md file was present, as the
  README requires. Read in full, including the D1-D30 defect register.

PACKET
  packets/P-17_hca_healthcare/P-17_packet.txt   (63,122 bytes)
  Section 1 parses to 50 blank-line-delimited excerpts, verified with a harness-equivalent split:
      A careers / values      8   (minimum 5, maximum 8 - at the cap)
      B employee reviews     15   (minimum 12, target 15 - at target)
      C job postings         10   (minimum 6, target 10 - at target; 3 postings, 3 functions,
                                   2 of them outside engineering)
      D first-person          8 passages from 3 sources   (target 3)
      E recent news           4   (3 independent + 1 company-authored, tagged, not counted)
      F human capital         5   (target 3, maximum 6)
  Terminal marker present as the last line. BUILD RECORD present as the first block.
  No Section 1 excerpt points at a Section 2, 3 or 4 artifact.

TWO RETRIEVAL METHODS
  Available: the plain-fetch tool and a JavaScript renderer (the browser pane). Both were attempted
  on every source that mattered. Two other routes were tried first and are unavailable here: direct
  HTTP from the cloud side (the session egress policy refused CONNECT to every target host) and a
  locally driven headless browser (that shell has no network at all).
  The renderer is the confirming route for all 50 Section 1 excerpts, per v4.11's rule that plain
  fetch is a route to a page and not an authority on its wording.

NOT RETRIEVED - and the three states kept apart
  DID NOT EXIST
    - No engineering or product blog. The company publishes one general-interest newsroom; there is
      no technical publication.
    - No contribution guidelines, RFC threads or public discussions on the repository organisation.
    - No technical conference talk by a named colleague, across two differently-phrased searches.
      The only conference presence found is investor conferences announced by press release.
    - No publication or modification date on any careers page, by either method. All 8 section A
      excerpts are access-dated as a result, and the packet says so.
  EXISTED BUT STALE
    - Nothing. Every ladder rung that yielded anything yielded material inside the 18-month gate,
      and no non-executive first-person material was found and rejected on age.
  EXISTED BUT COULD NOT BE REACHED
    - The optional review site's overall and category ratings. The renderer returned only the
      article element holding the newest review, which is all the recency cross-check needs, so
      2f's cross-site rating-divergence field is incomplete. Recorded, not guessed.
    - The regulator's browse-edgar endpoint, refused by robots rules at every variant - register
      D16 again, by a different mechanism than the empty documents previously recorded. Worked
      around with the direct archive-document route, which succeeded.
    - Plain fetch was refused by robots rules on the optional review site, the company's own job
      search and that regulator endpoint. The renderer reached all three.
    - A trade-press article returned an empty article element on the first renderer pass and the
      full interview on the second, with no error between. Two Section E excerpts exist only
      because I retried. Logged as a structural defect.
    - Per-hospital review entities. The review site splits this employer across a company-level
      profile, regional-brand profiles and a profile per individual hospital; four per-hospital
      profiles turned up from two searches against a company operating 190 hospitals. I did not
      merge them. Section 1's reviews come from the company-level profile only, the split is
      recorded with counts, and the choice is logged as a structural defect.

NOTABLE FINDING FROM THIS BUILD
  Three of the twenty most recent reviews on the required source are written by employees of an
  unrelated Georgia hospital system whose name collides with one of this company's own Florida
  facilities. All three name that other employer in their own text; the other system was confirmed
  externally as a separate non-profit entity; all three were excluded. A fourth, from the same
  region but naming no employer, is retained and flagged inline. The same profile's job-title index
  separately lists retail, hospitality and domestic job titles that fit no hospital operator, which
  corroborates that the pooling is a property of the profile rather than an incident. This is
  register D23 at population scale rather than as a single review.

PROMPT DEFECTS SURFACED: 7 structural, 7 cosmetic. The freeze condition is NOT met.
  Full text is in the operator handback. Structural, in short:
    S1  B0's entity check has no termination rule when a review site splits an employer by
        individual facility; it is unachievable as written at 190 hospitals.
    S2  B0's off-company remedy is written for a single pooled review and gives no handling for a
        confirmed population-level contamination rate.
    S3  B0's homonym check assumes the colliding name is external to the company; here the company
        owns a facility carrying it, so the name alone does not discriminate.
    S4  Rule 6's date-order rule, the 15-review cap and the off-company exclusions interact to drop
        current on-axis evidence, and the prompt does not say whether exclusions are backfilled.
    S5  The retrieval environment grants one page load per approval; the prompt's seven- and
        five-rung proof-of-absence ladders are specified as if retrieval were free.
    S6  v4.11's renderer-confirmation rule has no procedure for a page the renderer returns empty
        on one pass and in full on the next. D28's two-pass requirement covers truncation only.
    S7  Section F's "rewrite the proper noun" rule contradicts both the instruction to keep real
        names until anonymization and hard rule 2.

DEFECTS IN MY OWN BUILD
  1. Transcribing through tool output, I first wrote one section A excerpt with a straightened
     apostrophe and two section C excerpts with curly quotation marks the rendered page does not
     carry. Caught and corrected before assembly, but this is the same class of failure as D26 with
     me as the layer rather than the tool, and it argues for writing excerpts from the rendered text
     mechanically rather than by hand.
  2. I wrote "41 Section 1 excerpts" into the fidelity note when the true count is 50. Caught by
     the verification pass and corrected.
  3. Section A sits at its maximum of 8 while two of the eight carry little on-axis content. A
     tighter build would have spent those slots on the corporate culture-and-values page.
  4. I left the optional review site's rating block unread as a deliberate economy, which leaves a
     real gap in the vintage block rather than a recorded absence of data.
  5. Feedback is marked THIN and I considered marking it COVERED. The reason line in 2b states the
     base it rests on so the call can be re-judged downstream.

LIST UPDATES - both done, in the prescribed order, after the packet was confirmed on disk
  1. DONE  appended to to_be_scrubbed.txt:  "P-17<TAB>HCA Healthcare<TAB>researched 2026-10-04 (v4.11)"
  2. DONE  removed "P-17<TAB>HCA Healthcare" from to_be_researched.txt (exactly one line matched)
  Verified after the fact: the scrub line is present, and the research list now holds P-18 and P-19.

One company built. A fresh session is required for the next.
