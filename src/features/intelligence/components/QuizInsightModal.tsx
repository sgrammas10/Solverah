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
      <div className="absolute inset-0 bg-ink-primary/50" />
      <div className="relative w-full max-w-2xl rounded-2xl border border-cream-subtle bg-cream-base p-6 shadow-2xl shadow-ink-primary/20">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-forest-mid font-semibold">Insight</p>
            <h3 className="text-xl font-semibold text-ink-primary">{title}</h3>
          </div>
          {!loading && (
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-cream-muted px-4 py-1.5 text-xs font-semibold text-ink-secondary hover:border-forest-light hover:text-forest-dark transition-colors"
            >
              Close
            </button>
          )}
        </div>

        {loading ? (
          <div className="mt-6 space-y-4">
            <p className="text-sm text-ink-secondary">
              Generating your insight. This can take a few seconds.
            </p>
            <div className="h-2 w-full rounded-full bg-cream-subtle">
              <div
                className="h-2 rounded-full bg-forest-light transition-all duration-300"
                style={{ width: `${Math.min(100, Math.max(4, progress))}%` }}
              />
            </div>
          </div>
        ) : error ? (
          <div className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        ) : (
          <div className="mt-6 space-y-4 text-sm text-ink-secondary">
            <p className="text-sm text-ink-secondary">
              Your insights are ready. Choose where you want to go next.
            </p>
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={onViewInsights}
                className="rounded-full bg-forest-dark px-4 py-2 text-sm font-semibold text-cream-base shadow-sm hover:bg-forest-mid transition-colors"
              >
                {viewLabel}
              </button>
              <button
                type="button"
                onClick={onBackToAssessments}
                className="rounded-full border border-cream-muted px-4 py-2 text-sm font-semibold text-ink-secondary hover:border-forest-light hover:text-forest-dark transition-colors"
              >
                {backLabel}
              </button>
              <button
                type="button"
                onClick={onClose}
                className="rounded-full border border-cream-muted px-4 py-2 text-sm font-semibold text-ink-secondary hover:border-forest-light hover:text-forest-dark transition-colors"
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
