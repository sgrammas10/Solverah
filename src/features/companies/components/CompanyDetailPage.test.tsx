import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import CompanyDetailPage from "./CompanyDetailPage";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  fetchWithAuth: vi.fn(),
  params: { id: "42" },
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => mocks.navigate,
    useParams: () => mocks.params,
  };
});

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({ fetchWithAuth: mocks.fetchWithAuth }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.params = { id: "42" };
});

const MOCK_COMPANY: any = {
  id: 42,
  name: "Acme Corp",
  slug: "acme-corp",
  profile: {
    overview: {
      name: "Acme Corp",
      industry: "Technology",
      size: "500-1000",
      headquarters: "San Francisco, CA",
      website: "https://acme.com",
    },
    culture: {
      culture_narrative_company: "We value innovation.",
      culture_narrative_employees: "Great place to work.",
      core_values: ["Integrity", "Innovation"],
    },
    glassdoor: {
      overall_rating: 4.2,
      work_life_balance: 3.8,
      key_positives: "Excellent benefits",
      key_negatives: "Long hours",
    },
    interview: {
      difficulty: "Medium",
      process_overview: "Three rounds of interviews.",
    },
    compensation: {
      new_grad_swe_total: "$120k",
      mid_level_total: "$160k",
      senior_total: "$200k",
    },
    workforce_signals: {
      warn_risk_level: "low",
      analyst_summary: "Stable workforce outlook.",
    },
    tech_stack: {
      frontend: "React",
      backend: "Python",
    },
  },
};

function renderCompanyDetailPage(locationState?: object) {
  render(
    <MemoryRouter initialEntries={[{ pathname: "/companies/42", state: locationState }]}>
      <CompanyDetailPage />
    </MemoryRouter>
  );
}

// ─── loading state ─────────────────────────────────────────────────────────────

describe("CompanyDetailPage - loading state", () => {
  it("shows loading spinner on mount", () => {
    mocks.fetchWithAuth.mockReturnValue(new Promise(() => {}));
    renderCompanyDetailPage();
    expect(screen.getByText(/Loading company profile/i)).toBeInTheDocument();
  });
});

// ─── happy path ────────────────────────────────────────────────────────────────

describe("CompanyDetailPage - happy path", () => {
  it("renders company name after successful fetch", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce(MOCK_COMPANY);
    renderCompanyDetailPage();
    await waitFor(() => expect(screen.getByText("Acme Corp")).toBeInTheDocument());
  });

  it("renders industry, size, headquarters", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce(MOCK_COMPANY);
    renderCompanyDetailPage();
    await waitFor(() => expect(screen.getByText(/Technology/)).toBeInTheDocument());
    expect(screen.getByText(/San Francisco, CA/)).toBeInTheDocument();
  });

  it("renders culture narrative", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce(MOCK_COMPANY);
    renderCompanyDetailPage();
    await waitFor(() => expect(screen.getByText("We value innovation.")).toBeInTheDocument());
    expect(screen.getByText("Great place to work.")).toBeInTheDocument();
  });

  it("renders core values as chips", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce(MOCK_COMPANY);
    renderCompanyDetailPage();
    await waitFor(() => expect(screen.getByText("Integrity")).toBeInTheDocument());
    expect(screen.getByText("Innovation")).toBeInTheDocument();
  });

  it("renders Glassdoor ratings", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce(MOCK_COMPANY);
    renderCompanyDetailPage();
    await waitFor(() => expect(screen.getByText("4.2")).toBeInTheDocument());
  });

  it("renders tech stack", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce(MOCK_COMPANY);
    renderCompanyDetailPage();
    await waitFor(() => expect(screen.getByText("React")).toBeInTheDocument());
    expect(screen.getByText("Python")).toBeInTheDocument();
  });

  it("fetches from the correct endpoint using the id param", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce(MOCK_COMPANY);
    renderCompanyDetailPage();
    await waitFor(() => expect(mocks.fetchWithAuth).toHaveBeenCalledWith("/companies/42"));
  });
});

// ─── fit score banner ─────────────────────────────────────────────────────────

describe("CompanyDetailPage - fit score banner", () => {
  it("shows fit score when location state has fit data", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce(MOCK_COMPANY);
    renderCompanyDetailPage({
      fit_score: 0.82,
      top_matching_dimensions: ["empathy", "harmony"],
      top_mismatching_dimensions: ["pace"],
    });
    await waitFor(() => expect(screen.getByText("82%")).toBeInTheDocument());
  });

  it("does not show fit banner when no location state", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce(MOCK_COMPANY);
    renderCompanyDetailPage();
    await waitFor(() => expect(screen.getByText("Acme Corp")).toBeInTheDocument());
    expect(screen.queryByText(/CompanyLens™ fit score/i)).toBeNull();
  });
});

// ─── error handling ────────────────────────────────────────────────────────────

describe("CompanyDetailPage - error handling", () => {
  it("shows error UI when fetch fails", async () => {
    mocks.fetchWithAuth.mockRejectedValueOnce(new Error("API error"));
    renderCompanyDetailPage();
    await waitFor(() =>
      expect(screen.getByText(/Couldn't load this company profile/i)).toBeInTheDocument()
    );
  });

  it("retry button re-fetches and shows results on success", async () => {
    mocks.fetchWithAuth
      .mockRejectedValueOnce(new Error("first failure"))
      .mockResolvedValueOnce(MOCK_COMPANY);
    renderCompanyDetailPage();
    await waitFor(() => expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    await waitFor(() => expect(screen.getByText("Acme Corp")).toBeInTheDocument());
  });
});

// ─── navigation ───────────────────────────────────────────────────────────────

describe("CompanyDetailPage - navigation", () => {
  it("back button calls navigate(-1)", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce(MOCK_COMPANY);
    renderCompanyDetailPage();
    await waitFor(() => expect(screen.getByText(/back to companies/i)).toBeInTheDocument());
    fireEvent.click(screen.getByText(/back to companies/i));
    expect(mocks.navigate).toHaveBeenCalledWith(-1);
  });
});
