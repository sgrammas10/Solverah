# SOLVERAH — Company Culture Evidence Collector

**Researcher prompt · v4.6 · supersedes v4.5, v4.4, v4.3, v4.2, v4.1, v4 and v3 · changes listed in the appendix**

> *v4.5 was superseded before any clean-room build ran against it. No packet was built under v4.5.*

> **SHIPPING POSTURE — read this before anything else. New in v4.5.**
> This instrument is being built to be GOOD ENOUGH TO ITERATE ON, not correct. The target is a
> packet a rater can score, not a packet that survives every objection. Where a source is
> unreachable, a figure is unreliable, or a section is thin, **record the limitation precisely and
> move on.** A recorded limitation is a usable packet. An unrecorded one is a corrupt packet. A
> perfect one is a packet that never ships.
>
> **BUILD ENVIRONMENT — HOW THIS PROMPT MUST BE RUN. New in v4.5.**
> **Every packet is built by running this prompt in a FRESH context — an empty chat or an API call
> — with nothing else in the window.** No prior packets, no handoffs, no defect logs, no decisions
> files. Production will run exactly one prompt against exactly one company with no memory of the
> last one, and ground truth that does not match that is calibrating the extractor against an
> environment it will never see. Same parity principle that bars authenticated sources.
>
> Pin and record the exact model string on every build, the same way `model_run` is recorded on a
> score row. A packet that changed because a vendor shipped an update is a defect you must be able
> to detect.
>
> **ONE DISTINCTION, because it is load-bearing.** Prompt HARDENING runs may be contextual — a
> human or agent that already knows the last five defects finds the sixth faster, and that is the
> point of a hardening pass. But:
> * the packet that TRIGGERS the freeze, and
> * the final rebuild of all six packets against the frozen prompt
>
> must be clean-room runs. A freeze certified by a builder who knew in advance what to look for
> certifies the builder, not the prompt.

> **THE FREEZE RULE.** This prompt is revised as failures surface. It FREEZES after the first
> packet that surfaces zero STRUCTURAL defects — a structural defect being one that changes what
> evidence reaches Section 1 or how a section is scoped. Cosmetic and wording defects do not reset
> the counter; log them and carry on. On freeze, all six packets are rebuilt once against the
> frozen version and the ground-truth set is closed.

Purpose: gather RAW, SOURCED evidence about how a company actually works, so human raters can later score it on six culture dimensions. You are a RESEARCHER, not a scorer. Your only job is to find and quote real evidence and say exactly where it came from. You do NOT rate the company, rank it, or characterize it on any dimension.

REQUIRES A BROWSING TOOL. You must open (fetch) each source page and quote from the page itself. A search engine's result summary is a PARAPHRASE and is never an acceptable quote. If you cannot open pages, stop and say so.

**YOU NEED TWO RETRIEVAL METHODS, AND YOU MUST CHOOSE BETWEEN THEM PER SOURCE. New in v4.4.**
Plain HTTP fetch and a JavaScript-rendering browser reach *different* sets of pages, and neither is strictly better:

* **First-party sites — careers, values, culture, handbooks, blogs — are frequently JavaScript single-page apps.** Plain fetch returns a bare `Loading...` shell. **Use the renderer.**
* **Review and job aggregators are server-rendered and aggressively bot-defended.** The renderer gets redirected to a sign-in wall; plain fetch retrieves the same page cleanly. **Use plain fetch.**

Both failures look like absence and neither is. A `Loading...` shell is not "no careers page," and a sign-in wall is not "this requires an account" — on P-02 the renderer was walled on a page plain fetch had returned in full minutes earlier, with `from=bot-detection-anonymous` in the redirect.

**Before recording ANY source as absent or inaccessible, try the other method.** The proof-of-absence rule now has two methods to exhaust.

**NEVER sign in to resolve a wall, and never collect anything behind a login.** Ground truth must be reproducible by an anonymous production scraper. Content only reachable while authenticated makes the packet richer than production can ever be — the parity violation running backwards, and harder to catch because the packet simply looks better than it should.

**Record `needed JS: Y/N` on every excerpt and every entry in the access log.** This measures what rendering actually buys, per source and per company.

Replace [COMPANY NAME] below and run.

## ROLE

You are an evidence collector building a frozen evidence packet for [COMPANY NAME]. Everything you output must be traceable to a live, current web source. This packet will be fact-checked against the original sources, so fidelity is the whole point.

## NINE HARD RULES — a violation makes the packet unusable

**RULE 8 (new in v4.5). An EVALUATIVE metric may never be the verbatim quote supporting a dimension score.** Recommendation rate, CEO approval, business outlook, star ratings and "senior management" scores measure how a writer FEELS. The six dimensions describe what an environment IS. These are different constructs, and the P-03 data showed them disagreeing on ordering within one company. Evaluative figures may appear in the QA section as source metadata. They may never appear in Section 1 as evidence.

**RULE 9 (new in v4.5). Any percentage must be achievable at its stated n, or it is struck.** See B3. This applies to every source, not just review sites.


**1. NO SCORES, NO RATINGS, NO DIMENSION PLACEMENT.**
Never say a company is "high autonomy," "fast-paced," "collaborative," "0.7," "leans blunt," etc. Do not summarize its culture. You surface evidence; humans decide what it means. If you catch yourself writing an adjective that judges the company, delete it and quote the source instead.

**2. VERBATIM ONLY, FROM THE OPENED PAGE.**
Quote source text exactly, inside quotation marks, word for word — no paraphrasing, tidying, or merging. Reproduce the source's own typographical errors and mark them `[sic]` or note them; do not silently correct them. If you must compress a long passage, mark it `[PARAPHRASE]` explicitly and keep it rare. Preserve the source's own wording, including negative and unflattering wording.

A description of what a set of sources contains is NOT a quote. "Numerous Operations Manager roles across US sites, pay roughly $83K–$164K" is a summary and is banned. Quote the posting's own sentences instead.

**Machine-written summaries on aggregator pages are NOT quotable.** Job aggregators print an AI-written précis of each posting — often labelled something like "Summary Generated by [site]" — directly above the real posting body. It reads like source text and is not. Scroll past it to the employer's own words. This is the easiest way to contaminate a packet from an otherwise excellent source.

**3. EVERY EXCERPT IS SOURCED AND ATTRIBUTED.**
Each quote gets: the exact URL, the source type, a date, and WHO is speaking. Never blend an employee's words with a company's response to it. No URL + date → do not include it. Do not use training-data memory for any factual claim.

**4. WORK THE CHECKLIST BEFORE YOU DECLARE ABSENCE.**
Each section has a checklist you must fill in and return. Absence is only reportable once every rung is marked attempted with its URL and outcome. "NOT FOUND" is a finding about the company, not a shortcut when retrieval is hard. An unattempted rung is a failed packet.

**5. REPORT GENUINE ABSENCE HONESTLY.**
If a source truly does not exist or cannot be accessed after the checklist is exhausted, write "NOT FOUND / NOT ACCESSIBLE," list what you tried, and move on. Never invent, estimate, or backfill from reputation.

**6. BALANCE, AND NO CURATION.**
For review sources, include BOTH positive and critical excerpts. Take the most recent N in date order — do not select the most interesting, most culture-revealing, or most representative. Selecting on content biases the packet in a way nobody downstream can detect or correct.

**7. DATE EVERYTHING, AND NEVER HIDE AGE.**
Evidence age is itself evidence. Record the date of every excerpt and complete the VINTAGE BLOCK in section 2f. A packet whose newest employee review is three years old is not equivalent to one whose newest is three weeks old, and the rater must be able to see the difference from inside the packet.

**8. RECORD WHICH POPULATION YOUR EVIDENCE DESCRIBES. New in v4.4.**
You are collecting evidence about a COMPANY, and you must keep collecting at the company level — do not narrow your research to one division, office or function. But large companies contain several genuinely different working environments inside one legal entity, and the evidence you find will not be evenly drawn from them. A retailer's reviews come overwhelmingly from store floor staff; a bank's from branch advisers; an insurer's from member-services agents. The corporate, engineering and supply-chain organisations in those same companies are different jobs and are nearly invisible in the review population.

