afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

/**
 * Phase 1b moved API_BASE from "/api" to "/api/v1".
 *
 * The normalization matters more than it looks. VITE_API_URL is configured
 * per-deployment and is currently set to a value ending in "/api" in at least
 * one environment; if this file only appended, that environment would resolve
 * to ".../api/api/v1" and every request would 404 the moment the frontend
 * shipped. Stripping either suffix before appending is what lets the code
 * deploy without an environment variable being edited in lockstep.
 */
describe("API_BASE URL normalization", () => {
  it("defaults to the local API when VITE_API_URL is not set", async () => {
    vi.stubEnv("VITE_API_URL", "");
    const { API_BASE } = await import("../api");
    expect(API_BASE).toBe("http://localhost:5000/api/v1");
  });

  it("appends /api/v1 to a bare origin", async () => {
    vi.stubEnv("VITE_API_URL", "https://api.example.com");
    const { API_BASE } = await import("../api");
    expect(API_BASE).toBe("https://api.example.com/api/v1");
  });

  it("rewrites a variable still configured for the unversioned path", async () => {
    // The shape a deployment configured before Phase 1b has. Appending without
    // stripping would produce ".../api/api/v1".
    vi.stubEnv("VITE_API_URL", "https://api.example.com/api");
    const { API_BASE } = await import("../api");
    expect(API_BASE).toBe("https://api.example.com/api/v1");
  });

  it("is idempotent for a variable already pointing at /api/v1", async () => {
    vi.stubEnv("VITE_API_URL", "https://api.example.com/api/v1");
    const { API_BASE } = await import("../api");
    expect(API_BASE).toBe("https://api.example.com/api/v1");
  });

  it("strips trailing slashes", async () => {
    vi.stubEnv("VITE_API_URL", "https://api.example.com/api///");
    const { API_BASE } = await import("../api");
    expect(API_BASE).toBe("https://api.example.com/api/v1");
  });
});
