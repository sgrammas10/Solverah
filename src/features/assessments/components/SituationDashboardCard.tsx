/**
 * SituationDashboardCard -- the Situation Report, compacted to a dashboard card
 * (BUILD_PLAN D-6).
 *
 * THIS CARD IS THE DASHBOARD'S LEAD, and that is the whole point of D-6. The
 * dashboard used to open with "Here's your job search overview" over Job
 * Matches / Applications tiles -- a job board's information architecture,
 * without jobs, and PRODUCT_DECISIONS §1 names it "the largest remaining
 * contradiction". The spine is conditions: diagnose them, improve them, and
 * match as one output. So the first thing on the screen is where the reader's
 * conditions stand.
 *
 * NO NUMBERS IN THE `complete` RENDERING, same rule as SituationReportPage and
 * for the same reason (D-15). Magnitude arrives as one of three words, in
 * chips shaped exactly like A-7b's FocusStrip, and the ranking is expressed as
 * document order and nothing else. There is no count of dimensions, no "+2
 * more", and no bar: a digit here would hand back by pixel the gradient three
 * coarse buckets exist to withhold, and a dashboard is precisely where someone
 * would go looking for a number to watch week to week.
 *
 * The label maps below are copied from `SituationReportPage`, not imported:
 * that module is a route-level default export owned by another workstream, and
 * reaching into it for two constants would couple the dashboard to a page it
 * never renders. The maps ARE the vocabulary -- if they diverge, the report and
 * the dashboard would be naming the same bucket two ways, which the tests on
 * both sides would catch.
 *
 * ONE NEXT ACTION, NEVER A LIST. `nextAction` is a pure function of the state,
 * and it deliberately never repeats the link the card itself already offers:
 * in `complete` the card links to the report, so the action is the Manager
 * Decoder move; in `needs_core` the action is Work Pulse, which
 * `WorkPulseBanner` is usually already offering three inches higher, so the
 * dashboard passes `workPulseOfferedElsewhere` and this card stays quiet
 * rather than printing the same button twice.
 *
 * SILENT ON LOADING AND ON ERROR. The dashboard's own `/me/dashboard` query
 * documents the same posture ("a failed fetch leaves `data` undefined and this
 * page renders without the stats row"): a card that cannot say anything true
 * says nothing, rather than putting an error box at the top of the first screen
 * after sign-up.
 */
import { Link } from "react-router-dom";

import { useSituationReport } from "../useSituationReport";
import type { SituationDimensionEntry, SituationReport } from "../useSituationReport";

const DIMENSION_LABELS: Record<string, string> = {
  autonomy: "Autonomy",
  pace: "Pace",
  collaboration: "Collaboration",
  feedback: "Feedback",
  innovation: "Innovation",
  decision: "Decision-making",
};

/** Magnitude, as words. Never a number, never a bar. */
const BUCKET_LABELS: Record<string, string> = {
  straining: "Straining",
  notable: "Notable",
  aligned: "Aligned",
};

const CHIP_BUCKET_CLASSES: Record<string, string> = {
  straining: "border-amber-300 bg-amber-50 text-amber-800",
  notable: "border-cream-muted bg-white text-ink-secondary",
  aligned: "border-forest-light bg-forest-pale text-forest-dark",
};

function dimensionLabel(dimension: string): string {
  return DIMENSION_LABELS[dimension] ?? dimension;
}

/** The one suggested action, as data so it can be asserted on directly. */
export interface NextAction {
  to: string;
  label: string;
  hint: string;
}

/**
 * The single next action for a report state, or `null` when something else on
 * the dashboard is already offering it.
 *
 * Exported for the test, and because the derivation is the part of this file
 * worth reading: every state resolves to exactly one action or to none, and
 * there is nowhere for a second one to be appended.
 */
export function nextActionFor(
  report: SituationReport,
  workPulseOfferedElsewhere: boolean,
): NextAction | null {
  if (report.state === "needs_core") {
    if (workPulseOfferedElsewhere) return null;
    return {
      to: "/work-pulse",
      label: "Start Work Pulse",
      hint: "Twenty-four either-or questions, about eight minutes.",
    };
  }

  if (report.state === "needs_environment_report") {
    if (report.can_submit_environment_report) {
      return {
        to: "/environment-report",
        label: "Describe your job",
        hint: "Fifteen questions about the role you're in, about five minutes.",
      };
    }
    // `first_job`: there is no job to describe, so the useful move is the half
    // that needs no employer -- the same two the report itself offers this
    // reader, narrowed to one.
    return {
      to: "/focus-type",
      label: "Start FocusType",
      hint: "How you concentrate — worth knowing while you're choosing, not after.",
    };
  }

  return report.manager.has_profile
    ? {
        to: "/manager-profile/playbook",
        label: "Open your manager playbook",
        hint: "What to try with the person nearest your conditions.",
      }
    : {
        to: "/manager-profile",
        label: "Profile your manager",
        // Sixteen, as words: `ManagerProfilePage` says "16 questions", and this
        // hint can render in the `complete` state, where no digit may appear.
        hint: "Sixteen questions about how your manager actually operates.",
      };
}

