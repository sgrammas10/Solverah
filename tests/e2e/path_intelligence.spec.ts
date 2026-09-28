/**
 * Workstream F's real-stack flow: suggestions -> verdict -> re-rank -> deep fit.
 *
 * BUILD_PLAN §7's rule is one full `real_stack` flow per workstream, and this is
 * F's. `real_stack.spec.ts` covers registration, the assessment and Workstream
 * A's Situation Report; this file starts from a signed-in user and walks the
 * half F built: the corpus retrieval seam (F-3), the rewritten scorer (F-4),
 * deep fit on click (F-5) and the inline feedback loop (F-6).
 *
 * WHAT THIS PROVES, AND WHAT IT DELIBERATELY DOES NOT.
 *
 * It proves the PLUMBING across every layer at once: a job is accepted and
 * polled, a real scorer runs against a real corpus file, a shortlist is stored
 * and served, a verdict POST re-ranks it in place, and a card opens a deep fit
 * the API computed rather than a fixture. The mocked frontend suite has already
 * demonstrated it cannot catch cross-layer drift -- that is why this layer
 * exists at all.
 *
 * It says NOTHING about ranking quality, and must not be read as though it
 * does. Quality is F-2's offline harness's job, against the real 1,016-row
 * artifact and a labelled set; a browser is the wrong instrument for it, and
 * this file asserts shape and behaviour rather than which occupations come
 * back.
 *
 * ── WHICH CORPUS, AND A FINDING THAT DECIDES IT ────────────────────────────
 *
 * F-8 box 7's brief asked for this flow to run against F-3's committed 26-row
 * synthetic fixture, so that no runner would need the real artifact. **It
 * cannot.** The fixture's vectors are EIGHT-dimensional -- deliberately, so a
 * reader can check every cosine by hand -- and every real embedding is 1,536.
 * `adjacent` blends the corpus anchor with the user's skills document
 * (`path_scoring._blend`), so the two meet in one arithmetic expression and
 * numpy refuses to broadcast them. Measured here first as
 * `500 Unable to score career paths`, from `_build_query`.
 *
 * That is a fixture limitation and not a product defect: the fixture is usable
 * with a FAKE embedder, which is how `tests/test_path_scoring.py` uses it, and
 * unusable with a real one. Closing it means regenerating the fixture at 1,536
 * dimensions -- 160 KB, small enough to commit -- and rewriting every
 * hand-written vector assertion in `tests/test_occupation_retrieval.py` that
 * depends on its 8 readable planes. That is F-3's file and a chunk of its own;
 * F-8 records it rather than doing it.
 *
 * So this file runs against whatever corpus the API is serving, and the only
 * fixture-specific assertion is gated on `E2E_CORPUS_IS_FIXTURE`. Point the API
 * at the real artifact (local path, or S3 via `SOLVERAH_CORPUS_S3_KEY` once
 * Sebastian has published one) and set `E2E_CORPUS_IS_FIXTURE=0`.
 *
 * PREREQUISITES. Everything `real_stack.spec.ts` lists, and three more on the
 * Flask process:
 *
 *   SOLVERAH_CORPUS_PATH=...  a 1,536-dimension artifact -- see above
 *   OPENAI_API_KEY=...        embeddings, one batched request per scoring run
 *   ONET_API_KEY=...          the deep-fit step makes FOUR live O*NET calls for
 *                             the one occupation clicked. `OnetClient()` is
 *                             constructed before `deep_fit` runs, so a missing
 *                             key is a 500 rather than a typed error -- a known
 *                             defect, recorded in F-8's report, not fixed there.
 *
 * NOT in the CI gate, for the reason `playwright.config.ts` gives for the suite
 * as a whole.
 */
import { execFileSync } from "node:child_process";

import { expect, test } from "@playwright/test";

import { E2E_CORPUS_CODES, E2E_CORPUS_RESIDUALS } from "./fixtures/corpus";

const PSQL =
  process.env.E2E_PSQL ?? "C:/Program Files/PostgreSQL/18/bin/psql.exe";
const PGHOST = process.env.E2E_PGHOST ?? "localhost";
const PGPORT = process.env.E2E_PGPORT ?? "5433";
const PGUSER = process.env.E2E_PGUSER ?? "solverah";
const PGDATABASE = process.env.E2E_PGDATABASE ?? "solverah_e2e";