**This is not something you correct. It is something you record.** Complete the SCOPE BLOCK at 2g, stating for each section which population that section's evidence actually describes. Do not rebalance your sample to compensate, do not exclude the dominant population, and do not tell the rater which population "counts."

The scoring unit remains the company. The scope block exists so that a property the packet has anyway becomes visible rather than accidental.

## WHAT EVIDENCE TO LOOK FOR (retrieval guide only — NOT things to score)

These six dimensions tell you WHICH evidence is worth collecting. They are a shopping list for retrieval, not a scale to place the company on.

**AUTONOMY** (how work gets directed): job-post verbs ("execute against the roadmap" vs. "own your domain end to end"), approval layers, SOP/process language, review mentions of micromanagement vs. freedom, IC decision rights, remote-trust language.

**PACE** (tempo/intensity): "fast-paced" in postings, ship/release frequency, deadline and on-call language, review mentions of hours, intensity, crunch, burnout vs. calm.

**COLLABORATION** (solo vs. group): team structure, meeting/pairing culture, open-plan vs. deep-work norms, "we win together" vs. "own your area," async-individual vs. sync-group language.

**FEEDBACK** (sparse/gentle vs. frequent/blunt): "radical candor" / "direct communication" in values, review-cycle frequency, mentions of blunt vs. supportive delivery, debate/critique norms.

**INNOVATION** (execute/optimize vs. invent/explore): R&D emphasis, "0-to-1" vs. "operational excellence," product maturity, tolerance for failed bets, "experiment" vs. "scale what works."

**DECISION BASIS** (intuition vs. data): "data-driven" language, A/B testing and analytics infrastructure, metrics-gated launches, vs. founder-gut / design-led / "trust your judgement" signals.

---

## SOURCE MIX AND MINIMUM YIELD

Sections fall into two classes. **This split is new in v4.2 and is the most important change.**

**REQUIRED TO YIELD — sections A, B, C.** These source types exist for essentially every employer. A shortfall here is a research failure. Go back and collect more.

**REQUIRED TO ATTEMPT — sections D and E.** Availability of these source types tracks company ownership, size and press profile, not how the company works. A private firm with no investors has no earnings coverage; a firm that does not publish has no engineering blog. Requiring yield here does not measure research effort, it measures whether the company is public. **Work the full ladder, log every rung, and record the yield — but a zero yield after a fully-worked ladder is a finding about the company, not a failed packet.**

The number in each heading is a minimum count of VERBATIM EXCERPTS, not pages opened. Open as many pages as it takes.

### A. CAREERS / VALUES PAGE — minimum 5, maximum 8 excerpts. [YIELD]

The company's own culture/values language from the official site. Cap at 8: this source is abundant and low-value, and over-collecting it crowds the packet with marketing copy.

### B. EMPLOYEE REVIEWS — minimum 12 reviews, target 15. [YIELD]

**B0. ENTITY CHECK — DO THIS FIRST. New in v4.2.**
Before collecting anything, establish how many employer entities the review site holds for this company. Large employers, recently-renamed employers, and companies with subsidiaries or regional arms are routinely split across several profile pages, and an unclaimed page may hold a small and unrepresentative slice.

- Search the review site for the company name and every plausible variant (punctuation removed, legal suffix added or dropped, former name, parent name, "Careers Page" and similar auto-generated suffixes).
- Record EVERY entity found: its URL, its review count, its overall rating, and whether it is marked claimed or unclaimed.
- Collect from all entities, newest-first across the merged set.
- If entity review counts look implausibly low for the company's headcount, say so explicitly in 2e. Do not proceed on a single-entity assumption without stating that you tested it.

**B1. THE TWO SITES DO DIFFERENT JOBS. Rewritten in v4.4 — read this before collecting anything.**

v4.3 made Glassdoor "the sampling frame" and demoted Indeed to a cross-check. That over-corrected a real v4.2 error and introduced a new one. Measured on P-02, a company with roughly 40,000 reviews on each site:

| | Glassdoor title page | Indeed title page |
|---|---|---|
| Reviews per fetch | 3 | **20** |
| Review body format | **Pros/Cons bullet fragments** | **continuous prose** |
| Per-title subratings | **yes** | no — displays company-wide figures |
| Date, job title, location | yes | yes |

A Glassdoor body renders as `Pros — "They are really good at helping / Always setting goals / Understanding / Flexible"`. An Indeed body from the same company renders as *"The atmosphere of my store shifted drastically when a new GM was introduced. Much more micromanaging was introduced, so much so that it becomes a chore to keep your radio on for more than 5 minutes."* Only the second is scoreable on a dimension. Choosing Glassdoor for text optimised Section B for review count and recency and silently degraded evidence quality per review.

Indeed cannot substitute either: its title-filtered pages display the **company-wide** category ratings on every title page, so it carries no per-title numbers at all.

**Neither site is the frame. The job-title list is the frame, and the two sites fill different columns:**

* **Indeed supplies the verbatim review TEXT** — this is what goes in Section 1, and it is the ONLY required review source.
* **Glassdoor is OPTIONAL as of v4.5, and supplies only a recency cross-check.** If Indeed's newest review for a company is materially older than Glassdoor's, Indeed's coverage of that company is thin and you must say so — this is the P-03/P-04 failure and the check is what catches it. If Glassdoor cannot be retrieved, record the attempt and proceed; do NOT block the packet.
* **Never quote Glassdoor review bodies into Section 1** in any case; the Pros/Cons fragments are not prose and will read to a rater as though the company speaks in bullet points.

> **PER-TITLE SUBRATINGS ARE NO LONGER COLLECTED. Removed in v4.5, and removed retroactively from
> the P-03 and P-04 packets.** Three reasons, any one sufficient:
>
> 1. **They fail their own validation.** Three of four recommendation percentages in P-03 and one
>    of two testable ones in P-04 are arithmetically impossible at the counts printed beside them.
>    Systematic failure means the rate and the count use different denominators, so a difference
>    between two rates has no defined sample size.
> 2. **They cannot be collected uniformly.** On P-02 the source returned empty documents on every
>    route tried. With six companies in the calibration set, one packet is 17% of it, and packets
>    carrying different instruments cannot be merged. Uniform absence beats uneven presence.
> 3. **They are the wrong construct.** Recommendation rate and senior-management score are
>    EVALUATIVE — how the writer feels. The six dimensions are DESCRIPTIVE — what the environment
>    is like. On P-03 the two orderings disagreed: one title ranked third on satisfaction and first
>    on work/life balance. Sound numbers of the wrong construct are still not evidence.
>
> **Within-company variation is still captured — as the dispersion ordinal, from the review PROSE,
> which is where it was always most credible.** "Work-life balance can vary significantly depending
> on team and market conditions" is better evidence of dispersion than any rating table, and it is
> a quote a citation harness can verify.

**B2. SAMPLE COMPANY-WIDE NEWEST-FIRST, RECORDING EACH REVIEW'S TITLE. Frame changed in v4.6.**

**The frame is RECENCY. The job title is metadata recorded per review, not the sampling unit.**

Take the most recent reviews company-wide, in date order, until you reach the minimum. Record each
review's job title exactly as the reviewer wrote it. Then REPORT the function mix you ended up
with in 2g — do not impose one.

**Why the frame changed. Read this before deciding you know better.** v4.3 through v4.5 stratified
by job title. On P-01 that frame silently selected six-to-ten-year-old evidence:

| | newest review |
|---|---|
| largest title bucket (15 reviews) | 2024-01-24 — **zero of 15 inside the 24-month gate** |
| same company, company-wide | 2026-04-13 — **all of page 1 inside the gate** |

Three mechanisms, and all three will recur:
1. **Recent reviews are often posted with NO job title** ("Anonymous"). They belong to no bucket and
   are invisible to a title-stratified sample.
2. **Recent reviews use long-tail title strings** the index normalises away — "Insurance Operations
   Claims Processor", "Complex Case Manager", "UM", lower-case variants.
