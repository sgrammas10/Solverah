import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import FocusTypePage, { FOCUS_TYPE_DRAFT_KEY_PREFIX, focusTypeDraftKey } from "./FocusTypePage";

/** The signed-in user every test runs as, and their draft key. */
const USER_ID = "7";
const FOCUS_TYPE_DRAFT_KEY = focusTypeDraftKey(USER_ID);
import { createQueryClient } from "../../../shared/api/queryClient";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  fetchWithAuth: vi.fn(),
  updateProfileData: vi.fn(),
  user: null as any,
  profile: {} as Record<string, unknown>,
  locationState: null as any,
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({
    fetchWithAuth: mocks.fetchWithAuth,
    user: mocks.user,
  }),
}));

// The cache merge moved to the profile slice with the auth ⇄ profile cycle
// kill; the page takes it from useProfileActions() now.
vi.mock("../../profile/useProfileActions", () => ({
  useProfileActions: () => ({ updateProfileData: mocks.updateProfileData }),
}));

// The saved result comes from the profile query now, not off `user`.
vi.mock("../../profile/useProfile", () => ({
  // The query hook, resolved. `isLoading: false` is the point: consumers
  // branch on it, and a mock that omitted it would report undefined --
  // falsy, so the branches would run, but by accident rather than intent.
  useProfile: () => ({ data: mocks.profile, isLoading: false }),
}));

vi.mock("./focustype/Scene1", () => ({
  default: ({ onComplete }: { onComplete: (p: any) => void }) => (
    <button onClick={() => onComplete(["choice1"])}>Complete Scene 1</button>
  ),
}));
vi.mock("./focustype/Scene2", () => ({
  default: ({ onComplete }: { onComplete: (p: any) => void }) => (
    <button onClick={() => onComplete({ now: [], later: [], ignore: [] })}>Complete Scene 2</button>
  ),
}));
vi.mock("./focustype/Scene3", () => ({
  default: ({ onComplete }: { onComplete: (p: any) => void }) => (
    <button onClick={() => onComplete({ deep_solo: 3, planning: 2, social: 1, breaks: 2, exploring: 1 })}>Complete Scene 3</button>
  ),
}));
vi.mock("./focustype/Scene4", () => ({
  default: ({ onComplete }: { onComplete: (p: any) => void }) => (
    <button onClick={() => onComplete({ now: [], tomorrow: [], avg_decision_time_ms: 500 })}>Complete Scene 4</button>
  ),
}));
vi.mock("./focustype/Scene5", () => ({
  default: ({ onComplete }: { onComplete: (p: any) => void }) => (
    <button onClick={() => onComplete(["end"])}>Complete Scene 5</button>
  ),
}));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.user = { id: USER_ID };
  mocks.profile = {};
  mocks.locationState = null;
  sessionStorage.clear();
});

/** The submit mutation needs a client; fresh per render, per the
 *  useProfileForm.test precedent. Mutations never retry, so the real defaults
 *  from createQueryClient() are safe here. */
function renderFocusTypePage(state?: object) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[{ pathname: "/focus-type", state }]}>
        <FocusTypePage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ─── navigation guard ─────────────────────────────────────────────────────────

