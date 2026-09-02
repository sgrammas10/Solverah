/**
 * useWP.test.tsx — the split this hook's header documents, pinned.
 *
 * `answers` live in sessionStorage (a guest writes them with no session at
 * all); `cachedResult` lives in the TanStack Query cache under
 * `workPulseResultKeys.result()` and is deliberately NOT persisted. The
 * guest-resume flow that depends on the answers half surviving a sign-in is
 * proved end-to-end in `components/WorkPulseGuestResume.test.tsx`; this file
 * proves the hook-level contract both halves rely on.
 */
import type { ReactNode } from "react";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { useWP } from "./useWP";
import { workPulseResultKeys } from "./useWorkPulseResult";
import { createQueryClient } from "../../shared/api/queryClient";
import { WP_QUESTIONS } from "./data/wpQuestions";

const STORAGE_KEY = "solverah_wp";

const ALL_ANSWERS = WP_QUESTIONS.map((q) => ({
  questionId: q.id,
  optionId: q.options[0].id,
}));

const MOCK_RESULT = {
  narrative: "Test narrative",
  emerging_signals: [],
  archetype: "Thinker",
  archetype_description: "Test archetype description",
};

/** Fresh client per render — the established idiom; no cache crosses a test. */
let queryClient: QueryClient;
function createWrapper() {
  queryClient = createQueryClient();
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

function renderWP() {
  return renderHook(() => useWP(), { wrapper: createWrapper() });
}

describe("useWP", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("initialises with empty answers and no cached result", () => {
    const { result } = renderWP();
    expect(result.current.state.answers).toHaveLength(0);
    expect(result.current.state.cachedResult).toBeNull();
  });

  it("isComplete is false when answers are empty", () => {
    const { result } = renderWP();
    expect(result.current.isComplete).toBe(false);
  });

  it("setAnswer adds an answer for a new questionId", () => {
    const { result } = renderWP();
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
    const { result } = renderWP();
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
    const { result } = renderWP();
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
    const { result } = renderWP();
    act(() => {
      ALL_ANSWERS.forEach(({ questionId, optionId }) => {
        result.current.setAnswer(questionId, optionId);
      });
    });
    expect(result.current.isComplete).toBe(true);
    expect(result.current.state.answers).toHaveLength(WP_QUESTIONS.length);
  });

  it("resetWP clears all answers and the cached result", async () => {
    const { result } = renderWP();
    act(() => {
      result.current.setAnswer("wp-q1", "wp-q1-a");
    });
    act(() => {
      result.current.setCachedResult(MOCK_RESULT);
    });
    act(() => {
      result.current.resetWP();
    });
    expect(result.current.state.answers).toHaveLength(0);
    expect(result.current.isComplete).toBe(false);
    // Gone from the shared query cache too, not just from this hook's view.
    expect(queryClient.getQueryData(workPulseResultKeys.result())).toBeUndefined();
    await waitFor(() => expect(result.current.state.cachedResult).toBeNull());
  });

  it("persists answers to sessionStorage after setAnswer", () => {
    const { result } = renderWP();
    act(() => {
      result.current.setAnswer("wp-q3", "wp-q3-c");
    });
    const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY)!);
    expect(stored.answers).toHaveLength(1);
    expect(stored.answers[0]).toEqual({ questionId: "wp-q3", optionId: "wp-q3-c" });
  });

  it("reads pre-existing answers from sessionStorage on mount", () => {
    const preload = {
      answers: [{ questionId: "wp-q5", optionId: "wp-q5-b" }],
    };
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(preload));

    const { result } = renderWP();
    expect(result.current.state.answers).toHaveLength(1);
    expect(result.current.state.answers[0].questionId).toBe("wp-q5");
  });

  it("clears sessionStorage answers after resetWP", () => {
    const { result } = renderWP();
    act(() => {
      result.current.setAnswer("wp-q1", "wp-q1-a");
    });
    act(() => {
      result.current.resetWP();
    });
    const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY)!);
    expect(stored.answers).toHaveLength(0);
  });

  // ── The split itself ───────────────────────────────────────────────────────

  it("setCachedResult writes the shared work-pulse result query, and reads back from it", async () => {
    const { result } = renderWP();
    act(() => {
      result.current.setCachedResult(MOCK_RESULT);
    });
    // The write lands on the key every consumer of useWorkPulseResult reads —
    // this is what replaced the page-level setQueryData after a scoring job.
    expect(queryClient.getQueryData(workPulseResultKeys.result())).toEqual(MOCK_RESULT);
    // The observer's notification is scheduled, not synchronous — hence waitFor.
    await waitFor(() => expect(result.current.state.cachedResult).toEqual(MOCK_RESULT));
  });

  it("sees a result another consumer fetched into the shared query", async () => {
    const { result } = renderWP();
    act(() => {
      queryClient.setQueryData(workPulseResultKeys.result(), MOCK_RESULT);
    });
    await waitFor(() => expect(result.current.state.cachedResult).toEqual(MOCK_RESULT));
  });

  it("does not persist the cached result to sessionStorage", () => {
    // The server copy is authoritative after a reload; a persisted narrative
    // could survive a retake with nothing to invalidate it.
    const { result } = renderWP();
    act(() => {
      result.current.setCachedResult(MOCK_RESULT);
    });
    const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "{}");
    expect(stored.cachedResult).toBeUndefined();
  });

  it("ignores a legacy persisted cachedResult but keeps its answers", () => {
    // Sessions from before the split stored both halves under this key.
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        answers: [{ questionId: "wp-q5", optionId: "wp-q5-b" }],
        cachedResult: MOCK_RESULT,
      })
    );
    const { result } = renderWP();
    expect(result.current.state.answers).toHaveLength(1);
    expect(result.current.state.cachedResult).toBeNull();
  });
});
