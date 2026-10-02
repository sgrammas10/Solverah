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

## 2026-10-02 operator note — not a harvest entry

Written by hand on the afternoon of 2026-10-02, after the harvest entry below.

**The entry below says research and scrub did not run. Both ran, after it.** It was written
at 21:02 on 10-01. The scrub produced P-15's four files at 00:16 on 10-02, and research
built P-16 Smartsheet between 12:25 and 16:55 UTC on 10-02 (run report `COMPLETE`).

**P-14 Crawford & Company is VERIFIED.** It was promoted on the harvest before this one with a
`NOT YET VERIFIED` line. `Scripts/verify_scrub.py` PASSED on 2026-10-02:

```
python Scripts/verify_scrub.py P-14 --company "Crawford & Company" --company "Crawford"

1. PARSE           50 raw -> 50 scrubbed, A8 B15 C10 D7 E4 F6
3. QUOTE FIDELITY  50 compared - 15 changed WITH a declared edit - 0 undeclared - 0 not compared
4. IDENTIFIERS     0 URLs - 0 company name in either form - 0 lookup-key tokens
BUILD NOTES        section E header says yield 3, the harness parses 4
```

**P-15 Hudson River Trading is VERIFIED.** It is in `_scrub_env/packets_out/`, so tonight's
harvest promotes it. **That harvest must NOT write a `NOT YET VERIFIED` line for P-15**; write
`VERIFIED 2026-10-02 (operator note above)` in its place. Every other step applies unchanged.

```
python Scripts/verify_scrub.py P-15 --company "Hudson River Trading" --company "Hudson River" --company "HRT"

1. PARSE           31 raw -> 31 scrubbed, A8 B5 C10 D4 E4 (F legitimately empty: private)
3. QUOTE FIDELITY  31 compared - 13 changed WITH a declared edit - 0 undeclared - 0 not compared
4. IDENTIFIERS     0 URLs - 0 company name in any form - 0 lookup-key tokens
BUILD NOTES        section B holds 5 against a required minimum of 12
```

The job-board tokens the research run flagged as the sharpest identifiers in P-15 are gone.

**The verifier was fixed first.** P-15 originally FAILED on section F: "declared non-empty and
the harness parses ZERO". But F's header says `yield: 0`. The company is private, so there is no
human-capital disclosure to quote. The check failed any section that parsed zero, without
looking at what the header declared. A declared-0 section that parses 0 now counts as a match;
a section declared non-empty that parses empty still fails. Regression tests are in
`causal_graph/test_verify_scrub.py`. P-07 to P-15 all PASS under the fixed script. P-01 to
P-06 fail exactly as they did under the original script (round 1 is frozen, never re-scrubbed),
minus the declared-empty false positives, which also hit P-03, P-04 and P-05. One more false
alarm to know about: the name check matches substrings, so `--company RGA` on P-04 hits
"organisation". Use whole names, or read the hit before believing it.

**Two decisions for Sebastian, flagged rather than decided:**
- **P-15 is thin:** 31 excerpts against ~50 for the others. B has 5 reviews against a minimum
  of 12: the required source has 2 worldwide, and the optional one sign-in-walled after 3.
  F is empty (private), D is one voice, 3 of the 4 E excerpts come from one article, and all
  of A is access-dated. Rate it as-is (the packet carries a NOTE TO RATER) or replace the
  company.
- **P-14 acrostic:** the scrub flagged that the initials of the seven stripped value names
  still spell the company's acronym. No string check can catch that; it needs a reorder or a
  reword ruling.

## 2026-10-02 harvest

RESEARCH   Research never started: no RUN_REPORT.md and no packet in _build_env/packets/ (empty). P-16 Smartsheet is still the top line of to_be_researched.txt. This is "did not run", not "empty queue" -- 4 companies are still waiting.
SCRUB      Scrub did not produce output: _scrub_env/packets_out/ is empty (no ANON, diff, content_defects or run_report). The P-15 Hudson River Trading packet staged on 2026-10-01 is still sitting unconsumed in _scrub_env/packets_raw/ (byte-identical to packets/P-15_hudson_river_trading/P-15_packet.txt). Nothing promoted, no run folder created, no failed-run folder created (there was no partial set to preserve).
LISTS      to_be_researched: 4 remaining (P-16 Smartsheet, P-17 HCA Healthcare, P-18 Fifth Third Bank, P-19 Centene) · to_be_scrubbed: 1 waiting (P-15). No lines changed.
STAGED     Nothing new. packets_raw/ already holds exactly one packet (P-15), so step 4 was skipped. ANONYMIZATION_RULES_DRAFT.md in _scrub_env/ is byte-identical to anonymization/ -- no refresh needed.
REFUSED    nothing
NOT YET VERIFIED -- nothing promoted this harvest. (P-14 from the 2026-10-01 harvest is still unverified unless noted elsewhere: python Scripts/verify_scrub.py P-14 --company "Crawford & Company")

## 2026-10-01 harvest

