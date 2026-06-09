import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import SearchResults from "../SearchResults";

const mocks = vi.hoisted(() => ({
  fetchWithAuth: vi.fn(),
}));

vi.mock("../../contexts/useAuth", () => ({
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

function renderSearchResults(query = "react") {
  render(
    <MemoryRouter initialEntries={[`/search?q=${encodeURIComponent(query)}`]}>
      <SearchResults />
    </MemoryRouter>
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
      recommendations: [
        { ID: "1", Title: "Java Engineer", Company: "Corp", RoleDescription: "Java stuff", score: 0.5 },
      ],
    });
    renderSearchResults("python xyz noresult");
    await waitFor(() =>
      expect(screen.getByText(/No results found for/i)).toBeInTheDocument()
    );
  });

  it("shows no results when recommendations list is empty", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce({ recommendations: [] });
    renderSearchResults("anything");
    await waitFor(() =>
      expect(screen.getByText(/No results found for/i)).toBeInTheDocument()
    );
  });
});

// ─── happy path ────────────────────────────────────────────────────────────────

describe("SearchResults - happy path", () => {
  it("shows results heading with query", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce({ recommendations: MOCK_JOBS });
    renderSearchResults("react");
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /search results for/i })).toBeInTheDocument()
    );
  });

  it("renders matching job titles", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce({ recommendations: MOCK_JOBS });
    renderSearchResults("react");
    await waitFor(() =>
      expect(screen.getByText("Senior React Developer")).toBeInTheDocument()
    );
  });

  it("filters by title match", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce({ recommendations: MOCK_JOBS });
    renderSearchResults("python");
    await waitFor(() =>
      expect(screen.getByText("Python Backend Engineer")).toBeInTheDocument()
    );
    expect(screen.queryByText("Senior React Developer")).toBeNull();
  });

  it("shows all results when query is empty (returns all jobs)", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce({ recommendations: MOCK_JOBS });
    renderSearchResults("");
    await waitFor(() =>
      expect(screen.getByText("Senior React Developer")).toBeInTheDocument()
    );
    expect(screen.getByText("Python Backend Engineer")).toBeInTheDocument();
  });
});

// ─── expand / collapse ────────────────────────────────────────────────────────

describe("SearchResults - expand/collapse", () => {
  it("shows 'View more' when description is long, clicking expands it", async () => {
    const longDesc = "A".repeat(300);
    mocks.fetchWithAuth.mockResolvedValueOnce({
      recommendations: [
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
    mocks.fetchWithAuth.mockResolvedValueOnce({ recommendations: manyJobs });
    renderSearchResults("react");
    await waitFor(() => screen.getByRole("button", { name: /next/i }));
    expect(screen.getByRole("button", { name: /next/i })).toBeInTheDocument();
  });
});