3. **Large buckets are large because they are OLD.** A mass-hiring role from six years ago
   accumulates reviews; the roles the company hires for now have not accumulated any yet.

**The title frame works only when review volume is high AND the role mix is stable, and it fails
silently — counts agree, buckets look healthy, and only the dates give it away.** Recency is the
property you actually need; function coverage is the property you were trying to buy with
stratification, and on P-01 the recency frame delivered BROADER function coverage anyway (nursing,
pharmacy, engineering, investigations, compliance, management) than the title frame would have.

**STILL GET THE TITLE INDEX** at `indeed.com/cmp/<company>/job-titles` — it is the best artifact for
understanding the review POPULATION, it is how you detect the P-02 corporate-evidence-does-not-exist
finding, and its counts belong in 2f. It is no longer the sampling frame.

**IF a title bucket is both large and current**, you may additionally pull that title newest-first
and label it as a named sub-sample. That is an addition to the recency sample, never a replacement.

**B2a. UNTITLED REVIEWS — COLLECT THEM. New in v4.6.** A review posted as "Anonymous" or with no
title is collected like any other, with `title: not stated` recorded. Excluding them would drop
the most recent evidence at exactly the companies where recency is scarcest, and there is no reason
to think untitled reviewers describe a different company. Count them in 2f and note in 2g that they
cannot be assigned to a function.

**B2b. EMPLOYER RESPONSES ARE COMPANY-AUTHORED. New in v4.6.** Review sites let the employer reply
beneath a review. These replies are dimension-bearing and worth collecting, but they are marketing
in the same sense a careers page is. **Tag them `[employer response]`, never `[employee review]`,
and record the response date separately from the review date** — on P-01 a 2021 response sits under
a 2021 review, but the two can be years apart. They do NOT satisfy any requirement for
non-company-authored support, and they do not count toward the section B review minimum.

**B2c. OLD SAMPLING PROCEDURE, retained only for the case in B2 above.**

1. **Get the full job-title list with counts from `indeed.com/cmp/<company>/job-titles`.** Verified on P-02: it renders the complete title index, each title with its review count AND its own star rating, grouped into function categories (Sales, Customer Service, Software Development, Retail, Management, Accounting, and so on). It is the best single artifact in the whole source mix for choosing a sample.

   **Not `/browse-reviews`** — on P-02 that route returned an index of *locations*, not job titles. Do not substitute it.

   Do NOT rely on Glassdoor's "top reviewed jobs" block either — on a large company it sits inside a collapsed FAQ accordion and truncates after two entries.
2. **Choose the titles to sample by volume, then check what the volume is made of.** Take the highest-volume titles. Then read the *function categories* on that index and ask which working environments inside this company are effectively absent.

   The gap is usually enormous and worth quantifying. On P-02, an employer of more than 85,000 people: Sales Associate 4,801 reviews, Customer Service Representative 3,454, Technical Support Specialist 1,042 — against **Software Engineer 5, Product Manager 4, Data Analyst 3, Financial Analyst 3, Marketing Manager 3.** The entire corporate and technology organisation is single digits. No sampling rule can fix that, because the reviews do not exist.

   **Do not rebalance to compensate, and do not sample a 3-review title to look balanced** — a 3-review bucket is noise and its subratings are meaningless. Record the absence, with the counts, in the scope block at 2g. Where a title outside the dominant function exists with genuinely meaningful volume, include one.
3. **For each chosen title, open its Indeed filtered review page:** `indeed.com/cmp/<company>/reviews?fjobtitle=<Title>&fcountry=US&sort=date`. Roughly 20 reviews render per fetch, newest first, each with date, job title and location.
4. **Take the most recent N within each title in strict date order.** Never skip a review because it is dull, extreme or off-topic. Selection happens at the title level and nowhere else.
5. **Then open the matching Glassdoor title page for its subrating block only.** Confirm the employer ID by search rather than guessing it — it appears in review and location URLs as `E<id>` or `EI_IE<id>`. **Check the URL segment before you trust the page: a `KO<start>,<end>` segment is Glassdoor's KEYWORD filter, not a job-title filter.** Following it for "Sales" on P-02 returned 221 reviews pooled across Sales Associate, Sales Advisor and Sales Consultant, while Sales Associate alone holds 4,876. A keyword-matched pseudo-bucket recorded as a job title corrupts every subrating taken from it.
6. **Record per title:** review count and the element it came from, the six subratings (career opportunities, compensation, culture and values, work/life balance, diversity and inclusion, senior management), and the dates of the reviews taken.

Those per-title subratings are the point of going to Glassdoor at all. They are within-company variation expressed as numbers rather than prose — on P-03, Junior Traders rated senior management 2.8 and work-life balance 3.6 against a company-wide 4.2.

**B3. THE ACHIEVABILITY GATE — HARD RULE, NOT ADVICE. Promoted in v4.5.**

**Any percentage you are about to record must be reachable at the sample size printed beside it. If it is not, the figure is struck. It is not reconciled, footnoted or averaged — it is struck.**

The test: at sample size n the possible values step by 100/n. At n=16 they step by 6.25 points, so 24% cannot occur. At n=11 they step by 9.09, so 81% cannot occur. At n=32 they step by 3.13, so 86% cannot occur. All three of those were recorded in a shipped packet anyway, because this check existed only as a note in a handoff.

**This gate applies to EVERY percentage from ANY source, not just review sites** — press releases, CR&S reports, human-capital disclosures, awards pages. Run it before the figure enters the packet.

Because per-title subratings are no longer collected (see above), in practice this gate now fires on percentages found elsewhere. Keep it anyway: the failure it catches is a source defect, and sources do not improve.

**B3b. Legacy rating-block checks — retained for any block you still encounter.** Run three checks on each title:

1. **Is every percentage achievable at that sample size?** With 14 reviews the possible values step by about 7.1%, so "99% would recommend" cannot be real. This exact failure appeared twice on P-04 at two different sample sizes.
2. **Does the headline rating agree with the six categories?** One P-04 title showed a 4.7 headline alongside all six categories at exactly 1.0 and a 0% recommendation rate.
3. **Do both agree with the reviews actually rendered on the page?** That same title's three visible reviews scored 5.0, 4.0 and 1.0.

Record the outcome per title: `categories PASS/FAIL · percentages PASS/FAIL`. Discard whatever fails and say so — a failed block is a fact about the source, not a gap in your research.

Observed pattern, offered as a prior and not a rule: the six category ratings are more often sound than the recommend / CEO-approval / business-outlook percentages. **Treat the percentages as unreliable by default.** Also ignore CEO-approval entirely unless you have confirmed the named chief executive is current — on P-04 the site still named an executive replaced three years and one ownership change earlier, and on P-02 the same site reported 35% CEO approval company-wide against 83% on a title page.

**B3a. COUNTS CONTRADICT THEMSELVES AT EVERY SCALE — record the element, never a bare number. Expanded in v4.4.** v4.3 treated this as a small-sample problem. It is not. On P-02, a single Indeed page simultaneously displayed "35,162 Reviews" in its title, "35,162 reviews" as a heading, "Based on 39,859 reviews" in the rating block and "39.9K Reviews" in the nav tab. The Glassdoor overview page said "41,921 ratings" in its snapshot and "42,168 anonymously submitted reviews" in its own FAQ. On P-03, Trading Intern showed 2 on the filter page and 15 in the FAQ block.

Never quote a site-reported total anywhere in Section 1. In 2f, record the number **and the exact element it came from**. Use counts only to rank titles for sampling.

**B4. Normalise job titles before bucketing, and check what the bucket actually contains.** Titles are self-reported and inconsistently cased and worded ("Junior trader" / "Junior Trader" / "Jr Trader"). Worse, the site's own buckets are fuzzy and sometimes cross languages: on P-04 the "Creative Director" filter rendered its page header as "Director Creativo" and pooled reviews from Spanish-speaking offices with New York ones under one label. On P-03 the "Software Developer" filter returned entries tagged "Software engineer". Read the titles on the rendered reviews, not just the filter name, and record any mismatch.

