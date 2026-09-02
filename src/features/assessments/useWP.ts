/**
 * useWP — state for the original 12-question Work Pulse quiz (legacy; see
 * WorkPulsePage's header for why the live instrument no longer uses it).
 *
 * ── THE SPLIT: WHO OWNS WHAT, AND WHY IT IS EXACTLY THIS ────────────────────
 *
 * `answers` — sessionStorage, and only sessionStorage. A guest may answer all
 * twelve questions signed out and only then sign in; the resume works because
 * sessionStorage neither knows nor cares about the session, so the answers are
 * still there when WorkPulseResultsPage mounts with fresh credentials and
 * enqueues them. The TanStack Query cache cannot own this state: it holds
 * server data keyed by queries, and these answers have never been to the
 * server — there is nothing to fetch them back from.
 *
 * `cachedResult` — the query cache, under `workPulseResultKeys.result()`, and
 * only the query cache. The narrative is server data (it exists only once a
 * scoring job has run and the server has stored it), so the query keyed to
 * `GET /me/assessments/work_pulse/result` is its single home. This hook holds
 * a read-only observer on that key (`skipToken`: it never fetches — fetching
 * is `useWorkPulseResult`'s job, with auth attached); `setCachedResult` writes
 * the key directly, which is how a just-succeeded scoring job's result reaches
 * every consumer of the key without a second request. The result is no longer
 * persisted to sessionStorage: after a reload the server copy is authoritative
 * and `useWorkPulseResult` re-reads it, whereas a persisted copy could survive
 * a retake and present a stale narrative with nothing to invalidate it.
 *
 * Do not merge the two sides. Moving `answers` into the query would break the
 * guest resume above; persisting `cachedResult` again would re-create the
 * two-sources-of-truth problem the Phase 4 dedup removed.
 */
import { useEffect, useState } from "react";
import { skipToken, useQuery, useQueryClient } from "@tanstack/react-query";

import { workPulseResultKeys } from "./useWorkPulseResult";
import { WP_QUESTIONS } from "./data/wpQuestions";

export type WpAnswer = {
  questionId: string;
  optionId: string;
};

export type WpApiResponse = {
  narrative: string;
  emerging_signals: { title: string; description: string }[];
  archetype: string;
  archetype_description: string;
};

export type WpState = {
  answers: WpAnswer[];
  cachedResult: WpApiResponse | null;
};

const STORAGE_KEY = "solverah_wp";

function readAnswersFromStorage(): WpAnswer[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    // Older sessions stored `{ answers, cachedResult }`; the result half is
    // ignored on read (the server copy is re-fetched instead) and dropped on
    // the next write.
    const parsed = JSON.parse(raw) as Partial<WpState>;
    return parsed.answers ?? [];
  } catch {
    return [];
  }
}

export function useWP() {
  const queryClient = useQueryClient();
  const [answers, setAnswers] = useState<WpAnswer[]>(readAnswersFromStorage);

  // Observer only: `skipToken` means this never issues a request (it has no
  // auth to issue one with — a guest renders this hook). Data appears here
  // when `useWorkPulseResult` fetches the key or `setCachedResult` writes it.
  const cachedQuery = useQuery<WpApiResponse>({
    queryKey: workPulseResultKeys.result(),
    queryFn: skipToken,
  });
  const cachedResult = cachedQuery.data ?? null;

  useEffect(() => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ answers }));
  }, [answers]);

  const isComplete = answers.length === WP_QUESTIONS.length;

  function setAnswer(questionId: string, optionId: string) {
    setAnswers((prev) => {
      const rest = prev.filter((a) => a.questionId !== questionId);
      return [...rest, { questionId, optionId }];
    });
  }

  function setCachedResult(result: WpApiResponse) {
    queryClient.setQueryData(workPulseResultKeys.result(), result);
  }

  function resetWP() {
    setAnswers([]);
    queryClient.removeQueries({ queryKey: workPulseResultKeys.result() });
  }

  const state: WpState = { answers, cachedResult };

  return { state, isComplete, setAnswer, setCachedResult, resetWP };
}
