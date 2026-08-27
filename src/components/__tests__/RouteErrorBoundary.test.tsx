/**
 * RouteErrorBoundary — the route-level policy, and the Query integration.
 *
 * The three guarantees Phase 4b claims, asserted rather than asserted-about:
 *
 *   1. A route that throws renders a fallback, and the chrome around it — the
 *      Header, and therefore every way out — keeps working.
 *   2. Navigating away clears the error, so one broken screen does not latch on
 *      and poison the rest of the session.
 *   3. A failed `useProfile` query reaches the boundary at all. That is not
 *      free: TanStack Query swallows errors by default, and the four pages that
 *      branch on the profile document at mount were rendering a plausible wrong
 *      screen because of it. `throwOnError` is what converts that silent
 *      mis-render into a visible, retryable failure.
 */
import { lazy, useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route, Link } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { RouteErrorBoundary } from "../RouteErrorBoundary";
import { useProfile } from "../../hooks/useProfile";

const mockFetchWithAuth = vi.fn();
const mockUser = { id: "1", email: "ada@example.com", role: "job-seeker" };

// useProfile reaches for the real AuthProvider, which would drag the whole
// session-restore fetch into a test about error routing. Only two fields of the
// context matter here.
vi.mock("../../contexts/useAuth", () => ({
  useAuth: () => ({ user: mockUser, fetchWithAuth: mockFetchWithAuth }),
}));

