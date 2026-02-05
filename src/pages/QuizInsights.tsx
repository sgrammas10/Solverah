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
  const locationState = location.state as { insight?: { overallSummary?: string | null; insights?: InsightEntry[] } } | null;

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
      <div className="rounded-2xl border border-white/10 bg-slate-900/70 p-6 shadow-2xl shadow-black/30">
        <h3 className="text-lg font-semibold text-white">{title}</h3>
        {entry.summary ? (
          <p className="mt-2 text-sm text-slate-200/85">{entry.summary}</p>
        ) : null}
        {entry.keyTakeaways?.length ? (
          <div className="mt-4">
            <p className="text-xs uppercase tracking-[0.16em] text-emerald-200">Key takeaways</p>
            <ul className="mt-2 space-y-1 text-sm text-slate-200/85">
              {entry.keyTakeaways.map((item, idx) => (
                <li key={idx}>• {item}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {entry.combinedMeaning ? (
          <div className="mt-4">
            <p className="text-xs uppercase tracking-[0.16em] text-emerald-200">Combined meaning</p>
            <p className="mt-2 text-sm text-slate-200/85">{entry.combinedMeaning}</p>
          </div>
        ) : null}
        {entry.nextSteps?.length ? (
          <div className="mt-4">
            <p className="text-xs uppercase tracking-[0.16em] text-emerald-200">Next steps</p>
            <ul className="mt-2 space-y-1 text-sm text-slate-200/85">
              {entry.nextSteps.map((item, idx) => (
                <li key={idx}>• {item}</li>
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
            <div className="rounded-2xl border border-emerald-300/20 bg-emerald-400/10 p-5 text-sm text-emerald-50">
              <p className="text-xs uppercase tracking-[0.16em] text-emerald-200">Overall summary</p>
              <p className="mt-2">{locationState.insight.overallSummary}</p>
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
            <div className="rounded-2xl border border-emerald-300/20 bg-emerald-400/10 p-5 text-sm text-emerald-50">
              <p className="text-xs uppercase tracking-[0.16em] text-emerald-200">Overall summary</p>
              <p className="mt-2">{groupData._overallSummary}</p>
            </div>
          ) : null}
          <div className="mt-6 grid gap-4">{cards}</div>
        </>
      );
    }

    const single = insightsData[group] as InsightEntry | undefined;
    const title = single?.title || groupTitles[group] || "Insight";
    return <div className="grid gap-4">{renderInsightCard(title, single)}</div>;
  })();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-4xl px-6 py-12">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.16em] text-emerald-300">Insights</p>
            <h1 className="text-2xl font-semibold text-white">{groupTitles[group] || "Quiz Insights"}</h1>
            <p className="mt-2 text-sm text-slate-200/80">
              Personalized takeaways based on your quiz responses.
            </p>
          </div>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => navigate("/job-seeker/profile?tab=assessments")}
              className="rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-slate-100 hover:border-emerald-300/60"
            >
              Back to assessments
            </button>
          </div>
        </div>

        {loading ? (
          <div className="mt-10 text-sm text-slate-200/80">Loading insights…</div>
        ) : error ? (
          <div className="mt-10 rounded-xl border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-100">
            {error}
          </div>
        ) : content ? (
          <div className="mt-8">{content}</div>
        ) : (
          <div className="mt-10 rounded-xl border border-white/10 bg-white/5 p-5 text-sm text-slate-200/80">
            No insights found yet. Complete a quiz and generate insights to view them here.
          </div>
        )}
      </div>
    </div>
  );
}
