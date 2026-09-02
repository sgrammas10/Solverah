/**
 * contract.ts — handler builders bound to the generated OpenAPI types.
 *
 * The point of this file is that a test double cannot quietly stop resembling
 * the API. A hand-rolled `vi.fn()` fetch mock is free to return anything: the
 * shape it hands back is whatever the person writing the test believed the
 * endpoint returned on the day they wrote it, and nothing rechecks that belief
 * afterwards. When the endpoint changes, the mock keeps returning the old shape
 * and the test keeps passing -- green, and testing a version of the API that no
 * longer exists.
 *
 * `src/api/schema.ts` is generated from `docs/openapi.json`, which CI enforces
 * against the running app. Routing every handler through the builders below
 * means two things are checked at compile time, by `npm run type-check`:
 *
 *   1. the path exists in the contract -- `P extends ApiPath`;
 *   2. the body matches the schema for that path, method and status --
 *      `BodyOf<P, M, S>`.
 *
 * So when the API changes, `npm run generate:api` regenerates the types and the
 * handlers that no longer match stop compiling. That is the whole idea: the
 * mocks fail loudly at build time instead of silently at runtime.
 *
 * This is deliberately *not* a full contract test. It checks the shapes the
 * doubles return, not that Flask returns them -- `tests/test_frontend_contract.py`
 * covers the paths, and the OpenAPI document itself is checked against the app.
 */
import { http, HttpResponse, type HttpHandler, type HttpResponseResolver } from "msw";

import type { paths } from "../../src/shared/api/schema";

/** Every path the contract describes. */
export type ApiPath = keyof paths;

type Method = "get" | "put" | "post" | "delete" | "patch";

/**
 * The methods a given path actually serves.
 *
 * openapi-typescript emits *every* method key on *every* path, typing the ones
 * that do not exist as `get?: never` -- so `keyof paths[P]` is all five whether
 * or not they are served. An absent method's property type is `undefined`,
 * which is what the conditional below filters on; without it, `mock("delete",
 * "/api/v1/auth/session", ...)` would typecheck against an endpoint that has no
 * DELETE.
 */
export type MethodOf<P extends ApiPath> = {
  [M in Extract<keyof paths[P], Method>]: paths[P][M] extends { responses: unknown }
    ? M
    : never;
}[Extract<keyof paths[P], Method>];

/** The status codes the contract documents for a path and method. */
export type StatusOf<P extends ApiPath, M extends MethodOf<P>> = paths[P][M] extends {
  responses: infer R;
}
  ? Extract<keyof R, number>
  : never;

/** The JSON body the contract documents for a path, method and status. */
export type BodyOf<
  P extends ApiPath,
  M extends MethodOf<P>,
  S extends StatusOf<P, M>,
> = paths[P][M] extends { responses: infer R }
  ? S extends keyof R
    ? R[S] extends { content: { "application/json": infer B } }
      ? B
      : never
    : never
  : never;

/**
 * OpenAPI writes templated segments as `{kind}`; MSW matches them as `:kind`.
 *
 * Kept as a type as well as a runtime replacement so the string handed to MSW
 * is still tied to the contract path it came from rather than becoming an
 * opaque `string` at the boundary.
 */
type ToMswPath<S extends string> = S extends `${infer Head}{${infer Param}}${infer Tail}`
  ? `${Head}:${Param}${ToMswPath<Tail>}`
  : S;

/**
 * Match a contract path at any origin.
 *
 * `API_BASE` resolves from `VITE_API_URL` and is `http://localhost:5000/api/v1`
 * under the test env, but pinning that here would make every handler depend on
 * an environment variable that has nothing to do with what is being tested. The
 * leading `*` matches any origin, so the handlers keep working if the default
 * moves.
 */
export function route<P extends ApiPath>(path: P): `*${ToMswPath<P>}` {
  return `*${path.replace(/\{([^}]+)\}/g, ":$1")}` as `*${ToMswPath<P>}`;
}

/**
 * Start a handler for a contract path, then answer it.
 *
 *     mock("get", "/api/v1/auth/session").reply(200, { user, csrf_token, flags })
 *     mock("patch", "/api/v1/me/profile").resolve(async ({ request }) => ...)
 *
 * ── Why this is two calls rather than one ────────────────────────────────────
 *
 * The obvious signature is `mock(method, path, status, body)`, and it was that
 * first. It does not work, and the way it fails is quiet: with all four
 * arguments in one call, `P` and `M` are still being inferred while `body` is
 * being checked, so `BodyOf<P, M, S>` cannot be reduced and TypeScript falls
 * back to its constraint -- the union of the bodies of *every* documented
 * status. The path and the status were checked, but
 * `mock("get", "/api/v1/auth/session", 200, { error: "nope" })` compiled
 * happily: a 200 carrying the 401 body, which is exactly the class of drift
 * these helpers exist to catch.
 *
 * Splitting the call fixes it by construction. `P` and `M` are resolved by the
 * time the returned object exists, so `StatusOf` and `BodyOf` are concrete
 * types rather than deferred conditionals, and the status and the body are
 * checked against each other.
 */
export function mock<P extends ApiPath, M extends MethodOf<P>>(method: M, path: P) {
  const matcher = route(path);
  return {
    /** Answer with a fixed body, checked against the schema for this status. */
    reply<S extends StatusOf<P, M>>(status: S, body: BodyOf<P, M, S>): HttpHandler {
      return http[method](matcher, () =>
        HttpResponse.json(body as Record<string, unknown>, { status: status as number }),
      );
    },
    /**
     * Answer with a resolver, for what a fixed body cannot express: reading the
     * request to assert on it, or answering differently across calls (the
     * session probe is 401 before sign-in and 200 after).
     *
     * The path is still contract-checked; the body is not, because the resolver
     * owns the response. Prefer `reply` where the answer is fixed.
     */
    resolve(resolver: HttpResponseResolver): HttpHandler {
      return http[method](matcher, resolver);
    },
  };
}
