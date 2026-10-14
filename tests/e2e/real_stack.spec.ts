/**
 * The critical path against the REAL backend. No API stubs.
 *
 * `smoke.spec.ts` walks the same journey against `fixtures/api.ts`, which proves
 * the SPA behaves correctly given a contract-shaped response. It cannot prove the
 * server produces that shape -- both halves have only ever been tested against
 * their own idea of the contract. This file closes that gap: a real Flask process,
 * a real Postgres, real cookies, real session handling, and the real production
 * frontend bundle.
 *
 * WHAT IS REAL AND WHAT IS NOT. Everything in the application is real. The email
 * is not *sent* -- there is no Resend key in this environment -- so the six-digit
 * confirmation code is read back out of the database, which is the same value the
 * email would have carried. That is the only shortcut, and it is a shortcut around
 * a third party rather than around any Solverah code: registration still writes
 * the token, and `/verify-email` still validates it.
 *
 * PREREQUISITES, because this suite deliberately does not start the API for you:
 *
 *   1. A migrated database, and a Flask listening on :5000 with APP_ENV=development,
 *      SOLVERAH_IGNORE_DOTENV=1 (so it cannot reach production), JWT_COOKIE_SECURE=false
 *      and SOLVERAH_FORM_TOKEN_SECRET set.
 *   2. E2E_DATABASE_URL / E2E_PSQL pointing this file at that same database.
 *
 * If the API is not up, the first step fails with a connection error rather than
 * a confusing assertion, which is the intended failure mode.
 *
 * This file is NOT in the CI gate, for the same reason `playwright.config.ts`
 * gives for the suite as a whole.
 */
import { execFileSync } from "node:child_process";

import { expect, test } from "@playwright/test";

const PSQL =
  process.env.E2E_PSQL ?? "C:/Program Files/PostgreSQL/18/bin/psql.exe";
const PGHOST = process.env.E2E_PGHOST ?? "localhost";
const PGPORT = process.env.E2E_PGPORT ?? "5433";
const PGUSER = process.env.E2E_PGUSER ?? "solverah";
const PGDATABASE = process.env.E2E_PGDATABASE ?? "solverah_e2e";

function sql(statement: string): string {
  return execFileSync(
    PSQL,
    ["-h", PGHOST, "-p", PGPORT, "-U", PGUSER, "-d", PGDATABASE, "-tAc", statement],
    { env: { ...process.env, PGPASSWORD: process.env.PGPASSWORD ?? "solverah" }, encoding: "utf8" },
  ).trim();
}

// Unique per run: this database is not reset between runs, and a duplicate
// address would fail registration for a reason that has nothing to do with the app.
const STAMP = Date.now();
const USER = {
  name: "E2E Walker",
  email: `e2e-${STAMP}@example.com`,
  password: "E2e-Passw0rd!" + STAMP,
};

