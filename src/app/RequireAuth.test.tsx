/**
 * RequireAuth.test.tsx — the session gate at the route boundary, on the wire.
 *
 * The central test is the first one, and it is a statement about a *window*:
 * between mount and the session probe resolving, a protected route must show
 * neither its content (a flash of protected UI at a visitor who may be signed
 * out) nor the sign-in page (a signed-in user bounced to /login on every hard
 * refresh of a protected screen). Both failure modes are one deleted branch
 * away — treat "still loading" as "signed out" and you redirect early; treat
 * it as "signed in" and you flash — so the test holds the probe open with a
 * gate and asserts on the held-open state directly, then releases it and
 * asserts the gate resolves the right way.
 *
 * The probe is real: MSW serves `GET /auth/session`, AuthProvider issues it,
 * and RequireAuth reads the context. Nothing here mocks `useAuth`, because the
 * thing under test is precisely the handshake between the provider's
 * `sessionLoading` and the boundary that consumes it.
 */
import { render, screen, act } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { HttpResponse } from "msw";

import { RequireAuth } from "./RequireAuth";
// Extension spelled out for the same case-insensitive-filesystem reason as in
// AuthContext.boot.test.tsx: "../AuthContext" would resolve to authContext.ts.
import { AuthProvider } from "../features/auth/AuthContext.tsx";
import { createQueryClient } from "../shared/api/queryClient";
import { mock } from "../../tests/msw/contract";
import { server, useApiMocks, signedIn, TEST_USER, NO_FLAGS } from "../../tests/msw/server";

useApiMocks();

/** The RouteFallback skeleton RequireAuth holds the subtree open with. */
const ROUTE_SKELETON = ".animate-deferred-fade-in";

function mountAt(path: string, allowedRoles: string[] = ["job-seeker"]) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/" element={<div>home page</div>} />
            <Route path="/login" element={<div>sign-in page</div>} />
            <Route element={<RequireAuth allowedRoles={allowedRoles} />}>
              <Route path="/guarded" element={<div>protected content</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

/**
 * Replace the session handler with one held open until the test releases it.
 * Returns the release function; the response is then a signed-in 200.
 */
function gateSessionProbe(): () => void {
  let release!: () => void;
  const inFlight = new Promise<void>((resolve) => { release = resolve; });
  server.use(
    mock("get", "/api/v1/auth/session").resolve(async () => {
      await inFlight;
      return HttpResponse.json({
        user: TEST_USER,
        csrf_token: "test-csrf-token",
        flags: NO_FLAGS,
      });
    }),
  );
  return release;
}

describe("RequireAuth - while the session probe is in flight", () => {
  it("shows neither the protected content nor the sign-in redirect until the probe resolves", async () => {
    const release = gateSessionProbe();

    const { container } = mountAt("/guarded");

    // A settled tick with the probe still open: whatever is on screen now is
    // what a slow network shows the user. It must be the loading boundary --
    // not the content, and not /login.
    await act(async () => {});
    expect(screen.queryByText("protected content")).toBeNull();
    expect(screen.queryByText("sign-in page")).toBeNull();
    expect(container.querySelector(ROUTE_SKELETON)).not.toBeNull();

    await act(async () => { release(); });

    // The probe answered signed-in, so the held-back subtree renders. The
    // sign-in page never appeared at any point in between.
    expect(await screen.findByText("protected content")).toBeInTheDocument();
    expect(screen.queryByText("sign-in page")).toBeNull();
    expect(container.querySelector(ROUTE_SKELETON)).toBeNull();
  });
});

describe("RequireAuth - once the session is known", () => {
  it("redirects a signed-out visitor to /login", async () => {
    // The default handler 401s: an anonymous visitor deep-linking to a
    // protected route.
    mountAt("/guarded");

    expect(await screen.findByText("sign-in page")).toBeInTheDocument();
    expect(screen.queryByText("protected content")).toBeNull();
  });

  it("renders the guarded route for a signed-in user with an allowed role", async () => {
    server.use(signedIn());

    mountAt("/guarded");

    expect(await screen.findByText("protected content")).toBeInTheDocument();
  });

  it("redirects a signed-in user whose role is not allowed to /", async () => {
    // The fixture's role is job-seeker; guard the route for someone else.
    server.use(signedIn());

    mountAt("/guarded", ["recruiter"]);

    expect(await screen.findByText("home page")).toBeInTheDocument();
    expect(screen.queryByText("protected content")).toBeNull();
  });
});
