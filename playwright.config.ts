import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright — the E2E layer of ARCHITECTURE.md 6.5.
 *
 * NOT A CI GATE, deliberately, and that is a decision rather than an oversight.
 * A new gate that downloads ~115 MB of browser on every run and whose failures
 * include real flake is a gate that gets disabled the first busy week, taking
 * whatever signal it had with it. This suite is landed runnable and green
 * locally; promoting it to a required check is a later, separate change that
 * should come with a decision about browser caching and a retry policy.
 *
 * SERVES THE PRODUCTION BUILD, not the dev server. `vite preview` serves exactly
 * the artifact `npm run build` produced — the same chunk graph the bundle budget
 * in .size-limit.cjs measures — so this suite also exercises the lazy-route
 * splitting that Phase 4b introduced. A dev-server run would resolve modules
 * through Vite's transform pipeline instead and could pass while the built
 * artifact was broken.
 *
 * Type-checking: this file and everything under tests/e2e/ are outside the
 * `include` of both tsconfig.app.json ("src") and tsconfig.node.json
 * ("vite.config.ts"), so `npm run type-check` neither checks them nor changes
 * its result because of them. Playwright transpiles its own TypeScript.
 */
const PORT = Number(process.env.E2E_PORT ?? 4173);

export default defineConfig({
  testDir: "./tests/e2e",
  // The smoke path is one ordered journey; its steps share a stub state machine
  // and must run in sequence. Parallelism is per-file, and there is one file.
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: process.env.CI ? "list" : [["list"], ["html", { open: "never" }]],

  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },

  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],

  webServer: {
    // Build then preview: the suite is meaningless against a stale dist, and a
    // stale dist is the normal state of a working tree.
    command: `npm run build && npm run preview -- --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    stdout: "ignore",
    stderr: "pipe",
  },
});
