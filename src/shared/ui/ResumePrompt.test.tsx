import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";

import ResumePrompt from "./ResumePrompt";
import { firstUnansweredIndex, useResumePrompt } from "../lib/resumeDraft";

describe("ResumePrompt", () => {
  it("shows progress and fires the matching callback for each choice", () => {
    const onResume = vi.fn();
    const onStartOver = vi.fn();
    render(
      <ResumePrompt
        title="Work Pulse"
        answeredCount={7}
        total={24}
        onResume={onResume}
        onStartOver={onStartOver}
      />
    );

    expect(screen.getByText(/7 of 24 questions/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Pick up where you left off" }));
    expect(onResume).toHaveBeenCalledTimes(1);
    expect(onStartOver).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Start over" }));
    expect(onStartOver).toHaveBeenCalledTimes(1);
  });

  it("uses the supplied unit noun", () => {
    render(
      <ResumePrompt
        title="FocusType"
        answeredCount={2}
        total={5}
        unit="scene"
        onResume={() => {}}
        onStartOver={() => {}}
      />
    );
    expect(screen.getByText(/2 of 5 scenes/)).toBeInTheDocument();
  });
});

describe("firstUnansweredIndex", () => {
  const answered = new Set(["a", "b", "d"]);
  const has = (x: string) => answered.has(x);

  it("returns the first gap, not the count of answers", () => {
    expect(firstUnansweredIndex(["a", "b", "c", "d", "e"], has)).toBe(2);
  });

  it("returns the last index when everything is answered", () => {
    expect(firstUnansweredIndex(["a", "b", "d"], has)).toBe(2);
  });

  it("returns 0 for nothing answered and for an empty list", () => {
    expect(firstUnansweredIndex(["x", "y"], has)).toBe(0);
    expect(firstUnansweredIndex([], has)).toBe(0);
  });
});

describe("useResumePrompt", () => {
  it("reflects the draft seen at mount and ignores later changes", () => {
    const { result, rerender } = renderHook(({ had }) => useResumePrompt(had), {
      initialProps: { had: false },
    });
    expect(result.current.showResumePrompt).toBe(false);
    rerender({ had: true });
    expect(result.current.showResumePrompt).toBe(false);
  });

  it("dismisses", () => {
    const { result } = renderHook(() => useResumePrompt(true));
    expect(result.current.showResumePrompt).toBe(true);
    act(() => result.current.dismissResumePrompt());
    expect(result.current.showResumePrompt).toBe(false);
  });
});
