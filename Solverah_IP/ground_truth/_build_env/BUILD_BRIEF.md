# BUILD BRIEF — read this and execute it

You are building ONE company evidence packet for the Solverah ground-truth set.

**Say only this to start a build:** *"Read BUILD_BRIEF.md and build P-0X."*
Everything else is below.

---

## RULE ZERO — ONE COMPANY PER SESSION. NON-NEGOTIABLE.

**Build exactly one company in this session, then stop.**

Do not build a second. Do not "get a head start" on the next one. Do not read another company's
packet for reference. If you have already built a company in this conversation, **refuse** and tell
the operator to open a fresh session.

Production runs this prompt against one company with no memory of the previous one. A packet built
by a session that already knows what the last company's evidence looked like was built by an
instrument production does not have. That contamination is invisible in the output — the packet
simply looks better than it should — which is exactly why the rule is absolute rather than a
preference.

**You should have access to exactly two things: this brief and the collector prompt.** If a folder
is connected and you can see anything else — other packets, handoffs, decisions files, defect logs —
you are in the wrong folder. Stop and tell the operator.

**Do not ask for, and refuse if offered,** any handoff, decisions file, defect log, or another
company's packet. Those carry findings from earlier builds and reading them invalidates this run.

### The output folder must be EMPTY before you start. Check it first, every run.

If `packets/` contains anything at all — a folder, a packet, a stray file — **stop
immediately and report it. Do not build, and do not read what is there.**

This is the failure mode a nightly schedule creates that a human operator never did. One
company per session stops you building two. It does nothing about last night's finished
packet still sitting in the folder you just connected: fresh session, one company, and the
previous build in your context anyway. The harvest step is supposed to clear it before you
run, so a non-empty folder means the harvest did not happen — which is worth one lost night
to find out, because the alternative is a contaminated packet that nothing downstream can
detect.

---

## Step 1 — Which company

If the operator named one, use it.

**If nobody named one — the normal case on a scheduled run — open `to_be_researched.txt`
and take the topmost non-comment line. Do not ask.** There is no operator awake to answer,
and a run that stops to ask has burned a night and produced nothing.

Say which line you took, in one line, before you start.

If the file has no company lines, **stop and say so.** That is a correct run. Do not choose
a company yourself and do not go looking for one — which company enters the set is a
recorded decision about dimension-pole coverage, not a gap for you to fill.

### When the packet is written, update the two lists IN THIS ORDER

1. **First**, append one line to `to_be_scrubbed.txt`:
   `P-##    Company Name    researched YYYY-MM-DD (vX.Y)`
2. **Then**, and only then, remove that company's line from `to_be_researched.txt`.

**The order is not stylistic.** A run that dies between the two steps leaves the company on
both lists — a duplicate, which is visible and recoverable. Reverse the order and the same
crash removes it from one list without adding it to the other: the company is silently gone,
and nothing downstream will ever notice it is missing.

**Do neither of these until the packet file actually exists on disk.** A list that says a
packet was built is worth nothing if the packet is not there.

### Open the run report NOW, before you collect anything

**The moment you know which company you took, create `packets/RUN_REPORT.md`** (next to the
packet folder, not inside it). Its first two lines are exactly this, and you keep them current
for the whole run:

```
status  : IN PROGRESS
company : P-##  <Company Name>   (started <date> <time>)
```

Set `status` to `COMPLETE` only once the packet is on disk and both lists are updated. If you
stop for any reason — a source you cannot reach, an approval you cannot obtain, a tool that
will not run — set it to `ABORTED — <what stopped you>`, name the last thing you finished and
the first thing you could not, and stop there.

**Why this comes first rather than last.** An empty `packets/` folder is the same on disk
whether this task never started, died halfway, or is still working. Those need three different
responses from the harvest, and it cannot tell them apart. On 2026-09-08 the research session
was still browsing at 06:00, held up by site-access approvals, when the harvest fired; the
harvest found an empty folder and recorded that the night had produced nothing, which was the
only honest thing it could say. The status line is what makes that distinguishable.

**A diagnosed failure is worth far more than a silent one.** Never delete a partial report to
tidy up, and never leave the folder clean so it looks clean.

By the end of a successful run the report also covers:

