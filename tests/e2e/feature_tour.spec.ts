/**
 * A survey, not a gate. Walks every authenticated feature route as a real user
 * against the real backend and records what each one actually does.
 *
 * This exists to answer "which of these is real, which is a stub, and which is
 * broken" with evidence rather than memory -- the question you ask before
 * deciding what ships. It asserts almost nothing on purpose: a route that is
 * half-built is a FINDING, not a failure, and a suite that goes red on the first
 * one stops surveying.
 *
 * Prerequisites are the same as real_stack.spec.ts: a migrated database and a
 * Flask on :5000 started with SOLVERAH_IGNORE_DOTENV=1. External providers
 * (OpenAI, Groq, Resend, S3) are absent, which is itself informative -- any
 * route that hard-depends on one will show that here.
 *
 * Output is a table on stdout, plus test-results/tour-*.png per route.
 */
import { execFileSync } from "node:child_process";

import { expect, test } from "@playwright/test";

const PSQL = process.env.E2E_PSQL ?? "C:/Program Files/PostgreSQL/18/bin/psql.exe";
const PGARGS = ["-h", "localhost", "-p", "5433", "-U", "solverah", "-d", "solverah_e2e", "-tAc"];

function sql(statement: string): string {
  return execFileSync(PSQL, [...PGARGS, statement], {
    env: { ...process.env, PGPASSWORD: process.env.PGPASSWORD ?? "solverah" },
    encoding: "utf8",
  }).trim();
}

const STAMP = Date.now();
const USER = {
  name: "Tour Walker",
  email: `tour-${STAMP}@example.com`,
  password: "T0ur-Passw0rd!" + STAMP,
};

/** Routes worth surveying. `/companies/:id` needs a seeded id; `*` is the 404. */
const ROUTES: Array<{ path: string; label: string }> = [
  { path: "/job-seeker/dashboard", label: "Dashboard" },
  { path: "/job-seeker/profile", label: "Profile" },
  { path: "/intelligence", label: "Intelligence hub" },
  { path: "/solverah-profile", label: "Solverah profile (alias)" },
  { path: "/company-lens", label: "CompanyLens" },
  { path: "/trait-preferences", label: "Trait preferences" },
  { path: "/intelligence/paths", label: "Path Intelligence (Pro)" },
  { path: "/focus-type", label: "FocusType" },
  { path: "/focus-type/results", label: "FocusType results" },
  { path: "/manager-match", label: "ManagerMatch" },
  { path: "/manager-match/results", label: "ManagerMatch results" },
  { path: "/manager-profile", label: "Manager Decoder" },
  { path: "/manager-profile/playbook", label: "Manager Decoder playbook" },
  { path: "/environment-report", label: "Environment report" },
  { path: "/situation-report", label: "Situation Report" },
  { path: "/pulse", label: "Pulse check-in" },
  { path: "/pulse/trend", label: "Pulse trend" },
  { path: "/work-pulse/results", label: "Work Pulse results" },
  { path: "/career-quizzes", label: "Career quizzes hub" },
  { path: "/career-quizzes/early-career", label: "Quiz: early career" },
  { path: "/career-quizzes/career-transition", label: "Quiz: career transition" },
  { path: "/career-quizzes/mid-career", label: "Quiz: mid career" },
  { path: "/career-quizzes/teen-focused", label: "Quiz: teen focused" },
  { path: "/career-job-search", label: "Quiz: next chapter" },
  { path: "/future-your-way", label: "Quiz: future your way" },
  { path: "/quiz-insights", label: "Quiz insights" },
  { path: "/trust", label: "Trust / transparency" },
  { path: "/agent", label: "Agent chat" },
  { path: "/feed", label: "Feed" },
  { path: "/search", label: "Search" },
];

/**
 * CompanyLens is live (six-trait model, PRODUCT_DECISIONS §2, 2026-10-13), so the
 * generic COMING-SOON / GATED words say nothing about it. Name which of its three
 * states rendered instead. After this tour's core sitting, a fresh database gives
 * NO-COMPANIES; RANKED means researched companies already exist; CORE-REQUIRED
 * here means the sitting did not register. Any percentage is flagged loudly,
 * because the page must never show a score, a percentage or a probability.
 */
function companyLensState(body: string): string {
  let state = "LENS:UNRECOGNISED ";
  if (/Start with how you like to work/.test(body)) state = "LENS:CORE-REQUIRED ";
  else if (/No companies yet/.test(body)) state = "LENS:NO-COMPANIES ";
  else if (/Your companies|Not enough evidence yet/.test(body)) state = "LENS:RANKED ";
  if (/%/.test(body)) state += "LENS:PERCENT-SHOWN! ";
  return state;
}