beforeEach(() => {
  mockFetchWithAuth.mockReset();
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

/** Retries off: a test asserting on a rejected query should not wait out backoff. */
function testClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
}

/**
 * The real arrangement from AppShell: Header outside the boundary, routes
 * inside. Getting this wrong is the failure mode the placement exists to
 * prevent, so the test mirrors it rather than wrapping everything.
 */
function Shell({
  children,
  initialPath = "/broken",
}: {
  children: React.ReactNode;
  initialPath?: string;
}) {
  return (
    <QueryClientProvider client={testClient()}>
      <MemoryRouter initialEntries={[initialPath]}>
        <header>
          <Link to="/safe">Go somewhere else</Link>
        </header>
        <RouteErrorBoundary>{children}</RouteErrorBoundary>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function Exploding(): JSX.Element {
  throw new Error("this screen is broken");
}

function Safe() {
  return <h1>A working screen</h1>;
}

describe("RouteErrorBoundary - containment", () => {
  it("renders a fallback instead of a blank page when a route throws", () => {
    render(
      <Shell>
        <Routes>
          <Route path="/broken" element={<Exploding />} />
        </Routes>
      </Shell>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("We couldn't load this page.");
  });

  it("keeps navigation alive when a route throws", () => {
    render(
      <Shell>
        <Routes>
          <Route path="/broken" element={<Exploding />} />
        </Routes>
      </Shell>,
    );

    // The reason the boundary sits below the Header rather than around the
    // shell: the user must still have a way out that is not the back button.
    expect(screen.getByRole("link", { name: "Go somewhere else" })).toBeInTheDocument();
  });

  it("does not leak the raw error message to the user", () => {
    render(
      <Shell>
        <Routes>
          <Route path="/broken" element={<Exploding />} />
        </Routes>
      </Shell>,
    );

    expect(screen.queryByText(/this screen is broken/)).not.toBeInTheDocument();
  });

  it("clears the error when the user navigates to another route", async () => {
    const user = userEvent.setup();

    render(
      <Shell>
        <Routes>
          <Route path="/broken" element={<Exploding />} />
          <Route path="/safe" element={<Safe />} />
        </Routes>
      </Shell>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Go somewhere else" }));

    // Without resetKeys={[pathname]} the boundary stays latched and every
    // subsequent route renders the fallback for the rest of the session.
    expect(await screen.findByRole("heading", { name: "A working screen" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("RouteErrorBoundary - Suspense", () => {
  it("shows the route fallback while a lazy chunk is in flight, then the page", async () => {
    let resolveChunk: (m: { default: () => JSX.Element }) => void = () => {};
    const pending = new Promise<{ default: () => JSX.Element }>((resolve) => {
      resolveChunk = resolve;
    });
    const Lazy = lazy(() => pending);

    const { container } = render(
      <Shell initialPath="/lazy">
        <Routes>
          <Route path="/lazy" element={<Lazy />} />
        </Routes>
      </Shell>,
    );

    // The skeleton is aria-hidden on purpose -- it is scaffolding, not an
    // announcement -- so it is asserted on by class rather than by role.
    expect(container.querySelector(".animate-deferred-fade-in")).not.toBeNull();

    resolveChunk({ default: () => <h1>Lazy page</h1> });

    expect(await screen.findByRole("heading", { name: "Lazy page" })).toBeInTheDocument();
    expect(container.querySelector(".animate-deferred-fade-in")).toBeNull();
  });

  it("catches a chunk that fails to load rather than blanking the page", async () => {
    const Broken = lazy(() => Promise.reject(new Error("Failed to fetch dynamically imported module")));

    render(
      <Shell initialPath="/lazy">
        <Routes>
          <Route path="/lazy" element={<Broken />} />
        </Routes>
      </Shell>,
    );

    // A stale chunk URL after a redeploy is the everyday version of this.
    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't load this page.");
  });
});

describe("RouteErrorBoundary - failed profile queries", () => {
  /** A page shaped like the four that branch on the document at mount. */
  function ResultsScreen() {
    const { data, isLoading } = useProfile();
    if (isLoading) return <p>Loading your result…</p>;
    if (!data?.focus_type_result) return <p>You have not taken this quiz</p>;
    return <h1>Your result</h1>;
  }

  it("surfaces a failed profile fetch on the boundary instead of a wrong screen", async () => {
    mockFetchWithAuth.mockRejectedValue(new Error("Network request failed"));

    render(
      <Shell initialPath="/results">
        <Routes>
          <Route path="/results" element={<ResultsScreen />} />
        </Routes>
      </Shell>,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't load this page.");

    // The regression this guards. Before throwOnError the errored query was
    // indistinguishable from a successful fetch of an empty document, so this
    // screen told a user who *had* taken the quiz that they had not — and its
    // real-world siblings redirected them away to retake it.
    expect(screen.queryByText("You have not taken this quiz")).not.toBeInTheDocument();
  });

  it("still renders normally when the profile fetch succeeds", async () => {
    mockFetchWithAuth.mockResolvedValue({
      profile: { focus_type_result: { archetype: "Deep Diver" } },
    });

    render(
      <Shell initialPath="/results">
        <Routes>
          <Route path="/results" element={<ResultsScreen />} />
        </Routes>
      </Shell>,
    );

    expect(await screen.findByRole("heading", { name: "Your result" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("retry refetches the query rather than re-throwing the cached failure", async () => {
    const user = userEvent.setup();
    mockFetchWithAuth.mockRejectedValueOnce(new Error("Network request failed"));

    render(
      <Shell initialPath="/results">
        <Routes>
          <Route path="/results" element={<ResultsScreen />} />
        </Routes>
      </Shell>,
    );
    expect(await screen.findByRole("alert")).toBeInTheDocument();

    mockFetchWithAuth.mockResolvedValue({
      profile: { focus_type_result: { archetype: "Deep Diver" } },
    });
    await user.click(screen.getByRole("button", { name: "Try again" }));

    // This is what QueryErrorResetBoundary buys. Resetting only the boundary
    // would re-render the consumer, re-read the still-errored query and throw
    // again before paint -- a retry button that cannot ever succeed.
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Your result" })).toBeInTheDocument(),
    );
    expect(mockFetchWithAuth).toHaveBeenCalledTimes(2);
  });
});

describe("RouteErrorBoundary - unaffected paths", () => {
  it("leaves a working route completely alone", () => {
    function Counter() {
      const [n, setN] = useState(0);
      return (
        <button type="button" onClick={() => setN(n + 1)}>
          count {n}
        </button>
      );
    }

    render(
      <Shell initialPath="/safe">
        <Routes>
          <Route path="/safe" element={<Counter />} />
        </Routes>
      </Shell>,
    );

    expect(screen.getByRole("button", { name: "count 0" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
