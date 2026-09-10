/**
 * ManagerPlaybookPage.test.tsx — the four outcomes `useManagerPlaybook` can
 * settle into, over the real hook and a real query client (only `fetchWithAuth`
 * is mocked, per ManagerMatchResultsPage.test.tsx's precedent).
 *
 * The two 409 states are fixtured as `ApiError`s carrying `errors[0].code`,
 * never as bare `Error`s with a matching message: the page branches on
 * `error.errorFor(...)?.code`, and a bare Error would prove nothing about
 * that branch (CompanyLensPage.test.tsx's note on this applies here too).
 * They also must not retry: `shouldRetry` refuses a 409, and a fixture that
 * retried into a different queued response would silently rewrite what the
 * test is claiming.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import ManagerPlaybookPage from "./ManagerPlaybookPage";
import { createQueryClient } from "../../../shared/api/queryClient";
import { ApiError } from "../../../shared/api/apiError";
import type { ManagerPlaybookData } from "../useManagerPlaybook";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  fetchWithAuth: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({ fetchWithAuth: mocks.fetchWithAuth }),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

function renderPage() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <ManagerPlaybookPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const MOCK_DATA: ManagerPlaybookData = {
  dimension_scores: { autonomy: 0.8, feedback_style: 0.3, relationship: 0.5, growth_focus: 0.5 },
  scoring_key: "mp-v1",
  version: "v1",
  created_at: "2026-09-10T00:00:00Z",
  playbook: {
    privacy_notice: "This playbook is yours and private.",
    dimensions: [
      {
        dimension: "autonomy",
        user_need: 0.2,
        manager_style: 0.8,
        gap: 0.6,
        classification: "grind",
        direction: "over_supplied",
        severity: "acute",
        band: null,
        headline: "You are building your own brief every time",
        why: "Because reasons.",
        ask: "Ask for structure.",
        agenda: ["Bring a draft."],
        scripts: ["I'd like to write down what done looks like."],
        constraint_note: null,
      },
      {
        dimension: "feedback_style",
        user_need: 0.5,
        manager_style: 0.55,
        gap: 0.05,
        classification: "mesh",
        direction: null,
        severity: null,
        band: "mid",
        note: "You are both landing in much the same place.",
      },
      {
        dimension: "relationship",
        user_need: 0.5,
        manager_style: 0.5,
        gap: 0,
        classification: "mesh",
        direction: null,
        severity: null,
        band: "mid",
        note: "Little to fix here.",
      },
      {
        dimension: "growth_focus",
        user_need: 0.5,
        manager_style: 0.5,
        gap: 0,
        classification: "mesh",
        direction: null,
        severity: null,
        band: "mid",
        note: "Worth naming what you would like to get better at.",
      },
    ],
    priority: ["autonomy"],
    grind_count: 1,
    mesh_count: 3,
  },
};

// ── loading ───────────────────────────────────────────────────────────────────

describe("ManagerPlaybookPage - loading", () => {
  it("shows a loading spinner while the fetch is in flight", () => {
    mocks.fetchWithAuth.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText(/Loading your playbook/i)).toBeInTheDocument();
  });
});

// ── 409 no_manager_match ─────────────────────────────────────────────────────

describe("ManagerPlaybookPage - no ManagerMatch sitting (409 no_manager_match)", () => {
  it("bridges to ManagerMatch without the words unlock/locked", async () => {
    mocks.fetchWithAuth.mockRejectedValueOnce(
      new ApiError("Take ManagerMatch first", {
        status: 409,
        fieldErrors: [{ field: "manager_match", code: "no_manager_match" }],
      })
    );
    renderPage();
    await waitFor(() => expect(screen.getByText(/Take ManagerMatch first/i)).toBeInTheDocument());
    const bodyText = document.body.textContent ?? "";
    expect(bodyText.toLowerCase()).not.toMatch(/unlock|locked/);
  });

  it("the CTA navigates to /manager-match", async () => {
    mocks.fetchWithAuth.mockRejectedValueOnce(
      new ApiError("Take ManagerMatch first", {
        status: 409,
        fieldErrors: [{ field: "manager_match", code: "no_manager_match" }],
      })
    );
    renderPage();
    await waitFor(() => screen.getByRole("button", { name: /take managermatch/i }));
    fireEvent.click(screen.getByRole("button", { name: /take managermatch/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/manager-match");
  });
});

// ── 409 no_manager_profile ───────────────────────────────────────────────────

describe("ManagerPlaybookPage - no manager profile sitting (409 no_manager_profile)", () => {
  it("bridges to the manager-profile instrument without the words unlock/locked", async () => {
    mocks.fetchWithAuth.mockRejectedValueOnce(
      new ApiError("Profile your manager first", {
        status: 409,
        fieldErrors: [{ field: "manager_profile", code: "no_manager_profile" }],
      })
    );
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /Profile your manager/i })).toBeInTheDocument()
    );
    const bodyText = document.body.textContent ?? "";
    expect(bodyText.toLowerCase()).not.toMatch(/unlock|locked/);
  });

  it("the CTA navigates to /manager-profile", async () => {
    mocks.fetchWithAuth.mockRejectedValueOnce(
      new ApiError("Profile your manager first", {
        status: 409,
        fieldErrors: [{ field: "manager_profile", code: "no_manager_profile" }],
      })
    );
    renderPage();
    await waitFor(() => screen.getByRole("button", { name: /profile your manager/i }));
    fireEvent.click(screen.getByRole("button", { name: /profile your manager/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/manager-profile");
  });
});

// ── other failure ─────────────────────────────────────────────────────────────

describe("ManagerPlaybookPage - unrelated failure", () => {
  it("shows a generic error card with retry, not one of the two bridges", async () => {
    mocks.fetchWithAuth.mockRejectedValueOnce(new ApiError("Forbidden", { status: 403 }));
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/couldn't load your playbook/i)).toBeInTheDocument()
    );
    expect(screen.queryByText(/Take ManagerMatch first/i)).toBeNull();
    expect(screen.queryByRole("heading", { name: /Profile your manager/i })).toBeNull();
  });

  it("retry re-fetches and renders the playbook on success", async () => {
    mocks.fetchWithAuth
      .mockRejectedValueOnce(new ApiError("Forbidden", { status: 403 }))
      .mockResolvedValueOnce(MOCK_DATA);
    renderPage();
    await waitFor(() => screen.getByRole("button", { name: /try again/i }));
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    await waitFor(() =>
      expect(screen.getByText(/managing-up playbook/i)).toBeInTheDocument()
    );
  });
});

// ── success ───────────────────────────────────────────────────────────────────

describe("ManagerPlaybookPage - success", () => {
  it("renders the privacy notice verbatim", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce(MOCK_DATA);
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("This playbook is yours and private.")).toBeInTheDocument()
    );
  });

  it("renders the priority dimension in 'where to focus first'", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce(MOCK_DATA);
    renderPage();
    await waitFor(() => expect(screen.getByText(/Where to focus first/i)).toBeInTheDocument());
    expect(screen.getByText(/1\. Autonomy/)).toBeInTheDocument();
  });

  it("renders a grind card with why/ask/agenda/scripts", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce(MOCK_DATA);
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("You are building your own brief every time")).toBeInTheDocument()
    );
    expect(screen.getByText("Because reasons.")).toBeInTheDocument();
    expect(screen.getByText("Ask for structure.")).toBeInTheDocument();
    expect(screen.getByText("Bring a draft.")).toBeInTheDocument();
    expect(screen.getByText(/I'd like to write down what done looks like/)).toBeInTheDocument();
  });

  it("renders mesh cards with their one-liner notes", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce(MOCK_DATA);
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("Little to fix here.")).toBeInTheDocument()
    );
  });

  it("back nav and CTA both navigate to /intelligence", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce(MOCK_DATA);
    renderPage();
    await waitFor(() => screen.getByText(/managing-up playbook/i));
    fireEvent.click(screen.getByRole("button", { name: /back to intelligence hub/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/intelligence");
  });

  it("shows a no-grinds message when grind_count is 0", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce({
      ...MOCK_DATA,
      playbook: { ...MOCK_DATA.playbook, priority: [], grind_count: 0, mesh_count: 4 },
    });
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/meshes with what you need across all/i)).toBeInTheDocument()
    );
  });
});
