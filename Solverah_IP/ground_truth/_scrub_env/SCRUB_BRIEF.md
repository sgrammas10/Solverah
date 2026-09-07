# SCRUB BRIEF — read this and execute it

You are de-identifying ONE finished company evidence packet for Solverah.

**Say only this to start:** *"Read SCRUB_BRIEF.md and scrub the packet in
packets_raw."* Everything else is below.

A scheduled run cannot name the packet, because the operator is asleep and the harvest
chose it. You do not need the name: exactly one packet is put in front of you, and that
is the one you scrub.

This is the second of two passes. Someone else already built the packet. You are not
collecting evidence, not judging the company, and not improving the writing. You are
removing identifiers and leaving everything else exactly as you found it.

---

## RULE ZERO — ONE PACKET PER SESSION. NON-NEGOTIABLE.

**Scrub exactly one packet in this session, then stop.**

Do not scrub a second. Do not read another company's packet "for reference" on how a
scrub should look. If you have already scrubbed a packet in this conversation, **refuse**
and tell the operator to open a fresh session.

The reason is not tidiness. A scrubber that has seen three packets from the same sector
starts normalising the fourth toward them — smoothing phrasing, matching a house style,
"fixing" the one that looks different. That is an uncontrolled edit to the instrument the
entire calibration set depends on, and it is invisible in the output, because the packet
simply looks tidier than it should.

**You should have access to exactly three things:** this brief, the ruleset, and one raw
packet in `packets_raw/`. If a folder is connected and you can see anything else — other
packets, handoffs, decisions files, the repo — you are in the wrong folder. Stop and tell
the operator.

**Do not ask for, and refuse if offered,** the roster, a company list, another packet, or
anything naming which company this is. If you work out which company it is from the
evidence, that is expected and harmless — say so in the scrub log and keep going. Do not
search for anything.

---

## RULE ONE — EDIT THE FILE. NEVER RETYPE IT.

**This is the rule most likely to be broken and the one with the worst consequences.**

Work by copying the raw file and making only the specific substitutions the ruleset calls
for. Never reproduce a quote body by typing it out again.

It has already gone wrong. P-02 and P-05 were retyped rather than edited. The retyping
silently converted ASCII hyphens into em dashes **inside quote bodies**, and three quotes
then failed citation verification on punctuation alone — quotes that were substantively
untouched and still could not be matched.

The scorer and the rater tooling both string-match cited quotes against packet text. **A
quote that differs from the source by one character is a quote that cannot be verified.**

So, inside a quote body, never change:

- dashes (`-` is not `–` is not `—`), quote marks (`'` is not `’`), or ellipses
- spacing, line wrapping, or capitalisation
- spelling — including misspellings. R7 keeps source typos deliberately.

The only edits permitted inside a quote body are the ones the ruleset names:

- **R2** — the company name
- **R3** — named humans
- **R4 / A5** — branded names: internal programmes, external brands, joint ventures,
  subsidiaries, and internal organisation abbreviations
- **R6 / A1** — identifying figures, replaced with magnitude language
- **R5 / A6** — place names, including named agencies and administrative regions

Nothing else. Not one character.

**On R5 (amendment A6):** reuse the token the attribution already uses where one exists —
a rater who sees `[Site G]` in an attribution and the city printed one clause later is
worse off than under either consistent answer. Where the place has **no** pre-flag token,
**mint one** and log it with the string it replaced. The Section 4 pre-flag block does not
reach past section B, so this will happen; P-07 carried a named state employment agency and
a county in a section E quote body, and a WARN filing plus an agency plus a county plus a
date identifies harder than the city names R5 already removes.

**On R4 (amendment A5):** the test is whether the clause survives the rewrite. `Accelera`
becomes `[name stripped]` and the sentence still says what the company builds; that is the
shape to aim for. If removing the branded token would take the claim with it, you are
looking at signal rather than a fingerprint — leave it and say so in the log.

---

## RULE TWO — EVERY EDIT IS DECLARED ON THE EXCERPT LINE

Per amendment A4. A bracketed declaration goes on the excerpt line itself, where a rater
reads it — for example `— [proper noun rewritten in brackets; clause otherwise verbatim]`.

A scrub log alone is not enough. **An edit recorded only in a scrub log is not a recorded
edit**, because nobody reads the log while rating. Two real quote-body edits were found in
a fidelity audit precisely because they were correct under the rules and invisible where
they mattered.

Write the log as well. But the line declaration is the one that counts.

---

## RULE THREE — PUT A BLANK LINE BEFORE EVERY EXCERPT BULLET

This is the one place you are *required* to change the file's whitespace, and it does not
contradict Rule One, because it happens **outside** quote bodies. Not one character inside
a quote changes. What changes is the blank line separating an excerpt from whatever sits
above it.