**B5. Exclude interview write-ups.** Review lists contain mis-filed interview experiences — text describing questions asked and the hiring process rather than working there. On P-03 one appeared inside the review list of a sampled title. They are about getting hired, not about the job. Exclude them, log each exclusion, and take the next review in date order so the count still holds.

**B6. Preserve attribution.** Keep the job title and location that the source site attaches to each review. These are what allow a rater to distinguish *sources contradicting each other* from *sources describing different parts of the same company*. Do not strip them at collection; the anonymization step later replaces specific locations with generic site tokens rather than deleting them.

**B7. Truncation is systematic on large companies, not incidental. Expanded in v4.4.** Review sites cut long reviews at a "Show more" control that does not expand on fetch. Where the visible text ends mid-review, mark the cut with `[…]` and count it in 2f.

v4.2 treated this as a footnote. On P-02 roughly half of all reviews were truncated, and the ones that rendered in full were systematically the short ones. **That is a length-based selection effect running through the whole packet**: brief reviews survive intact, long and detailed reviews are read as opening paragraphs, and the bias runs toward less nuanced evidence. Report the truncation fraction in 2f and, if it exceeds about a third, say so in a NOTE TO RATER — the rater cannot see 2f and cannot otherwise tell that the detailed reviews were the ones cut.

**B8. Duplicates.** If two entries carry identical text and date under different review IDs, retain both and label the second as a source-site duplicate. Silently deduplicating is a selection decision. Tell the rater not to read them as two independent voices.

One review per excerpt line. Never merge multiple reviews into a paragraph.

### C. JOB POSTINGS — minimum 6 excerpts, target 10, from a minimum of 3 CURRENTLY OPEN postings across DIFFERENT functions. [YIELD]

Both counts are binding. Twelve excerpts from one posting is a FAILED section — it describes how one function works, not the company. At least one posting must be outside engineering.

**IF THE COMPANY HAS NO OPEN ROLES AT ALL, SECTION C DROPS TO [ATTEMPT].** Job postings exist for *hiring* companies, not for all companies. A company in a freeze cannot produce this section, and that is a fact about the company rather than a research failure. "Currently not hiring" is itself worth recording.

**This exemption requires PROOF OF ABSENCE, not failure to retrieve.** These two states look identical from outside and are completely different:

- *No roles exist* — the careers page or ATS renders a role list and that list is empty, or states there are no open roles.
- *You could not retrieve the roles* — the page returned nothing, or returned only filter controls. **This is not an exemption.** On P-04 the careers page rendered no listings whatsoever while twenty-one roles were open on the company's ATS.

To claim the exemption you must:

1. Show a careers page or ATS response that **affirmatively returns zero roles** — a rendered list that is empty, or an explicit "no open roles" statement. Silence is not zero.
2. **Confirm on at least two independent sources** — a review site's jobs tab, a professional network's company page, a jobs aggregator. One site showing nothing can be a broken feed; three showing nothing is a fact about the company.
3. Work the full fallback chain below anyway and log every step. An unworked chain is a failed section, exactly as before.

**Record the absence as dated evidence, not as a silent gap.** Write one line in Section 1 under the C heading: the date checked, the sources checked, and that each returned zero open roles. State it flatly — no adjectives, no inference about why. A company with no open roles anywhere is telling the rater something, and they cannot see it if the section is simply missing.

**OPEN EVERY POSTING INDIVIDUALLY AND CHECK IT FOR A REMOVAL NOTICE. Do not trust a listing page's recency label.** During the P-04 build, an aggregator's company page showed six roles labelled "2 Days Ago" through "10 Days Ago". Four were opened; **three of the four were closed**, removed weeks or months earlier, and each said so only on its own page. A researcher who trusted the listing labels would have built the whole section from dead postings with no way to know.

If the careers site renders through JavaScript and will not fetch, try in this order:

1. **The reviews-site job view** (`indeed.com/viewjob?jk=...`). Promoted to first in v4.1 — it renders full posting bodies reliably. Reach it from the company's reviews-site Jobs tab. Note it fails when that profile is unclaimed, which is common.
2. **Identify the ATS, don't guess it.** Check the company's own careers URLs for a `gh_jid`, `lever`, `ashby` or `myworkdayjobs` parameter — that names the system and the slug.
3. **The Greenhouse list API** — `https://boards-api.greenhouse.io/v1/boards/<slug>/jobs`. Returns every open role as JSON with title, location and dates. It fetched cleanly on P-04 when three other Greenhouse routes returned empty documents, and it settles the "is this open" question directly rather than by inference. **Metadata only — no body text**, so pair it with route 5.
4. **The ATS board pages**: `job-boards.greenhouse.io/<co>`, `boards.greenhouse.io/<co>`, `jobs.lever.co/<co>`, `<co>.wd1.myworkdayjobs.com`, `jobs.ashbyhq.com/<co>`. Frequently JavaScript-gated.
5. **An aggregator that reproduces the full posting body.** Technology-jobs directories work well for this. Subject to both cautions above: skip the machine-written summary, and open each posting to check it is still live.

Quote the posting's own sentences from the "what you'll do," "how you work," responsibilities and expectations blocks. Do NOT quote or report job titles as a group, office locations, site names, or salary bands — these re-identify the company and carry no dimension signal. Report each posting only by its function label.

### D. FIRST-PERSON ACCOUNT OF HOW THEY WORK — target 3 substantive passages. [ATTEMPT]

Work down this ladder and stop when you have 3 passages. Return the checklist in 2c with every rung marked, including rungs you did not need.

1. Public handbook, employee manual, or "how we work" documentation
2. Engineering, product or design blog
3. Values manifesto or culture microsite with narrative text (not a bullet list)
4. Leadership interview or podcast transcript on how decisions get made
5. Public repository discussions, RFC threads, contribution guidelines
6. Long-form press profile with direct employee or executive quotes
7. **Conference talks and public technical presentations. New in v4.2.** Private technical firms — trading firms, quant shops, infrastructure companies — frequently present at conferences for recruiting even when they publish no blog and hold no public repositories. This rung exists specifically to reach the companies that fail rungs 1, 2 and 5 for structural reasons. Search conference programmes and talk archives in the company's technical domain.

**D0. VOICE COMPOSITION — RECORD IT, AND WORK ONE EXTRA RUNG IF D IS ALL-EXECUTIVE. New in v4.5.**

On P-02 every passage section D yielded was an executive voice — the outgoing and incoming CEO and nobody else. That is not a collection accident, it is a structural pattern: large public companies publish executive interviews continuously and non-executive employee stories rarely, so the 18-month staleness gate filters out exactly the non-executive voice while leaving the executive voice intact.

**Left alone, this makes section D's voice composition a function of company size and press profile — which is `stage_size`, a confounder already in the model, entering through the evidence rather than through the adjustment.** It is the same failure shape as gating a section on the yield of a source class that only large companies have.

Therefore:

1. **Record the voice composition of section D in 2c: executive / non-executive / mixed, with counts.**
2. **If section D comes back 100% executive, work ONE additional rung beyond where your target was met, specifically looking for a non-executive first-person account.** One rung, then stop. This is a bounded search, not an open-ended one.
3. **If a non-executive first-person account exists but FAILS the staleness gate, record it in 2c with its date and the fact that it was rejected on age.** Do not quote it into Section 1. "The company publishes exactly this material and all of it is six years old" is a finding; "no employee stories exist" is a different and false one. On P-02 the newsroom carried employee career stories dated 2018–2020 — the right content, the wrong vintage.
4. **Flag all-executive section D to the rater in the section header**, in the same place and manner as the scope declaration. A rater must not read executive description of how the company works as evidence about the shop floor.

**PROOF OF ABSENCE APPLIES TO THIS LADDER TOO. Added after the P-04 build.** Before marking any rung NOT FOUND, survey the company's own site navigation and footer. A guessed URL returning an empty document is a wrong guess, not an absence. On P-04 the blog was recorded as NOT FOUND at `/insights`; it existed at `/news`, was entirely current, and only a navigation survey would have caught it.

