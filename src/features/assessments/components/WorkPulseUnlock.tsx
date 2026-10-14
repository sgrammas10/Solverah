/**
 * WorkPulseUnlock -- the dashboard's Work Pulse completion card.
 *
 * The current (24-item) instrument has no results screen by design: returning scores
 * hands a retaker a gradient to optimise against (D-15). Completion is the whole story.
 *
 * Until 2026-10-02 this card also had a data branch that previewed the retired
 * 12-question quiz's archetype and narrative. Nothing passed it the props that branch
 * needed, and the instrument is retired, so the branch is gone. A legacy completer still
 * reaches their stored narrative from /work-pulse ("View your previous analysis").
 */
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
    </div>
  );
}
