/**
 * "Maybe later" on the complete-your-profile popup (G41): hide it for 7 days,
 * per user. A UI preference, not a draft -- the key deliberately matches no
 * prefix in USER_DRAFT_KEY_PREFIXES, so logout does not wipe the snooze.
 * Storage can throw (private window, blocked site data); every access is
 * guarded and a missing or invalid value means "not snoozed".
 */
export const INTAKE_PROMPT_SNOOZE_MS = 7 * 24 * 60 * 60 * 1000;

const keyFor = (userId: string | number | null | undefined): string =>
  `solverah.intakePromptSnoozedUntil:${userId ?? 'anonymous'}`;

export function isIntakePromptSnoozed(
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

export function snoozeIntakePrompt(
  userId: string | number | null | undefined,
  now: number = Date.now(),
): void {
  try {
    window.localStorage.setItem(keyFor(userId), String(now + INTAKE_PROMPT_SNOOZE_MS));
  } catch {
    /* the popup just reopens next visit */
  }
}