RESEARCH   P-15 Hudson River Trading — 31 excerpts (A 8 · B 5 · C 10 · D 4 from 1 source · E 4 from 2 sources · F 0, private), collector v4.11 — moved to packets/P-15_hudson_river_trading/. Run report status was COMPLETE (2026-09-30 12:24–17:35 UTC; report mtime 17:33 UTC, so >24h old but not waiting on anyone). Structural checks passed: SECTION 1 present, `prompt version : v4.11`, sections A–F present, END OF PACKET marker present (v4.11 owes it).
           Flagged by the research run, not decided by the harvest: B FAILS its 12-review minimum (5 delivered, 0 inside the 24-month gate) — the required review source holds only 2 reviews worldwide (2022-10-13, 2017-12-13) and the optional source shows 3 of 119 anonymously, then a bot-detection sign-in wall; no sign-in used. Packet carries a NOTE TO RATER on this. D is one voice only. E is 3 of 4 excerpts from one article. A has no source dates (all 8 access-dated). Freeze status NOT triggered; 5 structural defects in collector v4.11: S1 B minimum unreachable with no rule for it, S2 B1a-REMEDY cap of 5 assumes the optional site yields 5, S3 no citation form for Section C bodies living in a third-party ATS iframe, S4 D0 trigger undecidable when author titles are unpublished, S5 staleness gate defined per rung, not per item. 8 cosmetic (C1–C8).
           Identifier risk: all 10 Section C excerpts cite the ATS embed URL (board slug and four numeric job tokens) — the sharpest identifiers in the file; flagged in Section 4 for the scrub.
           Not retrievable / stale: 2026-09-10 founder profile (paywall), 2025-10-31 podcast transcript (registration), pages 2–40 of optional review source; two on-axis blog posts from 2022 rejected on age; no handbook, no conference talk, no repo contribution guidelines; private, so no human-capital disclosure.
           Environment notes: browser needed a fresh one-use site grant for nearly every page load (about double the calls); MCP bridge dropped and reconnected ~20 times with no loss. D26 confirmed twice: plain fetch invented a pay figure and altered quoted passages that the rendered page did not carry.
           OPERATOR TO VERIFY: BUILD RECORD model string (`claude-opus-5`) is the session-configured identifier, not a confirmed serving model.
SCRUB      P-14 Crawford & Company — complete (all four files present); ANON promoted to anonymization/, content_defects to packets/P-14_crawford_and_company/, run record at _scrub_env_runs/P-14_run1/ (diff kept there only). Scrub report: 13/13 self-checks PASS, 50 raw / 50 output excerpts; edits: 12 company-name substitutions, 4 named humans, 4 branded names, 1 place, 50 attribution lines rewritten, 15 review ids, 4 posting ids, 6 site tokens. Flagged rather than decided: initials of the seven F1 value names still spell the stripped acronym; reviewer titles/headlines untouched ("Client LIAISON Manager", "Quite Satisfying Case Management Employment" near-unique, T2 exposure); no recurrence notes added (A3/A9), operator may overrule. Content defects CD-1..CD-5 recorded: review ordering, scope-note role mismatch, pre-flag misses/miscounts.
LISTS      to_be_researched: 4 remaining (P-16 Smartsheet, P-17 HCA Healthcare, P-18 Fifth Third Bank, P-19 Centene) · to_be_scrubbed: 1 waiting (P-15). P-14's line struck. Research noted last night that to_be_scrubbed still held P-14's line while packets/ was empty — consistent with the prior harvest not striking it until its scrub was promoted tonight.
STAGED     P-15 copied to _scrub_env/packets_raw/ for tonight; ANONYMIZATION_RULES_DRAFT.md refreshed in _scrub_env/.
REFUSED    nothing. (Deletion needed a session permission grant, which was approved.)
NOT YET VERIFIED — run: python Scripts/verify_scrub.py P-14 --company "Crawford & Company"

## 2026-09-30 harvest

