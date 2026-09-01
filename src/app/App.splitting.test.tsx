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
 *   2. The two loading states never overlap. AuthProvider's full-screen spinner
 *      and the route-level skeleton answer different questions, and chaining
 *      one behind the other in the same spot is the "stutter" this design was
 *      built to avoid.
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

/** The AuthProvider boot spinner, which has no accessible name to query by. */
const AUTH_SPINNER = ".animate-spin.rounded-full.h-32";
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

    // The assertion that matters. If PrelaunchLandingPage were lazy, React
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

  it("shows the auth spinner alone while the session is restoring", async () => {
    // The probe is held open by a gate the test releases, which is the MSW
    // equivalent of the never-resolving promise the fetch stub used to return.
    let release!: () => void;
    const inFlight = new Promise<void>((resolve) => { release = resolve; });
    server.use(
      mock("get", "/api/v1/auth/session").resolve(async () => {
        await inFlight;
        return HttpResponse.json({ error: "Not authenticated" }, { status: 401 });
      }),
    );

    const { container } = render(<App />);

    // Phase one: AuthProvider owns the viewport. The Router is not mounted, so
    // no route -- and therefore no route fallback -- can exist yet. This is the
    // structural reason the two spinners cannot collide.
    expect(container.querySelector(AUTH_SPINNER)).not.toBeNull();
    expect(container.querySelector(ROUTE_SKELETON)).toBeNull();

    await act(async () => {
      release();
      await inFlight;
    });
    await screen.findAllByText(/Solverah/i);

    // Phase two: the spinner is gone and the eager route is on screen. At no
    // point were both present.
    expect(container.querySelector(AUTH_SPINNER)).toBeNull();
    expect(container.querySelector(ROUTE_SKELETON)).toBeNull();
    expect(screen.getAllByText(/Solverah/i).length).toBeGreaterThan(0);
  });
});
