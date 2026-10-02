status  : COMPLETE
company : P-16  Smartsheet   (started 2026-10-02 12:25 UTC, finished 2026-10-02 16:55 UTC)

## Run log

- 2026-10-02 12:25 UTC — Scheduled run fired. Connected folder: _build_env.
- Pre-flight: `packets/` confirmed EMPTY before start.
- Queue: took the topmost non-comment line of `to_be_researched.txt` = `P-16  Smartsheet`.
- Collector prompt: **Company_Culture_Evidence_Collector_v4.11.md** (the only `v*.md` present),
  read in full including the D1–D30 defect register and the change history.

## Company and queue state

- Built: **P-16 Smartsheet**.
- Remaining on `to_be_researched.txt` after this run: P-17 HCA Healthcare, P-18 Fifth Third
  Bank, P-19 Centene.

## Packet

- Path: `packets/P-16_smartsheet/P-16_packet.txt` (73,258 bytes).
- Collector version: v4.11. Model recorded in the BUILD RECORD: `claude-opus-5`.
- Terminal marker `########## END OF PACKET ##########` present as the final line.
- Blank-line parse check run against the raw build: **44 of 44 Section 1 excerpts parse** (no
  stacked bullets).

### Section-by-section excerpt counts (against the prompt's minimums)

| Section | Yield | Minimum / target | Verdict |
|---|---|---|---|
| A careers / values | 8 | 5 min, 8 max | PASS (at cap) |
| B employee reviews | 15 | 12 min, 15 target | PASS |
| C job postings | 10 excerpts from 4 postings, 4 functions | 6 excerpts / 3 postings / 1 outside engineering | PASS |
| D first-person | 7 passages from 2 sources | target 3 | PASS (ladder 7/7 rungs logged) |
| E recent news | 3 independent (+1 company-authored, tagged, uncounted) | target 2, max 4 | PASS |
| F human capital | 0 — N/A PRIVATE | ATTEMPT | N/A, recorded |

- B reviews inside the 24-month gate: 10 of 15. Median review age 22.0 months. Newest
  2026-08-27, oldest used 2024-06-27.
- Recency cross-check against the optional review source: does **not** fire materially. The
  required source's newest review is newer than the optional source's as returned by plain
  fetch and ~10 weeks older than the renderer's. No B1a-REMEDY fragments admitted.
- Two NOTE TO RATER blocks at the head of Section B: source truncation at 33.3% of the sample,
  and a September 2026 structural event postdating the newest review.

## Could not retrieve — three different findings, kept apart

**Did not exist**
- No public employee handbook or "how we work" documentation (ladder rung D1), after a full
  navigation-and-footer survey of the company site plus web search.
- No independent technical-conference talk by company engineers (rung D7). The only conference
  programming found is the company's own customer conference.
- No current 10-K Item 1 Human Capital disclosure (Section F): the company ceased to be an SEC
  reporting company in January 2025.

**Existed but was stale (found, dated, rejected on the 18-month gate)**
- Developer blog at developers.smartsheet.com/blog — newest post 2020-02-27.
- Long-form employer profile at builtin.com with a named engineering leader describing how the
  team works — 2018-05-04. The "right content, wrong vintage" case.

**Existed but could not be reached (or not quotably)**
- The careers page's interview-step panels. Plain fetch returned their text (assessment and
  coding-interview language, good decision-basis material); the rendered DOM never exposes it,
  including after clicking the panel controls. Withheld under the v4.11 renderer-confirmation
  rule rather than promoted from plain fetch.
- The session's own cloud container has **no general web egress** — its headless browser and
  direct-fetch routes were refused by the egress gateway with 403 on CONNECT for every host,
  including a control host. Treated as an organisation policy denial and not routed around.
  All renderer work ran in the browser pane on the operator's machine over the device bridge,
  which required a per-page-load access grant; on this run the grants were answered
  automatically and nothing stalled.
- `sec.gov/cgi-bin/browse-edgar` refused by the target's robots rules. Consistent with the
  prompt's dead-route finding; not needed, since the company is private.

## Defects I noticed in my own build

Full report is **Section 5** of the packet: **6 structural, 6 cosmetic, 2 environment notes.**
The structural ones, shortest form:

1. **S1** — hard rule 8 and B6 disagree about per-review star ratings. Collected into Section 1
   attribution lines, then removed all 15 and moved them to 2f on the stricter reading.
2. **S2** — B7's truncation detection assumes a "Show more" marker that the renderer does not
   print on this source, while v4.11 pushes the builder toward the renderer. The
   prompt-compliant path yields 0% truncation here and drops a required NOTE TO RATER. I
   measured it by character-length clustering across two renderer passes, cross-checked against
   plain fetch's marker positions.
3. **S3** — Section F's public/private binary has no state for a recently-public company.
   Marked N/A PRIVATE; recorded the fork because PE take-privates will recur on the roster.
4. **S4** — the `accessed` rule guarantees its own 8-of-8 finding and offers no vintage fallback.
5. **S5** — D0 bounds the extra-rung search on voice seniority and is silent on voice
   concentration; 5 of 7 D passages come from one article about one country's engineering team.
6. **S6** — *brief-level, not collector-level:* `to_be_researched.txt`, the one file every run is
   required to open, carries cross-run findings in its comment block (which poles are thin,
   which packet is weakest, what leans the roster expects). Read before its contents were known.
   No packet was opened and no other company influenced any collection decision. Cheap fix:
   move the commentary out of the queue file.

**D26 is confirmed present in this retrieval environment, not assumed** — four measured
instances of the plain-fetch layer altering text, including a single-for-double quotation-mark
substitution inside a review and silent removal of literal markdown a reviewer typed. Details in
2e. Nothing in Section 1 rests on plain fetch.

## List updates — confirmed done, in the required order

1. Appended to `to_be_scrubbed.txt`: `P-16	Smartsheet	researched 2026-10-02 (v4.11)` — done
   **after** the packet file existed on disk.
2. Then removed `P-16	Smartsheet` from `to_be_researched.txt`.

One company built. Open a fresh session for the next.
