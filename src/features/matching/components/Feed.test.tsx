/**
 * /feed is an honest coming-soon screen until there is a feed.
 *
 * Regression: the page showed a search box, a dead Filters button, three tabs,
 * "Your Stats" at "--" and an always-empty recommendations list, in dark-theme
 * colours on the cream page. These tests pin that none of that comes back and
 * that no request fires.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import Feed from "./Feed";
import { createQueryClient } from "../../../shared/api/queryClient";

const mocks = vi.hoisted(() => ({
  user: { name: "Ada Lovelace" } as { name?: string } | null,
  fetchWithAuth: vi.fn(),
}));

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({ user: mocks.user, fetchWithAuth: mocks.fetchWithAuth }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.user = { name: "Ada Lovelace" };
  mocks.fetchWithAuth.mockResolvedValue({ data: [], next_cursor: null });
});

function renderFeed() {
  const { container } = render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <Feed />
      </MemoryRouter>
    </QueryClientProvider>
  );
  return container;
}

describe("Feed - coming soon", () => {
  it("greets the user by first name", () => {
    renderFeed();
    expect(screen.getByRole("heading", { name: "Your feed, Ada" })).toBeInTheDocument();
  });

  it("falls back to a plain heading without a name", () => {
    mocks.user = null;
    renderFeed();
    expect(screen.getByRole("heading", { name: "Your feed" })).toBeInTheDocument();
  });

  it("says the feed is coming soon", () => {
    renderFeed();
    expect(
      screen.getByRole("heading", { name: "The feed is coming soon" }),
    ).toBeInTheDocument();
  });

  it("makes no request, since nothing behind it is wired", () => {
    renderFeed();
    expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
  });

  it("shows none of the unwired surface", () => {
    renderFeed();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("button", { name: /filters|job feed|messages|notifications/i })).toBeNull();
    expect(screen.queryByText(/Your Stats/i)).toBeNull();
    expect(screen.queryByText(/Match score/i)).toBeNull();
  });

  it("points to the parts of the product that work", () => {
    renderFeed();
    expect(screen.getByRole("link", { name: "Go to your dashboard" })).toHaveAttribute(
      "href",
      "/job-seeker/dashboard",
    );
    expect(screen.getByRole("link", { name: "Open Intelligence" })).toHaveAttribute(
      "href",
      "/intelligence",
    );
  });

  it("uses the cream palette, not the old dark theme", () => {
    const container = renderFeed();
    expect(container.innerHTML).not.toMatch(/slate-|emerald-|bg-white\/5|border-white\/10/);
    expect(container.firstElementChild).toHaveClass("bg-cream-base");
  });
});