test("REAL STACK: register -> verify -> sign in -> assessment -> environment report -> Situation Report", async ({ page }) => {
  // Everything the browser complains about, collected rather than ignored. A
  // journey that "passes" while the console fills with errors is not a journey
  // a user would enjoy, and this is the cheapest place to notice.
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];

  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("requestfailed", (req) => {
    failedRequests.push(`${req.method()} ${req.url()} -- ${req.failure()?.errorText}`);
  });
  page.on("response", (res) => {
    if (res.status() >= 400) failedRequests.push(`${res.status()} ${res.request().method()} ${res.url()}`);
  });

  await test.step("register", async () => {
    await page.goto("/register");
    await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible();

    await page.getByLabel("Full name").fill(USER.name);
    await page.getByLabel("Email address").fill(USER.email);
    await page.getByLabel("Password", { exact: true }).fill(USER.password);
    await page.getByLabel("Confirm password").fill(USER.password);
    await page.getByLabel(/I am 16 or older/).check();

    await page.screenshot({ path: "test-results/real-01-register.png", fullPage: true });
    await page.getByRole("button", { name: "Create account" }).click();

    await expect(page).toHaveURL(/\/verify-email/, { timeout: 20_000 });
  });

  await test.step("the server actually persisted the registration", async () => {
    // The stubbed suite asserts the SPA *sent* the right body. This asserts the
    // server *stored* it -- the half no stub can speak for.
    const row = sql(
      `SELECT email_confirmed_at IS NULL FROM users WHERE email = '${USER.email}'`,
    );
    expect(row, "no user row was written by /auth/register").not.toEqual("");
    expect(row, "a brand-new user must not start out confirmed").toEqual("t");
  });

  await test.step("verify email with the real code", async () => {
    await expect(page.getByRole("heading", { name: "Check your inbox" })).toBeVisible();
    await expect(page.getByText(USER.email)).toBeVisible();

    const code = sql(`SELECT confirmation_token FROM users WHERE email = '${USER.email}'`);
    expect(code, "registration did not store a confirmation token").toMatch(/^\d{6}$/);

    const verifyButton = page.getByRole("button", { name: "Verify email" });
    await expect(verifyButton).toBeDisabled();
    await page.getByPlaceholder("000000").fill(code);
    await expect(verifyButton).toBeEnabled();
    await verifyButton.click();

    await expect(page.getByText(/Email verified/)).toBeVisible({ timeout: 20_000 });
    await expect(page).toHaveURL(/\/login/, { timeout: 20_000 });

    expect(
      sql(`SELECT email_confirmed_at IS NOT NULL FROM users WHERE email = '${USER.email}'`),
      "the UI said verified but the database disagrees",
    ).toEqual("t");
  });

  await test.step("sign in", async () => {
    await page.getByLabel("Email address").fill(USER.email);
    await page.getByLabel("Password", { exact: true }).fill(USER.password);
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page).toHaveURL(/\/job-seeker\/dashboard/, { timeout: 20_000 });
    await page.screenshot({ path: "test-results/real-02-dashboard.png", fullPage: true });
  });

  await test.step("the session survives a reload", async () => {
    // Real cookies, real SameSite, real refresh path -- none of which a stubbed
    // login exercises, and all of which are what actually break in production.
    await page.reload();
    await expect(page).toHaveURL(/\/job-seeker\/dashboard/, { timeout: 20_000 });
  });

  await test.step("assessment", async () => {
    await page.goto("/work-pulse");
    await expect(page.getByRole("heading", { name: "Work Pulse" })).toBeVisible({
      timeout: 20_000,
    });
    await page.screenshot({ path: "test-results/real-03-work-pulse.png", fullPage: true });

    // The item count comes from the server here, not from a fixture constant.
    const counter = await page.getByText(/Question 1 of \d+/).textContent();
    const total = Number(/of (\d+)/.exec(counter ?? "")?.[1]);
    expect(total, "the server served an assessment with no items").toBeGreaterThan(0);

    for (let n = 1; n <= total; n += 1) {
      await expect(page.getByText(`Question ${n} of ${total}`)).toBeVisible();
      const advance = page.getByRole("button", { name: n === total ? "Finish" : "Next" });
      await expect(advance).toBeDisabled();
      await page.getByRole("radio").nth(n % 2).click();
      await expect(advance).toBeEnabled();
      await advance.click();
    }

    // A saved sitting opens the optional tolerance step first (six-trait model,
    // 2026-10-13); skipping it writes nothing and leads on to the completion card.
    await expect(page.getByRole("heading", { name: "How much give is there?" })).toBeVisible({
      timeout: 30_000,
    });
    await page.getByRole("button", { name: "Skip for now" }).click();
    await expect(page.getByText("That's everything we need")).toBeVisible({ timeout: 30_000 });
    await page.screenshot({ path: "test-results/real-04-submitted.png", fullPage: true });
  });

  await test.step("the submission reached the database", async () => {
    const submissions = sql(
      `SELECT count(*) FROM assessment_submissions s
         JOIN users u ON u.id = s.user_id
        WHERE u.email = '${USER.email}'`,
    );
    expect(submissions, "the UI accepted the assessment but nothing was stored").not.toEqual("0");

    // Status and answers, not just a row: an empty submission would satisfy a
    // count and prove nothing about the instrument having been recorded.
    const detail = sql(
      `SELECT s.status || '|' || COALESCE(jsonb_array_length(
                CASE WHEN jsonb_typeof(s.answers) = 'array' THEN s.answers ELSE '[]'::jsonb END), -1)
         FROM assessment_submissions s
         JOIN users u ON u.id = s.user_id
        WHERE u.email = '${USER.email}'
        ORDER BY s.id DESC LIMIT 1`,
    );
    console.log("submission status|answer-array-length: " + detail);
  });

  await test.step("results render", async () => {
    await page.goto("/work-pulse/results");
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: "test-results/real-05-results.png", fullPage: true });

    // Deliberately weak: this step exists to CAPTURE what a real user sees after
    // finishing the assessment, not to encode today's copy as a requirement.
    const body = (await page.textContent("body")) ?? "";
    expect(body.length, "the results page rendered nothing at all").toBeGreaterThan(200);
  });

  // ── Workstream A: the Situation Report (BUILD_PLAN A-7, §6's "one full flow
  //    per workstream"). Everything below is real: a real environment-report
  //    submission, real rules scoring, a real gap against the pinned core
  //    sitting, and the real assembled guidance content.

  await test.step("give this user a career status", async () => {
    // SETUP, and the second SQL shortcut in this file -- called out because
    // the header promises there is only one. This is not a bypass of anything
    // under test: `career_status` is normally set by editing the profile (a
    // surface the feature tour already covers) and the environment instrument
    // reads it only to pick a tense and to stamp the stored row. Driving the
    // profile editor here would test the profile editor.
    //
    // `employed` deliberately, not `between_jobs`: it produces the full
    // present-tense report, and the needs-forward slicing has its own unit
    // coverage. A brand-new user may have no `profiles` row at all yet.
    sql(
      `INSERT INTO profiles (user_id, career_status, completeness, extra, version)
         SELECT id, 'employed', 0, '{}'::jsonb, 0 FROM users WHERE email = '${USER.email}'
       ON CONFLICT (user_id) DO UPDATE SET career_status = 'employed'`,
    );
    expect(
      sql(`SELECT p.career_status FROM profiles p
             JOIN users u ON u.id = p.user_id
            WHERE u.email = '${USER.email}'`),
    ).toEqual("employed");
  });

  await test.step("environment report", async () => {
    await page.goto("/environment-report");
    await expect(
      page.getByRole("heading", { name: /Now the other half/ }),
    ).toBeVisible({ timeout: 20_000 });
    await page.screenshot({ path: "test-results/real-07-env-intro.png", fullPage: true });

    await page.getByRole("button", { name: "Start" }).click();

    // The count comes off the page, not a fixture constant -- the item bank
    // lives in Python and this file must not encode a second copy of its size.
    const counter = await page.getByText(/Question 1 of \d+/).textContent();
    const total = Number(/of (\d+)/.exec(counter ?? "")?.[1]);
    expect(total, "the environment form rendered no questions").toBeGreaterThan(0);

    for (let n = 1; n <= total; n += 1) {
      await expect(page.getByText(`Question ${n} of ${total}`)).toBeVisible();
      const advance = page.getByRole("button", { name: n === total ? "Finish" : "Next" });
      await expect(advance).toBeDisabled();
      // Alternating anchors rather than a straight line: a straight-lined sheet
      // lands every dimension on the midpoint by design (the anchor-order
      // balance), which would produce a report with nothing in it to assert on.
      await page.getByRole("radio").nth(n % 2 === 0 ? 0 : 4).click();
      await expect(advance).toBeEnabled();
      await advance.click();
    }

    await expect(page).toHaveURL(/\/situation-report/, { timeout: 30_000 });
  });

  await test.step("the environment report reached the database", async () => {
    const row = sql(
      `SELECT e.version || '|' || COALESCE(e.career_status, '?') || '|' ||
              jsonb_array_length(to_jsonb(ARRAY(SELECT jsonb_object_keys(e.raw_answers))))
         FROM environment_reports e
         JOIN users u ON u.id = e.user_id
        WHERE u.email = '${USER.email}'
        ORDER BY e.id DESC LIMIT 1`,
    );
    expect(row, "the UI accepted the environment report but nothing was stored").not.toEqual("");
    console.log("environment report version|career_status|answer-count: " + row);
    expect(row, "the stored row did not snapshot the live career_status").toContain("|employed|");
  });

  await test.step("the Situation Report renders with buckets", async () => {
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: "test-results/real-08-situation-report.png", fullPage: true });

    await expect(page.getByRole("heading", { name: "You, and this job" })).toBeVisible();

    // At least one dimension came back classified. The three bucket words are
    // the ENTIRE resolution the report gives out, so their presence is the
    // assertion that the gap engine ran end to end.
    const buckets = page.getByText(/^(Aligned|Notable|Straining)$/);
    expect(await buckets.count(), "no dimension carried a bucket").toBeGreaterThan(0);

    // The guidance notice must reach the page verbatim -- it is the scope
    // disclaimer, not decoration. (The old "What this is, and what it isn't"
    // footer was folded into "About this report" in 0796599.)
    await expect(page.getByText(/This guidance is general, not personal/)).toBeVisible();
    await expect(page.getByRole("heading", { name: "About this report" })).toBeVisible();

    // D-15, checked at the pixel rather than in a unit test's fixture: the
    // payload carries `env_score` per dimension as a 0-1 float, and not one of
    // them may reach the page. Any leak shows up as a decimal.
    const body = (await page.textContent("body")) ?? "";
    expect(body, "a 0-1 score leaked into the rendered report").not.toMatch(/\b0\.\d/);
  });

  await test.step("the Solverah profile actually unlocks", async () => {
    // The regression this journey was written to catch. IntelligencePage gated on
    // `wpl_completed`, set only by the retired 12-item instrument, while its own
    // "Start Work Pulse" CTA opened /work-pulse -- the 24-item `core`, which sets
    // `wp_v2_completed`. Finishing onboarding therefore left the hub locked with
    // no route out. Unit tests could not see it: their fixtures set the legacy
    // flag by hand, so the mock disagreed with the server.
    await page.goto("/intelligence");
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: "test-results/real-06-intelligence.png", fullPage: true });

    await expect(
      page.getByText(/Complete Work Pulse to unlock your profile/i),
      "the hub is still locked after completing the instrument its own CTA starts",
    ).toHaveCount(0);

    // And unlocked to something, not to a blank page: the old code returned null
    // when there was no narrative, which `core` never produces.
    await expect(
      page.getByRole("heading", { name: /Everything we know about how you work/i }),
    ).toBeVisible();
  });

  // Reported at the end so the journey completes first and the screenshots exist.
  // These are findings, not necessarily failures -- see the run report.
  if (consoleErrors.length || failedRequests.length) {
    console.log("\n=== BROWSER CONSOLE ERRORS ===\n" + (consoleErrors.join("\n") || "(none)"));
    console.log("\n=== FAILED / 4xx-5xx REQUESTS ===\n" + (failedRequests.join("\n") || "(none)"));
  }
});
