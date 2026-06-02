import { useNavigate } from "react-router-dom";
import { X } from "lucide-react";

interface WorkPulseBannerProps {
  onDismiss: () => void;
}

export default function WorkPulseBanner({ onDismiss }: WorkPulseBannerProps) {
  const navigate = useNavigate();

  return (
    <div className="relative bg-forest-pale border border-forest-light rounded-xl px-5 py-4 flex items-start gap-4">
      <div className="flex-1 min-w-0">
        <p className="font-semibold text-forest-dark text-sm">Complete your Work Pulse</p>
        <p className="text-ink-secondary text-sm mt-0.5">
          12 questions that reveal how you actually work — takes about 4 minutes.
        </p>
        <button
          onClick={() => navigate("/work-pulse")}
          className="mt-3 inline-flex items-center bg-forest-dark text-white text-sm font-semibold px-4 py-2 rounded hover:bg-forest-mid transition-colors"
        >
          Start now
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
