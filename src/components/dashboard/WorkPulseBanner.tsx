import { useNavigate } from "react-router-dom";
import { X } from "lucide-react";

interface WorkPulseBannerProps {
  onDismiss: () => void;
  /**
   * True when the user completed the ORIGINAL 12-question Work Pulse but not the current
   * 24-item instrument. The instrument was replaced 2026-08-19; old sittings don't feed the
   * matching model, so previous completers are re-prompted with copy that acknowledges the
   * work they already did instead of pretending it never happened.
   */
  retake?: boolean;
}

export default function WorkPulseBanner({ onDismiss, retake = false }: WorkPulseBannerProps) {
  const navigate = useNavigate();

  return (
    <div className="relative bg-forest-pale border border-forest-light rounded-xl px-5 py-4 flex items-start gap-4">
      <div className="flex-1 min-w-0">
        <p className="font-semibold text-forest-dark text-sm">
          {retake ? "Work Pulse has been rebuilt" : "Complete your Work Pulse"}
        </p>
        <p className="text-ink-secondary text-sm mt-0.5">
          {retake
            ? "The new version replaces the one you took — 24 quick either-or questions, about 8 minutes, and it powers your matching directly."
            : "24 quick either-or questions about how you actually work — takes about 8 minutes."}
        </p>
        <button
          onClick={() => navigate("/work-pulse")}
          className="mt-3 inline-flex items-center bg-forest-dark text-white text-sm font-semibold px-4 py-2 rounded hover:bg-forest-mid transition-colors"
        >
          {retake ? "Retake it now" : "Start now"}
        </button>
      </div>
      <button
        onClick={onDismiss}
        aria-label="Dismiss"
        className="shrink-0 p-1 text-forest-light hover:text-forest-dark transition-colors"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