/**
 * Whether the API is serving the committed 26-row fixture.
 *
 * Defaults to FALSE -- the header explains why the fixture cannot carry this
 * flow while its vectors are 8-dimensional. Set `E2E_CORPUS_IS_FIXTURE=1` once
 * it is regenerated at 1,536, and the corpus-identity assertion comes back.
 */
const CORPUS_IS_FIXTURE = process.env.E2E_CORPUS_IS_FIXTURE === "1";

function sql(statement: string): string {
  return execFileSync(
    PSQL,
    ["-h", PGHOST, "-p", PGPORT, "-U", PGUSER, "-d", PGDATABASE, "-tAc", statement],
    {
      env: { ...process.env, PGPASSWORD: process.env.PGPASSWORD ?? "solverah" },
      encoding: "utf8",
    },
  ).trim();
}

const STAMP = Date.now();
const USER = {
  name: "E2E Path Walker",
  email: `e2e-paths-${STAMP}@example.com`,
  password: "E2e-Passw0rd!" + STAMP,
};

/**
 * The profile the scorer needs, written straight into the database.
 *
 * SETUP, and called out rather than buried. Driving the profile editor here
 * would test the profile editor -- which `feature_tour.spec.ts` already covers
 * -- and would put a dozen UI interactions in front of the thing this file is
 * about.
 *
 * **Written to the real tables, not to the profile blob.** Phase 2 moved
 * skills and experience out of `users.profile_data` into `profile_skills` and
 * `profile_experiences`; `profile_repository.load_document` assembles the
 * document from those rows and keeps only what has no column in
 * `profiles.extra`. A seed that writes `skills` into `extra` therefore looks
 * right in the database and is invisible to `build_user_profile` -- and the
 * first `update_document` that runs discards it, which is exactly what the
 * first draft of this file did.
 *
 * A data-shaped title on purpose: the fixture corpus's tech rows are the ones
 * with the most neighbours in it, so an `adjacent` search has somewhere to go.
 * A warehouse worker in a 26-row corpus has almost nothing that is not one of
 * the residual buckets retrieval filters out.
 */
const TITLE = "Data Analyst";
const SKILLS: readonly [string, number][] = [
  ["SQL", 5],
  ["Python", 3],
  ["Microsoft Excel", 5],
  ["Statistics", 3],
];
/** `skill_levels` has no column and stays in the document, as does this flag. */
const PROFILE_EXTRA = {
  skill_levels: {
    SQL: "advanced",
    Python: "intermediate",
    "Microsoft Excel": "advanced",
    Statistics: "intermediate",
  },
  // Otherwise the skill-rating modal opens over the page before the preferences
  // form does. That modal has its own coverage; here it is a gate in front of
  // this flow rather than part of it, and the ratings above are what it would
  // have collected.
  skills_proficiency_confirmed: true,
};

// Longer than the 30s default: one cold scoring run plus a deep fit is four
// live O*NET calls and two OpenAI round trips, on top of registration and the
// preferences form. F-5 measured the cold deep fit alone at 2,384 ms.
test.setTimeout(180_000);

