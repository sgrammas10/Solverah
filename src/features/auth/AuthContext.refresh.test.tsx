/**
 * AuthContext.refresh.test.tsx — the client half of refresh-token rotation.
 *
 * The server rotates refresh tokens on use and treats a retired token presented
 * again as evidence of theft: it revokes the whole family and the user is signed
 * out (solverah/services/refresh_tokens.py). That rule is correct and it has an
 * obvious way to fire on innocent traffic — two queries hitting a 401 at the
 * same instant, both presenting the same cookie. The server carries a short
 * grace window for it; this file is the other half, and the more important one,
 * because the grace window is a safety net and single-flight is the thing that
 * means it is rarely needed.
 *
 * Counted on the network rather than on a `vi.fn()` over `fetch`, for the reason
 * `AuthContext.boot.test.tsx` gives: "exactly one refresh" is a claim about what
 * the browser sends, and a spy counts calls rather than requests.
 *
 * What is asserted here, and why each one is a separate failure:
 *
 *   - a 401 refreshes and replays the request **once**;
 *   - N simultaneous 401s produce **one** POST /auth/refresh;
 *   - the replay carries the **new** CSRF token, not the stale one;
 *   - a failed refresh does **not** replay, and drops the local session;
 *   - a second 401 after a successful refresh surfaces as an error rather than
 *     starting a loop.
 *
 * The last is the one a naive implementation gets wrong in the most damaging
 * way: a retry that re-enters the refresh path turns one expired family into an
 * unbounded storm against the auth endpoint from every open tab.
 */
import { render, screen, waitFor, act } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { HttpResponse } from "msw";

import { AuthProvider } from "./AuthContext.tsx";
import { useAuth } from "./useAuth";
import type { AuthContextType } from "./authContext";
import { createQueryClient } from "../../shared/api/queryClient";
import { mock } from "../../../tests/msw/contract";
import {
  server,
  useApiMocks,
  recordRequests,
  signedIn,
  refreshSucceeds,
} from "../../../tests/msw/server";

useApiMocks();
const { requests } = recordRequests();

beforeEach(() => localStorage.clear());

const REFRESH = "POST /api/v1/auth/refresh";
const PROFILE = "GET /api/v1/me/profile";
const ME = "GET /api/v1/me";

/** Every X-CSRF-TOKEN header seen, in request order. */
const csrfHeaders: (string | null)[] = [];
beforeEach(() => {
  csrfHeaders.length = 0;
});

/**
 * `GET /me/profile` that 401s the first *n* times and then succeeds.
 *
 * The shape of an access token that aged out mid-session: the endpoint is fine,
 * the credential is not, and it is fine again once the credential is renewed.
 */
function profileExpiresTimes(n: number) {
  let seen = 0;
  return mock("get", "/api/v1/me/profile").resolve(({ request }) => {
    csrfHeaders.push(request.headers.get("X-CSRF-TOKEN"));
    seen += 1;
    if (seen <= n) {
      return HttpResponse.json({ error: "Token has expired" }, { status: 401 });
    }
    return HttpResponse.json({ profile: { firstName: "Ada" } });
  });
}

/** `GET /me` that 401s once and then succeeds — a second endpoint to race with. */
function meExpiresOnce() {
  let seen = 0;
  return mock("get", "/api/v1/me").resolve(() => {
    seen += 1;
    if (seen === 1) {
      return HttpResponse.json({ error: "Token has expired" }, { status: 401 });
    }
    return HttpResponse.json({
      id: 1,
      email: "ada@example.com",
      name: "Ada Lovelace",
      role: "job-seeker",
    });
  });
}

/** Mount a signed-in provider and hand back its context. */
async function mountSignedIn() {
  server.use(signedIn({ csrfToken: "stale-csrf" }));

  const ctxRef = { current: null as AuthContextType | null };

  function Probe() {
    const ctx = useAuth();
    ctxRef.current = ctx;
    if (ctx.sessionLoading) return null;
    return <span data-testid="ready">{ctx.user ? ctx.user.email : "anonymous"}</span>;
  }

  render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>,
  );

  await waitFor(() => screen.getByTestId("ready"));
  requests.length = 0;
  return new Proxy({} as AuthContextType, {
    get: (_t, prop: string | symbol) => (ctxRef.current as never)[prop as never],
  });
}

