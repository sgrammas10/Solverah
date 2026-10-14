import { USER_DRAFT_KEY_PREFIXES, clearUserDrafts, isUserDraftKey } from "./draftStorage";

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
});

/**
 * Every draft key USER_SCENARIOS.md Appendix A lists, plus the ones a grep of
 * `src/` for sessionStorage/localStorage finds that the appendix predates
 * (`env_report_answers_past`, `focus_type_draft`). If a lane adds a key and
 * this list does not grow, the backstop has a hole.
 */
const DRAFT_KEYS = [
  "solverah_assessment_answers",
  "env_report_answers",
  "env_report_answers_past",
  "mp_answers",
  "mm_answers",
  "solverah_wp",
  "solverah_intake",
  "focus_type_draft",
  "pendingQuizSave",
];

/** Browser-level state that is not one person's data and must survive. */
const KEPT_KEYS = ["guestQuizCompletedAt", "solverah.hasSession", "solverah.theme"];

describe("isUserDraftKey", () => {
  it.each(DRAFT_KEYS)("recognises %s", (key) => {
    expect(isUserDraftKey(key)).toBe(true);
  });

  it.each(KEPT_KEYS)("leaves %s alone", (key) => {
    expect(isUserDraftKey(key)).toBe(false);
  });

  it("matches a user-id suffix on every prefix, whatever the separator", () => {
    for (const prefix of USER_DRAFT_KEY_PREFIXES) {
      expect(isUserDraftKey(`${prefix}:42`)).toBe(true);
      expect(isUserDraftKey(`${prefix}_42`)).toBe(true);
    }
  });
});

describe("clearUserDrafts", () => {
  it("removes every draft from both storages and keeps UI preferences", () => {
    for (const key of DRAFT_KEYS) {
      sessionStorage.setItem(key, "{}");
      localStorage.setItem(key, "{}");
    }
    sessionStorage.setItem("mm_answers:7", "{}");
    localStorage.setItem("focus_type_draft:7", "{}");
    for (const key of KEPT_KEYS) {
      sessionStorage.setItem(key, "1");
      localStorage.setItem(key, "1");
    }

    clearUserDrafts();

    for (const key of [...DRAFT_KEYS, "mm_answers:7", "focus_type_draft:7"]) {
      expect(sessionStorage.getItem(key)).toBeNull();
      expect(localStorage.getItem(key)).toBeNull();
    }
    for (const key of KEPT_KEYS) {
      expect(sessionStorage.getItem(key)).toBe("1");
      expect(localStorage.getItem(key)).toBe("1");
    }
  });

  it("removes all of several drafts in one pass, not every other one", () => {
    // Storage is index-addressed: removing while walking key(i) skips entries.
    for (let i = 0; i < 6; i += 1) sessionStorage.setItem(`mm_answers:${i}`, "{}");
    clearUserDrafts();
    expect(sessionStorage.length).toBe(0);
  });

  it("does not throw when a storage is unavailable", () => {
    const original = Object.getOwnPropertyDescriptor(globalThis, "sessionStorage");
    Object.defineProperty(globalThis, "sessionStorage", {
      configurable: true,
      get() {
        throw new Error("SecurityError");
      },
    });
    try {
      localStorage.setItem("pendingQuizSave", "{}");
      expect(() => clearUserDrafts()).not.toThrow();
      expect(localStorage.getItem("pendingQuizSave")).toBeNull();
    } finally {
      if (original) Object.defineProperty(globalThis, "sessionStorage", original);
    }
  });
});
