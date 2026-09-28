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
import { render, screen, act, fireEvent, within } from "@testing-library/react";
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

it("offers the landing page's Sign in / Get started pair when signed out", () => {
  renderHeader("/login");

  expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  const start = screen.getByRole("link", { name: "Get started" });
  expect(start).toHaveAttribute("href", "/register");
  expect(start).toHaveClass("rounded-[4px]");
});

/**
 * Regression: the Feed modal was rendered INSIDE <header>, which carries
 * `backdrop-blur`. A backdrop-filter makes the header the containing block for
 * `position: fixed` descendants, so the "fullscreen" overlay was trapped in the
 * 64px bar and showed in the top-left corner. jsdom does no layout, so the
 * test asserts the structural cause: the dialog must not live under <header>.
 */
describe("Feed coming-soon modal", () => {
  it("renders outside the header so the header's backdrop-filter cannot trap it", () => {
    mocks.user = { name: "Ada Lovelace" };
    renderHeader("/job-seeker/dashboard");

    fireEvent.click(screen.getByRole("link", { name: "Feed" }));

    const dialog = screen.getByRole("dialog", { name: "Feature coming soon" });
    const header = document.querySelector("header")!;
    expect(header.contains(dialog)).toBe(false);
    expect(dialog.parentElement).toBe(document.body);
    // The product has launched: the copy must not tell people to wait for it.
    expect(dialog).not.toHaveTextContent(/after launch/i);
    // The Feed link opens the modal; it does not navigate.
    expect(screen.getByText("at /job-seeker/dashboard")).toBeInTheDocument();
  });

  it("closes on Got it and on Escape", () => {
    mocks.user = { name: "Ada Lovelace" };
    renderHeader("/job-seeker/dashboard");

    fireEvent.click(screen.getByRole("link", { name: "Feed" }));
    fireEvent.click(screen.getByRole("button", { name: "Got it" }));
    expect(screen.queryByRole("dialog")).toBeNull();

    fireEvent.click(screen.getByRole("link", { name: "Feed" }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("print", () => {
  it("keeps the header off printed pages", () => {
    mocks.user = { name: "Ada Lovelace" };
    renderHeader("/job-seeker/dashboard");
    expect(document.querySelector("header")).toHaveClass("print:hidden");
  });
});

/**
 * Regression: the signed-in nav was one unwrapped flex row (five links, the
 * name, the gear, logout) and ran off the side of a phone. The desktop row is
 * now `hidden md:flex`; below md a menu button opens the same links.
 */
describe("mobile menu", () => {
  beforeEach(() => {
    mocks.user = { name: "Ada Lovelace" };
  });

  it("hides the inline nav below md and offers a menu button there instead", () => {
    renderHeader("/job-seeker/dashboard");

    expect(screen.getByRole("navigation", { name: "Main" })).toHaveClass("hidden", "md:flex");
    const toggle = screen.getByRole("button", { name: "Open menu" });
    expect(toggle).toHaveClass("md:hidden");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("navigation", { name: "Mobile" })).toBeNull();
  });

  it("opens a panel with every link, the settings entry and logout", () => {
    renderHeader("/job-seeker/dashboard");

    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));

    expect(screen.getByRole("button", { name: "Close menu" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    const panel = screen.getByRole("navigation", { name: "Mobile" });
    for (const name of ["Feed", "Dashboard", "Intelligence", "Profile", "Agent", "Settings"]) {
      expect(within(panel).getByRole("link", { name })).toBeInTheDocument();
    }
    expect(within(panel).getByRole("link", { name: "Settings" })).toHaveAttribute(
      "href",
      "/settings",
    );
    expect(within(panel).getByRole("button", { name: "Log out" })).toBeInTheDocument();
  });

  it("closes when a link is followed", () => {
    renderHeader("/job-seeker/dashboard");

    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
    const panel = screen.getByRole("navigation", { name: "Mobile" });
    fireEvent.click(within(panel).getByRole("link", { name: "Agent" }));

    expect(screen.getByText("at /agent")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Mobile" })).toBeNull();
    expect(screen.getByRole("button", { name: "Open menu" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("closes on Escape", () => {
    renderHeader("/job-seeker/dashboard");

    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.queryByRole("navigation", { name: "Mobile" })).toBeNull();
  });

  it("opens the Feed modal from the menu and closes the menu", () => {
    renderHeader("/job-seeker/dashboard");

    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
    const panel = screen.getByRole("navigation", { name: "Mobile" });
    fireEvent.click(within(panel).getByRole("link", { name: "Feed" }));

    expect(screen.getByRole("dialog", { name: "Feature coming soon" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Mobile" })).toBeNull();
  });
});