**Why it is mandatory.** The citation harness finds excerpts by splitting the packet into
blank-line-delimited blocks and testing whether each block *starts* with a bullet. A bullet
that shares a block with the line above it — a posting header, a note, another bullet — is
not seen as an excerpt at all. It does not error. The excerpt silently ceases to exist for
every downstream consumer, while reading perfectly to a human.

**This is measured, not hypothetical.** P-07's section C declares ten job-posting excerpts.
Its posting headers sit directly against their bullets with no blank line, and the harness
parses **zero** of the ten. Meanwhile P-02 and P-05 parse to zero and P-06 to six *in raw
form*, and their hand-scrubbed versions parse to 48, 23 and 46 — because the hand scrub
retyped them and retyping happened to insert the blank lines. The retyping that caused the
em-dash defect was, at the same time, accidentally repairing the packets. Rule One removes
the accident in both directions, so this rule puts the repair back deliberately.

So: **every excerpt bullet begins a block.** A blank line above it, always — after a
section header, after a posting or group header, after a note, and between consecutive
bullets. Change nothing else about the spacing.

---

## The ruleset is the authority

`ANONYMIZATION_RULES_DRAFT.md` in this folder holds R1–R8, amendments A1–A4, and the four
judgment calls JC-1–JC-4. All of it is signed off. **Read it in full before you touch the
packet**, and apply it as written — do not improve on it, and do not extend a rule to a
case it does not cover without saying so in the log.

Three things in it are counter-intuitive and get missed. They are not optional:

- **Industry is not scrubbed.** Job titles give the sector away in every real packet, and
  the model adjusts for industry anyway. Do not attempt it. Do not soften job titles.
- **Source typos stay** (R7). `there [sic]`, `bexause`, `horrible.The` — verbatim.
- **`Remote` stays literal** (R5). It is work-mode signal, not a location.

And one that decides how the whole thing reads: **scrub identifiers, not signal.** A
distinctive phrase is usually the most identifying string *and* the highest-information
line in the section. The ruleset's governing principle explains why deleting it is the
wrong trade. When you are tempted to remove something because it "feels identifying,"
that principle is the test to apply.

---

## Steps

1. **Read the ruleset end to end.** Then read the raw packet end to end, before editing
   anything.
2. **Confirm exactly one packet in `packets_raw/`** (ignore `.gitkeep`).

   **Zero is normal and is a correct run** — it means nothing is waiting. Say so and
   stop. Do not go looking for a packet elsewhere; every other packet on this machine
   belongs to a company you must not see.

   **Two or more is a failure state.** You cannot tell which is yours, and guessing
   would scrub a packet that is already scrubbed or skip one that is not. Stop and
   report it.
3. **Work section by section.** Apply the ruleset. Preserve section order, section
   markers, and excerpt order exactly as the raw packet has them.
4. **Preserve the excerpt count.** Under A3, a claim appearing in two sections is kept in
   both, with a recurrence note attached to the second — it is never deleted. If your
   output has fewer excerpts than the raw packet, you have made a mistake.
5. **Write the scrubbed packet** to `packets_out/P-0X_packet_ANON.txt`, in the output
   format below.
6. **Write a diff** to `packets_out/P-0X_scrub_diff.txt` — every changed line, raw above
   scrubbed. This is the artifact that makes the scrub checkable instead of trusted, and
   it is the reason this pass is separate from the build.
7. **Run the self-check** below and record its result.
8. **Write `packets_out/P-0X_content_defects.txt`** if you found anything wrong with the
   packet itself — see "Content defects" below.
9. **Write `packets_out/P-0X_run_report.md`** — which packet you scrubbed, the per-section
   bullet table from self-check 13, all thirteen self-check results, every judgment call you
   made, and anything you flagged rather than decided. The harvest carries it out and folds
   it into `PIPELINE_LOG.md`. **Never leave a log file in this folder** — a running log would
   name every company scrubbed so far, and the next session would read it.

**`packets_out/` holds exactly those four files and nothing else.** Assembling the packet from
intermediate files is encouraged -- it is how Rule One gets followed mechanically rather than
promised -- but write intermediates to the system temp directory, never into `packets_out/`.

Two reasons, and the second is the one that bites. A stray `_body.tmp` is another packet's text
sitting in a folder the next session connects. And a scrubber that has to tidy up after itself
ends up asking for permission to delete files in the only folder holding its own output -- on a
scheduled overnight run there is nobody awake to answer, and no scrub has any business holding
that right to begin with.

---

## Output format

Match the existing scrubbed packets exactly. Header block first:

