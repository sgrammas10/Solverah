import { Link } from "react-router-dom";

interface WorkPulseUnlockProps {
  archetype?: string;
  narrativePreview?: string;
  onViewFull?: () => void;
}

export default function WorkPulseUnlock({
  archetype,
  narrativePreview,
  onViewFull,
}: WorkPulseUnlockProps) {
  const hasData = Boolean(archetype && narrativePreview);

  if (!hasData) {
    return (
      <div className="rounded-xl border border-forest-light bg-forest-pale px-5 py-4">
        <p className="text-xs font-semibold uppercase tracking-widest text-forest-light mb-1">
          ✦ Work Pulse Complete
        </p>
        <p className="text-sm font-semibold text-ink-primary">
          Work Pulse complete — view your results
        </p>
        <Link
          to="/work-pulse/results"
          className="mt-2 inline-block text-sm font-semibold text-forest-dark hover:underline"
        >
          View full analysis →
        </Link>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-forest-light bg-forest-pale px-6 py-5 space-y-3">
      <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
        ✦ Unlocked · Work Pulse
      </p>
      <p className="font-display text-xl font-semibold text-forest-dark">{archetype}</p>
      <p className="text-sm text-ink-primary leading-relaxed line-clamp-3">{narrativePreview}</p>
      <Link
        to="/work-pulse/results"
        onClick={onViewFull}
        className="inline-block text-sm font-semibold text-forest-dark hover:underline"
      >
        Read full analysis →
      </Link>
    </div>
  );
}
