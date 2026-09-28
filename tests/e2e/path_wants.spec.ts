/**
 * Workstream W's real-stack flow: the wants panel, end to end, against the DB.
 *
 * BUILD_PLAN §7's rule is one full `real_stack` flow per workstream. F's is
 * `path_intelligence.spec.ts` (preferences -> job -> shortlist -> verdict ->
 * deep fit -> start over). This is W's, and it sits BESIDE that file rather
 * than inside it: the two answer different questions, and a single 20-step
 * journey that fails at step 14 tells you less than two that fail separately.
 *
 * WHAT THIS PROVES. The wants layer across every layer at once, with the
 * DATABASE asserted at each step rather than the screen believed:
 *
 *   1. the suggestion list renders WITHOUT the panel -- ⚑7's rule, and the one
 *      claim in W-5 that no unit test can make (`PathWantsPanel` renders null
 *      in a mocked page whether or not the page is waiting on it);
 *   2. the panel is built from the user's OWN resolved occupation -- its task
 *      labels are byte-equal to the tasks sidecar's labels for the anchor the
 *      PUT later stores, so "the panel names the job the scorer anchored on"
 *      is checked against the artifact rather than against the heading;
 *   3. nothing is written until the button is pressed (W-5's one-save rule):
 *      zero `path_wants` rows and zero `PUT`s after three radio clicks;
 *   4. the PUT stores the ORIGINAL O*NET statement in `item_text`, not the
 *      plain-words label -- W-4's design doc §8.7 rule, and the one that makes
 *      an answer survive a quarterly relabel. Asserted against the sidecar;
 *   5. a save drops the shortlist and the page re-scores through its OWN
 *      existing enqueue-and-poll -- a NEW `scoring_jobs` row, not a second
 *      job flow;
 *   6. `reasons` reaches the wire as an array, and a card carrying one renders
 *      it (see the note on emptiness below);
 *   7. a tap still works with wants applied, and the wants rows survive it;
 *   8. ⚑12: no `%` anywhere on the page, deep-fit panel open;
 *   9. answers come back selected after a reload, and "Clear my answers"
 *      removes the rows and the reason lines with them.
 *
 * WHAT IT DOES NOT PROVE: ranking quality. W-3's offline harness measured that
 * (nDCG@10 0.300 -> 0.444 on the fifteen wants-stating profiles) against a
 * labelled set; a browser is the wrong instrument and this file asserts shape
 * and behaviour, never which occupations come back.
 *
 * ── `reasons` IS LEGITIMATELY EMPTY FOR SOME PAGES ─────────────────────────
 *
 * W-4's distinctiveness rule drops any phrase true of >= 70% of the page's
 * cards, from ALL of them -- so a page whose ten cards are alike on every
 * stated axis correctly carries no reason line at all. Asserting "a card has a
 * reason" would therefore be asserting a property of one profile's corpus
 * neighbourhood, which is exactly the kind of assertion that goes red for a
 * reason nobody can act on. So the assertion here is the wire contract --
 * `reasons` is present and is an array on every card -- and the rendered line
 * is asserted only when the payload actually carries one. The run logs which
 * happened and what the line said.
 *
 * ── PREREQUISITES ──────────────────────────────────────────────────────────
 *
 * Everything `path_intelligence.spec.ts` lists, plus the W-4 migration:
 *
 *   flask db upgrade            `20260921_path_wants`, or both panel calls 500
 *   SOLVERAH_CORPUS_PATH        a 1,536-dimension artifact WITH its two W-3
 *                               sidecars, `*.tasks.json` and `*.experience.json`
 *   OPENAI_API_KEY              embeddings; the stated task statements ride in
 *                               the one batched call `score_paths` already makes
 *   ONET_API_KEY                the deep-fit step's four live calls
 *
 * and the same two this suite's other real-stack files need: a Flask process on
 * the origin the bundle was BUILT against (`VITE_API_URL`), and `E2E_PSQL` /
 * `E2E_PGDATABASE` pointing this file at that same database.
 *
 * Run it the way the others are run, with the API up:
 *
 *   E2E_PGDATABASE=solverah_w7 npx playwright test tests/e2e/path_wants.spec.ts
 *
 * SKIPS RATHER THAN FAILS when the database, `psql` or the task sidecar is
 * absent -- a runner without them has nothing to say about this feature, and a
 * red that means "not configured" is a red that gets ignored. A Flask that is
 * DOWN is deliberately not part of that check: that is `real_stack.spec.ts`'s
 * intended failure mode, a connection error on the first step rather than a
 * silent green.
 *
 * NOT in the CI gate, for the reason `playwright.config.ts` gives for the suite
 * as a whole.
 */
