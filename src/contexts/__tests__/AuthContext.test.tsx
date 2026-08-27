import { render, screen, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "../AuthContext.tsx";
import { useAuth } from "../useAuth";
import type { AuthContextType, ProfileData } from "../authContext";
import { profileKeys, useProfile } from "../../hooks/useProfile";
import { createQueryClient } from "../../utils/queryClient";

const mockFetch = vi.fn();
globalThis.fetch = mockFetch as any;

beforeEach(() => {
  mockFetch.mockReset();
});

/**
 * A `GET /api/v1/auth/session` body.
 *
 * Phase 1b split `GET /api/profile` into the session probe and `/me/profile`.
 * The probe answers identity, the CSRF token and the completion flags, and
 * writes nothing -- the old endpoint returned the whole user document and
 * committed an audit row on every page load (P0-3).
 */
function sessionBody(overrides: Record<string, any> = {}) {
  return {
    user: { id: "1", email: "ada@example.com", name: "Ada", role: "job-seeker" },
    csrf_token: null,
    flags: {
      email_confirmed: true,
      wpl_completed: false,
      wpll_completed: false,
      wp_v2_completed: false,
    },
    ...overrides,
  };
}

/**
 * Index of the first fetch a test makes after the restore has settled.
 *
 * Phase 4a took the restore down to a single request -- the profile document
 * moved to its own query -- so anything a test does afterwards starts at call 1.
 * Named rather than written as a literal because getting it wrong reads as an
 * assertion about the wrong request.
 */
const FIRST_CALL_AFTER_RESTORE = 1;

/** The client the most recent `mountAuth` rendered with, for cache assertions. */
let currentClient: QueryClient;

/** Whatever is cached under the profile document key right now. */
function cachedProfile(): ProfileData | undefined {
  return currentClient.getQueryData<ProfileData>(profileKeys.document());
}

// Renders AuthProvider and waits for the loading phase to finish.
// Returns the captured context value once the Probe component mounts.
async function mountAuth(sessionResponse: {
  ok: boolean;
  data?: any;
  profile?: any;
  client?: QueryClient;
}) {
  // One response: the session probe. The restore no longer fetches the profile.
  mockFetch.mockResolvedValueOnce({
    ok: sessionResponse.ok,
    json: () => Promise.resolve(sessionResponse.data ?? {}),
  });

  // Retries off and gcTime zero: a test asserting on a rejected query should see
  // the failure on the first attempt rather than after the default backoff.
  //
  // `client` overrides that for the cases where those defaults are the wrong
  // instrument. gcTime zero collects an observer-less cache entry on the next
  // macrotask, so a test that asserts on cached data across an extra await is
  // racing the collector; and staleTime zero refetches even a seeded query,
  // which hides the suppression the seed guard exists to prevent. Those pass
  // `createQueryClient()` -- the client the app actually runs on.
  currentClient = sessionResponse.client ?? new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  if (sessionResponse.profile !== undefined) {
    currentClient.setQueryData(profileKeys.document(), sessionResponse.profile);
  }

  const ctxRef = { current: null as AuthContextType | null };

  function Probe() {
    const ctx = useAuth();
    ctxRef.current = ctx;
    return <span data-testid="ready" />;
  }

  render(
    <QueryClientProvider client={currentClient}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>
  );

  await waitFor(() => screen.getByTestId("ready"));
  return new Proxy({} as AuthContextType, {
    get(_, prop: string | symbol) {
      return (ctxRef.current as any)[prop as string];
    },
  });
}

// ─── Session restore ──────────────────────────────────────────────────────────

describe("AuthProvider - session restore", () => {
  it("sets user from a successful session probe", async () => {
    const ctx = await mountAuth({
      ok: true,
      data: sessionBody(),
    });
    expect(ctx.user?.email).toBe("ada@example.com");
  });

  it("stores the CSRF token from the response body", async () => {
    const ctx = await mountAuth({
      ok: true,
      data: sessionBody({ csrf_token: "tok-abc" }),
    });
    // We verify CSRF is stored by checking it gets attached to a subsequent POST
    mockFetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ ok: true }) });
    await act(async () => {
      await ctx.fetchWithAuth("/some-endpoint", { method: "POST" });
    });
    const postHeaders = mockFetch.mock.calls[FIRST_CALL_AFTER_RESTORE][1].headers;
    expect(postHeaders["X-CSRF-TOKEN"]).toBe("tok-abc");
  });

  it("sets user to null when the session probe fails", async () => {
    const ctx = await mountAuth({ ok: false, data: { error: "Unauthorized" } });
    expect(ctx.user).toBeNull();
  });

  it("sets user to null on network error", async () => {
    mockFetch.mockRejectedValueOnce(new Error("Network error"));
    const ctxRef = { current: null as AuthContextType | null };

    function Probe() {
      const ctx = useAuth();
      ctxRef.current = ctx;
      return <span data-testid="ready" />;
    }

    render(
      <QueryClientProvider client={new QueryClient()}>
        <AuthProvider><Probe /></AuthProvider>
      </QueryClientProvider>
    );
    await waitFor(() => screen.getByTestId("ready"));
    expect(ctxRef.current!.user).toBeNull();
  });
});

