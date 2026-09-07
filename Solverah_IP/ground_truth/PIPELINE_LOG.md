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

## 2026-09-07 — pipeline armed, no run yet

Three scheduled Claude Desktop tasks created: **Company Research** and **Company Scrub** at
00:00, **Company Harvest** at 06:00, all on Opus 5, each in a chat outside the Solverah IP
Planner project.

Starting state, verified clean: `_build_env/packets/`, `_scrub_env/packets_raw/` and
`_scrub_env/packets_out/` all empty. `to_be_researched.txt` holds P-11 Regeneron and P-12
Duke Energy. `to_be_scrubbed.txt` is empty.

P-07 Cummins and P-08 DigitalOcean were scrubbed by hand earlier the same day, verified, and
promoted — the three runs that proved the prompt before it was scheduled. P-09 Warby Parker
and P-10 Twilio remain unscrubbed and are deliberately left to the pipeline, as the first
real test of a backlog on `to_be_scrubbed.txt`.

**Expected tonight:** research builds P-11. The scrub finds `packets_raw/` empty and stops —
that is a correct run, since nothing has been staged yet. The harvest then moves P-11 into
`packets/`, stages a copy for tomorrow, and writes the first real entry above this one.
