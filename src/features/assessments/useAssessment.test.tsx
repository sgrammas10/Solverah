/**
 * Tests for useAssessment.
 *
 * Covers the two things that are easy to get wrong and invisible when wrong: the block
 * boundaries must disappear without disturbing item order, and stored answers from a different
 * instrument must not be submitted. The prune that enforces the second one must run once per
 * FETCH of the form, not once per mount — pinned below by refetching a changed form on a
 * mounted hook.
 */
import type { ReactNode } from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import {
  assessmentKeys,
  flattenItems,
  useAssessment,
  type AssessmentForm,
} from "./useAssessment";
import { createQueryClient } from "../../shared/api/queryClient";
import { ApiError } from "../../shared/api/apiError";

const fetchWithAuth = vi.fn();

vi.mock("../auth/useAuth", () => ({
  useAuth: () => ({ fetchWithAuth }),
}));

function makeForm(tokensByBlock: string[][]): AssessmentForm {
  return {
    form_version: "v2-2026-08-18",
    respondent_id: "opaque-respondent",
    blocks: tokensByBlock.map((tokens, b) => ({
      block: b,
      items: tokens.map((token) => ({
        token,
        prompt: `prompt for ${token}`,
        options: [
          { key: "A", text: `A of ${token}` },
          { key: "B", text: `B of ${token}` },
        ],
      })),
    })),
  };
}

/**
 * Tokens deliberately chosen so that alphabetical order != served order. With sequential
 * tokens (t1..t6) a stray `.sort()` is invisible, because the sorted order happens to equal
 * the served one -- which is exactly how an ordering bug ships.
 *
 * Served:       zulu, mike, alfa, yankee, bravo, charlie
 * Alphabetical: alfa, bravo, charlie, mike, yankee, zulu
 */
const SERVED_ORDER = ["zulu", "mike", "alfa", "yankee", "bravo", "charlie"];
const ALPHABETICAL = [...SERVED_ORDER].sort();

const FORM = makeForm([
  ["zulu", "mike", "alfa"],
  ["yankee", "bravo", "charlie"],
]);

/** Fresh client per render — the established idiom; no cache crosses a test. */
let queryClient: QueryClient;
function createWrapper() {
  queryClient = createQueryClient();
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

function renderAssessment() {
  return renderHook(() => useAssessment(), { wrapper: createWrapper() });
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
});

describe("flattenItems", () => {
  it("concatenates blocks in order and preserves item order inside each", () => {
    expect(flattenItems(FORM).map((i) => i.token)).toEqual(SERVED_ORDER);
  });

  it("does not sort — the served order is authoritative", () => {
    // The whole instrument rests on this. The 24 items are a difficulty ladder; served in
    // difficulty order they read as "a little / somewhat / quite / extremely" and a respondent
    // can walk down them to produce a consistent fake that scores HIGH on confidence. Any
    // client-side reordering silently defeats the server's shuffle and interleave.
    expect(SERVED_ORDER).not.toEqual(ALPHABETICAL);
    expect(flattenItems(FORM).map((i) => i.token)).not.toEqual(ALPHABETICAL);
  });

  it("keeps no trace of which block an item came from", () => {
    const items = flattenItems(FORM);
    items.forEach((item) => {
      expect(Object.keys(item).sort()).toEqual(["options", "prompt", "token"]);
    });
  });
});