function Chips({ dimensions }: { dimensions: SituationDimensionEntry[] }) {
  return (
    <ol className="flex flex-wrap gap-2">
      {dimensions.map((entry) => (
        <li
          key={entry.dimension}
          className={[
            "rounded-full border px-3 py-1 text-sm font-semibold",
            CHIP_BUCKET_CLASSES[entry.bucket],
          ].join(" ")}
        >
          {dimensionLabel(entry.dimension)} — {BUCKET_LABELS[entry.bucket]}
        </li>
      ))}
    </ol>
  );
}

interface SituationDashboardCardProps {
  /**
   * True when `WorkPulseBanner` is on screen. It already offers "Start now" for
   * the same instrument, so the card's own Work Pulse action is suppressed
   * rather than shown twice on one page.
   */
  workPulseOfferedElsewhere?: boolean;
}

export default function SituationDashboardCard({
  workPulseOfferedElsewhere = false,
}: SituationDashboardCardProps) {
  const { data: report, isLoading, isError } = useSituationReport();

  if (isLoading || isError || !report) return null;

  const action = nextActionFor(report, workPulseOfferedElsewhere);

  let heading: string;
  let body: React.ReactNode;
  let reportLink = false;

  if (report.state === "needs_core") {
    heading = "Your conditions, once we have your side";
    body = (
      <p className="text-sm text-ink-secondary leading-relaxed">
        Your Situation Report is the distance between how you work and what your job
        actually asks of you. Work Pulse is the first of those two, and it isn't
        finished yet.
      </p>
    );
  } else if (report.state === "needs_environment_report") {
    if (report.can_submit_environment_report) {
      heading = "One half to go";
      body = (
        <p className="text-sm text-ink-secondary leading-relaxed">
          Work Pulse told us how you work. What's missing is the job to measure it
          against — in your words, not the job description's.
        </p>
      );
    } else {
      heading = "Your report starts when the job does";
      reportLink = true;
      body = (
        <p className="text-sm text-ink-secondary leading-relaxed">
          Work Pulse is done and it holds. The other half is a role to measure it
          against, and you haven't started one yet — so there's nothing to report, and
          we'd rather say so.
        </p>
      );
    }
  } else {
    const past = report.needs_forward;
    heading = past ? "What to look for next" : "How your conditions sit";
    reportLink = true;
    body =
      report.dimensions.length > 0 ? (
        <div className="space-y-3">
          <p className="text-sm text-ink-secondary leading-relaxed">
            {past
              ? "Where you and that role pulled apart, furthest first."
              : "Where you and this job pull apart, furthest first."}
          </p>
          <Chips dimensions={report.dimensions} />
        </div>
      ) : (
        <p className="text-sm text-ink-secondary leading-relaxed">
          {past
            ? "Nothing came back to carry forward — you and that role were set much the same way."
            : "Nothing is straining. On every dimension we measure, you and this job are set much the same way."}
        </p>
      );
  }

  return (
    <div className="rounded-xl border border-cream-muted bg-white p-6" data-testid="situation-card">
      <p className="text-xs font-semibold uppercase tracking-widest text-forest-light mb-2">
        Situation Report
      </p>
      <h2 className="font-display text-lg font-semibold text-ink-primary mb-2">{heading}</h2>

      {body}

      {reportLink && (
        <p className="mt-4">
          <Link to="/situation-report" className="text-sm font-semibold text-forest-dark hover:underline">
            See your Situation Report →
          </Link>
        </p>
      )}

      {action && (
        <div className="mt-5 border-t border-cream-muted pt-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-forest-light mb-1">
            Next
          </p>
          <Link
            to={action.to}
            className="text-sm font-semibold text-forest-dark hover:underline"
          >
            {action.label} →
          </Link>
          <p className="text-xs text-ink-tertiary mt-1">{action.hint}</p>
        </div>
      )}
    </div>
  );
}
