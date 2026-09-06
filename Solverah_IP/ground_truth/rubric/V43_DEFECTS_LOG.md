# v4.3 defect log

_Opened 2026-08-13 during the P-02 (Best Buy) build. One entry per defect, with the evidence that
exposed it. Entries are findings, not decisions — the revision happens after Sebastian rules on the
forks marked **FORK**._

Company under test: Best Buy. First **public** company through the prompt (P-03, P-04 and P-05 are
all private), and the largest by two orders of magnitude — 39,859 reviews on one site, 41,921 on the
other, against 22 and 34 for the earlier builds.

---

## D1 — **FORK.** The two review sites are complementary, not substitutable. v4.3 treats them as
## substitutes and picks the wrong one for text.

This is the big one. v4.3 §B1 makes Glassdoor "your sampling frame" and demotes Indeed to
"the cross-check, not the frame," on the grounds that Glassdoor holds far more reviews and carries
per-title subratings. Both of those facts are true. The conclusion drawn from them is not.

Measured on the same company, same day:

| | Glassdoor title page | Indeed title page |
|---|---|---|
| Reviews per fetch | **3** | **20** |
| Review body format | **Pros/Cons bullet fragments** | **continuous prose** |
| Per-title subratings (6 categories) | **yes** | **no — shows company-wide figures** |
| Date per review | yes | yes |
| Location per review | yes | yes |
| Fetches for a 15-review sample across 5 titles | **~25** | **~5** |

The format difference is the part nobody measured. A Glassdoor review body renders as:

> Pros — "They are really good at helping / Always setting goals / Understanding / Good management /
> Flexible"  ·  Cons — "Sometime too much presumiré / Hours always changes / Customers are mean"

An Indeed review body from the same company renders as:

> "Your experience strongly depends on management in the store. The atmosphere of my store shifted
> drastically when a new GM was introduced. Much more micromanaging was introduced, so much so that
> it becomes a chore to keep your radio on for more than 5 minutes."

The second one carries autonomy signal a rater can actually score. The first is a keyword list.
**v4.3 optimised Section B for review count and recency and silently degraded evidence quality per
review** — which is the same class of error as v4.2 optimising for layer count.

Conversely, Indeed genuinely cannot supply what v4.3 wanted from Glassdoor: its title-filtered pages
display the *company-wide* detailed ratings (3.6 work-life balance, "Based on 39,859 reviews") on
every title page. There are no per-title numbers on Indeed at all.

**Proposed resolution — use both, for different things, and say so explicitly:**
* **Indeed** supplies the verbatim review text, sampled stratified by job title, newest-first.
* **Glassdoor** supplies the per-title subrating blocks — numbers only, no quotes — plus a
  cross-check on recency in case Indeed's coverage for a given company is thin.
* Neither is "the frame." The frame is the title list; the two sites fill different columns.

This also makes the P-03/P-04 correction narrower than currently written: the *staleness* finding was
genuinely an Indeed artifact on those two companies and the correction stands. But "Section B is now
built from Glassdoor" over-corrected, and on a large company it would produce a packet of bullet
fragments.

---

## D2 — v4.3's Glassdoor URL pattern is the keyword filter, not the job-title filter.

§B1 step 3 gives `glassdoor.com/Reviews/<Company>-<Title>-Reviews-EI_IE<id>...htm`. The URL that
actually matches that shape carries a `KO<start>,<end>` segment, which is Glassdoor's **keyword**
offset, not a title filter. Following it for "Sales" returns 221 reviews pooled across Sales
Associate, Sales Advisor, Sales Consultant and anything else containing the string — while the site's
own top-jobs block reports Sales Associate alone at 4,876.

Consequence: a researcher following v4.3 literally builds pseudo-buckets by string match and records
them as job titles. Every per-title subrating captured that way is scoped to a keyword, not a role.
This compounds D5 in v4.3's own §B4 (fuzzy buckets) rather than being covered by it.

---

## D3 — The "top reviewed jobs" block v4.3 tells you to read does not render on a large company.

§B1 step 1: "Open any Glassdoor company page and read the top reviewed jobs block. It lists each job
title with its review count. Record the full list and counts."

