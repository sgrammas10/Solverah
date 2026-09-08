# HARVEST BRIEF — read this and execute it

**Say only this to start:** *"Read HARVEST_BRIEF.md and harvest."*

Connect the `ground_truth/` folder — this one. You need to see both staging areas and all
the destinations, which is why this task is not isolated the way the other two are.

You are moving files, editing one list, and appending to one log. **You are not building,
scrubbing, judging, or improving anything.** If a file looks wrong, say so and leave it.

---

## Why this task exists

Two other scheduled tasks run each night, each in its own session:

- **research** — connects `_build_env/`, takes the top line of `to_be_researched.txt`,
  writes a raw packet, appends to `to_be_scrubbed.txt`, removes its line from the first list
- **scrub** — connects `_scrub_env/`, de-identifies the single packet in `packets_raw/`

Both are isolated on purpose. A research session that can see last night's packet builds a
contaminated one, and *"that contamination is invisible in the output — the packet simply
looks better than it should."* One company per session does not prevent that; it only stops
one session doing two companies. What prevents it is the folder being **empty** when the
session starts.

That is your job. **If you fail, tomorrow's research task refuses to run** — its brief tells
it to stop on a non-empty output folder — so a missed harvest costs one night, not a
corrupted packet.

You are also the only task that can see both `_build_env/` and `_scrub_env/`. That is why
list bookkeeping across the boundary lands here rather than in the task that logically owns
it: the scrub cannot remove its own line, because the list lives in a folder it must not be
able to read.

---

## RULE ZERO — NEVER OVERWRITE. STOP INSTEAD.

If a destination file already exists, **stop, leave everything where it is, and report it.**

Do not overwrite, do not rename around it, do not merge. A packet already at the destination
means something unexpected happened — a rerun, a manual copy, two harvests in one night —
and every one of those wants a human, not a guess. Losing one night is recoverable. Silently
replacing a verified packet with an unverified one is not.

---

## Order matters. Do the steps in this order.

Step 2 clears the scrub's input; step 4 refills it. Reverse them and tomorrow's scrub
session sees two packets and cannot tell which is its own.

---

## Step 1 — Inventory before you touch anything

Report what you find, by filename:

- `_scrub_env/packets_out/` — last night's scrub output
- `_scrub_env/packets_raw/` — the packet the scrub consumed
- `_build_env/packets/` — last night's research output, plus its `RUN_REPORT.md`
- `_build_env/to_be_scrubbed.txt` — packets awaiting or undergoing de-identification

`.gitkeep` files are structural. Ignore them everywhere; never move or delete one.

An empty set is a normal result — neither task ran, or the lists are empty. Say so and stop.
Do not go looking for work.

---

## Step 2 — Route the scrub output, then clear the scrub input, then strike the line

A complete scrub produces **four** files: `P-0X_packet_ANON.txt`, `P-0X_scrub_diff.txt`,
`P-0X_content_defects.txt`, `P-0X_run_report.md`.

**If any is missing, the scrub did not finish.** Move the whole partial set to
`_scrub_env_runs/P-0X_FAILED_<date>/`, promote nothing, strike no line, and report it. A
partial scrub is a failed scrub, and its line must stay on `to_be_scrubbed.txt` so it is
retried.

With all four present:

| file | goes to | why |
|---|---|---|
| `P-0X_packet_ANON.txt` | `anonymization/` | the rater- and scorer-facing artifact |
| `P-0X_content_defects.txt` | `packets/P-0X_<slug>/` | belongs with the build record it describes |
| all four, as copies | `_scrub_env_runs/P-0X_run<N>/` | the run record |

**The diff never leaves the run record.** Under amendment A6(a) it holds the minted-token
mapping — the identifying strings that were removed — so it must never reach a folder a
rater reads. Never copy it to `anonymization/` or `packets/`.

Number the run folder from what exists: if `P-0X_run3/` is there, yours is `run4`.

Then **empty `_scrub_env/packets_raw/`** — that packet is scrubbed, and its build record
already lives in `packets/`, so this copy is scratch. Delete it.

Then **remove that packet's line from `_build_env/to_be_scrubbed.txt`.** Only now: the line
means *awaiting or undergoing de-identification*, and it is not done until the output is
promoted.

---

## Step 3 — Route the research output

The research task writes `_build_env/packets/P-0X_<company_slug>/P-0X_packet.txt`.

Before moving it, check three things by reading the file. Cheap, and they catch a build that
died halfway:

1. It contains `########## SECTION 1` **and** `########## END OF PACKET ##########`.
2. Its header carries a `prompt version : vX.Y` line.
3. Sections A through F are present.

**If any check fails**, move the folder to `packets/P-0X_<slug>_INCOMPLETE_<date>/`, report
it, and **put the company back on the top of `to_be_researched.txt`** while removing its line
from `to_be_scrubbed.txt`. The research task already moved it across on the assumption the
packet was sound. It was not, so the move has to be undone, or the company is lost from both
lists.

