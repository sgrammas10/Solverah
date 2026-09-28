# Path Intelligence — decisions waiting on Sebastian

After the first user test of the wants panel (2026-09-22). Write your answer under each one;
I'll read this file rather than the chat. Anything not listed here is already being fixed
or is Julie's wording.

## 1. "Stay in my field" stops staying in the field once answers are saved

**What happens:** without answers, Stay gives all-tech jobs. With your three answers, Stay
returns the same ten jobs as "Something adjacent", including Logistics Engineers, Sales
Engineers and Project Management Specialists. Reproduced on your account.

**Why:** the answers rotate the search for all three search types. For Stay the search *was*
your field, so rotating it leaves the field.

**Options:**
- (a) **Recommended.** For Stay, keep the pool anchored to your own job and let the answers
  only re-order within it. Adjacent and Fresh keep the rotation. Needs four more labelled
  Stay-with-answers profiles first (the harness has one; the rule is five), then the scorer
  change gated on them. Two agents, run in sequence.
- (b) Leave it and note it.

**Your answer:**
- (a) **Recommended.** For Stay, keep the pool anchored to your own job and let the answers
  only re-order within it. Adjacent and Fresh keep the rotation. Needs four more labelled
  Stay-with-answers profiles first (the harness has one; the rule is five), then the scorer
  change gated on them. Two agents, run in sequence.

_Overseer, after reading: my "one profile" was wrong — the harness already has five
Stay-with-answers profiles (p21–p25). No labeller needed; W-11 is one scorer agent gated on
those five. Dispatched 2026-09-22 with rulings 1–4; item 6 dispatched as W-12._

## 2. Taps on "Stay in my field"

**What happens:** on Stay, "Not for me" lights up, the card vanishes for a moment, then comes
back. That is the F-6 rule (Stay ignores taps because it answers a direct question), but on
screen it looks broken.

**Options:**
- (a) **Recommended.** Stay honours "Not for me" and "Too similar" as removals only — no
  re-ordering. "Interesting" is remembered but doesn't move anything.
- (b) Keep ignoring taps; don't show the three buttons on Stay.
- (c) Keep as is; add a one-line note under the list.

**Your answer:**
- (a) **Recommended.** Stay honours "Not for me" and "Too similar" as removals only — no
  re-ordering. "Interesting" is remembered but doesn't move anything.

## 3. The reason lines never mention the condition you marked

**What happens:** you marked "more time with people". No card said anything about people
time. Cards did say things you never asked about: "More of the day indoors", "Less freedom to
set your own priorities".

**Why:** by the W-4 rule, a line true of 7 or more of the 10 cards is dropped from all of
them — and for a Software Developer, "more time with people than your job" is true of nearly
every card. Unmarked conditions then fill the two slots.

**Options:**
- (a) **Recommended.** A condition you marked is exempt from that drop. The line will repeat
  across cards, but it answers your question.