RESEARCH   P-14 Crawford & Company — 50 excerpts (A 8 · B 15 reviews · C 10 from 4 postings · D 7 from 5 sources · E 4 · F 6), collector v4.11 — moved to packets/P-14_crawford_and_company/. Run report status was COMPLETE (2026-09-29 12:31–13:15 UTC). Structural checks passed: SECTION 1 present, `prompt version : v4.11`, sections A–F present, END OF PACKET marker present (v4.11 owes it).
           Flagged by the research run, not decided by the harvest: 9 build defects, 4 STRUCTURAL — (1) no B0 rule for a subject-company review sitting on a third party's pooled profile (a 2026-08-19 "Property Adjuster — Remote" review excluded); (2) no test for whether a subsidiary brand's review profile is an entity of the company — 7 of 15 reviews come from the reading taken, a narrower reading gives a different, older section B; (3) D0's two voice categories cannot classify what the D ladder yielded; (4) Section A's core value framework is published as an image, recoverable only via the 10-K. 5 cosmetic (inert Indeed fcountry filter, browse-edgar robots refusal, renderer element search truncates at ~100 chars, E company-quote-in-reporting rule, one more in the packet's Step 5 list).
           Not retrievable / stale: no handbook, no long-form press profile, no conference talk, no layoff/RTO event in 12 months; GitHub org stale (one repo, last touched 2017); code of conduct is PDF-only (nothing quoted); a 10-K/A (accession 0001193125-26-116011) exists and was not opened. Review-site truncation: 7 of 15 reviews cut off. Reviews are mostly claims-facing roles; the packet carries a SCOPE note.
           OPERATOR TO VERIFY: BUILD RECORD model string (`claude-opus-5`) is the session-configured identifier, not a confirmed serving model.
           OPERATOR TO EYE: the comment block in to_be_researched.txt still says "P-13/P-14 above"; research left it untouched.
SCRUB      P-13 Schneider National — promoted to anonymization/P-13_packet_ANON.txt; content_defects to packets/P-13_schneider_national/; all four files at _scrub_env_runs/P-13_run1/ (diff stays in the run record only). Scrub run report: all 13 self-checks PASS; 55 excerpts in, 55 out; B 17 (max 15) and C 12 (max 10) over cap, correctly untouched (CD-4). Flagged, not decided: fleet-colour self-description left as the strongest remaining fingerprint (no rule covers colours); ruleset change history mentions a "named-clients rule" with no text (a customer abbreviation handled under A5); "operating center" vocabulary left; reviewer-level re-identification left per the OPEN item.
LISTS      to_be_researched: 5 remaining (next: P-15 Hudson River Trading) · to_be_scrubbed: 1 waiting (P-14). Harvest struck the P-13 line from to_be_scrubbed.txt after promotion; research had already updated both lists for P-14.
STAGED     P-14 copied to _scrub_env/packets_raw/ for tonight. Ruleset refreshed (was already byte-identical).
CLEANUP    File deletion is disabled and nobody was awake to approve it, so consumed files were moved to _to_delete/ rather than deleted: P-13_scrubout_* (packet_ANON, scrub_diff, run_report copies from packets_out — the diff copy must not be left where a rater could read it; delete it by hand) and the raw P-13 scratch packet from packets_raw, plus P-14's RUN_REPORT.md. Delete when convenient.
REFUSED    nothing
VERIFIED 2026-09-29 (operator note above) — P-13 Schneider National, verify_scrub.py PASSED (55 compared, 0 undeclared, 0 identifiers).
NOT YET VERIFIED — nothing new promoted except P-13 (verified above). P-14 is a raw packet awaiting tonight's scrub; run verify_scrub.py after it is scrubbed.

---

## 2026-09-29 operator note — not a harvest entry

Written by hand on the morning of 2026-09-29, after the harvest entry below.

**P-13 Schneider National is scrubbed and VERIFIED.** The scrub ran at 00:16 on 09-29, after
the harvest below, and left all four files in `_scrub_env/packets_out/`.
`Scripts/verify_scrub.py` PASSED against `packets_out/P-13_packet_ANON.txt`:

```
python Scripts/verify_scrub.py P-13 --company "Schneider National" --company "Schneider"

1. PARSE           55 raw -> 55 scrubbed, A8 B17 C12 D8 E4 F6 on both sides
3. QUOTE FIDELITY  55 compared - 18 changed WITH a declared edit - 0 undeclared - 0 not compared
4. IDENTIFIERS     0 URLs - 0 company name in either form - 0 lookup-key tokens
BUILD NOTES        B 17 against max 15, C 12 against max 10 -- over cap, correctly untouched
```

**So tonight's harvest must NOT write a `NOT YET VERIFIED` line for P-13.** Promote it as
normal and write `VERIFIED 2026-09-29 (operator note above)` in its place. Every other step
applies unchanged.

**The verifier was fixed the same morning.** Check 3 used to compare a quote only when a dash
directly followed it. That silently skipped truncated reviews (`"..." [...]  --`) and press
quotes with their attribution after them (`"...," Name said.  --`). P-13 first "passed" with
only 50 of 55 quotes compared, and two of the five skipped quotes carried name
substitutions. Those shapes are now compared, and any bullet that still can't be paired is
listed under `not compared` rather than dropped. Regression tests are in
`causal_graph/test_verify_scrub.py`. P-07 through P-12 were re-run under the fixed script:
all still PASS, with 0 bullets uncompared.

**Open ruleset decisions the P-13 scrub flagged but could not decide (Sebastian):**
- A section A excerpt describes the company by its fleet colour. The scrub calls it the
  strongest identifying detail left in the packet; no rule covers colours, so it was kept.
- The ruleset's change history mentions a "named-clients rule", but no such rule text exists.
  A customer abbreviation was handled under A5 instead.

## 2026-09-29 harvest

RESEARCH   P-13 Schneider National — 55 excerpts (A 8 · B 16 reviews · C 12 from 4 postings · D 8 from 2 sources · E 4 · F 6), collector v4.11 — moved to packets/P-13_schneider_national/. Run report status was COMPLETE; the run opened 2026-09-23 and sat on an unanswered approval until Sebastian accepted it 09-28, built 09-28/29. Structural checks passed: SECTION 1 present, `prompt version : v4.11`, sections A–F present, END OF PACKET marker present (v4.11 owes it).
           Flagged by the research run, not decided by the harvest: 9 build defects listed in its handback, 4 classed STRUCTURAL (retrieval-environment disconnections x4; search-stale job detail pages; a split review entity whose omission would have changed Section B; an undated first-party blog the staleness gate cannot apply to) — freeze did NOT trigger. Not retrievable: no handbook / eng blog / conference talk exist; GitHub org stale (2 repos, past 18-month gate); a 2006 "cuts 170 jobs" article caught and excluded; review-site optional source blocked by robots.txt then cut off by disconnect; Code of Conduct is an unreadable PDF (nothing quoted); CEO interview is video-only.
           OPERATOR TO VERIFY: the BUILD RECORD model string (`claude-opus-5`) is the session-configured identifier, not a confirmed serving model.
           CORRECTION: the research run's report says the harvest "did not fire" 09-23 → 09-28. It did (09-24, 09-25, 09-26, 09-28 entries), each time correctly deferring an IN PROGRESS report. See the 09-28 operator note.
SCRUB      nothing to route — _scrub_env/packets_out/ and packets_raw/ were both empty at start (no scrub ran last night; P-12 was promoted 09-21).
LISTS      to_be_researched: 6 remaining (next: P-14 Crawford & Company) · to_be_scrubbed: 1 waiting (P-13). No list edits by the harvest; research had already updated both.
STAGED     P-13 copied to _scrub_env/packets_raw/ for tonight. Ruleset refreshed (was already byte-identical to anonymization/ copy).
CLEANUP    RUN_REPORT.md and stray _RUN_REPORT_backup_fragment.txt moved out of _build_env/packets/ into _to_delete/ (file deletion is disabled, no one awake to approve it) — delete that pair by hand when convenient.
REFUSED    nothing
NOT YET VERIFIED — nothing promoted to anonymization/ this run. P-13 is a raw packet awaiting tonight's scrub; run verify_scrub.py after it is scrubbed.

---

## 2026-09-28 operator note — not a harvest entry

Written by hand at ~19:35 EDT, after the harvest entry below.

**The P-13 Schneider National run was never dead. It was waiting on Sebastian's approval.**
It opened its `RUN_REPORT.md` at 2026-09-23 12:22 UTC, then sat on an unanswered approval
prompt in Claude Desktop for five days. Every harvest from 09-24 on read that correctly as
`IN PROGRESS` and deferred; the escalating "crashed session" wording was a misreading. On
2026-09-28 at ~19:30 EDT Sebastian moved the old report to
`_to_delete/P-13_RUN_REPORT_ABORTED_2026-09-23.md` and accepted the prompt. The session
resumed at 23:32 UTC and **is building P-13 now**, under v4.11. The `ABORTED` in that filename
is wrong — the run was not aborted — but the file is kept as the only record of 09-23's start.

**The resumed session's report says the harvest "does not appear to have fired" 09-23 → 09-28.
It did** — 09-24, 09-25, 09-26 and 09-28 entries below, each correctly leaving the report
alone. The research session cannot see this log, so it read an untouched report as a missed
harvest.

**Nothing was lost.** No evidence was collected before the wait, so resuming does not break
Rule Zero. Both lists are unchanged, with P-13 still on top of `to_be_researched.txt` and
`to_be_scrubbed.txt` empty.

**Brief changes, made the same evening, per Sebastian: "if one has been running for that long
it's just waiting for approval on a site; no more run until that one is done."**
- `HARVEST_BRIEF.md` step 3: an `IN PROGRESS` report has **no age limit** and is never moved
  for being old. Past 24h, the entry's first line is an `ACTION` line telling Sebastian to open
  the Company Research task and answer its prompt, repeated every harvest until the report
  changes.
- `HARVEST_BRIEF.md` step 3: **a report with no status line is now treated as `IN PROGRESS`.**
  The resumed P-13 report has none — it begins at an `INTERRUPTION` heading — and the old rule
  (no status line + no packet → ABORTED, fold and delete) would have removed it mid-build.
- `BUILD_BRIEF.md`: another session's `RUN_REPORT.md` in `packets/` means a live run waiting
  on approval — stop, don't start a second company, don't touch the report. And the two status
  lines stay first in the file always, including after an interruption.

**Expect the next harvest to defer P-13** if the build is still running, with a flag for the
missing status line. That is correct. If the finished session never writes a status line, the
harvest will keep deferring. In that case a human checks the packet is there and adds
`status  : COMPLETE` as the report's first line.

## 2026-09-28 harvest

RESEARCH   deferred -- `_build_env/packets/RUN_REPORT.md` status line still reads `IN
           PROGRESS`, company P-13 Schneider National (started 2026-09-23 12:22 UTC,
           report file itself unchanged since 2026-09-23 12:20:50 UTC -- the same
           byte-for-byte report the last several harvests found). It is now roughly 124
           hours (~5 days 4 hours) since the last update, well past the 61 hours flagged
           on 2026-09-26. Per HARVEST_BRIEF.md Step 3, IN PROGRESS means touch nothing in
           `_build_env/`, so nothing there was moved or altered (there is still no packet
           folder to move regardless, only the report). Separately: no harvest log entry
           exists for 2026-09-27 in this file -- it is unknown whether that night's
           harvest ran at all, so there may be a one-night gap in this monitoring in
           addition to the stuck research session. Flagging again for a human, more
           urgently: this is well past any plausible "slow site approvals" explanation and
           reads like a dead or crashed research session that will never update on its
           own. The harvest task is not authorized to judge that -- only to keep
           reporting it.
SCRUB      nothing -- `_scrub_env/packets_out/` and `_scrub_env/packets_raw/` held only
           `.gitkeep`. No scrub ran: `to_be_scrubbed.txt` was already empty coming into
           tonight (last struck 2026-09-21, unchanged since). No partial four-file set, no
           `P-0X_run_report.md` to fold in.
LISTS      to_be_researched: 7 waiting (P-13 Schneider National, P-14 Crawford & Company,
           P-15 Hudson River Trading, P-16 Smartsheet, P-17 HCA Healthcare, P-18 Fifth Third
           Bank, P-19 Centene) -- unchanged, since research has not finished P-13 yet.
           to_be_scrubbed: 0 waiting -- unchanged, nothing to strike.
STAGED     nothing -- `to_be_scrubbed.txt` has no entries, so `packets_raw/` stays empty for
           tonight's scrub. Refreshed `_scrub_env/ANONYMIZATION_RULES_DRAFT.md` from
           `anonymization/ANONYMIZATION_RULES_DRAFT.md` per standing instruction (already
           identical byte-for-byte; copied over regardless).
REFUSED    nothing -- no destination collisions, no partial scrub set, no research packet to
           structural-check since none was produced. The one live `RUN_REPORT.md` was left
           exactly where it is, untouched and undeleted, because its run is still IN
           PROGRESS -- a live report only gets folded into this log and deleted once its
           run is finished.
NOT YET VERIFIED -- none (no packet promoted to anonymization/ this harvest)

---


## 2026-09-26 harvest

RESEARCH   deferred -- `_build_env/packets/RUN_REPORT.md` status line still reads `IN
           PROGRESS`, company P-13 Schneider National (started 2026-09-23 12:22 UTC,
           report file itself unchanged since 2026-09-23 12:20 UTC -- same mtime as the
           last two harvests reported). This is now the THIRD consecutive harvest
           (2026-09-24, 2026-09-25, and tonight) to find this exact report byte-for-byte
           unchanged, roughly 61 hours with no update. Per HARVEST_BRIEF.md Step 3, IN
           PROGRESS means touch nothing in `_build_env/`, so nothing there was moved or
           altered (there is still no packet folder to move regardless, only the report).
           Flagging again for a human, more urgently this time: three straight nights of
           zero movement is well past "slow site approvals" territory and reads like a
           dead or crashed research session that will never update on its own. The
           harvest task is not authorized to judge that -- only to keep reporting it.
SCRUB      nothing -- `_scrub_env/packets_out/` and `_scrub_env/packets_raw/` held only
           `.gitkeep`. No scrub ran: `to_be_scrubbed.txt` was already empty coming into
           tonight (last struck 2026-09-21, unchanged since). No partial four-file set, no
           `P-0X_run_report.md` to fold in.
LISTS      to_be_researched: 7 waiting (P-13 Schneider National, P-14 Crawford & Company,
           P-15 Hudson River Trading, P-16 Smartsheet, P-17 HCA Healthcare, P-18 Fifth Third
           Bank, P-19 Centene) -- unchanged, since research has not finished P-13 yet.
           to_be_scrubbed: 0 waiting -- unchanged, nothing to strike.
STAGED     nothing -- `to_be_scrubbed.txt` has no entries, so `packets_raw/` stays empty for
           tonight's scrub. Refreshed `_scrub_env/ANONYMIZATION_RULES_DRAFT.md` from
           `anonymization/ANONYMIZATION_RULES_DRAFT.md` per standing instruction (already
           identical byte-for-byte; copied over regardless).
REFUSED    nothing -- no destination collisions, no partial scrub set, no research packet to
           structural-check since none was produced. The one live `RUN_REPORT.md` was left
           exactly where it is, untouched and undeleted, because its run is still IN
           PROGRESS -- a live report only gets folded into this log and deleted once its
           run is finished.
NOT YET VERIFIED -- none (no packet promoted to anonymization/ this harvest)

## 2026-09-25 harvest

RESEARCH   deferred — `_build_env/packets/RUN_REPORT.md` status line still reads `IN
           PROGRESS`, company P-13 Schneider National (started 2026-09-23 12:22 UTC,
           report file itself last modified 2026-09-23 12:20 UTC). This is now the
           SECOND consecutive harvest (2026-09-24 and tonight) to find this exact report
           unchanged — going on ~37 hours with no update. Per HARVEST_BRIEF.md Step 3,
           IN PROGRESS means touch nothing in `_build_env/`, so nothing there was moved
           or altered (there is still no packet folder to move regardless, only the
           report). Flagging for a human: a research run stuck this long without any
           report update looks more like a dead/crashed session than a slow one, but the
           harvest task is not authorized to judge that — only to report it.
SCRUB      nothing — `_scrub_env/packets_out/` and `_scrub_env/packets_raw/` held only
           `.gitkeep`. No scrub ran: `to_be_scrubbed.txt` was already empty coming into
           tonight (last struck 2026-09-21, unchanged since). No partial four-file set, no
           `P-0X_run_report.md` to fold in.
LISTS      to_be_researched: 7 waiting (P-13 Schneider National, P-14 Crawford & Company,
           P-15 Hudson River Trading, P-16 Smartsheet, P-17 HCA Healthcare, P-18 Fifth Third
           Bank, P-19 Centene) — unchanged, since research has not finished P-13 yet.
           to_be_scrubbed: 0 waiting — unchanged, nothing to strike.
STAGED     nothing — `to_be_scrubbed.txt` has no entries, so `packets_raw/` stays empty for
           tonight's scrub. Refreshed `_scrub_env/ANONYMIZATION_RULES_DRAFT.md` from
           `anonymization/ANONYMIZATION_RULES_DRAFT.md` per standing instruction (already
           identical byte-for-byte; copied over regardless).
REFUSED    nothing — no destination collisions, no partial scrub set, no research packet to
           structural-check since none was produced. The one live `RUN_REPORT.md` was left
           exactly where it is, untouched and undeleted, because its run is still IN
           PROGRESS — a live report only gets folded into this log and deleted once its run
           is finished.
NOT YET VERIFIED — none (no packet promoted to anonymization/ this harvest)

---

## 2026-09-24 harvest

RESEARCH   deferred — `_build_env/packets/RUN_REPORT.md` status line reads `IN PROGRESS`,
           company P-13 Schneider National (started 2026-09-23 12:22 UTC). Per
           HARVEST_BRIEF.md Step 3, IN PROGRESS means the research session is still working
           right now — nothing in `_build_env/` was touched (there is no packet folder there
           to move regardless, only the report). Harvest of P-13 is deferred to tomorrow.
           Neither list was touched.
SCRUB      nothing — `_scrub_env/packets_out/` and `_scrub_env/packets_raw/` held only
           `.gitkeep`. No scrub ran: `to_be_scrubbed.txt` was already empty coming into
           tonight (last struck 2026-09-21, unchanged since). No partial four-file set, no
           `P-0X_run_report.md` to fold in.
LISTS      to_be_researched: 7 waiting (P-13 Schneider National, P-14 Crawford & Company,
           P-15 Hudson River Trading, P-16 Smartsheet, P-17 HCA Healthcare, P-18 Fifth Third
           Bank, P-19 Centene) — unchanged, since research has not finished P-13 yet.
           to_be_scrubbed: 0 waiting — unchanged, nothing to strike.
STAGED     nothing — `to_be_scrubbed.txt` has no entries, so `packets_raw/` stays empty for
           tonight's scrub. Refreshed `_scrub_env/ANONYMIZATION_RULES_DRAFT.md` from
           `anonymization/ANONYMIZATION_RULES_DRAFT.md` per standing instruction (already
           identical byte-for-byte; copied over regardless).
REFUSED    nothing — no destination collisions, no partial scrub set, no research packet to
           structural-check since none was produced. The one live `RUN_REPORT.md` was left
           exactly where it is, untouched and undeleted, because its run is still IN
           PROGRESS — a live report only gets folded into this log and deleted once its run
           is finished.
NOT YET VERIFIED — none (no packet promoted to anonymization/ this harvest)

---

## 2026-09-23 harvest

RESEARCH   nothing -- `_build_env/packets/` was completely empty: no company folder, and no
           `RUN_REPORT.md` at all (not even one to fold in or delete). Per HARVEST_BRIEF.md
           Step 3, no report and no packet means research never started -- a distinct outcome
           from last night's "STOPPED" run, which at least produced a report. Neither list
           bears a research fingerprint from tonight.
SCRUB      nothing -- `_scrub_env/packets_out/` and `_scrub_env/packets_raw/` held only
           `.gitkeep`. No scrub ran: there was nothing in `packets_raw/` for it to consume,
           since `to_be_scrubbed.txt` was already empty coming into tonight (last struck
           2026-09-21, unchanged since). No partial four-file set, no `P-0X_run_report.md`
           to fold in.
LISTS      to_be_researched: 7 waiting (P-13 Schneider National, P-14 Crawford & Company,
           P-15 Hudson River Trading, P-16 Smartsheet, P-17 HCA Healthcare, P-18 Fifth Third
           Bank, P-19 Centene -- P-15 through P-19 added by Sebastian since the last harvest
           logged this list) -- unchanged by this harvest, per instruction, since research
           never touched it. to_be_scrubbed: 0 waiting -- unchanged, nothing to strike.
STAGED     nothing -- `to_be_scrubbed.txt` has no entries, so `packets_raw/` stays empty for
           tonight's scrub. Refreshed `_scrub_env/ANONYMIZATION_RULES_DRAFT.md` from
           `anonymization/ANONYMIZATION_RULES_DRAFT.md` per standing instruction (already
           identical byte-for-byte; copied over regardless).
REFUSED    nothing -- no destination collisions, no partial scrub set, no research packet to
           structural-check since none was produced, no IN PROGRESS run to defer, and no
           `RUN_REPORT.md` to consolidate or delete this time, since none existed.
NOT YET VERIFIED -- none (no packet promoted to anonymization/ this harvest)

---

## 2026-09-22 harvest

RESEARCH   nothing -- `_build_env/packets/` held only `RUN_REPORT.md`, no company folder.
           Status line read "STOPPED -- no company to build (to_be_researched.txt has no
           company lines)" (run started 2026-09-22 12:17 UTC). Per the report: packets/ was
           checked first and was empty; to_be_researched.txt contained only comment lines,
           so no company was selected; the collector prompt was never loaded and no packet
           was written; neither list was touched. This is the correct empty-queue stop per
           BUILD_BRIEF.md Step 1, not a build defect -- same shape as the 2026-09-21 entry,
           this time reported under a "STOPPED" status rather than "ABORTED" (BUILD_BRIEF.md
           still defines no status value for this case; flagging again for Sebastian, not
           acted on). Folded in full above; report deleted (see REFUSED for how).
