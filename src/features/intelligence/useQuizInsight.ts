import { useEffect, useState } from "react";

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
  const [insightLoading, setInsightLoading] = useState(false);
  const [insightProgress, setInsightProgress] = useState(0);
  const [insightError, setInsightError] = useState<string | null>(null);
  const [insightResponse, setInsightResponse] = useState<QuizInsightResponse | null>(null);

  useEffect(() => {
    if (!insightLoading) return;
    setInsightProgress(8);
    const id = setInterval(() => {
      setInsightProgress((prev) => (prev < 90 ? Math.min(90, prev + 6 + Math.random() * 6) : prev));
    }, PROGRESS_TICK_MS);
    return () => clearInterval(id);
  }, [insightLoading]);

  const openInsight = () => {
    setInsightModalOpen(true);
    setInsightLoading(true);
    setInsightError(null);
  };

  const handleInsightClose = () => {
    setInsightModalOpen(false);
    setInsightError(null);
    setInsightProgress(0);
  };

  return {
    insightModalOpen,
    insightLoading,
    setInsightLoading,
    insightProgress,
    setInsightProgress,
    insightError,
    setInsightError,
    insightResponse,
    setInsightResponse,
    openInsight,
    handleInsightClose,
  };
}
