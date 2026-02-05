type QuizInsight = {
  key?: string;
  title?: string;
  summary?: string;
  keyTakeaways?: string[];
  combinedMeaning?: string;
  nextSteps?: string[];
};

type QuizInsightModalProps = {
  open: boolean;
  loading: boolean;
  progress: number;
  title: string;
  overallSummary?: string | null;
  insights?: QuizInsight[];
  error?: string | null;
  onClose: () => void;
};

export default function QuizInsightModal({
  open,
  loading,
  progress,
  title,
  overallSummary,
  insights,
  error,
  onClose,
}: QuizInsightModalProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      <div className="absolute inset-0 bg-slate-950/80" />
      <div className="relative w-full max-w-2xl rounded-2xl border border-white/10 bg-slate-900/95 p-6 text-slate-100 shadow-2xl shadow-black/40">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-emerald-300">Insight</p>
            <h3 className="text-xl font-semibold text-white">{title}</h3>
          </div>
          {!loading && (
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-white/10 px-3 py-1 text-xs font-semibold text-slate-200 hover:border-emerald-300/60"
            >
              Close
            </button>
          )}
        </div>

        {loading ? (
          <div className="mt-6 space-y-4">
            <p className="text-sm text-slate-200/80">
              Generating your insight. This can take a few seconds.
            </p>
            <div className="h-2 w-full rounded-full bg-white/10">
              <div
                className="h-2 rounded-full bg-emerald-400 transition-all duration-300"
                style={{ width: `${Math.min(100, Math.max(4, progress))}%` }}
              />
            </div>
          </div>
        ) : error ? (
          <div className="mt-6 rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-100">
            {error}
          </div>
        ) : (
          <div className="mt-6 space-y-5 text-sm text-slate-100">
            {overallSummary ? (
              <div className="rounded-lg border border-white/10 bg-white/5 p-4">
                <p className="text-xs uppercase tracking-[0.16em] text-emerald-200">Overall</p>
                <p className="mt-2 text-sm text-slate-100">{overallSummary}</p>
              </div>
            ) : null}

            {(insights || []).map((insight, idx) => (
              <div key={`${insight.key || "insight"}-${idx}`} className="rounded-xl border border-white/10 bg-white/5 p-4">
                <h4 className="text-base font-semibold text-white">
                  {insight.title || `Insight ${idx + 1}`}
                </h4>
                {insight.summary ? (
                  <p className="mt-2 text-sm text-slate-200/90">{insight.summary}</p>
                ) : null}
                {insight.keyTakeaways && insight.keyTakeaways.length > 0 ? (
                  <div className="mt-3">
                    <p className="text-xs uppercase tracking-[0.16em] text-emerald-200">Key takeaways</p>
                    <ul className="mt-2 space-y-1 text-sm text-slate-200/90">
                      {insight.keyTakeaways.map((item, i) => (
                        <li key={i}>• {item}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {insight.combinedMeaning ? (
                  <div className="mt-3">
                    <p className="text-xs uppercase tracking-[0.16em] text-emerald-200">Combined meaning</p>
                    <p className="mt-2 text-sm text-slate-200/90">{insight.combinedMeaning}</p>
                  </div>
                ) : null}
                {insight.nextSteps && insight.nextSteps.length > 0 ? (
                  <div className="mt-3">
                    <p className="text-xs uppercase tracking-[0.16em] text-emerald-200">Next steps</p>
                    <ul className="mt-2 space-y-1 text-sm text-slate-200/90">
                      {insight.nextSteps.map((item, i) => (
                        <li key={i}>• {item}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
