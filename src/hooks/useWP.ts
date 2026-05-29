import { useState, useEffect } from "react";
import { WP_QUESTIONS } from "../data/wpQuestions";

export type WpAnswer = {
  questionId: string;
  optionId: string;
};

export type WpState = {
  answers: WpAnswer[];
};

const STORAGE_KEY = "solverah_wp";

const DEFAULT_STATE: WpState = {
  answers: [],
};

function readFromStorage(): WpState {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_STATE;
    return JSON.parse(raw) as WpState;
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

  function resetWP() {
    setState(DEFAULT_STATE);
  }

  return { state, isComplete, setAnswer, resetWP };
}
