/**
 * useMP.test.tsx -- the Manager Profile draft is per user (G59).
 *
 * The draft used to live under one tab-wide `mp_answers` key. After a silent
 * session expiry the next account to sign in on that tab inherited it, and
 * ManagerProfilePage auto-submits a complete draft once its gate clears -- so
 * the previous person's 16 answers were scored as the new person's manager.
 */
import { renderHook, act } from "@testing-library/react";

import { useMP } from "./useMP";
import { MP_QUESTIONS } from "./data/mpQuestions";

/** Who `useAuth` says is signed in. Mutable so a test can switch accounts. */
const auth = vi.hoisted(() => ({ user: { id: "user-1" } as { id: string } | null }));
vi.mock("../auth/useAuth", () => ({
  useAuth: () => ({ user: auth.user }),
}));

const STORAGE_KEY = "mp_answers:user-1";
const LEGACY_KEY = "mp_answers";

/** A complete draft: the shape ManagerProfilePage auto-submits. */
const COMPLETE_DRAFT = MP_QUESTIONS.map((q) => ({ questionId: q.id, choice: "a" as const }));

describe("useMP", () => {
  beforeEach(() => {
    sessionStorage.clear();
    auth.user = { id: "user-1" };
  });

  it("the draft key carries the signed-in user's id", () => {
    const { result } = renderHook(() => useMP());
    act(() => {
      result.current.setAnswer("mp-q1", "a");
    });
    expect(JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "[]")).toEqual([
      { questionId: "mp-q1", choice: "a" },
    ]);
    expect(sessionStorage.getItem(LEGACY_KEY)).toBeNull();
  });

  it("answers are restored from storage by a fresh mount for the same user", () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(COMPLETE_DRAFT.slice(0, 8)));
    const { result } = renderHook(() => useMP());
    expect(result.current.answers).toHaveLength(8);
  });

  it("a second user on the same tab does not inherit the first user's complete draft", () => {
    // Regression (G59): with the shared key, user B mounted with user A's 16
    // answers and the page submitted them as B's. Written through the hook,
    // not seeded by key, so the test holds whatever key the hook chooses.
    const first = renderHook(() => useMP());
    act(() => {
      for (const a of COMPLETE_DRAFT) first.result.current.setAnswer(a.questionId, a.choice);
    });
    expect(first.result.current.answers).toHaveLength(COMPLETE_DRAFT.length);
    first.unmount();

    auth.user = { id: "user-2" };
    const { result } = renderHook(() => useMP());
    expect(result.current.answers).toHaveLength(0);
  });

  it("switching user on a live mount swaps to that user's draft", () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(COMPLETE_DRAFT));
    const { result, rerender } = renderHook(() => useMP());
    expect(result.current.answers).toHaveLength(COMPLETE_DRAFT.length);

    auth.user = { id: "user-2" };
    rerender();
    expect(result.current.answers).toHaveLength(0);
  });

  it("a pre-scoping unkeyed draft is discarded, not adopted", () => {
    sessionStorage.setItem(LEGACY_KEY, JSON.stringify(COMPLETE_DRAFT));
    const { result } = renderHook(() => useMP());
    expect(result.current.answers).toHaveLength(0);
    expect(sessionStorage.getItem(LEGACY_KEY)).toBeNull();
  });

  it("with nobody signed in nothing is written to storage", () => {
    auth.user = null;
    const { result } = renderHook(() => useMP());
    act(() => {
      result.current.setAnswer("mp-q1", "a");
    });
    expect(result.current.answers).toHaveLength(1);
    expect(sessionStorage.length).toBe(0);
  });

  it("reset() clears the answers and removes only this user's key", () => {
    sessionStorage.setItem("mp_answers:user-2", JSON.stringify(COMPLETE_DRAFT));
    const { result } = renderHook(() => useMP());
    act(() => {
      result.current.setAnswer("mp-q1", "b");
    });
    act(() => {
      result.current.reset();
    });
    expect(result.current.answers).toHaveLength(0);
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
    expect(sessionStorage.getItem("mp_answers:user-2")).not.toBeNull();
  });

  // The logout sweep's coverage of `mp_answers:<id>` is pinned in the auth
  // slice's own draftStorage.test.ts (a deep import from here is lint-banned).
});
