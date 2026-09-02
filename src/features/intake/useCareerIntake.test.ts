import { renderHook, act } from "@testing-library/react";
import { useCareerIntake } from "./useCareerIntake";

const STORAGE_KEY = "solverah_intake";

beforeEach(() => {
  sessionStorage.clear();
  vi.clearAllMocks();
});

describe("useCareerIntake", () => {
  describe("toggleStatement", () => {
    it("adds an ID when not present", () => {
      const { result } = renderHook(() => useCareerIntake());
      act(() => {
        result.current.toggleStatement("dir-1");
      });
      expect(result.current.state.selectedStatementIds).toContain("dir-1");
    });

    it("removes an ID when already present", () => {
      const { result } = renderHook(() => useCareerIntake());
      act(() => {
        result.current.toggleStatement("dir-1");
      });
      act(() => {
        result.current.toggleStatement("dir-1");
      });
      expect(result.current.state.selectedStatementIds).not.toContain("dir-1");
    });

    it("writes state to sessionStorage after a toggle", () => {
      const { result } = renderHook(() => useCareerIntake());
      act(() => {
        result.current.toggleStatement("job-1");
      });
      const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY)!);
      expect(stored.selectedStatementIds).toContain("job-1");
    });
  });

  describe("setWpllAnswer", () => {
    it("adds a new answer", () => {
      const { result } = renderHook(() => useCareerIntake());
      act(() => {
        result.current.setWpllAnswer("wpll-q1", "wpll-q1-a");
      });
      expect(result.current.state.wpllAnswers).toContainEqual({
        questionId: "wpll-q1",
        optionId: "wpll-q1-a",
      });
    });

    it("replaces an existing answer for the same question", () => {
      const { result } = renderHook(() => useCareerIntake());
      act(() => {
        result.current.setWpllAnswer("wpll-q1", "wpll-q1-a");
      });
      act(() => {
        result.current.setWpllAnswer("wpll-q1", "wpll-q1-c");
      });
      const answers = result.current.state.wpllAnswers.filter(
        (a) => a.questionId === "wpll-q1"
      );
      expect(answers).toHaveLength(1);
      expect(answers[0].optionId).toBe("wpll-q1-c");
    });
  });

  describe("setWpllInsightText", () => {
    it("sets state.wpllInsightText", () => {
      const { result } = renderHook(() => useCareerIntake());
      act(() => {
        result.current.setWpllInsightText("You thrive in focused environments.");
      });
      expect(result.current.state.wpllInsightText).toBe(
        "You thrive in focused environments."
      );
    });

    it("persists wpllInsightText to sessionStorage", () => {
      const { result } = renderHook(() => useCareerIntake());
      act(() => {
        result.current.setWpllInsightText("Test insight");
      });
      const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY)!);
      expect(stored.wpllInsightText).toBe("Test insight");
    });
  });

  describe("sessionStorage restoration", () => {
    it("restores state from sessionStorage on re-initialization", () => {
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          step: 2,
          selectedStatementIds: ["sus-1"],
          wpllAnswers: [],
          wpllInsightText: "",
        })
      );
      const { result } = renderHook(() => useCareerIntake());
      expect(result.current.state.step).toBe(2);
      expect(result.current.state.selectedStatementIds).toContain("sus-1");
    });

    it("falls back to default state when sessionStorage contains invalid JSON", () => {
      sessionStorage.setItem(STORAGE_KEY, "not-valid-json");
      const { result } = renderHook(() => useCareerIntake());
      expect(result.current.state.step).toBe(1);
      expect(result.current.state.selectedStatementIds).toHaveLength(0);
    });
  });
});
