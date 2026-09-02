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
      page.getByRole("heading", { name: /Companies ranked by how well they match/ }),
    ).toBeVisible();

    // Both ends of the ranking are walked, as two requests rather than one body.
    await expect(page.getByText("Companies that match how you work")).toBeVisible();
    await expect(page.getByText("Companies worth understanding before committing")).toBeVisible();

    // exact:true on the names: each card also prints the company name inside its
    // fit_summary sentence, so a substring match resolves to two elements.
    await expect(page.getByText("Northwind Labs", { exact: true })).toBeVisible();
    await expect(page.getByText("92% match")).toBeVisible();
    await expect(page.getByText("Grindstone Corp", { exact: true })).toBeVisible();

    expect([...api.matchOrders].sort()).toEqual(["best", "worst"]);
  });

  // Drift check. An endpoint the SPA calls that this suite does not model is
  // either a new call site or a moved one, and in both cases the stubs above are
  // no longer describing the app.
  expect(api.unhandled).toEqual([]);
});
