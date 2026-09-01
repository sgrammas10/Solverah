/**
 * Route integrity — every internal navigation target must resolve to a real route.
 *
 * `App.tsx` ends with `<Route path="*" element={<Navigate to="/" replace />} />`.
 * That catch-all is correct for genuine 404s, but it also means a mistyped
 * internal path fails *silently*: React Router matches nothing, the catch-all
 * fires, and the user lands on the public landing page. Because `/` renders its
 * own `LandingNav` and the global `Header` is suppressed there, the result looks
 * exactly like being signed out — even though the session is untouched.
 *
 * That is not hypothetical. `WorkPulsePage` navigated to `/dashboard`; the route
 * is registered at `/job-seeker/dashboard`. Finishing the Work Pulse assessment
 * bounced the user to the landing page looking logged out. Every API call in
 * that flow returned 200 — there was nothing in the server logs to find, because
 * the failure was entirely client-side routing.
 *
 * A per-component test cannot catch this: `WorkPulsePage.test.tsx` asserted
 * `navigate` was called with `"/dashboard"` and passed, because it checked the
 * literal string the component passed, never that the string was routable.
 * The check has to be cross-file, which is what this is.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const APP_TSX = join(SRC, "app", "App.tsx");

/** Collect every .ts/.tsx file under `dir`, skipping test files and fixtures. */
function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === "__tests__" || entry === "test") continue;
      out.push(...sourceFiles(full));
      continue;
    }
    if (!/\.tsx?$/.test(entry)) continue;
    if (/\.test\.tsx?$/.test(entry)) continue;
    out.push(full);
  }
  return out;
}

/** Every `path="..."` registered in App.tsx. */
function registeredRoutes(): string[] {
  const source = readFileSync(APP_TSX, "utf8");
  return [...source.matchAll(/path="([^"]+)"/g)].map((m) => m[1]);
}

/**
 * Does `target` match `route`, accounting for `:param` segments?
 *
 * `/companies/:id` matches `/companies/5`; segment counts must agree, so
 * `/companies` alone does not.
 */
function matches(target: string, route: string): boolean {
  if (route === "*") return false; // the catch-all is the bug, not a match
  const routeParts = route.split("/").filter(Boolean);
  const targetParts = target.split("/").filter(Boolean);
  if (routeParts.length !== targetParts.length) return false;
  return routeParts.every((part, i) => part.startsWith(":") || part === targetParts[i]);
}

/**
 * Static internal paths a file navigates or links to.
 *
 * Only string literals starting with `/` are considered. Template literals with
 * interpolation are skipped: their value is not knowable statically, so
 * including them would produce false failures rather than real findings.
 */
function navigationTargets(source: string): string[] {
  const found = new Set<string>();

  const patterns = [
    /navigate\(\s*"(\/[^"${}]*)"/g, // navigate("/path")
    /navigate\(\s*'(\/[^'${}]*)'/g,
    /\bto="(\/[^"${}]*)"/g, // <Link to="/path">  /  <Navigate to="/path">
    /\bto='(\/[^'${}]*)'/g,
  ];

  for (const pattern of patterns) {
    for (const match of source.matchAll(pattern)) {
      // Drop query string and hash — routing matches on pathname only.
      const path = match[1].split("?")[0].split("#")[0];
      if (path) found.add(path);
    }
  }
  return [...found];
}

describe("route integrity", () => {
  const routes = registeredRoutes();

  it("App.tsx registers the routes this check depends on", () => {
    // Guards the parser itself: if App.tsx stops using `path="..."`, every
    // assertion below would vacuously pass and the check would be dead weight.
    expect(routes.length).toBeGreaterThan(20);
    expect(routes).toContain("/job-seeker/dashboard");
    expect(routes).toContain("*");
  });

  it("every internal navigation target resolves to a registered route", () => {
    const broken: string[] = [];

    for (const file of sourceFiles(SRC)) {
      const source = readFileSync(file, "utf8");
      for (const target of navigationTargets(source)) {
        if (!routes.some((route) => matches(target, route))) {
          broken.push(`${file.slice(SRC.length + 1).replace(/\\/g, "/")} -> ${target}`);
        }
      }
    }

    expect(
      broken,
      `These targets match no route in App.tsx, so they hit the catch-all and ` +
        `silently redirect to "/" (which looks like being signed out):\n  ` +
        broken.join("\n  "),
    ).toEqual([]);
  });

  it("recognises a dynamic-segment route", () => {
    expect(matches("/companies/5", "/companies/:id")).toBe(true);
    expect(matches("/companies", "/companies/:id")).toBe(false);
  });

  it("would have caught the /dashboard regression", () => {
    // The exact defect this file exists for.
    expect(routes.some((route) => matches("/dashboard", route))).toBe(false);
    expect(routes.some((route) => matches("/job-seeker/dashboard", route))).toBe(true);
  });
});
