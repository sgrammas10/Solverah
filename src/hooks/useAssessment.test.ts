/**
 * Tests for useAssessment.
 *
 * Covers the two things that are easy to get wrong and invisible when wrong: the block
 * boundaries must disappear without disturbing item order, and stored answers from a different
 * instrument must not be submitted.
 */
import { act, renderHook, waitFor } from "@testing-library/react";

import { flattenItems, useAssessment, type AssessmentForm } from "./useAssessment";

const fetchWithAuth = vi.fn();

vi.mock("../contexts/useAuth", () => ({
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
    const { result } = renderHook(() => useAssessment());

    await waitFor(() => expect(result.current.items).not.toBeNull());
    expect(fetchWithAuth).toHaveBeenCalledWith("/assessment/form");
    expect(result.current.items!.map((i) => i.token)).toEqual(SERVED_ORDER);
    expect(result.current.items!.map((i) => i.token)).not.toEqual(ALPHABETICAL);
  });

  it("surfaces a load failure instead of rendering an empty form", async () => {
    fetchWithAuth.mockRejectedValueOnce(new Error("network down"));
    const { result } = renderHook(() => useAssessment());

    await waitFor(() => expect(result.current.loadError).toBe("network down"));
    expect(result.current.items).toBeNull();
  });

  it("restores answers from session storage on a resumed session", async () => {
    sessionStorage.setItem(
      "solverah_assessment_answers",
      JSON.stringify({ zulu: "A", mike: "B" })
    );
    fetchWithAuth.mockResolvedValueOnce(FORM);
    const { result } = renderHook(() => useAssessment());

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
    const { result } = renderHook(() => useAssessment());

    await waitFor(() => expect(result.current.items).not.toBeNull());
    await waitFor(() => expect(result.current.answers).toEqual({ zulu: "A" }));
  });

  it("refuses to submit an incomplete set", async () => {
    fetchWithAuth.mockResolvedValueOnce(FORM);
    const { result } = renderHook(() => useAssessment());
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
    const { result } = renderHook(() => useAssessment());
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
    const { result } = renderHook(() => useAssessment());
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
    expect(endpoint).toBe("/assessment/submit");
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
    const { result } = renderHook(() => useAssessment());
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
