# Solverah — Session Handoff, 2026-08-15 (second session of the day)

**Topic: P-06 scrubbed, the anonymization ruleset ratified and amended, the production-scrub
question reversed, three freeze decisions, the full rater grid built and hardened, packets made
addressable, and open question 5 closed.**
Custom instruction to honor: be logical and future-thinking, do not be agreeable — push back.

Sits on top of `SOLVERAH_HANDOFF_2026-08-15.md` (rater pages, scrubbing pass, the rater-plan
reversal). Supersedes it on two points, both marked SUPERSEDES below.

> **The reading order at the top of the 08-15 handoff still stands.** Read all five prior
> handoffs plus `RUN_CARD.md`, `anonymization/_STATE.md` and
> `anonymization/ANONYMIZATION_RULES_DRAFT.md` before acting. These files contradict each other by
> design; a later file does not supersede an earlier one unless it says so.

---

## Headline: the raters are unblocked. Nothing else is waiting on this workstream.

Eighteen scoring pages exist — six packets × three raters — against frozen packets and frozen
anchors. Instructions and a counterbalanced schedule are written. The remaining work before files
go out is administrative.

---

## What was done

### 1. P-06 Raymond James scrubbed — the anonymization pass is complete on all six

`anonymization/P-06_packet_ANON.txt`. 46 excerpts (A8/B15/C10/D4/E3/F6). Verified: 30 quote bodies
byte-identical to the source packet, 16 carrying bracketed substitutions with every unbracketed
fragment over 25 characters checked against source, zero mismatches. Identifier sweep clean on the
company name, "RJ", both executives, the complex manager's first name inside reported speech, both
reporters, the named acquisition, the named AI tool, all five cities, all URLs, all figures.

`P-01_packet_RATER_DRAFT.txt` renamed to `P-01_packet_ANON.txt`. All six now follow one convention.

### 2. Quote-fidelity audit across all six — two real findings

Every excerpt in every anon file string-matched against its source packet. This is the check the
citation-verification harness will run, executed by hand ahead of it.

**P-02 and P-05's source packets contain zero em dashes; their anon files are full of them.** Those
two were **retyped rather than edited**, and the retype silently normalised ASCII hyphens to em
dashes inside quote bodies. Nothing meaningful changed, but a wholesale retype is exactly the
uncontrolled edit to the instrument the ruleset exists to prevent, and it was invisible until the
audit ran. **Harness consequence: normalisation must cover dashes and smart quotes as well as
whitespace and the `[the company]` token.**

**Two genuine undeclared quote-body edits, both benign, neither bracketed.** P-01's
`Executive Speaker series` → `executive speaker series` (a correct R4 application, applied
silently). P-02's `Ethan said` → `the same intern said` (a correct R3 application, declared in the
scrub log but not on the line). Both say the same thing: an edit recorded only in a scrub log is
not visible where a rater would meet it. Now rule A4.

### 3. Ruleset ratified and amended — `ANONYMIZATION_RULES_DRAFT.md`

Status changed from DRAFT to **SIGNED OFF 2026-08-15**. R1–R8 and JC-1 through JC-4 stand. Four
amendments added from P-06:

* **A1 — R6 extends to every section**, not just E and F: strip identifying figures wherever they
  appear. P-06's Section D carried an advisor headcount inside a quote — one-query identification
  inside the peer set, and the sentence's actual claim survives the strip intact.
* **A2 — where JC-1 and R4 collide, R4 takes the branded token and JC-1 keeps the rest of the
  sentence.** Test is dimension signal per unit of fingerprint. Will recur on any company with
  named internal behaviours.
* **A3 — R8 executes as a rater-facing recurrence note, not a deletion.** Keeps both excerpts,
  prevents the rater reading one company claim in two costumes as triangulation, and preserves the
  fact that the claim reached a legal filing as evidence in its own right.
* **A4 — every substitution is bracketed on the excerpt line**, not only in the scrub log.

### 4. SUPERSEDES — anonymization moves out of the collector prompt

The 08-15 plan was to fold R1–R8 into v4.7 so Section 1 is born anonymized. **Reversed. The scrub
becomes a separate second pass with its own prompt.**

