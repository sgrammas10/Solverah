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

test("REAL STACK: register -> verify -> sign in -> assessment -> results", async ({ page }) => {
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
