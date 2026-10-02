/**
 * useQuizSubmission — the submit half of the three quiz pages.
 *
 * Built on useQuizInsight (modal + generation state). What lives here is what
 * the pages used to each hand-roll, and got wrong in the same ways
 * (2026-10-02 audit):
 *
 *   - #2 guest lockout: the lockout marker and the pending save were written
 *     BEFORE the insight call, so a failed call locked the guest out with
 *     nothing. They are written by `completeGuestQuiz`, after success only, and
 *     the guest insight is stored with them (G20).
 *   - a submit with no answers is refused here, before anything is sent.
 *   - #6 every signed-in request carries every saved quiz, so the server's
 *     "Across all your quizzes" synthesis really is across all of them.
 *   - #8 the profile cache is invalidated after every signed-in insight POST,
 *     so /quiz-insights reads the new insight, not the pre-POST copy.
 *   - #14 failures surface as `saveError` for inline display, not `alert()`.
 *
 * The two call sites keep their literal path shapes, which is what the
 * frontend contract scan (tests/test_frontend_contract.py) matches on.
 */
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { useAuth } from "../auth";
import { profileKeys, useProfileActions } from "../profile";
import { API_BASE } from "../../shared/api/api";
import { errorMessage, parseApiError } from "../../shared/api/apiError";
import { completeGuestQuiz, replayQuizResults } from "../../shared/lib/guestQuiz";
import { buildAllQuizzesPayload, type QuizRequestPayload } from "./quizPayload";
import { useQuizInsight, type QuizInsightResponse } from "./useQuizInsight";

export const NO_ANSWERS_MESSAGE = "Answer at least one question to get your insight.";
const SAVE_FAILED_MESSAGE = "We couldn't save your answers. Please try again.";
const EMPTY_INSIGHT_MESSAGE = "We couldn't generate your insight right now. Please try again.";

export function useQuizSubmission() {
  const insight = useQuizInsight();
  const { openInsight } = insight;
  const { fetchWithAuth } = useAuth();
  const { fetchProfileData, saveProfileData } = useProfileActions();
  const queryClient = useQueryClient();
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  /**
   * Guest preview: one quiz, nothing persisted server-side. `quizResults` is
   * what Login.tsx replays onto the account after sign-in.
   */
  const submitGuest = (payload: QuizRequestPayload, quizResults: Record<string, unknown>) => {
    setSaveError(null);
    if (!payload.quizzes.length) {
      setSaveError(NO_ANSWERS_MESSAGE);
      return;
    }
    openInsight(async () => {
      const res = await fetch(`${API_BASE}/intake/quiz-preview/insights`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw parseApiError(res, data, "Failed to generate insights.");
      }
      const result = {
        overallSummary: data?.overallSummary || null,
        insights: Array.isArray(data?.insights) ? data.insights : [],
      };
      if (!result.insights.length) throw new Error(EMPTY_INSIGHT_MESSAGE);
      // Only now: the guest has an insight to show for the quiz they spent.
      completeGuestQuiz({ quizGroup: payload.quizGroup, quizResults, quizPayload: payload }, result);
      return result;
    });
  };

  /**
   * Signed in: save the answers, then generate insights for every saved quiz.
   *
   * `pageResults` is this page's slice of `quizResults`, e.g.
   * `{ careerJobSearch: {...}, careerJobSearchSubmittedAt }`. Only that slice
   * is PATCHed, with the nested career-quiz map merged against the stored one
   * (the server merges one level shallower). Returns true when saved.
   */
  const submitSignedIn = async (pageResults: Record<string, unknown>): Promise<boolean> => {
    setSaveError(null);
    setSaving(true);
    let allResults: Record<string, unknown>;
    try {
      const current = await fetchProfileData();
      const existing = (current?.profileData as { quizResults?: Record<string, unknown> } | undefined)
        ?.quizResults;
      const patch = replayQuizResults(existing, pageResults);
      if (!patch) {
        setSaveError(NO_ANSWERS_MESSAGE);
        return false;
      }
      await saveProfileData({ quizResults: patch });
      allResults = { ...(existing ?? {}), ...patch };
    } catch (err) {
      setSaveError(errorMessage(err, SAVE_FAILED_MESSAGE));
      return false;
    } finally {
      setSaving(false);
    }

    const payload = buildAllQuizzesPayload(allResults);
    if (payload.quizzes.length) {
      openInsight(async (): Promise<QuizInsightResponse> => {
        const res = await fetchWithAuth("/me/quiz-insights", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        await queryClient.invalidateQueries({ queryKey: profileKeys.document() });
        return {
          overallInsight: res?.overallInsight || null,
          insights: Array.isArray(res?.insights) ? res.insights : [],
        };
      });
    }
    return true;
  };

  return {
    ...insight,
    saveError,
    saving,
    setSaveError,
    submitGuest,
    submitSignedIn,
  };
}
