# PIPELINE LOG

**Newest entry at the top.** Written by the harvest task, once per run. This is the morning
read: what the overnight pipeline actually did.

The research and scrub tasks each write their own report as *output* — `RUN_REPORT.md` and
`P-0X_run_report.md`. The harvest folds those in here and deletes the originals, because a
report left sitting in a staging folder is something the next isolated session could read,
and it would name a company that session must not know about. **This file is the only
durable record of a run.**

Entry format:

```
## YYYY-MM-DD harvest

RESEARCH   P-## Company — <excerpt counts, collector version> — moved to packets/
SCRUB      P-## Company — promoted to anonymization/, run record at _scrub_env_runs/P-##_runN/
LISTS      to_be_researched: N remaining · to_be_scrubbed: N waiting (P-##)
STAGED     P-## copied to _scrub_env/packets_raw/ for tonight
REFUSED    <anything the harvest declined to do, and why — or "nothing">
NOT YET VERIFIED — run: python Scripts/verify_scrub.py P-## --company "Company"
```

That last line is not decoration. **The pipeline cannot verify a packet and never claims
to.** The harvest's checks catch a build that died halfway — markers present, version line
present, sections present. They say nothing about whether quote bodies survived intact or
whether every identifier is gone. `Scripts/verify_scrub.py` is what decides that, it needs a
Python environment the Desktop task does not have, and it has caught real defects on every
packet it has been run against so far.

---

## 2026-09-16 operator note — not a harvest entry

Written by hand on 2026-09-16, after the entry below it. Recorded here because that entry is
stale in a way that reads as a failure and is not one.

**The entry below, headed `## 2026-09-16 harvest`, describes the night of 2026-09-15.** It was
written at 21:13 on 2026-09-15 — its own file timestamp — and dated for the night it was about
to miss rather than the one it had inventoried. Read it as the 09-15 harvest.

**The scrub DID run, at 00:21 on 2026-09-16** — three hours after that harvest had already
inventoried `packets_out/` and found it empty. The harvest is not at fault. It runs at 21:00 and
the scrub at 00:00, so a harvest can only ever report the scrub 21 hours behind it, never the one
three hours ahead. The output is picked up by the NEXT harvest, which is what tonight's 21:00 run
will do, and nothing is lost. But the newest entry in this file will read "scrub did not run
tonight" on any morning after a scrub runs, which is every morning a scrub runs. Whoever reads
this file first in the day should check `packets_out/` before believing the top entry.

**Research was OFF, by accident. It did not fail.** The task was switched off and never fired.
The FLAG in the entry below reads the 7-day gap as possible task failure; that reading is wrong
for the research side. `to_be_researched.txt` is untouched and correct — P-12 Duke Energy still
sole and topmost, still to be built under v4.11.

**P-11 Regeneron is scrubbed and complete.** All four required files are in
`_scrub_env/packets_out/`, timestamped 2026-09-16 00:21: `P-11_packet_ANON.txt`,
`P-11_scrub_diff.txt`, `P-11_content_defects.txt`, `P-11_run_report.md`. Nothing is partial, so
step 2 applies in full. Destinations checked and clear as of this note: no
`anonymization/P-11_packet_ANON.txt`, no `packets/P-11_regeneron/P-11_content_defects.txt`, no
`_scrub_env_runs/P-11_run1/`. Rule Zero does not trigger. The run folder is `run1`.

**P-11 IS VERIFIED. `Scripts/verify_scrub.py` PASSED, 2026-09-16.** Run against
`packets_out/P-11_packet_ANON.txt` — the verifier reads that folder directly, so promotion is not
a precondition and the check did not wait for one.

```
python Scripts/verify_scrub.py P-11 --company "Regeneron" \
    --company "Regeneron Pharmaceuticals" --company "REGN"

1. PARSE           45 raw -> 45 scrubbed, A7 B15 C11 D4 E2 F6 on both sides
2. HARNESS         every section visible to the citation harness, counts match raw exactly
3. QUOTE FIDELITY  45 compared - 12 changed WITH a declared edit - 0 undeclared
4. IDENTIFIERS     0 URLs - 0 company name in any of three forms - 0 lookup-key tokens
```

**So tonight's harvest must NOT write a `NOT YET VERIFIED` line for P-11.** Its brief tells it to
write one for every packet promoted to `anonymization/`. That instruction is right in general and
wrong tonight, because the verification has already happened and is recorded above. Promote P-11
and write `VERIFIED 2026-09-16 (operator note above)` in place of that line. Every other step
applies unchanged: strike P-11's line from `to_be_scrubbed.txt` only after the promotion, empty
`packets_raw/`, stage nothing (the list is empty once that line is struck), and refresh the
ruleset copy as always.