describe("fetchWithAuth — refresh then retry", () => {
  it("refreshes once and replays the request", async () => {
    const ctx = await mountSignedIn();
    server.use(profileExpiresTimes(1), refreshSucceeds());

    let body: unknown;
    await act(async () => {
      body = await ctx.fetchWithAuth("/me/profile");
    });

    expect(body).toEqual({ profile: { firstName: "Ada" } });
    expect(requests).toEqual([PROFILE, REFRESH, PROFILE]);
  });

  it("sends the refreshed CSRF token on the replay, not the stale one", async () => {
    // The reason the token lives in a ref rather than in state: the replay
    // happens in the same tick as the refresh, and a setState is not visible
    // to the closure that has to attach the header.
    const ctx = await mountSignedIn();
    server.use(profileExpiresTimes(1), refreshSucceeds("fresh-csrf"));

    await act(async () => {
      await ctx.fetchWithAuth("/me/profile", { method: "GET" });
    });

    // GETs carry no CSRF header at all, so assert through a mutating call.
    csrfHeaders.length = 0;
    server.use(
      mock("patch", "/api/v1/me/profile").resolve(async ({ request }) => {
        csrfHeaders.push(request.headers.get("X-CSRF-TOKEN"));
        return HttpResponse.json({ profile: {} });
      }),
    );
    await act(async () => {
      await ctx.fetchWithAuth("/me/profile", {
        method: "PATCH",
        body: JSON.stringify({ profile: {} }),
      });
    });

    expect(csrfHeaders).toEqual(["fresh-csrf"]);
  });

  it("issues ONE refresh for two simultaneous 401s", async () => {
    // The stampede. Two queries, two 401s, one exchange -- because the second
    // caller awaits the first one's promise instead of presenting the same
    // refresh token a second time and looking exactly like theft.
    const ctx = await mountSignedIn();
    server.use(profileExpiresTimes(1), meExpiresOnce(), refreshSucceeds());

    await act(async () => {
      await Promise.all([
        ctx.fetchWithAuth("/me/profile"),
        ctx.fetchWithAuth("/me"),
      ]);
    });

    expect(requests.filter((r) => r === REFRESH)).toHaveLength(1);
    // Both requests were replayed, so both callers got their answer.
    expect(requests.filter((r) => r === PROFILE)).toHaveLength(2);
    expect(requests.filter((r) => r === ME)).toHaveLength(2);
  });

  it("does not loop when the replay 401s again", async () => {
    // One refresh, two attempts, then the error surfaces. A retry that
    // re-entered the refresh path would spin here forever.
    const ctx = await mountSignedIn();
    server.use(profileExpiresTimes(99), refreshSucceeds());

    await expect(
      act(async () => {
        await ctx.fetchWithAuth("/me/profile");
      }),
    ).rejects.toThrow();

    expect(requests).toEqual([PROFILE, REFRESH, PROFILE]);
  });

  it("does not replay when the refresh itself fails", async () => {
    // The family is gone -- logged out elsewhere, or reuse detection fired.
    // There is nothing to retry with, and the original error is the honest one
    // to surface.
    const ctx = await mountSignedIn();
    server.use(profileExpiresTimes(99));  // default refresh handler 401s

    await expect(
      act(async () => {
        await ctx.fetchWithAuth("/me/profile");
      }),
    ).rejects.toThrow();

    expect(requests).toEqual([PROFILE, REFRESH]);
  });

  it("drops the local session when the refresh fails", async () => {
    // Same cache hygiene as logout, and for the same reason: every cached query
    // belongs to the session that just ended. There is no request to make --
    // the thing that would authenticate one is exactly what is gone.
    const ctx = await mountSignedIn();
    expect(ctx.user).not.toBeNull();
    server.use(profileExpiresTimes(99));

    await act(async () => {
      await ctx.fetchWithAuth("/me/profile").catch(() => undefined);
    });

    expect(ctx.user).toBeNull();
    expect(localStorage.getItem("solverah.hasSession")).toBeNull();
  });

  it("a later 401 can refresh again once the first exchange has settled", async () => {
    // Single-flight is per-exchange, not once-per-session: the ref is cleared
    // when the promise settles. Without that a session would get exactly one
    // refresh and then expire for good fifteen minutes later.
    const ctx = await mountSignedIn();
    server.use(profileExpiresTimes(1), refreshSucceeds());

    await act(async () => {
      await ctx.fetchWithAuth("/me/profile");
    });
    server.use(meExpiresOnce());
    await act(async () => {
      await ctx.fetchWithAuth("/me");
    });

    expect(requests.filter((r) => r === REFRESH)).toHaveLength(2);
  });
});
