import { render, screen, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./AuthContext.tsx";
import { useAuth } from "./useAuth";
import type { AuthContextType, ProfileData } from "./authContext";
import { profileKeys } from "../profile";
import { createQueryClient } from "../../shared/api/queryClient";

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
    // The provider renders children during the restore now (the app-wide gate
    // is retired), so "mounted" no longer implies "restored". Waiting on
    // `sessionLoading` keeps this helper's contract what it always was: the
    // context it returns describes a settled boot.
    if (ctx.sessionLoading) return null;
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
      if (ctx.sessionLoading) return null;
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

  // `updateProfileData` moved to the profile slice with the rest of the
  // document operations when the auth ⇄ profile cycle was broken; its merge
  // contract is asserted in profile/useProfileActions.test.tsx now.
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

// -- login and the profile document -------------------------------------------
//
// The seeding of the profile cache from the login envelope is the profile
// slice's reaction now (ProfileCacheSync, subscribed to auth's signed-in
// event), so the seeding tests live beside it in
// profile/ProfileCacheSync.test.tsx. What remains auth's own claim is the
// split: the document goes out on the event and never onto the User.

describe("AuthProvider - login and the profile document", () => {
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
      // Same reason as above: gcTime 0 would collect the seeded document
      // before this test could assert that logout is what removed it.
      client: createQueryClient(),
    });
    expect(cachedProfile()).toEqual({ firstName: "Ada" });

    mockFetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({}) });
    await act(async () => { await ctx.logout(); });

    // A second sign-in on this tab must not see the first user's document.
    expect(cachedProfile()).toBeUndefined();
  });
});


// -- logout clears per-user drafts in browser storage ---------------------------

/**
 * The drafts every instrument keeps client-side (USER_SCENARIOS.md Appendix A)
 * are keyed by instrument, not account, so on a shared tab the next person to
 * sign in was offered the last one's half-finished answers. Logout is the
 * backstop; `draftStorage.test.ts` covers the key list itself, this covers the
 * wiring -- that logout actually calls it, on both the explicit and the
 * request-failed path.
 */
describe("AuthProvider - logout clears per-user drafts", () => {
  const seedDrafts = () => {
    sessionStorage.setItem("mm_answers", JSON.stringify({ "mm-q1": "a" }));
    sessionStorage.setItem("focus_type_draft:1", "[1,2,3]");
    sessionStorage.setItem("solverah_assessment_answers", "{}");
    localStorage.setItem("pendingQuizSave", JSON.stringify({ quizGroup: "g" }));
    // Pure UI state: the one-quiz-per-device lockout stays.
    localStorage.setItem("guestQuizCompletedAt", "2026-10-01T00:00:00Z");
  };

  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
  });

  it("removes answers and the guest replay on an explicit logout", async () => {
    const ctx = await mountAuth({ ok: true, data: sessionBody() });
    seedDrafts();
    mockFetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({}) });

    await act(async () => { await ctx.logout(); });

    expect(sessionStorage.getItem("mm_answers")).toBeNull();
    expect(sessionStorage.getItem("focus_type_draft:1")).toBeNull();
    expect(sessionStorage.getItem("solverah_assessment_answers")).toBeNull();
    expect(localStorage.getItem("pendingQuizSave")).toBeNull();
    expect(localStorage.getItem("guestQuizCompletedAt")).toBe("2026-10-01T00:00:00Z");
  });

  it("removes them even when the logout request fails", async () => {
    // A person who clicked "log out" is logged out of this tab whatever the
    // network did, and that has to include the drafts.
    const ctx = await mountAuth({ ok: true, data: sessionBody() });
    seedDrafts();
    mockFetch.mockRejectedValueOnce(new Error("Network error"));

    await act(async () => { await ctx.logout(); });

    expect(sessionStorage.getItem("mm_answers")).toBeNull();
    expect(localStorage.getItem("pendingQuizSave")).toBeNull();
  });

  it("removes them on clearSessionLocally({ drafts: true }) -- the account-deletion call", async () => {
    const ctx = await mountAuth({ ok: true, data: sessionBody() });
    seedDrafts();

    act(() => { ctx.clearSessionLocally({ drafts: true }); });

    expect(sessionStorage.getItem("mm_answers")).toBeNull();
    expect(sessionStorage.getItem("focus_type_draft:1")).toBeNull();
    expect(localStorage.getItem("pendingQuizSave")).toBeNull();
    expect(localStorage.getItem("guestQuizCompletedAt")).not.toBeNull();
  });

  it("keeps them on a bare clearSessionLocally() -- the failed-refresh call", async () => {
    // refreshSession() resolves false on a network error too. A person
    // mid-Work-Pulse whose connection blips at submit must not lose 24 answers.
    const ctx = await mountAuth({ ok: true, data: sessionBody() });
    seedDrafts();

    act(() => { ctx.clearSessionLocally(); });

    expect(ctx.user).toBeNull();
    expect(sessionStorage.getItem("mm_answers")).not.toBeNull();
    expect(localStorage.getItem("pendingQuizSave")).not.toBeNull();
  });
});


// The seeding-guard tests (an envelope with no profileData must leave the
// cache unseeded) moved to profile/ProfileCacheSync.test.tsx, and the
// saveProfileData cache tests to profile/useProfileActions.test.tsx — the
// operations under test live in the profile slice now.
