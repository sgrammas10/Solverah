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
const AGENT = "POST /api/v1/agent/messages";

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

/**
 * `POST /agent/messages` that 401s the first *n* times and then streams.
 *
 * The one call site of `streamFetch`. The success body is `text/event-stream`,
 * not JSON -- which is why the agent chat cannot go through `fetchWithAuth`
 * and why this helper used to have no refresh at all: the access token aged
 * out after fifteen minutes and the first message after that failed, every
 * time, in any tab left open.
 */
function agentExpiresTimes(n: number) {
  let seen = 0;
  return mock("post", "/api/v1/agent/messages").resolve(({ request }) => {
    csrfHeaders.push(request.headers.get("X-CSRF-TOKEN"));
    seen += 1;
    if (seen <= n) {
      return HttpResponse.json({ error: "Token has expired" }, { status: 401 });
    }
    return new HttpResponse('data: {"chunk":"hi"}\n\ndata: {"done":true}\n\n', {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
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

/**
 * The same five properties, for `streamFetch`.
 *
 * `streamFetch` had none of this until the 2026-10-02 audit: it attached the
 * CSRF token and returned the raw response, and a 401 was handed straight to
 * the agent chat as a failed message. The fix shares one send-and-refresh core
 * with `fetchWithAuth` rather than copying it, and these tests are what hold
 * the two helpers to the same behaviour -- including the single-flight
 * promise, which they must share or two 401s across the two helpers would
 * present the same refresh token twice.
 *
 * One difference is deliberate and asserted: `streamFetch` returns the
 * response rather than parsing it, so a failure comes back as a non-ok
 * response, not a throw. That is what its caller already handles.
 */
describe("streamFetch — refresh then retry", () => {
  const post = (ctx: AuthContextType) =>
    ctx.streamFetch("/agent/messages", {
      method: "POST",
      body: JSON.stringify({ messages: [] }),
    });

  it("refreshes once and replays the request, returning the stream", async () => {
    const ctx = await mountSignedIn();
    server.use(agentExpiresTimes(1), refreshSucceeds());

    let res!: globalThis.Response;
    await act(async () => {
      res = await post(ctx);
    });

    expect(res.ok).toBe(true);
    expect(await res.text()).toContain('"chunk":"hi"');
    expect(requests).toEqual([AGENT, REFRESH, AGENT]);
  });

  it("sends the refreshed CSRF token on the replayed POST, not the stale one", async () => {
    // A streamed message is always a POST, so the replay is a CSRF-checked
    // request: the token from the refresh response has to reach it in the same
    // tick, which is why the token lives in a ref.
    const ctx = await mountSignedIn();
    server.use(agentExpiresTimes(1), refreshSucceeds("fresh-csrf"));

    await act(async () => {
      await post(ctx);
    });

    expect(csrfHeaders).toEqual(["stale-csrf", "fresh-csrf"]);
  });

  it("does not loop when the replay 401s again", async () => {
    const ctx = await mountSignedIn();
    server.use(agentExpiresTimes(99), refreshSucceeds());

    let res!: globalThis.Response;
    await act(async () => {
      res = await post(ctx);
    });

    expect(res.status).toBe(401);
    expect(requests).toEqual([AGENT, REFRESH, AGENT]);
  });

  it("does not replay when the refresh fails, and drops the local session", async () => {
    // Exactly what fetchWithAuth does on the same path: no second attempt, the
    // original 401 is what the caller sees, and the tab is signed out.
    const ctx = await mountSignedIn();
    expect(ctx.user).not.toBeNull();
    server.use(agentExpiresTimes(99)); // default refresh handler 401s

    let res!: globalThis.Response;
    await act(async () => {
      res = await post(ctx);
    });

    expect(res.status).toBe(401);
    expect(requests).toEqual([AGENT, REFRESH]);
    expect(ctx.user).toBeNull();
    expect(localStorage.getItem("solverah.hasSession")).toBeNull();
  });

  it("shares one refresh with a simultaneous fetchWithAuth 401", async () => {
    // The single-flight promise is the provider's, not the helper's. A
    // streamFetch and a fetchWithAuth 401 in the same instant must produce one
    // exchange or they present the same refresh token twice -- the exact
    // shape reuse detection exists to catch.
    const ctx = await mountSignedIn();
    server.use(agentExpiresTimes(1), profileExpiresTimes(1), refreshSucceeds());

    await act(async () => {
      await Promise.all([post(ctx), ctx.fetchWithAuth("/me/profile")]);
    });

    expect(requests.filter((r) => r === REFRESH)).toHaveLength(1);
    expect(requests.filter((r) => r === AGENT)).toHaveLength(2);
    expect(requests.filter((r) => r === PROFILE)).toHaveLength(2);
  });
});

describe("a failed refresh keeps per-user drafts", () => {
  it("drops the session but leaves the drafts in storage", async () => {
    // `refreshSession` resolves false on a network error as well as on a
    // revoked family, and this path cannot tell them apart. A connection blip
    // at submit therefore signs the tab out -- but must not cost the person
    // their in-progress answers. Only an explicit logout (and account
    // deletion) sweeps the drafts; see clearSessionLocally.
    const ctx = await mountSignedIn();
    sessionStorage.setItem("mm_answers", "{}");
    sessionStorage.setItem("solverah_assessment_answers", "{}");
    server.use(profileExpiresTimes(99));

    await act(async () => {
      await ctx.fetchWithAuth("/me/profile").catch(() => undefined);
    });

    expect(ctx.user).toBeNull();
    expect(sessionStorage.getItem("mm_answers")).toBe("{}");
    expect(sessionStorage.getItem("solverah_assessment_answers")).toBe("{}");
  });
});
