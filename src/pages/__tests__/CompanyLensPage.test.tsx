import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import CompanyLensPage from "../CompanyLensPage";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  fetchWithAuth: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../contexts/useAuth", () => ({
  useAuth: () => ({ fetchWithAuth: mocks.fetchWithAuth }),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

/**
 * One page of `GET /api/v1/me/matches`.
 *
 * Phase 1b replaced `GET /company-lens/matches`, which returned `best_fits` and
 * `worst_fits` in a single body, with a cursor-paginated ranking that `?order=`
 * reads from either end. The screen still shows both ends, so it now issues two
 * requests -- which is what `mockMatchesOnce` below exists to queue.
 */
const BEST_FITS = [
  {
    id: 1,
    name: "Stripe",
    slug: "stripe",
    industry: "Fintech",
    fit_score: 0.91,
    top_matching_dimensions: ["empathy", "creative_drive"],
    top_mismatching_dimensions: [],
    fit_summary: "Strong match for your work style.",
  },
  {
    id: 2,
    name: "Notion",
    slug: "notion",
    industry: "Productivity",
    fit_score: 0.85,
    top_matching_dimensions: ["harmony"],
    top_mismatching_dimensions: ["pace"],
    fit_summary: "Good overall alignment.",
  },
];

const WORST_FITS = [
  {
    id: 3,
    name: "Goldman Sachs",
    slug: "goldman-sachs",
    industry: "Finance",
    fit_score: 0.31,
    top_matching_dimensions: [],
    top_mismatching_dimensions: ["empathy", "harmony"],
    fit_summary: "High-pressure environment may not suit you.",
  },
];

function page(data: unknown[], order: string) {
  return {
    data,
    next_cursor: null,
    total_companies_scored: 100,
    lens: "culture",
    order,
  };
}

/** Queue the pair of responses one render of this screen consumes. */
function mockMatchesOnce() {
  mocks.fetchWithAuth
    .mockResolvedValueOnce(page(BEST_FITS, "best"))
    .mockResolvedValueOnce(page(WORST_FITS, "worst"));
}

function renderCompanyLensPage() {
  render(
    <MemoryRouter>
      <CompanyLensPage />
    </MemoryRouter>
  );
}

// ─── loading state ─────────────────────────────────────────────────────────────

describe("CompanyLensPage - loading state", () => {
  it("shows loading spinner on mount", () => {
    mocks.fetchWithAuth.mockReturnValue(new Promise(() => {}));
    renderCompanyLensPage();
    expect(screen.getByText(/Scoring companies/i)).toBeInTheDocument();
  });
});

// ─── happy path ────────────────────────────────────────────────────────────────

describe("CompanyLensPage - happy path", () => {
  it("renders section headings after fetch", async () => {
    mockMatchesOnce();
    renderCompanyLensPage();
    await waitFor(() =>
      expect(screen.getByText(/Companies that match how you work/i)).toBeInTheDocument()
    );
    expect(screen.getByText(/Companies worth understanding/i)).toBeInTheDocument();
  });

  it("renders best-fit company names", async () => {
    mockMatchesOnce();
    renderCompanyLensPage();
    await waitFor(() => expect(screen.getByText("Stripe")).toBeInTheDocument());
    expect(screen.getByText("Notion")).toBeInTheDocument();
  });

  it("renders worst-fit company names", async () => {
    mockMatchesOnce();
    renderCompanyLensPage();
    await waitFor(() => expect(screen.getByText("Goldman Sachs")).toBeInTheDocument());
  });

  it("renders fit score percentages", async () => {
    mockMatchesOnce();
    renderCompanyLensPage();
    await waitFor(() => expect(screen.getByText("91% match")).toBeInTheDocument());
  });
});

// ─── no-prefs state ────────────────────────────────────────────────────────────