// ─── login ────────────────────────────────────────────────────────────────────

describe("AuthProvider - login", () => {
  it("sets user on successful login", async () => {
    const ctx = await mountAuth({ ok: false });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        user: { id: "2", email: "ada@example.com", name: "Ada", role: "job-seeker", profileComplete: false },
        csrfToken: "tok-login",
      }),
    });

    let user: any;
    await act(async () => {
      user = await ctx.login("ada@example.com", "password123");
    });

    expect(user.email).toBe("ada@example.com");
    expect(ctx.user?.email).toBe("ada@example.com");
  });

  it("throws with server error message on failed login", async () => {
    const ctx = await mountAuth({ ok: false });

    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({ error: "email not confirmed" }),
    });

    await expect(
      act(async () => { await ctx.login("ada@example.com", "wrong"); })
    ).rejects.toThrow("email not confirmed");
  });
});

// ─── logout ───────────────────────────────────────────────────────────────────

describe("AuthProvider - logout", () => {
  it("clears user and CSRF token on successful logout", async () => {
    const ctx = await mountAuth({
      ok: true,
      data: sessionBody({ csrf_token: "tok-abc" }),
    });

    // Mock the logout POST
    mockFetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({}) });

    await act(async () => { await ctx.logout(); });

    expect(ctx.user).toBeNull();
  });

  it("still clears user even when the logout request fails", async () => {
    const ctx = await mountAuth({
      ok: true,
      data: sessionBody(),
    });

    mockFetch.mockRejectedValueOnce(new Error("Network error"));

    await act(async () => { await ctx.logout(); });

    expect(ctx.user).toBeNull();
  });
});

// ─── fetchWithAuth ────────────────────────────────────────────────────────────

describe("AuthProvider - fetchWithAuth", () => {
  it("attaches X-CSRF-TOKEN header on POST requests", async () => {
    const ctx = await mountAuth({
      ok: true,
      data: sessionBody({ user: { id: "1", email: "a@b.com", name: "A", role: "job-seeker" }, csrf_token: "csrf-123" }),
    });

    mockFetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ ok: true }) });

    await act(async () => {
      await ctx.fetchWithAuth("/save", { method: "POST" });
    });

    const headers = mockFetch.mock.calls[FIRST_CALL_AFTER_RESTORE][1].headers;
    expect(headers["X-CSRF-TOKEN"]).toBe("csrf-123");
  });

  it("does not attach X-CSRF-TOKEN on GET requests", async () => {
    const ctx = await mountAuth({
      ok: true,
      data: sessionBody({ user: { id: "1", email: "a@b.com", name: "A", role: "job-seeker" }, csrf_token: "csrf-123" }),
    });

    mockFetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ data: "ok" }) });

    await act(async () => {
      await ctx.fetchWithAuth("/me/profile", { method: "GET" });
    });

    const headers = mockFetch.mock.calls[FIRST_CALL_AFTER_RESTORE][1].headers;
    expect(headers["X-CSRF-TOKEN"]).toBeUndefined();
  });

  it("throws with the server error message on non-2xx response", async () => {
    const ctx = await mountAuth({ ok: false });

    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({ error: "Not authorised" }),
    });

    await expect(
      act(async () => { await ctx.fetchWithAuth("/protected", { method: "GET" }); })
    ).rejects.toThrow("Not authorised");
  });

  it("throws when the response body is null", async () => {
    const ctx = await mountAuth({ ok: false });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(null),
    });

    await expect(
      act(async () => { await ctx.fetchWithAuth("/endpoint", { method: "GET" }); })
    ).rejects.toThrow("Unexpected response from server");
  });

  it("always includes credentials: include", async () => {
    const ctx = await mountAuth({ ok: false });
    mockFetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ ok: true }) });

    await act(async () => { await ctx.fetchWithAuth("/anything"); });

    expect(mockFetch.mock.calls[FIRST_CALL_AFTER_RESTORE][1].credentials).toBe("include");
  });
});

// ─── updateProfile / updateProfileData ───────────────────────────────────────

