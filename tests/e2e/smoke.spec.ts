/**
 * The critical path, per ARCHITECTURE.md 6.5: register -> verify -> assessment -> matches.
 *
 * One test, not four. The steps are not independent -- each depends on the state
 * the previous one left in the stub state machine and in the browser's session --
 * and splitting them into separate tests would mean either re-driving the whole
 * prefix each time or sharing mutable state between tests that Playwright is free
 * to reorder. `test.step` gives the same per-stage readability in the report
 * without pretending the stages are separable.
 *
 * A fifth stage appears here that 6.5 does not name: SIGN IN, between verify and
 * assessment. It is not scope creep -- the app requires it. ConfirmEmail redirects
 * to /login on success and issues no session of its own, and /work-pulse is behind
 * RequireAuth. Without signing in, the assessment step would land on /login and
 * a test asserting "we reached the assessment" would be asserting a redirect.
 *
 * Read tests/e2e/fixtures/api.ts before trusting a green run here: the API is
 * stubbed, and the header of that file says exactly what that does and does not
 * prove.
 */
import { expect, test } from "@playwright/test";

import { ITEM_COUNT, TEST_USER, installApiStubs } from "./fixtures/api";
// The same no-probability guard the CompanyLens component tests run.
import { assertNoProbabilityText } from "../msw/companyLensHandlers";

