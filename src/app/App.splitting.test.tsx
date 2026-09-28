/**
 * App — the code-splitting contract, asserted where it is easy to break.
 *
 * Phase 4b made 26 of the 33 route modules lazy. The two properties that make
 * that a win rather than a regression are invisible in a bundle report and easy
 * to undo by accident, so they are pinned here:
 *
 *   1. The entry surface stays eager. Converting `/` to `React.lazy` would look
 *      tidy and would put a chunk round trip in front of first paint — exactly
 *      the cost the split exists to remove. A test that fails when the landing
 *      page suspends is the cheapest guard against that.
 *
 *   2. Public first paint owes the API nothing. Retiring AuthProvider's
 *      full-screen gate (ARCHITECTURE.md 6.3) means the landing page renders
 *      while `GET /auth/session` is still in flight; the session wait now
 *      exists only behind RequireAuth. The third test holds the probe open and
 *      asserts the landing page is already on screen — the regression it
 *      catches is any new render gate on the session anywhere above routing.
 *
 * The session probe is served by MSW rather than by a `vi.fn()` over
 * `globalThis.fetch`. The default handler 401s, which is the signed-out boot
 * this file is describing, so the first test no longer has to say so.
 */
import { render, screen, act } from "@testing-library/react";
import { HttpResponse } from "msw";

import App from "./App";
import { mock } from "../../tests/msw/contract";
import { server, useApiMocks, recordRequests } from "../../tests/msw/server";

/** The route-level Suspense skeleton from RouteFallback. */
const ROUTE_SKELETON = ".animate-deferred-fade-in";

useApiMocks();
const { requests } = recordRequests();

describe("App - route code splitting", () => {
  it("renders the landing page without ever showing a route skeleton", async () => {
    // Signed out: the default session handler 401s and AuthProvider settles to
    // user = null.
    const { container } = render(<App />);

    await screen.findAllByText(/Solverah/i);

    // The assertion that matters. If LandingPage were lazy, React
    // would suspend on the way in and this fallback would have mounted.
    expect(container.querySelector(ROUTE_SKELETON)).toBeNull();
  });

  it("boots the whole app with a single request", async () => {
    // The same exit condition AuthContext.boot.test.tsx asserts, checked here
    // against the real router and the real route tree rather than a bare
    // provider — this is the closest a component test gets to what a browser
    // does on a cold load of `/`.
    render(<App />);
    await screen.findAllByText(/Solverah/i);

    expect(requests).toEqual(["GET /api/v1/auth/session"]);
  });

  it("renders the landing page while the session probe is still in flight", async () => {
    // The probe is held open by a gate the test releases. Everything asserted
    // before the release is what a visitor on a slow connection sees -- and it
    // must be the landing page, not a gate. This is 6.3's second defect,
    // asserted from the outside: public first paint stopped depending on
    // /auth/session the day AuthProvider's full-screen spinner was retired,
    // and this test fails if any render gate on the session comes back.
    let release!: () => void;
    const inFlight = new Promise<void>((resolve) => { release = resolve; });
    server.use(
      mock("get", "/api/v1/auth/session").resolve(async () => {
        await inFlight;
        return HttpResponse.json({ error: "Not authenticated" }, { status: 401 });
      }),
    );

    const { container } = render(<App />);

    // Phase one: the probe has not answered, and the landing page is already
    // on screen -- zero wait, with no route skeleton either (the entry route
    // is eager).
    await screen.findAllByText(/Solverah/i);
    expect(container.querySelector(ROUTE_SKELETON)).toBeNull();

    await act(async () => {
      release();
      await inFlight;
    });

    // Phase two: the probe settling changes nothing the visitor can see.
    expect(container.querySelector(ROUTE_SKELETON)).toBeNull();
    expect(screen.getAllByText(/Solverah/i).length).toBeGreaterThan(0);
  });
});
