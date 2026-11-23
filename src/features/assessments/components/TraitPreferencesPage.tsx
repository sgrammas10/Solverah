/**
 * TraitPreferencesPage -- /trait-preferences, the retake door for the tolerance and
 * must-have step that follows Work Pulse. Retakeable any time, no cadence (ruling
 * 2026-10-13). Each save is a new sitting; the earlier ones are kept server-side.
 *
 * Save and Cancel both return to /work-pulse, but only Save says so there (G48): it
 * passes `traitPreferencesSaved: true` (WorkPulseLocationState), which the page turns
 * into a "Saved" confirmation. Cancel passes nothing and leaves the stored answers as
 * they were.
 */
import { useNavigate } from "react-router-dom";

import TraitPreferencesStep from "./TraitPreferencesStep";
import { RETAKE_SITTING_NOTE } from "./traitPreferencesCopy";
import type { WorkPulseLocationState } from "./WorkPulsePage";

export default function TraitPreferencesPage() {
  const navigate = useNavigate();

  function handleFinished(outcome: "saved" | "skipped") {
    if (outcome === "saved") {
      const state: WorkPulseLocationState = { traitPreferencesSaved: true };
      navigate("/work-pulse", { state });
    } else {
      navigate("/work-pulse");
    }
  }

  return (
    <div className="min-h-screen bg-cream-base">
      <div className="mx-auto max-w-2xl px-4 sm:px-6 pt-12 pb-16">
        <div className="rounded-xl border border-cream-muted bg-cream-base px-5 py-8 sm:px-8 shadow-sm">
          <p className="mb-4 text-xs font-semibold uppercase tracking-widest text-forest-mid">
            Work Pulse
          </p>
          <p className="mb-4 text-sm text-forest-mid">{RETAKE_SITTING_NOTE}</p>
          <TraitPreferencesStep skipLabel="Cancel" onFinished={handleFinished} />
        </div>
      </div>
    </div>
  );
}
