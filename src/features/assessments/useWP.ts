import { useState, useEffect } from "react";
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

const DEFAULT_STATE: WpState = {
  answers: [],
  cachedResult: null,
};

function readFromStorage(): WpState {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_STATE;
    const parsed = JSON.parse(raw) as Partial<WpState>;
    return {
      answers: parsed.answers ?? [],
      cachedResult: parsed.cachedResult ?? null,
    };
  } catch {
    return DEFAULT_STATE;
  }
}

export function useWP() {
  const [state, setState] = useState<WpState>(readFromStorage);

  useEffect(() => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [state]);

  const isComplete = state.answers.length === WP_QUESTIONS.length;

  function setAnswer(questionId: string, optionId: string) {
    setState((s) => {
      const rest = s.answers.filter((a) => a.questionId !== questionId);
      return { ...s, answers: [...rest, { questionId, optionId }] };
    });
  }

  function setCachedResult(result: WpApiResponse) {
    setState((s) => ({ ...s, cachedResult: result }));
  }

  function resetWP() {
    setState(DEFAULT_STATE);
  }

  return { state, isComplete, setAnswer, setCachedResult, resetWP };
}
