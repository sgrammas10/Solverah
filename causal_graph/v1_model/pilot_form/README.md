# Pilot form: from Google Form to training rows

Before launch, the match model gets its first real outcome rows from a Google Form you send
to your network (pre-registration Amendment 2,
`Solverah_IP/PREREGISTRATION_2026-10-01_FIRST_OUTCOME_FIT.md`). The form is generated from
the app's own questions, and the answers are loaded into a **local** research database
through the app's own code, so they become training rows exactly like app rows, labelled
`respondent_source = 'pilot_form'`.

Nothing here talks to Google. You paste a script into Google yourself, and you download the
answers yourself.

Commands below are for Git Bash, run from the repo root.

---

## 1. Make sure the form script is current

The form script (`build_form.gs`) and its answer key (`form_mapping.json`) are committed.
They only need regenerating if someone changed the questions in the app:

```sh
python -m causal_graph.v1_model.pilot_form.generate_form_script --check
```

If it says `STALE`, regenerate (and then build a new form, step 2):

```sh
python -m causal_graph.v1_model.pilot_form.generate_form_script
```

**Don't edit question wording in the Google Forms editor.** The import matches answers to
questions by their exact wording, and refuses a CSV whose questions don't match. If Julie
changes copy, change it in the app's question bank (or `spec.py` for the form-only framing),
regenerate, and build a fresh form.

## 2. Create the form (once)

1. Go to <https://script.google.com> and click **New project**.
2. Delete the placeholder code, open `causal_graph/v1_model/pilot_form/build_form.gs`, copy
   all of it, and paste it in.
3. Click **Save**, make sure `buildPilotForm` is selected next to **Run**, and click **Run**.
4. Google asks for permission to manage your forms. Allow it.
5. Open **Execution log**. It shows two links: the **Edit link** (keep it to yourself) and
   the **Share link** (what you send people).

Each run creates a brand-new form, so run it once.

## 3. Check the settings in the form editor

Open the Edit link and check:

- **Settings > Responses > Collect email addresses: "Do not collect".** The only email is
  the optional question on the last page. (The script sets this; confirm it.)
- **Settings > Responses > Allow response editing: off.**
- **Settings > Responses > Limit to 1 response: leave off.** Turning it on forces people to
  sign in to Google, which breaks the "anonymous" promise in the intro. Duplicate rows are
  caught on import anyway.
- **Settings > Presentation > Shuffle question order: off.** The question order is the
  app's own order and must not be shuffled.
- **Each question's three-dot menu > Shuffle option order: unticked.** It is off by default;
  spot-check a few. Option order matters (some questions deliberately list the
  options high-to-low and some low-to-high).
- **Preview** the form (eye icon) and try each answer to "Where are you in your career?":
  *Currently employed* goes to "Your job", *Between jobs* goes to "The job you most recently
  left", *Looking for my first job* goes straight to the last page. After a job section,
  "Describe a previous job too?" goes to "The job before that" or to the end.

Don't submit test answers into the real form. If you do, note the row's pilot id after
importing and add `pilot-<id>@pilotform.solverah.invalid` to the pre-registration's
Appendix A before Look 1.

## 4. Send it

**Send > link icon > Copy**, and send the Share link to people.

## 5. Download the answers

In the form editor: **Responses > three-dot menu > Download responses (.csv)**. It
downloads a zip; unzip it. (Or link a Sheet and use **File > Download > CSV**; same
columns.)

Save the CSV **outside the repo**, for example in `Desktop/solverah-pilot/`. It contains
respondents' emails.

## 6. Create the local research database (once)

The database is `solverah_pilot` on the local Postgres at port 5433. The import refuses
any database whose name does not start with `solverah_pilot`, any host other than
`localhost`/`127.0.0.1`, and `APP_ENV=production`. There is no override.

```sh
export PATH="/c/Program Files/PostgreSQL/18/bin:$PATH"; export PGPASSWORD=solverah
psql -h localhost -p 5433 -U solverah -d postgres -c "CREATE DATABASE solverah_pilot OWNER solverah"
for ext in citext pg_trgm vector; do
  psql -h localhost -p 5433 -U solverah -d solverah_pilot -c "CREATE EXTENSION IF NOT EXISTS $ext"
done
```

Then build its tables. `FLASK_SKIP_DOTENV=1` matters: the Flask command loads `.env` by
itself otherwise, and `.env` holds the **production** database address.

```sh
FLASK_SKIP_DOTENV=1 SOLVERAH_IGNORE_DOTENV=1 APP_ENV=development \
  DATABASE_URL=postgresql://solverah:solverah@localhost:5433/solverah_pilot \
  JWT_SECRET_KEY=local-pilot-not-a-real-secret-32-bytes-min \
  JWT_COOKIE_SECURE=false JWT_COOKIE_SAMESITE=Lax \
  python -m flask db upgrade
```

**Never point pytest at `solverah_pilot`.** The test suite wipes its database. The tests
use `solverah_pilot_test`.

## 7. Import the answers

Set these once per terminal:

```sh
export SOLVERAH_IGNORE_DOTENV=1 APP_ENV=development \
  JWT_SECRET_KEY=local-pilot-not-a-real-secret-32-bytes-min \
  JWT_COOKIE_SECURE=false JWT_COOKIE_SAMESITE=Lax \
  PILOT_DB=postgresql://solverah:solverah@localhost:5433/solverah_pilot
```

First a dry run, which reads the CSV and writes nothing:

```sh
python -m causal_graph.v1_model.pilot_form.import_responses \
  ~/Desktop/solverah-pilot/responses.csv --dry-run
```

Then the real import:

