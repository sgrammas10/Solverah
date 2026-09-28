/**
 * Condition experiments (BUILD_PLAN B-5). An offer, never a nag -- the same
 * house rule B-2's anti-nag copy follows: "moved / didn't", never "worked",
 * because a two-week, single-user, unblinded before/after comparison cannot
 * support a causal claim. Verdicts are words; the two counts are the only
 * numbers, and they are plain check-in counts, never a delta or a percentage.
 */
import {
  isExperimentAlreadyActive,
  useAbandonExperiment,
  useStartExperiment,
} from "../../useExperiments";
import type { Experiment } from "../../useExperiments";
import { BODY, QUIET_BUTTON, REPORT_H2, dimensionLabel, formatDate } from "./format";

const READOUT_COPY: Record<string, string> = {
  not_enough_data: "There weren't enough check-ins on one side of this to say anything yet.",
  moved_up: "Your numbers moved up over those two weeks.",
  moved_down: "Your numbers moved down over those two weeks.",
  about_the_same: "Your numbers didn't move much over those two weeks.",
};

function readoutCountsProse(before: number, after: number): string {
  const beforeText = `${before} check-in${before === 1 ? "" : "s"} before`;
  const afterText = `${after} after`;
  return `That's based on ${beforeText}, ${afterText}.`;
}

/** `useExperiments()` boiled down to what a cell needs to decide whether it
 *  may offer its start button -- a failed or in-flight fetch must never look
 *  like "definitely nothing running", which is what an empty `experiments`
 *  array would otherwise say. */
export type ExperimentsStatus = "loading" | "error" | "ready";

interface ExperimentControlProps {
  dimension: string;
  direction: "under" | "over";
  experiments: Experiment[];
  hasActiveElsewhere: boolean;
  status: ExperimentsStatus;
}

/** The one cell-level control for a `change_in_place` register: a button
 *  that starts a two-week experiment, a running state once it exists, and
 *  the readout in words once it has ended. Not shown in the needs-forward
 *  rendering -- the server never sends `experiment_name` there, and there is
 *  no live job to run an experiment against. */
export function ExperimentControl({
  dimension,
  direction,
  experiments,
  hasActiveElsewhere,
  status,
}: ExperimentControlProps) {
  const start = useStartExperiment();
  const abandon = useAbandonExperiment();

  // Newest first off the wire, and an abandoned attempt on this cell is
  // treated as if it never happened -- abandoning is "let me try something
  // else, or the same thing again," not a state this cell keeps showing.
  const current = experiments.find(
    (experiment) =>
      experiment.dimension === dimension &&
      experiment.direction === direction &&
      experiment.phase !== "abandoned",
  );

  if (current?.phase === "running") {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-[4px] bg-forest-pale/50 px-4 py-3">
        <p className="text-[0.95rem] text-forest-dark">
          Running since {formatDate(current.started_at)}, through {formatDate(current.ends_at)}.
        </p>
        <button
          type="button"
          onClick={() => abandon.mutate(current.id)}
          disabled={abandon.isPending}
          className="text-[0.9rem] font-semibold text-ink-secondary underline underline-offset-4 hover:text-ink-primary disabled:opacity-50 print:hidden"
        >
          Abandon
        </button>
      </div>
    );
  }

  if (current?.phase === "ended") {
    return (
      <div className="space-y-1 rounded-[4px] bg-cream-base px-4 py-3">
        <p className={BODY}>{READOUT_COPY[current.readout.verdict]}</p>
        <p className="text-[0.85rem] text-ink-secondary">
          {readoutCountsProse(current.readout.before_count, current.readout.after_count)}
        </p>
      </div>
    );
  }

  // A failed or in-flight `experiments` fetch is not "nothing running" --
  // offering the button on that reading would let a click land on a running
  // experiment the page just doesn't know about yet, and hit the server's 409.
  if (status === "loading") {
    return <p className="text-[0.85rem] text-ink-tertiary print:hidden">Loading…</p>;
  }
  if (status === "error") {
    return null;
  }

  return (
    <div className="space-y-1.5 print:hidden">
      <button
        type="button"
        onClick={() => start.mutate({ dimension: dimension as never, direction })}
        disabled={start.isPending || hasActiveElsewhere}
        className={QUIET_BUTTON}
      >
        Try this for two weeks
      </button>
      {hasActiveElsewhere && (
        <p className="text-[0.85rem] text-ink-secondary">
          Only one experiment can run at a time — finish or abandon the other one first.
        </p>
      )}
      {start.isError && !isExperimentAlreadyActive(start.error) && (
        <p className="text-[0.85rem] text-red-700" role="alert">
          We couldn't start that just now. Please try again in a moment.
        </p>
      )}
    </div>
  );
}

const EXPERIMENT_PHASE_LABELS: Record<string, string> = {
  running: "Running",
  ended: "Ended",
  abandoned: "Abandoned",
};

interface ExperimentsSectionProps {
  experiments: Experiment[];
  status: ExperimentsStatus;
  onRetry: () => void;
}

/** "Your experiments": a record of past attempts, not a second payoff
 *  surface. Nothing renders when nobody has ever started one. */
export function ExperimentsSection({ experiments, status, onRetry }: ExperimentsSectionProps) {
  // Shown even with an empty list -- a failed fetch is not the same fact as
  // "you have never started one," and the two must not render identically.
  if (status === "error") {
    return (
      <section className="space-y-3">
        <h2 className={REPORT_H2}>Your experiments</h2>
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-[6px] border border-cream-muted bg-white px-5 py-4">
          <p className="text-[0.95rem] text-ink-secondary">
            We couldn't load your experiments right now.
          </p>
          <button type="button" onClick={onRetry} className={`${QUIET_BUTTON} print:hidden`}>
            Try again
          </button>
        </div>
      </section>
    );
  }

  if (experiments.length === 0) return null;

  return (
    <section className="space-y-3">
      <h2 className={REPORT_H2}>Your experiments</h2>
      <ul className="divide-y divide-cream-muted rounded-[6px] border border-cream-muted bg-white">
        {experiments.map((experiment) => (
          <li key={experiment.id} className="space-y-1 px-5 py-4">
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <p className="font-semibold text-ink-primary">
                {dimensionLabel(experiment.dimension)} — {experiment.experiment_name}
              </p>
              <span className="text-[0.85rem] font-semibold text-ink-secondary">
                {EXPERIMENT_PHASE_LABELS[experiment.phase]}
              </span>
            </div>
            <p className="text-[0.85rem] text-ink-tertiary">
              {formatDate(experiment.started_at)} – {formatDate(experiment.ends_at)}
            </p>
            {experiment.phase === "ended" && (
              <p className={BODY}>
                {READOUT_COPY[experiment.readout.verdict]}{" "}
                {readoutCountsProse(experiment.readout.before_count, experiment.readout.after_count)}
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
