import { useState } from "react";

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

function _readAnswers(): MMAnswer[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as MMAnswer[]) : [];
  } catch {
    return [];
  }
}

// Module-level singleton: initialised once from sessionStorage on module load.
let _state: MMState = { answers: _readAnswers(), cachedResult: null };

// Re-reads sessionStorage to simulate module re-initialisation (tests only).
export function _resetMMState() {
  _state = { answers: _readAnswers(), cachedResult: null };
}

export function useMM() {
  const [state, setState] = useState<MMState>(_state);

  function setAnswer(questionId: string, choice: 'a' | 'b') {
    const rest = _state.answers.filter((a) => a.questionId !== questionId);
    _state = { ..._state, answers: [...rest, { questionId, choice }] };
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(_state.answers));
    setState(_state);
  }

  function setCachedResult(result: MMResult) {
    _state = { ..._state, cachedResult: result };
    setState(_state);
  }

  function reset() {
    _state = { answers: [], cachedResult: null };
    sessionStorage.removeItem(STORAGE_KEY);
    setState(_state);
  }

  return { state, setAnswer, setCachedResult, reset };
}
