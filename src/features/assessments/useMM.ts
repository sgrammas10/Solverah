/**
 * useMM — state for the ManagerMatch forced-choice quiz.
 *
 * The split mirrors `useWP` (see that file's header for the full reasoning):
 *
 * `answers` — sessionStorage, the source of truth for in-progress answers.
 * They have never been to the server, so no query can restore them; storage is
 * what carries them across a mid-quiz reload, and across a reload while the
 * scoring job is still running.
 *
 * The draft is keyed by the signed-in user's id (`mm_answers:<id>`). It used
 * to be one tab-wide `mm_answers` key, so a second account signing in on the
 * same tab inherited the first account's draft, and ManagerMatchPage's
 * resume-on-mount would then score those answers as the second user's. A
 * pre-scoping `mm_answers` key is removed on sight rather than adopted: it has
 * no owner to adopt it for. Without a user there is no key at all and the
 * draft lives in memory only (the route sits behind `RequireAuth`, so that is
 * a transient state, not a mode).
 *
 * The draft is cleared when a scoring succeeds (`clearAnswers`). A finished
 * sitting has nothing left to resume, and leaving it behind is what let a
 * later visit to `/manager-match` silently re-score it.
 *
 * `cachedResult` — the TanStack Query cache, under
 * `managerMatchResultKeys.result()`. This used to be a module-level singleton
 * (`let _state`), which existed only so two sequentially-mounted consumers
 * could see one result object. The query cache is that singleton, properly
 * keyed: this hook holds a read-only observer on the key (`skipToken` — it
 * never fetches; `useManagerMatchResult` does, with auth attached), and
 * `setCachedResult` writes the key directly, which is how a just-succeeded
 * scoring job's result reaches ManagerMatchResultsPage without a request.
 */
import { useState } from "react";
import { skipToken, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "../auth";
import { managerMatchResultKeys } from "./useManagerMatchResult";

export interface MMAnswer {
  questionId: string;
  choice: 'a' | 'b';
}

export interface MMResult {
  archetype: string;
  dimension_scores: Record<string, number>;
  narrative: string;
  what_to_look_for: string[];
  red_flags: string[];
  archetype_description: string;
}

export interface MMState {
  answers: MMAnswer[];
  cachedResult: MMResult | null;
}

/**
 * Prefix of every per-user draft key. Exported so a sign-out sweep can find
 * the drafts without knowing which user wrote them.
 */
export const MM_DRAFT_KEY_PREFIX = "mm_answers:";

/** The unscoped key every draft used before it was keyed by user. */
const LEGACY_STORAGE_KEY = "mm_answers";

/** The draft key for `userId`, or null when nobody is signed in. */
export function mmDraftKey(userId: string | null | undefined): string | null {
  return userId ? `${MM_DRAFT_KEY_PREFIX}${userId}` : null;
}

function safeRemove(key: string) {
  try {
    sessionStorage.removeItem(key);
  } catch {
    // Storage unavailable: nothing persisted, so nothing to remove.
  }
}

function readAnswers(key: string | null): MMAnswer[] {
  safeRemove(LEGACY_STORAGE_KEY);
  if (!key) return [];
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as MMAnswer[]) : [];
  } catch {
    return [];
  }
}

export function useMM() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const storageKey = mmDraftKey(user?.id);

  const [answers, setAnswers] = useState<MMAnswer[]>(() => readAnswers(storageKey));
  // A different user on the same mount (sign-out then sign-in without a
  // remount) must not keep the previous user's in-memory answers. Adjusting
  // state during render, not in an effect, so no render ever pairs one user's
  // key with another user's answers.
  const [loadedKey, setLoadedKey] = useState(storageKey);
  if (loadedKey !== storageKey) {
    setLoadedKey(storageKey);
    setAnswers(readAnswers(storageKey));
  }

  // Observer only — see the header. Data appears when a scoring job's result
  // is written here or when `useManagerMatchResult` fetches the stored copy.
  const cachedQuery = useQuery<MMResult>({
    queryKey: managerMatchResultKeys.result(),
    queryFn: skipToken,
  });
  const cachedResult = cachedQuery.data ?? null;

  function setAnswer(questionId: string, choice: 'a' | 'b') {
    setAnswers((prev) => {
      const rest = prev.filter((a) => a.questionId !== questionId);
      const next = [...rest, { questionId, choice }];
      // Written through here rather than from an effect, so `reset()` removing
      // the key stays removed instead of being re-written as `[]`. Idempotent,
      // so Strict Mode re-running the updater is harmless.
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

  function setCachedResult(result: MMResult) {
    queryClient.setQueryData(managerMatchResultKeys.result(), result);
  }

  /** Drop the draft and keep any result. What a succeeded scoring calls. */
  function clearAnswers() {
    setAnswers([]);
    if (storageKey) safeRemove(storageKey);
  }

  /** Drop the draft and the cached result. What a retake or "Start over" calls. */
  function reset() {
    clearAnswers();
    queryClient.removeQueries({ queryKey: managerMatchResultKeys.result() });
  }

  const state: MMState = { answers, cachedResult };

  return { state, setAnswer, setCachedResult, clearAnswers, reset };
}
