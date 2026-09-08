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
