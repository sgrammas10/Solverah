# Anonymization pass — state as of 2026-08-15

## Done — the pass is COMPLETE. All six packets scrubbed.

| Packet | File | Notes |
|---|---|---|
| P-01 Oscar Health | `P-01_packet_ANON.txt` | First pass; the ruleset was derived from it. Renamed from `P-01_packet_RATER_DRAFT.txt` on 2026-08-15. |
| P-02 Best Buy | `P-02_packet_ANON.txt` | |
| P-03 Akuna | `P-03_packet_ANON.txt` | Sections D and E genuinely empty |
| P-04 R/GA | `P-04_packet_ANON.txt` | Heaviest scrub of the six |
| P-05 Doist | `P-05_packet_ANON.txt` | Anonymization weakest here — see below |
| P-06 Raymond James | `P-06_packet_ANON.txt` | Scrubbed 2026-08-15. 46 excerpts (A8/B15/C10/D4/E3/F6), 30 verbatim-matched against source, 16 carrying a bracketed substitution with every unbracketed fragment verified against source. Three ruleset deviations and three source-packet defects logged in the file. |

## P-06 — what it forced, and what needs your sign-off

Three things came up that the ruleset does not settle. All are recorded in P-06's scrub log;
they are listed here because they are ruleset decisions, not packet decisions.

**1. R6 was extended to Section D.** The rule as written covers Sections E and F. The first D
excerpt carried an advisor headcount inside a quote — a one-query identification inside this
company's peer set, carrying no dimension signal, in a sentence whose actual claim survives the
strip intact. P-02 already applied magnitude language inside an E quote body, so the mechanism is
not new; only the section is. **Recommend R6 be rewritten for v4.7 as "strip identifying figures
wherever they appear, in any section."**

**2. JC-1 and R4 collide, for the first time.** A named five-behaviour list sits inside a sentence
whose remainder is a values statement. JC-1 protects distinctive verbatim self-description; R4
says rewrite the branded proper noun and keep the clause. Both apply to one sentence. The split
taken: generalise the five behaviour names (near-pure fingerprint), keep the values clause
(independence → autonomy, "conservative, long-term" → pace and innovation). **Needs a general
rule, because this will recur on any company with named internal behaviours.**

**3. R8 was applied as a visible note rather than as a deletion.** R8 says a claim appearing in
both A and F is quoted once with the recurrence noted. P-06 has exactly that case — a named
culture document referenced in the careers copy and again in the 10-K. Applying R8 literally would
have dropped an excerpt and made P-06 inconsistent with the five packets scrubbed before R8
existed. Instead both excerpts stay and the F excerpt carries a rater-facing recurrence note that
tells the rater not to read it as corroboration. **Decide which form the v4.7 rebuild uses.**

## Quote-fidelity audit across all six — run 2026-08-15

Every quoted excerpt in every anon file was string-matched against its source packet. This is the
check the citation-verification harness will run, executed by hand ahead of it.

| | excerpts | verbatim match | carry a bracketed substitution | unexplained mismatch |
|---|---|---|---|---|
| P-01 | 33 | 22 | 10 | 1 |
| P-02 | 48 | 24 | 21 | 3 → 1 after dash normalisation |
| P-03 | 37 | 23 | 14 | 0 |
| P-04 | 31 | 19 | 12 | 0 |
| P-05 | 10 | 6 | 3 | 1 → 0 after dash normalisation |
| P-06 | 46 | 30 | 16 | 0 |

**Finding 1 — P-02 and P-05's source packets contain ZERO em dashes; their anon files are full of
them.** Those two anon files were retyped rather than edited from source, and the retype silently
normalised ASCII hyphens to em dashes inside quote bodies. No meaning changed, but a wholesale
retype is exactly the uncontrolled edit to the instrument the ruleset warns about, and it is only
visible because the audit was run. **Harness consequence: the normalisation step must strip dashes
and smart quotes as well as whitespace, or three P-02/P-05 quotes fail verification for punctuation.**

**Finding 2 — two genuine undeclared quote-body edits, both benign, neither bracketed.**

* P-01: `Executive Speaker series` → `executive speaker series`. A correct R4 application — the
  ruleset uses this exact string as its worked example — but applied silently, with no bracket and
  no note on the line. A rater citing that sentence produces text that does not match the source.
