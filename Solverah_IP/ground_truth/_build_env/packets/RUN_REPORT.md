status  : COMPLETE
company : P-15  Hudson River Trading   (started 2026-09-30 12:24 UTC · finished 2026-09-30 17:35 UTC)

## Selection
- `packets/` verified EMPTY before start.
- Took the topmost non-comment line of `to_be_researched.txt`: `P-15	Hudson River Trading`.
- Remaining on `to_be_researched.txt` after this run: P-16 Smartsheet, P-17 HCA Healthcare,
  P-18 Fifth Third Bank, P-19 Centene.
- Collector prompt used: **v4.11** (`Company_Culture_Evidence_Collector_v4.11.md`, the only
  `v*.md` file in the folder, as the README requires).

## Packet
- Path: `packets/P-15_hudson_river_trading/P-15_packet.txt` (59,085 bytes, 693 lines)
- Excerpts by section: **A 8 · B 5 · C 10 · D 4 · E 4 · F 0 — 31 total**
- Structural checks run against the built file: 31 bullets, **0** not preceded by a blank
  line (citation-harness requirement); terminal marker `########## END OF PACKET ##########`
  present as the last line; no Section 1 text points at a Section 2/3/4 artifact.

## Yield against the prompt's minimums
| section | minimum | got | verdict |
|---|---|---|---|
| A careers/values | 5 (max 8) | 8 | PASS (at cap) |
| B employee reviews | 12 | 5 | **FAIL — unreachable, see below** |
| C job-post excerpts | 6 (target 10) | 10 | PASS |
| C open postings | 3 | 4 | PASS |
| C outside engineering | 1 | 3 | PASS |
| D first-person | target 3 | 4 passages from 1 source | PASS on count, 1 voice only |
| E recent news | target 2 (max 4) | 4 from 2 sources | PASS |
| F human capital | attempt | N/A — private | correct absence |

**Why B cannot be fixed by collecting more.** The required review source holds **two**
reviews for this company worldwide. Tested three ways — the US profile, the same profile
with the country filter set to ALL, and the regional mirror — all return the identical two,
dated 2022-10-13 and 2017-12-13, and every count element on every page says 2. The recency
cross-check fired **materially** under B1a-REMEDY (optional source's newest review is 47.6
months newer; 0 of the 12-review minimum inside the 24-month gate), so up to 5 labelled
Pros/Cons fragments were admissible — but the optional source displays only **3 of its 119**
reviews to an anonymous reader and redirects page 2 onward to a sign-in with
`reason=bot-detection` in the query string. No sign-in was used, per the parity rule. Section
B is therefore 2 + 3 = 5, and the prompt's own remedy cannot reach the prompt's own gate.

## Could not retrieve — and which kind of finding each is
- **Existed but could not be reached:** the 2026-09-10 long-form founder profile (renderer
  returns headline, byline, date and two paragraphs, then a paywall; plain fetch refused by
  robots.txt). The 2025-10-31 leadership podcast transcript (gated behind registration). Pages
  2-40 of the optional review source (bot-detection sign-in wall). The European subsidiary's
  2022 regulatory PDF (not renderable, and stale anyway).
- **Existed but was stale:** the two blog posts that describe team practice directly, dated
  2022-08-02 and 2022-02-01 — precisely the on-axis material sections D and the
  collaboration/decision dimensions want. Recorded as found-and-rejected-on-age, not quoted.
  Note the 2022-08-02 post is *currently featured* as the "CULTURAL SPOTLIGHT" item on the
  company's live culture page.
- **Did not exist:** no public handbook or employee manual (site navigation and footer
  surveyed, not guessed). No company-attributed conference talk with retrievable text. No
  contribution guidelines or RFC threads on the confirmed code-repository organisation.
  No annual report with an Item 1 Human Capital disclosure — the company is private.