SCRUB      nothing -- `_scrub_env/packets_out/` and `_scrub_env/packets_raw/` held only
           `.gitkeep`. No scrub ran: there was nothing in `packets_raw/` for it to consume,
           since `to_be_scrubbed.txt` was already empty coming into tonight (last struck on
           2026-09-21). No partial four-file set, no P-0X_run_report.md to fold in.
LISTS      to_be_researched: 2 waiting (P-13 Schneider National, P-14 Crawford & Company --
           added by Sebastian at 12:25 UTC, twelve minutes after tonight's research run had
           already stopped on an empty queue; not consumed by tonight's run, available for
           tomorrow's) -- unchanged by this harvest, per instruction, since research never
           touched it. to_be_scrubbed: 0 waiting -- unchanged, nothing to strike.
STAGED     nothing -- `to_be_scrubbed.txt` has no entries, so `packets_raw/` stays empty for
           tonight's scrub. Refreshed `_scrub_env/ANONYMIZATION_RULES_DRAFT.md` from
           `anonymization/ANONYMIZATION_RULES_DRAFT.md` per standing instruction (already
           identical byte-for-byte; copied over regardless).
REFUSED    nothing structural -- no destination collisions, no partial scrub set, no research
           packet to structural-check since none was produced, no IN PROGRESS run to defer.
           One housekeeping deviation, same as 2026-09-21: this session's delete-permission
           request went unanswered (unattended run, no one to grant it), so the consolidated
           `RUN_REPORT.md` could not be deleted outright -- moved instead to
           `_to_delete/RUN_REPORT_consolidated_2026-09-22.md` so the next research session
           still finds `packets/` empty. Sebastian can delete that copy at will.
NOT YET VERIFIED -- none (no packet promoted to anonymization/ this harvest)

---

## 2026-09-21 harvest

**Gap note:** last harvest logged was 2026-09-18. No harvest ran the nights of 2026-09-19 or
2026-09-20 (this session was not fired). Nothing was lost -- Rule Zero and the inventory
below found exactly the state three idle nights would produce, no more -- but flagging the
gap itself since three missed nights in a row is worth a human noticing.

RESEARCH   nothing -- `_build_env/packets/` held only `RUN_REPORT.md`, no company folder.
           **Research failed to run tonight** in the narrow sense the report itself gives:
           status ABORTED, reason quoted verbatim -- "to_be_researched.txt contains no
           company lines (queue empty)" (run started 2026-09-18 12:16 UTC). The report's
           own note calls this the correct outcome for an empty queue, not a build defect --
           BUILD_BRIEF.md Step 1 instructs exactly this stop-and-say-so behavior, and no
           company was ever selected. `to_be_researched.txt` and `to_be_scrubbed.txt` left
           untouched, per instruction: nothing was consumed, so nothing was updated. Folded
           in full above/here; the report also flagged (as a STRUCTURAL gap, its own words)
           that BUILD_BRIEF.md defines no report-status value for an empty-queue run and no
           instruction to file a report at all in that case -- recorded here for Sebastian,
           not acted on.
SCRUB      P-12 Duke Energy -- promoted to anonymization/, run record at
           _scrub_env_runs/P-12_run1/. Complete four-file set found in packets_out/
           (packet_ANON, scrub_diff, content_defects, run_report). 52/52 excerpts preserved
           (A8 B15 C11 D8 E4 F6), 8 declared quote-body edits, all 13 self-checks passed
           per the scrub's own report (company name/short forms and `http`: zero
           occurrences; diff verified programmatically, not by reading). Two BUILD-side
           defects confirmed uncorrected, both recorded in `P-12_content_defects.txt` and
           left as-is per instruction: (1) section C holds 11 excerpts against its own
           header's stated 6-10 range/cap of 10; (2) five pre-flag-vs-sweep disagreements
           in section 4 -- four over-flags (company name in section A/scope, seven
           regulatory identifiers, Aron Wallace attributed to one extra D excerpt, Lisa Sorg
           listed without qualifying that she never appears in section 1) and one genuine
           miss (section E's "North and South Carolina" place-name, handled per R5/A6
           despite the miss). Scrub's own report also flags a residual re-identification
           risk in section E (utility-sector specificity) and a recognition flag (scrubber
           recognized the company from surviving evidence, not by searching for
           identifiers) -- both recorded per the brief's instructions, neither actioned.
           Diff file copied to the run record only, per instruction that it never reach
           anonymization/ or packets/.