On this company the block appears only inside a collapsed FAQ accordion and truncates after two
entries — `Sales Associate (4876) ; Customer Service Representative` with the count cut off. The full
list is not retrievable from that route.

It *is* retrievable elsewhere: Indeed exposes a complete title index at `/cmp/<co>/browse-reviews` and
`/cmp/<co>/job-titles`, both of which rendered fully. The step needs a fallback, and the fallback
happens to be on the site v4.3 demoted.

---

## D4 — Headline counts and percentages contradict each other *within a single page*, on both sites.

v4.3 §B4a already says to distrust the percentages and §B4a/B1a give three validation checks. Those
checks were written from P-04, a company with ~14 reviews per title, and are all sample-size
arguments. They do not catch what happens here, where sample sizes are huge and the numbers still
disagree:

* Indeed, one page, simultaneously: page title "35,162 Reviews", heading "## 35,162 reviews",
  rating block "Based on 39,859 reviews", nav tab "39.9K Reviews".
* Glassdoor overview: snapshot "based on 41,921 ratings"; FAQ lower on the *same page* "based on
  42,168 anonymously submitted reviews".
* Glassdoor CEO approval: **35%** company-wide on the overview page vs **83%** on the Sales page.
  v4.3 already says ignore CEO approval — correct, and this confirms it for a second reason.
* The Sales title page reports "66% would recommend" in its header while its own FAQ block says
  "58% of employees in US would recommend … compared to 66% of Best Buy employees worldwide." The
  header figure and the FAQ figure are scoped differently and neither says which.

**Proposed rule:** counts are unreliable at every scale, not only at small n. Record the count *and
the exact element it came from*, never a single number. Add an explicit instruction not to quote a
site-reported total anywhere in Section 1.

---

## D5 — No section for the 10-K Human Capital disclosure. Decided in, never written in.