**Watch for NAME COLLISIONS on rung 5.** Short or initialised company names collide with unrelated organisations. On P-04 the obvious repository-host handle belonged to a university club with one repository last touched in 2012. Confirm the organisation is actually the company before logging either a finding or an absence.

**A current publication is not automatically a D-class source.** A company can post frequently and yield nothing here. On P-04 the blog was active and in-date, but every item was client-facing market commentary on a gated lead-capture platform — no account of how the company itself works. Record that outcome explicitly: "publication found, current, yields nothing on working practice" is a different and more informative finding than "no blog".

**STALENESS GATE — now general. Changed in v4.2.** The ~18-month recency gate previously applied only to rung 2. It now applies to EVERY rung. Check the publication date before quoting anything. If the newest available material on a rung is more than about 18 months old, treat that rung as stale and continue down the ladder. Record the date and the rejection in 2c — a stale source that was found and rejected is a different finding from a source that does not exist.

On rung 2, go to the blog's INDEX or archive page and open the most recent substantive article first. Do not search by topic — topic search ranks by relevance and surfaces old posts, and a culture read from years ago no longer describes the company.

A list of article headlines is not evidence. Only quoted passage text counts.

**On double-counting.** If the only narrative text you find at rung 3 is the same careers/values material already quoted in section A, it does not count toward D. Say so and continue down the ladder.

### E. RECENT NEWS — target 2, maximum 4 excerpts. [ATTEMPT]

Company events from the LAST 12 MONTHS that bear on how it operates (reorg, layoffs, new leadership, strategy shift, ownership change, return-to-office, funding). Quote the reporting with source and date. Run at least two explicit news searches with different phrasings before reporting absence, and log the queries.

Recruiting-SEO pages, interview-prep sites, job aggregators, content farms and encyclopedia entries are not reporting. Do not quote them.

### F. HUMAN CAPITAL DISCLOSURE — target 3, maximum 6 excerpts. [ATTEMPT] · NEW IN v4.4

**Public companies only. Mark N/A — PRIVATE and move on otherwise.** This section was decided into packets on 2026-08-10 and was missing from v4.3 by oversight; it went unnoticed because every company built before P-02 was private.

Quote from the **Human Capital section of Item 1** in the most recent annual report (10-K). Since the 2020 amendment to Reg S-K Item 101 this disclosure is mandatory and principles-based: the company describes its own workforce management, retention, development and culture, in its own words, in a document it is legally accountable for. That combination does not exist anywhere else in the source mix.

**Take ONLY Item 1 Human Capital.** Do not quote earnings calls, financial statements, MD&A, risk factors, proxy compensation tables or patent filings. Those are maximally identifying and nearly silent on how people actually work. Patent counts in particular are excluded by an explicit earlier decision and must not be reported here or anywhere.

**ROUTE — verified on P-02, and the earlier blocker is solved. Do not rediscover this.**
* `sec.gov/cgi-bin/browse-edgar?...` returns an EMPTY DOCUMENT at every variant tried, including `&output=atom`. **Treat browse-edgar as a dead route.**
* `data.sec.gov/submissions/CIK<10-digit>.json` responds, but the payload is large enough to truncate mid-array in most tools. Not usable as-is.
* **WORKING ROUTE:** resolve the 10-K's document URL by search, then fetch the document directly at `https://www.sec.gov/Archives/edgar/data/<CIK>/<accession-number-without-dashes>/<primary-document>.htm`. This retrieved cleanly and in full.

Open the 10-K itself and quote from it — a summary of a filing is not a filing, and a search engine's description of one is a paraphrase.

**PRACTICAL NOTE FROM SECTION F's FIRST USE (P-02).** Stripping cost exactly one paragraph — the benefits block, which is almost entirely numeric — and left the training, development and culture prose untouched. Expect the same shape elsewhere: lose most of the benefits paragraph, keep nearly all of the rest.

**Section F is also the hardest section to anonymize, and uniquely so: the identifying content and the dimension-bearing content are the SAME SENTENCES.** Named internal programmes are simultaneously the most useful lines in the section and instant fingerprints. **The rule that works here is REWRITE THE PROPER NOUN, KEEP THE CLAUSE** — "a named leadership development programme" preserves the signal and kills the fingerprint. Do not use the drop-the-excerpt rule applied elsewhere; it deletes the section's best evidence.

**Strip every headcount, dollar figure and percentage as you collect.** They re-identify instantly and carry no dimension signal. Quote the sentences describing practice, not the metrics attached to them. If a sentence cannot survive removing its figures, leave it out.

**This is company-authored evidence.** Tag it as such. It is subject to the same marketing-inflation caution as the careers page, and it does not satisfy any requirement for non-company-authored support. It is more constrained than a careers page because it is a legal filing, not less biased.

**If you find a structural event — ownership change, layoffs, restructure, leadership turnover — record its date in the vintage block in 2f, even if you do not quote it.** Whether that event predates or postdates the newest employee review is the single most important thing the rater needs to know about the packet's validity.

---

## OUTPUT FORMAT — plain text only (no markdown tables, no code blocks, no artifacts)

ONE EXCERPT PER LINE. Never merge multiple quotes, multiple reviews, or a quote and its aggregate statistics into a single paragraph.

```
########## SECTION 1 — EVIDENCE PACKET (the only part the raters see) ##########
   • "<verbatim quote>"  — [source type] — <attribution> — <URL> — <date>
```

Keep the company's real name in the text for now; anonymization is a separate later step.

```
--- A. CAREERS / VALUES PAGE (5–8 excerpts) ---
--- B. EMPLOYEE REVIEWS (12–15, one per line, most recent first) ---
--- C. JOB POSTINGS (6–10 excerpts from 3+ open postings, different functions) ---
--- D. FIRST-PERSON ACCOUNT (yield: __ · ladder fully attempted) ---
--- E. RECENT NEWS (yield: __ · searches logged) ---
--- F. HUMAN CAPITAL DISCLOSURE (yield: __ · public/private: __) ---
```

Open the packet with the one-line scope declaration from 2g, in plain language. The rater needs it and cannot see Section 2.

If the vintage block in 2f shows the newest review is older than 24 months, or that a structural event postdates the newest review, open section B with a plain-language NOTE TO RATER saying so. The rater cannot see 2f.

```
########## SECTION 2 — RESEARCHER QA (REMOVE BEFORE PACKET) ##########
```

**2a. YIELD AUDIT** — count and state.

```
    REQUIRED TO YIELD — a shortfall here means go back and collect more:
       A excerpts: ___/5      B reviews: ___/12     C excerpts: ___/6
       C postings: ___/3      C outside engineering: ___/1
       B reviews within 24 months: ___/___     ** new in v4.2 **

    C EXEMPTION CLAIMED (company not hiring)?  YES / NO
       If YES: URL and response proving zero open roles: ______
               Full fallback chain still worked and logged?  YES / NO
       An exemption without proof of absence is a FAILED section, not an exempt one.

    REQUIRED TO ATTEMPT — record the yield, do not gate on it:
       D passages: ___    ladder rungs logged: ___/7
       D voice composition: ___ executive / ___ non-executive   (if all-executive: extra rung
                            worked? ___ · stale non-executive material found and rejected? ___)
       E excerpts: ___    searches logged: ___
       F excerpts: ___    public? YES / NO / N/A     10-K filing date: ___
```

The B-recency line does not block the packet. It exists so that a packet passing on count but resting on old evidence is visibly different from one passing on current evidence.

**2b. EVIDENCE COVERAGE** — for each dimension state ONLY "COVERED" / "THIN" / "NONE". No direction, no score.

```
       autonomy: ___   pace: ___   collaboration: ___
       feedback: ___   innovation: ___   decision: ___
```

**2c. LADDER CHECKLIST** — mandatory. One line per rung, even for rungs you did not need.

