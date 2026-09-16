/**
 * Header.test.tsx — the signed-in entry point to /settings, and the order of
 * operations on logout.
 *
 * The gear is the ONLY way into account settings: nothing links to /settings
 * from the body of the app, and no dropdown exists to hide it in. If it stops
 * rendering, the page is still routable but unreachable, and the promises the
 * Privacy Policy and Terms make about "your account settings" quietly stop
 * being true — with every test on the page itself still green.
 *
 * Logout must finish clearing the session BEFORE the Header navigates to "/":
 * the landing page sends a signed-in visitor to the dashboard
 * (RedirectIfAuthenticated), so arriving there with `user` still set bounces
 * the person who just clicked "Logout" into the app and, once the session
 * clears, out to /login. The test holds `logout()` open and reads the router's
 * location on either side of the release.
 *
 * `useAuth` is the only mock; the router runs for real under MemoryRouter so
 * the link's resolved href and the post-logout location are the real ones.
 */
import { render, screen, act, fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import Header from "./Header";

const mocks = vi.hoisted(() => ({
  user: null as { name: string } | null,
  logout: vi.fn(),
}));

vi.mock("../features/auth/useAuth", () => ({
  useAuth: () => ({ user: mocks.user, logout: mocks.logout }),
}));

function LocationProbe() {
  const location = useLocation();
  return <div>at {location.pathname}</div>;
}

function renderHeader(initialPath = "/") {
  render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route
          path="*"
          element={
            <>
              <Header />
              <LocationProbe />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.user = null;
});

it("navigates to / only after logout() has settled", async () => {
  mocks.user = { name: "Ada Lovelace" };
  let release!: () => void;
  mocks.logout.mockImplementation(
    () => new Promise<void>((resolve) => { release = resolve; }),
  );
  renderHeader("/job-seeker/dashboard");

  await act(async () => {
    fireEvent.click(screen.getByTitle("Logout"));
  });

  // The request is in flight: the session is not cleared yet, so the Header
  // must not have moved. Navigating now would land on "/" signed in.
  expect(mocks.logout).toHaveBeenCalledTimes(1);
  expect(screen.getByText("at /job-seeker/dashboard")).toBeInTheDocument();

  await act(async () => { release(); });

  expect(await screen.findByText("at /")).toBeInTheDocument();
});

it("offers a gear into /settings when signed in", () => {
  mocks.user = { name: "Ada Lovelace" };
  renderHeader();

  const gear = screen.getByRole("link", { name: "Account settings" });
  expect(gear).toHaveAttribute("href", "/settings");
});

it("shows no settings entry point when signed out", () => {
  renderHeader();

  expect(screen.queryByRole("link", { name: "Account settings" })).toBeNull();
});