LISTS      to_be_researched: 0 remaining (unchanged; queue is genuinely empty, awaiting a
           line from Sebastian) · to_be_scrubbed: 0 waiting -- P-12's line struck now that
           promotion is complete.
STAGED     nothing -- `to_be_scrubbed.txt` is empty once P-12's line was struck, so
           `packets_raw/` stays empty for tonight's scrub. Refreshed
           `_scrub_env/ANONYMIZATION_RULES_DRAFT.md` from
           `anonymization/ANONYMIZATION_RULES_DRAFT.md` per standing instruction (already
           identical byte-for-byte; copied over regardless).
REFUSED    nothing structural -- no destination collisions (Rule Zero clear on
           `anonymization/P-12_packet_ANON.txt`, `packets/P-12_duke_energy/
           P-12_content_defects.txt`, and `_scrub_env_runs/P-12_run1/`), no partial scrub
           set, no research packet to structural-check since none was produced, no IN
           PROGRESS run to defer. One housekeeping deviation, same shape as prior harvests
           under this constraint: this session's delete-permission request went
           unanswered (unattended run, no one to grant it), so the consolidated
           `RUN_REPORT.md`, the scrub's own `P-12_run_report.md`, `P-12_scrub_diff.txt`
           (already copied into the run record), and the emptied `packets_raw/
           P-12_packet.txt` scratch copy could not be deleted outright -- moved instead to
           `_to_delete/` (`EMPTY_QUEUE_RUN_REPORT_consolidated_2026-09-21.md`,
           `P-12_scrub_run_report_consolidated_2026-09-21.md`,
           `P-12_scrub_diff_consolidated_2026-09-21.txt`,
           `P-12_packet_raw_scratch_2026-09-21.txt`). None carry anything a future isolated
           research/scrub session can read from within its own connected folder; only
           cleanup by a human remains.
