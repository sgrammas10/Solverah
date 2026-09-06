# BUILD BRIEF — read this and execute it

You are building ONE company evidence packet for the Solverah ground-truth set.

**Say only this to start a build:** *"Read ground_truth/BUILD_BRIEF.md and build P-0X."*
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

---

## Step 1 — Which company

If the operator named one, use it. If not, ask, and stop until they answer.

| ID | Company | State |
|---|---|---|
| P-01 | Oscar Health | never built clean — folder empty |
| P-02 | Best Buy | needs clean rebuild |
| P-03 | Akuna Capital | needs clean rebuild |
| P-04 | R/GA | needs clean rebuild |
| P-05 | Doist | needs clean rebuild |
| P-06 | Raymond James | never started |

Do not look at any existing packet file for the company you are building, even your own. If one
exists, ignore it completely — you are producing an independent build.

---

## Step 2 — Load the collector prompt

**If it was attached to this conversation as a file, use that.** Otherwise read the
**highest-numbered** `Company_Culture_Evidence_Collector_v*.md` available to you. Read it in full,
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
