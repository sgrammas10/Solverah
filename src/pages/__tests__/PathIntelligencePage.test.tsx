import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import PathIntelligencePage from "../PathIntelligencePage";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  fetchWithAuth: vi.fn(),
  user: {} as Record<string, unknown>,
  profile: { path_preferences: { move_type: "stay_in_field" } } as Record<string, unknown>,
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => mocks.navigate,
  };
});

vi.mock("../../contexts/useAuth", () => ({
  useAuth: () => ({ fetchWithAuth: mocks.fetchWithAuth, user: mocks.user }),
}));

// Experience, skills and path preferences come from the profile query now.
vi.mock("../../hooks/useProfile", () => ({
  // The query hook, resolved. `isLoading: false` is the point: consumers
  // branch on it, and a mock that omitted it would report undefined --
  // falsy, so the branches would run, but by accident rather than intent.
  useProfile: () => ({ data: mocks.profile, isLoading: false }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.profile = { path_preferences: { move_type: "stay_in_field" } };
});

function renderPage() {
  render(
    <MemoryRouter>
      <PathIntelligencePage />
    </MemoryRouter>
  );
}

// ─── loading state ─────────────────────────────────────────────────────────

describe("PathIntelligencePage - loading state", () => {
  it("shows 3 skeleton cards on mount", () => {
    mocks.fetchWithAuth.mockReturnValue(new Promise(() => {}));
    renderPage();
    const container = screen.getByLabelText(/loading suggestions/i);
    expect(container).toBeInTheDocument();
    expect(container.children).toHaveLength(3);
  });
});

// ─── error state ───────────────────────────────────────────────────────────

describe("PathIntelligencePage - error state", () => {
  it("shows error message when fetch fails", async () => {
    mocks.fetchWithAuth.mockRejectedValueOnce(new Error("Server error"));
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByText(/couldn't load your path suggestions/i)
      ).toBeInTheDocument()
    );
  });

  it("retry button re-calls the endpoint", async () => {
    mocks.fetchWithAuth
      .mockRejectedValueOnce(new Error("first failure"))
      .mockRejectedValueOnce(new Error("second failure"));
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument()
    );
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    await waitFor(() => expect(mocks.fetchWithAuth).toHaveBeenCalledTimes(2));
  });
});

// ─── career status not set ─────────────────────────────────────────────────

describe("PathIntelligencePage - career status not set", () => {
  it("renders the career status onboarding prompt when API returns career_status_not_set", async () => {
    mocks.fetchWithAuth.mockRejectedValueOnce(
      new Error("career_status_not_set")
    );
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByText(/set your career status/i)
      ).toBeInTheDocument()
    );
  });
});

// ─── skill proficiency modal ───────────────────────────────────────────────

const baseUser = mocks.user;

describe("PathIntelligencePage - skill proficiency modal", () => {
  afterEach(() => {
    mocks.user = baseUser;
  });

  it("shows proficiency modal on first PI visit when skills are unrated", () => {
    mocks.profile = {
      path_preferences: { move_type: "stay_in_field" },
      skills: ["React", "Python"],
      skills_proficiency_confirmed: false,
    };

    renderPage();
    expect(screen.getByText("Rate your skills")).toBeInTheDocument();
  });

  it("skip closes modal and shows nudge banner after results load", async () => {
    mocks.profile = {
      path_preferences: { move_type: "stay_in_field" },
      skills: ["React"],
      skills_proficiency_confirmed: false,
    };
    mocks.fetchWithAuth.mockResolvedValueOnce({
      suggestions: [],
      career_status: "employed",
    });

    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /skip for now/i }));

    await waitFor(() =>
      expect(
        screen.getByText(/rate your skills to get more accurate/i)
      ).toBeInTheDocument()
    );
  });

  it("saving ratings PATCHes proficiency then re-fetches suggestions", async () => {
    mocks.profile = {
      path_preferences: { move_type: "stay_in_field" },
      skills: ["React"],
      skills_proficiency_confirmed: false,
    };
    mocks.fetchWithAuth
      .mockResolvedValueOnce({ skills_proficiency_confirmed: true, skill_levels: {} })
      .mockResolvedValueOnce({ suggestions: [], career_status: "employed" });

    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /save & continue/i }));

    await waitFor(() =>
      expect(mocks.fetchWithAuth).toHaveBeenCalledWith(
        "/me/skills",
        expect.objectContaining({ method: "PUT" })
      )
    );
    await waitFor(() =>
      expect(mocks.fetchWithAuth).toHaveBeenCalledWith(
        "/me/path-suggestions"
      )
    );
  });
});
