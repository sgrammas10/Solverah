# Packet anonymization — ruleset

**Status: SIGNED OFF 2026-08-15 by Sebastian.** R1–R8 and JC-1 through JC-4 stand as written below,
with the three P-06 amendments recorded in "Amendments from P-06" immediately after the rules.
Derived by running the pass by hand on P-01, then applied to P-02 through P-06.

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
