/**
 * CareerStatusReturnDialog — "Status saved. Go back to <label>?"
 *
 * Shown on the profile page after a career status is saved, when the user was
 * sent there from another page that carried a `returnTo` (see
 * shared/lib/careerStatusReturn). Best-guess copy; Julie revises.
 */
import { useEffect, useRef } from "react";

interface CareerStatusReturnDialogProps {
  label: string;
  onGoBack: () => void;
  onStay: () => void;
}

export default function CareerStatusReturnDialog({
  label,
  onGoBack,
  onStay,
}: CareerStatusReturnDialogProps) {
  const goBackRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    goBackRef.current?.focus();
  }, []);

  // Escape means "stay": the dialog is an offer, never a gate.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onStay();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onStay]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      <div className="absolute inset-0 bg-ink-primary/50" onClick={onStay} />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="career-status-return-title"
        className="relative z-10 w-full max-w-sm bg-white rounded-2xl shadow-2xl px-6 py-5 space-y-4"
      >
        <div>
          <p id="career-status-return-title" className="font-semibold text-ink-primary font-display">
            Status saved.
          </p>
          <p className="text-sm text-ink-secondary mt-1">Go back to {label}?</p>
        </div>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onStay}
            className="px-4 py-2 rounded text-sm font-medium text-ink-secondary hover:text-ink-primary transition-colors"
          >
            Stay here
          </button>
          <button
            ref={goBackRef}
            type="button"
            onClick={onGoBack}
            className="bg-forest-dark text-white font-semibold px-4 py-2 rounded text-sm hover:bg-forest-mid transition-colors"
          >
            Go back
          </button>
        </div>
      </div>
    </div>
  );
}
