/**
 * useMP -- state for the manager-profile forced-choice quiz.
 *
 * Simpler than `useMM`: manager-profile scores deterministically and
 * instantly (`solverah/services/manager_playbook_service.py`'s docstring --
 * "like `focus_type` and unlike `manager_match`"), so there is no scoring job
 * and no query-cache result tier to hold. `answers` in sessionStorage is the
 * only state, carrying in-progress answers across a mid-quiz reload exactly
 * as `useMM`'s does.
 *
 * The draft is keyed by the signed-in user's id (`mp_answers:<id>`), the same
 * way `useMM` keys `mm_answers:<id>` (G59). It used to be one tab-wide
 * `mp_answers` key, so after a silent session expiry the next account to sign
 * in on that tab inherited the draft, and ManagerProfilePage's auto-submit of a
 * complete draft would score it as theirs. A pre-scoping `mp_answers` key is
 * removed on sight rather than adopted: it has no owner to adopt it for.
 * Without a user there is no key at all and the draft lives in memory only
 * (the route sits behind `RequireAuth`, so that is a transient state, not a
 * mode). The logout sweep in `auth/draftStorage.ts` matches the `mp_answers`
 * prefix, which covers both the bare and the suffixed key.
 */
import { useState } from "react";

import { useAuth } from "../auth";

export interface MPAnswer {
  questionId: string;
  choice: "a" | "b";
}

/** Prefix of every per-user draft key. */
export const MP_DRAFT_KEY_PREFIX = "mp_answers:";

/** The unscoped key every draft used before it was keyed by user. */
const LEGACY_STORAGE_KEY = "mp_answers";

/** The draft key for `userId`, or null when nobody is signed in. */
export function mpDraftKey(userId: string | null | undefined): string | null {
  return userId ? `${MP_DRAFT_KEY_PREFIX}${userId}` : null;
}

function safeRemove(key: string) {
  try {
    sessionStorage.removeItem(key);
  } catch {
    // Storage unavailable: nothing persisted, so nothing to remove.
  }
}

function readAnswers(key: string | null): MPAnswer[] {
  safeRemove(LEGACY_STORAGE_KEY);
  if (!key) return [];
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as MPAnswer[]) : [];
  } catch {
    return [];
  }
}

export function useMP() {
  const { user } = useAuth();
  const storageKey = mpDraftKey(user?.id);

  const [answers, setAnswers] = useState<MPAnswer[]>(() => readAnswers(storageKey));
  // A different user on the same mount must not keep the previous user's
  // in-memory answers. Adjusted during render, not in an effect, so no render
  // ever pairs one user's key with another user's answers.
  const [loadedKey, setLoadedKey] = useState(storageKey);
  if (loadedKey !== storageKey) {
    setLoadedKey(storageKey);
    setAnswers(readAnswers(storageKey));
  }

  function setAnswer(questionId: string, choice: "a" | "b") {
    setAnswers((prev) => {
      const rest = prev.filter((a) => a.questionId !== questionId);
      const next = [...rest, { questionId, choice }];
      if (storageKey) {
        try {
          sessionStorage.setItem(storageKey, JSON.stringify(next));
        } catch {
          // Storage full or blocked: the draft stays in memory for this mount.
        }
      }
      return next;
    });
  }

  function reset() {
    setAnswers([]);
    if (storageKey) safeRemove(storageKey);
  }

  return { answers, setAnswer, reset };
}