NOT YET VERIFIED -- run: python Scripts/verify_scrub.py P-12 --company "Duke Energy" \
           --company "Duke Energy Corporation"


## 2026-09-18 harvest

RESEARCH   P-12 Duke Energy -- packet 52 excerpts (A8 B15 C11 D8 E4 F6), collector v4.11 --
           moved to packets/. RUN_REPORT status COMPLETE; all four structural checks passed
           (SECTION 1 marker, prompt version v4.11, sections A-F present, END OF PACKET
           marker present -- required and found, since v4.11 owes it). Report self-flags 4
           STRUCTURAL / 4 COSMETIC build defects, none corrected in the packet, none of
           which the harvest's checks call for -- recorded here for the rater/scorer, not
           acted on. B recency 15/15 inside the 24-month gate. Could-not-retrieve: Glassdoor
           cross-check unreachable (robots.txt + bot wall, not absence), Code of Business
           Ethics found but not quotably retrievable (PDF, no text), public code repos a
           genuine absence (GitHub org affirmatively states none), Section A vintage
           entirely unknown (all 8 excerpts accessed-dated, no publication dates exist).
           Source-pooling flag: the review site pools an unrelated same-named health-system
           employer into this profile; no clinical review entered Section 1 so no exclusion
           was required, but the stated population count is overstated by an undetermined
           amount -- flagged to the rater in de-identifiable form inside Section 1.
