# Packet anonymization — ruleset

**Status: SIGNED OFF 2026-08-15 by Sebastian.** R1–R8 and JC-1 through JC-4 stand as written below,
with the P-06 amendments (A1–A4) recorded in "Amendments from P-06" immediately after the rules.
Derived by running the pass by hand on P-01, then applied to P-02 through P-06.

**AMENDED 2026-09-07 — A5, A6, A7, from the first prompt-driven scrub (P-07).** See
"Amendments from P-07". A5 extends R4 to branded names generally; A6 puts R5 inside quote
bodies and permits minting a token where the pre-flag block does not reach; A7 settles that
review headlines are kept. **Every packet scrubbed before 2026-09-07 predates all three**, and
P-01–P-06 additionally predate A3 and A4 — a mechanical check on 2026-09-06 found P-01 short one
section F excerpt (original R8, which A3 reversed) and carrying three undeclared quote-body edits
(the defect A4 was written for). **Those six are not to be re-scrubbed.** They are the bytes round 1
was rated against and the 18 returned rater JSONs are tied to them; re-scrubbing would orphan that
data. The divergence is recorded, not corrected.

**Destination — CHANGED 2026-08-15.** The earlier plan was to fold these rules into the collector
prompt as v4.7 so Section 1 is born anonymized. That is superseded. **Anonymization becomes a
separate second pass with its own prompt, run against a finished packet.** Reasoning in
"Why a separate pass" at the end of this document. The collector prompt keeps only the pre-flag
block (Section 4), which is the input the scrub pass reads.

---

## The governing principle

**Scrub identifiers, not signal.**

This is narrower than the instinct, and the reasoning matters more than the rule.

There are two distinct threats and they have been getting bundled:

| | Threat | Mechanism | Fixable by scrubbing? |
|---|---|---|---|
| **T1** | Rater **recognises** the company while reading | Memory | **No** |
| **T2** | Rater **looks it up** | Search | Yes — but by removing URLs and forbidding search, not by editing quotes |

T1 is the one that damages the data, because prior leakage is directional and correlates with company
fame, so it survives aggregation. T1 is also the one you already decided you cannot eliminate — the
recognition Y/N flag exists for exactly this, and the 08-10 handoff records the instruction not to
over-correct on it. Julie identified Wayfair from a far more conservative packet, from memory.

T2 is a protocol violation, not an instrument property. It is fixed by deleting URLs, telling raters
not to search, and asking them at submit whether they did.

Neither threat is reduced by rewriting a quote body. So quote bodies stay verbatim, and the cost of
rewriting them is high:

* **It breaks the citation-verification harness.** Human raters will be asked for the verbatim quote
  behind each score, and the harness string-matches that quote against packet text. Same mechanism
  is planned for the LLM in production. A paraphrased packet cannot be verified against anything.
* **Every rewrite is an uncontrolled edit to the instrument**, made by hand, differently each time,
  on the one artifact the whole calibration set depends on. Six packets × ~60 excerpts is ~360
  opportunities to change what a rater reads.
* **The distinctive phrases are the culture signal.** "No genius without grit. Be relentless. Be
  scrappy" is both the most identifying string in Section A and its highest-information line on pace
  and innovation. Scrubbing it deletes the measurement.

---

## Rules

### R1 — Attribution lines: strip the name and the URL, keep the source class and the date

The source tag is load-bearing (the proposed 0.7 rule turns on company-authored vs. not) and the date
is load-bearing (the recency/vintage notes). The company name and URL are pure identifier.

```
BEFORE  — [company values page] — Oscar Health (company-authored, value 03) — https://www.hioscar.com/careers — retrieved 2026-08-13 (needed JS: N)
AFTER   — [company values page] — company-authored — retrieved 2026-08-13 (needed JS: N)
```

Review URLs additionally carry a **slug derived from the review title** (`/reviews/don-t-trust-anyone`,
`/reviews/run-don-t-walk`). Exact-match searchable. Replace the whole URL with a stable local ID
(`rev-01` … `rev-15`) so scores remain traceable to a specific review without the string being
lookup-able.