The decisive reason is not tidiness: **a fused prompt destroys the baseline.** If Section 1 is born
scrubbed, the unscrubbed version never exists and nothing can be diffed — the audit above only
worked because both files existed. A scrub you cannot diff is a scrub you are trusting rather than
checking. Supporting reasons: both artifacts are wanted anyway under JC-3; ruleset changes stay
cheap when decoupled (they have already moved four times); and the collector already carries nine
hard rules, seven ladder rungs and a D1–D21 register.

**The em-dash bug is not fixable by a prompt.** It exists because a model re-emitted a whole packet
from scratch. Any prompt that rewrites the file reintroduces it. What kills the class is making the
scrub a patch rather than a retype, which points at three components:

* **a script** for the mechanical majority — URL stripping, `rev-NN` IDs, location tokens, name
  substitution from a supplied list, bracketing. Never retypes, so it structurally cannot produce
  the bug.
* **a prompt** for the judgment minority only — fingerprint calls, R4 rewrites, magnitude language.
  Emits a change list, not a file.
* **a verifier** — the fidelity audit as a script. Not extra work; it is the citation-verification
  harness arriving early.

### 5. SUPERSEDES — the scrub DOES belong in production

The standing reading since 08-07 was that anonymization is a test instrument only, because "a
production scraper always knows which company it is scraping." **Reversed by Sebastian, correctly.**

That reasoning is true of the **scraper** and irrelevant to the **scorer**. They are separate calls.
The scorer conditions only on what the packet contains, so deleting the name deletes something real
to condition on. That is categorically different from prompting a model to ignore what it knows —
the thing 08-07 rightly established does not work. A model can be denied a cue; it cannot ablate a
prior on request.

Evidence: Test 1's identified run explained a dimension with "the overall business remains a mature
retailer" and cited "rapid top-down changes with little notice," neither in the packet, both
tracking the real company. Test 2 destroyed every numeric delta in Test 1 but not this — sampling
variance does not invent facts that track a specific real company.

**Three limits recorded so this is not overclaimed:**
1. It reduces prior conditioning; it does not produce blindness. Julie identified GT-01 from a more
   conservative packet, from memory, and a frontier model infers better than she does.
2. **Citation verification catches the residual and would have caught both phrases mechanically,
   scrub or no scrub. The two are layered, not alternatives.** An earlier draft of the ruleset
   framed them as competing. That was wrong.
3. n = 1 per condition. Re-running Test 1 at n=5 is now load-bearing on a production design
   decision, not just on a disagreement with Julie.

**Consequences:** JC-3 is settled by force — if the scorer reads the scrubbed packet, that file *is*
the packet and the harness matches against it. And this argues *for* the script form, because in
production the scraper already holds the name, executives and locations as metadata, so substitution
becomes a lookup rather than an inference.

**The benefit nobody argued for, possibly the largest:** scrubbing production packets makes
production input match ground-truth input. That constraint has been outstanding since July — first
as the objection to hand-researching filings, then as 08-10's item 7 on stratified sampling being
unreproducible at scale. The recurring failure is calibrating the extractor against input it will
never see. This is one of the few decisions that makes the two converge.

### 6. Three freeze decisions — the raters can start

* **The v4.6 packets are frozen and the clean-room rebuild is cancelled.** Consistent with Julie's
  70–80% posture. Accepted cost: every "not reached" stays a one-method finding, and P-02's and
  P-06's Section A stays substituted evidence. The alternative was paying for the rating round
  twice, which is the George failure.
* **`anchors.json` frozen at `v1-frozen-2026-08-15`.**
* **Three raters: two lawyers plus Julie.** The 08-15 standing recommendation, adopted.

### 7. Julie rates BEFORE she writes the anchors — and the order is irreversible

Her value as third rater is the Julie-vs-lawyers comparison: what expertise and prior knowledge
contribute, against two readers holding the lens roughly constant. **That comparison only works
while she is not the author.** Once she writes the anchors her scores stop measuring expertise and
start measuring authorship — she applies what she meant, the lawyers apply what the text says, and
the two cannot be separated. Round 1 on frozen v1 anchors is her only clean shot at being a third
rater; writing first spends it.

The reverse order costs nothing. Rewriting after the round is strictly better informed — the
agreement rule hands her the anchors that actually failed rather than the ones she would guess at.
Rewriting before the round is guessing with zero data, and would need a scoring round afterward
anyway.

**Recorded for round 2:** after she writes v2 she cannot cleanly re-score against it either. Plan
either to exclude her scores there or to add a fourth reader.

