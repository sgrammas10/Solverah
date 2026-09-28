/**
 * /search is an honest coming-soon screen until there is something to search.
 *
 * Regression: the page filtered `/me/recommendations` (always empty) by `?q=`,
 * so every query ended at "No results found for ..." with pagination and a
 * "Match score" waiting behind it, all in dark-theme colours on the cream page.
 * These tests pin that no fake search surface comes back and no request fires.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import SearchResults from "./SearchResults";
import { createQueryClient } from "../../../shared/api/queryClient";

const mocks = vi.hoisted(() => ({
  fetchWithAuth: vi.fn(),
}));

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({ fetchWithAuth: mocks.fetchWithAuth }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.fetchWithAuth.mockResolvedValue({ data: [], next_cursor: null });
});

function renderSearchResults(query = "react") {
  const { container } = render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[`/search?q=${encodeURIComponent(query)}`]}>
        <SearchResults />
      </MemoryRouter>
    </QueryClientProvider>
  );
  return container;
}

describe("SearchResults - coming soon", () => {
  it.each(["react", "", "   ", "xyzzy gibberish"])(
    "says search is coming soon for query %j",
    (query) => {
      renderSearchResults(query);
      expect(
        screen.getByRole("heading", { name: "Search is coming soon" }),
      ).toBeInTheDocument();
    },
  );

  it("makes no request, since there is nothing behind it yet", () => {
    renderSearchResults("react");
    expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
  });

  it("shows none of the fake search surface", () => {
    renderSearchResults("react");
    expect(screen.queryByText(/No results found/i)).toBeNull();
    expect(screen.queryByText(/Search results for/i)).toBeNull();
    expect(screen.queryByText(/Match score/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /next|previous/i })).toBeNull();
    // Echoing the query back would imply it was used.
    expect(screen.queryByText(/react/i)).toBeNull();
  });

  it("offers a way back to the dashboard", () => {
    renderSearchResults("react");
    expect(
      screen.getByRole("link", { name: "Back to your dashboard" }),
    ).toHaveAttribute("href", "/job-seeker/dashboard");
  });

  it("uses the cream palette, not the old dark theme", () => {
    const container = renderSearchResults("react");
    expect(container.innerHTML).not.toMatch(/slate-|emerald-|bg-white\/5|border-white\/10/);
    expect(container.firstElementChild).toHaveClass("bg-cream-base");
  });
});
