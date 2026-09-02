/**
 * useMM.test.tsx — the singleton's replacement, pinned.
 *
 * The module-level `_state` singleton is gone; the query cache is the
 * singleton now, keyed by `managerMatchResultKeys.result()`. Answers live in
 * sessionStorage (as before), so what used to be "restored when the module
 * re-initialises" is now "restored by any fresh mount", and what used to be
 * "two components share `_state`" is "two components share a QueryClient".
 */
import type { ReactNode } from "react";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { useMM } from "./useMM";
import { managerMatchResultKeys } from "./useManagerMatchResult";
import { createQueryClient } from "../../shared/api/queryClient";

const STORAGE_KEY = "mm_answers";

const MOCK_RESULT = {
  archetype: "The Autonomist",
  dimension_scores: { autonomy: 0.8, feedback_style: 0.3, relationship: 0.5, growth_focus: 0.6 },
  narrative: "You work best with minimal oversight.",
  what_to_look_for: ["1:1 frequency", "decision-making latitude"],
  red_flags: ["Micromanagement"],
  archetype_description: "You are self-directed and independent.",
};

/** Fresh client per render — the established idiom; no cache crosses a test. */
let queryClient: QueryClient;
function createWrapper(client?: QueryClient) {
  queryClient = client ?? createQueryClient();
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

function renderMM(client?: QueryClient) {
  return renderHook(() => useMM(), { wrapper: createWrapper(client) });
}

describe("useMM", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("setAnswer appends a new answer correctly", () => {
    const { result } = renderMM();
    act(() => {
      result.current.setAnswer("mm-q1", "a");
    });
    expect(result.current.state.answers).toHaveLength(1);
    expect(result.current.state.answers[0]).toEqual({ questionId: "mm-q1", choice: "a" });
  });

  it("calling setAnswer again with same questionId overwrites rather than duplicates", () => {
    const { result } = renderMM();
    act(() => {
      result.current.setAnswer("mm-q1", "a");
    });
    act(() => {
      result.current.setAnswer("mm-q1", "b");
    });
    expect(result.current.state.answers).toHaveLength(1);
    expect(result.current.state.answers[0].choice).toBe("b");
  });

  it("setCachedResult stores the result and it is readable from state", async () => {
    const { result } = renderMM();
    act(() => {
      result.current.setCachedResult(MOCK_RESULT);
    });
    // It lands on the shared query key — which is what makes it visible to
    // ManagerMatchResultsPage without a request.
    expect(queryClient.getQueryData(managerMatchResultKeys.result())).toEqual(MOCK_RESULT);
    // The observer's notification is scheduled, not synchronous — hence waitFor.
    await waitFor(() => expect(result.current.state.cachedResult).toEqual(MOCK_RESULT));
  });

  it("a result cached by one mount is visible to a later mount on the same client", () => {
    // The claim the singleton existed for: ManagerMatchPage writes the result,
    // navigates, and the next screen's hooks read the same object. The app has
    // exactly one QueryClient, so sharing it is the production shape.
    const client = createQueryClient();
    const first = renderMM(client);
    act(() => {
      first.result.current.setCachedResult(MOCK_RESULT);
    });
    first.unmount();

    const second = renderMM(client);
    expect(second.result.current.state.cachedResult).toEqual(MOCK_RESULT);
  });

  it("reset() clears answers, clears cachedResult, and removes the sessionStorage key", async () => {
    const { result } = renderMM();
    act(() => {
      result.current.setAnswer("mm-q1", "a");
    });
    act(() => {
      result.current.setCachedResult(MOCK_RESULT);
    });
    act(() => {
      result.current.reset();
    });
    expect(result.current.state.answers).toHaveLength(0);
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
    expect(queryClient.getQueryData(managerMatchResultKeys.result())).toBeUndefined();
    await waitFor(() => expect(result.current.state.cachedResult).toBeNull());
  });

  it("answers written via setAnswer are persisted to sessionStorage", () => {
    const { result } = renderMM();
    act(() => {
      result.current.setAnswer("mm-q3", "b");
    });
    const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY)!);
    expect(stored).toHaveLength(1);
    expect(stored[0]).toEqual({ questionId: "mm-q3", choice: "b" });
  });

  it("answers are restored from sessionStorage by a fresh mount", () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify([{ questionId: "mm-q5", choice: "a" }]));
    const { result } = renderMM();
    expect(result.current.state.answers).toHaveLength(1);
    expect(result.current.state.answers[0].questionId).toBe("mm-q5");
  });
});
