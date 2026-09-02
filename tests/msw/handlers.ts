/**
 * handlers.ts — the default API doubles, in contract shapes.
 *
 * Everything here is built through `contract.ts`, so every path and every fixed
 * body is checked against the generated OpenAPI types at type-check time. See
 * that file for why that matters.
 *
 * The defaults describe a *signed-out browser with no data*: the session probe
 * 401s and the profile document is empty. That is the state the app actually
 * boots into for an anonymous visitor, and picking it as the baseline means a
 * test that needs something else has to say so -- with `server.use(...)` and one
 * of the builders below -- rather than inheriting a signed-in session it never
 * asked for and does not mention.
 */
import { HttpResponse } from "msw";

import { mock } from "./contract";
import type { components } from "../../src/shared/api/schema";

type SummaryUser = components["schemas"]["SummaryUser"];
type SessionFlags = components["schemas"]["SessionFlags"];

/**
 * The signed-in user these handlers describe.
 *
 * `id` is a number because the contract says `integer`. Note that
 * `src/contexts/authContext.ts` declares `id: string` on both `SessionResponse`
 * and `User` -- the two disagree, and this fixture follows the contract because
 * the contract is the half that CI checks against the running API. Nothing in
 * the app reads the id in a way that makes the difference observable at
 * runtime, which is precisely why the drift survived; it is written down here
 * rather than papered over.
 */
export const TEST_USER: SummaryUser = {
  id: 1,
  email: "ada@example.com",
  name: "Ada Lovelace",
  role: "job-seeker",
};

/** Nothing completed — the state a newly registered account is in. */
export const NO_FLAGS: SessionFlags = {
  email_confirmed: true,
  wpl_completed: false,
  wpll_completed: false,
  wp_v2_completed: false,
};

/** `GET /auth/session` answering as a signed-in user. */
export function signedIn(
  overrides: { user?: Partial<SummaryUser>; flags?: Partial<SessionFlags>; csrfToken?: string } = {},
) {
  return mock("get", "/api/v1/auth/session").reply(200, {
    user: { ...TEST_USER, ...overrides.user },
    csrf_token: overrides.csrfToken ?? "test-csrf-token",
    flags: { ...NO_FLAGS, ...overrides.flags },
  });
}

/** `GET /auth/session` answering as an anonymous visitor. This is the default. */
export function signedOut() {
  return mock("get", "/api/v1/auth/session").reply(401, { error: "Not authenticated" });
}

/** `GET /me/profile` answering with a given document. */
export function profileDocument(profile: Record<string, unknown> = {}) {
  return mock("get", "/api/v1/me/profile").reply(200, { profile });
}

/**
 * `PATCH /me/profile` echoing back what it was sent, merged over `base`.
 *
 * The real endpoint merges the incoming keys over the stored document and
 * returns the result, and `saveProfileData` writes that result straight into
 * the query cache. A double that returned a fixed body would make the cache
 * disagree with what the test just asked to save.
 */
export function profilePatchEchoes(base: Record<string, unknown> = {}) {
  return mock("patch", "/api/v1/me/profile").resolve(async ({ request }) => {
    const body = (await request.json()) as { profile?: Record<string, unknown> };
    return HttpResponse.json({ profile: { ...base, ...(body?.profile ?? {}) } });
  });
}

/** `POST /auth/login` succeeding, with the profile document folded into `user`. */
export function loginSucceeds(profileData: Record<string, unknown> = {}) {
  return mock("post", "/api/v1/auth/login").reply(200, {
    message: "login successful",
    csrfToken: "test-csrf-token",
    // The login envelope nests the profile document inside `user` and is
    // preserved verbatim; AuthContext.splitLoginUser strips it into the cache.
    user: { ...TEST_USER, wpl_completed: false, wpll_completed: false, wp_v2_completed: false, profileData },
  });
}

/** `POST /auth/login` rejecting the credentials. */
export function loginFails(message = "Invalid email or password") {
  return mock("post", "/api/v1/auth/login").reply(401, { error: message });
}

/**
 * The baseline every suite starts from: a signed-out browser.
 *
 * Only the routes the migrated tests actually exercise are listed. An
 * unhandled request is an error rather than a pass-through -- see `server.ts`
 * -- so a call this list does not cover fails the test that made it instead of
 * escaping to the network.
 */
export const defaultHandlers = [
  signedOut(),
  mock("post", "/api/v1/auth/logout").reply(200, { message: "logout successful" }),
  profileDocument(),
  profilePatchEchoes(),
  mock("post", "/api/v1/auth/register").reply(201, {
    message: "Account created. Check your email for a code.",
    user: TEST_USER,
  }),
  mock("post", "/api/v1/auth/email/verify").reply(200, { message: "Email verified" }),
  mock("post", "/api/v1/auth/email/verify/resend").reply(200, { message: "New code sent" }),
  mock("post", "/api/v1/auth/password/forgot").reply(200, { message: "Code sent" }),
  mock("post", "/api/v1/auth/password/reset").reply(200, {
    message: "Signed in",
    csrfToken: "test-csrf-token",
    user: TEST_USER,
  }),
  mock("post", "/api/v1/intake/early-access").reply(200, { ok: true }),
];
