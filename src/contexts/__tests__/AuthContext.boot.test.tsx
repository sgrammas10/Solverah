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
 */
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";

// The extension is load-bearing, as it is in AuthContext.test.tsx. This
// directory holds both `AuthContext.tsx` (the provider) and `authContext.ts`
// (the types and the context object), and on a case-insensitive filesystem
// `../AuthContext` resolves to the latter -- which has no `AuthProvider`, so
// React renders `undefined` and fails with "Element type is invalid".
import { AuthProvider } from "../AuthContext.tsx";
import { useAuth } from "../useAuth";
import { useProfile } from "../../hooks/useProfile";
import { createQueryClient } from "../../utils/queryClient";
import {
  server,
  useApiMocks,
  recordRequests,
  signedIn,
  profileDocument,
} from "../../../tests/msw/server";

useApiMocks();
const { requests } = recordRequests();

const SESSION = "GET /api/v1/auth/session";
const PROFILE = "GET /api/v1/me/profile";

/** Renders nothing but proves the provider finished booting. */
function Shell() {
  const { user } = useAuth();
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
    mount();
    await waitFor(() => expect(screen.getByTestId("shell")).toHaveTextContent("anonymous"));

    expect(requests).toEqual([SESSION]);
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
