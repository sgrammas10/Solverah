/**
 * guestQuiz.ts — the anonymous quiz preview's local state.
 *
 * Two localStorage keys:
 *   - `pendingQuizSave`: the guest's answers, the insight request, and (since
 *     2026-10-02, G20) the insight itself, replayed onto the account by
 *     Login.tsx after sign-in. Cleared on logout with the other per-user drafts.
 *   - `guestQuizCompletedAt`: the one-free-quiz lockout marker. Pure UI state;
 *     it survives logout on purpose.
 *
 * Audit 2026-10-02 #2: both used to be written BEFORE the insight call, so any
 * failure (a 429, a 500, an empty submit) locked the guest out with nothing to
 * show, and an empty save then failed the replay on every later sign-in. They
 * are written only by {@link completeGuestQuiz}, after a successful insight,
 * and a save that carries no answers is never stored or returned.
 */

/** The guest-visible insight, as GuestQuizInsights renders it. */
export type GuestInsight = {
  overallSummary?: string | null;
  insights?: {
    key?: string;
    title?: string;
    summary?: string;
    keyTakeaways?: string[];
    combinedMeaning?: string;
    nextSteps?: string[];
  }[];
};

export type PendingQuizSave = {
  quizGroup: string;
  quizResults: Record<string, unknown>;
  quizPayload: Record<string, unknown>;
  createdAt: string;
  insight?: GuestInsight | null;
};

const STORAGE_KEY = "pendingQuizSave";
const COMPLETED_KEY = "guestQuizCompletedAt";

/** Every guest quiz now belongs to the career group (G16; see quizPayload.ts). */
const CAREER_QUIZ_GROUP = "careerQuizzes";

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);

/** True when any value, at any depth, is a selected option index. */
function hasAnyAnswer(value: unknown): boolean {
  if (typeof value === "number") return true;
  if (!isRecord(value)) return false;
  return Object.values(value).some(hasAnyAnswer);
}

/** True when the request names at least one quiz with at least one item. */
function hasQuizItems(payload: unknown): boolean {
  if (!isRecord(payload) || !Array.isArray(payload.quizzes)) return false;
  return payload.quizzes.some(
    (quiz) => isRecord(quiz) && Array.isArray(quiz.items) && quiz.items.length > 0,
  );
}

/** A save worth keeping: answers to write and a request with items. */
export function isUsablePendingSave(save: unknown): save is PendingQuizSave {
  return (
    isRecord(save) &&
    typeof save.quizGroup === "string" &&
    hasAnyAnswer(save.quizResults) &&
    hasQuizItems(save.quizPayload)
  );
}

/**
 * Pre-2026-10-02 saves for Career & Job Search and Your Future, Your Way named
 * their own flat group (G16). Read them as career-group saves so the replay
 * stores the insight where every page reads it.
 */
function normalize(save: PendingQuizSave): PendingQuizSave {
  if (save.quizGroup === CAREER_QUIZ_GROUP) return save;
  return {
    ...save,
    quizGroup: CAREER_QUIZ_GROUP,
    quizPayload: { ...save.quizPayload, quizGroup: CAREER_QUIZ_GROUP },
  };
}

export const setPendingQuizSave = (payload: PendingQuizSave) => {
  if (!isUsablePendingSave(payload)) return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  } catch {
    // ignore storage failures
  }
};

/** The stored save, or null. An unusable one (the pre-fix empty save) is removed. */
export const getPendingQuizSave = (): PendingQuizSave | null => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!isUsablePendingSave(parsed)) {
      localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return normalize(parsed);
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

/** The guest's insight, persisted with the pending save (G20). */
export const getGuestInsight = (): GuestInsight | null => {
  const insight = getPendingQuizSave()?.insight;
  return insight && Array.isArray(insight.insights) && insight.insights.length ? insight : null;
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

/**
 * Record a guest quiz that produced an insight: store the save (with the
 * insight) and set the lockout. Call ONLY after the insight request succeeded.
 * A save with no answers is refused and nothing is written.
 */
export function completeGuestQuiz(save: Omit<PendingQuizSave, "createdAt">, insight: GuestInsight) {
  const full: PendingQuizSave = { ...save, insight, createdAt: new Date().toISOString() };
  if (!isUsablePendingSave(full)) return;
  setPendingQuizSave(full);
  markGuestQuizCompleted();
}

/**
 * The `quizResults` to PATCH when replaying a guest save onto an account, or
 * null when there is nothing to write.
 *
 * The server merges `quizResults` one level deep, so a `careerQuizzes` value
 * replaces the account's whole career-quiz map. That is merged here, one level
 * further, with what the account already holds -- a guest's one quiz must not
 * wipe the three it answered while signed in. Empty values are dropped, so an
 * empty map can never be written over saved answers.
 */
export function replayQuizResults(
  existingQuizResults: unknown,
  pendingQuizResults: unknown,
): Record<string, unknown> | null {
  if (!isRecord(pendingQuizResults)) return null;
  const existing = isRecord(existingQuizResults) ? existingQuizResults : {};
  const patch: Record<string, unknown> = {};
  let answered = false;

  for (const [key, value] of Object.entries(pendingQuizResults)) {
    if (key === CAREER_QUIZ_GROUP && isRecord(value)) {
      const quizzes = Object.fromEntries(
        Object.entries(value).filter(([, answers]) => hasAnyAnswer(answers)),
      );
      if (!Object.keys(quizzes).length) continue;
      const existingGroup = isRecord(existing[CAREER_QUIZ_GROUP]) ? existing[CAREER_QUIZ_GROUP] : {};
      patch[key] = { ...(existingGroup as Record<string, unknown>), ...quizzes };
      answered = true;
    } else if (isRecord(value)) {
      if (!hasAnyAnswer(value)) continue;
      patch[key] = value;
      answered = true;
    } else if (typeof value === "string" && key.endsWith("SubmittedAt")) {
      patch[key] = value;
    }
  }
  return answered ? patch : null;
}
