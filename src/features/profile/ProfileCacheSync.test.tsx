/**
 * ProfileCacheSync.test.tsx — login seeds the profile cache, via the event.
 *
 * These assertions lived in AuthContext.test.tsx while AuthProvider seeded the
 * cache itself. The seeding is this slice's reaction now — auth announces the
 * sign-in, ProfileCacheSync writes the document — so the tests moved here with
 * it. Their meaning is unchanged: a fresh sign-in has the document before
 * anything asks for it, and an envelope that carried no document must leave
 * the cache unseeded rather than resolved-empty.
 *
 * The provider and the login flow are real (a mocked `fetch`, not a mocked
 * hook), because the thing under test is the whole handshake: login splits the
 * envelope, emits the event, and this component — mounted exactly as the app
 * mounts it — reacts.
 */
import { render, screen, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AuthProvider, useAuth } from "../auth";
import type { AuthContextType, ProfileData } from "../auth";
import { ProfileCacheSync } from "./ProfileCacheSync";
import { profileKeys, useProfile } from "./useProfile";
import { createQueryClient } from "../../shared/api/queryClient";

const mockFetch = vi.fn();
globalThis.fetch = mockFetch as unknown as typeof fetch;

beforeEach(() => {
  mockFetch.mockReset();
});

/** The client the most recent mount rendered with, for cache assertions. */
let currentClient: QueryClient;

function cachedProfile(): ProfileData | undefined {
  return currentClient.getQueryData<ProfileData>(profileKeys.document());
}

/**
 * Renders AuthProvider + ProfileCacheSync (the app's own composition) over a
 * signed-out restore, and returns the settled auth context.
 *
 * `createQueryClient()` — the app's client — on purpose, twice over: gcTime
 * zero would collect an observer-less seeded entry before an assertion could
 * see it, and staleTime zero would refetch even a seeded query, hiding the
 * very suppression the guard tests exist to catch.
 */
async function mountWithSync() {
  // The restore probe: nobody signed in yet.
  mockFetch.mockResolvedValueOnce({ ok: false, json: () => Promise.resolve({}) });

  currentClient = createQueryClient();
  const ctxRef = { current: null as AuthContextType | null };

  function Probe() {
    const ctx = useAuth();
    ctxRef.current = ctx;
    if (ctx.sessionLoading) return null;
    return <span data-testid="ready" />;
  }

  render(
    <QueryClientProvider client={currentClient}>
      <AuthProvider>
        <ProfileCacheSync />
        <Probe />
      </AuthProvider>
    </QueryClientProvider>
  );

  await waitFor(() => screen.getByTestId("ready"));
  return ctxRef as { current: AuthContextType };
}

describe("ProfileCacheSync - login seeds the profile cache", () => {
  /**
   * `POST /auth/login` still returns the profile document inside its user
   * envelope (SessionUser in solverah/schemas/auth.py). Dropping the boot fetch
   * would only move that request to the first screen that renders the document
   * unless the login response is written through to the cache.
   */
  it("seeds the cached profile document from the login response", async () => {
    const ctx = await mountWithSync();

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

    await act(async () => { await ctx.current.login("ada@example.com", "password123"); });

    expect(cachedProfile()).toEqual({ firstName: "Ada", skills: ["Python"] });
  });

  /**
   * The guard. `splitLoginUser` hands back `undefined` for an envelope with no
   * profileData, and seeding that would pin an *empty document* into the cache
   * as resolved -- fresh for the whole staleTime window, so the first real
   * fetch never goes out and consumers that branch on the document
   * (FocusTypeResultsPage, PathIntelligencePage) navigate away from results
   * that exist on the server. `POST /auth/login` folds profileData in today,
   * so this is latent; it stops being latent the moment `auth_service` stops
   * folding it in, which is why this asserts the guard rather than the
   * envelope.
   */
  it("leaves the cached document unseeded rather than resolving it empty", async () => {
    const ctx = await mountWithSync();

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

    await act(async () => { await ctx.current.login("ada@example.com", "password123"); });

    // `undefined`, not `{}`. Only the former makes useProfile() fetch.
    expect(cachedProfile()).toBeUndefined();
  });

  /** The consequence of the guard, end to end. */
  it("lets useProfile fetch the document under the app's real staleTime", async () => {
    const client = createQueryClient();

    // Restore fails -- nobody is signed in, so useProfile stays disabled until
    // login() sets the user.
    mockFetch.mockResolvedValueOnce({ ok: false, json: () => Promise.resolve({}) });

    const ctxRef = { current: null as AuthContextType | null };

    function Probe() {
      ctxRef.current = useAuth();
      const { data } = useProfile();
      return <span data-testid="probe">{data ? JSON.stringify(data) : "no-data"}</span>;
    }

    render(
      <QueryClientProvider client={client}>
        <AuthProvider>
          <ProfileCacheSync />
          <Probe />
        </AuthProvider>
      </QueryClientProvider>
    );
    await waitFor(() => screen.getByTestId("probe"));

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
      expect(screen.getByTestId("probe").textContent).toContain("Ada");
    });

    const urls = mockFetch.mock.calls.map((call: unknown[]) => String(call[0]));
    expect(urls.some((url) => url.includes("/me/profile"))).toBe(true);
  });
});
