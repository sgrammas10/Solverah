# Packet feasibility tracks company type, not culture

_From the P-03 (Akuna Capital) pilot build, 2026-08-10._

## What happened

P-03 passes sections A, B and C of v4.1 and fails D and E outright. The failures are not retrieval
laziness — the full ladder was worked and every rung is logged. They are structural:

- **No blog, no handbook.** A private proprietary trading firm publishes nothing about how it works.
- **Zero public repositories.** The GitHub org exists and is empty.
- **The only leadership interview is nine years old.**
- **No credible reporting in 12 months.** A firm with no investors, no earnings calls and no
  regulatory disclosure obligations generates almost no press. What surfaced instead was
  recruiting SEO, interview-prep sites and aggregators.

## Why this matters more than one packet

The v4.1 minimums are fixed so packets are comparable. But the *achievability* of those minimums is
a function of company type, and it runs the same direction as the confounders already in the model:

| | Best Buy (P-02) | Akuna (P-03) | Doist (P-05) |
|---|---|---|---|
| Stage | 5 | 3 | 2 |
| Public? | Yes | No | No |
| Reviews available | 39,850 | 22 | few |
| Newest review | days old | 2026-02 | — |
| Open postings | thousands | 6 | **zero** |
| Blog / handbook | corporate | none | extensive |
| Press in 12mo | continuous | none | some |

Large public companies clear every quota easily. Small private companies cannot clear D and E at
all, and clear B only by reaching years into the past. **Packet richness correlates with
`stage_size`.** That is the same range-restriction problem already identified for confidence, now
operating one layer earlier — at whether a packet can be built at all.

The consequence, if unaddressed: the ground-truth set silently becomes a large-public-company set,
which is exactly the skew the 19-company roster was criticised for. Except this time the filter is
the instrument rather than the selection.

## Update after P-04 (R/GA): recency is not a small-company problem

The P-04 build changes the diagnosis. R/GA is mid-sized and well known — none of the obscurity that
explains Akuna's thin packet applies. Its section A is rich and its news coverage is substantial.

And its newest employee review is **February 2024** — two and a half years before collection. Zero
of the fifteen most recent fall within 24 months.

In the period those reviews do not cover, the company was sold by its holding-company parent to a
private equity firm, went through layoffs, restructures and client losses, installed new leadership,
and reorganised into five service practices. Section B and Section E therefore describe two
different organisations, and nothing inside the packet would tell a rater that.

Review recency does not track company size. It tracks whether that company's employees happen to
post on the particular review site being scraped — which is close to arbitrary.

**Second flag from the same build:** the review profile for R/GA is named "R/GA Careers Page", is
marked UNCLAIMED, and holds 34 reviews with 5 salary records. That is implausibly few for an agency
of this size and suggests reviews are fragmented across multiple employer entities on the source
site. Every packet built on a single-entity assumption inherits this risk. Worth a check step in
the prompt: search for other entity pages for the same company before collecting.

## The recency hole in v4.1

Section B passes on **count**, with no recency requirement. P-03's fifteen most recent reviews reach
back to November 2017; ten are older than three years. The packet therefore describes a firm as it
was five to eight years ago and still passes the yield audit.

Meanwhile ladder rung 2 has an explicit ~18-month staleness gate — which correctly rejected a 2018
article during the P-01 build. The gate exists, it is just scoped to one rung.

**Recommendation: make the staleness gate general.** Apply it to every ladder rung and add a review
recency line to the yield audit — something like "B reviews within 24 months: ___/N". A company that
cannot supply recent reviews should fail visibly rather than pass on stale ones, because the rater
currently cannot tell the two apart from inside the packet.

## Options on the roster

1. **Accept asymmetric packets and record why.** Let D and E come back NOT FOUND for small private
   firms, with the ladder proving the attempt. Honest, and the absence is itself information — but
   it means small-company scores rest almost entirely on company-authored copy plus old reviews,
   which collides with the non-company-source support flag.
2. **Relax D and E for private companies.** Set a different minimum by company type. Comparability
   drops, and you would need to record which standard each packet was built to.
3. **Swap the small companies out.** Cleanest packets, worst roster — you would be back to a
   stage-5-skewed set and would lose the autonomy-high, pace-low and collaboration-solo anchors.

Option 3 is what happens by default if nobody decides. Worth deciding deliberately instead.

## Also relevant to production

None of this is specific to the ground-truth exercise. A production scraper hits exactly the same
wall on any private company, and the six dimensions would be extracted from thinner, older, more
marketing-weighted evidence for precisely the small companies a candidate might most want an honest
read on.