### R2 — Company name inside a quote body: substitute, don't delete

The only place a quote body gets edited. `[the company]`, preserving grammar.

```
BEFORE  "Oscar is a great company to work for, but sometimes unorganized!"
AFTER   "[The company] is a great company to work for, but sometimes unorganized!"
```

**Spec requirement this creates:** the citation-verification harness must normalise `[the company]`
before string-matching, or every quote containing a substitution fails verification. Add to the
harness spec now, not after it is written.

### R3 — Named humans: strip the name, keep the role

Role is load-bearing (scope, voice composition, the D0 executive rung). The name is not.

```
Yvonne Wang, Senior Product Designer at Oscar  →  a Senior Product Designer
"Bertolini said"                               →  "[the chief executive] said"
```

Also applies to journalist bylines → publication class only (`trade press`, `business press`).

### R4 — Named internal programmes: rewrite the proper noun, keep the clause

Per Section 4's own instruction. `Executive Speaker series` → `an executive speaker series`. The
practice is the signal; the branded name is the fingerprint.

### R5 — Locations: tokenise places, preserve "Remote"

Section 4 already specifies this and it is right. Dispersion depends on seeing that sites differ, not
which they are. `Remote` is a work-mode carrying autonomy and collaboration signal — keep it literal.
`not stated` stays `not stated`.

### R6 — Strip figures in Section E, not just Section F

**This is a gap in the current prompt.** Section F strips every headcount, dollar figure and
percentage by rule. Section E carries `$60 million in administrative cost savings` and
`a $137 million third quarter loss` with no such protection. A specific loss figure plus a quarter is
a one-query identification, and Section E is the *lowest* dimension-signal section in the packet —
it is context on stability, not on how people work. The figures cost nothing to remove.

Replace with magnitude language: `a substantial third-quarter loss`.

### R7 — Preserved source typos: keep

`there [sic]`, `every roll [sic]`, `bexause`, `labtop`, `horrible.The`. Each is a one-query search
string, so they are a T2 exposure only, and R1 has already removed the review URLs. They are
verbatim-required and they are not identifiers. Keep, and note the exposure in the run record.

---

---

## Amendments from P-06 — DECIDED 2026-08-15

**A1 — R6 now covers every section, not just E and F.** Read R6 as *"strip identifying figures
wherever they appear, in any section, replacing them with magnitude language."* P-06's Section D
carried an advisor headcount inside a quote: a one-query identification inside that company's peer
set, in a sentence whose actual claim survives the strip untouched. Precedent already existed —
P-02 applied magnitude language inside an E quote body — so only the section was new.

**A2 — where JC-1 and R4 collide, R4 wins on the branded token and JC-1 keeps the rest of the
sentence.** P-06 had a named five-behaviour list sitting inside a values statement. Split applied:
generalise the branded list, keep the values clause. The test is dimension signal per unit of
fingerprint — a list of internal behaviour names is near-pure fingerprint, while a values clause
naming independence and a conservative long-term posture is direct autonomy, pace and innovation
evidence. Expect this collision on any company with named internal behaviours.

**A3 — R8 is executed as a rater-facing recurrence note, not as a deletion.** When a claim appears
in both A and F, keep both excerpts and attach a note to the second telling the rater it is one
claim appearing twice, not two sources agreeing. This achieves R8's purpose — preventing false
triangulation inside the company-authored layer — without changing the excerpt count, and it keeps
the fact that the claim reached a legal filing visible as evidence in its own right. Deleting the
second copy would have destroyed that.

