# Source Availability — Probe Results

_Run 2026-08-10, before packet build. Purpose: establish which evidence sources are actually
retrievable before committing to a packet spec. Findings apply to both the ground-truth build
and the production scraper._

## Verdict by source

| Source | Status | Notes |
|---|---|---|
| Company careers / benefits / culture pages | **Works** | Retrieved in full, richly. Doist careers page returned complete body copy, benefits detail, and named employee testimonials. |
| Company engineering / culture blogs | **Works** (expected) | Same domain class as careers. Verify per company. |
| Job posts on company site | **Works** (expected) | See Doist caveat below. |
| **Indeed reviews** | **Works — and is the find** | Full verbatim review text, each carrying **job title and location**. See below. |
| Glassdoor | **Unusable** | Fetch returns an empty body. Client-rendered / anti-bot. |
| Reddit | **Blocked** | Hard 403, domain on blocklist. |
| News | Untested | Expect mixed by outlet. |
| 10-K Human Capital (Item 1) | Untested | Applies only to P-01 Oscar, P-02 Best Buy, P-06 Raymond James. Akuna, R/GA, Doist are private. |

## Indeed solves the dispersion dependency

The open question gating the dispersion decision was whether review quotes would carry enough
attribution for a rater to distinguish *"sources contradict each other"* from *"sources describe
different parts of the company."*

Indeed returns, per review: **job title**, **location**, date, and full text. Examples pulled from
the Best Buy probe:

- `Digital Imaging Specialist · Florence, KY` — "the management was terrible and would constantly
  micromanage what you're doing"
- `Sales Advisor` (location withheld by reviewer) — "I work at a particularly strong Best Buy...
  management at my particular location has been more than just that"
- `Anonymous · New York, NY` — "Sales development is taken seriously if you take it seriously.
  Will depend on the management team of course"

Job title is a workable **function** proxy and location is a workable **site** proxy. Tenure is not
exposed. That is enough to score dispersion at the three-level ordinal agreed; it is not enough to
score dispersion by seniority.

Indeed also exposes filtered views by job title and by location, which makes deliberate
cross-function sampling possible rather than accidental.

## Trap: do not use search-engine summaries of Glassdoor

Web search returns fluent summaries of Glassdoor content even though the pages themselves cannot be
fetched. That text is **search-engine-interpreted prose, not verbatim quotes**, and putting it in a
packet violates the core packet rule — raters and the LLM must score raw evidence, never another
model's characterization of evidence. It is tempting precisely because it reads well and fills the
thin-packet gap.

Rule: **if it cannot be quoted verbatim from a retrievable page, it does not go in the packet.**

## Known gaps to resolve before the build

1. **Doist has no open roles.** The careers page currently lists none, so P-05 gets no job-post
   source. Doist carries three of the twelve pole anchors (autonomy-high, pace-low,
   collaboration-solo), so this is the worst packet to lose a source class on. Its `/how-we-work`
   pages are unusually substantive and partly compensate, but they are company-authored, which
   interacts with the non-company-source support flag.

2. **Best Buy's Indeed reviews are overwhelmingly store-level** — sales associates, warehouse
   workers. Corporate and technology functions are a different environment inside the same legal
   entity. This is the enterprise-vs-function scoping problem in concrete form. Indeed's job-title
   attribution makes it visible rather than silent, which is the argument for capturing dispersion
   rather than averaging it away. Sample deliberately across both.

3. **Private companies have no filings.** Akuna, R/GA, Doist. Expected, and consistent with the
   prior finding that layer count tracks company type rather than culture-evidence quality.

## Implication for production

Glassdoor being unavailable and Reddit being blocked is not only a ground-truth problem — it
constrains the production scraper the same way. The experiential source class effectively reduces
to Indeed unless a licensed data source is acquired later. Worth knowing before the packet spec
treats "employee reviews" as a source-agnostic category.
