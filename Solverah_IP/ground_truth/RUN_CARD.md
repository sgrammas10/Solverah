# Operator guide — running the six builds

**⚠ THIS FILE IS FOR YOU, NOT FOR A BUILDER.** It contains findings from earlier builds, including
an answer key for P-01. Pasting it into a build session contaminates the run. The builder reads
`BUILD_BRIEF.md`, which is written to be safe.

---

## How you start a build

**Do NOT build inside the Solverah IP Planner project.** A new chat inside the project is not a
clean session — it automatically inherits the project's custom instructions, its knowledge documents
(handoffs, decisions files) and `memory.md` from previous conversations. That is worse than a stray
paste, because it arrives silently and you never see it happen.

Two ways to run it. Use the second unless you have a reason not to.

### Option A — plain session, repo folder connected

Open a chat **outside the project**, connect `Solverah_IP`, and type:

> Read ground_truth/BUILD_BRIEF.md and build P-01.

The brief instructs the builder not to open handoffs, decisions files, defect logs or other packets.
That is *instructed* isolation — it depends on the builder obeying.

### Option B — isolated build folder (recommended)

`ground_truth/_build_env/` contains only the brief, the current collector prompt, and an empty
`packets/` directory. Open a chat **outside the project**, connect **only `_build_env`**, and type:

> Read BUILD_BRIEF.md and build P-01.

Nothing contaminating is reachable, so isolation is *structural* rather than instructed. When the
build finishes, copy `_build_env/packets/P-0X_*` back into `ground_truth/packets/`.

**The failure mode of Option B is a stale prompt copy.** Before each build round, re-copy the newest
`Company_Culture_Evidence_Collector_v*.md` into `_build_env/` and delete the old one. Exactly one
should ever be present, or the builder will pick a superseded version and you won't notice.

### Either way

**Six companies means six fresh sessions, one line each.** Not one session doing six — the second
company would be built by a session that already knows the first company's evidence, which is the
contamination that got the P-01 partial quarantined. Rule Zero in the brief makes the builder refuse
a second company, so it's enforced rather than remembered.

---

## Your checklist before each run

- [ ] **Outside the project.** Not a new chat within Solverah IP Planner — that inherits project
      knowledge and memory automatically.
- [ ] **Nothing pasted in.** No handoffs, no decisions files, no other packets, no defect log, no
      notes from me. The prompt carries what the builder needs — that's why the defect register
      lives inside it now.
- [ ] **If using Option B:** exactly one `Company_Culture_Evidence_Collector_v*.md` in `_build_env/`,
      and it is the newest one.
- [ ] **Browsing enabled, with both retrieval methods available** — plain HTTP fetch and a
      JavaScript renderer. Defect D13: they reach different sources and neither is better.
- [ ] **Model string pinned and written down.** The exact string, not an alias.
- [ ] The right folder is connected — `_build_env` for Option B, `Solverah_IP` for Option A.

---

## During the run — do not help

The builder loads the collector prompt itself and saves the packet itself. You should not need to
type anything after the opening line.

**Do not help.** This is the hard part and it is the whole point.

If the builder asks a clarifying question, that is data — it means the prompt is ambiguous. Write
the question down verbatim, answer as minimally as you can, and mark the run **assisted**. If you
find yourself explaining something the prompt should have said, you have found a defect.

If it gets stuck on retrieval, let it work the fallback chains. Getting stuck and *recording it
correctly* is a pass. "Publication found, current, yields nothing on working practice" is a
legitimate and informative outcome. Silently guessing is the failure.

The brief already asks the builder to self-report defects and to refuse a second company, so you
should not have to prompt for either. If it tries to start a second company, stop it — that is
itself a defect worth logging.

---

## What the builder saves (verify it did)

```
ground_truth/packets/P-0X_<company>/P-0X_packet.txt
```

It stamps this at the top of the file. Check that it is there and that the model string is real:

```
BUILD RECORD
  prompt version : v4.6
  model string   : <exact string>
  built          : <date>
  environment    : clean session, no prior context
  assisted       : NO   (or: YES — list every question you answered)
```

That block is not bookkeeping. If two builds of the same company disagree later, the model string is
the first thing you check — same reason `model_run` sits on every score row.

---

## Classify each defect it reports

The builder classifies its own defects. Re-classify them yourself — it is grading its own work, and
it has an incentive to call things cosmetic.

**The test: did it change what evidence reached Section 1, or how a section was scoped?**

| | STRUCTURAL | COSMETIC |
|---|---|---|
| Effect | Wrong or missing evidence, wrong scope | Wording, numbering, formatting, a dead URL |
| Action | Revise prompt, new version, **counter resets** | Log it, carry on, counter does not reset |

Worked examples from real builds:

* *"The largest title bucket's newest review was 31 months old"* → **STRUCTURAL.** Changed which
  reviews reached Section 1. This is what broke v4.5.
* *"Section B rules B2, B3 and B4 each appear twice"* → **COSMETIC.** Confusing, changed nothing.
* *"Reviews posted with no job title couldn't be placed in any bucket"* → **STRUCTURAL.** Evidence
  was excluded.
* *"The careers page returned a Loading… shell"* → **COSMETIC if** the builder switched methods and
  got it; **STRUCTURAL if** the prompt led it to record an absence.

When it's genuinely ambiguous, call it structural. The cost of one extra revision round is a day.
The cost of freezing on a bad instrument is six packets and a rater's time.

---

## The freeze decision

**Zero structural defects → v4.6 freezes.** Then:

1. Rebuild all six packets against the frozen version, clean-room each time.
2. Close the ground-truth set.
3. Onboard Rater B — **not before**. A rater who starts pre-freeze is scoring a different
   instrument, which is exactly what made the previous rater's scores unmergeable.

**One or more structural defects →** revise, bump the version, and the next company becomes the
candidate. Don't rebuild the earlier packets yet; they get rebuilt once, at the end, against
whatever finally freezes.

The bar is deliberately low. One clean packet proves very little about the instrument. It exists to
**terminate the loop**, not to certify anything — every prior version was revised in response to a
defect, and without a stopping rule "revise until no failures" means revise forever.

---

## Build order

1. **P-01 Oscar Health** — current candidate. Never built clean; the folder is empty.
2. **P-06 Raymond James** — never started. Expect it to resemble P-02 (advisors dominating the
   review population the way store staff did).
3. **Rebuild P-02, P-03, P-04, P-05** against the frozen version.

Nothing in `packets/` is clean-room right now. That reads like a step backwards; the alternative was
six packets built on an instrument nobody had tested in the environment it has to run in.

---

## Answer key — read only AFTER the run

`_quarantine_not_ground_truth/P-01_CONTAMINATED_do_not_use_as_ground_truth.txt` is a P-01 partial
built with full knowledge of every prior defect. **Never paste it into a builder session.** Use it
afterwards to tell a genuine finding from a rediscovery.

What it already established about Oscar Health:

* Company-wide newest review **2026-04-13**; largest title bucket's newest **2024-01-24**. v4.6's
  recency frame should make this a non-issue. **If Section B still comes back stale, the frame
  change failed — that is structural and important.**
* Untitled "Anonymous" reviews are in the recent stream (rule B2a should catch them).
* An employer response dated 2021-02-22 sits in the review stream (rule B2b should catch it).
* The job-titles index omits "Care Guide" while the reviews page lists it first (D21).
* Indeed shows company-wide subratings on title-filtered pages — third company confirming this.
* Direct-Archives EDGAR works; `browse-edgar` doesn't (D16).
* Section F was already built and is correct. **A clean run should reproduce it independently** —
  compare the two as a free consistency check. Do not copy the old one forward.

Found unprompted → v4.6 is working. Missed → each miss is a defect with a known cause, which is the
cheapest kind to fix.