- (b) Say the repeated fact once above the list ("Most of these involve more time with people
  than your job") and keep the cards for what's distinct. Nicer; adds a field to the API.
- (c) Leave it.

**Your answer:**
- (a) **Recommended.** A condition you marked is exempt from that drop. The line will repeat
  across cards, but it answers your question.

## 4. A line that goes against what you asked

**What happens:** you asked for *less* people time; two cards still said "More time with
people than your current job". That is deliberate — it's the honest fact about a card that
made the list anyway — but it reads as arguing.

**Options:**
- (a) **Recommended.** Keep it, worded to acknowledge the ask: "Still more time with people
  than your current job." (Best-guess copy; Julie revises.)
- (b) Drop the line when it goes against the ask.

**Your answer:**
- (a) **Recommended.** Keep it, worded to acknowledge the ask: "Still more time with people
  than your current job." (Best-guess copy; Julie revises.)


## 6. Two follow-ups outside the wants panel — do them now or after launch?

- After a tap, newly surfaced cards show a fallback sentence ("Uses your SQL.") and no
  pills, because a tap re-ranks without re-running the narrator. From F-6.
- In the card panel, "Worth picking up" largely repeats "Tools people use", and the tools
  list shows your own skills under long names ("Structured query language SQL"). From F-5.

**Your answer:**
do them now

## 7. New, from W-11: Sales Engineers still shows on your Stay page

Rulings 1–4 are built and reviewed (2026-09-22). With your three answers, Stay now drops
Logistics Engineers, Project Management Specialists and Security Management Specialists.
**Sales Engineers stays (7th)**, and Architectural & Engineering Managers arrives (10th).
Both are genuine neighbours of Software Developers by the same measure as every other
card — Sales Engineers is the 29th-closest of the 30 the pool holds — and your "more people
time" promotes them. The ruling as written can't remove them; only the pool can:

- (a) Leave it. A Stay user who asks for more people time gets the most people-facing job
  in their neighbourhood. Defensible.
- (b) Tighten Stay's pool: fewer neighbours (30 → ~20), or same SOC major group only
  (15-xxxx for a developer). A new measured ruling; the five Stay profiles can't see it
  (W-11 found their pools never reach that boundary), so it would be judged on your case
  and on reading the lists, not on the harness.

**Your answer:** Leave it for now (2026-09-28). Sebastian doesn't have the domain knowledge
to judge which neighbouring jobs belong under "Stay"; once this is on main, Julie tests it
and flags lists that look wrong. Options on file if she does: (a) smaller pool 30 → 20,
(b) same SOC family only (cuts promotion paths into 11-xxxx), (c) soft penalty for
off-family jobs — overseer's pick, (d) cap how far answers can lift a card on Stay.
Judge any change by reading lists for 4–5 job types, not the harness (W-11: the labelled
Stay profiles never reach the pool's edge).

---

## Already in hand — nothing to decide

- **All landed and reviewed 2026-09-22, ready to stage on your word:** W-10 (four screen
  fixes + one correction), W-11 (rulings 1–4), W-12 A + B (real narratives on cards that
  surface after a tap — the job narrates twenty in two parallel batches at no extra job time,
  ~$0.0007 per job; fit panel shows each tool once). Backend suite 3,806 / 0 failed, Vitest
  1,018 / 1,018, type-check clean — re-run by me. W-9 is your commit `ada024f`.
- **Fourth run (section O) was against the OLD API:** Flask started 13:30, W-13 was written
  14:10–14:43 — so O1, O2, O5 showed pre-W-13 behaviour and don't count. Rule from now on:
  I check the API process start time against the file times before handing over a test
  prompt. Re-run O after W-14 lands and a restart.
- **W-14 landed and reviewed** (found by me on the real stack, not by the tester): (1) Start
  over returned the cards you'd removed as fallback sentences with no pills; (2) a tap or
  Start over on a cold cache (right after an API restart) cached a page of ten fallbacks and
  the next job served it as if narrated. Both fixed and re-proven on the real stack; full
  suite 3,855 / 0. **Staging list:** `solverah/services/intelligence_service.py`,
  `solverah/services/path_cache.py`, `tests/test_path_feedback_api.py`,
  `tests/test_path_suggestions_api.py`; docs: `BUILD_PLAN.md`, `PATH_WANTS_DECISIONS.md`.
  Then restart Flask and run section O.
- **Third-run user tests** are section N of `docs/PATH_WANTS_USER_TESTS.md` (27 checks).
- **Third run done (60 → 25/27):** its two failures + three notes became **W-13, landed and
  reviewed 2026-09-22** — the narrator no longer sees a score and its output is scrubbed
  for grade words; the "Start over" bar survives a reload (the cached payload had been
  stored without the feedback map); one option selected at a time; "HTML" not "Hypertext
  markup language HTML"; subtitle says "matched to". Backend 3,848 / 0, Vitest 1,023,
  type-check clean. **Fourth-run tests = section O (7 checks).** W-13 staging list:
  `path_narrative.py`, `path_deep_fit.py`, `intelligence_service.py`,
  `PathIntelligencePage.tsx` + test, `PathPreferencesForm.tsx` + test,
  `test_path_narrative.py`, `test_path_deep_fit.py`, `test_path_suggestions_api.py`,
  `test_path_feedback_api.py`; docs: `BUILD_PLAN.md`, `PATH_WANTS_USER_TESTS.md`,
  `PATH_WANTS_DECISIONS.md`.
- **Staging list** (one commit or three, your call):
  - W-10: `PathWantsPanel.tsx` + test, `usePathWants.ts`, `PathSuggestionCard.tsx` + test,
    `PathPreferencesForm.tsx` + new test
  - W-11: `backend/services/path_scoring.py`, `tests/test_path_scoring.py`,
    `tests/test_path_eval.py`, `tests/fixtures/path_eval/runs/w11_stay_anchored.json`
    (path_scoring.py and test_path_scoring.py also carry W-12's `reserve` lines — they
    can't be split, so W-11 and W-12 go together or in that order)
  - W-12: `path_deep_fit.py`, `path_narrative.py`, `intelligence_service.py`,
    `path_cache.py`, `test_path_deep_fit.py`, `test_path_fit_api.py`, `test_path_narrative.py`,
    `test_path_suggestions_api.py`, `test_path_feedback_api.py`
  - Docs: `BUILD_PLAN.md` (W-10/11/12 notes), `PATH_WANTS_USER_TESTS.md`,
    `PATH_WANTS_DECISIONS.md`

- **W-9** (running): card open makes no O*NET call; top three cards pre-warmed; card-open
  rate limit 10 → 30/min.
- **W-10** (running): "Re-sorting…" flashing then pills clickable; "1 thing you want to
  change" showing before a save; tooltip covering the tap buttons; "Adjust search
  preferences" starting blank.
- **Wording for Julie:** subtitle says "scored" (page shows no score); "Start over" only
  forgets taps (suggest "Forget my taps"); some reason lines read oddly ("More of the day
  indoors" for a developer).
- **Not defects:** the lab page showing 17 raw task statements and running the old scorer
  (needed a restart); the 27 s clear on Fresh direction (first Fresh run in a process pays a
  ~10 s cluster fit on your Python 3.10); cards opening in 15 ms with no spinner (you had
  already opened them — W-9 covers the cold case).
- **My test doc was wrong on two rows** (F3, E5) — corrected in
  `docs/PATH_WANTS_USER_TESTS.md`.
