/**
 * useProfileActions.test.tsx — the imperative document operations and the cache.
 *
 * These assertions lived in AuthContext.test.tsx while the operations lived on
 * the auth context. The operations moved here when the auth ⇄ profile cycle
 * was broken; the assertions moved with them, meaning intact: the server's
 * copy of a save replaces the cache, a present-but-empty document is
 * authoritative, a response that failed to carry one invalidates instead of
 * clobbering, and updateProfileData is a shallow merge with no round trip.
 *
 * The transport is the real AuthProvider over a mocked `fetch`, as in the
 * tests these came from — the operations are defined by what goes over the
 * wire and what lands in the cache, not by which hook hands them out.
 */
import { render, screen, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AuthProvider, useAuth } from "../auth";
import type { ProfileData } from "../auth";
import { useProfileActions } from "./useProfileActions";
import { profileKeys } from "./useProfile";
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

type Actions = ReturnType<typeof useProfileActions>;

/**
 * Renders the hook under the real providers, with `profile` pre-seeded into
 * the document cache, and returns the actions once the boot has settled.
 *
 * `createQueryClient()` -- the app's client -- because gcTime zero would
 * collect the observer-less seeded entry before an assertion could read it.
 */
async function mountActions(profile?: ProfileData) {
  // The session probe: signed out. The operations don't read `user`, so the
  // cheapest settled boot is enough.
  mockFetch.mockResolvedValueOnce({ ok: false, json: () => Promise.resolve({}) });

  currentClient = createQueryClient();
  if (profile !== undefined) {
    currentClient.setQueryData(profileKeys.document(), profile);
  }

  const ref = { current: null as Actions | null };

  function Probe() {
    const { sessionLoading } = useAuth();
    ref.current = useProfileActions();
    if (sessionLoading) return null;
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
  return ref as { current: Actions };
}

// -- saveProfileData writes back the server's copy ----------------------------

describe("useProfileActions - saveProfileData and the cache", () => {
  it("replaces the cached document with the server's copy of the merge", async () => {
    const actions = await mountActions({ firstName: "Ada" });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ profile: { firstName: "Ada", lastName: "Lovelace" } }),
    });

    await act(async () => { await actions.current.saveProfileData({ lastName: "Lovelace" }); });

    // The server's copy, so anything the write allowlist dropped or normalised
    // is what consumers see next.
    expect(cachedProfile()).toEqual({ firstName: "Ada", lastName: "Lovelace" });
  });

  it("writes through a present-but-empty document", async () => {
    const actions = await mountActions({ firstName: "Ada" });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ profile: {} }),
    });

    await act(async () => { await actions.current.saveProfileData({}); });

    // A present `{}` is the server describing the document it just wrote, not a
    // response that failed to carry one. It is authoritative.
    expect(cachedProfile()).toEqual({});
  });

  it("does not clobber the cached document when the response carries no profile", async () => {
    const actions = await mountActions({ firstName: "Ada", skills: ["Python"] });

    // No `profile` key at all: the envelope failed to carry the document. That
    // is not the same statement as "the document is empty".
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({}),
    });

    await act(async () => { await actions.current.saveProfileData({ lastName: "Lovelace" }); });

    // Left alone and invalidated, rather than overwritten with `{}` and marked
    // fresh -- the next reader refetches instead of rendering an empty profile.
    expect(cachedProfile()).toEqual({ firstName: "Ada", skills: ["Python"] });
    expect(
      currentClient.getQueryState(profileKeys.document())?.isInvalidated
    ).toBe(true);
  });
});

// -- updateProfileData merges without a round trip ----------------------------

describe("useProfileActions - updateProfileData", () => {
  it("merges into the cached profile document", async () => {
    const actions = await mountActions({ firstName: "Ada" });

    act(() => { actions.current.updateProfileData({ lastName: "Lovelace" }); });

    // A shallow merge that preserves keys it was not given, and no request:
    // the only fetch so far is the boot probe.
    expect(cachedProfile()?.lastName).toBe("Lovelace");
    expect(cachedProfile()?.firstName).toBe("Ada");
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });
});