test("REAL STACK (F): path suggestions -> verdict -> re-rank -> deep fit", async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];
  const apiCalls: string[] = [];

  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("requestfailed", (req) => {
    failedRequests.push(`${req.method()} ${req.url()} -- ${req.failure()?.errorText}`);
  });
  page.on("response", (res) => {
    const url = res.url();
    if (url.includes("/api/v1/me/path")) {
      apiCalls.push(`${res.status()} ${res.request().method()} ${new URL(url).pathname}`);
    }
    if (res.status() >= 400) {
      failedRequests.push(`${res.status()} ${res.request().method()} ${url}`);
    }
  });

  await test.step("register and verify", async () => {
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
  });

  await test.step("sign in", async () => {
    await page.getByLabel("Email address").fill(USER.email);
    await page.getByLabel("Password", { exact: true }).fill(USER.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/job-seeker\/dashboard/, { timeout: 20_000 });
  });

  await test.step("seed the profile the scorer reads", async () => {
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
                  SELECT count(*) FROM profile_experiences pe WHERE pe.user_id = p.user_id
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

    // Three one-question steps. `adjacent` deliberately: it is the intent F-6's
    // feedback loop was built for, and the one this flow taps a verdict on.
    // `fresh_start` would additionally need a cluster sidecar beside the corpus,
    // which the committed fixture does not carry -- that path would fall back to
    // an in-process k-means fit and test scikit-learn's availability rather than
    // anything Solverah wrote.
    for (const label of ["Something adjacent", "Similar level", "Learning & growth"]) {
      await expect(page.getByRole("button", { name: new RegExp(label) })).toBeVisible({
        timeout: 20_000,
      });
      await page.getByRole("button", { name: new RegExp(label) }).click();
      await page
        .getByRole("button", { name: /^(Next →|See my paths →)$/ })
        .click();
    }

    // The last click fires the PUT. Waiting for the form to go away rather than
    // querying straight after the click: the first draft of this file raced the
    // request and read an empty column, which looks exactly like a bug in the
    // endpoint and is not one.
    await expect(
      page.getByRole("button", { name: /See my paths →/ }),
    ).toBeHidden({ timeout: 20_000 });
    await page.screenshot({
      path: "test-results/f-01-preferences-done.png",
      fullPage: true,
    });

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

  await test.step("the job runs and a shortlist comes back", async () => {
    // The card list is the assertion. Getting here at all means the POST was
    // accepted, the poll reached `succeeded`, `score_paths` ran against a real
    // corpus file and the result was stored and served -- five layers, none of
    // them stubbed.
    const cards = page.locator("[data-onet-code]");
    await expect(cards.first()).toBeVisible({ timeout: 60_000 });
    await page.screenshot({ path: "test-results/f-02-shortlist.png", fullPage: true });

    firstPage = await cards.evaluateAll((nodes) =>
      nodes.map((n) => n.getAttribute("data-onet-code") ?? ""),
    );
    expect(firstPage.length, "the shortlist was empty").toBeGreaterThan(0);
    expect(new Set(firstPage).size, "the same card was shown twice").toEqual(
      firstPage.length,
    );

    for (const code of firstPage) {
      expect(code, "a card carried no O*NET code").toMatch(/^\d{2}-\d{4}(\.\d{2})?$/);
      expect(
        E2E_CORPUS_RESIDUALS,
        "retrieval served an '..., All Other' residual bucket",
      ).not.toContain(code);
    }

    if (CORPUS_IS_FIXTURE) {
      // What proves the API is actually pointed at the committed fixture,
      // rather than a README line claiming it is.
      for (const code of firstPage) {
        expect(
          E2E_CORPUS_CODES,
          `${code} is not in the fixture corpus -- is SOLVERAH_CORPUS_PATH set?`,
        ).toContain(code);
      }
    }

    expect(
      sql(
        `SELECT count(*) FROM scoring_jobs j JOIN users u ON u.id = j.user_id
          WHERE u.email = '${USER.email}' AND j.status = 'succeeded'`,
      ),
      "no succeeded job row -- the shortlist did not come from the job pair",
    ).not.toEqual("0");
  });

  await test.step("both verdicts reach the server and re-rank the list", async () => {
    // F-6's loop, end to end, and BOTH signals -- they are not symmetric and
    // the design says so. "Interesting" rotates the query toward that card and
    // the card STAYS (dismissing something the user just said they liked would
    // be the opposite of what they asked for). "Too similar" raises the annulus
    // inner radius, so the card and everything nearer the anchor than it are
    // excluded from the next retrieval, and the card GOES.
    //
    // The first draft of this step asserted `aria-pressed` on a `too_similar`
    // control and failed because the control no longer existed -- which is the
    // product behaving correctly and the test asking the wrong question.
    const liked = firstPage[0];

    await page
      .locator(`[data-onet-code="${liked}"] [data-verdict="interesting"]`)
      .click();
    await expect(
      page.locator(`[data-onet-code="${liked}"] [data-verdict="interesting"]`),
      "an 'interesting' card did not stay, or did not report itself pressed",
    ).toHaveAttribute("aria-pressed", "true", { timeout: 20_000 });

    // Wait for the re-rank to settle, then READ THE PAGE AGAIN before picking
    // the second card. Two things make that necessary, and both are F-6 working
    // as designed rather than flake: every verdict control is disabled while
    // `feedbackPending`, so clicking straight through races a node that is
    // about to be replaced; and the Rocchio rotation changes which occupations
    // are RETRIEVED, not merely their order, so a code that was on the first
    // page may legitimately not be on the second. Both cost this step a failing
    // run before it was written this way.
    await expect(
      page.locator(`[data-onet-code="${liked}"] [data-verdict="interesting"]`),
    ).toBeEnabled({ timeout: 20_000 });

    const afterLike = await page
      .locator("[data-onet-code]")
      .evaluateAll((nodes) => nodes.map((n) => n.getAttribute("data-onet-code") ?? ""));
    const dismissed = afterLike.find((code) => code !== liked);
    expect(dismissed, "nothing on the page to dismiss but the liked card").toBeTruthy();

    await page
      .locator(`[data-onet-code="${dismissed}"] [data-verdict="too_similar"]`)
      .click();
    await expect(
      page.locator(`[data-onet-code="${dismissed}"]`),
      "a card the user called too similar came back",
    ).toHaveCount(0, { timeout: 20_000 });

    await expect(
      page.getByText(/These paths are shaped by what you've told us/),
    ).toBeVisible({ timeout: 20_000 });
    await page.screenshot({ path: "test-results/f-03-reranked.png", fullPage: true });

    // Real rows, not optimistic UI. This is the half no frontend test can see.
    expect(
      sql(
        `SELECT string_agg(f.onet_code || '=' || f.verdict, ',' ORDER BY f.onet_code)
           FROM path_feedback f JOIN users u ON u.id = f.user_id
          WHERE u.email = '${USER.email}'`,
      ),
      "the verdicts never reached the database",
    ).toEqual(
      [`${liked}=interesting`, `${dismissed}=too_similar`].sort().join(","),
    );

    const afterTaps = await page
      .locator("[data-onet-code]")
      .evaluateAll((nodes) => nodes.map((n) => n.getAttribute("data-onet-code") ?? ""));

    expect(afterTaps.length, "the taps emptied the page").toBeGreaterThan(0);
    expect(afterTaps, "the liked card was dropped").toContain(liked);
    // Deliberately NOT "the order changed". Whether a rotation reorders a
    // particular page is a ranking question, and this file is not a ranking
    // test -- F-2's harness is. What IS guaranteed by design is the two
    // behaviours asserted above.
  });

  await test.step("clicking a card opens a deep fit the API computed", async () => {
    const remaining = await page
      .locator("[data-onet-code]")
      .evaluateAll((nodes) => nodes.map((n) => n.getAttribute("data-onet-code") ?? ""));
    const clicked = remaining[0];

    await page
      .locator(`[data-onet-code="${clicked}"]`)
      .getByRole("button", { name: /^See how .* fits you$/ })
      .click();

    const panel = page.getByRole("dialog");
    await expect(panel).toBeVisible({ timeout: 20_000 });
    // F-5 measured the common case -- a different user, a card somebody else
    // warmed -- at 844 ms, and the cold case at 2,384 ms with four O*NET calls.
    await expect(panel.getByText(/What you'd be doing/)).toBeVisible({
      timeout: 30_000,
    });
    await page.screenshot({ path: "test-results/f-04-deep-fit.png", fullPage: true });

    // Stored per (user, occupation), which is the half the panel cannot show.
    expect(
      sql(
        `SELECT count(*) FROM path_fits f JOIN users u ON u.id = f.user_id
          WHERE u.email = '${USER.email}' AND f.onet_code = '${clicked}'`,
      ),
      "the deep fit rendered but was never stored",
    ).toEqual("1");

    await panel.getByRole("button", { name: "Close" }).click();
    await expect(panel).toBeHidden();
  });

  await test.step("starting over puts the default list back", async () => {
    await page.getByRole("button", { name: "Start over" }).click();
    await expect(
      page.getByText(/These paths are shaped by what you've told us/),
    ).toBeHidden({ timeout: 20_000 });

    expect(
      sql(
        `SELECT count(*) FROM path_feedback f JOIN users u ON u.id = f.user_id
          WHERE u.email = '${USER.email}'`,
      ),
      "the judgements survived a clear",
    ).toEqual("0");
  });

  console.log("\n=== PATH API CALLS ===\n" + apiCalls.join("\n"));
  if (consoleErrors.length || failedRequests.length) {
    console.log("\n=== BROWSER CONSOLE ERRORS ===\n" + (consoleErrors.join("\n") || "(none)"));
    console.log(
      "\n=== FAILED / 4xx-5xx REQUESTS ===\n" + (failedRequests.join("\n") || "(none)"),
    );
  }
});