test("register -> verify -> assessment -> matches", async ({ page }) => {
  const api = await installApiStubs(page);

  await test.step("register", async () => {
    await page.goto("/register");
    await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible();

    await page.getByLabel("Full name").fill(TEST_USER.name);
    await page.getByLabel("Email address").fill(TEST_USER.email);
    // exact:true, or this also matches the "Confirm password" label.
    await page.getByLabel("Password", { exact: true }).fill(TEST_USER.password);
    await page.getByLabel("Confirm password").fill(TEST_USER.password);
    await page.getByLabel(/I am 16 or older/).check();

    await page.getByRole("button", { name: "Create account" }).click();

    // Register navigates to /verify-email carrying the address in router state,
    // which is why the next step does not have to retype it.
    await expect(page).toHaveURL(/\/verify-email/);

    expect(api.register).toMatchObject({
      email: TEST_USER.email,
      name: TEST_USER.name,
      role: "job-seeker",
      terms_accepted: true,
    });
    // The accepted version is recorded server-side as evidence, so its presence
    // is part of the contract rather than a detail of the form.
    expect(typeof api.register?.terms_version).toBe("string");
  });

  await test.step("verify email", async () => {
    await expect(page.getByRole("heading", { name: "Check your inbox" })).toBeVisible();
    // The address came through router state, not a re-entry by the user.
    await expect(page.getByText(TEST_USER.email)).toBeVisible();

    const verifyButton = page.getByRole("button", { name: "Verify email" });
    // The 6-digit guard: the button stays disabled until the code is complete.
    await expect(verifyButton).toBeDisabled();

    await page.getByPlaceholder("000000").fill(TEST_USER.verificationCode);
    await expect(verifyButton).toBeEnabled();
    await verifyButton.click();

    await expect(page.getByText(/Email verified/)).toBeVisible();
    expect(api.verify).toEqual({
      email: TEST_USER.email,
      code: TEST_USER.verificationCode,
    });

    // ConfirmEmail redirects after REDIRECT_DELAY_MS (2 s), so this wait is real
    // rather than incidental.
    await expect(page).toHaveURL(/\/login/, { timeout: 15_000 });
  });

  await test.step("sign in", async () => {
    await page.getByLabel("Email address").fill(TEST_USER.email);
    await page.getByLabel("Password", { exact: true }).fill(TEST_USER.password);
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page).toHaveURL(/\/job-seeker\/dashboard/);
    expect(api.login).toEqual({
      email: TEST_USER.email,
      password: TEST_USER.password,
    });
  });

  await test.step("matches before the assessment", async () => {
    await page.goto("/company-lens");

    // No core sitting yet: a prompt, not an error and not an empty ranking.
    await expect(
      page.getByRole("heading", { name: "Start with how you like to work" }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Take Work Pulse" })).toBeVisible();
    await expect(page.locator('section[aria-labelledby="lens-ranked"]')).toHaveCount(0);
  });

  await test.step("assessment", async () => {
    await page.goto("/work-pulse");

    // Reaching the form at all is the RequireAuth assertion: a session that
    // did not survive the reload would have redirected to /login instead.
    await expect(page.getByRole("heading", { name: "Work Pulse" })).toBeVisible();

    const expectedTokens = api.servedForm.blocks.flatMap((b) => b.items.map((i) => i.token));
    expect(expectedTokens).toHaveLength(ITEM_COUNT);

    for (let n = 1; n <= ITEM_COUNT; n += 1) {
      await expect(page.getByText("Question " + n + " of " + ITEM_COUNT)).toBeVisible();

      const advance = page.getByRole("button", { name: n === ITEM_COUNT ? "Finish" : "Next" });
      // Every question gates its own advance button until it has been answered.
      await expect(advance).toBeDisabled();

      // Alternate the choice so the submitted payload is not a constant, which
      // would pass even if the stepper wrote every answer to the same token.
      await page.getByRole("radio").nth(n % 2).click();
      await expect(advance).toBeEnabled();
      await advance.click();
    }

    // A saved sitting opens the tolerance step first (six-trait model,
    // 2026-10-13). Skipping writes nothing -- any PUT would show up in
    // `api.unhandled` -- and leads on to the completion card.
    await expect(page.getByRole("heading", { name: "How much give is there?" })).toBeVisible();
    await page.getByRole("button", { name: "Skip for now" }).click();
    await expect(page.getByText("That's everything we need")).toBeVisible();

    // The submission is the point of the step: 24 answers, keyed by the opaque
    // tokens the server issued, in the instrument the server served.
    const responses = api.submission?.responses ?? {};
    expect(Object.keys(responses).sort()).toEqual([...expectedTokens].sort());
    expect(Object.values(responses).every((v) => v === "A" || v === "B")).toBe(true);
  });

  await test.step("matches", async () => {
    await page.goto("/company-lens");

    await expect(
      page.getByRole("heading", { name: "Companies, read against how you like to work" }),
    ).toBeVisible();

    // The server's order IS the ranking, and the page keeps it: the company
    // with a broken must-have is listed last among the ranked, never hidden.
    const ranked = page.locator('section[aria-labelledby="lens-ranked"] article');
    await expect(ranked).toHaveCount(2);
    expect(await ranked.evaluateAll((els) => els.map((el) => el.getAttribute("aria-label")))).toEqual(
      ["Northwind Freight", "Grindstone Corp"],
    );
    // Coverage is the only number on a card: how much of the company we could read.
    await expect(ranked.first().getByText("Based on 4 of 6 traits")).toBeVisible();
    await expect(ranked.nth(1).getByText("1 must-have outside your give")).toBeVisible();

    // A company read on too few traits is not placed, and says what is missing.
    await expect(page.getByRole("heading", { name: "Not enough evidence yet" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Little Studio" })).toBeVisible();

    // The tolerance step was skipped, so the page offers it again.
    await expect(page.getByRole("link", { name: "Tell us how much give you have" })).toBeVisible();

    // PRODUCT_DECISIONS §2: never a score, a percentage or a probability.
    assertNoProbabilityText(await page.getByRole("main").innerText());

    expect(api.matchStates).toEqual(["core_required", "ranked"]);
  });

  // Drift check. An endpoint the SPA calls that this suite does not model is
  // either a new call site or a moved one, and in both cases the stubs above are
  // no longer describing the app.
  expect(api.unhandled).toEqual([]);
});
