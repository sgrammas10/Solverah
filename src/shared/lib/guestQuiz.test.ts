import {
  clearPendingQuizSave,
  completeGuestQuiz,
  getGuestInsight,
  getPendingQuizSave,
  hasCompletedGuestQuiz,
  markGuestQuizCompleted,
  replayQuizResults,
  setPendingQuizSave,
} from "./guestQuiz";
import type { PendingQuizSave } from "./guestQuiz";

const PAYLOAD = {
  quizGroup: "careerQuizzes",
  quizzes: [{ key: "earlyCareer", title: "Early", items: [{ question: "Q1", selected: "A" }] }],
};

const sample: PendingQuizSave = {
  quizGroup: "careerQuizzes",
  quizResults: { careerQuizzes: { earlyCareer: { 1: 0 } } },
  quizPayload: PAYLOAD,
  createdAt: "2024-01-01T00:00:00.000Z",
};

const INSIGHT = { overallSummary: "S", insights: [{ title: "Early", summary: "x" }] };

beforeEach(() => {
  localStorage.clear();
});

describe("setPendingQuizSave / getPendingQuizSave", () => {
  it("round-trips a payload through localStorage", () => {
    setPendingQuizSave(sample);
    expect(getPendingQuizSave()).toEqual(sample);
  });

  it("returns null when nothing is stored", () => {
    expect(getPendingQuizSave()).toBeNull();
  });

  it("returns null when stored value is malformed JSON", () => {
    localStorage.setItem("pendingQuizSave", "{not-json}");
    expect(getPendingQuizSave()).toBeNull();
  });

  it("overwrites a previous save with the new payload", () => {
    const updated: PendingQuizSave = {
      ...sample,
      quizResults: { careerQuizzes: { midCareer: { 2: 1 } } },
    };
    setPendingQuizSave(sample);
    setPendingQuizSave(updated);
    expect(getPendingQuizSave()?.quizResults).toEqual(updated.quizResults);
  });

  // Audit 2026-10-02 #2: an empty save was stored, then failed the replay on
  // every sign-in and was never cleared.
  it("refuses to store a save with no answers", () => {
    setPendingQuizSave({ ...sample, quizResults: { careerQuizzes: {} } });
    expect(localStorage.getItem("pendingQuizSave")).toBeNull();
  });

  it("refuses to store a save whose request has no items", () => {
    setPendingQuizSave({
      ...sample,
      quizPayload: { quizGroup: "careerQuizzes", quizzes: [{ key: "earlyCareer", title: "E", items: [] }] },
    });
    expect(localStorage.getItem("pendingQuizSave")).toBeNull();
  });

  it("drops an empty save written before the fix instead of returning it", () => {
    localStorage.setItem(
      "pendingQuizSave",
      JSON.stringify({ quizGroup: "careerJobSearch", quizResults: { careerJobSearch: {} }, quizPayload: {} }),
    );
    expect(getPendingQuizSave()).toBeNull();
    expect(localStorage.getItem("pendingQuizSave")).toBeNull();
  });

  // G16: the stand-alone quizzes' saves named their own flat group.
  it("reads a legacy flat-group save as a career-group save", () => {
    localStorage.setItem(
      "pendingQuizSave",
      JSON.stringify({
        quizGroup: "careerJobSearch",
        quizResults: { careerJobSearch: { 1: 2 } },
        quizPayload: {
          quizGroup: "careerJobSearch",
          quizzes: [{ key: "careerJobSearch", title: "CJS", items: [{ question: "Q", selected: "A" }] }],
        },
        createdAt: "2024-01-01T00:00:00.000Z",
      }),
    );
    const save = getPendingQuizSave();
    expect(save?.quizGroup).toBe("careerQuizzes");
    expect(save?.quizPayload.quizGroup).toBe("careerQuizzes");
  });
});

describe("clearPendingQuizSave", () => {
  it("removes the stored payload so get returns null", () => {
    setPendingQuizSave(sample);
    clearPendingQuizSave();
    expect(getPendingQuizSave()).toBeNull();
  });

  it("is safe to call when nothing is stored", () => {
    expect(() => clearPendingQuizSave()).not.toThrow();
  });
});

describe("markGuestQuizCompleted / hasCompletedGuestQuiz", () => {
  it("returns false before the quiz is marked completed", () => {
    expect(hasCompletedGuestQuiz()).toBe(false);
  });

  it("returns true after marking completed", () => {
    markGuestQuizCompleted();
    expect(hasCompletedGuestQuiz()).toBe(true);
  });

  it("stores an ISO timestamp when marked completed", () => {
    const before = Date.now();
    markGuestQuizCompleted();
    const raw = localStorage.getItem("guestQuizCompletedAt");
    expect(raw).not.toBeNull();
    expect(new Date(raw!).getTime()).toBeGreaterThanOrEqual(before);
  });
});

describe("completeGuestQuiz", () => {
  it("stores the save with its insight and sets the lockout", () => {
    const { createdAt: _createdAt, ...save } = sample;
    completeGuestQuiz(save, INSIGHT);
    expect(hasCompletedGuestQuiz()).toBe(true);
    expect(getGuestInsight()).toEqual(INSIGHT);
    expect(getPendingQuizSave()?.quizResults).toEqual(sample.quizResults);
  });

  it("does nothing -- no lockout -- for a save without answers", () => {
    completeGuestQuiz({ ...sample, quizResults: {} }, INSIGHT);
    expect(hasCompletedGuestQuiz()).toBe(false);
    expect(getPendingQuizSave()).toBeNull();
  });

  it("the insight goes when the save is cleared", () => {
    const { createdAt: _createdAt, ...save } = sample;
    completeGuestQuiz(save, INSIGHT);
    clearPendingQuizSave();
    expect(getGuestInsight()).toBeNull();
  });
});

describe("replayQuizResults", () => {
  it("merges a guest career quiz into the account's other career answers", () => {
    const patch = replayQuizResults(
      { careerQuizzes: { midCareer: { 1: 3 } }, careerJobSearch: { 1: 0 } },
      { careerQuizzes: { earlyCareer: { 1: 0 } }, careerQuizzesSubmittedAt: "t" },
    );
    expect(patch).toEqual({
      careerQuizzes: { midCareer: { 1: 3 }, earlyCareer: { 1: 0 } },
      careerQuizzesSubmittedAt: "t",
    });
  });

  it("never returns an empty map to write over saved answers", () => {
    expect(replayQuizResults({ careerQuizzes: { midCareer: { 1: 3 } } }, { careerQuizzes: {} })).toBeNull();
    expect(replayQuizResults({}, { careerJobSearch: {}, careerJobSearchSubmittedAt: "t" })).toBeNull();
    expect(replayQuizResults({}, null)).toBeNull();
  });

  it("passes a flat quiz through as-is", () => {
    expect(replayQuizResults(undefined, { careerJobSearch: { 3: 1 } })).toEqual({
      careerJobSearch: { 3: 1 },
    });
  });
});