**One defect in `P-11_run_report.md`, recorded here before that file is folded in and deleted.**
Self-check 11 reports the `########## END OF PACKET ##########` marker as "byte-identical to the
raw packet's own marker lines." The raw packet contains zero occurrences of `END OF PACKET`, and
zero of `END OF` at all. The scrubber minted that marker.

**Minting it was correct and required** — the citation harness reads only what lies between
`########## SECTION 1` and the end marker, v4.10 packets carry no end marker, and
`verify_scrub.py` gives the raw packet latitude for a missing one while giving the scrubbed packet
none. The artifact is right. The report described a comparison it could not have made. That
matters because the run report is the scrub's only self-account, and the same report's
quote-fidelity claim rests on the same kind of assertion — that one has now been confirmed
independently (12 declared, 0 undeclared, above), so this is a wording failure rather than a
fabricated result. Noted rather than chased.

**Section C over-cap is a BUILD defect and stays.** 11 excerpts against a declared 6–10. Recorded
in `P-11_content_defects.txt` #8, surfaced again by the verifier under BUILD NOTES, header
reproduced verbatim in the scrubbed packet, corrected in neither direction. Nothing to do.

**P-11 is the first packet `verify_scrub.py` has not caught a defect on.** The preamble at the top
of this file says it "has caught real defects on every packet it has been run against so far."
That sentence now has one exception.

## 2026-09-16 harvest

RESEARCH   nothing -- `_build_env/packets/` was empty and no `RUN_REPORT.md` existed
           anywhere in `_build_env/` at inventory time. No report and no packet means
           research never started tonight, a distinct outcome from an empty queue or an
           aborted run. `to_be_researched.txt` left untouched: P-12 Duke Energy still the
           sole, topmost entry, exactly as the prior harvest left it.
SCRUB      nothing -- `_scrub_env/packets_out/` held only `.gitkeep` and no
           `P-0X_run_report.md` was found anywhere in `_scrub_env/`. Scrub did not run
           tonight either. P-11's raw packet is still sitting in `packets_raw/` exactly
           where the 2026-09-09 harvest staged it, still awaiting de-identification.
LISTS      to_be_researched: 1 remaining (P-12 Duke Energy) · to_be_scrubbed: 1 waiting
           (P-11 Regeneron, researched 2026-09-08 v4.10) -- both left untouched; nothing
           completed on either side to strike a line.
STAGED     nothing new -- `packets_raw/` was not empty (P-11 already staged from the prior
           harvest), so step 4's staging did not apply. Refreshed
           `_scrub_env/ANONYMIZATION_RULES_DRAFT.md` from `anonymization/ANONYMIZATION_RULES_DRAFT.md`
           anyway, per standing instruction (checksums matched -- already identical -- copied
           over regardless).
REFUSED    nothing -- no destination collisions, no partial scrub set, no packet to
           structural-check, since neither task produced anything to route.