```
PACKET P-0X   ·   DE-IDENTIFIED   ·   RATER-FACING
  scrubbed from : P-0X_packet.txt (build v4.N, model <model>, built <date>)
  ruleset       : ANONYMIZATION_RULES_DRAFT.md
  scrubbed      : <date>
  status        : <DRAFT / final, plus any caveat carried from the source packet>

  DO NOT SEARCH FOR ANY PHRASE IN THIS PACKET. If you recognise the company, that is
  expected and is not a failure — record it on the recognition flag and keep scoring
  from the evidence in front of you, not from what you know.
```

Then the packet body, section markers unchanged (`########## SECTION 1 — EVIDENCE PACKET
##########`, `--- A. CAREERS / VALUES PAGE (5-8 excerpts) ---`, and so on).

Excerpt lines keep their existing shape: the quote, then the source descriptor, source
class, date, retrieval note, then any bracketed edit declarations, then any recurrence
note. Attribution lines lose the company name and the URL and keep the class and the date
(R1); review URLs become stable local ids `rev-01`…`rev-NN` so a score stays traceable to
a specific review without the string being searchable.

Close the packet with this line, exactly:

```
########## END OF PACKET ##########
```

**Then** the scrub log: counts per rule, every judgment call you made and why, and
anything you deliberately left alone.

### Three format details the tooling depends on — get these wrong and the packet is unreadable

The citation harness reads **only** the text between `########## SECTION 1` and
`########## END OF PACKET ##########`, both matched literally. Change either marker and
the packet does not parse at all.

- **The header block goes before the `SECTION 1` marker**, and must contain a literal
  `build vX.Y` — the parser reads the collector version from there and **refuses to guess**
  if it is missing. Carry the version from the raw packet; never invent one.
- **The scrub log goes after the `END OF PACKET` marker.** That is what keeps it out of
  the scored text. A log placed inside the packet becomes evidence the scorer reads.
- **Excerpt lines must begin with `•` or `·`**, and section markers must read
  `--- A. ` … `--- F. `. Both are matched by regex. A reformatted bullet is an excerpt
  that silently disappears from the packet.

---

## Self-check — run this before you declare finished

Report each line with a result. A self-check you do not report is a self-check you did not
run.

1. `http` appears zero times in the output.
2. The company's name — and its obvious short forms — appear zero times outside a
   bracketed substitution.
3. Every review is referenced as `rev-NN`, and the same review always gets the same id.
4. Every quote body is character-identical to the raw packet **except** where a bracketed
   declaration on that line says otherwise. Verify by diff, not by reading.
5. Every substitution you made is declared on its own excerpt line, not only in the log.
6. Excerpt count matches the raw packet, section by section.
7. Source typos are still present and still misspelled.
8. `Remote` is still literal wherever the raw packet had it.
9. Job titles and sector language are untouched.
10. The diff file exists and contains every changed line.
11. Both markers are present and literal, the header carries `build vX.Y`, and the scrub
    log sits after `########## END OF PACKET ##########`.
12. **Every excerpt bullet has a blank line directly above it** (Rule Three). Check this
    by looking at the line above each bullet, not by trusting that you did it — this is
    the check that catches a whole section going invisible.
13. **Report a per-section table: bullets counted, versus the count that section's header
    declares.** For example `A: 8 bullets / header says 8 — match`.

    Where they disagree, **do not fix either one.** A header that undercounts its own
    section is a content defect: record it in `P-0X_content_defects.txt` and reproduce the
    header verbatim. P-07's section E header declares two excerpts and the section holds
    four; that is a build defect to report, not a number to correct.

    A section showing **zero** bullets, or a whole-packet total in the single digits, is a
    different thing entirely — that is Rule Three failing, and it means the packet is
    effectively empty no matter how it reads. Fix it before you finish.

If any check fails, fix it and re-run the check. If a check cannot pass because the
ruleset conflicts with itself on this packet, stop and report — do not resolve a ruleset
conflict on your own initiative.

---

## Content defects — you are the second reader, so say what you see

You are the only person or process that reads a finished packet closely before a rater
does. Twice now that has caught real problems: a quote in P-06 that appears nowhere in the
section it cites, a review count stated as six where the correct count is eight, and an
attribution title contradicting the reviewer's own body text.

Those went unrecorded for weeks, because the build process produces *prompt*-defect files
and had nowhere to put *content* defects. That is what
`packets_out/P-0X_content_defects.txt` is for.

Record anything of this shape: a quote that cannot be found in the section it is attributed
to, a stated count that disagrees with the actual number of items, an attribution that
contradicts the excerpt, a date that cannot be right, an internal contradiction between two
company-authored excerpts.

**Do not fix them.** Record them, and scrub around them. A defect corrected during the
scrub is a defect that silently disappears from the build record, and the build is what
needs correcting.

Write the file even if it is empty — say "no content defects found." An absent file is
indistinguishable from a scrubber who did not look.
