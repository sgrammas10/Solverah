import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import FocusTypePage from "../FocusTypePage";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  fetchWithAuth: vi.fn(),
  updateProfileData: vi.fn(),
  user: null as any,
  locationState: null as any,
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../contexts/useAuth", () => ({
  useAuth: () => ({
    fetchWithAuth: mocks.fetchWithAuth,
    updateProfileData: mocks.updateProfileData,
    user: mocks.user,
  }),
}));

vi.mock("../../components/focustype/Scene1", () => ({
  default: ({ onComplete }: { onComplete: (p: any) => void }) => (
    <button onClick={() => onComplete(["choice1"])}>Complete Scene 1</button>
  ),
}));
vi.mock("../../components/focustype/Scene2", () => ({
  default: ({ onComplete }: { onComplete: (p: any) => void }) => (
    <button onClick={() => onComplete({ now: [], later: [], ignore: [] })}>Complete Scene 2</button>
  ),
}));
vi.mock("../../components/focustype/Scene3", () => ({
  default: ({ onComplete }: { onComplete: (p: any) => void }) => (
    <button onClick={() => onComplete({ deep_solo: 3, planning: 2, social: 1, breaks: 2, exploring: 1 })}>Complete Scene 3</button>
  ),
}));
vi.mock("../../components/focustype/Scene4", () => ({
  default: ({ onComplete }: { onComplete: (p: any) => void }) => (
    <button onClick={() => onComplete({ now: [], tomorrow: [], avg_decision_time_ms: 500 })}>Complete Scene 4</button>
  ),
}));
vi.mock("../../components/focustype/Scene5", () => ({
  default: ({ onComplete }: { onComplete: (p: any) => void }) => (
    <button onClick={() => onComplete(["end"])}>Complete Scene 5</button>
  ),
}));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.user = null;
  mocks.locationState = null;
});

function renderFocusTypePage(state?: object) {
  render(
    <MemoryRouter initialEntries={[{ pathname: "/focus-type", state }]}>
      <FocusTypePage />
    </MemoryRouter>
  );
}

// ─── navigation guard ─────────────────────────────────────────────────────────

describe("FocusTypePage - navigation guard", () => {
  it("redirects to /focus-type/results when user already has a saved result", async () => {
    mocks.user = {
      profileData: {
        focus_type_result: {
          archetype: "Deep Diver",
          dimension_scores: {},
          recommendations: [],
        },
      },
    };
    renderFocusTypePage();
    await waitFor(() =>
      expect(mocks.navigate).toHaveBeenCalledWith(
        "/focus-type/results",
        expect.objectContaining({ replace: true })
      )
    );
  });

  it("does not redirect when retake=true even with saved result", async () => {
    mocks.user = {
      profileData: {
        focus_type_result: { archetype: "Deep Diver", dimension_scores: {}, recommendations: [] },
      },
    };
    renderFocusTypePage({ retake: true });
    await waitFor(() => expect(screen.getByText(/Discover how you actually focus/i)).toBeInTheDocument());
    expect(mocks.navigate).not.toHaveBeenCalledWith(
      "/focus-type/results",
      expect.anything()
    );
  });
});

// ─── intro phase ──────────────────────────────────────────────────────────────

describe("FocusTypePage - intro phase", () => {
  it("renders intro screen by default", () => {
    renderFocusTypePage();
    expect(screen.getByText(/Discover how you actually focus/i)).toBeInTheDocument();
  });

  it("shows 'Each choice is final' disclaimer", () => {
    renderFocusTypePage();
    expect(screen.getByText(/Each choice is final/i)).toBeInTheDocument();
  });

  it("shows time estimate", () => {
    renderFocusTypePage();
    expect(screen.getByText(/4 minutes/i)).toBeInTheDocument();
  });

  it("clicking Begin transitions to scene 1", () => {
    renderFocusTypePage();
    fireEvent.click(screen.getByRole("button", { name: /begin/i }));
    expect(screen.getByText("Complete Scene 1")).toBeInTheDocument();
  });
});

// ─── scenes phase ─────────────────────────────────────────────────────────────

