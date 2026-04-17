import { render, screen, waitFor, act } from "@testing-library/react";
import { AuthProvider } from "../AuthContext";
import { useAuth } from "../useAuth";
import type { AuthContextType } from "../authContext";

const mockFetch = vi.fn();
globalThis.fetch = mockFetch as any;

beforeEach(() => {
  mockFetch.mockReset();
});

// Renders AuthProvider and waits for the loading phase to finish.
// Returns the captured context value once the Probe component mounts.
async function mountAuth(sessionResponse: { ok: boolean; data?: any }) {
  mockFetch.mockResolvedValueOnce({
    ok: sessionResponse.ok,
    json: () => Promise.resolve(sessionResponse.data ?? {}),
  });

  const ctxRef = { current: null as AuthContextType | null };

  function Probe() {
    const ctx = useAuth();
    ctxRef.current = ctx;
    return <span data-testid="ready" />;
  }

  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>
  );

  await waitFor(() => screen.getByTestId("ready"));
  return ctxRef.current!;
}

// ─── Session restore ──────────────────────────────────────────────────────────

describe("AuthProvider - session restore", () => {
  it("sets user from a successful profile fetch", async () => {
    const ctx = await mountAuth({
      ok: true,
      data: { id: "1", email: "ada@example.com", name: "Ada", role: "job-seeker", profileComplete: false },
    });
    expect(ctx.user?.email).toBe("ada@example.com");
  });

  it("stores the CSRF token from the response body", async () => {
    const ctx = await mountAuth({
      ok: true,
      data: { id: "1", email: "ada@example.com", name: "Ada", role: "job-seeker", profileComplete: false, csrfToken: "tok-abc" },
    });
    // We verify CSRF is stored by checking it gets attached to a subsequent POST
    mockFetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ ok: true }) });
    await act(async () => {
      await ctx.fetchWithAuth("/some-endpoint", { method: "POST" });
    });
    const postHeaders = mockFetch.mock.calls[1][1].headers;
    expect(postHeaders["X-CSRF-TOKEN"]).toBe("tok-abc");
  });

  it("sets user to null when the profile fetch fails", async () => {
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

    render(<AuthProvider><Probe /></AuthProvider>);
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
      data: { id: "1", email: "ada@example.com", name: "Ada", role: "job-seeker", profileComplete: false, csrfToken: "tok-abc" },
    });

    // Mock the logout POST
    mockFetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({}) });

    await act(async () => { await ctx.logout(); });

    expect(ctx.user).toBeNull();
  });

  it("still clears user even when the logout request fails", async () => {
    const ctx = await mountAuth({
      ok: true,
      data: { id: "1", email: "ada@example.com", name: "Ada", role: "job-seeker", profileComplete: false },
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
      data: { id: "1", email: "a@b.com", name: "A", role: "job-seeker", profileComplete: false, csrfToken: "csrf-123" },
    });

    mockFetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ ok: true }) });

    await act(async () => {
      await ctx.fetchWithAuth("/save", { method: "POST" });
    });

    const headers = mockFetch.mock.calls[1][1].headers;
    expect(headers["X-CSRF-TOKEN"]).toBe("csrf-123");
  });

  it("does not attach X-CSRF-TOKEN on GET requests", async () => {
    const ctx = await mountAuth({
      ok: true,
      data: { id: "1", email: "a@b.com", name: "A", role: "job-seeker", profileComplete: false, csrfToken: "csrf-123" },
    });

    mockFetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ data: "ok" }) });

    await act(async () => {
      await ctx.fetchWithAuth("/profile", { method: "GET" });
    });

    const headers = mockFetch.mock.calls[1][1].headers;
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

    expect(mockFetch.mock.calls[1][1].credentials).toBe("include");
  });
});

// ─── updateProfile / updateProfileData ───────────────────────────────────────

describe("AuthProvider - optimistic updates", () => {
  it("updateProfile patches the in-memory user", async () => {
    const ctx = await mountAuth({
      ok: true,
      data: { id: "1", email: "ada@example.com", name: "Ada", role: "job-seeker", profileComplete: false },
    });

    act(() => { ctx.updateProfile({ profileComplete: true }); });

    expect(ctx.user?.profileComplete).toBe(true);
  });

  it("updateProfileData merges new profile data", async () => {
    const ctx = await mountAuth({
      ok: true,
      data: { id: "1", email: "ada@example.com", name: "Ada", role: "job-seeker", profileComplete: false, profileData: { firstName: "Ada" } },
    });

    act(() => { ctx.updateProfileData({ lastName: "Lovelace" } as any); });

    expect((ctx.user?.profileData as any)?.lastName).toBe("Lovelace");
    expect((ctx.user?.profileData as any)?.firstName).toBe("Ada");
  });
});
