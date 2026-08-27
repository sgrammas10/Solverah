/**
 * useAssessment -- state for the person-side culture assessment.
 *
 * DIFFERS DELIBERATELY FROM useWP AND EVERY OTHER QUIZ HOOK IN THIS APP.
 *
 * The other quizzes import their questions from `src/data/*.ts`. This one must not, ever.
 * Item order is a correctness requirement, not a presentation choice:
 *
 *  - The 24 items form a graduated-difficulty ladder. Shown in difficulty order they read as
 *    "a little / somewhat / quite / extremely", and a respondent who wants to look decisive can
 *    simply endorse further down the list. The result is a perfectly consistent fabrication that
 *    the confidence measure scores HIGH.
 *  - The server shuffles per respondent and interleaves the six dimensions so no two adjacent
 *    items measure the same thing. That ordering is authoritative. If a TypeScript helper also
 *    computed an order, the two PRNGs would have to agree bit-for-bit forever across two
 *    languages, and a divergence would be silent -- it would corrupt a resumed session's
 *    ordering rather than raising.
 *
 * So: the client renders what the server sends, in the order it was sent. It does not sort,
 * group, reorder, reverse, or shuffle anything, and it never randomizes options.
 *
 * The payload carries no item ids and no dimension labels -- they are absent from the JSON, not
 * blanked, so they cannot be recovered from the DOM. Items are addressed by opaque per-
 * respondent tokens. Do not add anything to this hook that would let a token be traced back to
 * a dimension.
 */
import { useCallback, useEffect, useState } from "react";

import { useAuth } from "../contexts/useAuth";

export type AssessmentOption = {
  key: string;
  text: string;
};

export type AssessmentItem = {
  /** Opaque HMAC of (respondent, item). Not an item id, and not invertible by the client. */
  token: string;
  prompt: string;
  options: AssessmentOption[];
};

type AssessmentBlock = {
  block: number;
  items: AssessmentItem[];
};

export type AssessmentForm = {
  form_version: string;
  respondent_id: string;
  blocks: AssessmentBlock[];
};

export type AssessmentSubmitResponse = {
  submission_id: string;
  scoring_key_version: string;
  dimensions_scored: number;
};

/** {token: chosen option key} */
export type AssessmentAnswers = Record<string, string>;

export const EXPECTED_ITEM_COUNT = 24;

const STORAGE_KEY = "solverah_assessment_answers";

function readStoredAnswers(): AssessmentAnswers {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return parsed as AssessmentAnswers;
  } catch {
    return {};
  }
}

/**
 * Flatten the blocks into one ordered list.
 *
 * Block boundaries are NOT surfaced to the UI. Each block holds exactly one item per dimension,
 * so telling a respondent where a block ends tells them that every run of six contains one of
 * each -- which hands back a good part of what the interleave exists to hide. The blocks are a
 * server-side construction for building the order; to the respondent this is 24 questions in a
 * row.
 */
export function flattenItems(form: AssessmentForm): AssessmentItem[] {
  return form.blocks.flatMap((b) => b.items);
}

export function useAssessment() {
  const { fetchWithAuth } = useAuth();

  const [items, setItems] = useState<AssessmentItem[] | null>(null);
  const [answers, setAnswers] = useState<AssessmentAnswers>(readStoredAnswers);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const form = await fetchWithAuth<AssessmentForm>("/assessments/core/form");
        if (cancelled) return;

        const fetched = flattenItems(form);
        setItems(fetched);

        // Drop any stored answer whose token is not in the form we just received.
        //
        // Tokens are stable for a respondent, so on an ordinary resume every stored answer
        // still matches. They change if the active item file changes -- which means the stored
        // answers belong to a different instrument. Keeping them would submit answers to
        // questions this respondent was never shown; the server would reject the submission
        // wholesale on the first unknown token, which is correct but reads to the user as an
        // inexplicable failure at the very end. Dropping them here surfaces it as unanswered
        // questions instead, which is recoverable.
        const valid = new Set(fetched.map((i) => i.token));
        setAnswers((prev) => {
          const kept = Object.fromEntries(
            Object.entries(prev).filter(([token]) => valid.has(token))
          );
          return Object.keys(kept).length === Object.keys(prev).length ? prev : kept;
        });
      } catch (err) {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : "Could not load the assessment.");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [fetchWithAuth]);

  useEffect(() => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(answers));
  }, [answers]);

  const setAnswer = useCallback((token: string, optionKey: string) => {
    setAnswers((prev) => ({ ...prev, [token]: optionKey }));
  }, []);

  const answeredCount = items
    ? items.filter((i) => answers[i.token] !== undefined).length
    : 0;
  const isComplete = items !== null && answeredCount === items.length;

  const submit = useCallback(async (): Promise<AssessmentSubmitResponse | null> => {
    if (!items) return null;

    // Guard rather than trust the caller. A short set is not scoreable -- a mean over fewer
    // than four items per dimension does not land on the scoring lattice and cannot be compared
    // with a company score. The server refuses it too; failing here just spares the round trip.
    if (items.length !== EXPECTED_ITEM_COUNT) {
      setSubmitError(
        `The assessment returned ${items.length} questions, expected ${EXPECTED_ITEM_COUNT}.`
      );
      return null;
    }
    const responses = Object.fromEntries(
      items.map((i) => [i.token, answers[i.token]]).filter(([, v]) => v !== undefined)
    );
    if (Object.keys(responses).length !== items.length) {
      setSubmitError("Please answer every question before submitting.");
      return null;
    }

    setSubmitting(true);
    setSubmitError(null);
    try {
      const result = await fetchWithAuth<AssessmentSubmitResponse>("/assessments/core/submissions", {
        method: "POST",
        body: JSON.stringify({ responses }),
      });
      sessionStorage.removeItem(STORAGE_KEY);
      return result;
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Could not submit the assessment.");
      return null;
    } finally {
      setSubmitting(false);
    }
  }, [answers, fetchWithAuth, items]);

  return {
    items,
    answers,
    answeredCount,
    isComplete,
    loadError,
    submitError,
    submitting,
    setAnswer,
    submit,
  };
}
