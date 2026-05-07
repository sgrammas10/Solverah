afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("API_BASE URL normalization", () => {
  it("defaults to http://localhost:5000/api when VITE_API_URL is not set", async () => {
    vi.stubEnv("VITE_API_URL", "");
    const { API_BASE } = await import("../api");
    expect(API_BASE).toBe("http://localhost:5000/api");
  });

  it("preserves a correctly formed URL", async () => {
    vi.stubEnv("VITE_API_URL", "https://api.example.com/api");
    const { API_BASE } = await import("../api");
    expect(API_BASE).toBe("https://api.example.com/api");
  });

  it("strips trailing slashes", async () => {
    vi.stubEnv("VITE_API_URL", "https://api.example.com/api///");
    const { API_BASE } = await import("../api");
    expect(API_BASE).toBe("https://api.example.com/api");
  });

  it("appends /api when the base URL does not end with it", async () => {
    vi.stubEnv("VITE_API_URL", "https://api.example.com");
    const { API_BASE } = await import("../api");
    expect(API_BASE).toBe("https://api.example.com/api");
  });
});
