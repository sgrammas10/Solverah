/**
 * "Not now" on the first-run "What brings you here?" dialog: hide it for one
 * day, per user. Mirrors `intakePromptSnooze` (G41). A UI preference, not a
 * draft -- the key matches no prefix in USER_DRAFT_KEY_PREFIXES, so logout does
 * not wipe the snooze. Storage can throw (private window, blocked site data);
 * every access is guarded and a missing or invalid value means "not snoozed".
 */
export const CAREER_MOMENT_PROMPT_SNOOZE_MS = 24 * 60 * 60 * 1000;

const keyFor = (userId: string | number | null | undefined): string =>
  `solverah.careerMomentPromptSnoozedUntil:${userId ?? 'anonymous'}`;

export function isCareerMomentPromptSnoozed(
  userId: string | number | null | undefined,
  now: number = Date.now(),
): boolean {
  try {
    const raw = window.localStorage.getItem(keyFor(userId));
    if (!raw) return false;
    const until = Number(raw);
    return Number.isFinite(until) && until > now;
  } catch {
    return false;
  }
}

export function snoozeCareerMomentPrompt(
  userId: string | number | null | undefined,
  now: number = Date.now(),
): void {
  try {
    window.localStorage.setItem(keyFor(userId), String(now + CAREER_MOMENT_PROMPT_SNOOZE_MS));
  } catch {
    /* the dialog just reopens next visit */
  }
}