SCRUB      nothing -- `_scrub_env/packets_out/` held only `.gitkeep` at inventory time. No
           scrub ran overnight: `packets_raw/` had nothing staged for it after the
           2026-09-17 harvest emptied `to_be_scrubbed.txt`, and P-12 was not queued until
           today. No four-file set to route, no partial set to quarantine, nothing to
           promote or strike.
LISTS      to_be_researched: 0 remaining -- list is empty; the next research run will
           correctly stop and say so until Sebastian adds a line. to_be_scrubbed: 1 waiting
           (P-12 Duke Energy, researched 2026-09-17 v4.11) -- line left untouched, per
           instruction: not done until its scrub output is promoted.
STAGED     P-12 copied (not moved) to `_scrub_env/packets_raw/` for tonight -- the topmost,
           and only, line on `to_be_scrubbed.txt`. Refreshed
           `_scrub_env/ANONYMIZATION_RULES_DRAFT.md` from
           `anonymization/ANONYMIZATION_RULES_DRAFT.md` per standing instruction (already
           identical byte-for-byte; copied over regardless).
REFUSED    nothing structural -- no destination collision (Rule Zero clear on
           `packets/P-12_duke_energy`), no partial scrub set found, no IN PROGRESS or
           ABORTED research run to defer or fold in. One housekeeping deviation: this
           session's delete-permission request for `_build_env/` was not granted (no one
           to answer it unattended), so `RUN_REPORT.md` was folded into this entry as
           instructed but could not be deleted outright -- moved instead to
           `_to_delete/P-12_RUN_REPORT_consolidated_2026-09-18.md`, matching how prior
           harvests under the same constraint handled it. It carries nothing a future
           isolated research/scrub session can read; only cleanup by a human remains.
