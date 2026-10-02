/**
 * draftStorage.ts — the browser-storage keys that hold one person's answers,
 * and the sweep that removes them when their session ends.
 *
 * Every instrument drafts its in-progress answers client-side (there is no
 * server-side draft anywhere in the product; USER_SCENARIOS.md Appendix A).
 * Those drafts are keyed by instrument, not by account, so on a shared tab
 * user B was offered user A's half-finished Manager Match. The instrument
 * lanes are scoping their own keys to the user; this sweep is the backstop
 * that runs at logout regardless, and it is the ONE place that knows the full
 * list -- a slice adding a draft key adds it here too.
 *
 * ── What is and is not on the list ──────────────────────────────────────────
 *
 * On it: anything that holds answers or profile-shaped data. That includes
 * `pendingQuizSave`, the guest quiz's answers held for replay at the next
 * sign-in -- a logout is exactly the moment that "next sign-in" stops being
 * the person who answered. (Sign-in itself never touches it: a guest who
 * answered and then signs in must get their replay.)
 *
 * Not on it: pure UI state that belongs to the browser rather than the
 * person. `guestQuizCompletedAt` is the one-quiz-per-device lockout, and
 * `solverah.hasSession` is the boot hint, which `rememberSession(false)`
 * already handles on its own terms.
 *
 * ── Matched by prefix ───────────────────────────────────────────────────────
 *
 * Lanes are adding a user-id suffix to their keys this wave
 * (`focus_type_draft:42`), and `useEnvReport` already has `env_report_answers`
 * next to `env_report_answers_past`. `startsWith` covers the bare key, the
 * suffixed one, and whatever separator a lane picks, so this list does not
 * have to track that choice. The cost is that a prefix also matches any other
 * key that happens to start with it -- which is why the prefixes are the full
 * instrument names rather than anything shorter.
 */

/** Prefixes of every storage key that holds a person's answers or profile data. */
export const USER_DRAFT_KEY_PREFIXES: readonly string[] = [
  "solverah_assessment_answers", // Work Pulse core (24) — useAssessment
  "env_report_answers",          // Environment Report, current + _past — useEnvReport
  "mp_answers",                  // Manager Profile — useMP
  "mm_answers",                  // Manager Match — useMM
  "solverah_wp",                 // legacy 12-question Work Pulse — useWP
  "solverah_intake",             // /start wizard: statements + WPLL answers — useCareerIntake
  "focus_type_draft",            // FocusType — FocusTypePage
  "pendingQuizSave",             // guest quiz answers held for replay — guestQuiz.ts
];

/** Whether `key` names a per-user draft, by prefix. */
export function isUserDraftKey(key: string): boolean {
  return USER_DRAFT_KEY_PREFIXES.some((prefix) => key.startsWith(prefix));
}

/**
 * Remove every per-user draft from `sessionStorage` and `localStorage`.
 *
 * Keys are collected before anything is removed: `Storage` is index-addressed
 * and removing while walking `key(i)` skips every other entry. Each storage is
 * swept inside its own try/catch because either can be absent (a non-browser
 * runtime) or throw on access (a private window with site data blocked), and
 * a draft sweep must never be what stops a logout from finishing.
 */
export function clearUserDrafts(): void {
  for (const name of ["sessionStorage", "localStorage"] as const) {
    try {
      const storage = globalThis[name];
      if (!storage) continue;
      const doomed: string[] = [];
      for (let i = 0; i < storage.length; i += 1) {
        const key = storage.key(i);
        if (key !== null && isUserDraftKey(key)) doomed.push(key);
      }
      for (const key of doomed) storage.removeItem(key);
    } catch {
      // Storage unavailable: there is nothing of this person's held there.
    }
  }
}
