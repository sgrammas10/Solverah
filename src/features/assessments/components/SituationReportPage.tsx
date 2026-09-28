/**
 * SituationReportPage -- the Situation Report (BUILD_PLAN A-7), the payoff
 * surface the whole of workstream A exists to reach.
 *
 * NO NUMBERS. NOT ONE. The payload carries `env_score` per dimension and a
 * `rank`, and this page renders neither -- no score, no gap, no bar, no meter,
 * no percentage, no ordinal. Magnitude arrives as one of three words and
 * direction as one of two phrases, and that is the entire resolution the
 * reader gets. This is not restraint about visual clutter: D-15 holds because
 * three coarse buckets are too blunt to hill-climb, and a progress bar drawn
 * from `env_score` would hand back by pixel exactly the gradient the buckets
 * exist to withhold. Ranking is expressed as document order and nothing else.
 *
 * THREE STATES, and the third has two renderings:
 *
 *   needs_core                 -- no completed Work Pulse. Bridge to it. An
 *                                 environment report already on file is
 *                                 acknowledged (it is echoed in the payload)
 *                                 but produces no buckets, because there is
 *                                 nothing to diff it against.
 *   needs_environment_report   -- Work Pulse done, no environment report.
 *                                 Normally the prompt to describe the job;
 *                                 for a `first_job` user
 *                                 (`can_submit_environment_report: false`)
 *                                 there is no form to offer and never will be
 *                                 for that role, so the state renders forward
 *                                 instead of prompting.
 *   complete                   -- the report. `needs_forward` true means the
 *                                 pinned `career_status` is past-tense and the
 *                                 SERVER has already sliced the payload:
 *                                 aligned rows dropped, `change_in_place`
 *                                 reduced to its signal, `negotiate` and
 *                                 `decoder_crossref` suppressed. This page
 *                                 renders what arrives; it does not re-slice,
 *                                 and it must not reintroduce a section by
 *                                 filling a gap with copy of its own. The one
 *                                 line it does add is the sentence about the
 *                                 dropped aligned set, which A-6b left here on
 *                                 purpose: "if the section needs something in
 *                                 place of the dropped rows, it is one line
 *                                 about the set of them, written once at A-7"
 *                                 (`situation_content.aligned_note_for`).
 *
 * LAYOUT (2026-09-28 redesign): summary first (`situation/ReportSummary`),
 * then each strained dimension as a compact card whose guidance sits behind
 * a disclosure (`situation/StrainCard`), in the server's order, then the
 * aligned dimensions grouped in one panel (`situation/AlignedList`). The
 * disclosure only hides; every piece of guidance stays in the DOM and a
 * printed report shows all of it.
 *
 * THE PIN (⚑5) IS SURFACED, not hidden. The report reads the person side
 * through one named core sitting and stays there; a retake does not move it.
 * That guarantee is worth nothing to a user who cannot see it, and the
 * re-pin has to be a thing they do on purpose -- so the footer says so plainly
 * and the button next to it is the only thing that moves the pin.
 * `recalibrated: false` is a success meaning "already current", not an error.
 */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import {
  isAlignedEntry,
  isNoCoreSittingRefusal,
  useRecalibrateSituationReport,
  useSituationReport,
} from "../useSituationReport";
import type {
  AlignedDimensionEntry,
  SituationComplete,
  SituationManagerSection,
  SituationReportEventSinceReport,
  StrainDimensionEntry,
} from "../useSituationReport";
import { usePulseHistory } from "../usePulse";
import type { PulseEventType } from "../usePulse";
import { useExperiments } from "../useExperiments";
import PulseSparkline from "./PulseSparkline";
import { LEAD, PAGE_H1, PRIMARY, SECONDARY } from "../../../shared/ui/publicStyles";
import AlignedList from "./situation/AlignedList";
import { ExperimentsSection, type ExperimentsStatus } from "./situation/Experiments";
import ReportSummary from "./situation/ReportSummary";
import StrainCard from "./situation/StrainCard";
import {
  BODY_MUTED,
  PANEL,
  QUIET_BUTTON,
  REPORT_H2,
  TEXT_LINK,
} from "./situation/format";

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="min-h-screen bg-cream-base font-body text-ink-primary antialiased print:bg-white">
      <div className="mx-auto w-full max-w-3xl space-y-10 px-6 pb-24 pt-10 md:pt-14 print:max-w-none print:px-0 print:pt-0">
        {children}
      </div>
    </main>
  );
}