```
       D1 handbook          attempted Y/N   URL: ___   outcome: ___
       D2 eng/product blog  attempted Y/N   URL: ___   newest post date: ___   outcome: ___
       D3 culture microsite attempted Y/N   URL: ___   outcome: ___
       D4 leader interview  attempted Y/N   URL: ___   date: ___   outcome: ___
       D5 public repos      attempted Y/N   URL: ___   outcome: ___
       D6 press profile     attempted Y/N   URL: ___   date: ___   outcome: ___
       D7 conference talk   attempted Y/N   URL: ___   date: ___   outcome: ___
       Rungs rejected as stale (>18 months): ___
       C fallbacks tried: reviews-site job view ___  ATS param found ___  greenhouse ___
                          lever ___  workday ___  ashby ___  aggregator ___
       E news searches run: ___   queries used: ___
```

**2d. SOURCE ACCESS LOG** — every URL opened or attempted, and the outcome.

**2e. FIDELITY NOTE** — flag any `[PARAPHRASE]` and why a verbatim quote wasn't possible. Flag any posting whose open/closed status you could not confirm. Flag preserved source typos. Flag the entity-check result, including any implausible review counts.

**2f. VINTAGE BLOCK — new in v4.2. Compute, do not judge.**

```
       Review entities found: ___ (URL, count, rating, claimed/unclaimed for each)
       Review counts BY SITE, each with the ELEMENT it came from: ___
          ** never a bare number — see B3a. Counts contradict themselves on the same page. **
       Conflicting counts observed on a single page: ___
       Headline ratings BY SITE: ___ (overall, and work/life balance — record divergence)
       Job titles sampled, each with review count and the element the count came from: ___
       Per-title subratings: NOT COLLECTED — removed in v4.5, see section B
       Achievability gate run on every percentage recorded anywhere in the packet: ___ (Y/N)
       Percentages struck for failing the gate, with title and figure: ___
       Titles present but NOT sampled, with counts: ___
       Interview write-ups excluded from review lists: ___
       Newest review date BY SITE: ___   ** divergence here is the P-03/P-04 failure signature **
       Oldest review used: ___
       Median age of reviews used: ___ months
       Reviews truncated at source: ___/___  = ___%   ** >33% requires a NOTE TO RATER, see B7 **
       Source-site duplicates retained: ___
       Newest careers-page modification date: ___
       Structural events found and their dates: ___
       Does any structural event postdate the newest review?  YES / NO
```

These are facts, not judgments. Do not interpret them and do not adjust anything because of them — record them and let the rater and the model use them.

**2g. SCOPE BLOCK — new in v4.4. Record, do not correct.**

The scoring unit is the company. This block records which population each section's evidence actually came from, so that an unavoidable property of the packet is visible rather than accidental. See hard rule 8.

```
       A careers / values     population: ___  (usually company-wide)
       B employee reviews     population: ___  (the job titles sampled — be specific)
       C job postings         population: ___  (the functions posted for)
       D first-person         population: ___  (whichever org publishes — often technology)
       E news                 population: ___  (usually company-wide)
       F human capital        population: ___  (usually company-wide)

       Working environments known to exist in this company but ABSENT from the
       review population: ___
       Does the company-authored evidence (A, F) describe a wider population than the
       experiential evidence (B)?  YES / NO
```

The last line matters more than it looks. On a large company the answer is almost always YES, and it interacts directly with any scoring rule that requires non-company-authored support: the company-authored half describes everyone, the non-company-authored half describes the store floor. State it and let the rater weigh it.

**One-line scope declaration for the head of the packet** (the rater sees this, and only this, from 2g):
```
       "The employee reviews in this packet come from ___. Other parts of this company —
        ___ — are not represented in them. Company-authored sources describe the whole
        organisation."
```

```
########## SECTION 3 — ROSTER / CONFOUNDER BLOCK (NEVER IN THE PACKET) ##########
```

- Approx. headcount + date + source (for stage_index). State confidence; an old third-party figure is not a company-sourced one.
- Stage/size cues (public/private, ownership, funding stage, revenue if disclosed) + source
- Pay-posture EVIDENCE vs. talent-market peers — do NOT assign the 1–5 band. Note the correct reference class.
- Industry (tech / finance / healthcare / retail / other) + one-line justification

```
########## SECTION 4 — ANONYMIZATION PRE-FLAGS ##########
```

List every identifying token left in Section 1: company name occurrences, product and brand names, executive and author names, named clients, office locations, named internal programs and tools, and any distinctive phrase that could re-identify the company. Flag verbatim self-descriptions separately — they are searchable even after the name is removed. **Preserved source typos are unique-string identifiers; flag them.**

**On review locations:** do NOT delete them. The dispersion field depends on being able to see variation across sites. Replace specific locations with generic tokens (`[Site A]`, `[Site B]`) that preserve the distinction without naming the place.

## FINAL CHECK BEFORE YOU RETURN

- Did I run the entity check BEFORE collecting reviews, and record every entity found?
- Did I take review TEXT from Indeed, and keep Glassdoor's Pros/Cons fragments out of Section 1 entirely?
- Did I run the achievability gate on every percentage anywhere in the packet, and strike the failures rather than reconcile them?
- Is any figure in Section 1 an EVALUATIVE metric being used as evidence for a dimension? (Rule 8.)
- Did I record section D's voice composition, and work one extra rung if it came back all-executive?
- If something was unreachable, did I record the limitation precisely rather than blocking the packet? (Shipping posture.)
- Did I check every Glassdoor URL for a `KO` keyword segment before treating it as a job-title filter?
- Did I complete the scope block at 2g, and put the one-line scope declaration at the head of the packet?
- If the company is public, did I collect Item 1 Human Capital and strip every figure from it?
- Did I meet every line of the required-to-yield audit, including the C posting count?
- Is the ladder checklist complete, with all seven rungs marked and dates recorded?
- Did I apply the 18-month staleness gate to every rung, not just the blog?
- Did I complete the vintage block, and add a NOTE TO RATER if it warrants one?
- Did I confirm each quoted posting is currently open?
- Did I place the company on ANY dimension or use a judging adjective? Remove it.
- Is every excerpt verbatim, on its own line, with attribution, a URL and a date?
- Did I preserve review job titles and locations, and strip locations and pay bands from job posts?
- Are confounders kept OUT of Section 1 and only in Section 3?

---

## APPENDIX — DEFECT REGISTER. Read this before you start. New in v4.6.

Every defect below was found by building a real packet. Each one cost a rebuild or shipped a wrong
finding. **They are listed here, in the prompt, because the single most expensive lesson of this
project is that a rule living only in a handoff is not a rule** — the achievability gate sat in a
handoff for three days and three packets shipped impossible percentages in the meantime.

**The meta-pattern, if you read nothing else: AN EMPTY OR IMPLAUSIBLE RESPONSE IS NOT AN ABSENCE.**
Seven variants are now on record. Before you write "not found", ask what the tool would have shown
if the thing existed, and try the other retrieval method.