### 8. Rater grid built — 18 pages

`rater_app/out/` — P-01 through P-06 × raters A, B, C. Leak-checked: no company name, executive
name, URL or scrub-log content reaches any page.

`rater_app/RATER_INSTRUCTIONS.md` — what the job is, the no-search rule, recognition as data rather
than confession, one-packet-at-a-time, what the two numbers mean, click-to-cite, and the
counterbalanced order (A forward, B reversed, C rotated) so drift over ~4 hours does not land on the
same companies for all three.

### 9. A live smoke test, and what it exposed

Sebastian ran a real packet end to end and sent the result file back. **The mechanism works:** the
JSON downloads, and all six citations string-matched the packet. Two capture problems showed up in
the actual data, and both were fixed before any rater sees a file.

* **Selections could start and end mid-word.** One citation came back as
  `"e and ask for direct feedback. Be grateful for and"`. It verifies — matching is
  substring-based — but it is not readable as evidence.
* **Whether the source attribution got captured was luck of the drag.** Five of six citations
  happened to include the `— [company values page] — company-authored` tail; one did not. Since
  the ≤0.7 measurement turns on source class, that made a recorded measurement into an inference
  that would have been right five times in six *by accident*.

### 10. Packets are now ADDRESSABLE, and the ≤0.7 measurement is recorded rather than inferred

Every excerpt is wrapped at build time with its section, its index and its source class, so a
citation reports its provenance no matter how sloppily it was selected. Selections snap to whole
words, reject anything under 25 characters, and reject anything outside an excerpt. Each dimension
in the result file now carries `source_mix`, `excerpts_cited` and `noncompany_support`.

**A page containing an unclassified excerpt fails the build.** This matters more than it sounds:
the classifier failed four separate times against real packets, and each failure would have
silently mis-measured an entire section rather than erroring.

1. A truncation marker sitting between the quote and its attribution (P-01).
2. A slash in `[company engineering/design blog]`, which a substring list missed (P-01).
3. The words "no publication date shown" in P-06's careers lines, which matched a
   publication-noun test scanning the whole attribution and marked eight company-authored
   excerpts as disputed.
4. P-05's section note describing the mix as including "the founder and CEO", which leaked
   executive detection onto two engineer-written posts.

**The lesson generalises:** a classifier that returns a plausible-looking wrong answer is worse
than one that stops. The build gate is the reason all four surfaced in an afternoon.

### 11. THREE different excerpt formats exist across the six packets

Discovered while parsing. This is a collector-prompt finding, not a formatting nit — anything that
parses packets must handle all three, and "the packet format" is not one format:

* one line per excerpt, attribution inline — P-02, P-03, P-06
* excerpt body wrapped over several lines, attribution on a later line — P-01, P-04
* a group of excerpts sharing a single preamble line — P-05 section D

Fold a single excerpt shape into v4.7.

### 12. OPEN QUESTION 5 CLOSED — `disputed` counts as company-authored

Full reasoning and caveats in `ground_truth/rater_app/SOURCE_CLASS_RULING.md`.

Employee-bylined writing on a company-run outlet (engineering blogs, newsrooms, culture magazines)
**counts as company-authored** for the ≤0.7 measurement. Sebastian's call. Strongest argument for
it: a measurement that can be satisfied by the thing it is meant to detect is not a measurement —
otherwise any company manufactures non-company support by starting a blog. It also matches v4.6's
existing treatment of employer responses to reviews.

**Qualification recorded with the ruling:** the editorial filter is on *valence*, not on
descriptive content, and the six dimensions are descriptive. A company suppresses "management here
is terrible" but publishes "we work asynchronously" proudly — and that second sentence is real
evidence on collaboration and pace. The material is **topic-selected**, not false. The right
reason to call it company-authored is selection over which true things get told.

**Consequence accepted knowingly — the flag is partly a size proxy.**

```
P-01  A:CCCCCCCC B:NNNNNNNNNNNNNNN C:CCCCCCCCCC D:DDD    E:NNN  F:CCCCCC
P-02  A:CCCCCCCC B:NNNNNNNNNNNNNNN C:CCCCCCCCCC D:DDDDC  E:NNNN F:CCCCCC
P-03  A:CCCCCCCC B:NNNNNNNNNNNNNNN C:CCCCCCCCCCCCCC
P-04  A:CCCCCCCC B:NNNNNNNNNNNNNNN C:CCCCCCCCCCCCCCCC    D:NNN  E:NNN
P-05  A:CCCCCCCC B:CC              C:R          D:DDDDDDDDDDCC
P-06  A:CCCCCCCC B:NNNNNNNNNNNNNNN C:CCCCCCCCCC D:NNDD   E:NNN  F:CCCCCC

C = company   N = non-company   D = disputed   R = researcher observation
```

