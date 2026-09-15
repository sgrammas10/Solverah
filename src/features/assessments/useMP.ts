/**
 * useMP -- state for the manager-profile forced-choice quiz.
 *
 * Simpler than `useMM`: manager-profile scores deterministically and
 * instantly (`solverah/services/manager_playbook_service.py`'s docstring --
 * "like `focus_type` and unlike `manager_match`"), so there is no scoring job
 * and no query-cache result tier to hold. `answers` in sessionStorage is the
 * only state, carrying in-progress answers across a mid-quiz reload exactly
 * as `useMM`'s does.
 */
import { useState } from "react";

export interface MPAnswer {
  questionId: string;
  choice: "a" | "b";
}

const STORAGE_KEY = "mp_answers";

function readAnswers(): MPAnswer[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as MPAnswer[]) : [];
  } catch {
    return [];
  }
}

export function useMP() {
  const [answers, setAnswers] = useState<MPAnswer[]>(readAnswers);

  function setAnswer(questionId: string, choice: "a" | "b") {
    setAnswers((prev) => {
      const rest = prev.filter((a) => a.questionId !== questionId);
      const next = [...rest, { questionId, choice }];
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }

  function reset() {
    setAnswers([]);
    sessionStorage.removeItem(STORAGE_KEY);
  }

  return { answers, setAnswer, reset };
}