NOT YET VERIFIED -- nothing promoted to `anonymization/` this run, so no new verification is
           owed. P-12's own verification comes due only after it is scrubbed and promoted.

## 2026-09-17 harvest

RESEARCH   nothing -- `_build_env/packets/` was empty and no `RUN_REPORT.md` existed
           anywhere in `_build_env/` at inventory time. No report and no packet means
           research never started tonight. `to_be_researched.txt` left untouched: P-12
           Duke Energy still the sole, topmost entry.
SCRUB      P-11 Regeneron -- promoted to anonymization/, run record at
           _scrub_env_runs/P-11_run1/. Complete four-file set found in packets_out/
           (packet_ANON, scrub_diff, content_defects, run_report), scrubbed 2026-09-16,
           45/45 excerpts preserved (A7 B15 C11 D4 E2 F6) with 12 quote-body edits, all
           declared; company name/short forms, `http`, and all 13 self-checks passed per
           the scrub's own report. One BUILD-side defect confirmed uncorrected: Section C
           carries 11 excerpts against its declared 6-10 header (content-defects #8),
           header reproduced verbatim per instruction. `P-11_content_defects.txt` also
           records 8 pre-flag-block accuracy problems (7 OVER-FLAG, 1 MISS -- "Safety
           Sciences Strategy," de-branded under R4/A5 though never pre-flagged) -- none
           corrected in the packet, all recorded for the rater. Diff file copied to the
           run record only, per instruction that it never reach anonymization/ or
           packets/.
LISTS      to_be_researched: 1 remaining (P-12 Duke Energy) - to_be_scrubbed: 0 waiting --
           P-11's line struck now that promotion is complete.
STAGED     nothing -- `to_be_scrubbed.txt` is empty once P-11's line was struck, so
           `packets_raw/` stays empty for tonight's scrub. Refreshed
           `_scrub_env/ANONYMIZATION_RULES_DRAFT.md` from
           `anonymization/ANONYMIZATION_RULES_DRAFT.md` anyway, per standing instruction
           (already identical byte-for-byte; copied over regardless).
REFUSED    nothing -- no destination collisions (Rule Zero clear on `anonymization/`,
           `packets/P-11_regeneron/`, and `_scrub_env_runs/P-11_run1/`), no partial scrub
           set, no research packet to structural-check since none was produced.
VERIFIED   2026-09-16 (operator note above) -- P-11 was already run through
           `Scripts/verify_scrub.py` before this harvest, per the 2026-09-16 operator
           note: 45/45 parsed both sides, harness counts match, 12/12 declared quote
           edits with 0 undeclared, 0 identifiers found. No `NOT YET VERIFIED` line
           written for P-11, per that note's instruction.

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