| # | Defect | Found on |
|---|---|---|
| D1 | The two review sites are complementary, not substitutable; v4.3 picked the wrong one for text. | P-02 |
| D2 | Glassdoor's `KO<start>,<end>` URL segment is the KEYWORD filter, not the job-title filter. A keyword pseudo-bucket recorded as a title corrupts everything taken from it. | P-02 |
| D3 | Glassdoor's "top reviewed jobs" block truncates on a large company; the real index is elsewhere. | P-02 |
| D4 | Counts contradict themselves WITHIN a single page, on both sites, at every scale. Record the element the number came from, never a bare count. Intermittent, not systematic — 1 of 4 titles on P-02. | P-02, P-03 |
| D5 | Section F (10-K human capital) was decided in on 2026-08-10 and existed in no prompt version. Unnoticed because every earlier company was private. | P-02 |
| D6 | The "sample one title outside the core function" rule inverts on a large retailer. | P-02 |
| D7 | Source truncation is systematic, not incidental — a LENGTH-BASED selection effect. Reviews that survive in full are the short ones, so the detailed accounts are the ones you read only the opening of. Flag it to the rater when it exceeds a third of the sample. | P-02, P-04 |
| D8 | Duplicate rule numbering in Section B (two each of B2, B3, B4). | v4.3 |
| D9 | Sections A and F describe a wider population than B. Always true; say so in 2g. | P-02 |
| D10 | The same job title appears in two function categories with different counts and ratings. | P-02 |
| D11 | Category labels are not function labels — "Software Development" was mostly in-store tech support. | P-02 |
| D12 | Section A's primary route is JavaScript-gated and it had no fallback chain. | P-02 |
| D13 | **The renderer is NOT strictly better than plain fetch — they reach different sources.** Minutes after the renderer retrieved a JS-gated careers page, the same renderer was bot-walled to a sign-in page on an aggregator that plain fetch had returned in full. Renderer → first-party JS sites. Plain fetch → aggregators. Try both before recording an absence. | P-02 |
| D14 | Section D can return 100% EXECUTIVE voice on a large public company, structurally: executive interviews are published continuously, employee stories rarely, so the staleness gate strips the non-executive voice and leaves the executive one. Makes D's voice a function of `stage_size`. See D0. | P-02 |
| D15 | In Section F the identifying content and the dimension-bearing content are the SAME SENTENCES. Named internal programmes are both the best evidence and instant fingerprints. Rewrite the proper noun, keep the clause. | P-02 |
| D16 | `browse-edgar` returns an empty document at every variant including `&output=atom`; `data.sec.gov/submissions` truncates mid-array. Fetch the archive document directly. | P-02, confirmed P-01 |
| D17 | **Percentages that are arithmetically impossible at their stated n shipped in three separate packets** and one of them was the sole support for a model-level claim. See hard rule 9. | P-03, P-04, P-05 |
| D18 | **STRATIFYING BY JOB TITLE SELECTS STALE EVIDENCE** when review volume is low or the role mix has turned over. Largest bucket's newest review was 31 months old while the company-wide stream was four months old. Cause of the v4.6 frame change. | P-01 |
| D19 | Recent reviews are frequently posted with NO job title. Under a title frame they are uncollectable; they are also unassignable to a function in 2g. See B2a. | P-01 |
| D20 | Employer RESPONSES sit inside the review stream. Company-authored content wearing an experiential source's clothes. See B2b. | P-01 |
| D21 | The job-titles INDEX omitted a title that the reviews page listed FIRST under "popular job titles", and which carries recent reviews. The index is not authoritative. | P-01 |

## Appendix — change history

### v4.6 — after P-01 broke the v4.5 sampling frame on its first section

Written 2026-08-13. v4.5 never had a clean-room run; no packet was built under it.

1. **SECTION B'S FRAME IS NOW RECENCY, NOT JOB TITLE (B2).** P-01's largest title bucket had zero
   reviews inside the 24-month gate while the company-wide stream was entirely inside it. The title
   frame works only when review volume is high and the role mix is stable, and it fails silently.
   Title becomes per-review metadata; the function mix is reported, not imposed. The title index is
   still collected — it is how you detect what the review population is — but it is not the frame.
2. **Untitled reviews are collected (B2a).** Excluding them drops the newest evidence at exactly the
   companies where recency is scarcest.
3. **Employer responses are tagged `[employer response]` (B2b)** and never counted as employee
   reviews or as non-company-authored support.
4. **A DEFECT REGISTER now sits in the prompt**, D1–D21, with the source packet for each. Rules that
   live only in handoffs do not propagate; that failure has now cost three packets.

### v4.5 — after finishing P-02, and the first version that is about SHIPPING

Written 2026-08-13, immediately after P-02 reached full yield on every gate. Five changes, four of
which delete or bound something rather than add to it. That is deliberate: v4.2, v4.3 and v4.4 each
grew the prompt in response to a defect, and the instrument was accumulating requirements faster
than packets.

1. **SHIPPING POSTURE AND A FREEZE RULE, at the top of the prompt.** The target is a packet good
   enough to iterate on, not a correct one. The prompt freezes after the first packet that surfaces
   zero STRUCTURAL defects; cosmetic ones do not reset the counter. Without a termination condition
   the revise-as-failures-surface policy of v4.4 never ends, and every remaining company is a type
   the prompt has not seen.

2. **PER-TITLE SUBRATINGS REMOVED, and removed retroactively from P-03 and P-04.** They fail their
   own achievability check (3 of 4 in P-03, 1 of 2 testable in P-04); they could not be retrieved at
   all on P-02, which would have put one packet of six on a different instrument; and they are an
   evaluative construct being used to evidence descriptive dimensions. Glassdoor is demoted to an
   OPTIONAL recency cross-check. Indeed is now the only required review source. Within-company
   variation is captured as the dispersion ordinal from review PROSE, which is more credible
   evidence and is quotable, so a citation harness can verify it.

3. **THE ACHIEVABILITY GATE IS NOW HARD RULE 9**, applying to every percentage from every source.
   It existed from 2026-08-10 as a note in a handoff and consequently never propagated: the P-03
   packet shipped with three impossible percentages, and one of them — 24% at n=16 — was the sole
   support for a model-level claim about level effects. A rule that lives only in a handoff is not
   a rule.

4. **EVALUATIVE METRICS BARRED FROM SECTION 1 AS DIMENSION EVIDENCE — hard rule 8.** Recommendation
   rate, CEO approval, outlook and senior-management scores measure how a writer feels; the six
   dimensions describe what an environment is. On P-03 the two orderings disagreed inside one
   company. This is a construct bar, which is stronger than the reliability caution it replaces:
   sound numbers of the wrong construct are still not evidence.

5. **SECTION D VOICE COMPOSITION (D0).** P-02 returned a section D that was 100% executive voice.
   The mechanism is structural — large public companies publish executive interviews continuously
   and employee stories rarely, so the staleness gate removes the non-executive voice and leaves
   the executive one. Unaddressed, D's voice composition becomes a function of `stage_size`, a
   confounder already in the model, entering through the evidence. The prompt now requires
   recording the composition, working one bounded extra rung when D is all-executive, logging
   stale non-executive material as found-and-rejected rather than absent, and flagging the
   composition to the rater.

Also folded in: the working EDGAR route (browse-edgar is dead at every variant; fetch the archive
document directly), and the practical shape of section F figure-stripping and anonymization from its
first real use.

### v4.4 — after the first PUBLIC company (P-02)

Every company built before this one — P-03, P-04, P-05 — was private, and the largest held 34
reviews. P-02 holds roughly 40,000 on each site and files a 10-K. Six of the eight defects below were
invisible until a company of that type went through the prompt. Full evidence in
`V43_DEFECTS_LOG.md`.

**1. The two review sites do different jobs, and v4.3 assigned the wrong one to text.** The central
change. v4.3 made Glassdoor the frame because it holds more reviews and carries per-title subratings.
Both true; the conclusion was wrong. Glassdoor renders review bodies as Pros/Cons bullet fragments,
three per fetch. Indeed renders continuous prose, twenty per fetch — and its title pages display
*company-wide* category ratings, so it carries no per-title numbers at all. Neither substitutes for
the other. **Indeed now supplies the text, Glassdoor supplies the subratings, and the job-title list
is the frame.** v4.3's correction to the P-03/P-04 staleness finding stands; the over-correction to
"Glassdoor is the frame" does not.

**2. v4.3's Glassdoor URL pattern was the keyword filter, not the job-title filter.** A `KO<n>,<n>`
segment is a keyword offset. Following it for "Sales" pooled 221 reviews across Sales Associate, Sales
Advisor and Sales Consultant while Sales Associate alone holds 4,876. Every subrating captured that
way is scoped to a string match rather than a role.

**3. The "top reviewed jobs" block does not render on a large company.** It sits in a collapsed FAQ
and truncates after two entries. The full title index is on Indeed at `/browse-reviews` and
`/job-titles` — on the site v4.3 demoted.

**4. Counts contradict themselves at every scale, not just at small n.** v4.3's validation checks were
all sample-size arguments written from P-04's 14-review titles. On P-02 one Indeed page displayed
35,162 / 35,162 / 39,859 / 39.9K simultaneously, and Glassdoor's overview said 41,921 in its snapshot
and 42,168 in its own FAQ. Counts are now recorded with the element they came from, and no
site-reported total may appear in Section 1.