import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

const PSQL =
  process.env.E2E_PSQL ?? "C:/Program Files/PostgreSQL/18/bin/psql.exe";
const PGHOST = process.env.E2E_PGHOST ?? "localhost";
const PGPORT = process.env.E2E_PGPORT ?? "5433";
const PGUSER = process.env.E2E_PGUSER ?? "solverah";
const PGDATABASE = process.env.E2E_PGDATABASE ?? "solverah_w7";

/** The corpus directory the API was pointed at, for the sidecar cross-checks. */
const CORPUS_DIR =
  process.env.E2E_CORPUS_DIR ?? process.env.SOLVERAH_CORPUS_PATH ?? "";

function sql(statement: string): string {
  return execFileSync(
    PSQL,
    ["-h", PGHOST, "-p", PGPORT, "-U", PGUSER, "-d", PGDATABASE, "-tAc", statement],
    {
      env: { ...process.env, PGPASSWORD: process.env.PGPASSWORD ?? "solverah" },
      encoding: "utf8",
    },
  )
    .replace(/\r/g, "")
    .trim();
}

/** `{code: [{task, label}]}` from the corpus's tasks sidecar, or null. */
type TaskRow = { task: string; label: string };
function loadTaskSidecar(): Record<string, TaskRow[]> | null {
  if (!CORPUS_DIR || !existsSync(CORPUS_DIR)) return null;
  const name = readdirSync(CORPUS_DIR).find((f) => f.endsWith(".tasks.json"));
  if (!name) return null;
  const parsed = JSON.parse(readFileSync(join(CORPUS_DIR, name), "utf8"));
  return (parsed.tasks ?? null) as Record<string, TaskRow[]> | null;
}

/** `{code: title}` from the corpus manifest, or null. */
function loadCorpusTitles(): Record<string, string> | null {
  if (!CORPUS_DIR || !existsSync(CORPUS_DIR)) return null;
  // The manifest, not one of the four sidecars beside it: exactly one dot.
  const name = readdirSync(CORPUS_DIR).find((f) => /^[^.]+\.json$/.test(f));
  if (!name) return null;
  const parsed = JSON.parse(readFileSync(join(CORPUS_DIR, name), "utf8"));
  const codes: string[] = parsed.codes ?? [];
  const titles: string[] = parsed.titles ?? [];
  if (codes.length === 0 || codes.length !== titles.length) return null;
  return Object.fromEntries(codes.map((code, i) => [code, titles[i]]));
}

const STAMP = Date.now();
const USER = {
  name: "E2E Wants Walker",
  email: `e2e-wants-${STAMP}@example.com`,
  password: "E2e-Passw0rd!" + STAMP,
};

/**
 * A developer, for the same reason `path_intelligence.spec.ts` picks a data
 * title: the corpus's tech rows have the most neighbours, so `adjacent` has
 * somewhere to go, and W-3's measurement set contains this shape of profile
 * (p26 "developer done with code" is its largest single gain). `adjacent` also
 * has to be the intent here because `stay_in_field` ignores CARD feedback by
 * design (F-6) and this flow taps one.
 */
const TITLE = "Software Developer";
/**
 * `proficiency` is the SCORE column, and only `{1, 3, 5}` round-trips:
 * `profile_document.PROFICIENCY_BY_SCORE` inverts `{beginner: 1, intermediate:
 * 3, advanced: 5}` and a 4 in that column makes `GET /me/profile` raise a bare
 * `KeyError` (seen once while writing this, and the seed was wrong rather than
 * the app -- nothing but this file can put a 4 there).
 */
const SKILLS: readonly [string, number][] = [
  ["Python", 5],
  ["SQL", 5],
  ["JavaScript", 3],
  ["Git", 3],
  ["Amazon Web Services", 3],
];
const PROFILE_EXTRA = {
  skill_levels: {
    Python: "advanced",
    SQL: "advanced",
    JavaScript: "intermediate",
    Git: "intermediate",
    "Amazon Web Services": "intermediate",
  },
  // Otherwise the skill-rating modal opens in front of this flow. It has its
  // own coverage; here it is a gate rather than part of what is under test.
  skills_proficiency_confirmed: true,
};

