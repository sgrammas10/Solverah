import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import FocusTypeResultsPage from "../FocusTypeResultsPage";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  user: null as any,
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => mocks.navigate,
    Navigate: ({ to }: { to: string }) => {
      mocks.navigate(to, { replace: true });
      return null;
    },
  };
});

vi.mock("../../contexts/useAuth", () => ({
  useAuth: () => ({ user: mocks.user }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.user = null;
});

const MOCK_RESULT = {
  archetype: "Deep Diver",
  dimension_scores: {
    deep_focus: 8,
    burst_energy: 3,
    reactivity: 2,
    structure_need: 6,
    urgency_drive: 4,
    social_fuel: 1,
  },
  recommendations: [
    "Block deep-work time in the morning.",
    "Minimise notification interruptions.",
  ],
};

function renderWithState(state?: object) {
  render(
    <MemoryRouter
      initialEntries={[{ pathname: "/focus-type/results", state }]}
    >
      <FocusTypeResultsPage />
    </MemoryRouter>
  );
}

// ─── happy path (from location state) ─────────────────────────────────────────

describe("FocusTypeResultsPage - happy path", () => {
  it("renders the archetype name from location state", () => {
    renderWithState({ result: MOCK_RESULT });
    expect(screen.getByText("Deep Diver")).toBeInTheDocument();
  });

  it("renders the archetype description", () => {
    renderWithState({ result: MOCK_RESULT });
    expect(screen.getByText(/best work when nothing breaks your flow/i)).toBeInTheDocument();
  });

  it("renders all recommendations", () => {
    renderWithState({ result: MOCK_RESULT });
    expect(screen.getByText("Block deep-work time in the morning.")).toBeInTheDocument();
    expect(screen.getByText("Minimise notification interruptions.")).toBeInTheDocument();
  });

  it("renders dimension score labels", () => {
    renderWithState({ result: MOCK_RESULT });
    expect(screen.getByText("Deep Focus")).toBeInTheDocument();
    expect(screen.getByText("Burst Energy")).toBeInTheDocument();
  });
});

// ─── happy path (from user profileData) ───────────────────────────────────────

describe("FocusTypeResultsPage - result from profileData", () => {
  it("renders archetype from user.profileData when no location state", () => {
    mocks.user = { profileData: { focus_type_result: MOCK_RESULT } };
    renderWithState(undefined);
    expect(screen.getByText("Deep Diver")).toBeInTheDocument();
  });
});

// ─── navigation guard ─────────────────────────────────────────────────────────

describe("FocusTypeResultsPage - navigation guard", () => {
  it("redirects to /focus-type when no result and no profileData", () => {
    mocks.user = null;
    renderWithState(undefined);
    expect(mocks.navigate).toHaveBeenCalledWith("/focus-type", { replace: true });
  });
});

// ─── navigation actions ───────────────────────────────────────────────────────

describe("FocusTypeResultsPage - navigation actions", () => {
  it("back to intelligence hub button calls navigate", () => {
    renderWithState({ result: MOCK_RESULT });
    fireEvent.click(screen.getByRole("button", { name: /intelligence hub/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/intelligence");
  });

  it("bottom CTA calls navigate to /intelligence", () => {
    renderWithState({ result: MOCK_RESULT });
    fireEvent.click(screen.getByRole("button", { name: /back to intelligence/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/intelligence");
  });
});