**5. Section F added: 10-K Item 1 Human Capital.** Decided into packets on 2026-08-10, never written
into the prompt. Nobody noticed because no public company had been built. Half the roster is public.

**6. Hard rule 8 and the scope block at 2g.** A large company contains several genuinely different
working environments, and the review population is not evenly drawn from them — P-02's popular titles
are entirely store-level while its corporate, technology and supply-chain organisations are nearly
invisible. v4.3's "sample one title outside the core function" rule, written for small firms,
*inverts* here and selects more store roles.

The scoring unit stays the company, deliberately: ground-truth input must match production input, and
a production scraper reads company-wide. But the packet is scoped either way — scoring "the company"
silently means scoring whoever posts reviews. The scope block records that property instead of
correcting it. Consequence recorded honestly in the defects log: sections A and F describe a wider
population than section B, which interacts with any rule requiring non-company-authored support.

**7. Truncation reframed as a selection effect.** v4.2 treated "Show more" as a footnote. On P-02 it
affects roughly half of all reviews, and the ones surviving intact are systematically the short ones.
Long detailed reviews are read as opening paragraphs. Above about a third, it now requires a note to
the rater.

**8. Section B rule numbering fixed.** v4.3 contained two rules each numbered B2, B3 and B4 — an
editing artifact of the v4.2→v4.3 rewrite. The prompt is an instrument and its rules get cited by
number in packet QA blocks.

### v4.3 — after testing the review sources properly

v4.2 was built on a false premise about where employee reviews live, and it produced two packets with wrong headline findings. The correction is the whole of this version.

**What went wrong.** Glassdoor's whole-company review listing returns an empty document on fetch, and that was recorded as "Glassdoor unusable." It is not. Individual review permalinks render — v4.1 already said so — and **job-title-filtered review pages render fully, newest-first, three per page, with predictable pagination**. Nobody tested those routes. Section B was therefore built entirely from Indeed, which held 22 reviews for P-03 and 34 for P-04 against roughly 150 and **768** on Glassdoor.

The consequence was not a minor sampling issue. Both packets concluded that the companies' reviews were years stale — P-04's stated that its newest review predated an ownership change, layoffs and a leadership replacement, and told the rater so in a prominent note. Glassdoor holds reviews for both companies from 2026, including one from a P-04 tech director titled "3 Layoffs in a Year?". The staleness finding was an artifact of the source, not a fact about the companies.

This is the same failure as the `/insights` blog miss and the JavaScript-gated careers page: **an empty response was read as an absence.** It has now happened three times in three sections. The proof-of-absence rule exists for exactly this and must be applied to every source class, including ones a previous version of this prompt already told you how to reach.

**Four changes follow.**

1. **Section B is now sampled stratified by job title, newest-first within each title.** This is deterministic, reproducible, paginated, and selects on nothing but date within a bucket — so rule 6 holds. It is also stratified by function, which is what the dispersion field actually needs.
2. **Per-title subratings are captured.** Each title page carries six category ratings. That is within-company variation as numbers rather than prose: on P-03, Junior Traders rated senior management 2.8 and work/life balance 3.6 against a company-wide 4.2.
3. **Cross-site rating divergence is recorded, never reconciled.** The same company scored 4.2 and 3.1 on work-life balance on the two sites. Both go in the vintage block. Averaging them or picking one destroys the signal.
4. **Interview write-ups are excluded and logged, and job titles are normalised before bucketing.** Both surfaced immediately in the first stratified sample.

Also recorded: the stratified frame surfaced a P-03 review from Sydney, where the Indeed set showed only Chicago. The company had been treated as single-site on the strength of the thinner source.

### v4.2 — after building packets P-03 and P-04

P-03 (a private trading firm) failed sections D and E outright despite a fully-worked ladder: no blog, no handbook, an empty public repository org, a nine-year-old leadership interview, and no credible reporting in twelve months. P-04 (a mid-sized agency) produced a rich careers page and substantial news coverage but its newest employee review was two and a half years old — from a review profile marked unclaimed and holding implausibly few reviews for the company's size. Six changes follow.

**1. Sections split into required-to-YIELD and required-to-ATTEMPT.** The single most important change. D and E availability tracks ownership, size and press profile rather than how a company works, so gating on their yield systematically fails small private companies — which correlates with `stage_size`, a confounder already in the model. Every packet still works the same ladder; only the pass condition differs.

**2. Entity check added to section B.** P-04's review profile was named "<Company> Careers Page", marked unclaimed, and held 34 reviews and 5 salary records for an agency of over a thousand people. A single-entity assumption is unsafe and every packet built on one inherits the risk.

**3. The staleness gate is now general.** It previously applied only to ladder rung 2, where it correctly rejected a 2018 article during the P-01 build. It did not cover rung 4, which is how a 2017 leadership interview reached the P-03 packet, and it did not cover reviews at all.

**4. Review-recency line added to the yield audit, and a vintage block added at 2f.** P-03 passed the B quota on count while thirteen of its fifteen reviews were older than 24 months. P-04's newest review predated an ownership change, layoffs, a leadership replacement and a service reorganisation — so its review section and its news section described two different organisations, with nothing in the packet to say so. The vintage block is researcher-computed rather than rater-judged: these are facts, and rater time is the scarce resource.

**5. Ladder rung 7 added: conference talks.** Rungs 1, 2 and 5 all reward companies that publish. Private technical firms present at conferences for recruiting even when they publish nothing else. Honest note: this rung returned nothing for P-03, though peer firms in the same specialism do present. Retained because it costs one search and targets exactly the population that fails the other rungs.

**6. Section C routing rewritten after finishing P-04.** Three additions, all from that build. The Greenhouse **list API** is now an explicit step — it fetched cleanly when the board page, the embed board and the detail API all returned empty documents, and it answers the open/closed question directly. Aggregator **machine-written summaries** are explicitly banned, because they sit directly above the real posting body and read exactly like source text. And every posting must now be **opened individually to check for a removal notice**: an aggregator listing showed six roles as recent, four were opened, and three of the four were already closed, each saying so only on its own page.

**7. Truncation, duplicate and typo handling specified.** All three surfaced in P-03 and P-04 and none were covered: review sites cut long reviews at "Show more" and do not expand on fetch; two entries appeared with identical text and date under different IDs; and a careers page carried typographical errors that are both verbatim-required and uniquely identifying.

### v4.1 — after building packet P-01

The v4 text was adequate; the first P-01 run failed anyway. Rungs 1 and 2 of the section D ladder were never attempted, and no news search was run — the ladder was prose, and prose gets read past. Both sections came back short. Reworking them properly, without changing a word of the prompt, moved innovation and decision from THIN to COVERED and took the packet from 9,613 to 11,232 characters. Four changes followed.

1. **The ladder became a returnable checklist.** Every rung must be marked attempted with a URL and an outcome, including rungs that weren't needed. An unattempted rung is a failed packet rather than a thin one.
2. **Reviews lead with the Indeed listing, not Glassdoor permalinks.** The Indeed company reviews page returned roughly 20 reviews in one fetch, newest-first, with date, role and location. Glassdoor permalinks returned three per fetch.
3. **Section D: open the blog index, not a topic search.** Topic search surfaced a 2018 article, rejected as stale. The publication index surfaced a May 2026 article that carried two dimensions on its own.
4. **Section C binds on posting count, not just excerpt count.** P-01 produced twelve job-post excerpts and still failed, because all twelve came from one engineering posting that had been closed since January 2025.

### v4 — after measuring the 19 v3 packets

Measured composition: employee reviews 48.4% of the corpus, careers/values 20.5%, news 12.0%, blog/culture 10.4%, job postings 8.7% — 19 lines total across all 19 companies. Blog/culture was an empty stub in 7 of 19.

v3 asked for "~15 most recent reviews" (a count of the thing quoted) but "2–3 current postings" (a count of pages opened), so the researcher opened three postings and wrote one summary line. Quotas moved from sources to excerpts; section C raised and re-pointed at responsibility language; section D turned into a ladder; locations and pay bands removed from job-post capture; one excerpt per line enforced; and the yield audit added.