describe("useAssessment", () => {
  it("loads the form from the server rather than from a bundled data file", async () => {
    fetchWithAuth.mockResolvedValueOnce(FORM);
    const { result } = renderAssessment();

    await waitFor(() => expect(result.current.items).not.toBeNull());
    expect(fetchWithAuth).toHaveBeenCalledWith("/assessments/core/form");
    expect(result.current.items!.map((i) => i.token)).toEqual(SERVED_ORDER);
    expect(result.current.items!.map((i) => i.token)).not.toEqual(ALPHABETICAL);
  });

  it("surfaces a load failure instead of rendering an empty form", async () => {
    // A 4xx: not retryable in shouldRetry's classification, so it surfaces on
    // the first attempt. The retried path is pinned separately below.
    fetchWithAuth.mockRejectedValueOnce(new ApiError("That could not be found.", { status: 404 }));
    const { result } = renderAssessment();

    await waitFor(() => expect(result.current.loadError).toBe("That could not be found."));
    expect(result.current.items).toBeNull();
    expect(fetchWithAuth).toHaveBeenCalledTimes(1);
  });

  it("retries a retryable load failure through shouldRetry's bounded retries", async () => {
    // The conversion to a query adopts the shared retry policy ON PURPOSE —
    // safe for this GET because Phase 3a removed every commit from GET
    // handlers. A 503 gets retried; the second attempt lands.
    fetchWithAuth
      .mockRejectedValueOnce(new ApiError("upstream hiccup", { status: 503 }))
      .mockResolvedValueOnce(FORM);
    const { result } = renderAssessment();

    await waitFor(
      () => expect(result.current.items).not.toBeNull(),
      // The first retry waits ~1s of real backoff.
      { timeout: 5000 }
    );
    expect(result.current.loadError).toBeNull();
    expect(fetchWithAuth).toHaveBeenCalledTimes(2);
  });

  it("restores answers from session storage on a resumed session", async () => {
    sessionStorage.setItem(
      "solverah_assessment_answers",
      JSON.stringify({ zulu: "A", mike: "B" })
    );
    fetchWithAuth.mockResolvedValueOnce(FORM);
    const { result } = renderAssessment();

    await waitFor(() => expect(result.current.items).not.toBeNull());
    expect(result.current.answers).toEqual({ zulu: "A", mike: "B" });
    expect(result.current.answeredCount).toBe(2);
  });

  it("drops stored answers whose tokens are not in the served form", async () => {
    // Tokens change when the active item file changes. Keeping the stale ones would submit
    // answers to questions this respondent was never shown, and the server would reject the
    // whole submission on the first unknown token -- at the very end, after 24 questions.
    sessionStorage.setItem(
      "solverah_assessment_answers",
      JSON.stringify({ zulu: "A", "token-from-an-older-item-file": "B" })
    );
    fetchWithAuth.mockResolvedValueOnce(FORM);
    const { result } = renderAssessment();

    await waitFor(() => expect(result.current.items).not.toBeNull());
    await waitFor(() => expect(result.current.answers).toEqual({ zulu: "A" }));
  });

  it("prunes again on every fetch, not only on the first mount", async () => {
    // The regression the conversion to a query invites: an onSuccess wired to
    // the first load only, leaving a refetch that returns a rotated form free
    // to submit answers to items this respondent was never shown.
    fetchWithAuth.mockResolvedValueOnce(FORM);
    const { result } = renderAssessment();
    await waitFor(() => expect(result.current.items).not.toBeNull());

    act(() => result.current.setAnswer("zulu", "A"));
    await waitFor(() => expect(result.current.answers).toEqual({ zulu: "A" }));

    // The active item file changed server-side: a refetch serves new tokens.
    const ROTATED = makeForm([["xray", "victor", "tango"]]);
    fetchWithAuth.mockResolvedValueOnce(ROTATED);
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: assessmentKeys.coreForm() });
    });

    await waitFor(() =>
      expect(result.current.items!.map((i) => i.token)).toEqual(["xray", "victor", "tango"])
    );
    // The answer to the old form's item is gone — pruned by the second fetch.
    await waitFor(() => expect(result.current.answers).toEqual({}));
  });

  it("refuses to submit an incomplete set", async () => {
    fetchWithAuth.mockResolvedValueOnce(FORM);
    const { result } = renderAssessment();
    await waitFor(() => expect(result.current.items).not.toBeNull());

    act(() => result.current.setAnswer("zulu", "A"));

    let returned: unknown;
    await act(async () => {
      returned = await result.current.submit();
    });

    expect(returned).toBeNull();
    // Only the initial GET. Nothing was posted.
    expect(fetchWithAuth).toHaveBeenCalledTimes(1);
  });

  it("refuses to submit when the server did not return 24 items", async () => {
    fetchWithAuth.mockResolvedValueOnce(FORM); // 6 items
    const { result } = renderAssessment();
    await waitFor(() => expect(result.current.items).not.toBeNull());

    act(() => {
      SERVED_ORDER.forEach((t) => result.current.setAnswer(t, "A"));
    });

    await act(async () => {
      await result.current.submit();
    });

    expect(result.current.submitError).toMatch(/returned 6 questions, expected 24/);
    expect(fetchWithAuth).toHaveBeenCalledTimes(1);
  });

  it("posts {token: option_key} and clears storage on success", async () => {
    const full = makeForm([
      Array.from({ length: 12 }, (_, i) => `a${i}`),
      Array.from({ length: 12 }, (_, i) => `b${i}`),
    ]);
    fetchWithAuth.mockResolvedValueOnce(full);
    const { result } = renderAssessment();
    await waitFor(() => expect(result.current.items).not.toBeNull());

    act(() => {
      result.current.items!.forEach((i) => result.current.setAnswer(i.token, "A"));
    });
    await waitFor(() => expect(result.current.isComplete).toBe(true));

    fetchWithAuth.mockResolvedValueOnce({
      submission_id: "abc",
      scoring_key_version: "v2-2026-08-18+mean_pole",
      dimensions_scored: 6,
    });

    await act(async () => {
      await result.current.submit();
    });

    const [endpoint, options] = fetchWithAuth.mock.calls[1];
    expect(endpoint).toBe("/assessments/core/submissions");
    expect(options.method).toBe("POST");
    const body = JSON.parse(options.body);
    expect(Object.keys(body.responses)).toHaveLength(24);
    expect(Object.values(body.responses).every((v) => v === "A")).toBe(true);
    expect(sessionStorage.getItem("solverah_assessment_answers")).toBeNull();
  });

  it("does not expose dimension scores from the submit response", async () => {
    // The submit endpoint deliberately returns no scores. If it ever starts to, this test is
    // the place that notices -- returning them hands a retaker a gradient to optimise against.
    const full = makeForm([Array.from({ length: 24 }, (_, i) => `t${i}`)]);
    fetchWithAuth.mockResolvedValueOnce(full);
    const { result } = renderAssessment();
    await waitFor(() => expect(result.current.items).not.toBeNull());

    act(() => {
      result.current.items!.forEach((i) => result.current.setAnswer(i.token, "A"));
    });
    await waitFor(() => expect(result.current.isComplete).toBe(true));

    fetchWithAuth.mockResolvedValueOnce({
      submission_id: "abc",
      scoring_key_version: "v2-2026-08-18+mean_pole",
      dimensions_scored: 6,
    });

    let returned: any;
    await act(async () => {
      returned = await result.current.submit();
    });

    expect(returned).not.toBeNull();
    expect(Object.keys(returned).sort()).toEqual([
      "dimensions_scored",
      "scoring_key_version",
      "submission_id",
    ]);
  });
});
