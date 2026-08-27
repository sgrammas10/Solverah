import { renderHook, act } from "@testing-library/react";
import { useWP } from "./useWP";
import { WP_QUESTIONS } from "../data/wpQuestions";

const STORAGE_KEY = "solverah_wp";

const ALL_ANSWERS = WP_QUESTIONS.map((q) => ({
  questionId: q.id,
  optionId: q.options[0].id,
}));

describe("useWP", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("initialises with empty answers and no cached result", () => {
    const { result } = renderHook(() => useWP());
    expect(result.current.state.answers).toHaveLength(0);
    expect(result.current.state.cachedResult).toBeNull();
  });

  it("isComplete is false when answers are empty", () => {
    const { result } = renderHook(() => useWP());
    expect(result.current.isComplete).toBe(false);
  });

  it("setAnswer adds an answer for a new questionId", () => {
    const { result } = renderHook(() => useWP());
    act(() => {
      result.current.setAnswer("wp-q1", "wp-q1-a");
    });
    expect(result.current.state.answers).toHaveLength(1);
    expect(result.current.state.answers[0]).toEqual({
      questionId: "wp-q1",
      optionId: "wp-q1-a",
    });
  });

  it("setAnswer replaces the existing answer for the same questionId", () => {
    const { result } = renderHook(() => useWP());
    act(() => {
      result.current.setAnswer("wp-q1", "wp-q1-a");
    });
    act(() => {
      result.current.setAnswer("wp-q1", "wp-q1-d");
    });
    expect(result.current.state.answers).toHaveLength(1);
    expect(result.current.state.answers[0].optionId).toBe("wp-q1-d");
  });

  it("setAnswer preserves answers for other questions", () => {
    const { result } = renderHook(() => useWP());
    act(() => {
      result.current.setAnswer("wp-q1", "wp-q1-a");
      result.current.setAnswer("wp-q2", "wp-q2-b");
    });
    act(() => {
      result.current.setAnswer("wp-q1", "wp-q1-c");
    });
    expect(result.current.state.answers).toHaveLength(2);
    const q2 = result.current.state.answers.find((a) => a.questionId === "wp-q2");
    expect(q2?.optionId).toBe("wp-q2-b");
  });

  it("isComplete is true when all 12 questions are answered", () => {
    const { result } = renderHook(() => useWP());
    act(() => {
      ALL_ANSWERS.forEach(({ questionId, optionId }) => {
        result.current.setAnswer(questionId, optionId);
      });
    });
    expect(result.current.isComplete).toBe(true);
    expect(result.current.state.answers).toHaveLength(WP_QUESTIONS.length);
  });

  it("resetWP clears all answers and the cached result", () => {
    const { result } = renderHook(() => useWP());
    act(() => {
      result.current.setAnswer("wp-q1", "wp-q1-a");
    });
    act(() => {
      result.current.setCachedResult({
        narrative: "Test narrative",
        emerging_signals: [],
        archetype: "Thinker",
        archetype_description: "Test archetype description",
      });
    });
    act(() => {
      result.current.resetWP();
    });
    expect(result.current.state.answers).toHaveLength(0);
    expect(result.current.state.cachedResult).toBeNull();
    expect(result.current.isComplete).toBe(false);
  });

  it("persists answers to sessionStorage after setAnswer", () => {
    const { result } = renderHook(() => useWP());
    act(() => {
      result.current.setAnswer("wp-q3", "wp-q3-c");
    });
    const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY)!);
    expect(stored.answers).toHaveLength(1);
    expect(stored.answers[0]).toEqual({ questionId: "wp-q3", optionId: "wp-q3-c" });
  });

  it("reads pre-existing state from sessionStorage on mount", () => {
    const preload = {
      answers: [{ questionId: "wp-q5", optionId: "wp-q5-b" }],
      cachedResult: null,
    };
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(preload));

    const { result } = renderHook(() => useWP());
    expect(result.current.state.answers).toHaveLength(1);
    expect(result.current.state.answers[0].questionId).toBe("wp-q5");
  });

  it("clears sessionStorage after resetWP", () => {
    const { result } = renderHook(() => useWP());
    act(() => {
      result.current.setAnswer("wp-q1", "wp-q1-a");
    });
    act(() => {
      result.current.resetWP();
    });
    const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY)!);
    expect(stored.answers).toHaveLength(0);
    expect(stored.cachedResult).toBeNull();
  });
});