function BackLink() {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={() => navigate("/intelligence")}
      className="text-[0.9rem] font-medium text-ink-secondary transition-colors hover:text-forest-mid print:hidden"
    >
      <span aria-hidden>←</span> Intelligence Hub
    </button>
  );
}

function TrustLink() {
  return (
    <p className="text-[0.9rem]">
      <Link to="/trust" className={TEXT_LINK}>
        How this works, and what we hold back
      </Link>
    </p>
  );
}

/** Title block shared by the gate states: one heading, short copy, one action. */
function Gate({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Shell>
      <BackLink />
      <article className="max-w-[60ch] space-y-5">
        <h1 className={PAGE_H1}>{title}</h1>
        {children}
      </article>
    </Shell>
  );
}

// ---------------------------------------------------------------------------
// Resubmission prompt (BUILD_PLAN B-4). An offer, never a nag: it says
// nothing when `events_since_report` is empty, and there is no dismiss state
// to track, because resubmitting the environment report is what actually
// clears it -- the new report's `submitted_at` moves past every event that
// prompted this banner. `events[0]` is the newest (the server orders newest
// first), so a mixed batch of event types is worded off the most recent one.
// ---------------------------------------------------------------------------

const RESUBMISSION_LEAD: Record<PulseEventType, string> = {
  new_manager: "You logged a new manager since this report",
  reorg: "Your team went through a reorg since this report",
  remote_change: "Where you work changed since this report",
  role_change: "Your role changed since this report",
  // `other` has no sensible specific wording -- this is the generic line.
  other: "Something about this job has changed since this report",
};

function ResubmissionBanner({ events }: { events: SituationReportEventSinceReport[] }) {
  if (events.length === 0) return null;
  const lead = RESUBMISSION_LEAD[events[0].type] ?? RESUBMISSION_LEAD.other;

  return (
    <section className="flex flex-col gap-3 rounded-[6px] border border-forest-light/50 bg-forest-pale/60 px-5 py-4 sm:flex-row sm:items-center sm:justify-between print:hidden">
      <p className="text-[0.98rem] leading-[1.55] text-forest-dark">
        {lead} — does your Situation Report still describe this job?
      </p>
      <Link to="/environment-report" className={`${SECONDARY} shrink-0 bg-white`}>
        Describe it again
      </Link>
    </section>
  );
}

// ---------------------------------------------------------------------------
// The experienced trend, beside the diagnosis (BUILD_PLAN B-4). Sourced from
// the same `usePulseHistory` hook B-3's trend view uses -- no situation-report
// payload field for this, since the raw check-ins already reached the wire
// there. Degrades exactly as B-3's own experienced line does: nothing at zero
// check-ins but a one-line invitation, a single dot at one, the line from two.
// ---------------------------------------------------------------------------