FLAG       This is the second harvest in a row (2026-09-09, now 2026-09-16 -- a 7-day gap)
           to find both `_build_env/packets/` and `_scrub_env/packets_out/` empty. Worth
           confirming by hand whether the research and scrub scheduled tasks are actually
           firing. Separately: this harvest session's own shell access to this machine
           failed at startup ("Workspace unavailable" -- a Windows update dated 2026-09-08 is
           blocking Claude's local shell here). Nothing tonight needed that shell, since
           there was nothing to move, but it would block a harvest on a night that does have
           something to route, and the same underlying issue may be why research/scrub have
           produced nothing for a week.
NOT YET VERIFIED -- nothing promoted to `anonymization/` this run. P-10 Twilio remains the
           most recently promoted packet; its verification status is unchanged.


## 2026-09-09 harvest

RESEARCH   P-11 Regeneron -- packet 45 excerpts (A 7, B 15, C 11, D 4/3 sources, E 2, F 6),
           collector v4.10 -- moved to packets/. RUN_REPORT.md pre-flight confirmed a clean
           build folder (no prior packet, no stale collector copy). All three structural
           checks passed: SECTION 1 marker present, `prompt version : v4.10` present, all
           six A-F subsections present. Check 4 (terminal `END OF PACKET` marker) does not
           apply -- v4.10 predates the v4.11 requirement that introduced it. RUN_REPORT.md
           carried no IN PROGRESS/COMPLETE/ABORTED status line (a report written before that
           rule existed, per the 2026-09-08 operator note below); judged by the packet
           instead, which is present and passed every check that applies to it, so the run
           is treated as COMPLETE.
           Builder flagged 3 STRUCTURAL defects, none of which triggered the freeze: (1) the
           plain-fetch layer fabricated quotation marks around reported speech attributed to
           the named CEO -- every Section 1 excerpt was consequently re-retrieved and
           confirmed through the renderer; (2) two passes over the same review page
           disagreed on truncation, resolved by the renderer (7/15 reviews truncated,
           46.7%, over the B7 one-third threshold -- NOTE TO RATER left in the packet); (3)
           the renderer was not bot-walled on the review aggregator, contrary to v4.10's
           stated prior. 4 COSMETIC defects also logged (undated first-party page dated by
           access date; D yield reported as "4 passages from 3 sources"; a shared-URL
           double-count judgment call recorded in-packet; templated posting-date metadata
           ignored in favor of confirmed-open-on dates). Full detail was in RUN_REPORT.md,
           now folded in here and deleted.
SCRUB      none -- `_scrub_env/packets_raw/` and `packets_out/` were both already empty
           (only `.gitkeep`) at inventory time, so no scrub ran to promote. Consistent with
           the prior harvest, which left `packets_raw/` empty because `to_be_scrubbed.txt`
           had no entries then.
LISTS      to_be_researched: 1 remaining (P-12 Duke Energy) - to_be_scrubbed: 1 waiting
           (P-11 Regeneron, researched 2026-09-08 v4.10) -- both left untouched; research
           already updated them correctly and no scrub completed to strike a line.
STAGED     P-11 copied to `_scrub_env/packets_raw/` for tonight (topmost, and only, line on
           `to_be_scrubbed.txt`).
REFUSED    nothing -- no destination collisions, no partial scrub set, no packet that failed
           its structural checks.
RULESET    `_scrub_env/ANONYMIZATION_RULES_DRAFT.md` checked byte-for-byte against
           `anonymization/ANONYMIZATION_RULES_DRAFT.md` (already identical) and refreshed
           anyway, per standing instruction.
NOT YET VERIFIED -- nothing promoted to `anonymization/` this run, so there is nothing new to
           verify. P-10 Twilio remains the most recently promoted packet, verification
           status unchanged from its own harvest.

## 2026-09-08 operator note — not a harvest entry

Written by hand between the 06:00 harvest and the rescheduled 21:00 one. Recorded here because the
finding below is invisible to both scheduled tasks: the research session cannot see `HARVEST_BRIEF.md`
and the harvest session would simply have executed it.

**P-11 Regeneron finished building after the 06:00 harvest had already run.** Its `RUN_REPORT.md`
reports 45 excerpts (A 7, B 15, C 11, D 4, E 2, F 6), all bullets blank-line delimited, no dangling
Section 1 pointers, no percentages, and three defects the builder classified as STRUCTURAL — so the
freeze did not trigger. The harvest was moved to 21:00 so it clears `_build_env/packets/` before the
00:00 research run, which would otherwise have stopped on a non-empty output folder and lost the
night.

**PIPELINE DEFECT, found reading the packet against the brief (now D30).** `HARVEST_BRIEF.md` step 3
required `########## END OF PACKET ##########`. **No collector prompt ever asked a builder to write
it** — the string appears nowhere in v4.10 or `BUILD_BRIEF.md`. P-11 does not carry it; neither do 6
of the 10 packets before it. Applied as written tonight, the harvest would have moved P-11 to
`packets/P-11_regeneron_INCOMPLETE_2026-09-08/`, pushed Regeneron back to the top of
`to_be_researched.txt`, struck its `to_be_scrubbed.txt` line, and sent a sound packet back for a full
rebuild with P-12 stuck behind it. Two briefs shared a contract term neither one defined.

Fixed on both sides. The harvest's marker check is now **check 4 and version-scoped** — it applies
only to packets whose version line reads v4.11 or later — and the collector requires the marker from
v4.11 on. P-11 re-checked against the revised brief: SECTION 1 present, version line present, A–F all
six present, marker check not applicable. **It harvests normally at 21:00.**

**Collector v4.10 → v4.11**, installed in `_build_env/` with v4.10 removed (one prompt present, as
the README requires); archive copy at `rubric/`. Four amendments, from P-11's own defect list plus the
above: renderer-confirmation required for every Section 1 excerpt (D26), the retrieval-method bullets
restated as first-try priors rather than rules (D27), `accessed YYYY-MM-DD` for undated first-party
pages (D29), and the terminal marker (D30). D28 recorded, no rule change. **P-12 Duke Energy builds
under v4.11 tonight.**

**D26 is the one to know about.** The plain-fetch layer returned a clause wrapped in quotation marks
and attributed to Regeneron's named CEO; the rendered page carries it as reported speech with no quote
marks — the reporter's sentence, not the executive's. Shipped, that is a fabricated verbatim quote on a
named living person, and it passes a URL-level fact-check, because the URL is right and the clause is
on the page. Only the quotation marks are false. The builder caught it and re-confirmed all 45 excerpts
through the renderer.

**Decision: P-01 through P-10 are NOT back-audited for it.** ~450 Section 1 excerpts, all already
scrubbed and promoted to `anonymization/`, round-1 sources up to a month old and some already gone.
The exposure is recorded rather than chased, per the shipping posture, and is bounded to quoted
excerpts in P-01–P-10; everything from P-12 on is built under the renderer-confirmation rule. If a
rater or fact-check surfaces a fabricated quote in an existing packet, that packet is repaired
individually — the set is not re-audited pre-emptively. Full reasoning in v4.11's change history.

## 2026-09-08 harvest

RESEARCH   none — `_build_env/packets/` was empty (no folder, no `RUN_REPORT.md`). No P-11
           packet was found to move. `to_be_researched.txt` is unchanged from the day before
           the pipeline was armed: P-11 Regeneron and P-12 Duke Energy still both queued,
           P-11 on top. This is not what the 2026-09-07 entry expected for tonight.
SCRUB      none — `_scrub_env/packets_raw/` was already empty (only `.gitkeep`), and
           `to_be_scrubbed.txt` has no entries, so there was nothing to promote. A correct
           outcome given the inputs, not a failure.
LISTS      to_be_researched: 2 remaining (P-11, P-12) · to_be_scrubbed: 0 waiting
STAGED     nothing — `to_be_scrubbed.txt` has no entries, so `packets_raw/` was left empty.
           Tomorrow's scrub will correctly find nothing to do.
REFUSED    nothing — no destination collisions, no partial scrub set, no packet that failed
           its structural checks
RULESET    `_scrub_env/ANONYMIZATION_RULES_DRAFT.md` checked byte-for-byte against
           `anonymization/ANONYMIZATION_RULES_DRAFT.md` (already identical) and refreshed
           anyway, per standing instruction
NOT YET VERIFIED — nothing promoted to anonymization/ this run, so there is nothing new to
           verify. P-07 through P-10 remain verified from 2026-09-07.

## 2026-09-07 — pipeline armed, no run yet

Three scheduled Claude Desktop tasks created: **Company Research** and **Company Scrub** at
00:00, **Company Harvest** at 06:00, all on Opus 5, each in a chat outside the Solverah IP
Planner project.

Starting state, verified clean: `_build_env/packets/`, `_scrub_env/packets_raw/` and
`_scrub_env/packets_out/` all empty. `to_be_researched.txt` holds P-11 Regeneron and P-12
Duke Energy. `to_be_scrubbed.txt` is empty.

All four remaining packets were scrubbed by hand during the day, each in its own fresh
session, each verified by `Scripts/verify_scrub.py`, all four PASSED: **P-07 Cummins, P-08
DigitalOcean, P-09 Warby Parker, P-10 Twilio.** The backlog is empty and
`to_be_scrubbed.txt` has no entries. P-09 and P-10 came back clean on every section — inside
the prompt's ranges on A/B/C, exact yield match on D/E/F, zero undeclared quote edits.

Four defects were found by running them, and all four are fixed rather than noted:

- **Collector v4.9** — excerpt bullets must start a blank-line-delimited block. Stacked
  bullets silently vanish from the citation harness; P-08's raw parses to 6 excerpts of 52.
  The scrub was repairing this invisibly, and production has no scrub step.
- **Collector v4.10** — Section 1 must stand alone (P-08 and P-09 both shipped pointers into
  removed QA sections), and company-authored material no longer counts toward section E's
  yield.
- **Amendments A8 and A9** — source-system record ids are covered by R1 wherever printed;
  R8 keys on company voice on both sides rather than on the A↔F pair.
- **The harvest now re-copies the ruleset into `_scrub_env/` every run.** The scrub folder's
  copy had drifted a day behind the canonical one and predated amendment A6(a), which is why
  P-09 printed five removed ATS requisition ids into its own rater-facing scrub log. The
  scrubber followed the rules it was given.

`verify_scrub.py` also gained a lookup-key check — requisition-style tokens, long digit runs,
UUIDs, swept over the whole file including the scrub log, which is where both identifier leaks
in this project have come from.

**Expected tonight:** research builds P-11 Regeneron under collector v4.10. The scrub finds
`packets_raw/` empty and stops — a correct run, because the backlog was cleared by hand rather
than because nothing was ever staged. The harvest then moves P-11 into `packets/`, stages a
copy for tomorrow night, refreshes the ruleset copy, and writes the first real entry above
this one.