**P-05 has ZERO non-company-authored excerpts** — 12 company, 10 disputed, 1 researcher
observation, and its section B holds two employer *responses* rather than reviews. It cannot
register non-company support on any dimension. P-03 has no D, E or F at all. The four packets that
*can* register support are the large or public ones. So the flag will mostly track company size,
not evidence quality — the same range-restriction shape already documented against layer count.
**Read it conditional on which evidence types the packet could contain**, never as a quality mark.

**Implementation: rule at analysis time, record at capture time.** `disputed` stays a distinct
class in the JSON; fold it into `company` downstream. That keeps the ruling testable once scores
exist — if disputed-supported dimensions behave like company-supported ones, the reasoning is
validated rather than assumed, and if they don't, the ruling reverses without re-rating anyone.

---

## Defects found and fixed in the rater app

**The anchor hash covered only `cfg["dimensions"]`.** Not the confidence bands, the bias gates, the
band values or the agreement rule — all of which are rater-facing and shape the numbers produced. A
change to the confidence wording left the hash identical, so a score row would claim an instrument
version it was not produced under. **This is the exact failure the hash exists to prevent, and the
same reasoning as stamping `model_run` on every LLM score.** Now hashed over every non-underscore
config key, with a regression check confirming the hash moves when any of the five fields changes.
Hash moved `d426fd431e36` → `55c4501b25c5`; anything generated before 2026-08-15 carries the old
stamp and is not comparable.

**One confidence band was written for the LLM, not for a person.** "Low" read *"…The model should
lean on its prior here."* A lawyer cannot act on that. Rewritten to "You can defend a direction, but
only weakly."

**P-04's header told the rater it had "the heaviest scrubbing of the six"** — a cross-packet
comparison inside a design that deliberately shows one packet at a time. Removed.

**Result capture was silently loss-prone.** Both the resume-after-crash behaviour and the submit
lock ride on `localStorage`, which on a `file://` page is the flakiest thing in the browser — and
the failure was swallowed by an empty `catch`. A rater could have scored for forty minutes into
memory that vanished on refresh, seeing nothing wrong. Now: a probe on load with a loud red
banner, a second banner if storage dies mid-session, the result file **downloads automatically on
submit** rather than waiting for a button, and the unload guard covers the case it previously
missed — a *finished* sitting whose file was never saved.

**`test_rater_page.js` — 42 assertions in a headless DOM**, driving the real `commit()` path
rather than faking state. Covers storage present, denied and dying mid-session; a full six-
dimension run with auto-download; payload contents including the anchor hash; the reopen-locked
path; excerpt markup and classification; word snapping; the minimum-citation guard; and the
`noncompany_support` computation. Run it after any change to the generator.

---

## No version control in this repo — a near-miss worth recording

A scripted edit to `build_rater_page.py` clobbered the entire HTML `TEMPLATE` string. There is no
git in `Solverah_IP/`, so there was nothing to revert to. It was recovered by reverse-engineering
the template out of an already-rendered page — the substitutions are deterministic, so this was
exact, and the reconstruction was verified byte-identical to the original outside the packet
region before being trusted.

Recovery worked because a rendered artifact happened to still exist. That is luck, not a process.
Sebastian's call: the old version is not needed, and this is not being pursued further. Recorded
so the exposure is visible rather than forgotten — every file in this repo is one bad edit from
gone, including the six packets and the collector prompt.

## Live fragility, not fixed

**The generator cuts the scrub log by matching the literal string `SCRUB LOG`.** If a future scrub
log carries any other heading, the entire operator log — residual-exposure notes, ruleset
deviations, source-packet defects, and in P-06's case a company name inside a defect note — ships
into the rater's page. It works today only because all six files happen to use that exact heading.
**This is a rule that fires only if someone remembers a magic string**, which is the pattern that
has already bitten this project twice. Harden it before the next packet is scrubbed.

---

## Source-packet defects found during the P-06 scrub — not anonymization issues