function ExperiencedTrendSection() {
  const { data, isLoading } = usePulseHistory();

  if (isLoading) return null;

  const checkins = data?.checkins ?? [];

  if (checkins.length === 0) {
    return (
      <section className={`${PANEL} px-5 py-4 print:hidden`}>
        <p className={BODY_MUTED}>
          You haven't checked in on Pulse yet.{" "}
          <Link to="/pulse" className={TEXT_LINK}>
            Check in
          </Link>
        </p>
      </section>
    );
  }

  // Newest first off the wire; the chart wants ascending (oldest first, left to right).
  const points = [...checkins].reverse().map((c) => ({ date: c.taken_at ?? "", value: c.experienced }));

  return (
    <section className="space-y-3 print:break-inside-avoid">
      <h2 className={REPORT_H2}>How work's been working for you</h2>
      <div className={`${PANEL} space-y-3 px-5 py-4`}>
        <PulseSparkline ariaLabel="How work's working for you, over time" points={points} compact />
        {points.length === 1 && (
          <p className="text-[0.85rem] text-ink-secondary">
            One check-in so far — the line fills in as you add more.
          </p>
        )}
        <Link to="/pulse/trend" className={`${TEXT_LINK} text-[0.9rem] print:hidden`}>
          See your full trend
        </Link>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// The shared tail: manager section, guidance notice, honest footer, the pin
// ---------------------------------------------------------------------------

function ManagerSection({ manager }: { manager: SituationManagerSection }) {
  return (
    <section className="space-y-3 print:break-inside-avoid">
      <h2 className={REPORT_H2}>The half one person enacts</h2>
      <div className={`${PANEL} space-y-3 px-5 py-5 sm:px-6`}>
        <p className={BODY_MUTED}>
          {manager.has_profile
            ? "Some of what this report calls the environment is really your manager. You have already profiled them, so that half has its own playbook — read the two together where they touch the same dimension."
            : "Some of what this report calls the environment is really one person, and from the inside the two look identical. The Manager Decoder separates them: profile the manager you actually have, and it returns the protocol for that half."}
        </p>
        <Link
          to={manager.has_profile ? "/manager-profile/playbook" : "/manager-profile"}
          className={`${TEXT_LINK} text-[0.95rem]`}
        >
          {manager.has_profile ? "Open your playbook" : "Profile your manager"}
        </Link>
      </div>
    </section>
  );
}

function GuidanceNotice({ notice }: { notice: string }) {
  return (
    <p className="border-l-2 border-cream-muted pl-4 text-[0.92rem] leading-[1.6] text-ink-secondary">
      {notice}
    </p>
  );
}

/** The pin control (⚑5). Only rendered where a report exists, which means a
 *  core sitting exists, which means the `no_core_sitting` 409 should be
 *  unreachable -- handled anyway, because "should be unreachable" is not a
 *  reason to render a raw failure at a user. */
function PinFooter() {
  const recalibrate = useRecalibrateSituationReport();
  const moved = recalibrate.data?.recalibrated;

  return (
    <div className="space-y-2 print:hidden">
      <button
        type="button"
        onClick={() => recalibrate.mutate()}
        disabled={recalibrate.isPending}
        className={QUIET_BUTTON}
      >
        {recalibrate.isPending
          ? "Re-reading…"
          : "Re-read this against my latest Work Pulse"}
      </button>
      {recalibrate.isSuccess && (
        <p className="text-[0.85rem] text-ink-secondary" role="status">
          {moved
            ? "Re-pinned. This report now reads your most recent Work Pulse sitting."
            : "Already reading your most recent Work Pulse sitting — nothing moved."}
        </p>
      )}
      {recalibrate.isError && (
        <p className="text-[0.85rem] text-red-700" role="alert">
          {isNoCoreSittingRefusal(recalibrate.error)
            ? "There is no Work Pulse sitting to pin to yet."
            : "We couldn't re-read it just now. Please try again in a moment."}
        </p>
      )}
    </div>
  );
}

function HonestFooter() {
  const p = "text-[0.92rem] leading-[1.65] text-ink-secondary";
  return (
    <footer className="space-y-4 border-t border-cream-muted pt-8">
      <h2 className={REPORT_H2}>What this is, and what it isn't</h2>
      <div className="space-y-3 max-w-[64ch]">
        <p className={p}>
          It is the distance between two things you told us: how you work, from Work
          Pulse, and what your job offers, from your own description of it. Nothing in it
          came from your employer, your colleagues or anyone else, and nothing in it is a
          judgement about the place you work.
        </p>
        <p className={p}>
          It is not a score, and there is deliberately not a single number in it. You get
          one of three words for magnitude and a direction, and no finer reading than
          that — a finer one would be a dial, and an instrument you can optimise against
          stops measuring the thing it was built to measure.
        </p>
        <p className={p}>
          It is not advice to leave, and not advice to stay. Every suggestion in it was
          written before we knew anything about you and chosen by a lookup, and the
          judgement about what to do with it is yours — you can see things about your
          situation that this report cannot.
        </p>
        <p className={p}>
          It is pinned. The report reads your Work Pulse from one named sitting and stays
          there, so retaking Work Pulse does not quietly move this page underneath you.
          It moves when you ask it to and not before.
        </p>
      </div>
      <PinFooter />
      <TrustLink />
    </footer>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function SituationReportPage() {
  const navigate = useNavigate();
  const query = useSituationReport();

  if (query.isLoading) {
    return (
      <div className="min-h-screen bg-cream-base font-body flex flex-col items-center justify-center gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin motion-reduce:animate-none" />
        <p className="text-[0.95rem] text-ink-secondary">Loading your Situation Report…</p>
      </div>
    );
  }

  if (query.isError) {
    return (
      <div className="min-h-screen bg-cream-base font-body flex items-center justify-center px-6">
        <div className="max-w-sm w-full rounded-[6px] border border-red-200 bg-red-50 px-5 py-4 text-[0.95rem] text-red-800">
          <p className="font-semibold mb-1">We couldn't load your Situation Report right now.</p>
          <p className="text-[0.88rem]">Please try again in a moment.</p>
          <button
            type="button"
            onClick={() => query.refetch()}
            className="mt-3 text-[0.88rem] font-semibold text-red-800 underline underline-offset-4"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  const report = query.data;
  if (!report) return null;

  // ── needs_core ────────────────────────────────────────────────────────────
  if (report.state === "needs_core") {
    const hasEnvironment = report.environment !== null;
    return (
      <Gate title="This one needs your side first">
        <p className={LEAD}>
          The Situation Report compares how you work with what your job asks of you.
          Work Pulse is your half, and it isn't finished yet.
        </p>
        <p className={LEAD}>
          {hasEnvironment
            ? "Your description of the job is saved — that half is done. Work Pulse takes about eight minutes."
            : "Work Pulse is 24 either-or questions and takes about eight minutes."}
        </p>
        <div className="pt-2">
          <button type="button" onClick={() => navigate("/work-pulse")} className={PRIMARY}>
            Start Work Pulse
          </button>
        </div>
      </Gate>
    );
  }

  // ── needs_environment_report ──────────────────────────────────────────────
  if (report.state === "needs_environment_report") {
    if (!report.can_submit_environment_report) {
      // `first_job`: there is no role to describe and no form to offer, so
      // this state is terminal until they start one. It renders forward
      // rather than prompting, and it does NOT invent per-dimension guidance
      // -- with no environment scores there are no gaps, and a report
      // assembled out of a job the reader has never held would be fiction in
      // the report's own voice.
      return (
        <Gate title="Your report starts when the job does">
          <p className={LEAD}>
            Work Pulse is done, and it holds. The other half is a job to measure it
            against, and you haven't started one yet — so there is nothing to report,
            and we won't invent one. Once you're in a role, fifteen questions about it
            bring the report back the same day.
          </p>
          <p className={LEAD}>
            Until then, FocusType and ManagerMatch need no employer, and they're most
            useful while you're choosing between offers.
          </p>
          <div className="flex flex-wrap gap-3 pt-2">
            <button type="button" onClick={() => navigate("/focus-type")} className={PRIMARY}>
              Start FocusType
            </button>
            <button type="button" onClick={() => navigate("/manager-match")} className={SECONDARY}>
              Start ManagerMatch
            </button>
          </div>
          <div className="pt-4">
            <TrustLink />
          </div>
        </Gate>
      );
    }

    return (
      <Gate title="One half to go">
        <p className={LEAD}>
          Work Pulse told us how you work. Now fifteen questions about your job, in your
          own words. About five minutes, and the report comes back straight away.
        </p>
        <div className="pt-2">
          <button type="button" onClick={() => navigate("/environment-report")} className={PRIMARY}>
            Describe your job
          </button>
        </div>
        <div className="pt-8">
          <ManagerSection manager={report.manager} />
        </div>
      </Gate>
    );
  }

  // ── complete ──────────────────────────────────────────────────────────────
  return <CompleteReport report={report} />;
}

/**
 * The `complete` state, as its own component so `useExperiments` -- a hook --
 * is called unconditionally on every one of ITS renders, the same reasoning
 * `ExperiencedTrendSection` is a separate component rather than an inline
 * call inside `SituationReportPage`'s early-return-laden body.
 */
function CompleteReport({ report }: { report: SituationComplete }) {
  const past = report.needs_forward;
  const experimentsQuery = useExperiments();
  const experiments = experimentsQuery.data?.experiments ?? [];
  // Whichever cell owns the running one already short-circuits past this --
  // `ExperimentControl` only consults this prop from the "offer the button"
  // branch, which a cell with its own running experiment never reaches.
  const hasActiveExperiment = experiments.some((experiment) => experiment.phase === "running");
  // `isFetching` on an error means a retry is already in flight -- treated as
  // loading so "Try again" doesn't look dead while it resolves.
  const experimentsStatus: ExperimentsStatus =
    experimentsQuery.isLoading || (experimentsQuery.isError && experimentsQuery.isFetching)
      ? "loading"
      : experimentsQuery.isError
        ? "error"
        : "ready";

  // Presentation only: which cards are open. Grouping keeps the server's
  // order within each group -- document order IS the ranking, never re-sorted.
  const strained = report.dimensions.filter(
    (entry): entry is StrainDimensionEntry => !isAlignedEntry(entry),
  );
  const aligned = report.dimensions.filter(
    (entry): entry is AlignedDimensionEntry => isAlignedEntry(entry),
  );
  const [open, setOpen] = useState<ReadonlySet<string>>(() => new Set());
  const allOpen = strained.length > 0 && strained.every((entry) => open.has(entry.dimension));
  const toggle = (dimension: string) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(dimension)) next.delete(dimension);
      else next.add(dimension);
      return next;
    });
  const toggleAll = () =>
    setOpen(allOpen ? new Set() : new Set(strained.map((entry) => entry.dimension)));

  return (
    <Shell>
      <div className="flex items-center justify-between gap-4 print:hidden">
        <BackLink />
        <button type="button" onClick={() => window.print()} className={QUIET_BUTTON}>
          Print this report
        </button>
      </div>

      <article className="space-y-12">
        <header className="max-w-[62ch] space-y-4">
          <h1 className={PAGE_H1}>{past ? "What to look for next" : "You, and this job"}</h1>
          <p className={LEAD}>
            {past
              ? "Ranked by how far apart you and that role sat. What comes first is what to look hardest at in the next one."
              : "Ranked by how far apart you and the role sit. What is under most strain comes first."}
          </p>
          {past && (
            <p className={LEAD}>
              If you and that role fitted on some dimension, it is not listed below — the
              fit was real, but this report can see that the job ended and not why, and a
              past match turned forward would be a guess wearing the report's voice.
            </p>
          )}
        </header>

        {report.dimensions.length > 0 && (
          <ReportSummary dimensions={report.dimensions} past={past} />
        )}

        <ResubmissionBanner events={report.events_since_report} />

        {report.dimensions.length === 0 ? (
          <section className="rounded-[6px] border border-forest-light/50 bg-forest-pale/60 px-6 py-5">
            <p className="text-[1rem] leading-[1.6] text-forest-dark">
              {past
                ? "Nothing came back to carry forward: on every dimension we measure, you and that role were set much the same way. That is worth knowing about the kind of role to look for, even though the report will not turn it into an instruction."
                : "Nothing is straining. On every dimension we measure, you and this job are set much the same way — which is uncommon enough to be worth noticing rather than assuming."}
            </p>
          </section>
        ) : (
          <>
            {/* Document order IS the ranking. There is no rank number on
                screen, and there must not be one. */}
            {strained.length > 0 && (
              <section aria-labelledby="situation-strained" className="space-y-4">
                <div className="flex flex-wrap items-end justify-between gap-3">
                  <h2 id="situation-strained" className={REPORT_H2}>
                    {past ? "Where that role strained" : "Where it strains"}
                  </h2>
                  {strained.length > 1 && (
                    <button
                      type="button"
                      onClick={toggleAll}
                      className="text-[0.9rem] font-semibold text-forest-dark underline decoration-forest-light/50 underline-offset-4 hover:decoration-forest-dark print:hidden"
                    >
                      {allOpen ? "Hide all guidance" : "Show all guidance"}
                    </button>
                  )}
                </div>
                <div className="space-y-4">
                  {strained.map((entry) => (
                    <StrainCard
                      key={entry.dimension}
                      entry={entry}
                      past={past}
                      manager={report.manager}
                      experiments={experiments}
                      hasActiveElsewhere={hasActiveExperiment}
                      experimentsStatus={experimentsStatus}
                      open={open.has(entry.dimension)}
                      onToggle={() => toggle(entry.dimension)}
                    />
                  ))}
                </div>
              </section>
            )}
            {aligned.length > 0 && (
              <section aria-labelledby="situation-aligned" className="space-y-4">
                <h2 id="situation-aligned" className={REPORT_H2}>
                  What's working
                </h2>
                <AlignedList entries={aligned} />
              </section>
            )}
          </>
        )}

        <ExperiencedTrendSection />

        <ManagerSection manager={report.manager} />

        <GuidanceNotice notice={report.guidance_notice} />

        {!past && (
          <ExperimentsSection
            experiments={experiments}
            status={experimentsStatus}
            onRetry={() => experimentsQuery.refetch()}
          />
        )}
      </article>

      <HonestFooter />
    </Shell>
  );
}