/** The four axes W-4 asks about, in the order the panel shows them. */
const CONDITION_LABELS = [
  "Time working with other people",
  "Dealing with customers or the public",
  "Leading or directing other people",
  "At a desk, rather than on your feet",
];

// Two cold scoring runs (the first page and the re-score after the save), a
// third after the tap, a fourth after the clear, plus a cold deep fit at four
// live O*NET calls. 180s is not enough for this one.
test.setTimeout(480_000);

const taskSidecar = loadTaskSidecar();
const corpusTitles = loadCorpusTitles();

test("REAL STACK (W): wants panel -> re-ranked page -> tap -> fit panel -> clear", async ({
  page,
}) => {
  test.skip(!existsSync(PSQL), `no psql at ${PSQL} -- set E2E_PSQL`);
  test.skip(
    (() => {
      try {
        return sql("SELECT to_regclass('public.path_wants') IS NULL") !== "f";
      } catch {
        return true;
      }
    })(),
    `${PGDATABASE} is unreachable or has no path_wants table -- run flask db upgrade`,
  );
  test.skip(
    taskSidecar === null,
    "no *.tasks.json beside the corpus -- set E2E_CORPUS_DIR / SOLVERAH_CORPUS_PATH",
  );

  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];
  const apiCalls: string[] = [];
  /** Every `/me/path-wants` request, by method -- the "nothing written yet" check. */
  const wantsCalls: string[] = [];
  /** The last succeeded job payload, for the `reasons` wire assertion. */
  let lastJobResult: Record<string, unknown> | null = null;

  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("requestfailed", (req) => {
    failedRequests.push(`${req.method()} ${req.url()} -- ${req.failure()?.errorText}`);
  });
  page.on("response", async (res) => {
    const url = res.url();
    if (url.includes("/api/v1/me/path")) {
      apiCalls.push(`${res.status()} ${res.request().method()} ${new URL(url).pathname}`);
    }
    if (url.includes("/api/v1/me/path-wants")) {
      wantsCalls.push(`${res.request().method()} ${res.status()}`);
    }
    if (url.includes("/api/v1/me/path-suggestion-jobs/") && res.status() === 200) {
      try {
        const body = (await res.json()) as { status?: string; result?: Record<string, unknown> };
        if (body.status === "succeeded" && body.result) lastJobResult = body.result;
      } catch {
        /* a poll body that is not JSON is the failedRequests listener's problem */
      }
    }
    if (res.status() >= 400) {
      failedRequests.push(`${res.status()} ${res.request().method()} ${url}`);
    }
  });

  await test.step("register, verify and sign in", async () => {
    await page.goto("/register");
    await page.getByLabel("Full name").fill(USER.name);
    await page.getByLabel("Email address").fill(USER.email);
    await page.getByLabel("Password", { exact: true }).fill(USER.password);
    await page.getByLabel("Confirm password").fill(USER.password);
    await page.getByLabel(/I am 16 or older/).check();
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page).toHaveURL(/\/verify-email/, { timeout: 20_000 });

    const code = sql(
      `SELECT confirmation_token FROM users WHERE email = '${USER.email}'`,
    );
    expect(code, "registration did not store a confirmation token").toMatch(/^\d{6}$/);
    await page.getByPlaceholder("000000").fill(code);
    await page.getByRole("button", { name: "Verify email" }).click();
    await expect(page).toHaveURL(/\/login/, { timeout: 20_000 });

    await page.getByLabel("Email address").fill(USER.email);
    await page.getByLabel("Password", { exact: true }).fill(USER.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/job-seeker\/dashboard/, { timeout: 20_000 });
  });

  await test.step("seed the current job and skills the anchor resolves from", async () => {
    // SETUP, called out rather than buried, and `path_intelligence.spec.ts`'s
    // reasoning verbatim: driving the profile editor here would test the
    // profile editor. The rows go to `profile_skills` / `profile_experiences`
    // because Phase 2 moved them out of `users.profile_data` and
    // `profile_repository.load_document` reads only those.
    //
    // The CURRENT job is the whole input to this feature -- the panel asks
    // about it and `no_anchor` is the answer without it -- so `is_current` is
    // load-bearing here in a way it is not in F's flow.
    const extra = JSON.stringify(PROFILE_EXTRA).replace(/'/g, "''");
    sql(
      `INSERT INTO profiles (user_id, career_status, completeness, extra, version)
         SELECT id, 'employed', 0, '${extra}'::jsonb, 0
           FROM users WHERE email = '${USER.email}'
       ON CONFLICT (user_id) DO UPDATE
         SET career_status = 'employed', extra = '${extra}'::jsonb`,
    );
    sql(
      `INSERT INTO profile_experiences (user_id, company_name, title, is_current, ordinal)
         SELECT id, 'Acme', '${TITLE}', true, 0 FROM users WHERE email = '${USER.email}'`,
    );
    SKILLS.forEach(([label, proficiency], index) => {
      const slug = label.toLowerCase().replace(/[^a-z0-9]+/g, "-");
      sql(`INSERT INTO skills (slug, label) VALUES ('${slug}', '${label}')
             ON CONFLICT (slug) DO NOTHING`);
      sql(
        `INSERT INTO profile_skills (user_id, skill_id, label, proficiency, ordinal)
           SELECT u.id, s.id, '${label}', ${proficiency}, ${index}
             FROM users u, skills s
            WHERE u.email = '${USER.email}' AND s.slug = '${slug}'
          ON CONFLICT (user_id, skill_id) DO UPDATE SET proficiency = ${proficiency}`,
      );
    });

    expect(
      sql(
        `SELECT p.career_status || '|' || (
                  SELECT count(*) FROM profile_skills ps WHERE ps.user_id = p.user_id
                ) || '|' || (
                  SELECT count(*) FROM profile_experiences pe
                   WHERE pe.user_id = p.user_id AND pe.is_current
                )
           FROM profiles p JOIN users u ON u.id = p.user_id
          WHERE u.email = '${USER.email}'`,
      ),
      "the profile seed did not land in the tables the repository reads",
    ).toEqual(`employed|${SKILLS.length}|1`);
  });

  await test.step("answer the three path preferences", async () => {
    await page.goto("/intelligence/paths");
    await expect(
      page.getByRole("heading", { name: "Your Career Paths" }),
    ).toBeVisible({ timeout: 20_000 });

    for (const label of ["Something adjacent", "Similar level", "Learning & growth"]) {
      await expect(page.getByRole("button", { name: new RegExp(label) })).toBeVisible({
        timeout: 20_000,
      });
      await page.getByRole("button", { name: new RegExp(label) }).click();
      await page.getByRole("button", { name: /^(Next →|See my paths →)$/ }).click();
    }
    await expect(
      page.getByRole("button", { name: /See my paths →/ }),
    ).toBeHidden({ timeout: 20_000 });

    expect(
      sql(
        `SELECT p.extra->'path_preferences'->>'move_intent'
           FROM profiles p JOIN users u ON u.id = p.user_id
          WHERE u.email = '${USER.email}'`,
      ),
      "the preferences the UI accepted were not stored",
    ).toEqual("adjacent");
  });

  let firstPage: string[] = [];

  await test.step("the list renders, and the panel did not gate it", async () => {
    // ⚑7's rule, checked at the pixel. The user has touched nothing on the
    // panel -- it is collapsed and unanswered -- and the shortlist is here.
    const cards = page.locator("[data-onet-code]");
    await expect(cards.first()).toBeVisible({ timeout: 120_000 });
    await page.screenshot({ path: "test-results/w-01-shortlist.png", fullPage: true });

    firstPage = await cards.evaluateAll((nodes) =>
      nodes.map((n) => n.getAttribute("data-onet-code") ?? ""),
    );
    expect(firstPage.length, "the shortlist was empty").toBeGreaterThan(0);
    for (const code of firstPage) {
      expect(code, "a card carried no O*NET code").toMatch(/^\d{2}-\d{4}(\.\d{2})?$/);
    }

    expect(
      sql(
        `SELECT count(*) FROM scoring_jobs j JOIN users u ON u.id = j.user_id
          WHERE u.email = '${USER.email}' AND j.status = 'succeeded'`,
      ),
      "no succeeded job row -- the shortlist did not come from the job pair",
    ).not.toEqual("0");

    // No wants stated yet, so W-3 pins that the conditions sidecar is never
    // read and every card carries `[]`. Nothing on the page may show a reason.
    expect(
      await page.locator("[data-reasons]").count(),
      "a card carried a reason line before any want was stated",
    ).toEqual(0);
  });

  /** `[kind, key, label]` for the rows this flow answers. */
  let markedLess = "";
  let markedMore = "";
  let markedCondition = "";

  await test.step("the panel names the resolved occupation and offers its tasks", async () => {
    const toggle = page.getByRole("button", {
      name: /Tell us what should change about your job/,
    });
    await expect(toggle, "the wants panel never rendered").toBeVisible({ timeout: 30_000 });
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");

    const heading = await page.getByText(/^About your work: /).textContent();
    const anchorTitle = (heading ?? "").replace("About your work: ", "").trim();
    expect(anchorTitle.length, "the panel did not name an occupation").toBeGreaterThan(0);
    console.log(`[W-7] panel anchor title: ${anchorTitle}`);

    const taskRows = page.locator('fieldset[data-want^="want-task-"]');
    const conditionRows = page.locator('fieldset[data-want^="want-condition-"]');
    const taskCount = await taskRows.count();
    expect(taskCount, "the panel offered no tasks").toBeGreaterThan(0);
    expect(taskCount, "the panel offered more than the eight W-3 selects").toBeLessThanOrEqual(8);
    expect(
      await conditionRows.count(),
      "the panel did not offer exactly the four W-4 conditions",
    ).toEqual(4);

    for (const [index, label] of CONDITION_LABELS.entries()) {
      await expect(
        conditionRows.nth(index).getByText(label, { exact: true }),
        "the conditions are not the four axes in the order W-4 fixes",
      ).toBeVisible();
    }

    // "Fine as it is" pre-selected on EVERY row, tasks and conditions alike:
    // W-4's "fine is the absence of a row", rendered.
    const everyRow = page.locator("fieldset[data-want]");
    const rowCount = await everyRow.count();
    for (let i = 0; i < rowCount; i += 1) {
      await expect(
        everyRow.nth(i).getByRole("radio", { name: "Fine as it is" }),
        "a row did not open on 'Fine as it is'",
      ).toBeChecked();
    }

    await page.screenshot({ path: "test-results/w-02-panel-open.png", fullPage: true });

    // Mark one task less, one task more, one condition more.
    markedLess = (await taskRows.nth(0).locator("legend").textContent())?.trim() ?? "";
    markedMore = (await taskRows.nth(1).locator("legend").textContent())?.trim() ?? "";
    markedCondition = CONDITION_LABELS[0];

    // The inputs are `sr-only`; the visible pill is the label's own span, which
    // is what a user clicks and what drives the radio.
    await taskRows.nth(0).getByText("Less of this", { exact: true }).click();
    await taskRows.nth(1).getByText("More of this", { exact: true }).click();
    await conditionRows.nth(0).getByText("More of this", { exact: true }).click();

    await expect(taskRows.nth(0).getByRole("radio", { name: "Less of this" })).toBeChecked();
    await expect(taskRows.nth(1).getByRole("radio", { name: "More of this" })).toBeChecked();
    await expect(
      conditionRows.nth(0).getByRole("radio", { name: "More of this" }),
    ).toBeChecked();

    console.log(
      `[W-7] marked less="${markedLess}" more="${markedMore}" condition="${markedCondition}"`,
    );
  });

  await test.step("three clicks wrote NOTHING", async () => {
    // W-5's one-save rule, and the half only the database can speak for.
    expect(
      sql(
        `SELECT count(*) FROM path_wants w JOIN users u ON u.id = w.user_id
          WHERE u.email = '${USER.email}'`,
      ),
      "a radio click wrote a row -- the panel is saving per control",
    ).toEqual("0");
    expect(
      wantsCalls.filter((c) => c.startsWith("PUT")),
      "a radio click sent a PUT -- the panel is saving per control",
    ).toEqual([]);
  });

  let anchorCode = "";

  await test.step("'Update my suggestions' writes once and re-scores", async () => {
    const jobsBefore = Number(
      sql(
        `SELECT count(*) FROM scoring_jobs j JOIN users u ON u.id = j.user_id
          WHERE u.email = '${USER.email}' AND j.job_type = 'path_suggestions'`,
      ),
    );

    const save = page.locator("[data-wants-save]");
    await expect(save, "the save button stayed disabled after three edits").toBeEnabled();
    await save.click();

    // `aria-busy`, not the button's prose and not the cards. The prose is
    // Julie's to change; the cards never leave the DOM between the old list and
    // the new one, so waiting on them is waiting on nothing. `aria-busy` is
    // exactly `wants.saving || awaitingRescore` -- true from the click until the
    // page's own enqueue-and-poll has landed the re-ranked list.
    //
    // The FIRST of these two is load-bearing and was learned the hard way: a
    // click returns before React has re-rendered, so every "has it finished"
    // assertion passes instantly against the pre-click DOM and the step then
    // reads a database the save has not reached yet.
    await expect(save, "the save never entered its busy state").toHaveAttribute(
      "aria-busy",
      "true",
      { timeout: 60_000 },
    );
    await expect(save, "the save never settled").toHaveAttribute("aria-busy", "false", {
      timeout: 300_000,
    });
    await expect(page.locator("[data-onet-code]").first()).toBeVisible({ timeout: 60_000 });

    expect(
      wantsCalls.filter((c) => c.startsWith("PUT")),
      "the save was not exactly one PUT",
    ).toEqual(["PUT 200"]);

    const rows = sql(
      `SELECT string_agg(w.kind || '|' || w.verdict || '|' || w.anchor_onet_code, E'\\n'
                         ORDER BY w.kind, w.verdict)
         FROM path_wants w JOIN users u ON u.id = w.user_id
        WHERE u.email = '${USER.email}'`,
    );
    const parsed = rows.split("\n").filter(Boolean);
    expect(parsed.length, "the three answers did not become three rows").toEqual(3);
    anchorCode = parsed[0].split("|")[2];
    expect(anchorCode, "the rows carry no anchor O*NET code").toMatch(
      /^\d{2}-\d{4}(\.\d{2})?$/,
    );
    for (const row of parsed) {
      expect(row.split("|")[2], "the three rows disagree about the anchor").toEqual(anchorCode);
    }
    expect(parsed.map((r) => r.split("|").slice(0, 2).join("|")).sort()).toEqual(
      ["condition|more", "task|less", "task|more"].sort(),
    );
    console.log(`[W-7] anchor stored on path_wants: ${anchorCode}`);

    // `item_text` is the ORIGINAL O*NET statement, not the plain-words label --
    // design doc §8.7, and what makes an answer survive a relabel. Checked
    // against the sidecar the API itself reads, and against the labels the
    // panel actually rendered.
    const texts = sql(
      `SELECT string_agg(w.kind || E'\\t' || w.item_text, E'\\n' ORDER BY w.kind, w.verdict)
         FROM path_wants w JOIN users u ON u.id = w.user_id
        WHERE u.email = '${USER.email}'`,
    )
      .split("\n")
      .map((line) => line.split("\t"));

    const taskTexts = texts.filter(([kind]) => kind === "task").map(([, text]) => text);
    const conditionTexts = texts
      .filter(([kind]) => kind === "condition")
      .map(([, text]) => text);
    expect(conditionTexts, "a condition stored an item_text -- an axis has none").toEqual([""]);
    expect(taskTexts.length).toEqual(2);

    const sidecarRows = taskSidecar?.[anchorCode] ?? [];
    expect(
      sidecarRows.length,
      `the tasks sidecar has no rows for ${anchorCode} -- wrong corpus?`,
    ).toBeGreaterThan(0);
    for (const label of [markedLess, markedMore]) {
      const row = sidecarRows.find((r) => r.label === label);
      expect(row, `the panel showed a label the sidecar does not carry: ${label}`).toBeTruthy();
      expect(
        taskTexts,
        "item_text is the display label, not the O*NET statement it was written from",
      ).toContain(row!.task);
      expect(
        taskTexts,
        "the plain-words label reached the column the scorer embeds",
      ).not.toContain(label);
    }

    // And the anchor the panel showed is the anchor the rows carry.
    if (corpusTitles) {
      await expect(
        page.getByText(`About your work: ${corpusTitles[anchorCode]}`),
        "the panel named a different occupation from the one the answers were stored against",
      ).toBeVisible();
    }

    await expect
      .poll(
        () =>
          Number(
            sql(
              `SELECT count(*) FROM scoring_jobs j JOIN users u ON u.id = j.user_id
                WHERE u.email = '${USER.email}' AND j.job_type = 'path_suggestions'`,
            ),
          ),
        {
          message:
            "the save did not start a new scoring job -- the shortlist was not re-ranked",
          timeout: 60_000,
        },
      )
      .toBeGreaterThan(jobsBefore);

    await page.screenshot({ path: "test-results/w-03-after-save.png", fullPage: true });
  });

  await test.step("the re-ranked payload carries `reasons`, and a line renders when it does", async () => {
    const suggestions = (lastJobResult?.["suggestions"] ?? []) as Array<{
      onet_code?: string;
      title?: string;
      reasons?: unknown;
    }>;
    expect(suggestions.length, "the re-scored job returned no suggestions").toBeGreaterThan(0);
    for (const suggestion of suggestions) {
      expect(
        Array.isArray(suggestion.reasons),
        `${suggestion.onet_code} carries no \`reasons\` array on the wire`,
      ).toBe(true);
    }

    const withReasons = suggestions.filter(
      (s) => Array.isArray(s.reasons) && (s.reasons as string[]).length > 0,
    );
    console.log(
      `[W-7] cards with a reason: ${withReasons.length} of ${suggestions.length}`,
    );
    for (const s of withReasons) {
      console.log(`[W-7]   ${s.onet_code} ${s.title}: ${(s.reasons as string[]).join(" | ")}`);
    }

    if (withReasons.length > 0) {
      // Rendered, not merely served. W-4's distinctiveness rule can
      // legitimately empty this for a page whose cards are all alike, which is
      // why the wire assertion above is the unconditional one.
      const rendered = page.locator("[data-reasons]");
      expect(
        await rendered.count(),
        "the payload carried reasons and the card rendered none",
      ).toBeGreaterThan(0);
      const first = (await rendered.first().textContent()) ?? "";
      expect(first.trim().length).toBeGreaterThan(0);
      expect(first, "a reason line is a percentage in a costume").not.toContain("%");
      console.log(`[W-7] first rendered reason line: ${first.trim()}`);
    } else {
      console.log(
        "[W-7] no card carried a reason for this profile -- legitimate, see the header",
      );
    }
  });

  await test.step("a tap still works, and the wants survive it", async () => {
    const codes = await page
      .locator("[data-onet-code]")
      .evaluateAll((nodes) => nodes.map((n) => n.getAttribute("data-onet-code") ?? ""));
    const liked = codes[0];

    await page.locator(`[data-onet-code="${liked}"] [data-verdict="interesting"]`).click();
    await expect(
      page.locator(`[data-onet-code="${liked}"] [data-verdict="interesting"]`),
      "an 'interesting' card did not stay, or did not report itself pressed",
    ).toHaveAttribute("aria-pressed", "true", { timeout: 60_000 });
    await expect(
      page.locator(`[data-onet-code="${liked}"] [data-verdict="interesting"]`),
    ).toBeEnabled({ timeout: 60_000 });

    expect(
      sql(
        `SELECT f.verdict FROM path_feedback f JOIN users u ON u.id = f.user_id
          WHERE u.email = '${USER.email}' AND f.onet_code = '${liked}'`,
      ),
      "the tap never reached path_feedback",
    ).toEqual("interesting");

    const afterTap = await page
      .locator("[data-onet-code]")
      .evaluateAll((nodes) => nodes.map((n) => n.getAttribute("data-onet-code") ?? ""));
    expect(afterTap.length, "the tap emptied the page").toBeGreaterThan(0);
    expect(afterTap, "the liked card was dropped").toContain(liked);
    await expect(
      page.getByText(/These paths are shaped by what you've told us/),
    ).toBeVisible({ timeout: 20_000 });

    // The re-rank goes through `_rescore`, which W-4 wired to read the stored
    // wants at the SECOND of its two sites. A tap must not clear them.
    expect(
      sql(
        `SELECT count(*) FROM path_wants w JOIN users u ON u.id = w.user_id
          WHERE u.email = '${USER.email}'`,
      ),
      "the tap cleared the stated wants",
    ).toEqual("3");
    await expect(
      page.getByRole("button", { name: /Tell us what should change about your job/ }),
    ).toContainText("3 things you want to change");

    await page.screenshot({ path: "test-results/w-04-after-tap.png", fullPage: true });
  });

  await test.step("the deep fit opens, and there is no % anywhere on the page", async () => {
    const codes = await page
      .locator("[data-onet-code]")
      .evaluateAll((nodes) => nodes.map((n) => n.getAttribute("data-onet-code") ?? ""));
    const clicked = codes[0];

    await page
      .locator(`[data-onet-code="${clicked}"]`)
      .getByRole("button", { name: /^See how .* fits you$/ })
      .click();

    const panel = page.getByRole("dialog");
    await expect(panel).toBeVisible({ timeout: 30_000 });
    await expect(panel.getByText(/What you'd be doing/)).toBeVisible({ timeout: 60_000 });

    expect(
      sql(
        `SELECT count(*) FROM path_fits f JOIN users u ON u.id = f.user_id
          WHERE u.email = '${USER.email}' AND f.onet_code = '${clicked}'`,
      ),
      "the deep fit rendered but was never stored",
    ).toEqual("1");

    // ⚑12, checked at the pixel with the panel OPEN -- which is the screen
    // W-1 removed four bars and a per-gap number from. Not one `%` may survive
    // anywhere on the document, panel and page together.
    const body = (await page.textContent("body")) ?? "";
    expect(body, "a percentage reached the page").not.toContain("%");
    await page.screenshot({ path: "test-results/w-05-deep-fit.png", fullPage: true });

    await panel.getByRole("button", { name: "Close" }).click();
    await expect(panel).toBeHidden();
  });

  await test.step("a reload brings the answers back", async () => {
    await page.reload();
    const toggle = page.getByRole("button", {
      name: /Tell us what should change about your job/,
    });
    await expect(toggle, "the panel did not come back after a reload").toBeVisible({
      timeout: 60_000,
    });
    await expect(
      toggle,
      "the collapsed row did not count the stored answers",
    ).toContainText("3 things you want to change");

    await toggle.click();
    const taskRows = page.locator('fieldset[data-want^="want-task-"]');
    const conditionRows = page.locator('fieldset[data-want^="want-condition-"]');
    await expect(
      taskRows.filter({ hasText: markedLess }).getByRole("radio", { name: "Less of this" }),
      "the stored 'less' did not come back selected",
    ).toBeChecked();
    await expect(
      taskRows.filter({ hasText: markedMore }).getByRole("radio", { name: "More of this" }),
      "the stored 'more' did not come back selected",
    ).toBeChecked();
    await expect(
      conditionRows.nth(0).getByRole("radio", { name: "More of this" }),
      "the stored condition did not come back selected",
    ).toBeChecked();

    await page.screenshot({ path: "test-results/w-06-reloaded.png", fullPage: true });
  });

  await test.step("'Clear my answers' removes the rows and the reason lines", async () => {
    // The list has to be on screen first: the page re-scores on a save and the
    // clear goes through the same path, so clicking while the first re-score is
    // still in flight would race a disabled control.
    await expect(page.locator("[data-onet-code]").first()).toBeVisible({ timeout: 180_000 });

    const clear = page.locator("[data-wants-clear]");
    const save = page.locator("[data-wants-save]");
    await expect(clear, "'Clear my answers' is not offered with answers stored").toBeVisible();
    await clear.click();

    // The same `aria-busy` gate the save step uses, and for the same reason:
    // "Clear my answers" goes through the one save.
    await expect(save, "the clear never entered its busy state").toHaveAttribute(
      "aria-busy",
      "true",
      { timeout: 60_000 },
    );
    await expect(save, "the clear never settled").toHaveAttribute("aria-busy", "false", {
      timeout: 300_000,
    });
    await expect(page.locator("[data-onet-code]").first()).toBeVisible({ timeout: 60_000 });

    expect(
      sql(
        `SELECT count(*) FROM path_wants w JOIN users u ON u.id = w.user_id
          WHERE u.email = '${USER.email}'`,
      ),
      "the answers survived a clear",
    ).toEqual("0");

    await expect(
      page.getByRole("button", { name: /Tell us what should change about your job/ }),
      "the collapsed row still counts answers that are gone",
    ).not.toContainText("things you want to change");

    // No wants stated, so W-3's pin says the conditions sidecar is never read
    // and every card is back to `[]`.
    await expect(
      page.locator("[data-reasons]"),
      "a reason line survived the clear",
    ).toHaveCount(0, { timeout: 60_000 });

    await page.screenshot({ path: "test-results/w-07-cleared.png", fullPage: true });
  });

  console.log("\n=== PATH API CALLS ===\n" + apiCalls.join("\n"));
  console.log("\n=== /me/path-wants CALLS ===\n" + wantsCalls.join("\n"));
  console.log("\n=== BROWSER CONSOLE ERRORS ===\n" + (consoleErrors.join("\n") || "(none)"));
  console.log(
    "\n=== FAILED / 4xx-5xx REQUESTS ===\n" + (failedRequests.join("\n") || "(none)"),
  );
});
