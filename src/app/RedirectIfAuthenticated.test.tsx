/**
 * RedirectIfAuthenticated.test.tsx — the entry-surface gate, on the wire.
 *
 * The regression this file exists for: a returning visitor with a live session
 * opened solverah.com and got the signed-out landing page; on /login the
 * global Header showed their name over the sign-in form. The first test is
 * that scenario end to end — and it is a statement about a *window*, the same
 * way RequireAuth.test.tsx's first test is: between mount and the session
 * probe resolving, a returning visitor must see neither the landing page (the
 * flash) nor the dashboard (the session is not known yet). The probe is held
 * open with a gate so the held-open state can be asserted on directly.
 *
 * The probe is real: MSW serves `GET /auth/session`, AuthProvider issues it,
 * and the gate reads the context. Nothing mocks `useAuth`, because the thing
 * under test is the handshake between `sessionLoading`, the session hint in
 * localStorage, and the boundary that consumes both.
 *
 * `localStorage` is part of the fixture: the `solverah.hasSession` hint is
 * what separates "returning visitor, hold the page" from "first visit, draw it
 * now", and it is cleared before every test.
 */
import { render, screen, act, fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { HttpResponse } from "msw";

import { RedirectIfAuthenticated } from "./RedirectIfAuthenticated";
// Extension spelled out for the same case-insensitive-filesystem reason as in
// AuthContext.boot.test.tsx: "../AuthContext" would resolve to authContext.ts.
import { AuthProvider } from "../features/auth/AuthContext.tsx";
import { useAuth } from "../features/auth/useAuth";
import { createQueryClient } from "../shared/api/queryClient";
import { mock } from "../../tests/msw/contract";
import { server, useApiMocks, signedIn, loginSucceeds, TEST_USER, NO_FLAGS } from "../../tests/msw/server";

useApiMocks();

/** The RouteFallback skeleton the gate holds a returning visitor behind. */
const ROUTE_SKELETON = ".animate-deferred-fade-in";
const SESSION_HINT_KEY = "solverah.hasSession";

beforeEach(() => localStorage.clear());

/** Stands in for the Login page: signs in through the real AuthProvider and
 *  reports what the context says, so the test can see whether the boundary
 *  let the page keep the screen after its own sign-in. */
function SignInProbe() {
  const { login, user } = useAuth();
  return (
    <div>
      <div>{user ? `signed in as ${user.name}` : "sign-in page"}</div>
      <button onClick={() => void login("ada@example.com", "pass")}>sign in</button>
    </div>
  );
}

function mountAt(path: string) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route element={<RedirectIfAuthenticated />}>
              <Route path="/" element={<div>landing page</div>} />
              <Route path="/login" element={<SignInProbe />} />
            </Route>
            <Route path="/job-seeker/dashboard" element={<div>dashboard</div>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

/**
 * Replace the session handler with one held open until the test releases it.
 * Returns the release function; the response is then the given verdict.
 */
function gateSessionProbe(answer: "signed-in" | "signed-out"): () => void {
  let release!: () => void;
  const inFlight = new Promise<void>((resolve) => { release = resolve; });
  server.use(
    mock("get", "/api/v1/auth/session").resolve(async () => {
      await inFlight;
      if (answer === "signed-out") {
        return HttpResponse.json({ error: "Not authenticated" }, { status: 401 });
      }
      return HttpResponse.json({
        user: TEST_USER,
        csrf_token: "test-csrf-token",
        flags: NO_FLAGS,
      });
    }),
  );
  return release;
}

describe("RedirectIfAuthenticated - a returning visitor with a live session", () => {
  it("holds the landing page back while the probe is in flight, then lands on the dashboard", async () => {
    localStorage.setItem(SESSION_HINT_KEY, "1");
    const release = gateSessionProbe("signed-in");

    const { container } = mountAt("/");

    // A settled tick with the probe still open: what is on screen now is what
    // a slow network shows the user. It must be the skeleton -- not the
    // landing page (the flash), and not the dashboard (not known yet).
    await act(async () => {});
    expect(screen.queryByText("landing page")).toBeNull();
    expect(screen.queryByText("dashboard")).toBeNull();
    expect(container.querySelector(ROUTE_SKELETON)).not.toBeNull();

    await act(async () => { release(); });

    expect(await screen.findByText("dashboard")).toBeInTheDocument();
    expect(screen.queryByText("landing page")).toBeNull();
    expect(container.querySelector(ROUTE_SKELETON)).toBeNull();
  });

  it("sends them from /login to the dashboard instead of drawing the sign-in form", async () => {
    localStorage.setItem(SESSION_HINT_KEY, "1");
    server.use(signedIn());

    mountAt("/login");

    expect(await screen.findByText("dashboard")).toBeInTheDocument();
    expect(screen.queryByText("sign-in page")).toBeNull();
  });

  it("renders the page once the probe says the remembered session is gone", async () => {
    localStorage.setItem(SESSION_HINT_KEY, "1");
    const release = gateSessionProbe("signed-out");

    const { container } = mountAt("/");

    await act(async () => {});
    expect(container.querySelector(ROUTE_SKELETON)).not.toBeNull();
    expect(screen.queryByText("landing page")).toBeNull();

    await act(async () => { release(); });

    expect(await screen.findByText("landing page")).toBeInTheDocument();
    expect(screen.queryByText("dashboard")).toBeNull();
    expect(container.querySelector(ROUTE_SKELETON)).toBeNull();
  });
});

describe("RedirectIfAuthenticated - a first visit", () => {
  it("draws the landing page immediately, without waiting on the probe", async () => {
    // No hint: this browser has never signed in. The probe is held open for
    // the whole test -- the page must not be waiting on it.
    gateSessionProbe("signed-out");

    const { container } = mountAt("/");

    expect(screen.getByText("landing page")).toBeInTheDocument();
    expect(container.querySelector(ROUTE_SKELETON)).toBeNull();

    await act(async () => {});
    expect(screen.getByText("landing page")).toBeInTheDocument();
  });

  it("still redirects when a probe the hint did not predict reports a session", async () => {
    // Hint lost (cleared site data) but the cookies survived: the page draws
    // first, and the late verdict still moves the visitor on.
    server.use(signedIn());

    mountAt("/");

    expect(screen.getByText("landing page")).toBeInTheDocument();
    expect(await screen.findByText("dashboard")).toBeInTheDocument();
    expect(screen.queryByText("landing page")).toBeNull();
  });
});

describe("RedirectIfAuthenticated - a sign-in completed on the page", () => {
  it("is not pre-empted: the page keeps the screen and owns the navigation", async () => {
    // The default probe 401s; the visitor signs in through the page itself.
    // The boundary's verdict was "page" the moment the probe answered, and a
    // session appearing afterwards must not flip it -- Login's onSuccess is
    // the one that decides where to go (return-to-origin, pending quiz).
    server.use(loginSucceeds());

    mountAt("/login");

    expect(await screen.findByText("sign-in page")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "sign in" }));
    });

    expect(await screen.findByText("signed in as Ada Lovelace")).toBeInTheDocument();
    expect(screen.queryByText("dashboard")).toBeNull();
  });
});
