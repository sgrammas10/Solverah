import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import SearchResults from "./SearchResults";
import { createQueryClient } from "../../../shared/api/queryClient";
import { ApiError } from "../../../shared/api/apiError";

const mocks = vi.hoisted(() => ({
  fetchWithAuth: vi.fn(),
}));

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({ fetchWithAuth: mocks.fetchWithAuth }),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

const MOCK_JOBS = [
  {
    ID: "1",
    Title: "Senior React Developer",
    Company: "Acme Corp",
    Location: "New York, NY",
    EmploymentType: "Full-time",
    RoleDescription: "Build enterprise-scale React applications.",
    score: 0.92,
    Link: "https://acme.com/jobs/1",
  },
  {
    ID: "2",
    Title: "Python Backend Engineer",
    Company: "Globex",
    Location: "Remote",
    EmploymentType: "Contract",
    RoleDescription: "Develop Python microservices.",
    score: 0.75,
    Link: "https://globex.com/jobs/2",
  },
];

/** The recommendations query needs a client; fresh per render, per the
 *  useProfileForm.test precedent, so no cache entry leaks between tests. */
function renderSearchResults(query = "react") {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[`/search?q=${encodeURIComponent(query)}`]}>
        <SearchResults />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ─── loading state ─────────────────────────────────────────────────────────────

describe("SearchResults - loading state", () => {
  it("shows loading indicator while fetching", () => {
    mocks.fetchWithAuth.mockReturnValue(new Promise(() => {}));
    renderSearchResults();
    // Loading renders a spinning Search icon; no results text yet
    expect(screen.queryByText(/Search results for/i)).toBeNull();
  });
});

// ─── empty state ──────────────────────────────────────────────────────────────

describe("SearchResults - empty state", () => {
  it("shows no results message when no jobs match the query", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce({
      data: [
        { ID: "1", Title: "Java Engineer", Company: "Corp", RoleDescription: "Java stuff", score: 0.5 },
      ],
    });
    renderSearchResults("python xyz noresult");
    await waitFor(() =>
      expect(screen.getByText(/No results found for/i)).toBeInTheDocument()
    );
  });

  it("shows no results when recommendations list is empty", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce({ data: [], next_cursor: null });
    renderSearchResults("anything");
    await waitFor(() =>
      expect(screen.getByText(/No results found for/i)).toBeInTheDocument()
    );
  });
});

// ─── failed fetch (G15) ────────────────────────────────────────────────────────

/**
 * Regression: `data ?? []` used to read a failed `/me/recommendations` fetch
 * as an empty list, which rendered as "No results found" -- indistinguishable
 * from a real search that came up empty.
 */
describe("SearchResults - failed fetch (G15)", () => {
  it("shows a retry notice rather than 'No results found'", async () => {
    mocks.fetchWithAuth.mockRejectedValue(new ApiError("boom", { status: 403 }));
    renderSearchResults("react");

    expect(
      await screen.findByText(/We couldn't run that search right now/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/No results found/i)).toBeNull();
  });

  it("refetches when Try again is clicked", async () => {
    mocks.fetchWithAuth
      .mockRejectedValueOnce(new ApiError("boom", { status: 403 }))
      .mockResolvedValueOnce({ data: MOCK_JOBS, next_cursor: null });
    renderSearchResults("react");

    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));

    expect(
      await screen.findByRole("heading", { name: /search results for/i }),
    ).toBeInTheDocument();
  });
});

// ─── happy path ────────────────────────────────────────────────────────────────

describe("SearchResults - happy path", () => {
  it("shows results heading with query", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce({ data: MOCK_JOBS, next_cursor: null });
    renderSearchResults("react");
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /search results for/i })).toBeInTheDocument()
    );
  });

  it("renders matching job titles", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce({ data: MOCK_JOBS, next_cursor: null });
    renderSearchResults("react");
    await waitFor(() =>
      expect(screen.getByText("Senior React Developer")).toBeInTheDocument()
    );
  });

  it("filters by title match", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce({ data: MOCK_JOBS, next_cursor: null });
    renderSearchResults("python");
    await waitFor(() =>
      expect(screen.getByText("Python Backend Engineer")).toBeInTheDocument()
    );
    expect(screen.queryByText("Senior React Developer")).toBeNull();
  });

});

// ─── empty query ──────────────────────────────────────────────────────────────

describe("SearchResults - empty query", () => {
  it("shows an invitation to search instead of querying when the query is empty", async () => {
    renderSearchResults("");
    await waitFor(() =>
      expect(screen.getByText(/search for companies and roles/i)).toBeInTheDocument()
    );
    expect(screen.queryByText(/no results found/i)).toBeNull();
    expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
  });

  it("shows an invitation to search instead of querying when the query is whitespace-only", async () => {
    renderSearchResults("   ");
    await waitFor(() =>
      expect(screen.getByText(/search for companies and roles/i)).toBeInTheDocument()
    );
    expect(screen.queryByText(/no results found/i)).toBeNull();
    expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
  });
});

// ─── expand / collapse ────────────────────────────────────────────────────────

describe("SearchResults - expand/collapse", () => {
  it("shows 'View more' when description is long, clicking expands it", async () => {
    const longDesc = "A".repeat(300);
    mocks.fetchWithAuth.mockResolvedValueOnce({
      data: [
        { ID: "1", Title: "React Dev", Company: "Co", RoleDescription: longDesc, score: 0.9, Link: "#" },
      ],
    });
    renderSearchResults("react");
    await waitFor(() => screen.getByRole("button", { name: /view more/i }));
    fireEvent.click(screen.getByRole("button", { name: /view more/i }));
    expect(screen.getByRole("button", { name: /view less/i })).toBeInTheDocument();
  });
});

// ─── pagination ───────────────────────────────────────────────────────────────

describe("SearchResults - pagination", () => {
  it("shows pagination controls when there are more than 5 results", async () => {
    const manyJobs = Array.from({ length: 8 }, (_, i) => ({
      ID: String(i),
      Title: `React Engineer ${i}`,
      Company: "Corp",
      Location: "NY",
      EmploymentType: "Full-time",
      RoleDescription: "React work.",
      score: 0.8,
      Link: "#",
    }));
    mocks.fetchWithAuth.mockResolvedValueOnce({ data: manyJobs, next_cursor: null });
    renderSearchResults("react");
    await waitFor(() => screen.getByRole("button", { name: /next/i }));
    expect(screen.getByRole("button", { name: /next/i })).toBeInTheDocument();
  });
});
