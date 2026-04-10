import {
  clearPendingQuizSave,
  getPendingQuizSave,
  hasCompletedGuestQuiz,
  markGuestQuizCompleted,
  setPendingQuizSave,
} from "../guestQuiz";
import type { PendingQuizSave } from "../guestQuiz";

const sample: PendingQuizSave = {
  quizGroup: "group-1",
  quizResults: { score: 42 },
  quizPayload: { answers: [1, 2, 3] },
  createdAt: "2024-01-01T00:00:00.000Z",
};

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
    const updated: PendingQuizSave = { ...sample, quizGroup: "group-2" };
    setPendingQuizSave(sample);
    setPendingQuizSave(updated);
    expect(getPendingQuizSave()?.quizGroup).toBe("group-2");
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