* P-02: `Ethan said` → `the same intern said`. A correct R3 application and it IS declared in
  P-02's scrub log, but not marked on the excerpt line itself.

Neither is an anonymization failure. Both say the same thing: **an edit recorded only in a scrub
log is not visible where it matters.** Same shape as "a rule that lives only in a handoff is not a
rule." Every substitution belongs in brackets on the line, which is what P-06 does.

## Source-packet defects found during the scrub — not anonymization issues

* Section 4's pre-flag block quotes an A excerpt that does not exist in Section 1 ("Raymond James
  is where good people grow"). The company-name occurrence it pointed at is real; the quoted text
  was written from memory.
* Section 4 says six reviews carry no location. The correct count is eight.
* rev-10's attribution title contradicts the role the reviewer names in their own body text. Left
  verbatim per the v4.6 rule.

## Three things that need your decision

**1. P-05 cannot be blinded — but it STAYS. (Reversed 2026-08-14.)**
Fully remote with no location restrictions, bootstrapped, async-first, uses its own product
internally, publishes an engineering blog, zero open roles, zero reviews on the main aggregator. The
operating model *is* the fingerprint and no scrubbing touches it.

My first call was to drop it from the set. That was wrong, and it conflated two claims: *cannot be
anonymized* does not imply *should be removed*. Anonymization is a test instrument; citation
verification is the control that survives into production, and the rater page enforces it. P-05
unblinded is a valid packet with recognition recorded as yes.

Two positive reasons to keep it:
* It is the only stage 1–2 company in the set, and Akuna the only stage 3. Without it the calibration
  set spans stage 3–5 with a single point at 3 — and `stage_size` is the largest confounder, the
  common cause of all six dimensions. A set with almost no variation in the biggest confounder cannot
  calibrate the scale it exists to calibrate. The roster notes already flagged this skew and called
  for small companies deliberately.
* It is the packet that breaks the proposed 0.7 rule, which is worth knowing now. **Open question: is
  an engineering blog post written by an employee but published on a company-run site
  "company-authored"?** If yes, no dimension in P-05 can exceed 0.7 and the packet caps out. If no,
  any company can evade the rule by publishing employee bylines. Answer before the raters start.

The thin evidence handles itself: P-05 should produce low-confidence scores, which is confidence
tracking evidence availability — calibration working, not bias.

**2. JC-2 — Section E — is now decidable, and P-04 is the packet to decide it on.** Fully scrubbed,
P-04's Section E still reads: an agency sold by its long-time holding-company parent to private equity
in a management buyout in early 2025, which then acquired an AI design studio. Anyone who reads the
ad trade press places that instantly, and the events carry almost no dimension signal. Against
dropping it: the ownership change is the single most important fact for reading Section B, because
every review predates it.

**3. New rule needed in v4.7 — named clients.** P-04 quotes a review naming a major client. No
previous packet had one and the collector prompt has no rule for it. I substituted a generic
descriptor. Needs to be written down before the rebuild.

## Deviations from the ruleset, flagged rather than hidden

* **P-05 R6:** two equipment-allowance dollar figures retained. Not identifying alone, and the only
  pay-posture signal in the packet.
* **P-05 tooling:** third-party developer tool names generalised, where P-03 retained them as
  non-identifying. In P-05 the combination of framework names, platform and blog voice narrows it
  much further. The inconsistency is real — pick one rule for v4.7.
* **P-02:** "enrich lives through technology" retained under JC-1, but it is the strongest candidate
  for a single JC-1 exception across all six: a trademarked purpose statement, not a description of
  how people work, so removing it costs almost no dimension signal.

## Then

1. ~~Scrub P-06.~~ DONE 2026-08-15.
2. Adversarial re-identification check on all six (task #6) — search every retained distinctive
   phrase and preserved typo, confirm quotes still string-match for the citation harness.
3. Generate rater pages: `python build_rater_page.py --packet <anon file> --packet-id P-0X --rater A|B --out ./out`
4. Rater instructions and the counterbalanced schedule (task #4).
5. All of the above is against one-method v4.6 builds. The v4.7 rebuild replaces the packet text;
   the rater pages regenerate unchanged.