- **Reached by the other method after the first failed:** the trade-press article that carries
  three of four Section E excerpts would not render on the `.de` domain (returned a "System
  Maintenance" page) and rendered in full on `.com`. The four job-posting bodies were absent
  from plain fetch *and* from the rendered company page, and were only obtained by reading the
  ATS iframe `src` off the DOM.

## Defects in my own build
1. I cited the ATS embed URL for all 10 Section C excerpts rather than the company job page a
   human reader navigates to. The embed URL is where I confirmed the wording and it carries
   the text; the company page serves the same text inside an iframe. Defensible, but it puts
   a board slug and four numeric job tokens into Section 1's citation surface — the sharpest
   identifiers in the file. Flagged in Section 4. A later build may prefer the reverse.
2. Section A is at its cap of 8 and every one of the 8 is access-dated, because no page on
   this company's site publishes a date by either method. The rater learns nothing about
   Section A's vintage from Section A. Stated in 2f as the finding it is, but it does mean
   a third of the packet's excerpts have no source date at all.
3. Section D is 4 passages from a single voice. I worked five further rungs looking for a
   second in-date first-person account and found none. The concentration is real and is
   flagged to the rater in the Section 1 header, but a rater could reasonably call D a
   one-source section rather than a yielding one.
4. Three of four Section E excerpts come from one article. Flagged in 2e; the target of 2 is
   met on excerpts but only 2 independent sources exist behind them.

## Defects in the COLLECTOR PROMPT (v4.11) — structural first
### STRUCTURAL
- **S1 · Section B's minimum is unreachable when the required source holds fewer reviews than
  the minimum, and the prompt has no rule for that state.** B is [YIELD] tier: "A shortfall
  here is a research failure. Go back and collect more." Here the entire global population on
  the required source is 2, and B1a-REMEDY caps the supplement at 5, so the maximum Section B
  this prompt permits is 7 against a minimum of 12. The prompt's own remedy cannot satisfy the
  prompt's own gate, and nothing says whether such a packet ships, gets re-scoped, or is
  rejected. This determined what reached Section 1.
- **S2 · B1a-REMEDY's cap of 5 assumes the optional site will yield 5.** Anonymously it yields
  3 of 119 and walls the rest behind bot detection. The prompt gives no instruction for
  "remedy fires materially but the optional site yields fewer than the cap", and does not say
  whether to keep paginating (I did; walled at page 2). The binding constraint turned out to
  be the site's anonymous page-1 size, which the remedy never mentions.
- **S3 · Section C has no defined citation form when the posting body lives in a third-party
  ATS iframe.** The fallback chain's route 4 assumes the ATS board page renders the body. Here
  the board job URL *redirects back* to the company page, and the body is extractable only
  from an embed URL that is not a page anyone navigates to. Three URLs were defensible and the
  choice decides whether a citation harness can verify 10 of 31 excerpts. I chose and recorded
  it; the prompt should choose.
- **S4 · D0's trigger is undecidable when a first-person author's title is not published.**
  D0 mandates a bounded extra rung "if section D comes back 100% executive", and rule 3 wants
  "WHO is speaking" — but this blog names its authors and states no titles. Whether the
  trigger fired cannot be evaluated from the source. I recorded 0-confirmed-executive /
  1-employee-no-title and worked the extra rungs regardless, which is the safe reading, but
  the prompt makes a mandatory search conditional on a fact its own sources often omit.
- **S5 · The staleness gate is defined per RUNG; the problem on this build was a stale ITEM
  inside a current rung.** Rung 2 is current (newest post 2026-09), so the rung is not stale —
  yet the only two posts on it that describe working practice are from 2022. The gate's text
  ("if the newest available material on a rung is more than about 18 months old, treat that
  rung as stale and continue down the ladder") does not cover per-item rejection inside a live
  rung. I applied it per item by reading across from a different sentence elsewhere ("Check the
  publication date before quoting anything"). That call kept two rich collaboration and
  decision-basis passages out of Section 1, so it is structural either way it is resolved.

### COSMETIC
- **C1** 2a has no field for a Section B shortfall *reason*, nor for the optional source's
  anonymous-visibility limit, though B1a-REMEDY makes both load-bearing. Added as prose.
- **C2** 2c's ladder checklist has no field for "rung current but yields nothing on working
  practice" — an outcome the D-section prose explicitly names as a distinct finding. The free
  text `outcome:` absorbed it, so the distinction is invisible to a structured reader.
- **C3** 2f asks for "Newest careers-page modification date" as though a date will exist, in
  the same version whose rule-3 amendment establishes that it usually will not. The field
  should ask for a date *or* an access-dated count.
- **C4** The BUILD RECORD offers exactly two options — the exact model string, or
  `UNKNOWN — operator to fill`. This environment supplies a configured identifier and warns
  that the serving model may differ, which is a third state and more informative than either.
  I wrote the identifier with the qualification attached.
- **C5** The excerpt template has one URL field, but v4.11 requires recording the *confirming*
  route per excerpt, and on this build the discovery URL and the confirming URL differ for 14
  excerpts. `needed JS: Y/N` carries the method but not the route.
- **C6** 2f wants claimed/unclaimed per review entity; the required source does not display it
  on the rendered review page at all. Recorded NOT STATED.
- **C7** Section E bans "job aggregators" by site category rather than by content test. The
  only non-paywalled trade reporting on this company with substantive quotes runs under a news
  masthead that is also a job board — bylined reporter, date, original executive quotes. I
  treated it as reporting and recorded the call in 2e; a builder reading the category ban
  literally would have shipped a zero-yield Section E on a company that is actively covered.
- **C8** B2c steps 5-6 and B3b still read as live instructions to collect per-title subratings
  and run rating-block checks, in the same document that twice says they are no longer
  collected. "Retained only for the case in B2 above" is easy to read past.

**Freeze status: NOT triggered.** Five structural defects on this build.

## Environment / pipeline observations (not prompt defects)
- The browser required a **fresh site-access grant for essentially every page load** — a
  `scope: "site"` request was granted "for one use" each time — which roughly doubled the call
  count for a browsing-heavy build. Worth knowing before the next scheduled run.
- The MCP bridge to this device disconnected and reconnected around twenty times mid-run. No
  work was lost; every affected call succeeded on retry.
- **`packets/` was empty but `to_be_scrubbed.txt` still carried P-14's line.** Per that file's
  own header the harvest consumes the line *and* stages the packet, so the two signals
  disagree: the packet folder had been cleared while the line had not. Not a blocker under
  BUILD_BRIEF (which gates only on `packets/` being empty) and I proceeded, but flagging it in
  case the harvest half-completed on 2026-09-29.
- v4.11's D26 warning was confirmed twice on this build, both times on sources I would have
  quoted. On the trade-press article, plain fetch reported a pay figure of "£945,500" that
  appears nowhere on the rendered page (which says "over £900k"). On the blog post behind all
  four Section D passages, plain fetch returned three quotation-marked passages, two of which
  do not match the page — sentences merged, a capital introduced, a clause dropped. Both are
  written up in 2e with the rendered text alongside. **The renderer-confirmation rule earned
  its place on this build.**

## List updates — both confirmed done, in the prescribed order
1. Appended to `to_be_scrubbed.txt`: `P-15	Hudson River Trading	researched 2026-09-30 (v4.11)` ✔
2. *Then* removed `P-15	Hudson River Trading` from `to_be_researched.txt` ✔
Both performed only after the packet existed on disk.

One company built. Open a fresh session for the next.
