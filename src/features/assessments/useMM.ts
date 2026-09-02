/**
 * useMM — state for the ManagerMatch forced-choice quiz.
 *
 * The split mirrors `useWP` (see that file's header for the full reasoning):
 *
 * `answers` — sessionStorage, the source of truth for in-progress answers.
 * They have never been to the server, so no query can restore them; storage is
 * what carries them across the ManagerMatchPage → results navigation and a
 * mid-quiz reload.
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

const STORAGE_KEY = "mm_answers";

function readAnswers(): MMAnswer[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as MMAnswer[]) : [];
  } catch {
    return [];
  }
}

export function useMM() {
  const queryClient = useQueryClient();
  const [answers, setAnswers] = useState<MMAnswer[]>(readAnswers);

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
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }

  function setCachedResult(result: MMResult) {
    queryClient.setQueryData(managerMatchResultKeys.result(), result);
  }

  function reset() {
    setAnswers([]);
    sessionStorage.removeItem(STORAGE_KEY);
    queryClient.removeQueries({ queryKey: managerMatchResultKeys.result() });
  }

  const state: MMState = { answers, cachedResult };

  return { state, setAnswer, setCachedResult, reset };
}
