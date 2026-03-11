type QuizInsightModalProps = {
  open: boolean;
  loading: boolean;
  progress: number;
  title: string;
  error?: string | null;
  onClose: () => void;
  onViewInsights: () => void;
  onBackToAssessments: () => void;
  viewLabel?: string;
  backLabel?: string;
};

export default function QuizInsightModal({
  open,
  loading,
  progress,
  title,
  error,
  onClose,
  onViewInsights,
  onBackToAssessments,
  viewLabel = "View insights",
  backLabel = "Back to assessments",
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
          <div className="mt-6 space-y-4 text-sm text-slate-100">
            <p className="text-sm text-slate-200/80">
              Your insights are ready. Choose where you want to go next.
            </p>
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={onViewInsights}
                className="rounded-full bg-emerald-400/90 px-4 py-2 text-sm font-semibold text-slate-950 shadow-md shadow-emerald-500/30"
              >
                {viewLabel}
              </button>
              <button
                type="button"
                onClick={onBackToAssessments}
                className="rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-slate-100 hover:border-emerald-300/60"
              >
                {backLabel}
              </button>
              <button
                type="button"
                onClick={onClose}
                className="rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-slate-100 hover:border-emerald-300/60"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
