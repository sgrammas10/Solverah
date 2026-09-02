/**
 * useQuizInsight.test.tsx — the shared insight modal/mutation hook.
 *
 * The generation call is a mutation the hook owns; the three quiz tabs hand it
 * their own transport as a request closure (which is what keeps the guest
 * preview's bare fetch and the signed-in POST as literal, contract-scannable
 * call sites in the components). What these tests pin:
 *
 *   - `insightLoading`/`insightError` are the mutation's state, not booleans a
 *     caller has to flip;
 *   - the ONE fake-progress ticker is driven by the mutation lifecycle:
 *     isPending starts it, settling ends it;
 *   - a failed request is not retried — an insight generation is an OpenAI
 *     call, and mutations never retry.
 */
import type { ReactNode } from "react";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";

import { useQuizInsight, type QuizInsightResponse } from "./useQuizInsight";
import { createQueryClient } from "../../shared/api/queryClient";

function createWrapper() {
  const queryClient = createQueryClient();
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

function setup() {
  const { result } = renderHook(() => useQuizInsight(), { wrapper: createWrapper() });
  return result;
}

describe("useQuizInsight", () => {
  it("openInsight opens the modal and resolves the request into insightResponse", async () => {
    const result = setup();
    const response: QuizInsightResponse = {
      overallSummary: "A summary",
      insights: [{ title: "Insight", summary: "Detail" }],
    };

    act(() => {
      result.current.openInsight(async () => response);
    });
    expect(result.current.insightModalOpen).toBe(true);

    await waitFor(() => expect(result.current.insightResponse).toEqual(response));
    expect(result.current.insightLoading).toBe(false);
    expect(result.current.insightError).toBeNull();
    expect(result.current.insightProgress).toBe(100);
  });

  it("the ticker runs while the mutation is pending and settles with it", async () => {
    const result = setup();
    let resolveRequest!: (r: QuizInsightResponse) => void;

    act(() => {
      result.current.openInsight(
        () => new Promise<QuizInsightResponse>((resolve) => { resolveRequest = resolve; })
      );
    });

    // isPending started the ticker: the bar leaves zero before any tick fires.
    await waitFor(() => expect(result.current.insightLoading).toBe(true));
    expect(result.current.insightProgress).toBeGreaterThanOrEqual(8);

    await act(async () => {
      resolveRequest({ insights: [] });
    });
    await waitFor(() => expect(result.current.insightLoading).toBe(false));
    expect(result.current.insightProgress).toBe(100);
  });

  it("a 4xx from the insight endpoint surfaces as insightError and is not retried", async () => {
    const result = setup();
    // 4xx means fail: the payload is what it is, and a second identical OpenAI
    // call would only be a second bill — mutations never retry.
    const request = vi.fn<() => Promise<QuizInsightResponse>>()
      .mockRejectedValue(new Error("Failed to generate insights."));

    act(() => {
      result.current.openInsight(request);
    });

    await waitFor(() =>
      expect(result.current.insightError).toBe("Failed to generate insights.")
    );
    expect(result.current.insightLoading).toBe(false);
    expect(request).toHaveBeenCalledTimes(1);
  });

  it("handleInsightClose closes the modal, zeroes the bar, and clears the failure", async () => {
    const result = setup();
    act(() => {
      result.current.openInsight(() => Promise.reject(new Error("boom")));
    });
    await waitFor(() => expect(result.current.insightError).toBe("boom"));

    act(() => {
      result.current.handleInsightClose();
    });

    expect(result.current.insightModalOpen).toBe(false);
    expect(result.current.insightProgress).toBe(0);
    await waitFor(() => expect(result.current.insightError).toBeNull());
  });

  it("setInsightResponse still seeds stored insights without running the mutation", () => {
    const result = setup();
    const stored: QuizInsightResponse = { overallInsight: null, insights: [{ title: "Saved" }] };

    act(() => {
      result.current.setInsightResponse(stored);
    });

    expect(result.current.insightResponse).toEqual(stored);
    expect(result.current.insightLoading).toBe(false);
    expect(result.current.insightModalOpen).toBe(false);
  });
});
