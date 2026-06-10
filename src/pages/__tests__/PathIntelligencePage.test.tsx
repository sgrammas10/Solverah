import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import PathIntelligencePage from "../PathIntelligencePage";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  fetchWithAuth: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => mocks.navigate,
  };
});

vi.mock("../../contexts/useAuth", () => ({
  useAuth: () => ({ fetchWithAuth: mocks.fetchWithAuth }),
}));

beforeEach(() => {
  vi.clearAllMocks();
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