The 2026-08-10 handoff records a decision: take the **Human Capital section of Item 1** into packets
(mandatory under amended Reg S-K Item 101, principles-based, describes workforce management in the
company's own words, scrubbable once headcounts are stripped), while leaving out earnings calls,
financial statements and patent filings.

v4.3 contains no such section, and no mention of filings anywhere. This went unnoticed because P-03,
P-04 and P-05 are all private and none of them files. P-02 and P-06 do, and P-01 does.

Half the roster is public. The prompt currently has no route to a source the project already decided
belongs in packets.

---

## D6 — Section B's "one title outside the core function" rule inverts on a large retailer.

§B1 step 2 requires at least one sampled title "outside the company's core function — the support,
operations or administrative roles whose experience usually differs most." That rule was written for
small firms where the core is engineering or trading and the outlier is an ops or admin role.

Here, the core function *by review volume* is retail floor sales, and every one of the site's popular
titles is store-level: Sales Associate, Cashier, Retail Sales Associate, Repair Technician, Warehouse
Worker, Asset Protection Specialist. Following the rule as written selects **more** store roles.

The corporate, supply-chain and technology organisations are a different working environment inside
the same legal entity, and they are nearly invisible in the review population. This is the
enterprise-vs-function scoping problem the source probe flagged, now concrete: a packet built to spec
will describe a retail floor job and be scored as "Best Buy."

**This is a scoping question the prompt cannot answer on its own** — see the FORK note at the bottom.

---

## D7 — Truncation is the norm, not the exception, and v4.3's rule assumes it is rare.

§B3 says to mark truncation with `[…]` and count it in 2f. On this company roughly half of all
Indeed reviews end at "…Show more" and do not expand on fetch. The reviews that *do* render in full
are systematically the short ones.

That is not a footnote in the vintage block — it is a length-based selection effect operating on
every large-company packet. Short reviews survive intact; long, detailed reviews are read as opening
paragraphs. The bias runs toward less nuanced evidence.

---

## D8 — Duplicate rule numbering in Section B makes the prompt ambiguous to follow.

Section B contains **two** rules numbered B2, **two** numbered B3 and **two** numbered B4:

* B2 "Indeed as the cross-check" *and* B2 "Preserve attribution"
* B3 "Confirm the employer ID by search" *and* B3 "Truncation"
* B4 "Normalise job titles before bucketing" *and* B4 "Duplicates"

Editing artifact from the v4.2→v4.3 rewrite. Cosmetic, but the prompt is an instrument and its rules
get cited by number in packet QA blocks.

---

## Open FORK for Sebastian

**D6 is not a prompt bug, it is an unanswered modelling question**, and it will recur on P-06
(Raymond James: financial advisors vs. corporate) and P-01 (Oscar Health: member-services vs.
engineering). Three of six companies.

The question: **what is the unit being scored?** The legal entity, or a specific working environment
inside it? The person side of the model measures one individual's preferences; the company side
currently claims to describe a whole company. For a 85,000-person retailer with 1,000+ stores, there
is no single answer that is true.

Options, none free:

1. **Score the modal employee experience.** Sample by review volume, which means the store floor.
   Honest about who most employees are, useless to the candidate considering the corporate tech org.
2. **Score a named sub-unit and record it.** Packet declares "corporate/technology" or "retail
   operations" as its scope. Preserves meaning, but P-02 stops being comparable to P-05, where the
   whole company is 100 people, and adds a scope field the schema does not have.
3. **Sample deliberately across both and let the dispersion field carry it.** Matches the existing
   dispersion design. Requires that dispersion actually be scoreable from the packet, and produces a
   company that reads as internally contradictory — which is, arguably, true.

Option 1 is what happens by default if nobody decides — same failure mode as the roster question in
`PACKET_FEASIBILITY_FINDING.md`, where option 3 was the silent default.

---

# RESOLUTIONS — Sebastian, 2026-08-13

**D1 → split by role.** Indeed supplies verbatim review text, stratified by job title, newest-first.
Glassdoor supplies per-title subrating blocks (numbers only, never quotes) plus a recency cross-check.
Neither site is "the frame"; the title list is the frame and the two sites fill different columns.

**D6 → record the scope, do not change the scoring unit.** *(Revised the same day. The first call was
"named sub-unit"; it was reversed after the production-parity collision below was raised.)*

The packet still describes the company. Production parity is preserved, the schema does not fork, and
role/team granularity does not enter v1 through the calibration set. What changes is only that the
packet **records which population its evidence actually came from**, per section — metadata, in the
same spirit as the recognition Y/N flag, which is recorded and does not alter scoring.

**Why the reversal.** Two arguments, both of which outrank the meaning gained by sub-unit scoping:

1. *Ground-truth input must match production input* — a locked decision from 2026-08-10. A production
   scraper reaches a careers page and a review site and takes what is there, company-wide. Packets
   hand-scoped to a sub-unit would calibrate the extractor on a granularity production never emits.
   This is collision #2 from that handoff, re-entered from a different direction.
2. Role/team matching is explicitly deferred in v1 until companies supply their own data. Sub-unit
   scoping is that capability arriving early and through the calibration set.

**What survives from the original argument, and why the metadata line is not cosmetic.** A packet is
sub-unit-scoped *either way*. Best Buy's review population is overwhelmingly store floor, so scoring
"the company" silently means scoring retail operations — the weighting is not chosen, it is set by
who happens to post reviews. The modal-experience option is the undeclared version of the sub-unit
option. Recording the scope makes an accidental property visible without acting on it, and it makes
"how much does scope drive score variance?" a question that can later be asked at all. Right now it
cannot be.

**D5 → implement.** 10-K Human Capital section added; it was already decided in on 2026-08-10 and
only the write-up was missing.

D2, D3, D4, D7, D8 → fix as specified above. All are corrections, no judgment call needed.

---

## D9 — consequence of the D6 resolution, found while writing it in.

**Sections A and D cannot be scoped to a sub-unit. Sections B and C can.**

A careers/values page is written for the whole legal entity. A handbook or engineering blog belongs to
whoever writes it and is usually the technology org regardless of where the company's headcount sits.
Reviews and job postings, by contrast, carry a job title and can be filtered to a declared sub-unit.

So a sub-unit-scoped packet is not uniformly scoped. It mixes:
* company-wide, company-authored marketing copy (A),
* sub-unit-specific experiential evidence (B),
* sub-unit-specific employer language (C),
* whatever org happens to publish (D),
* company-wide events (E).

*Written under the original D6 call. It survives the reversal unchanged — the per-section scope line
is now metadata rather than a scoping instruction, but the mismatch it records is identical.*

This is not fatal but it is not nothing, and it interacts directly with the proposed scoring rule
*"no dimension scores above 0.7 unless a non-company-authored source supports it."* On a sub-unit
packet, the company-authored half describes a different population than the non-company-authored
half. A rater told "this packet describes retail operations" will read Section A's corporate values
copy as if it were about retail operations. It is not; it is about everyone.

**Handling adopted:** the scope declaration at the head of the packet must state *per section*
whether that section is scoped to the sub-unit or company-wide. Cheap to produce, and it makes the
mismatch visible instead of silent. Recorded here because it is a real weakness of the option chosen,
not a reason to reverse it — the alternatives all had worse ones.

---

# v4.4 defects — found while building P-02 under v4.4

## D10 — the same job title appears in two function categories with different counts and ratings.

On Indeed's `/job-titles` index for P-02, **Technical Support Specialist** appears under *Software
Development* (1,042 reviews, 3.6) **and** under *IT Operations & Helpdesk* (711 reviews, 3.7). Same
title string, two categories, two counts, two ratings.

Consequences: any category-level total double-counts, and the two entries cannot both be right about
the same population. Rule — never sum category counts, and when a title appears twice, record both
appearances rather than picking one.

## D11 — category labels are not function labels.

P-02's *Software Development* category is dominated by Technical Support Specialist, which at this
company is the in-store repair and support arm — store-level work, not corporate engineering.
Sampling that category to reach "engineering" reaches the store floor under a different name.

Use the category headings to *navigate* the index. Never treat one as evidence that a function is
represented.

## D12 — **Section A is [YIELD] and has no fallback chain. On P-02 its primary route is unreachable.**

The most consequential defect found under v4.4, and it inverts an assumption every version has held
since v4.2: that sections A, B and C "exist for essentially every employer" and a shortfall is a
research failure.

P-02's careers, culture and values pages are served by a JavaScript single-page application on the
ATS domain. Every URL on it — the careers root, `?id=item_detail&content=culture`,
`?id=item_detail&content=values` — returns an identical `Loading...` shell with no body content. The
pages exist and are rich; they cannot be retrieved by fetch.

Section C anticipates exactly this and gives a five-step fallback chain. **Section A gives none.** It
names one source, "the official site," and gates the packet on yielding five excerpts from it.

**Route that worked:** the company's corporate/newsroom domain, a conventional server-rendered site on
a different host, carrying company-authored culture language, an inclusion-and-belonging page, an
ethics page and a corporate-responsibility report. Company-authored, quotable, dated.

**Proposed Section A fallback chain, ordered:**
1. Careers / culture / values pages on the careers domain.
2. **The corporate or newsroom domain** (`corporate.<company>.com`, `about.<company>.com`,
   `<company>.com/company`). Frequently a separate, server-rendered CMS while the careers site is an
   ATS-hosted SPA. This is where P-02's Section A came from.
3. Corporate-responsibility / ESG / sustainability report PDFs — these carry substantial workforce
   and working-practice language and are static documents.
4. The 10-K Item 1 Human Capital disclosure (section F) — note that on a JS-gated company the
   **filing is more retrievable than the careers page**, which reverses the usual expectation that
   filings are the hard-to-reach source.
5. Only after all four: record the absence, with the URLs and the `Loading...` responses as proof.

**Why this matters beyond one packet.** A `Loading...` shell read as an absence is the same error as
`/insights`, the JS-gated careers page and the Glassdoor listing — the fourth occurrence, now in the
one section the prompt treats as guaranteed. And enterprise careers sites are overwhelmingly
ATS-hosted SPAs, so **a production scraper using plain HTTP fetch loses Section A on precisely the
largest companies** — the same direction as every other availability problem found so far, but
running the opposite way: big companies fail here where small ones succeed.

**Instrument note.** A JavaScript-rendering browser resolves this. Whether packets are built with a
renderer is a spec decision, not a tooling detail: it changes which sources are reachable, and
therefore what a packet contains.

### RESOLVED — Sebastian, 2026-08-13: production WILL render JavaScript.

Production uses a headless browser (Playwright/Puppeteer class). Rationale: a non-rendering scraper
loses section A on most large enterprises, because ATS-hosted single-page apps are the norm at that
size. That loss is **correlated with company size**, so it enters the corpus in the same direction as
`stage_size` — and unlike every previous availability finding, which ran against small private firms,
this one runs the opposite way. The two do not cancel; they make the bias non-monotonic and harder to
reason about. Rendering at this scale is a few hundred thousand page loads, which is hours on a small
worker pool rather than a cost that changes anything.

**Consequences for the ground-truth build, all binding:**

1. Packets are built **with** a renderer, because production has one. Parity holds.
2. The section A fallback chain above stays in the prompt, but as a genuine fallback for pages that
   fail *even when rendered*, not as the standard route.
3. **ANONYMOUS-EQUIVALENT CONTENT ONLY.** The renderer used during the ground-truth build is an
   authenticated browser on a personal machine. If it is signed into a review site or a professional
   network it will return content a logged-out production scraper can never reach — ground truth
   *richer* than production, which is the same parity violation in reverse and considerably harder to
   detect, because the packet simply looks better than it should. Collect nothing behind a login.
   Where a page differs signed-in versus signed-out, take the signed-out version.
4. **Record `needed JS: Y/N` per source** in the access log at 2d. Across six packets this measures
   exactly what rendering buys, per company and per section — turning a judgment call into a number,
   and giving the production build a concrete requirement rather than an assumption.

---

## D13 — **The renderer is not strictly better than plain fetch. They reach DIFFERENT sources, and
## neither dominates.** Found immediately after the rendering decision.

This qualifies the D12 resolution and is the most operationally important thing found today.

Minutes after the renderer was connected and used successfully to retrieve section A from a page that
plain fetch could not touch, the same renderer was pointed at an Indeed job posting. It was
**redirected to a sign-in wall**, with `from=bot-detection-anonymous` in the redirect URL. Plain HTTP
fetch had retrieved the same class of page, on the same site, without incident, minutes earlier — and
did so again immediately afterwards.

| Source | Plain HTTP fetch | JS renderer |
|---|---|---|
| Careers / values SPA (ATS domain) | **`Loading...` shell — fails** | **retrieves in full** |
| Indeed job posting | **retrieves in full** | **bot-walled to sign-in** |
| Indeed review listings | retrieves in full | not retested — assume at risk |
| Corporate / newsroom CMS | retrieves in full | retrieves in full |
| Glassdoor title pages | retrieves in full | not retested |

The naive reading of D12 — "production renders, therefore render everything" — **would have lost
Indeed**, which under v4.4 is the primary source for section B review text. That is a worse outcome
than the problem D12 was solving.

**Rule: choose the retrieval method per source, and record which one was used.** Renderer for
JS-gated first-party sites; plain fetch for the review and job aggregators, which are the most
aggressively bot-defended and, being server-rendered, gain nothing from a renderer anyway. Where a
source fails on one method, try the other before recording an absence — the proof-of-absence rule now
has two methods to exhaust, not one.

**Never resolve a bot wall by signing in.** It breaks the anonymous-equivalent rule from the D12
resolution, and worse, it silently produces ground truth that production cannot reproduce.

**For production, this is a requirement, not a nuance.** A scraper that renders everything will be
bot-detected on exactly the sites that hold the experiential evidence. The production fetcher needs
both paths and a per-domain policy. Worth knowing before the scraper is built rather than after.

**Honest note on the pattern.** Four times this project has recorded an empty or unhelpful response
as an absence and been wrong. This is the fifth variant, and it is subtler: the failure was not an
empty response but a *plausible* one — a real sign-in page, which reads as "this content requires an
account" rather than "you were detected." A researcher who had not just fetched the same page by
another route would have recorded it as gated and moved on.

---

**Second-order note for the model, not for the prompt:** if packets carry a scope, the company-side
dimension scores are scoped too, and `stage_size` for a sub-unit is not the same as `stage_size` for
the legal entity. Best Buy's retail operations is a stage-5 environment by headcount and a very
different one by decision rights. The confounder encoding assumes one company, one row. Flagged for
the schema, not resolvable here.
