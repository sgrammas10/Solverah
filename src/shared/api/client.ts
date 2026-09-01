/**
 * client.ts — the typed API client, generated-schema-backed.
 *
 * `schema.ts` next to this file is generated from `docs/openapi.json` by
 * `npm run generate:api`. That document is the contract CI enforces, so it is
 * the truth about what the API accepts and returns; deriving the client's types
 * from it is what makes a call site that sends the wrong body a type error
 * rather than a 422 someone finds in a browser.
 *
 * ── This client is deliberately not wired to any call site yet ───────────────
 *
 * Phase 4b generates the client; it does not migrate onto it. The reason is
 * specific rather than a matter of sequencing taste.
 * `tests/test_frontend_contract.py` finds every endpoint the SPA calls by
 * scanning `src/` for the two forms call sites are written in today -- the
 * template literal built on the API base constant, and the authenticated fetch
 * helper called with a string path -- and asserts that every one of them is a
 * path the API serves. A call rewritten as `api.GET(...)` is in neither form
 * and is invisible to that scan. Migrating call sites therefore has to happen
 * together with teaching that test the third shape, and doing both at once
 * would mean changing the check and the thing it checks in one step. So:
 * generate here, migrate when the scan can see the result.
 *
 * That scanner is also why this comment describes those two forms instead of
 * spelling them out. Written literally, the prose matched the regex and the
 * scan counted this file as calling an endpoint named `/path`, which the API
 * does not serve -- so the contract test failed on a docstring. Worth knowing
 * before adding an example here.
 *
 * ── Why this is a factory and not a module-level singleton ───────────────────
 *
 * The CSRF token is not readable from a cookie. The backend returns it in the
 * JSON body of the session probe and of login, and `AuthProvider` holds it in
 * React state -- see ARCHITECTURE.md Appendix B, which fixes that scheme
 * verbatim. A singleton created at import time cannot see that state, so it
 * could issue reads and would silently fail every write.
 *
 * Taking the getter as an argument is what lets the eventual migration keep the
 * scheme exactly as it is: `AuthProvider` instantiates this with its own
 * `() => csrfToken`, and the middleware below attaches the header on precisely
 * the methods `fetchWithAuth` attaches it on today. Nothing about how auth works
 * changes -- only what the request is written with.
 */
import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "./schema";
import { API_BASE } from "./api";

/**
 * Origin, not `API_BASE`.
 *
 * The generated paths are the ones written in the OpenAPI document, and those
 * are absolute: `/api/v1/me/profile`, not `/me/profile`. `API_BASE` already
 * ends in `/api/v1`, so using it here would produce `/api/v1/api/v1/...`. The
 * version still lives in exactly one place -- `shared/api/api.ts` -- and this strips
 * it back off rather than reintroducing a second copy of it.
 */
const API_ORIGIN = API_BASE.replace(/\/api\/v1$/, "");

/** The methods `fetchWithAuth` attaches the CSRF token on. Kept identical. */
const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/**
 * Build a typed client that signs state-changing requests with the CSRF token.
 *
 * @param getCsrfToken Reads the current token. Called per request rather than
 *   captured once, because the token is replaced on login and cleared on logout,
 *   and a client built at mount would otherwise hold the token from boot for the
 *   lifetime of the provider.
 */
export function createApiClient(getCsrfToken: () => string | null) {
  const client = createClient<paths>({
    baseUrl: API_ORIGIN,
    // The JWT lives in an HttpOnly cookie; every request has to carry it, and
    // the API is cross-origin in every deployed environment.
    credentials: "include",
  });

  const attachCsrf: Middleware = {
    onRequest({ request }) {
      if (!MUTATING_METHODS.has(request.method.toUpperCase())) return undefined;
      const token = getCsrfToken();
      if (!token) return undefined;
      request.headers.set("X-CSRF-TOKEN", token);
      return request;
    },
  };

  client.use(attachCsrf);
  return client;
}

/** The client's type, for callers that need to hold one without inferring it. */
export type ApiClient = ReturnType<typeof createApiClient>;

export type { paths };
