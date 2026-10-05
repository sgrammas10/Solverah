/**
 * useWP.test.tsx — the read-only observer left after the 12-question Work
 * Pulse was retired (2026-10-02).
 *
 * `cachedResult` lives in the TanStack Query cache under
 * `workPulseResultKeys.result()` and is deliberately NOT persisted. The answer
 * side this file used to pin went with the instrument.
 */
import type { ReactNode } from "react";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { useWP } from "./useWP";
import { workPulseResultKeys } from "./useWorkPulseResult";
import { createQueryClient } from "../../shared/api/queryClient";

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

  it("initialises with no cached result", () => {
    const { result } = renderWP();
    expect(result.current.state.cachedResult).toBeNull();
  });

  it("has no answer side any more", () => {
    // Retired with the instrument: nothing can submit a sitting.
    const { result } = renderWP();
    expect(result.current).not.toHaveProperty("setAnswer");
    expect(result.current).not.toHaveProperty("resetWP");
    expect(result.current.state).not.toHaveProperty("answers");
  });

  it("setCachedResult writes the shared work-pulse result query, and reads back from it", async () => {
    const { result } = renderWP();
    act(() => {
      result.current.setCachedResult(MOCK_RESULT);
    });
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

  it("writes nothing to sessionStorage", () => {
    const { result } = renderWP();
    act(() => {
      result.current.setCachedResult(MOCK_RESULT);
    });
    expect(sessionStorage.getItem("solverah_wp")).toBeNull();
  });
});