```sh
python -m causal_graph.v1_model.pilot_form.import_responses \
  ~/Desktop/solverah-pilot/responses.csv --database-url "$PILOT_DB"
```

What it prints:

- **imported now / already imported**: re-running on the same file, or on a later download
  that still has the old rows in it, is safe. Rows already in the database are skipped.
- **current-job reports / past-job reports**: the training rows. Past-job rows are
  exploratory only (Amendment 1).
- **first_job**: these people answered the how-you-work questions but have no job to
  describe, so, as in the app, they get no job report and no training row.
- **skipped**: a row that can't be used at all (for example, the how-you-work questions
  weren't all answered). The reason is listed.
- **failed**: a row the app's own code refused. It is rolled back entirely; the reason is
  listed.

Each respondent is stored as a user `pilot-<id>@pilotform.solverah.invalid` that cannot
sign in. Real emails go only to `Desktop/solverah-pilot/emails.csv` (columns `pilot_id`,
`email`, `followup_ok`): never into the database, never into the repo, never onto the
screen. An emails.csv from before `followup_ok` existed still loads; its rows read `no`.

If the import says **REFUSED: the CSV does not match form_mapping.json**, the CSV is from a
different form or the form's questions were edited after it was built. If it says the form
was generated from **different item banks**, the app's questions changed after the form was
built; the old form's answers can't be scored as the new questions.

## 8. Send someone their report

1. Open `Desktop/solverah-pilot/emails.csv` and find the person's **pilot id**.
2. With the step-7 variables still set:

   ```sh
   python -m causal_graph.v1_model.pilot_form.report_back <pilot_id> --database-url "$PILOT_DB"
   ```

3. It writes `Desktop/solverah-pilot/reports/<pilot_id>.txt`. Open it, read it over, and
   paste it into an email.

The report is the app's own Situation Report for that person: the same ranking, the same
guidance text, the same "what to look for next" version for someone between jobs. It
contains words only, never scores or numbers (D-15); the helper refuses to write a report
that contains a digit. Two lines in some reports point to the app's Manager Decoder, which
pilot respondents can't open; trim them if you like.

Someone looking for their first job has no report (there's no job to compare against).

## Follow-up consent (a later check-in, not built yet)

The last page asks, optionally, **"Can we check in once in a few months?"** The intro and
the email question say the email is used for the report and, only if they say yes, one
check-in. `followup_ok` in `emails.csv` is `yes` only when the person said yes **and** left
an email (a yes with no email can't be acted on, so it counts as no); blank counts as no.

Nothing sends that check-in yet. When one is built, it re-asks only "Overall, how well is
this role working for you?" (`experienced`), and only of `followup_ok = yes` respondents.
Those later ratings are **exploratory** under the pre-registration (Part 3, "Pulse repeats
of `experienced`"); they are not part of Look 1 or Look 2 and don't count toward the
thresholds.

---

## What's in this folder

| file | what it is |
|---|---|
| `spec.py` | The form as data, read from the app's question banks. The only words written here are the intro, page titles and the few form-only questions (best-guess copy; Julie owns copy). |
| `generate_form_script.py` | Writes `build_form.gs` and `form_mapping.json` from the spec. `--check` reports stale files. |
| `build_form.gs` | Generated. The Apps Script you paste into Google. |
| `form_mapping.json` | Generated. Which column is which question, and which option text means which stored answer. |
| `responses.py` | Reads the downloaded CSV into answers. No database. |
| `import_responses.py` | Writes those answers through the app's own code into `solverah_pilot`. |
| `report_back.py` | One person's report as plain text. |
| `sample_csv.py` | Builds a fake export from the mapping, for tests and trying things out. |
| `legacy/` | Frozen mappings for form structures that predate the current one -- never regenerated. `import_responses` accepts a CSV matching any of them so an already-distributed older form keeps working. |

## How the form differs from the app

- **Question order.** The app shows each person the how-you-work questions in their own
  shuffled order. A Google Form has one order for everyone, so the form uses the order the
  app would show one particular person. The same rules hold (no two questions about the same
  thing back to back), but everyone sees the same sequence.
- **Pages, not one question per screen.** The how-you-work questions come eight to a page;
  the job questions in five pages (the setup, two pages about the work, "Overall, how well
  is this role working for you?" alone on its own page so it is answered last, then the five
  optional outcome questions below).
- **Tense.** The app picks present or past tense from your profile. The form asks "Where
  are you in your career?" and sends people to a present-tense or past-tense copy of the job
  questions.

## The five optional outcome questions (2026-10-13)

Each job section ends with an extra, optional page: satisfaction, performance, engagement,
sustainability, and whether they expect to still be in the role a year from now. They come
**after** "Overall, how well is this role working for you?", never before it -- that question
is still the one the model is fitted on, and it must stay unprimed by anything evaluative.
The five are exploratory only (pre-registration Amendment 3): they inform nothing today,
change no score or report, and a respondent can skip any or all of them.

**If you already sent out a form built before this date** (pilot-v1-2026-10-01, without
these questions), its responses still import. The sixteen required questions are unchanged,
so they score exactly as before; the five outcome columns are simply left blank for those
rows. You do not need to rebuild or resend that form -- `import_responses` recognises either
export and uses whichever mapping matches. You only need to rebuild the form (step 2) if you
want new respondents to see the five outcome questions.

## Where the rows go next

`assemble_training_data.assemble_environment_training_data` on `solverah_pilot` returns
these rows with `respondent_source = 'pilot_form'`. The pre-registration's rules apply as
written: first current report per respondent; past-job rows exploratory; at each look the
calls are also computed on app rows alone, and a disagreement is reported as
"mode-sensitive".
