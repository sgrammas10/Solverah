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
 * THE PIN (⚑5) IS SURFACED, not hidden. The report reads the person side
 * through one named core sitting and stays there; a retake does not move it.
 * That guarantee is worth nothing to a user who cannot see it, and the
 * re-pin has to be a thing they do on purpose -- so the footer says so plainly
 * and the button next to it is the only thing that moves the pin.
 * `recalibrated: false` is a success meaning "already current", not an error.
 */
import { Link, useNavigate } from "react-router-dom";

import {
  isAlignedEntry,
  isNoCoreSittingRefusal,
  useRecalibrateSituationReport,
  useSituationReport,
} from "../useSituationReport";
import type {
  AlignedDimensionEntry,
  SituationManagerSection,
  StrainDimensionEntry,
} from "../useSituationReport";

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

/** Direction, as a phrase. Past tense where the role is behind the reader. */
function directionLabel(direction: "under" | "over", past: boolean): string {
  if (direction === "under") return past ? "Less than you needed" : "Less than you need";
  return past ? "More than you needed" : "More than you need";
}

function dimensionLabel(dimension: string): string {
  return DIMENSION_LABELS[dimension] ?? dimension;
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-cream-base print:bg-white">
      <div className="mx-auto max-w-2xl px-6 pt-12 pb-20 space-y-8">{children}</div>
    </div>
  );
}

function BackLink() {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={() => navigate("/intelligence")}
      className="flex items-center gap-1.5 text-sm font-semibold text-forest-dark hover:underline print:hidden"
    >
      <span aria-hidden>←</span> Intelligence Hub
    </button>
  );
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="text-xs font-semibold uppercase tracking-widest text-forest-light">
      {children}
    </h4>
  );
}

// ---------------------------------------------------------------------------
// Dimension cards
// ---------------------------------------------------------------------------

function AlignedCard({ entry }: { entry: AlignedDimensionEntry }) {
  return (
    <article className="rounded-xl border border-forest-light bg-forest-pale/60 px-6 py-5 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-display text-base font-semibold text-ink-primary">
          {dimensionLabel(entry.dimension)}
        </h3>
        <span className="rounded-full border border-forest-light bg-white px-2.5 py-0.5 text-xs font-semibold text-forest-mid">
          {BUCKET_LABELS.aligned}
        </span>
      </div>
      <p className="text-sm text-ink-primary leading-relaxed">{entry.aligned_note}</p>
    </article>
  );
}

