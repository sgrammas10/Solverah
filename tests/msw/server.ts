/**
 * server.ts — the MSW server and its lifecycle, for tests that want a network.
 *
 * ── Why this is opt-in rather than wired into `src/test/setup.ts` ────────────
 *
 * Most of this suite does not reach the network at all. Twenty test files mock
 * the `useAuth` module itself, replacing `fetchWithAuth` with a `vi.fn()`; no
 * request is ever issued, so an interceptor installed globally would sit idle
 * under them and, with `onUnhandledRequest: "error"`, would have nothing to say
 * either way. Turning it on globally would mean every one of those files paid
 * the setup cost to change nothing about what they assert.
 *
 * The files that *do* issue requests opt in by calling `useApiMocks()`. That
 * also keeps the two styles from being confused for each other: a file that
 * calls it is testing what goes over the wire, and a file that does not is
 * testing a component against a stubbed hook.
 *
 * ── Why unhandled requests are an error ──────────────────────────────────────
 *
 * The failure mode this replaces is a `vi.fn()` that answers *every* URL with
 * the same canned body. A test written that way passes whether the code calls
 * the right endpoint or the wrong one, and keeps passing after the call site
 * moves to a path that does not exist. `onUnhandledRequest: "error"` is the
 * opposite default: a request nobody modelled fails the test that made it.
 */
import { setupServer } from "msw/node";

import { defaultHandlers } from "./handlers";

export const server = setupServer(...defaultHandlers);

/**
 * Install the API doubles for the current file.
 *
 * Call once at the top level of a test file. Handlers added by an individual
 * test with `server.use(...)` are reset between tests, so a test that overrides
 * the session probe cannot leak a signed-in session into the next one.
 */
export function useApiMocks(): void {
  beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
  afterEach(() => server.resetHandlers());
  afterAll(() => server.close());
}

/**
 * Record every request the code under test issues, as `"METHOD /path"`.
 *
 * This is the thing a `vi.fn()` assigned over `globalThis.fetch` was really
 * being used for in several of these files -- counting calls -- except that it
 * counted calls to a function rather than requests on a network, and so counted
 * nothing if the code reached the network any other way.
 *
 * The list is cleared before each test, so a count is always for the test making
 * it. Call at the top level of a file, after `useApiMocks()`.
 */
export function recordRequests(): { readonly requests: string[] } {
  const requests: string[] = [];
  const onStart = ({ request }: { request: Request }) => {
    requests.push(`${request.method} ${new URL(request.url).pathname}`);
  };

  beforeAll(() => server.events.on("request:start", onStart));
  beforeEach(() => {
    requests.length = 0;
  });
  afterAll(() => server.events.removeListener("request:start", onStart));

  return { requests };
}

export { server as apiServer };
export * from "./handlers";