* Section 4's pre-flags quote an A excerpt that does not exist in Section 1 ("Raymond James is where
  good people grow"). The name occurrence it pointed at is real; the quoted text was written from
  memory.
* Section 4 says six reviews carry no location. The correct count is eight.
* rev-10's attribution title contradicts the role the reviewer names in their own body text. Left
  verbatim per the v4.6 rule.

---

## Open / next

1. **Send the packets out.** Assign which lawyer is A and which is B, Julie as C, distribute the six
   files each plus `RATER_INSTRUCTIONS.md`. Nothing is blocking this.
2. **The confidence definition is formally still open from 08-10 — but the frozen bands quietly
   answer it**, defining confidence as corroboration across source types. That is closer to "layer
   count" than to "evidence quality for this dimension," and 08-15 flagged layer count as the weaker
   of the two. Frozen either way for round 1; know which one shipped.

   **This now interacts with the question-5 ruling and is worth watching.** Confidence is defined by
   corroboration across source types, and the ruling removes an entire source type from the
   non-company side for small private companies. P-05 can no longer corroborate anything from
   outside the company. It should therefore produce uniformly low confidence — which is calibration
   working, not bias, *provided* nobody later shrinks low-confidence scores toward 0.5. That
   shrinkage was explicitly rejected in the canonical handoff and the reason applies with more force
   now: it would land on exactly the small companies the set has fewest of.
3. **Adversarial re-identification — deprioritised, not dropped.** It does not block raters, because
   recognition is already captured as data on the page. Three attacks when it happens: search the
   retained strings and preserved typos; the combination attack (no single fact identifies, the
   conjunction might); and the model attack — hand an anon packet to a fresh LLM and ask it to name
   the company. **That third one is now measuring a production control**, not checking a
   ground-truth artifact, and it supplies the number missing from Test 1.
4. **Build the scrub as script + prompt + verifier** per section 4 above, when production work
   starts. The verifier is the citation-verification harness.
5. **Roster**: `ground_truth/roster/` is an EMPTY FOLDER. `Solverah_Ground_Truth_Roster_v2.md` — the
   18-company list — is not in the repo. Six packets exist against a roster of eighteen, and the
   confounder `scale` placeholders need ~15 scored companies. Find the file or the roster is lost.
6. Carried and untouched: re-run the scorer variance test on a stronger model; re-run the
   blind/identified test at n=5 per condition (now load-bearing, see 5 above); the correction owed to
   Julie on the confidence claim; bias-test the 24 assessment items; write `assemble_training_data(db)`.

---

## Framings that survived pushback this session

* **A fused prompt destroys the baseline.** Anything born already-transformed cannot be diffed
  against what it was, so its transformation can only be trusted, never checked.
* **The scraper knows the company; the scorer does not have to.** Denying a model a cue is not the
  same as asking it to ignore a prior. The first works, the second does not.
* **Scrub and citation verification are layered, not alternatives.** Scrub lowers the rate, the
  harness catches the residual.
* **An edit recorded only in a scrub log is not a recorded edit** — the same shape as "a rule that
  lives only in a handoff is not a rule."
* **A retype is an uncontrolled edit even when nothing meaningful changes.** P-02 and P-05 prove it
  and the only evidence was punctuation.
* **Julie writing the anchors spends her one clean shot at being a third rater.** Author and
  independent reader are mutually exclusive roles on the same instrument.
* **Anchors are rewritten from disagreement, not from suspicion.** Do not fix the instrument before
  measuring where it breaks — which is the agreement rule's own design.
* **Freezing is how you ship fast. Skipping is how you pay twice.** Starting raters while a rebuild
  is scheduled is not speed.
* **A classifier that returns a plausible wrong answer is worse than one that stops.** Four
  near-misses in an afternoon, each of which would have silently mis-measured a whole section.
  The build gate is why they surfaced.
* **A measurement that can be satisfied by the thing it detects is not a measurement.** The
  argument that settled question 5.
* **Editorial selection operates on valence, not on descriptive facts.** Which is why company-run
  writing is still worth reading, and still not corroboration.
* **Rule at analysis time, record at capture time.** A ruling baked into capture cannot be tested
  or reversed; one applied downstream can be both.
* **Evidence availability keeps re-entering as a confound wearing new clothes** — layer count,
  then packet richness, now the non-company-support flag. Expect the next one.
