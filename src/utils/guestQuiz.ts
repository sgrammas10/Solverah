export type PendingQuizSave = {
  quizGroup: string;
  quizResults: Record<string, unknown>;
  quizPayload: Record<string, unknown>;
  createdAt: string;
};

const STORAGE_KEY = "pendingQuizSave";
const COMPLETED_KEY = "guestQuizCompletedAt";

export const setPendingQuizSave = (payload: PendingQuizSave) => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  } catch {
    // ignore storage failures
  }
};

export const getPendingQuizSave = (): PendingQuizSave | null => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as PendingQuizSave;
  } catch {
    return null;
  }
};

export const clearPendingQuizSave = () => {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore storage failures
  }
};

export const markGuestQuizCompleted = () => {
  try {
    localStorage.setItem(COMPLETED_KEY, new Date().toISOString());
  } catch {
    // ignore storage failures
  }
};

export const hasCompletedGuestQuiz = (): boolean => {
  try {
    return Boolean(localStorage.getItem(COMPLETED_KEY));
  } catch {
    return false;
  }
};
