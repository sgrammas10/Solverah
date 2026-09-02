/**
 * useQuizInsight — modal + generation state for the quiz insight flows.
 *
 * The generation call is a mutation owned here, so the three quiz tabs read
 * `insightLoading`/`insightError` off the mutation instead of each hand-rolling
 * a loading boolean and an error string around their fetch. The caller still
 * owns the transport: the guest preview posts with a bare `fetch` (no session
 * behind it) and the signed-in tabs post through `fetchWithAuth`, and both call
 * sites keep their literal path shapes, which is what the frontend contract
 * scan matches on.
 */
import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { errorMessage } from "../../shared/api/apiError";

const PROGRESS_TICK_MS = 350;

export type QuizInsight = {
  key?: string;
  title?: string;
  summary?: string;
  keyTakeaways?: string[];
  combinedMeaning?: string;
  nextSteps?: string[];
};

export type QuizInsightResponse = {
  overallSummary?: string | null;
  overallInsight?: { summary?: string; keyTakeaways?: string[]; nextSteps?: string[] } | null;
  insights: QuizInsight[];
};

export function useQuizInsight() {
  const [insightModalOpen, setInsightModalOpen] = useState(false);
  const [insightProgress, setInsightProgress] = useState(0);
  // Stays state rather than the mutation's `data`: the tabs also seed this
  // with insights already stored on the profile document.
  const [insightResponse, setInsightResponse] = useState<QuizInsightResponse | null>(null);

  const generateInsight = useMutation({
    mutationFn: (request: () => Promise<QuizInsightResponse>) => request(),
    onSuccess: (data) => {
      setInsightResponse(data);
      setInsightProgress(100);
    },
  });

  const insightLoading = generateInsight.isPending;
  const insightError = generateInsight.isError
    ? errorMessage(generateInsight.error, "Failed to generate insights.")
    : null;

  // Simulated progress — UX, not server state. The mutation lifecycle drives
  // it: isPending starts the ticker, settling (either way) ends it.
  useEffect(() => {
    if (!insightLoading) return;
    setInsightProgress(8);
    const id = setInterval(() => {
      setInsightProgress((prev) => (prev < 90 ? Math.min(90, prev + 6 + Math.random() * 6) : prev));
    }, PROGRESS_TICK_MS);
    return () => clearInterval(id);
  }, [insightLoading]);

  /** Open the modal and run the caller's generation request through the mutation. */
  const openInsight = (request: () => Promise<QuizInsightResponse>) => {
    setInsightModalOpen(true);
    generateInsight.mutate(request);
  };

  const handleInsightClose = () => {
    setInsightModalOpen(false);
    setInsightProgress(0);
    generateInsight.reset();
  };

  return {
    insightModalOpen,
    insightLoading,
    insightProgress,
    insightError,
    insightResponse,
    setInsightResponse,
    openInsight,
    handleInsightClose,
  };
}
