/**
 * AuthContext.boot.test.tsx — the boot path, counted on the network.
 *
 * `AuthContext.test.tsx` already asserts that the restore issues one request,
 * and it does so by counting calls to a `vi.fn()` assigned over
 * `globalThis.fetch`. That test is the right instrument for what it covers --
 * it also asserts on the `credentials` and headers handed to `fetch`, which is
 * transport detail an interceptor does not see -- and it stays as it is.
 *
 * This file asserts the same exit condition one level down, where it is a claim
 * about requests rather than about function calls. The distinction is not
 * academic: a spy on `globalThis.fetch` counts nothing that reaches the network
 * another way, and it counts a call that never became a request. P0-3 is a
 * statement about what the browser sends on every page load, so it is worth
 * having one test that measures exactly that.
 *
 * The second test is the other half, and the more useful of the two. "One
 * request on boot" is trivially satisfiable by never fetching the profile at
 * all; what makes it a fix rather than a deletion is that the document still
 * arrives on the screens that render it. So: nothing on boot, and exactly one
 * `GET /me/profile` when something actually asks for the document.
 *
 * ── S3 and the refresh exchange ─────────────────────────────────────────────
 *
 * The access token is fifteen minutes now, so a 401 on the boot probe is the
 * ordinary state of a returning visitor rather than a signed-out one, and the
 * boot path answers it with `POST /auth/refresh` and a second probe. That is a
 * second request, and the P0-3 exit condition is a claim about how many
 * requests a page load costs -- so the two have to be reconciled rather than
 * one quietly weakening the other.
 *
 * They are reconciled by *who* pays for it. The refresh is attempted only when
 * this browser has had a session before (the `solverah.hasSession` hint), so an
 * anonymous visitor's boot is still exactly one request -- and the anonymous
 * landing page is the highest-volume boot in the product. A returning
 * signed-in visitor pays three (probe, refresh, probe) instead of being signed
 * out, which is the trade this round exists to make.
 *
 * `localStorage` is therefore part of this file's fixture and is cleared
 * between tests: without that, the signed-in test above leaves the hint behind
 * and the "anonymous visitor" test is no longer testing an anonymous visitor.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";

// The extension is load-bearing, as it is in AuthContext.test.tsx. This
// directory holds both `AuthContext.tsx` (the provider) and `authContext.ts`
// (the types and the context object), and on a case-insensitive filesystem
// `../AuthContext` resolves to the latter -- which has no `AuthProvider`, so
// React renders `undefined` and fails with "Element type is invalid".
import { AuthProvider } from "./AuthContext.tsx";
import { useAuth } from "./useAuth";
import { useProfile } from "../profile";
import { createQueryClient } from "../../shared/api/queryClient";
import {
  server,
  useApiMocks,
  recordRequests,
  signedIn,
  profileDocument,
  refreshSucceeds,
  sessionExpiredThenSignedIn,
} from "../../../tests/msw/server";

useApiMocks();
const { requests } = recordRequests();

// See the module docstring: the boot path reads this, so a test that does not
// clear it inherits the previous test's browser.
beforeEach(() => localStorage.clear());

const SESSION = "GET /api/v1/auth/session";
const PROFILE = "GET /api/v1/me/profile";
const REFRESH = "POST /api/v1/auth/refresh";

/** Mark this browser as one that has signed in before. */
function withPriorSession() {
  localStorage.setItem("solverah.hasSession", "1");
}

/** Renders nothing but proves the provider finished booting.
 *
 * Reading `sessionLoading` is what makes "anonymous" mean "the probe answered
 * signed-out": the provider renders children during the restore now (the
 * app-wide gate is retired), so without it the signed-out tests would assert
 * on the request list before the request had necessarily been recorded. */
function Shell() {
  const { user, sessionLoading } = useAuth();
  if (sessionLoading) return <span data-testid="shell">restoring</span>;
  return <span data-testid="shell">{user ? user.email : "anonymous"}</span>;
}

