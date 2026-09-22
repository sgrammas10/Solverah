# Path Intelligence — user tests for the local site

What a user should see. Nothing here is about the code; each test is a thing to do
and what should happen on screen. Tick the box if it did. Write what you saw instead
if it didn't — the exact words on screen, and how long it took if that was the problem.

## Before you start

Three things running, in this order:

1. The API, on the local W database (never the one in `.env`):
   ```powershell
   $env:DATABASE_URL="postgresql://solverah:solverah@localhost:5433/solverah_w7"
   $env:SOLVERAH_CORPUS_PATH="C:\Users\Sebastian Grammas\Desktop\solverah-corpus"
   flask run --host ::1
   ```
   `--host ::1` is what removes the two-second pause on every request. Port stays 5000.
2. The frontend: `npm run dev`, then open http://localhost:5173.
3. Sign in as `e2e-wants-1790021094021@example.com` / `E2e-Passw0rd!1790021094021`
   (a Software Developer with five skills and a current job).

Go to **Path Intelligence → Your Career Paths** (`/intelligence/paths`).

Timings below are what to expect with the API started as above. "First time" means the
first time anyone has done it since the API started.

---

## A. The page without touching the panel

| # | Do | Expect | ✓ |
|---|----|--------|---|
| A1 | Open the page fresh (no preferences saved yet) | Three questions, one at a time: *Stay in my field / Something adjacent / Fresh direction*, then *Looking to move up / Similar level / Open to either*, then the priority. Last button says **See my paths →** | ☐ |
| A2 | Answer *Something adjacent*, *Similar level*, *Learning & growth* | Grey placeholder cards, then a list of up to 10 jobs within about 10–20 s. Each card: job title, a line "Software Developer → *title*", a sentence on why, and up to a few small pills | ☐ |
| A3 | Look at the whole page | **No percentage anywhere.** No score, no bar, no "strong / good / weak" grade on any card | ☐ |
| A4 | Look above the list | One collapsed row: "Tell us what should change about your job, and we'll re-sort these" with **Open** on the right. It is closed. It has not stopped the list from appearing | ☐ |
| A5 | Look at the cards | No card carries a small grey reason line under its why-sentence (those only appear after you've said what should change) | ☐ |
| A6 | Under every card | Three round buttons: **Interesting / Too similar to my job / Not for me**, none lit. A greyed **Set as target role** button; hovering it says "Coming soon" | ☐ |

## B. Opening the panel

| # | Do | Expect | ✓ |
|---|----|--------|---|
| B1 | Click the "Tell us what should change…" row | It opens in place. Right-hand label changes to **Hide**. The list below does not move or reload | ☐ |
| B2 | Read the heading | "About your work: **Software Developers**" — the plural O*NET name, your own job | ☐ |
| B3 | Read the first group, "What you spend your time on" | Between 1 and 8 short task descriptions written in plain words, each with three pills: **Less of this / Fine as it is / More of this**. **Fine as it is** is lit on every row | ☐ |
| B4 | Read the second group, "How you work" | Exactly four rows, in this order: *Time working with other people* · *Dealing with customers or the public* · *Leading or directing other people* · *At a desk, rather than on your feet*. Fine on all four | ☐ |
| B5 | Look at the bottom of the panel | **Update my suggestions** is greyed out (nothing changed yet). No "Clear my answers" link | ☐ |
| B6 | Click **Hide**, then **Open** again | Closes and reopens. Nothing else on the page changes | ☐ |

## C. Answering without saving

| # | Do | Expect | ✓ |
|---|----|--------|---|
| C1 | On one task row click **Less of this** | That pill lights green; *Fine* on that row goes dark. Only that row changes | ☐ |
| C2 | On another task row click **More of this** | Same. **Update my suggestions** is now enabled | ☐ |
| C3 | On *Time working with other people* click **More of this** | Same | ☐ |
| C4 | Look at the list of jobs | **Unchanged.** Nothing re-sorts until you press the button | ☐ |
| C5 | Reload the page (F5), open the panel | All three answers are **gone** — back to Fine everywhere. Nothing was saved | ☐ |
| C6 | Set the same three answers again, then click **Fine as it is** on all three | Button goes back to greyed out — you're back where you started, so there's nothing to save | ☐ |

## D. Saving

Set: LESS on **the row about fixing / correcting software problems**, MORE on **the row about
finding out what users need**, MORE on *Time working with other people*.

| # | Do | Expect | ✓ |
|---|----|--------|---|
| D1 | Click **Update my suggestions** | Button reads **Re-sorting your paths…** and every pill in the panel greys out. The list is replaced by placeholder cards. The panel stays on screen the whole time (it does not vanish behind the placeholders) | ☐ |
| D2 | Wait | New list within about 10–20 s. Button reads **Update my suggestions** again and is greyed out (nothing new to save). **Clear my answers** link now shows beside it | ☐ |
| D3 | Close the panel | Collapsed row now says **3 things you want to change** under the title | ☐ |
| D4 | Compare the new list with the one from A2 | The **order has changed.** The job most about fixing software (Computer Programmers) is **no longer first**; jobs about working out what people need and working with people are nearer the top (e.g. Computer Systems Analysts) | ☐ |
| D5 | Look at the cards | Some (not necessarily all) now carry one or two short grey lines under the why-sentence, saying what is different about *that* job on the conditions you marked — e.g. "More time with people than your current job" or "Among the most people-facing jobs". Words only, no numbers, no percentages. (Task answers change the order but don't write a line — only the four "How you work" rows do) | ☐ |
| D6 | Read those lines | They're about the **job**, never a grade on you. If a line looks wrong for that job, note it here | ☐ |
| D7 | Open the panel | The three answers are still lit exactly as you set them | ☐ |

## E. Changing an answer after saving

| # | Do | Expect | ✓ |
|---|----|--------|---|
| E1 | Flip *Time working with other people* to **Less of this**, click Update | Re-sorts again. The people-facing jobs that rose in D4 should **fall** back, and reason lines change with them | ☐ |
| E2 | Set every row back to **Fine**, click Update | Re-sorts. List looks like A2 again (same order, allowing one adjacent swap). No reason lines on any card. Collapsed row no longer shows "things you want to change" | ☐ |
| E3 | Set only **More of this** on *Leading or directing other people*, click Update | Managerial / lead jobs move up; a line like "More leading other people" or "A lot of leading other people" appears on some | ☐ |
| E4 | Set only *At a desk* to **Less of this**, click Update | Jobs that are more on-your-feet move up; lines like "More on your feet, less desk time" | ☐ |
| E5 | Any of E1–E4 | If you asked for *less* people time, no card says "Among the most people-facing jobs". A card may still say "More time with people than your current job" — that's the honest fact about that card, not a recommendation (ruling pending on wording it "Still more…") | ☐ |

Restore D's three answers before section F.

## F. Taps (Interesting / Too similar / Not for me) with answers saved

| # | Do | Expect | ✓ |
|---|----|--------|---|
| F1 | On the first card click **Interesting** | Button lights at once. Card **stays**. A moment later the list re-sorts with jobs like it nearer the top. A bar appears under the list: "These paths are shaped by what you've told us" with **Start over** | ☐ |
| F2 | On another card click **Not for me** | Card **disappears immediately**; the list fills back to 10 a moment later, with jobs like the removed one pushed down or gone | ☐ |
| F3 | On a card very close to your own job click **Too similar to my job** | Card disappears, and so does any card *even closer* to your own job than it. Cards further away than the tapped one stay (Software Developer → tapping Computer Programmers does not remove QA Analysts) | ☐ |
| F4 | While a tap is in flight | All the tap buttons on every card grey out together, then come back | ☐ |
| F5 | Open the panel after the taps | Still **3 things you want to change**, the three answers still lit. Taps did not clear them | ☐ |
| F6 | Click **Start over** | The taps are forgotten: the removed cards can come back, "Interesting" is unlit, the bar disappears. Your **panel answers are kept** — the list is still shaped by them (reason lines still present) | ☐ |

## G. Opening a card

| # | Do | Expect | ✓ |
|---|----|--------|---|
| G1 | Click the body of a card (title or text — not the round buttons) | A panel slides over the page at once: "How this fits you" + the job title, a spinner "Working out how this fits you…" | ☐ |
| G2 | Time it, first open of that job since the API started | Content within about **1–3 s** (this is the one W-9 is fixing) | ☐ |
| G3 | Close it and open the same card again | Content **well under a second** | ☐ |
| G4 | Read it | Sections, in this order and only when they have something: **Training** (one sentence: needs more / less / about the same training as your current level), **Skills you already have** (pills — should include your real skills like Python, SQL), **Worth picking up**, **What you'd be doing** (bullets), **Tools people use** (pills). **No number, bar or percentage anywhere** | ☐ |
| G5 | "Worth picking up" | Should not list something you already have under a longer name (e.g. "Structured query language SQL" when you have SQL) | ☐ |
| G6 | Press **Esc** | Panel closes | ☐ |
| G7 | Open again, click the dark area outside the panel | Panel closes | ☐ |
| G8 | Open again, click **✕** | Panel closes | ☐ |
| G9 | With the panel open, the whole page | Still no `%` anywhere | ☐ |

## H. Reload, persistence, clear

| # | Do | Expect | ✓ |
|---|----|--------|---|
| H1 | Reload the page | List comes back (may take the same 10–20 s). Collapsed row says **3 things you want to change**. Reason lines are there | ☐ |
| H2 | Open the panel | The three answers are lit exactly as saved | ☐ |
| H3 | Sign out, sign back in, come back to the page | Same as H1/H2 | ☐ |
| H4 | Click **Clear my answers** | Goes through the same "Re-sorting your paths…" as a save. Afterwards: every row back to Fine, no "things you want to change", no reason lines, **Clear my answers** link gone, Update greyed out | ☐ |
| H5 | Reload after clearing | Still clear | ☐ |

## I. Search types (Adjust search preferences → the first question)

Set the D answers again first, so each search type is seen with the same wants.

| # | Do | Expect | ✓ |
|---|----|--------|---|
| I1 | **Stay in my field** | Jobs from the same software/tech family. The panel still shows and its answers still re-order this list. Taps: *Interesting / Not for me* have little or no visible effect here (that's by design for this search type) | ☐ |
| I2 | **Something adjacent** | Mostly tech-adjacent, with a few from nearby fields (analyst, product, sales engineering). Wants and taps both visibly move the list | ☐ |
| I3 | **Fresh direction** | Broader and more varied — jobs from several different fields, not ten variations on one. With your three answers saved, the variety narrows toward what you asked for; with the panel cleared it widens again | ☐ |
| I4 | Any type | The panel's answers survive switching search type — open it after each and check the count | ☐ |

## J. Keyboard and narrow screen

| # | Do | Expect | ✓ |
|---|----|--------|---|
| J1 | Tab through the open panel | Each task row is one stop; **← →** arrow keys move between Less / Fine / More on that row; the lit pill shows a focus ring | ☐ |
| J2 | Tab through a card | Stops: the card body (Enter opens the fit panel), the three verdict buttons. Nothing is reachable twice | ☐ |
| J3 | Make the window phone-width (~400 px) | Panel pills wrap onto a second line under their label, nothing runs off the side, no horizontal scrollbar. Cards' three verdict buttons wrap too | ☐ |
| J4 | Phone-width, open a card | Fit panel fits the width, scrolls inside itself | ☐ |

## K. Things that should not happen

| # | Check | ✓ |
|---|-------|---|
| K1 | Nothing on the page ever says a percentage, a score out of anything, or a grade like "Strong fit" | ☐ |
| K2 | The panel never blocks the list: even if it fails to load, the jobs still appear | ☐ |
| K3 | An answer is never saved by clicking a pill alone — only by the Update button | ☐ |
| K4 | Pressing Update with nothing changed is impossible (button greyed) | ☐ |
| K5 | No red error box appears anywhere during A–J. If one does, copy its exact words | ☐ |
| K6 | Browser console (F12) has no red errors after the run | ☐ |

---

## M. Second run — card open speed (W-9, landed 2026-09-22)

Restart Flask first (the sidecar is read when the API starts serving). Sign in as the same
account. Use "Adjust search preferences" → *Fresh direction* to get a list of jobs nobody has
opened before, then:

| # | Do | Expect | ✓ |
|---|----|--------|---|
| M1 | Let the list land. Wait 3 s. Click the **first** card | The panel opens **already filled** — no spinner at all | ☐ |
| M2 | Close it, click the **second** and **third** cards | Same: no spinner | ☐ |
| M3 | Click **Show more**, wait 3 s, click the **fourth** card | No spinner (the next three are warmed when they appear) | ☐ |
| M4 | Click **Show more** again *immediately* and click the **seventh** card within a second | A spinner is allowed here; content within about **1 s** (was 1–3 s before W-9) | ☐ |
| M5 | Close and reopen any card you've opened | Instant, no spinner | ☐ |
| M6 | Open eleven different cards inside one minute (use *Something adjacent* and *Stay in my field* lists too) | No error box. Before W-9 the eleventh would have failed with a rate-limit message | ☐ |
| M7 | Reload the page, open the first card at once | Filled or a spinner well under 1 s — either is a pass | ☐ |
| M8 | Everything in section G still holds (sections, no numbers, Esc / outside-click / ✕ close) | ☐ |

## N. Third run — W-10, W-11, W-12 (landed 2026-09-22)

Restart Flask first. Sign in as the same account. Start from *Something adjacent* with the
panel cleared and no taps (press "Start over" and "Clear my answers" if they show).

**N-A. The panel (W-10)**

| # | Do | Expect | ✓ |
|---|----|--------|---|
| NA1 | Open the panel, click one pill, close the panel | The collapsed row shows **no** "1 thing you want to change" line (nothing is saved yet) | ☐ |
| NA2 | Open it, click **Clear my answers** | Pill goes back to Fine at once, **no** re-sort happens, list untouched | ☐ |
| NA3 | Set D's three answers, click **Update my suggestions**, watch the button and the pills for the whole re-sort | Button reads **Re-sorting your paths…** and every pill stays greyed **until the new cards appear** (10–20 s). It must not flip back early | ☐ |
| NA4 | Same as NA3 but on *Fresh direction* (slower, up to ~30 s) | Same: busy label and greyed pills for the whole wait | ☐ |
| NA5 | After the save, close the panel | Row says **3 things you want to change** | ☐ |
| NA6 | Hover **Set as target role** on any card | The "Coming soon" tooltip appears **below** the button and covers none of the three verdict buttons | ☐ |
| NA7 | Click **Adjust search preferences** | Each of the three questions opens with your **current choice already highlighted**; you can still change it; Next/See my paths works | ☐ |

**N-B. Stay in my field (W-11)** — keep D's three answers saved

| # | Do | Expect | ✓ |
|---|----|--------|---|
| NB1 | Search type **Stay in my field** | **No** Logistics Engineers, Project Management Specialists or Security Management Specialists. Mostly software / IT; Sales Engineers and Architectural & Engineering Managers may still appear — they are neighbours of your job by the same measure as the rest, and whether to tighten that is decision item 7, not a failure | ☐ |
| NB2 | Compare with **Something adjacent** (same answers) | The two lists differ | ☐ |
| NB3 | On Stay, click **Not for me** on any card | The card disappears **and stays gone**; the rest of the list keeps its order, one new card fills in at the bottom | ☐ |
| NB4 | On Stay, click **Too similar to my job** on the card closest to your job (Computer Programmers) | It disappears, and so does anything even closer to your job; nothing else re-orders | ☐ |
| NB5 | On Stay, click **Interesting** on a card | Button lights; the card stays; **the order does not change** | ☐ |
| NB6 | Clear the panel (all Fine) and look at Stay again | Same all-tech list as before any answers | ☐ |

**N-C. Reason lines (W-11)** — set D's three answers again, *Something adjacent*

| # | Do | Expect | ✓ |
|---|----|--------|---|
| NC1 | Read the lines under the cards | Most cards now carry a line about **people time** — "More time with people than your current job" or "Among the most people-facing jobs" — even though it repeats across cards. It is the axis you marked | ☐ |
| NC2 | Same page | Lines about things you didn't mark (indoors, freedom to set priorities) appear **less** than before and never on 7+ cards | ☐ |
| NC3 | Flip people time to **Less of this**, Update | A card that still has more people time than your job says **"Still more time with people than your current job"** — with "Still" — never the bare "More time with people…" | ☐ |
| NC4 | Any page | Never more than two lines per card; no numbers or percentages | ☐ |

**N-D. Cards after a tap (W-12)** — *Something adjacent*, answers saved

| # | Do | Expect | ✓ |
|---|----|--------|---|
| ND1 | Note the list. Click **Not for me** on two cards, one after the other (wait for each to settle) | The cards that come in to replace them have a **real why-sentence** (a full sentence about you and the job) and **pills**, like the rest — not "Uses your SQL." and not "A different direction. Open it to see…" | ☐ |
| ND2 | Tap **Not for me** three more times | Still real sentences on newcomers for the first ~10 new cards; after that a fallback sentence is allowed (the reserve is ten deep) | ☐ |
| ND3 | Reload | The list comes back; tap once more — newcomers still have real sentences (the reserve survives a reload until the list is re-scored) | ☐ |
| ND4 | Time a tap | The list settles in well under a second after the click | ☐ |

**N-E. The fit panel (W-12)**

| # | Do | Expect | ✓ |
|---|----|--------|---|
| NE1 | Open **Computer Programmers** (or any software job) | "Skills you already have" shows your skills **under your names** (SQL, Amazon Web Services, Python) | ☐ |
| NE2 | Same panel | "Tools people use" does **not** repeat anything from "Skills you already have" or "Worth picking up". No "Structured query language SQL", no "Amazon Web Services AWS software" | ☐ |
| NE3 | Same panel | "Worth picking up" and "Tools people use" have **no item in common** | ☐ |
| NE4 | Open two other jobs | Same three checks. A job with nothing new in Tools may show no "Tools people use" section at all — that's a pass | ☐ |
| NE5 | All panels | Still no number, bar or percentage | ☐ |

## O. Fourth run — W-13 (landed 2026-09-22)

Restart Flask first. Same account, *Something adjacent*, D's three answers saved.

| # | Do | Expect | ✓ |
|---|----|--------|---|
| O1 | Read every why-sentence and every pill on the page, then tap Not-for-me three times and read the newcomers too | **No** sentence or pill rates the fit: nothing like "strong fit", "great match", "ideal", "highly suitable", "top choice", a score or a `%`. Sentences describe the work and which of your skills it uses. ("Matches your … archetype" as a pill is fine) | ☐ |
| O2 | Tap **Not for me** on two cards, then **reload** | The removed cards stay removed **and** the bar "These paths are shaped by what you've told us / Start over" is there | ☐ |
| O3 | Press **Start over** after the reload | The removed cards can come back; the bar disappears | ☐ |
| O4 | Adjust search preferences: pick a different option on question 1, then move the mouse across the others on the way to Next | Exactly **one** option looks selected. Hovering another does not tint it green | ☐ |
| O5 | Open Computer Programmers' fit panel, read "Worth picking up" and "Tools people use" | Acronyms shown as acronyms: **HTML**, **CSS**, **XML**, not "Hypertext markup language HTML". Names like "Oracle Java", "Node.js", "Microsoft Azure software" unchanged | ☐ |
| O6 | Page subtitle | "Career paths **matched to** your skills and work profile…" — not "scored against" | ☐ |
| O7 | Everything in N-D still holds (newcomers after a tap have real sentences and pills) | ☐ |

## L. The lab page (127.0.0.1:5077) — optional

Start from the repo root with the pinned venv:
```powershell
& "C:\Users\Sebastian Grammas\Desktop\solverah-venv311\Scripts\python.exe" "C:\Users\Sebastian Grammas\Desktop\solverah-experience-proto\lab\lab.py"
```
Restart it if it was already running: it loads the scorer once at start, and the ranking fix landed after your last session.

| # | Do | Expect | ✓ |
|---|----|--------|---|
| L1 | Title "Software Developer", path *adjacent*, skills `Python:advanced`, `SQL:advanced`, `JavaScript:intermediate`. Click **Load this job's O*NET tasks** | The same task rows as the site's panel, each with less / fine / more | ☐ |
| L2 | Click **Run** with everything on fine | Three columns: *Backend today*, *Backend with wants*, *Scratch formula*. The two backend columns show the **same order** | ☐ |
| L3 | Set the same three answers as section D, **Run** | *Backend with wants* re-orders; badges say **up N / down N / new / same** against *Backend today*. Computer Programmers shows a **down** badge and is not first. This column should match the site's order after D2 (allowing one adjacent swap) | ☐ |
| L4 | "Why not …?" — type `programmer`, **Look up** | Shows where Computer Programmers ranks before and after the wants, and the numbers that moved it | ☐ |
| L5 | Tap **interesting** on a card in a backend column | The column re-runs; badges now show what the tap moved; a taps bar lists your taps with an **x** to undo and **clear all taps** | ☐ |
| L6 | Tap **not for me** / **too similar** on a card | Card is hidden; "Dropped out" line names it and says "(you tapped it)" | ☐ |
| L7 | Move the three sliders | Only the *Scratch formula* column changes; the two backend columns do not | ☐ |