describe("AuthProvider - optimistic updates", () => {
  it("updateProfile patches the in-memory user", async () => {
    const ctx = await mountAuth({
      ok: true,
      data: sessionBody(),
    });

    act(() => { ctx.updateProfile({ profileComplete: true }); });

    expect(ctx.user?.profileComplete).toBe(true);
  });

  it("updateProfileData merges into the cached profile document", async () => {
    const ctx = await mountAuth({
      ok: true,
      data: sessionBody(),
      profile: { firstName: "Ada" },
    });

    act(() => { ctx.updateProfileData({ lastName: "Lovelace" } as any); });

    // The merge target moved from `user.profileData` to the query cache in
    // Phase 4a. The contract is otherwise unchanged: a shallow merge that
    // preserves keys it was not given.
    expect((cachedProfile() as any)?.lastName).toBe("Lovelace");
    expect((cachedProfile() as any)?.firstName).toBe("Ada");
  });
});

// -- The boot path ------------------------------------------------------------

describe("AuthProvider - session restore issues one request", () => {
  /**
   * The exit condition for Phase 4a, asserted directly.
   *
   * The restore used to Promise.all the session probe with GET /me/profile,
   * because `User` carried `profileData` and six components read it off the user
   * object. Both are gone, and this fails if either comes back: the second
   * request was a read of data the app shell does not render, on the critical
   * path of every page load (P0-3).
   */
  it("calls /auth/session and nothing else", async () => {
    await mountAuth({ ok: true, data: sessionBody() });

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(String(mockFetch.mock.calls[0][0])).toContain("/auth/session");
  });

  it("does not fetch the profile document on boot", async () => {
    await mountAuth({ ok: true, data: sessionBody() });

    const urls = mockFetch.mock.calls.map((call: any[]) => String(call[0]));
    expect(urls.some((url) => url.includes("/me/profile"))).toBe(false);
  });

  it("leaves the profile cache untouched by the restore", async () => {
    await mountAuth({ ok: true, data: sessionBody() });

    // Nothing seeded it, and boot must not: the document is fetched by the
    // screens that render it, through useProfile().
    expect(cachedProfile()).toBeUndefined();
  });
});

// -- login seeds the profile cache --------------------------------------------

describe("AuthProvider - login and the profile cache", () => {
  /**
   * `POST /auth/login` still returns the profile document inside its user
   * envelope (SessionUser in solverah/schemas/auth.py). Dropping the boot fetch
   * would only move that request to the first screen that renders the document
   * unless the login response is written through to the cache.
   */
  it("seeds the cached profile document from the login response", async () => {
    const ctx = await mountAuth({ ok: false });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        user: {
          id: "2", email: "ada@example.com", name: "Ada", role: "job-seeker",
          profileComplete: false,
          profileData: { firstName: "Ada", skills: ["Python"] },
        },
        csrfToken: "tok-login",
      }),
    });

    await act(async () => { await ctx.login("ada@example.com", "password123"); });

    expect(cachedProfile()).toEqual({ firstName: "Ada", skills: ["Python"] });
  });

  it("keeps profileData off the User object", async () => {
    const ctx = await mountAuth({ ok: false });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        user: {
          id: "2", email: "ada@example.com", name: "Ada", role: "job-seeker",
          profileComplete: false,
          profileData: { firstName: "Ada" },
        },
        csrfToken: "tok-login",
      }),
    });

    let returned: any;
    await act(async () => { returned = await ctx.login("ada@example.com", "password123"); });

    expect(returned).not.toHaveProperty("profileData");
    expect(ctx.user).not.toHaveProperty("profileData");
  });
});

// -- logout clears cached server state -----------------------------------------

describe("AuthProvider - logout drops the cached profile", () => {
  it("removes the profile document so it cannot outlive the session", async () => {
    const ctx = await mountAuth({
      ok: true,
      data: sessionBody(),
      profile: { firstName: "Ada" },
    });
    expect(cachedProfile()).toEqual({ firstName: "Ada" });

    mockFetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({}) });
    await act(async () => { await ctx.logout(); });

    // A second sign-in on this tab must not see the first user's document.
    expect(cachedProfile()).toBeUndefined();
  });
});


// -- login without a profile document -----------------------------------------

