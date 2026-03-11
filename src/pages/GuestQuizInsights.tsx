import { useLocation, useNavigate } from "react-router-dom";

type InsightEntry = {
  title?: string;
  summary?: string;
  keyTakeaways?: string[];
  combinedMeaning?: string;
  nextSteps?: string[];
};

type InsightPayload = {
  overallSummary?: string | null;
  insights?: InsightEntry[];
};

export default function GuestQuizInsights() {
  const location = useLocation();
  const navigate = useNavigate();
  const state = location.state as { insight?: InsightPayload } | null;
  const insight = state?.insight;

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

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-4xl px-6 py-12">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.16em] text-emerald-300">Insights</p>
            <h1 className="text-2xl font-semibold text-white">Quiz Insights</h1>
            <p className="mt-2 text-sm text-slate-200/80">
              Actionable takeaways based on your quiz responses.
            </p>
          </div>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => navigate("/quiz-preview")}
              className="rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-slate-100 hover:border-emerald-300/60"
            >
              Back to quizzes
            </button>
            <button
              type="button"
              onClick={() => navigate("/login")}
              className="rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-slate-100 hover:border-emerald-300/60"
            >
              Sign in to save results
            </button>
            <button
              type="button"
              onClick={() => navigate("/register")}
              className="rounded-full border border-emerald-300/50 bg-emerald-300/10 px-4 py-2 text-sm font-semibold text-emerald-100 hover:border-emerald-200 hover:text-white"
            >
              Create account
            </button>
          </div>
        </div>

        {!insight?.insights?.length ? (
          <div className="mt-10 rounded-xl border border-white/10 bg-white/5 p-5 text-sm text-slate-200/80">
            No insights found. Please take a quiz to generate insights.
          </div>
        ) : (
          <div className="mt-8">
            {insight.overallSummary ? (
              <div className="rounded-2xl border border-emerald-300/20 bg-emerald-400/10 p-5 text-sm text-emerald-50">
                <p className="text-xs uppercase tracking-[0.16em] text-emerald-200">Overall summary</p>
                <p className="mt-2">{insight.overallSummary}</p>
              </div>
            ) : null}
            <div className="mt-6 grid gap-4">
              {insight.insights.map((entry, idx) =>
                renderInsightCard(entry.title || `Insight ${idx + 1}`, entry),
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
