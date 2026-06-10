import { useNavigate } from "react-router-dom";

export default function ManagerMatchResultsPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
      <div className="max-w-sm w-full text-center space-y-4">
        <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
          ManagerMatch™
        </p>
        <h1 className="font-display text-2xl font-semibold text-ink-primary">
          Results coming soon
        </h1>
        <p className="text-sm text-ink-secondary">
          Your ManagerMatch results have been saved. Full results view is in progress.
        </p>
        <button
          type="button"
          onClick={() => navigate('/intelligence')}
          className="w-full bg-forest-dark text-white font-semibold py-3.5 rounded hover:bg-forest-mid transition-colors"
        >
          Go to Intelligence Hub
        </button>
      </div>
    </div>
  );
}
