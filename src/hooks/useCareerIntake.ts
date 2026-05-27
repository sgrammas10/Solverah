import { useState, useEffect } from "react";

export type CareerIntakeState = {
  step: 1 | 2 | 3 | 4;
  selectedStatementIds: string[];
  wplAnswers: { questionId: string; optionId: string }[];
};

const STORAGE_KEY = "solverah_intake";

const DEFAULT_STATE: CareerIntakeState = {
  step: 1,
  selectedStatementIds: [],
  wplAnswers: [],
};

function readFromStorage(): CareerIntakeState {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_STATE;
    return JSON.parse(raw) as CareerIntakeState;
  } catch {
    return DEFAULT_STATE;
  }
}

export function useCareerIntake() {
  const [state, setState] = useState<CareerIntakeState>(readFromStorage);

  useEffect(() => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [state]);

  function setStep(step: 1 | 2 | 3 | 4) {
    setState((s) => ({ ...s, step }));
  }

  function toggleStatement(id: string) {
    setState((s) => ({
      ...s,
      selectedStatementIds: s.selectedStatementIds.includes(id)
        ? s.selectedStatementIds.filter((x) => x !== id)
        : [...s.selectedStatementIds, id],
    }));
  }

  function setWplAnswer(questionId: string, optionId: string) {
    setState((s) => {
      const rest = s.wplAnswers.filter((a) => a.questionId !== questionId);
      return { ...s, wplAnswers: [...rest, { questionId, optionId }] };
    });
  }

  function resetIntake() {
    setState(DEFAULT_STATE);
  }

  return { state, setStep, toggleStatement, setWplAnswer, resetIntake };
}
