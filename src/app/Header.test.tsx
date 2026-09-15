/**
 * Header.test.tsx — the signed-in entry point to /settings.
 *
 * The gear is the ONLY way into account settings: nothing links to /settings
 * from the body of the app, and no dropdown exists to hide it in. If it stops
 * rendering, the page is still routable but unreachable, and the promises the
 * Privacy Policy and Terms make about "your account settings" quietly stop
 * being true — with every test on the page itself still green.
 *
 * `useAuth` is the only mock; the router runs for real under MemoryRouter so
 * the link's resolved href is the real one.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import Header from "./Header";

const mocks = vi.hoisted(() => ({
  user: null as { name: string } | null,
  logout: vi.fn(),
}));

vi.mock("../features/auth/useAuth", () => ({
  useAuth: () => ({ user: mocks.user, logout: mocks.logout }),
}));

function renderHeader() {
  render(
    <MemoryRouter>
      <Header />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.user = null;
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
