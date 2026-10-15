/**
 * TraitPreferencesPage -- /trait-preferences, the retake door for the tolerance and
 * must-have step that follows Work Pulse. Retakeable any time, no cadence (ruling
 * 2026-10-13). Each save is a new sitting; the earlier ones are kept server-side.
 */
import { useNavigate } from "react-router-dom";

import TraitPreferencesStep from "./TraitPreferencesStep";
import { RETAKE_SITTING_NOTE } from "./traitPreferencesCopy";

export default function TraitPreferencesPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-cream-base">
      <div className="mx-auto max-w-2xl px-4 sm:px-6 pt-12 pb-16">
        <div className="rounded-xl border border-cream-muted bg-cream-base px-5 py-8 sm:px-8 shadow-sm">
          <p className="mb-4 text-xs font-semibold uppercase tracking-widest text-forest-mid">
            Work Pulse
          </p>
          <p className="mb-4 text-sm text-forest-mid">{RETAKE_SITTING_NOTE}</p>
          <TraitPreferencesStep
            skipLabel="Cancel"
            onFinished={() => navigate("/work-pulse")}
          />
        </div>
      </div>
    </div>
  );
}