test("FEATURE TOUR: what every authenticated route actually does", async ({ page }) => {
  test.setTimeout(600_000);

  // ── sign up and complete the assessment, so the tour sees the unlocked app ──
  await page.goto("/register");
  await page.getByLabel("Full name").fill(USER.name);
  await page.getByLabel("Email address").fill(USER.email);
  await page.getByLabel("Password", { exact: true }).fill(USER.password);
  await page.getByLabel("Confirm password").fill(USER.password);
  await page.getByLabel(/I am 16 or older/).check();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/verify-email/, { timeout: 20_000 });

  const code = sql(`SELECT confirmation_token FROM users WHERE email = '${USER.email}'`);
  await page.getByPlaceholder("000000").fill(code);
  await page.getByRole("button", { name: "Verify email" }).click();
  await expect(page).toHaveURL(/\/login/, { timeout: 20_000 });

  await page.getByLabel("Email address").fill(USER.email);
  await page.getByLabel("Password", { exact: true }).fill(USER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/job-seeker\/dashboard/, { timeout: 20_000 });

  await page.goto("/work-pulse");
  const counter = await page.getByText(/Question 1 of \d+/).textContent();
  const total = Number(/of (\d+)/.exec(counter ?? "")?.[1]);
  for (let n = 1; n <= total; n += 1) {
    await page.getByRole("radio").nth(n % 2).click();
    await page.getByRole("button", { name: n === total ? "Finish" : "Next" }).click();
  }
  // The optional tolerance step opens first; skip it so the tour sees an
  // unanswered user (it surveys /trait-preferences on its own below).
  await page.getByRole("button", { name: "Skip for now" }).click({ timeout: 30_000 });
  await expect(page.getByText("That's everything we need")).toBeVisible({ timeout: 30_000 });

  // ── the survey ──
  const rows: string[] = [];

  for (const { path, label } of ROUTES) {
    const errors: string[] = [];
    const bad: string[] = [];
    const onConsole = (m: any) => { if (m.type() === "error") errors.push(m.text()); };
    const onResponse = (r: any) => {
      if (r.status() >= 400) bad.push(`${r.status()} ${new URL(r.url()).pathname}`);
    };
    page.on("console", onConsole);
    page.on("response", onResponse);

    let landed = "";
    let heading = "";
    let chars = 0;
    let note = "";

    try {
      await page.goto(path, { timeout: 30_000 });
      await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
      landed = new URL(page.url()).pathname;

      const h = page.locator("h1, h2").first();
      heading = ((await h.count()) ? (await h.textContent())?.trim() : "") ?? "";

      const main = (await page.textContent("body")) ?? "";
      chars = main.replace(/\s+/g, " ").trim().length;

      // Cheap classifiers so triage does not need 22 screenshots.
      if (/coming soon|not yet available|under construction/i.test(main)) note += "COMING-SOON ";
      if (/unlock|locked/i.test(main)) note += "GATED ";
      if (/something went wrong|couldn't load|error/i.test(main)) note += "ERROR-COPY ";
      if (chars < 400) note += "NEARLY-EMPTY ";
      if (path === "/company-lens") note += companyLensState(main);
      if (landed !== path) note += `REDIRECTED->${landed} `;

      await page.screenshot({
        path: `test-results/tour-${path.replace(/\//g, "_")}.png`,
        fullPage: true,
      });
    } catch (err: any) {
      note += "THREW:" + String(err?.message ?? err).slice(0, 60);
    }

    page.off("console", onConsole);
    page.off("response", onResponse);

    rows.push(
      [
        label.padEnd(30),
        path.padEnd(34),
        String(chars).padStart(6),
        (errors.length ? `err:${errors.length}` : "-").padEnd(8),
        (bad.length ? bad.slice(0, 2).join(",") : "-").padEnd(22),
        (note || "ok") + (heading ? ` | "${heading.slice(0, 44)}"` : ""),
      ].join(" "),
    );
  }

  console.log("\n\n================ FEATURE TOUR ================");
  console.log(
    ["ROUTE".padEnd(30), "PATH".padEnd(34), " CHARS", "CONSOLE ", "HTTP".padEnd(22), "NOTES"].join(" "),
  );
  console.log("-".repeat(150));
  for (const r of rows) console.log(r);
  console.log("=".repeat(150) + "\n");
});
