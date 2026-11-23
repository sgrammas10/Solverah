/**
 * WorkPulseUnlock -- the dashboard's Work Pulse completion card.
 *
 * The current (24-item) instrument has no results screen by design: returning scores
 * hands a retaker a gradient to optimise against (D-15). Completion is the whole story,
 * so the card never links to a result. What it does link to (G46) is the way back in:
 * a retake of Work Pulse (straight into the form, `{ retake: true }` -- see
 * WorkPulseLocationState) and the tolerance step at /trait-preferences. Before this,
 * nothing in the product reached /work-pulse once it was complete.
 *
 * Until 2026-10-02 this card also had a data branch that previewed the retired
 * 12-question quiz's archetype and narrative. Nothing passed it the props that branch
 * needed, and the instrument is retired, so the branch is gone. A legacy completer still
 * reaches their stored narrative from /work-pulse ("View your previous analysis").
 */
import { Link } from "react-router-dom";

import type { WorkPulseLocationState } from "./WorkPulsePage";

const RETAKE_STATE: WorkPulseLocationState = { retake: true };

export default function WorkPulseUnlock() {
  return (
    <div className="rounded-xl border border-forest-light bg-forest-pale px-5 py-4">
      <p className="text-xs font-semibold uppercase tracking-widest text-forest-light mb-1">
        ✦ Work Pulse Complete
      </p>
      <p className="text-sm font-semibold text-ink-primary">
        Work Pulse complete — your answers now power your matching
      </p>
      <p className="text-sm text-ink-secondary mt-0.5">
        Nothing to check back on here: it works in the background as we line up the
        environments where you'd do your best work.
      </p>
      {/* Quiet text links: a retake is for when something has changed, not a score
          to chase. Same two doors as the hub's Work Pulse card. */}
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
        <Link
          to="/work-pulse"
          state={RETAKE_STATE}
          className="text-xs font-semibold text-forest-dark hover:underline"
        >
          Retake Work Pulse →
        </Link>
        <Link
          to="/trait-preferences"
          className="text-xs text-ink-secondary hover:underline"
        >
          Change how much give you have on each area →
        </Link>
      </div>
    </div>
  );
}
