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
      <div key={title} className="border border-cream-muted rounded-xl bg-white p-6">
        <h3 className="font-display text-lg font-semibold text-ink-primary mb-3">{title}</h3>
        {entry.summary ? (
          <p className="text-sm text-ink-secondary leading-relaxed mb-4">{entry.summary}</p>
        ) : null}
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
        {entry.combinedMeaning ? (
          <div className="mb-4">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-2">
              Combined meaning
            </p>
            <p className="text-sm text-ink-secondary leading-relaxed">{entry.combinedMeaning}</p>
          </div>
        ) : null}
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

  return (
    <div className="min-h-screen bg-cream-base font-sans text-ink-primary">
      <div className="mx-auto max-w-4xl px-6 py-12">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-8">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-light mb-2">
              Insights
            </p>
            <h1 className="font-display text-3xl font-bold text-ink-primary">Quiz Insights</h1>
            <p className="mt-2 text-sm text-ink-secondary">
              Actionable takeaways based on your quiz responses.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => navigate("/quiz-preview")}
              className="border border-cream-muted bg-white text-ink-secondary text-sm font-semibold px-5 py-2.5 rounded-full hover:border-forest-pale hover:text-forest-mid transition-colors"
            >
              Back to quizzes
            </button>
            <button
              type="button"
              onClick={() => navigate("/login")}
              className="border border-cream-muted bg-white text-ink-secondary text-sm font-semibold px-5 py-2.5 rounded-full hover:border-forest-pale hover:text-forest-mid transition-colors"
            >
              Sign in to save results
            </button>
            <button
              type="button"
              onClick={() => navigate("/register")}
              className="rounded-full bg-forest-light px-5 py-2.5 text-sm font-semibold text-white hover:bg-forest-mid transition-colors"
            >
              Create account
            </button>
          </div>
        </div>

        {!insight?.insights?.length ? (
          <div className="rounded-xl border border-cream-muted bg-white px-5 py-6 text-sm text-ink-secondary">
            No insights found. Please take a quiz to generate insights.
          </div>
        ) : (
          <div>
            {insight.overallSummary ? (
              <div className="rounded-xl border border-forest-pale bg-forest-pale px-5 py-4 text-sm text-forest-dark mb-6">
                <p className="text-xs font-semibold uppercase tracking-[0.08em] text-forest-mid mb-2">
                  Overall summary
                </p>
                <p className="leading-relaxed">{insight.overallSummary}</p>
              </div>
            ) : null}
            <div className="grid gap-4">
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
