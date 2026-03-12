import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/useAuth";

type InsightEntry = {
  title?: string;
  summary?: string;
  keyTakeaways?: string[];
  combinedMeaning?: string;
  nextSteps?: string[];
};

type InsightGroup = {
  _overallSummary?: string;
  _generatedAt?: string;
  _model?: string;
  [key: string]: any;
};

const groupTitles: Record<string, string> = {
  careerQuizzes: "Career Quizzes Insights",
  careerJobSearch: "Career & Job Search Insights",
  yourFutureYourWay: "Your Future, Your Way Insights",
};

export default function QuizInsights() {
  const { fetchProfileData } = useAuth();
  const [insightsData, setInsightsData] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const locationState = location.state as {
    insight?: { overallSummary?: string | null; insights?: InsightEntry[] };
  } | null;

  const group = useMemo(() => {
    const params = new URLSearchParams(location.search);
    return params.get("group") || "careerQuizzes";
  }, [location.search]);

  useEffect(() => {
    (async () => {
      try {
        if (!fetchProfileData) {
          setError("Unable to load insights.");
          return;
        }
        const data = await fetchProfileData();
        const profileData = data?.profileData || {};
        const quizInsights = (profileData as any)?.quizInsights;
        if (!quizInsights || typeof quizInsights !== "object") {
          setInsightsData(null);
        } else {
          setInsightsData(quizInsights as Record<string, any>);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load insights.");
      } finally {
        setLoading(false);
      }
    })();
  }, [fetchProfileData]);

  const renderInsightCard = (title: string, entry?: InsightEntry) => {
    if (!entry) return null;
    return (
      <div key={title} className="border border-cream-muted rounded-xl bg-white p-6">
        <h3 className="font-display text-lg font-semibold text-ink-primary mb-3">{title}</h3>

        {entry.summary && (
          <p className="text-sm text-ink-secondary leading-relaxed mb-4">{entry.summary}</p>
        )}

        {entry.keyTakeaways?.length ? (
          <div className="mb-4">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-2">
              Key takeaways
            </p>
            <ul className="space-y-1.5">
              {entry.keyTakeaways.map((item, idx) => (
                <li key={idx} className="flex items-start gap-2 text-sm text-ink-secondary">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-forest-light" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {entry.combinedMeaning && (
          <div className="mb-4">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-2">
              Combined meaning
            </p>
            <p className="text-sm text-ink-secondary leading-relaxed">{entry.combinedMeaning}</p>
          </div>
        )}

        {entry.nextSteps?.length ? (
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-2">
              Next steps
            </p>
            <ul className="space-y-1.5">
              {entry.nextSteps.map((item, idx) => (
                <li key={idx} className="flex items-start gap-2 text-sm text-ink-secondary">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-forest-mid" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    );
  };

  const content = (() => {
    if (!insightsData && locationState?.insight?.insights?.length) {
      return (
        <div className="mt-6 grid gap-4">
          {locationState.insight.overallSummary ? (
            <div className="rounded-xl border border-forest-pale bg-forest-pale px-5 py-4 text-sm text-forest-dark">
              <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-mid mb-2">
                Overall summary
              </p>
              <p className="leading-relaxed">{locationState.insight.overallSummary}</p>
            </div>
          ) : null}
          {locationState.insight.insights.map((entry, idx) =>
            renderInsightCard(entry.title || `Insight ${idx + 1}`, entry),
          )}
        </div>
      );
    }

    if (!insightsData) return null;

    if (group === "careerQuizzes") {
      const groupData = insightsData.careerQuizzes as InsightGroup | undefined;
      if (!groupData) return null;
      const cards = Object.keys(groupData)
        .filter((key) => !key.startsWith("_"))
        .map((key) => {
          const entry = groupData[key] as InsightEntry;
          return renderInsightCard(entry?.title || key, entry);
        })
        .filter(Boolean);
      return (
        <>
          {groupData._overallSummary ? (
            <div className="rounded-xl border border-forest-pale bg-forest-pale px-5 py-4 text-sm text-forest-dark">
              <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-mid mb-2">
                Overall summary
              </p>
              <p className="leading-relaxed">{groupData._overallSummary}</p>
            </div>
          ) : null}
          <div className="mt-4 grid gap-4">{cards}</div>
        </>
      );
    }

    const single = insightsData[group] as InsightEntry | undefined;
    const title = single?.title || groupTitles[group] || "Insight";
    return <div className="grid gap-4">{renderInsightCard(title, single)}</div>;
  })();

  return (
    <div className="min-h-screen bg-cream-base font-sans text-ink-primary">
      <div className="mx-auto max-w-4xl px-6 py-12">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-8">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-2">
              Insights
            </p>
            <h1 className="font-display text-3xl font-bold text-ink-primary">
              {groupTitles[group] || "Quiz Insights"}
            </h1>
            <p className="mt-2 text-sm text-ink-secondary">
              Personalized takeaways based on your quiz responses.
            </p>
          </div>
          <button
            type="button"
            onClick={() => navigate("/job-seeker/profile?tab=assessments")}
            className="border border-cream-muted bg-white text-ink-secondary text-sm font-semibold px-5 py-2.5 rounded hover:border-forest-pale hover:text-forest-mid transition-colors"
          >
            Back to assessments
          </button>
        </div>

        {loading ? (
          <p className="text-sm text-ink-tertiary">Loading insights…</p>
        ) : error ? (
          <div className="rounded-xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
            {error}
          </div>
        ) : content ? (
          content
        ) : (
          <div className="rounded-xl border border-cream-muted bg-white px-5 py-6 text-sm text-ink-secondary">
            No insights found yet. Complete a quiz and generate insights to view them here.
          </div>
        )}
      </div>
    </div>
  );
}