describe("FocusTypePage - navigation guard", () => {
  it("redirects to /focus-type/results when user already has a saved result", async () => {
    mocks.profile = {
      focus_type_result: {
        archetype: "Deep Diver",
        dimension_scores: {},
        recommendations: [],
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
    mocks.profile = {
      focus_type_result: { archetype: "Deep Diver", dimension_scores: {}, recommendations: [] },
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

// ─── draft persistence + resume prompt ───────────────────────────────────────

describe("FocusTypePage - saved draft and resume prompt", () => {
  const TWO_SCENES = {
    scene_1: ["choice1"],
    scene_2: { now: [], later: [], ignore: [] },
  };

  it("persists each finished scene to sessionStorage", () => {
    // Regression: scenes lived in memory only, so a reload lost them.
    renderFocusTypePage();
    fireEvent.click(screen.getByRole("button", { name: "Begin" }));
    fireEvent.click(screen.getByText("Complete Scene 1"));
    const stored = JSON.parse(sessionStorage.getItem(FOCUS_TYPE_DRAFT_KEY)!);
    expect(stored).toEqual({ scene_1: ["choice1"] });
  });

  it("offers the resume prompt for a saved draft instead of the intro", () => {
    sessionStorage.setItem(FOCUS_TYPE_DRAFT_KEY, JSON.stringify(TWO_SCENES));
    renderFocusTypePage();
    expect(screen.getByRole("button", { name: "Pick up where you left off" })).toBeInTheDocument();
    expect(screen.getByText(/2 of 5 scenes/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Begin" })).toBeNull();
  });

  it("'Pick up where you left off' opens the first unfinished scene and submits the whole draft", async () => {
    sessionStorage.setItem(FOCUS_TYPE_DRAFT_KEY, JSON.stringify(TWO_SCENES));
    mocks.fetchWithAuth.mockResolvedValue({ archetype: "X", dimension_scores: {}, recommendations: [] });
    renderFocusTypePage();
    fireEvent.click(screen.getByRole("button", { name: "Pick up where you left off" }));
    expect(screen.getByText("Scene 3 of 5")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Complete Scene 3"));
    fireEvent.click(screen.getByText("Complete Scene 4"));
    await act(async () => {
      fireEvent.click(screen.getByText("Complete Scene 5"));
    });
    const body = JSON.parse(mocks.fetchWithAuth.mock.calls[0][1].body);
    expect(body.scene_1).toEqual(["choice1"]);
    expect(body.scene_2).toEqual({ now: [], later: [], ignore: [] });
    expect(body.scene_5).toEqual(["end"]);
    await waitFor(() => expect(sessionStorage.getItem(FOCUS_TYPE_DRAFT_KEY)).toBeNull());
  });

  it("'Start over' clears the draft and opens scene 1", () => {
    sessionStorage.setItem(FOCUS_TYPE_DRAFT_KEY, JSON.stringify(TWO_SCENES));
    renderFocusTypePage();
    fireEvent.click(screen.getByRole("button", { name: "Start over" }));
    expect(screen.getByText("Scene 1 of 5")).toBeInTheDocument();
    expect(sessionStorage.getItem(FOCUS_TYPE_DRAFT_KEY)).toBeNull();
  });

  it("a retake discards the draft and shows the intro", () => {
    sessionStorage.setItem(FOCUS_TYPE_DRAFT_KEY, JSON.stringify(TWO_SCENES));
    renderFocusTypePage({ retake: true });
    expect(screen.getByRole("button", { name: "Begin" })).toBeInTheDocument();
    expect(sessionStorage.getItem(FOCUS_TYPE_DRAFT_KEY)).toBeNull();
  });
});

// ─── F6: the draft belongs to one user ──────────────────────────────────────

describe("FocusTypePage - the draft is scoped to the user (F6)", () => {
  const TWO_SCENES = {
    scene_1: ["choice1"],
    scene_2: { now: [], later: [], ignore: [] },
  };

  it("keys the draft by user id", () => {
    renderFocusTypePage();
    fireEvent.click(screen.getByRole("button", { name: "Begin" }));
    fireEvent.click(screen.getByText("Complete Scene 1"));
    expect(sessionStorage.getItem(`${FOCUS_TYPE_DRAFT_KEY_PREFIX}:${USER_ID}`)).not.toBeNull();
    expect(sessionStorage.getItem(FOCUS_TYPE_DRAFT_KEY_PREFIX)).toBeNull();
  });

  it("does not offer another user's draft", () => {
    // Regression: one unscoped key, so whoever signed in next in the same tab
    // was offered (and could submit) the previous user's scenes.
    sessionStorage.setItem(focusTypeDraftKey("someone-else"), JSON.stringify(TWO_SCENES));
    renderFocusTypePage();
    expect(screen.queryByRole("button", { name: "Pick up where you left off" })).toBeNull();
    expect(screen.getByRole("button", { name: "Begin" })).toBeInTheDocument();
  });

  it("drops an old unscoped draft instead of adopting it", () => {
    sessionStorage.setItem(FOCUS_TYPE_DRAFT_KEY_PREFIX, JSON.stringify(TWO_SCENES));
    renderFocusTypePage();
    expect(screen.queryByRole("button", { name: "Pick up where you left off" })).toBeNull();
    expect(sessionStorage.getItem(FOCUS_TYPE_DRAFT_KEY_PREFIX)).toBeNull();
  });

  it("clears this user's draft on a successful submit", async () => {
    mocks.fetchWithAuth.mockResolvedValue({ archetype: "X", dimension_scores: {}, recommendations: [] });
    renderFocusTypePage();
    fireEvent.click(screen.getByRole("button", { name: "Begin" }));
    for (const label of ["Complete Scene 1", "Complete Scene 2", "Complete Scene 3", "Complete Scene 4"]) {
      fireEvent.click(screen.getByText(label));
    }
    expect(sessionStorage.getItem(FOCUS_TYPE_DRAFT_KEY)).not.toBeNull();
    await act(async () => {
      fireEvent.click(screen.getByText("Complete Scene 5"));
    });
    await waitFor(() => expect(sessionStorage.getItem(FOCUS_TYPE_DRAFT_KEY)).toBeNull());
  });
});

// ─── F11: the retake flag and history ───────────────────────────────────────

describe("FocusTypePage - retake state and history (F11)", () => {
  const SAVED = {
    focus_type_result: { archetype: "Deep Diver", dimension_scores: {}, recommendations: [] },
  };
  const TWO_SCENES = {
    scene_1: ["choice1"],
    scene_2: { now: [], later: [], ignore: [] },
  };

  it("strips the retake flag from the history entry once it is read", () => {
    // Router state survives a reload. Left in place, a reload mid-retake read
    // as a fresh "Retake" click and wiped the finished scenes.
    mocks.profile = SAVED;
    renderFocusTypePage({ retake: true });
    expect(mocks.navigate).toHaveBeenCalledWith("/focus-type", { replace: true, state: null });
  });

  it("a reload mid-retake resumes the draft rather than wiping it or bouncing to the old result", async () => {
    // What a reload looks like after the flag is stripped: a saved result, a
    // draft, and no retake state.
    mocks.profile = SAVED;
    sessionStorage.setItem(FOCUS_TYPE_DRAFT_KEY, JSON.stringify(TWO_SCENES));
    renderFocusTypePage();
    expect(screen.getByRole("button", { name: "Pick up where you left off" })).toBeInTheDocument();
    expect(JSON.parse(sessionStorage.getItem(FOCUS_TYPE_DRAFT_KEY)!)).toEqual(TWO_SCENES);
    expect(mocks.navigate).not.toHaveBeenCalledWith("/focus-type/results", expect.anything());
  });

  it("replaces this history entry with the results, so Back does not start a fresh retake", async () => {
    mocks.profile = SAVED;
    const result = { archetype: "Sprint & Reset", dimension_scores: {}, recommendations: [] };
    mocks.fetchWithAuth.mockResolvedValueOnce(result);
    renderFocusTypePage({ retake: true });
    fireEvent.click(screen.getByRole("button", { name: /begin/i }));
    for (const label of ["Complete Scene 1", "Complete Scene 2", "Complete Scene 3", "Complete Scene 4"]) {
      fireEvent.click(screen.getByText(label));
    }
    await act(async () => {
      fireEvent.click(screen.getByText("Complete Scene 5"));
    });
    await waitFor(() =>
      expect(mocks.navigate).toHaveBeenCalledWith("/focus-type/results", {
        replace: true,
        state: { result },
      })
    );
  });
});