With the checks passing, **move** the folder to `packets/P-0X_<company_slug>/`.

Leave both lists alone — research has already updated them correctly.

### Read `RUN_REPORT.md`'s status line before you touch anything in `_build_env/`

It says `IN PROGRESS`, `COMPLETE`, or `ABORTED — <reason>`.

**`IN PROGRESS` means the research session is still working right now. Touch nothing in
`_build_env/`.** Do not move a packet, do not delete the report, do not change either list.
Move and stage the scrub side as normal, then say in the log that research was still running
and its harvest is deferred to tomorrow. A research run can take all night when site approvals
are slow — that happened on 2026-09-08 — and harvesting a packet out from under a session that
is still writing it is how a half-built packet reaches `packets/` looking finished.

**`ABORTED` means the run failed, and the report is that night's only deliverable.** Fold it
into the log in full — which company, how far it got, what stopped it — then delete it. Change
neither list: research updates them only after a packet exists on disk, so the company is still
correctly queued and will simply be retried. Say plainly that the research failed and quote the
reason it gave. Never soften that into "nothing to do", which is the wording for an empty queue;
the two must not read alike.

**A report with no status line at all** was written by a session predating this rule — the
2026-09-08 run is one, since the rule was added while it was still working. Judge that one by
the packet: if a packet folder is there and passed its checks, treat the run as `COMPLETE` and
harvest it normally; if there is no packet, treat it as `ABORTED` and say so.

**No report and no packet** means research never started. Say that, and say it as a distinct
outcome from the three above.

---

## Step 4 — Stage tomorrow's scrub

Only if `_scrub_env/packets_raw/` is now empty.

Take the **topmost** line of `_build_env/to_be_scrubbed.txt`, find that packet at
`packets/P-0X_<slug>/P-0X_packet.txt`, and **copy** it into `_scrub_env/packets_raw/`.
Copy, never move — `packets/` holds the permanent build record.

Take the top line, not the newest packet. The list is the queue, and it may hold a backlog
if a scrub failed or was skipped; the oldest waiting packet goes first.

If `to_be_scrubbed.txt` has no entries, leave `packets_raw/` empty. Tomorrow's scrub will
correctly find nothing to do.

**Then refresh the ruleset, every run, whether or not you staged a packet.** Copy
`anonymization/ANONYMIZATION_RULES_DRAFT.md` over `_scrub_env/ANONYMIZATION_RULES_DRAFT.md`.

The scrub folder holds a *copy* rather than the file itself, because a session that could see
`anonymization/` could see every packet already scrubbed. A copy drifts. On 2026-09-07 the
scrub env's copy predated amendment A6(a) by a day, and P-09 duly printed five removed ATS
requisition ids into its own rater-facing scrub log — the exact thing A6(a) forbids — because
the rule had never reached the session applying it. The scrubber followed the rules it was
given. Overwriting the copy nightly is what keeps that sentence true.

---

## Step 5 — Append to the pipeline log

`PIPELINE_LOG.md`, in this folder. Newest entry at the top. One entry per harvest:

```
## 2026-09-08 harvest

RESEARCH   P-11 Regeneron — packet 4x excerpts, collector v4.8 — moved to packets/
SCRUB      P-10 Twilio — promoted to anonymization/, run record at _scrub_env_runs/P-10_run1/
LISTS      to_be_researched: 1 remaining · to_be_scrubbed: 1 waiting (P-11)
STAGED     P-11 copied to _scrub_env/packets_raw/ for tonight
REFUSED    nothing
NOT YET VERIFIED — run: python Scripts/verify_scrub.py P-10 --company "Twilio"
```

Fold in what the two `RUN_REPORT.md` / `P-0X_run_report.md` files say — the excerpt counts,
the self-check results, anything either task flagged rather than decided. Then delete those
two report files; they have been consolidated and a stray report left in a staging folder is
something the next isolated session could read.

**This log is the thing a human reads in the morning.** Write it for someone who was not
here: name what happened, not what you did.

---

## Step 6 — Prove the staging areas are clean, and report

Report the contents of `_build_env/packets/`, `_scrub_env/packets_out/` and
`_scrub_env/packets_raw/`.

The first two must be empty apart from `.gitkeep`. `_scrub_env/packets_raw/` holds **exactly
one** packet, or none if nothing is waiting.

**Two or more packets in `packets_raw/` is a failure state** — tomorrow's scrub cannot tell
which is its own. Say so loudly rather than choosing one.

Then report, briefly: what moved, which lines changed on which list, what you refused and
why, and the `NOT YET VERIFIED` line for every packet promoted to `anonymization/`.

You cannot verify a packet and must never claim one is verified. The structural checks in
step 3 catch a packet that died; they say nothing about whether quote bodies survived intact
or whether every identifier is gone. That check is `Scripts/verify_scrub.py`, it is run by a
human or an agent with a Python environment, and it is the one that decides whether the
packet is sound.