/** A screen that renders the profile document, as the six migrated consumers do. */
function ProfileScreen() {
  const { data: profile, isLoading } = useProfile();
  if (isLoading) return <span data-testid="profile">loading</span>;
  return <span data-testid="profile">{String((profile as { firstName?: string })?.firstName)}</span>;
}

function mount(children?: React.ReactNode) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <Shell />
        {children}
      </AuthProvider>
    </QueryClientProvider>
  );
}

describe("boot path", () => {
  it("issues exactly one request, and it is the session probe", async () => {
    server.use(signedIn());

    mount();
    await waitFor(() => expect(screen.getByTestId("shell")).toHaveTextContent("ada@example.com"));

    expect(requests).toEqual([SESSION]);
  });

  it("issues exactly one request when the visitor is signed out", async () => {
    // The default handler 401s. A failed probe must not trigger a profile fetch
    // either -- `useProfile` is gated on `user`, and an anonymous landing page
    // is the highest-volume boot there is.
    //
    // Nor a refresh: this browser has never had a session, so there is no
    // refresh cookie and the exchange would be a guaranteed 401 against a
    // rate-limited endpoint. Behind one NAT gateway that is how real users
    // start seeing 429s on refreshes that matter.
    mount();
    await waitFor(() => expect(screen.getByTestId("shell")).toHaveTextContent("anonymous"));

    expect(requests).toEqual([SESSION]);
  });

  it("refreshes and re-probes when a returning visitor's access token has expired", async () => {
    // The S3 case, and the one that decides whether a fifteen-minute access
    // token is a security improvement or a fifteen-minute session. The probe
    // 401s because the token aged out; the thirty-day refresh cookie is still
    // good; the visitor never sees a login screen.
    withPriorSession();
    server.use(sessionExpiredThenSignedIn(), refreshSucceeds());

    mount();
    await waitFor(() =>
      expect(screen.getByTestId("shell")).toHaveTextContent("ada@example.com"),
    );

    // Order is the assertion: refresh between the two probes. A boot path that
    // re-probed without refreshing would get the same 401 twice, and one that
    // refreshed without re-probing would never learn who the visitor is.
    expect(requests).toEqual([SESSION, REFRESH, SESSION]);
  });

  it("does not retry the refresh in a loop when it fails", async () => {
    // A returning visitor whose family was revoked -- logged out elsewhere, or
    // reuse detection fired. One refresh, one refusal, done. A loop here would
    // be an unbounded storm against the auth endpoint from every open tab.
    withPriorSession();

    mount();
    await waitFor(() => expect(screen.getByTestId("shell")).toHaveTextContent("anonymous"));

    expect(requests).toEqual([SESSION, REFRESH]);
  });

  it("forgets the session hint once the refresh has failed", async () => {
    // So the next page load is one request again rather than two forever.
    withPriorSession();

    mount();
    await waitFor(() => expect(screen.getByTestId("shell")).toHaveTextContent("anonymous"));

    expect(localStorage.getItem("solverah.hasSession")).toBeNull();
  });

  it("fetches the profile document only when a screen renders it", async () => {
    server.use(signedIn(), profileDocument({ firstName: "Ada" }));

    mount(<ProfileScreen />);
    await waitFor(() => expect(screen.getByTestId("profile")).toHaveTextContent("Ada"));

    // Order matters as much as the count: the probe resolves first and the
    // document is fetched after, rather than both going out together the way
    // the Promise.all on the old restore did.
    expect(requests).toEqual([SESSION, PROFILE]);
  });

  it("does not fetch the document twice when two screens read it", async () => {
    // The de-duplication that made moving the document to a query worth doing
    // rather than pushing the same request onto every consumer.
    server.use(signedIn(), profileDocument({ firstName: "Ada" }));

    mount(
      <>
        <ProfileScreen />
        <ProfileScreen />
      </>
    );
    await waitFor(() =>
      expect(screen.getAllByTestId("profile")[1]).toHaveTextContent("Ada")
    );

    expect(requests.filter((r) => r === PROFILE)).toEqual([PROFILE]);
  });
});