describe("FocusTypePage - scenes phase", () => {
  it("shows Scene 1 indicator after clicking Begin", () => {
    renderFocusTypePage();
    fireEvent.click(screen.getByRole("button", { name: /begin/i }));
    expect(screen.getByText(/Scene 1 of 5/i)).toBeInTheDocument();
  });

  it("advances to Scene 2 after completing Scene 1", async () => {
    renderFocusTypePage();
    fireEvent.click(screen.getByRole("button", { name: /begin/i }));
    fireEvent.click(screen.getByText("Complete Scene 1"));
    expect(screen.getByText("Complete Scene 2")).toBeInTheDocument();
  });
});

// ─── submitting phase ─────────────────────────────────────────────────────────

describe("FocusTypePage - submitting phase", () => {
  it("shows spinner after all 5 scenes are completed", async () => {
    mocks.fetchWithAuth.mockReturnValue(new Promise(() => {}));
    renderFocusTypePage();
    fireEvent.click(screen.getByRole("button", { name: /begin/i }));
    fireEvent.click(screen.getByText("Complete Scene 1"));
    fireEvent.click(screen.getByText("Complete Scene 2"));
    fireEvent.click(screen.getByText("Complete Scene 3"));
    fireEvent.click(screen.getByText("Complete Scene 4"));
    fireEvent.click(screen.getByText("Complete Scene 5"));
    await waitFor(() =>
      expect(screen.getByText(/Calculating your FocusType/i)).toBeInTheDocument()
    );
  });

  it("navigates to /focus-type/results on successful submission", async () => {
    const mockResult = { archetype: "Deep Diver", dimension_scores: {}, recommendations: [] };
    mocks.fetchWithAuth.mockResolvedValueOnce(mockResult);
    renderFocusTypePage();
    fireEvent.click(screen.getByRole("button", { name: /begin/i }));
    fireEvent.click(screen.getByText("Complete Scene 1"));
    fireEvent.click(screen.getByText("Complete Scene 2"));
    fireEvent.click(screen.getByText("Complete Scene 3"));
    fireEvent.click(screen.getByText("Complete Scene 4"));
    await act(async () => { fireEvent.click(screen.getByText("Complete Scene 5")); });
    await waitFor(() =>
      expect(mocks.navigate).toHaveBeenCalledWith(
        "/focus-type/results",
        expect.objectContaining({ state: { result: mockResult } })
      )
    );
  });
});

// ─── error phase ──────────────────────────────────────────────────────────────

describe("FocusTypePage - error phase", () => {
  it("shows error UI when submission fails", async () => {
    mocks.fetchWithAuth.mockRejectedValueOnce(new Error("API error"));
    renderFocusTypePage();
    fireEvent.click(screen.getByRole("button", { name: /begin/i }));
    fireEvent.click(screen.getByText("Complete Scene 1"));
    fireEvent.click(screen.getByText("Complete Scene 2"));
    fireEvent.click(screen.getByText("Complete Scene 3"));
    fireEvent.click(screen.getByText("Complete Scene 4"));
    await act(async () => { fireEvent.click(screen.getByText("Complete Scene 5")); });
    await waitFor(() =>
      expect(screen.getByText(/Something went wrong submitting/i)).toBeInTheDocument()
    );
  });

  it("retry button re-submits and navigates on success", async () => {
    const mockResult = { archetype: "Sprint & Reset", dimension_scores: {}, recommendations: [] };
    mocks.fetchWithAuth
      .mockRejectedValueOnce(new Error("first failure"))
      .mockResolvedValueOnce(mockResult);
    renderFocusTypePage();
    fireEvent.click(screen.getByRole("button", { name: /begin/i }));
    for (const label of ["Complete Scene 1", "Complete Scene 2", "Complete Scene 3", "Complete Scene 4"]) {
      fireEvent.click(screen.getByText(label));
    }
    await act(async () => { fireEvent.click(screen.getByText("Complete Scene 5")); });
    await waitFor(() => screen.getByRole("button", { name: /try again/i }));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: /try again/i })); });
    await waitFor(() =>
      expect(mocks.navigate).toHaveBeenCalledWith(
        "/focus-type/results",
        expect.anything()
      )
    );
  });
});