**A4 — every substitution is bracketed ON THE EXCERPT LINE.** Not only in the scrub log. The
fidelity audit of 2026-08-15 found two real quote-body edits (P-01's `Executive Speaker series` →
`executive speaker series`, P-02's `Ethan said` → `the same intern said`) that were correct
applications of R4 and R3 respectively but were invisible where a rater would encounter them. One
was declared in a scrub log nobody reads while rating. **An edit recorded only in a scrub log is
not a recorded edit** — the same shape as "a rule that lives only in a handoff is not a rule."

## Amendments from P-07 — DECIDED 2026-09-07

The first packet scrubbed by prompt rather than by hand. All three came from the scrub pass
flagging a gap and declining to close it on its own initiative, which is the behaviour the
brief asks for — each is recorded here so the next scrubber looks it up instead of deciding
it again.

**A5 — R4 covers BRANDED NAMES generally, not only internal programmes.** Read R4 as
*"rewrite the branded proper noun, keep the clause"* across internal programmes, external
brand names, joint ventures, subsidiaries, and internal organisation abbreviations. P-07
carried an energy-technology brand and a named battery joint venture inside quote bodies,
plus an internal works-unit abbreviation across three review excerpts. Each is a one-query
identification at least as strong as the company name R2 already removes, and in every case
the surrounding clause survives the rewrite untouched — which is the test. The scrub pass
extended R4 to all three and declared each on its line; this amendment makes that a lookup
rather than a judgment call, so two scrubbers cannot answer it differently.

**A6 — R5 applies inside quote bodies, and a place with no pre-flag token gets one minted.**
The scrub brief originally permitted in-body edits only for places already tokenised in the
Section 4 pre-flag block, to keep the substitution mechanical. P-07 showed the cost: its
section E layoff excerpt names a state employment agency and a county inside a quote body,
neither pre-flagged, so both correctly survived into the rater-facing packet. A WARN filing
plus a named state agency plus a county plus a date is a stronger identification than the
city names R5 already removes.

So: **tokenise it, mint a new token if none exists, and log every minted token with the
string it replaced.** Reuse the attribution's token where one exists — a rater who sees
`[Site G]` in an attribution and the city printed one clause later is worse off than under
either consistent answer.

**A6(a) — CORRECTED 2026-09-07, hours after A6 was written, by the run that first applied
it.** The mapping goes in the **diff file or the run record. Never in the packet's own
scrub log.** The scrub log sits after `########## END OF PACKET ##########` in the
rater-facing file, so "`Marshall County` → `[County A]`" written there hands the rater the
identifier the substitution just removed — the scrub log undoing the scrub, one screen
below it. The packet's log records only that a token was minted and how many; the string it
replaced lives where the rater never looks. Applies to every rule that logs a removed
string, not only R5.

**This also records a build-side gap, which is the durable fix.** The Section 4 pre-flag
block does not reach past section B. Minting keeps today's packets clean; extending the
pre-flag block across every section is what stops the scrubber from having to mint at all.

**A7 — review headlines are KEPT, and this is now explicit rather than an omission.** R1
replaces review URLs partly *because the slug derives from the headline* — and the packet
then prints that headline in the attribution, leaving the same exact-match search string by
another route. That is a real hole and it was correctly flagged rather than patched
mid-scrub.

It is nonetheless the same trade R7 already settles for preserved source typos: an
exact-match searchable string is **T2 exposure**, and T2 *"is a protocol violation, not an
instrument property."* Raters are instructed not to search and are asked at submit whether
they did. Against that, the headline is the reviewer's own words and carries evidence — P-07's
CD-2 turns on a headline contradicting its own review body, which is a signal that only
exists because the headline is there.

**Keep headlines verbatim. Record the exposure in the run record, as R7 does. Do not strip
them, and do not re-open this per packet.**

---

## Amendments from P-09 — DECIDED 2026-09-07

Both came from the scrub pass flagging a gap and declining to close it alone, which is the
behaviour the brief asks for. Recorded here so the next scrubber looks them up instead of
deciding them a third time.

**A8 — R1 covers SOURCE-SYSTEM RECORD IDS wherever they are printed, not only inside a URL.**
Read R1's rev-NN treatment as covering any id that resolves to a source record: ATS posting
and requisition ids, review ids, req numbers, order numbers. Replace each with a stable local
token numbered within its section — `[posting 1]` … `[posting 5]` — so the fact that five
distinct postings across five functions were sampled stays visible and traceable to a rater,
while the searchable string does not survive.

P-09 is why. Its five ATS posting ids appeared in the attribution as plain text *as well as*
inside the URL. R1 stripped them from the URL and left them in the attribution, and one was an
alphanumeric requisition string — an exact-match token that resolves straight to the company's
job board. Every ATS-sourced packet will hit this, so it is a rule, not a judgment call.

**The ATS vendor name stays.** A recruiting platform used by thousands of employers is
retrieval-method signal, not a company fingerprint. The identifying hostname goes with the URL.

**A6(a) governs how you log this, and P-09 is also the packet that proved why.** Its scrub log
explained the removal by printing all five ids verbatim. The log sits after
`########## END OF PACKET ##########`, so the citation harness never reads it and a rater
always does — the scrub undone one screen below itself, exactly as A6(a) describes. Record the
count and the shape of what was removed. The strings go in the diff.

**A9 — R8 keys on COMPANY VOICE ON BOTH SIDES, not on the A↔F section pair.** Read R8 as
*"where a company-authored claim is reproduced by another company-authored source, attach the
recurrence note"* — whichever sections those two happen to be. The pair was never the point:
what R8 prevents is a rater reading one company voice twice and counting it as corroboration.

P-09's section D is three-quarters corporate voice, and one passage restates a section A claim
in different words while quoting an A core value inside its own parenthesis. That is the
false-triangulation pattern in full, across a boundary R8 as written did not reach. Under A3
the treatment stays a rater-facing recurrence note; nothing is deleted.

This has a build-side cause and the scrub cannot fix it: defect S-3 records that the collector
has no slot for corporate voice in section D, which is how D filled up with it. Amending R8
stops the damage reaching a rater. It does not stop section D being the wrong shape.

---

## OPEN — reviewer-level re-identification. Flag it; do not decide it.

**Status: undecided as of 2026-09-07. A scrubber that meets this leaves it alone, records the
exposure in the run record, and moves on.** Do not soften titles on your own initiative and do
not treat this section's existence as authorisation.

P-09 carries four review titles that are near-unique in the source's own index — two appear
exactly once — each sitting beside a site token and a date. That combination identifies a
**reviewer**, not the company, which is a category this ruleset has never covered: every rule
above is written to protect the employer's identity.

It collides with the industry finding directly. Titles carry sector and function signal that
raters score on, and the finding is explicit that industry is not scrubbable and must not be
attempted. Whatever is decided has to preserve that signal.

Two constraints on whoever decides it. P-01 through P-06 are frozen against the eighteen round-1
rater JSONs and cannot be re-scrubbed, so any rule here applies forward only. **Updated 2026-09-07:
the original wording named P-10 as the earliest boundary; P-10 has since been scrubbed without such a
rule, so the earliest reachable boundary is now P-11, or P-07 with four re-scrubs.** Either way the
set becomes deliberately inconsistent on this axis, the second such re-baseline after A21. And the exposure is T2 under R7's own framing: raters are
instructed not to search and are asked at submit whether they did.

---

## What anonymization CANNOT do — record this rather than fight it

**Industry is not scrubbable and should not be attempted.** P-01's job titles alone —
Utilization Review Nurse, Care Guide, Complex Case Manager, Insurance Operations Claims Processor —
identify the sector before any careers-page copy is read. The same will be true of every packet.

This qualifies a standing claim. The roster protocol says confounders stay out of the packet because
they would re-identify. That holds for `stage_size` and `comp`. It does **not** hold for `industry`,
which is inferable from any real packet and is adjusted for in the model anyway. Stop treating it as
a leak.

---

## JUDGMENT CALLS — need your decision before I touch P-02 to P-06

### R8 — A↔F double-counting must key on the CLAIM, not the sentence  *(v4.7 spec finding)*

DEF-5 added a no-double-count rule for the A↔F boundary and the builder applied it correctly to the
seven value names — quoted once in A, different sentences taken for F. But the rule is written
against duplicate *sentences*, so a reworded restatement passes it. One did:

* A, careers page: "powered by people from all kinds of backgrounds … make a frustrating healthcare
  system easier, more human and better for absolutely everyone"
* F, 10-K: "powered by people from varied and broad backgrounds … making a frustrating healthcare
  system easier, more human, and better for everyone"

Not an identification problem — an evidence-weighting one. The rater sees a careers page and a legal
filing and reads two independent company voices. It is one claim in two costumes. Under the
triangulation principle, apparent agreement across sources is exactly what raises confidence, so the
packet manufactures a false triangulation *within* the company-authored layer.

Rule: when a claim appears in both A and F in any form, quote it once and note that it recurs in the
other source. The recurrence is itself informative — it says the culture claim is load-bearing enough
to enter a legal filing — but it must be visible as recurrence, not presented as corroboration.

---

## JUDGMENT CALLS

**JC-1. Do distinctive verbatim self-descriptions stay? — DECIDED 2026-08-14: YES, keep.**
The specific strings at stake in P-01:
* "the first health insurance company built around a full stack technology platform" — near-unique,
  appears in Section A **and** all three Section C postings
* "making a frustrating healthcare system easier, more human, and better for everyone" — Section A
  **and** Section F
* the seven value names, appearing verbatim in Section A **and** again inside the 10-K

Section 4 flags the duplication as itself a tell. It is — but the duplication is also real evidence
(the company says the same thing in its careers copy and its legal filing, which is a signal about
how declared the culture is). Deleting the Section F copies would remove that.
**Default if you don't object: keep all of them.**

**JC-2. Section E — keep it at all?**
Three excerpts, all trade/business press, all about layoffs, losses and profitability guidance. After
R3 and R6 strip the executive, the publications and the figures, what remains is roughly "the insurer
is cutting costs and expects to return to profitability." That is near-zero dimension signal at
non-trivial re-identification cost. The alternative view: layoffs and constant reorganisation are
directly relevant to pace and autonomy, and several reviews reference exactly that, so Section E
corroborates them from a non-company-authored source — which is precisely what the proposed 0.7 rule
requires. **I lean keep, scrubbed hard.** Your call.

**JC-3. Does the scrubbed packet become the canonical artifact?**
It has to, if the citation-verification harness is going to work — humans and the LLM must score the
same bytes. That means the raw packet becomes a build record, and the scrubbed file becomes
`P-0X_packet_RATER.txt`, versioned, never edited after a rater opens it. Confirming because it
changes what "the packet" refers to in every other document.

**JC-4. The scope declaration names the sector** ("a health insurer"). Under the industry finding
above this is harmless and it makes the scope block readable. Keep as written?

---

## Why a separate pass — DECIDED 2026-08-15

Superseding the original "fold it into v4.7" plan.

**1. A fused prompt destroys the baseline you need to verify the scrub against.** If Section 1 is
born anonymized, the unscrubbed version never exists, so nothing can be diffed. The fidelity audit
that caught the em-dash drift and the two undeclared edits was only possible because a raw packet
and a scrubbed packet both existed. A scrub you cannot diff is a scrub you are trusting rather than
checking, and this project's whole posture is that a rule which cannot fire mechanically does not
hold.

**2. The two artifacts are both wanted anyway.** The raw packet is the build record. The scrubbed
packet is the canonical rater artifact under JC-3. A fused prompt produces one file where the
design calls for two.

**3. The rules will keep moving; collection is expensive and scrubbing is cheap.** R6's scope,
R8's execution and the named-clients rule all changed after five packets were already scrubbed.
Decoupled, a ruleset change costs one cheap text pass over existing packets. Fused, it costs a full
re-collection against websites that have since changed — and the packet you get back is not the
same packet.

**4. The collector is already over-loaded.** v4.2 through v4.6 each grew in response to a defect,
and 08-13b records the instrument accumulating requirements faster than it accumulated packets.
Adding eight scrub rules to a prompt already carrying nine hard rules, seven ladder rungs and a
D1–D21 defect register makes every rule compete for attention with every other one.

**5. A scrub is deterministic work wearing an LLM costume.** No retrieval, no judgment on most of
it. Which points at the real architecture, three parts not one:

* **A script** for the mechanical majority — strip URLs, assign `rev-NN` IDs, tokenise locations,
  substitute a supplied name list, bracket every substitution. Byte-exact, unit-testable, and it
  **cannot produce the em-dash class of bug at all, because it never retypes the file.** That bug
  exists purely because a model re-emitted a whole packet from scratch; a patch operation has no
  opportunity to introduce it.
* **A prompt** for the judgment minority — which distinctive phrase is a fingerprint, R4 rewrites,
  magnitude language for figures. It should emit a change list, not a rewritten file.
* **A verifier** — the fidelity audit run as a script on every packet, with normalisation covering
  whitespace, smart quotes, dashes and the `[the company]` token. This is the same harness the
  citation-verification work needs, so it is not extra work; it is that work, arriving early.

---

## Does the scrub belong in production? — DECIDED 2026-08-15: YES

**Decision: production packets are scrubbed before scoring. The scrub is a pipeline stage, not
only a ground-truth-set tool.**

This overturns the reading carried since 08-07 that anonymization is purely a test instrument. That
reading rested on "a production scraper always knows which company it is scraping" — which is true
of the **scraper** and irrelevant to the **scorer**. They are separate calls. The scorer conditions
only on what the packet contains, so deleting the name deletes something real to condition on.
That is categorically different from prompting a model to ignore what it knows, which is the thing
08-07 correctly established does not work — a model can be denied a cue, it cannot ablate a prior
on request.

**The evidence.** Test 1 (08-07, GT-01): the identified run explained a dimension with "the overall
business remains a mature retailer" and cited "rapid top-down changes with little notice" — neither
in the packet, both tracking the real company. The blind run explained the same dimension from the
job posts. Test 2 destroyed every numeric delta in Test 1, but not this: sampling variance does not
invent facts that track a specific real company. Leakage is demonstrated by content, not by numbers.

### What this does NOT establish, and must not be overclaimed

1. **Anonymization reduces prior conditioning. It does not produce blindness.** Julie identified
   GT-01 from a *more conservative* packet than Test 1's, from memory. A frontier model is better at
   that inference than a human expert, not worse. A scrubbed production packet is a packet the
   scorer will often still place. So the scrub cannot be the only control.
2. **Citation verification remains the control that catches the residual**, and it would have caught
   both out-of-packet phrases mechanically, by string-match, without any scrub. **The two are
   layered, not alternatives.** Scrub lowers the rate; the harness catches what gets through. An
   earlier draft of this document framed them as competing. That was wrong.
3. **n = 1 per condition.** Two phrases prove leakage *can* occur. They do not measure how often, or
   how much scrubbing reduces it. Re-running Test 1 at n=5 per condition (carried open item) is now
   load-bearing on a production design decision, not just on a disagreement with Julie.

### Two consequences that follow immediately

* **JC-3 is settled by force, not by judgment.** If the scorer reads the scrubbed packet, the
  scrubbed packet *is* the packet, and the citation harness matches against it. The raw packet
  becomes a build record only.
* **This is an argument FOR the script form, not against it.** In production the scraper already
  holds the company name, executive names and locations as metadata, so substitution becomes a
  lookup rather than an inference — the mechanical majority gets *more* mechanical, and the
  judgment minority shrinks.

### The benefit nobody argued for, which may be the largest one

Scrubbing production packets makes **production input match ground-truth input**. That constraint
has been outstanding since July — first as the objection to hand-researching filings for the
ground-truth set, then again as 08-10's open item 7 on stratified sampling being unreproducible at
scale. The recurring failure mode is calibrating the extractor against input it will never see in
production. Scrubbing both sides is one of the few decisions that makes the two converge rather
than drift further apart.