describe("CompanyLensPage - no-prefs state", () => {
  it("shows 'Complete Work Pulse' CTA when culture preferences missing", async () => {
    mocks.fetchWithAuth
      .mockRejectedValueOnce(new Error("culture preferences not set"))
      .mockRejectedValueOnce(new Error("culture preferences not set"));
    renderCompanyLensPage();
    await waitFor(() =>
      expect(screen.getByText(/Complete Work Pulse to unlock CompanyLens/i)).toBeInTheDocument()
    );
  });

  it("navigates to /work-pulse when 'Start Work Pulse' clicked", async () => {
    mocks.fetchWithAuth
      .mockRejectedValueOnce(new Error("Work Pulse not completed"))
      .mockRejectedValueOnce(new Error("Work Pulse not completed"));
    renderCompanyLensPage();
    await waitFor(() => screen.getByRole("button", { name: /start work pulse/i }));
    fireEvent.click(screen.getByRole("button", { name: /start work pulse/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/work-pulse");
  });
});

// ─── error handling ────────────────────────────────────────────────────────────

describe("CompanyLensPage - error handling", () => {
  it("shows error UI on fetch failure", async () => {
    mocks.fetchWithAuth
      .mockRejectedValueOnce(new Error("API down"))
      .mockRejectedValueOnce(new Error("API down"));
    renderCompanyLensPage();
    await waitFor(() =>
      expect(screen.getByText(/Couldn't load your company matches/i)).toBeInTheDocument()
    );
  });

  it("retry button re-fetches successfully", async () => {
    // The failed attempt consumes both of its calls before the retry's pair.
    mocks.fetchWithAuth
      .mockRejectedValueOnce(new Error("API down"))
      .mockRejectedValueOnce(new Error("API down"));
    renderCompanyLensPage();
    await waitFor(() => screen.getByRole("button", { name: /try again/i }));
    mockMatchesOnce();
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    await waitFor(() => expect(screen.getByText("Stripe")).toBeInTheDocument());
  });
});

// ─── view toggle ──────────────────────────────────────────────────────────────

describe("CompanyLensPage - view toggle", () => {
  it("toggles to list view when list icon clicked", async () => {
    mockMatchesOnce();
    renderCompanyLensPage();
    await waitFor(() => screen.getByTitle("List view"));
    fireEvent.click(screen.getByTitle("List view"));
    // List view still shows the same company names
    expect(screen.getByText("Stripe")).toBeInTheDocument();
  });
});

// ─── navigation ───────────────────────────────────────────────────────────────

describe("CompanyLensPage - navigation", () => {
  it("back to intelligence button navigates to /intelligence", async () => {
    mockMatchesOnce();
    renderCompanyLensPage();
    await waitFor(() => screen.getByText(/back to intelligence/i));
    fireEvent.click(screen.getByText(/back to intelligence/i));
    expect(mocks.navigate).toHaveBeenCalledWith("/intelligence");
  });

  it("clicking a company card navigates to the company detail page", async () => {
    mockMatchesOnce();
    renderCompanyLensPage();
    await waitFor(() => screen.getAllByText("View company profile →")[0]);
    fireEvent.click(screen.getAllByText("View company profile →")[0]);
    expect(mocks.navigate).toHaveBeenCalledWith(
      "/companies/1",
      expect.objectContaining({ state: expect.objectContaining({ fit_score: 0.91 }) })
    );
  });
});


// ─── de-duplication across the two ends ───────────────────────────────────────

describe("CompanyLensPage - overlapping ends", () => {
  it("does not render a company in both lists", async () => {
    // The endpoint this screen replaced partitioned at the midpoint so a
    // company could never appear in both slices. A paginated ranking cannot do
    // that -- with few companies the two orders genuinely overlap -- so the
    // screen filters the weak end against the strong one.
    mocks.fetchWithAuth
      .mockResolvedValueOnce(page(BEST_FITS, "best"))
      .mockResolvedValueOnce(page([...BEST_FITS].reverse(), "worst"));

    renderCompanyLensPage();

    await waitFor(() => expect(screen.getByText("Stripe")).toBeInTheDocument());
    expect(screen.getAllByText("Stripe")).toHaveLength(1);
    expect(screen.getAllByText("Notion")).toHaveLength(1);
  });
});
