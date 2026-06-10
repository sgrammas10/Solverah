import { renderHook, act } from "@testing-library/react";
import { useMM, _resetMMState } from "./useMM";

const STORAGE_KEY = "mm_answers";

describe("useMM", () => {
  beforeEach(() => {
    sessionStorage.clear();
    _resetMMState();
  });

  it("setAnswer appends a new answer correctly", () => {
    const { result } = renderHook(() => useMM());
    act(() => {
      result.current.setAnswer("mm-q1", "a");
    });
    expect(result.current.state.answers).toHaveLength(1);
    expect(result.current.state.answers[0]).toEqual({ questionId: "mm-q1", choice: "a" });
  });

  it("calling setAnswer again with same questionId overwrites rather than duplicates", () => {
    const { result } = renderHook(() => useMM());
    act(() => {
      result.current.setAnswer("mm-q1", "a");
    });
    act(() => {
      result.current.setAnswer("mm-q1", "b");
    });
    expect(result.current.state.answers).toHaveLength(1);
    expect(result.current.state.answers[0].choice).toBe("b");
  });

  it("setCachedResult stores the result and it is readable from state", () => {
    const { result } = renderHook(() => useMM());
    const mockResult = {
      archetype: "The Autonomist",
      dimension_scores: { autonomy: 0.8, feedback_style: 0.3, relationship: 0.5, growth_focus: 0.6 },
      narrative: "You work best with minimal oversight.",
      what_to_look_for: ["1:1 frequency", "decision-making latitude"],
      red_flags: ["Micromanagement"],
      archetype_description: "You are self-directed and independent.",
    };
    act(() => {
      result.current.setCachedResult(mockResult);
    });
    expect(result.current.state.cachedResult).toEqual(mockResult);
  });

  it("reset() clears answers, clears cachedResult, and removes the sessionStorage key", () => {
    const { result } = renderHook(() => useMM());
    act(() => {
      result.current.setAnswer("mm-q1", "a");
    });
    act(() => {
      result.current.setCachedResult({
        archetype: "The Operator",
        dimension_scores: {},
        narrative: "n",
        what_to_look_for: [],
        red_flags: [],
        archetype_description: "d",
      });
    });
    act(() => {
      result.current.reset();
    });
    expect(result.current.state.answers).toHaveLength(0);
    expect(result.current.state.cachedResult).toBeNull();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("answers written via setAnswer are persisted to sessionStorage", () => {
    const { result } = renderHook(() => useMM());
    act(() => {
      result.current.setAnswer("mm-q3", "b");
    });
    const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY)!);
    expect(stored).toHaveLength(1);
    expect(stored[0]).toEqual({ questionId: "mm-q3", choice: "b" });
  });

  it("answers are restored from sessionStorage when module is re-initialised", () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify([{ questionId: "mm-q5", choice: "a" }]));
    // Simulate module re-init: _resetMMState re-reads sessionStorage into _state
    _resetMMState();
    const { result } = renderHook(() => useMM());
    expect(result.current.state.answers).toHaveLength(1);
    expect(result.current.state.answers[0].questionId).toBe("mm-q5");
  });
});