- which company you took, and what remained on `to_be_researched.txt` after you
- the packet path, its section-by-section excerpt counts, and the collector version
- anything you could not retrieve, and what you did instead
- any defect you noticed in your own build
- both list updates, confirmed as done

The harvest carries this out and folds it into `PIPELINE_LOG.md`, which is what a human
reads in the morning. **Do not create a log file that stays in this folder.** A running log
here would name every company built so far, and the next session would read it — the exact
cross-run leakage RULE ZERO exists to prevent.

Do not look at any existing packet file for the company you are building, even your own. If one
exists, ignore it completely — you are producing an independent build.

---

## Step 2 — Load the collector prompt

**If it was attached to this conversation as a file, use that.** Otherwise read the
**highest-numbered** `Company_Culture_Evidence_Collector_v*.md` available to you. **Version
numbers are numeric, not alphabetical — v4.10 is newer than v4.9.** Read it in full,
including its defect-register appendix — the register is there because rules that live outside the
prompt have repeatedly failed to reach the person doing the work.

If you cannot locate the collector prompt at all, **stop and say so.** Do not attempt the build from
this brief alone; this brief is not the specification and does not contain it.

Record which version you used.

---

## Step 3 — Build

Execute the collector prompt against your company, substituting the company name for
`[COMPANY NAME]`. Follow it exactly as written. It is the specification; this brief only tells you
how to run it.

Two things it depends on:

* **Browsing.** Open and quote from actual pages. A search-engine snippet is a paraphrase and is
  never an acceptable quote.
* **Two retrieval methods.** Plain HTTP fetch and a JavaScript renderer reach *different* sets of
  pages and neither is better. First-party sites (careers, culture, blogs) are often JS apps and
  need the renderer; review and job aggregators are server-rendered and bot-defended, where the
  renderer gets walled and plain fetch works. **Try both before recording anything as absent.**

**Never sign in to anything.** Content reachable only while authenticated makes the packet richer
than a production scraper can reproduce.

**Do not ask the operator to resolve ambiguity if you can avoid it.** Make a defensible choice,
record it, and list it as a defect in Step 5. A question you had to ask is a prompt failure, and it
is more valuable recorded than resolved verbally.

---

## Step 4 — Deliver the packet

**If you can write files:** save to `packets/P-0X_<company_slug>/P-0X_packet.txt`.

**If you have no filesystem** (nothing connected, prompt supplied as an attachment or pasted):
output the complete packet as plain text in the chat, in one block, for the operator to save. This
is the expected mode, not a degraded one — production has no filesystem either. Do not summarise,
truncate, or offer to continue later. The packet is the deliverable and it must be complete.

Either way, put this at the very top, before anything else:

```
BUILD RECORD
  prompt version : v4.X
  model          : <your exact model string, not an alias>
  built          : <date>
  environment    : clean session, one company, no prior packet context
  assisted       : NO      (or: YES — list every question the operator answered)
```

If you genuinely cannot determine your exact model string, write `model: UNKNOWN — operator to
fill` rather than guessing. A wrong string is worse than a blank one.

---

## Step 5 — Self-report defects. This is not optional.

The build is only half the deliverable. Finish by listing **every** point where the collector prompt
was unclear, contradictory, missing an instruction you needed, or told you to do something that did
not work — plus anything you had to decide for yourself.

**Do not fix them. Do not soften them. List them**, each with the prompt section it relates to.

For each, classify it yourself and say why:

* **STRUCTURAL** — it changed what evidence reached Section 1, or how a section was scoped.
* **COSMETIC** — wording, numbering, formatting, a dead URL. Confusing but changed nothing.

When genuinely torn, call it structural.

A build that produces a good packet and an empty defect list is a suspicious result, not a good one.
Every build so far has surfaced something.

---

## Step 6 — Stop, and hand back

End with a short summary for the operator:

1. Company and prompt version used.
2. Yield per section against the prompt's minimums — what passed, what didn't.
3. **The defect list, structural first.**
4. Anything you could not retrieve, and what you tried. Distinguish clearly between *did not exist*,
   *existed but was stale*, and *existed but could not be reached* — these are three different
   findings and only the first is an absence.
5. One line: *"One company built. Open a fresh session for the next."*

Then stop. Do not start another company.