describe("AuthProvider - login when the envelope carries no profileData", () => {
  /**
   * `splitLoginUser` returns `undefined` for a user envelope with no
   * profileData, and `seedProfileCache` turns `undefined` into the empty
   * document. That is a resolved cache entry, not a missing one, so the query
   * is fresh for the whole staleTime window and the first real fetch never
   * goes out -- consumers that branch on the document (FocusTypeResultsPage,
   * PathIntelligencePage) navigate away from results that exist on the server.
   *
   * `POST /auth/login` folds profileData in today, so this is latent. It stops
   * being latent the moment `auth_service` stops folding it in, which is why
   * this asserts the guard rather than the envelope.
   */
  it("leaves the cached document unseeded rather than resolving it empty", async () => {
    // The app's client, not the gcTime-zero default: an unguarded seed writes
    // `{}` and gcTime zero would collect it before the assertion runs, so the
    // test would pass against the very bug it is here to catch.
    const ctx = await mountAuth({ ok: false, client: createQueryClient() });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        user: {
          id: "2", email: "ada@example.com", name: "Ada", role: "job-seeker",
          profileComplete: false,
        },
        csrfToken: "tok-login",
      }),
    });

    await act(async () => { await ctx.login("ada@example.com", "password123"); });

    // `undefined`, not `{}`. Only the former makes useProfile() fetch.
    expect(cachedProfile()).toBeUndefined();
  });

  /**
   * The consequence, end to end.
   *
   * Built on `createQueryClient()` rather than the bare client `mountAuth`
   * makes: the suppression is staleTime-dependent, and TanStack's default of
   * zero would refetch even a seeded query, hiding the bug this guards.
   */
  it("lets useProfile fetch the document under the app's real staleTime", async () => {
    const client = createQueryClient();

    // Restore fails -- nobody is signed in, so useProfile stays disabled until
    // login() sets the user.
    mockFetch.mockResolvedValueOnce({ ok: false, json: () => Promise.resolve({}) });

    const ctxRef = { current: null as AuthContextType | null };

    function Probe() {
      ctxRef.current = useAuth();
      const { data } = useProfile();
      return <span data-testid="ready">{data ? JSON.stringify(data) : "no-data"}</span>;
    }

    render(
      <QueryClientProvider client={client}>
        <AuthProvider><Probe /></AuthProvider>
      </QueryClientProvider>
    );
    await waitFor(() => screen.getByTestId("ready"));

    // A login envelope with no profileData: the shape this path sees if the
    // response stops carrying the field.
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        user: { id: "2", email: "ada@example.com", name: "Ada", role: "job-seeker" },
        csrfToken: "tok-login",
      }),
    });
    // ...and the GET useProfile must then make to get the real document.
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ profile: { firstName: "Ada", skills: ["Python"] } }),
    });

    await act(async () => {
      await ctxRef.current!.login("ada@example.com", "password123");
    });

    // Seeding `{}` would leave this reading "{}" for 60s and never request it.
    await waitFor(() => {
      expect(screen.getByTestId("ready").textContent).toContain("Ada");
    });

    const urls = mockFetch.mock.calls.map((call: any[]) => String(call[0]));
    expect(urls.some((url) => url.includes("/me/profile"))).toBe(true);
  });
});

// -- saveProfileData writes back the server's copy ----------------------------

describe("AuthProvider - saveProfileData and the cache", () => {
  it("replaces the cached document with the server's copy of the merge", async () => {
    const ctx = await mountAuth({
      ok: true,
      data: sessionBody(),
      profile: { firstName: "Ada" },
      client: createQueryClient(),
    });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ profile: { firstName: "Ada", lastName: "Lovelace" } }),
    });

    await act(async () => { await ctx.saveProfileData({ lastName: "Lovelace" } as any); });

    // The server's copy, so anything the write allowlist dropped or normalised
    // is what consumers see next.
    expect(cachedProfile()).toEqual({ firstName: "Ada", lastName: "Lovelace" });
  });

  it("writes through a present-but-empty document", async () => {
    const ctx = await mountAuth({
      ok: true,
      data: sessionBody(),
      profile: { firstName: "Ada" },
      client: createQueryClient(),
    });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ profile: {} }),
    });

    await act(async () => { await ctx.saveProfileData({} as any); });

    // A present `{}` is the server describing the document it just wrote, not a
    // response that failed to carry one. It is authoritative.
    expect(cachedProfile()).toEqual({});
  });

  it("does not clobber the cached document when the response carries no profile", async () => {
    const ctx = await mountAuth({
      ok: true,
      data: sessionBody(),
      profile: { firstName: "Ada", skills: ["Python"] },
      client: createQueryClient(),
    });

    // No `profile` key at all: the envelope failed to carry the document. That
    // is not the same statement as "the document is empty".
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({}),
    });

    await act(async () => { await ctx.saveProfileData({ lastName: "Lovelace" } as any); });

    // Left alone and invalidated, rather than overwritten with `{}` and marked
    // fresh -- the next reader refetches instead of rendering an empty profile.
    expect(cachedProfile()).toEqual({ firstName: "Ada", skills: ["Python"] });
    expect(
      currentClient.getQueryState(profileKeys.document())?.isInvalidated
    ).toBe(true);
  });
});
