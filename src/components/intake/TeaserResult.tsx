import { useState, useEffect, useCallback } from "react";
import { API_BASE } from "../../utils/api";
import TierBar from "./TierBar";

interface TeaserResultProps {
  wpllAnswers: { questionId: string; optionId: string }[];
  onInsightReceived: (text: string) => void;
  cachedInsightText: string;
  onContinue: () => void;
}

type FetchState = "loading" | "error" | "success";

const FALLBACK_LOCKED_SECTIONS = [
  "Environmental Friction Score",
  "Work Rhythm Pattern",
  "Emerging Archetype Signals",
];

export default function TeaserResult({
  wpllAnswers,
  onInsightReceived,
  cachedInsightText,
  onContinue,
}: TeaserResultProps) {
  const [fetchState, setFetchState] = useState<FetchState>(
    cachedInsightText ? "success" : "loading"
  );
  const [insightText, setInsightText] = useState(cachedInsightText);
  const [lockedSections, setLockedSections] = useState<string[]>(
    cachedInsightText ? FALLBACK_LOCKED_SECTIONS : []
  );

  const fetchInsight = useCallback(async () => {
    setFetchState("loading");
    try {
      const response = await fetch(`${API_BASE}/assessments/wpll/submissions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          answers: wpllAnswers.map((a) => ({
            question_id: a.questionId,
            option_id: a.optionId,
          })),
        }),
      });

      if (!response.ok) throw new Error("Non-OK response");

      const data = (await response.json()) as {
        insight_text: string;
        locked_sections: string[];
      };

      const sections =
        data.locked_sections?.length >= 3
          ? data.locked_sections.slice(0, 3)
          : FALLBACK_LOCKED_SECTIONS;

      setInsightText(data.insight_text);
      setLockedSections(sections);
      onInsightReceived(data.insight_text);
      setFetchState("success");
    } catch {
      setFetchState("error");
    }
  }, [wpllAnswers, onInsightReceived]);

  useEffect(() => {
    if (!cachedInsightText) {
      fetchInsight();
    }
  }, [cachedInsightText, fetchInsight]);

  if (fetchState === "loading") {
    return (
      <div className="flex flex-col items-center gap-4 py-16">
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
        <p className="text-sm text-ink-secondary">Reading your responses…</p>
      </div>
    );
  }

  if (fetchState === "error") {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
        <p className="font-medium mb-1">We couldn't generate your insight right now.</p>
        <p className="text-xs">Please try again in a moment.</p>
        <button onClick={fetchInsight} className="mt-3 text-xs font-semibold text-red-700 underline">
          Try again
        </button>
      </div>
    );
  }

  const displayedSections =
    lockedSections.length >= 3 ? lockedSections.slice(0, 3) : FALLBACK_LOCKED_SECTIONS;

  return (
    <div>
      <p className="text-sm font-semibold uppercase tracking-widest text-forest-light mb-3">
        Here's what's emerging from your responses
      </p>

      <div className="rounded-xl border border-cream-muted bg-white p-6">
        <p className="text-base text-ink-primary leading-relaxed">{insightText}</p>
      </div>

      {displayedSections.map((title) => (
        <div
          key={title}
          className="rounded-lg border border-cream-muted bg-cream-base p-4 mt-3 flex items-center justify-between"
        >
          <div>
            <div className="flex items-center gap-2">
              <span className="text-ink-tertiary text-sm">🔒</span>
              <span className="text-sm font-medium text-ink-primary">{title}</span>
            </div>
            <p className="text-xs text-ink-tertiary mt-0.5">Unlock with a free account</p>
          </div>
          <div className="flex flex-col gap-1.5 ml-4 shrink-0">
            <div className="bg-cream-muted rounded h-2 w-24 opacity-60" />
            <div className="bg-cream-muted rounded h-2 w-16 opacity-60" />
            <div className="bg-cream-muted rounded h-2 w-20 opacity-60" />
          </div>
        </div>
      ))}

      <div className="mt-8 mb-8">
        <TierBar />
      </div>

      <button
        type="button"
        onClick={onContinue}
        className="w-full bg-forest-dark text-white font-semibold py-3.5 rounded hover:bg-forest-mid transition-colors"
      >
        Create my free account →
      </button>

      <p className="text-xs text-ink-tertiary text-center mt-2">
        No credit card required. Takes 60 seconds.
      </p>
    </div>
  );
}