function StrainCard({
  entry,
  past,
  manager,
}: {
  entry: StrainDimensionEntry;
  past: boolean;
  manager: SituationManagerSection;
}) {
  const { registers } = entry;
  const isStraining = entry.bucket === "straining";
  const managerHref = manager.has_profile ? "/manager-profile/playbook" : "/manager-profile";
  const managerCta = manager.has_profile ? "Open your playbook →" : "Profile your manager →";

  return (
    <article
      className={[
        "rounded-xl px-6 py-6 space-y-5 border",
        isStraining ? "border-amber-300 bg-amber-50/70" : "border-cream-muted bg-white",
      ].join(" ")}
    >
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-display text-lg font-semibold text-ink-primary">
            {dimensionLabel(entry.dimension)}
          </h3>
          <span
            className={[
              "rounded-full border bg-white px-2.5 py-0.5 text-xs font-semibold",
              isStraining
                ? "border-amber-300 text-amber-700"
                : "border-cream-muted text-ink-secondary",
            ].join(" ")}
          >
            {BUCKET_LABELS[entry.bucket]}
          </span>
          <span className="text-xs text-ink-tertiary">
            {directionLabel(entry.direction, past)}
          </span>
        </div>
        <p className="font-display text-base font-semibold text-ink-primary">
          {entry.diagnosis.headline}
        </p>
        <p className="text-sm text-ink-primary leading-relaxed">{entry.diagnosis.text}</p>
      </header>

      {registers.change_in_place && (
        <section className="space-y-2 border-t border-black/5 pt-4">
          <SectionHeading>Change it in place</SectionHeading>
          {registers.change_in_place.experiment_name && (
            <p className="text-sm font-semibold text-ink-primary">
              {registers.change_in_place.experiment_name}
            </p>
          )}
          {registers.change_in_place.experiment && (
            <p className="text-sm text-ink-primary leading-relaxed">
              {registers.change_in_place.experiment}
            </p>
          )}
          {registers.change_in_place.steps && registers.change_in_place.steps.length > 0 && (
            <ul className="space-y-1.5 pt-1">
              {registers.change_in_place.steps.map((stepText) => (
                <li
                  key={stepText.slice(0, 48)}
                  className="flex gap-2 text-sm text-ink-primary leading-relaxed"
                >
                  <span className="text-forest-mid shrink-0 font-bold" aria-hidden>
                    ›
                  </span>
                  {stepText}
                </li>
              ))}
            </ul>
          )}
          <div className="pt-1">
            <SectionHeading>
              {past ? "What to watch for next time" : "How you'll know it worked"}
            </SectionHeading>
            <p className="text-sm text-ink-primary leading-relaxed">
              {registers.change_in_place.signal}
            </p>
          </div>
        </section>
      )}

      {registers.negotiate && (
        <section className="space-y-3 border-t border-black/5 pt-4">
          <SectionHeading>Negotiate it</SectionHeading>
          <div className="space-y-1">
            <p className="text-xs font-semibold text-ink-secondary">Who, and where</p>
            <p className="text-sm text-ink-primary leading-relaxed">
              {registers.negotiate.who_and_where}
            </p>
          </div>
          <div className="space-y-1">
            <p className="text-xs font-semibold text-ink-secondary">How to open</p>
            <p className="text-sm text-ink-primary leading-relaxed">
              {registers.negotiate.opening}
            </p>
          </div>
          {registers.negotiate.scripts.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs font-semibold text-ink-secondary">What to say</p>
              <ul className="space-y-1.5">
                {registers.negotiate.scripts.map((script) => (
                  <li
                    key={script.slice(0, 48)}
                    className="text-sm text-ink-primary leading-relaxed italic border-l-2 border-forest-light/40 pl-3"
                  >
                    “{script}”
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="space-y-1">
            <p className="text-xs font-semibold text-ink-secondary">If the answer is no</p>
            <p className="text-sm text-ink-primary leading-relaxed">
              {registers.negotiate.if_no}
            </p>
          </div>
        </section>
      )}

      {registers.rarely_moves && (
        <section className="space-y-3 border-t border-black/5 pt-4">
          <SectionHeading>This one rarely moves</SectionHeading>
          <div className="space-y-1">
            <p className="text-xs font-semibold text-ink-secondary">Why it's usually fixed</p>
            <p className="text-sm text-ink-primary leading-relaxed">
              {registers.rarely_moves.why_fixed}
            </p>
          </div>
          <div className="space-y-1">
            <p className="text-xs font-semibold text-ink-secondary">What staying costs</p>
            <p className="text-sm text-ink-primary leading-relaxed">
              {registers.rarely_moves.cost_of_staying}
            </p>
          </div>
          <div className="space-y-1">
            <p className="text-xs font-semibold text-ink-secondary">What that means</p>
            <p className="text-sm text-ink-primary leading-relaxed">
              {registers.rarely_moves.what_it_implies}
            </p>
          </div>
        </section>
      )}

      {/* The Decoder hand-off. `defers_to_decoder` is the whole-dimension
          deferral (feedback); `decoder_crossref` is the softer "some of this
          may be one person" paragraph (autonomy). A dimension can carry
          either, and neither duplicates protocol that lives in C-2. */}
      {entry.defers_to_decoder && (
        <section className="rounded-lg border border-cream-muted bg-white/80 px-4 py-3 space-y-2">
          <p className="text-sm text-ink-secondary leading-relaxed">
            How feedback actually reaches you is enacted by one person rather than by
            the company, so the protocol for it lives in the Manager Decoder rather
            than here.
          </p>
          <Link
            to={managerHref}
            className="inline-block text-sm font-semibold text-forest-dark hover:underline"
          >
            {managerCta}
          </Link>
        </section>
      )}

      {entry.decoder_crossref && (
        <section className="rounded-lg border border-cream-muted bg-white/80 px-4 py-3 space-y-2">
          <p className="text-sm text-ink-secondary leading-relaxed">
            {entry.decoder_crossref}
          </p>
          <Link
            to={managerHref}
            className="inline-block text-sm font-semibold text-forest-dark hover:underline"
          >
            {managerCta}
          </Link>
        </section>
      )}
    </article>
  );
}

// ---------------------------------------------------------------------------
// The shared tail: manager section, guidance notice, honest footer, the pin
// ---------------------------------------------------------------------------

function ManagerSection({ manager }: { manager: SituationManagerSection }) {
  return (
    <section className="rounded-xl border border-cream-muted bg-white px-6 py-5 space-y-3">
      <h2 className="font-display text-lg font-semibold text-ink-primary">
        The half one person enacts
      </h2>
      <p className="text-sm text-ink-secondary leading-relaxed">
        {manager.has_profile
          ? "Some of what this report calls the environment is really your manager. You have already profiled them, so that half has its own playbook — read the two together where they touch the same dimension."
          : "Some of what this report calls the environment is really one person, and from the inside the two look identical. The Manager Decoder separates them: profile the manager you actually have, and it returns the protocol for that half."}
      </p>
      <Link
        to={manager.has_profile ? "/manager-profile/playbook" : "/manager-profile"}
        className="inline-block text-sm font-semibold text-forest-dark hover:underline"
      >
        {manager.has_profile ? "Open your playbook →" : "Profile your manager →"}
      </Link>
    </section>
  );
}

function GuidanceNotice({ notice }: { notice: string }) {
  return (
    <section className="rounded-lg border border-cream-muted bg-white px-5 py-4">
      <p className="text-sm text-ink-secondary leading-relaxed">{notice}</p>
    </section>
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
        className="text-sm font-semibold text-forest-dark hover:underline disabled:opacity-50 disabled:no-underline"
      >
        {recalibrate.isPending
          ? "Re-reading…"
          : "Re-read this against my latest Work Pulse"}
      </button>
      {recalibrate.isSuccess && (
        <p className="text-xs text-ink-tertiary" role="status">
          {moved
            ? "Re-pinned. This report now reads your most recent Work Pulse sitting."
            : "Already reading your most recent Work Pulse sitting — nothing moved."}
        </p>
      )}
      {recalibrate.isError && (
        <p className="text-xs text-red-700" role="alert">
          {isNoCoreSittingRefusal(recalibrate.error)
            ? "There is no Work Pulse sitting to pin to yet."
            : "We couldn't re-read it just now. Please try again in a moment."}
        </p>
      )}
    </div>
  );
}

function HonestFooter() {
  return (
    <section className="border-t border-cream-muted pt-6 space-y-3">
      <h2 className="font-display text-lg font-semibold text-ink-primary">
        What this is, and what it isn't
      </h2>
      <p className="text-sm text-ink-secondary leading-relaxed">
        It is the distance between two things you told us: how you work, from Work
        Pulse, and what your job offers, from your own description of it. Nothing in it
        came from your employer, your colleagues or anyone else, and nothing in it is a
        judgement about the place you work.
      </p>
      <p className="text-sm text-ink-secondary leading-relaxed">
        It is not a score, and there is deliberately not a single number in it. You get
        one of three words for magnitude and a direction, and no finer reading than
        that — a finer one would be a dial, and an instrument you can optimise against
        stops measuring the thing it was built to measure.
      </p>
      <p className="text-sm text-ink-secondary leading-relaxed">
        It is not advice to leave, and not advice to stay. Every suggestion in it was
        written before we knew anything about you and chosen by a lookup, and the
        judgement about what to do with it is yours — you can see things about your
        situation that this report cannot.
      </p>
      <p className="text-sm text-ink-secondary leading-relaxed">
        It is pinned. The report reads your Work Pulse from one named sitting and stays
        there, so retaking Work Pulse does not quietly move this page underneath you.
        It moves when you ask it to and not before.
      </p>
      <PinFooter />
      <p className="text-xs text-ink-tertiary leading-relaxed pt-2">
        <Link to="/trust" className="font-semibold text-forest-dark hover:underline">
          How this works, and what we hold back →
        </Link>
      </p>
    </section>
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
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
        <p className="text-sm text-ink-secondary">Loading your Situation Report…</p>
      </div>
    );
  }

  if (query.isError) {
    return (
      <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
        <div className="max-w-sm w-full rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
          <p className="font-medium mb-1">We couldn't load your Situation Report right now.</p>
          <p className="text-xs">Please try again in a moment.</p>
          <button
            type="button"
            onClick={() => query.refetch()}
            className="mt-3 text-xs font-semibold text-red-700 underline"
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
      <Shell>
        <BackLink />
        <article className="space-y-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
            Situation Report
          </p>
          <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">
            This one needs your side first
          </h1>
          <p className="text-sm text-ink-secondary leading-relaxed">
            The Situation Report is the distance between two things: how you work, and
            what your job actually asks of you. Work Pulse is the first of those, and
            it isn't finished yet.
          </p>
          <p className="text-sm text-ink-secondary leading-relaxed">
            {hasEnvironment
              ? "Your description of the job is saved and waiting — that half is done. Work Pulse takes about eight minutes and completes the picture."
              : "Work Pulse is 24 either-or questions about the conditions you do your best work in — about eight minutes."}
          </p>
          <button
            type="button"
            onClick={() => navigate("/work-pulse")}
            className="inline-flex items-center bg-forest-dark text-white text-sm font-semibold px-6 py-3 rounded hover:bg-forest-mid transition-colors"
          >
            Start Work Pulse →
          </button>
        </article>
      </Shell>
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
        <Shell>
          <BackLink />
          <article className="space-y-4">
            <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
              Situation Report
            </p>
            <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">
              Your report starts when the job does
            </h1>
            <p className="text-sm text-ink-secondary leading-relaxed">
              This report is the distance between how you work and what a role actually
              asks of you. You have given us the first half — Work Pulse is done, and it
              holds. The second half is a job to measure against, and you haven't started
              one yet.
            </p>
            <p className="text-sm text-ink-secondary leading-relaxed">
              So there is nothing to report, and we would rather say that than assemble
              something out of a role you have never held. The moment you are in one,
              describe it in about ten questions and the report comes back the same day.
            </p>
            <p className="text-sm text-ink-secondary leading-relaxed">
              What is worth doing now is the half that needs no employer. FocusType maps
              how you concentrate, and ManagerMatch tells you which management styles
              bring out your best — which is a useful thing to know while you are
              choosing between offers rather than after.
            </p>
            <div className="flex flex-wrap gap-3 pt-1">
              <button
                type="button"
                onClick={() => navigate("/focus-type")}
                className="inline-flex items-center bg-forest-dark text-white text-sm font-semibold px-6 py-3 rounded hover:bg-forest-mid transition-colors"
              >
                Start FocusType →
              </button>
              <button
                type="button"
                onClick={() => navigate("/manager-match")}
                className="inline-flex items-center border border-forest-dark text-forest-dark text-sm font-semibold px-6 py-3 rounded hover:bg-forest-pale transition-colors"
              >
                Start ManagerMatch →
              </button>
            </div>
            <p className="text-xs text-ink-tertiary leading-relaxed pt-2">
              <Link to="/trust" className="font-semibold text-forest-dark hover:underline">
                How this works, and what we hold back →
              </Link>
            </p>
          </article>
        </Shell>
      );
    }

    return (
      <Shell>
        <BackLink />
        <article className="space-y-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
            Situation Report
          </p>
          <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">
            One half to go
          </h1>
          <p className="text-sm text-ink-secondary leading-relaxed">
            Work Pulse told us how you work. Now about ten questions about your job —
            what the role actually offers, in your words rather than the job
            description's. About five minutes, and the report comes back straight away.
          </p>
          <button
            type="button"
            onClick={() => navigate("/environment-report")}
            className="inline-flex items-center bg-forest-dark text-white text-sm font-semibold px-6 py-3 rounded hover:bg-forest-mid transition-colors"
          >
            Describe your job →
          </button>
          <div className="pt-4">
            <ManagerSection manager={report.manager} />
          </div>
        </article>
      </Shell>
    );
  }

  // ── complete ──────────────────────────────────────────────────────────────
  const past = report.needs_forward;

  return (
    <Shell>
      <div className="flex items-center justify-between print:hidden">
        <BackLink />
        <button
          type="button"
          onClick={() => window.print()}
          className="text-xs font-semibold text-ink-tertiary hover:underline"
        >
          Print this report
        </button>
      </div>

      <article className="space-y-8">
        <header className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
            Situation Report
          </p>
          <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">
            {past ? "What to look for next" : "You, and this job"}
          </h1>
          <p className="text-sm text-ink-secondary leading-relaxed">
            {past
              ? "Ranked by how far apart you and that role sat. What comes first is what to look hardest at in the next one."
              : "Ranked by how far apart you and the role sit. What is under most strain comes first."}
          </p>
          {past && (
            <p className="text-sm text-ink-secondary leading-relaxed">
              If you and that role fitted on some dimension, it is not listed below — the
              fit was real, but this report can see that the job ended and not why, and a
              past match turned forward would be a guess wearing the report's voice.
            </p>
          )}
        </header>

        {report.dimensions.length === 0 ? (
          <section className="rounded-xl border border-forest-light bg-forest-pale px-6 py-5">
            <p className="text-sm text-forest-dark font-medium leading-relaxed">
              {past
                ? "Nothing came back to carry forward: on every dimension we measure, you and that role were set much the same way. That is worth knowing about the kind of role to look for, even though the report will not turn it into an instruction."
                : "Nothing is straining. On every dimension we measure, you and this job are set much the same way — which is uncommon enough to be worth noticing rather than assuming."}
            </p>
          </section>
        ) : (
          /* Document order IS the ranking. There is no rank number on screen,
             and there must not be one. */
          <section className="space-y-4">
            {report.dimensions.map((entry) =>
              isAlignedEntry(entry) ? (
                <AlignedCard key={entry.dimension} entry={entry} />
              ) : (
                <StrainCard
                  key={entry.dimension}
                  entry={entry}
                  past={past}
                  manager={report.manager}
                />
              ),
            )}
          </section>
        )}

        <ManagerSection manager={report.manager} />

        <GuidanceNotice notice={report.guidance_notice} />
      </article>

      <HonestFooter />
    </Shell>
  );
}
