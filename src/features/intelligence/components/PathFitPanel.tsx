/**
 * PathFitPanel — the Tier-2 deep fit for one occupation, opened by a card click.
 *
 * F-5 built `POST /me/path-fit/{onet_code}` and deliberately left it unwired;
 * this is the wiring (BUILD_PLAN F-6). Everything rendered here comes straight
 * from what the API returns — nothing is LLM-written, and `narrative` is
 * always null for now, so there is no placeholder for it.
 *
 * ── NO SCORE, NOT EVEN IN WORDS (§8.5, W-1) ─────────────────────────────────
 *
 * `fit_score`, `skills_score`, `coverage_score` and `work_style_score` stay on
 * the wire — the contract does not change — but none of the four is rendered,
 * as a number, a bar, or a word standing in for one ("Strong overlap" is still
 * a grade put on the user). The panel's content is the sections that need no
 * score to make sense: Training, Skills you already have, Worth picking up,
 * What you'd be doing, Tools people use.
 *
 * ── THE SPINNER IS SIZED TO 850 ms, NOT TO 12 ms ───────────────────────────
 *
 * Measured server-side: 2,384 ms cold, 844 ms when another user has already
 * opened the same card, 12 ms once *this* user has. The middle number is the
 * common case on a shared shortlist, so the spinner appears immediately rather
 * than after a deferred fade — at 850 ms a delayed spinner reads as a frozen
 * page — and the panel opens before the request lands so the click has an
 * effect straight away. See `PATH_FIT_EXPECTED_MS`.
 *
 * ── THE GAP LIST IS THE API'S, NOT THIS PANEL'S ────────────────────────────
 *
 * This panel renders what the API returns and filters nothing.
 *
 * It was written that way while a known defect was live: `_EMBED_THRESHOLD` in
 * `path_deep_fit` is too strict for O*NET's verbose names, so a user with "SQL"
 * could be told "Structured query language SQL" was a gap. Hiding it here would
 * have made it invisible to exactly the people who could report it. F-8 box 5
 * fixed it at the source -- skill-name normalisation, not a tuned threshold --
 * and the rule survives the fix: a gap the backend sends is a gap we show.
 */
import { useEffect } from "react";

import { pathFitMessage } from "../pathFailure";
import { PATH_FIT_EXPECTED_MS, type PathFit } from "../usePathFeedback";

export interface PathFitPanelProps {
  /** The occupation being analysed. Used for the heading before data arrives. */
  title: string;
  fit: PathFit | null;
  /** Loading state; the panel is mounted and empty while this is true. */
  pending: boolean;
  /** The server's `{"error": code}` string, or null. */
  errorCode: string | null;
  onClose: () => void;
  onRetry: () => void;
}

function Section({ heading, children }: { heading: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-forest-light">
        {heading}
      </h3>
      {children}
    </section>
  );
}

function Pills({ items }: { items: string[] }) {
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item) => (
        <span
          key={item}
          className="rounded-full border border-cream-muted bg-cream-base px-3 py-1 text-xs text-ink-primary"
        >
          {item}
        </span>
      ))}
    </div>
  );
}

/**
 * Julie owns this wording; it is a best guess and is meant to be revised on the
 * built product. The *structure* is not a wording question: a Job Zone is
 * education and training required, and the only thing a user needs from it is
 * whether this path asks for more schooling than they have.
 */
function zoneLine(fit: PathFit): string {
  const zone = fit.zone;
  if (zone.occupation_zone == null || zone.delta == null) {
    return "We don't have training requirements for this one.";
  }
  if (zone.delta > 0) {
    return `Needs more training than your current level${
      zone.user_zone_resolved ? "" : " (we've estimated your level)"
    }.`;
  }
  if (zone.delta < 0) {
    return "Needs less training than your current level.";
  }
  return "About the same training as your current level.";
}

export default function PathFitPanel({
  title,
  fit,
  pending,
  errorCode,
  onClose,
  onRetry,
}: PathFitPanelProps) {
  // Escape closes. SkillProficiencyModal, the in-slice precedent this shell is
  // copied from, has no key handler; adding one here rather than matching that
  // omission, because this panel is opened by a click on a card the user was
  // reading and the way out of it has to be obvious.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const failure = errorCode ? pathFitMessage(errorCode) : null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center px-4 py-8 overflow-y-auto">
      <div
        className="absolute inset-0 bg-ink-primary/40"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`How ${title} fits you`}
        className="relative w-full max-w-2xl rounded-2xl border border-cream-subtle bg-cream-base shadow-2xl shadow-ink-primary/20"
      >
        <div className="flex items-start justify-between gap-4 border-b border-cream-muted px-6 py-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
              How this fits you
            </p>
            <h2 className="font-display text-xl font-semibold text-ink-primary">{title}</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 rounded px-2 py-1 text-ink-tertiary hover:text-ink-primary transition-colors"
          >
            ✕
          </button>
        </div>

        <div className="max-h-[70vh] overflow-y-auto px-6 py-5 space-y-6">
          {pending && (
            <div
              role="status"
              aria-live="polite"
              // The expected wait is on the element rather than only in a
              // comment, so the test can assert the panel was sized to the
              // measured latency instead of asserting a spinner exists.
              data-expected-ms={PATH_FIT_EXPECTED_MS}
              className="flex flex-col items-center gap-3 py-10"
            >
              <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
              <p className="text-sm text-ink-secondary">Working out how this fits you…</p>
            </div>
          )}

          {!pending && failure && (
            <div
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700"
            >
              <p className="font-medium mb-1">{failure.text}</p>
              {failure.retryable && (
                <button
                  type="button"
                  onClick={onRetry}
                  className="mt-3 text-xs font-semibold text-red-700 underline"
                >
                  Try again
                </button>
              )}
            </div>
          )}

          {!pending && !failure && fit && (
            // The generated types mark every list field optional, because the
            // schema gives them a default rather than requiring them. Defaulting
            // once here keeps four `?? []` out of the markup below.
            <>
              <Section heading="Training">
                <p className="text-sm text-ink-primary leading-relaxed">{zoneLine(fit)}</p>
              </Section>

              {(fit.matched_skills ?? []).length > 0 && (
                <Section heading="Skills you already have">
                  <Pills items={fit.matched_skills ?? []} />
                </Section>
              )}

              {(fit.gap_skills ?? []).length > 0 && (
                <Section heading="Worth picking up">
                  {/* Sorted by importance already, per the backend contract (F-5)
                     -- this list renders that order without a number attached
                     to it (§8.5, W-1). */}
                  <ul className="space-y-1.5">
                    {(fit.gap_skills ?? []).map((gap) => (
                      <li key={gap.name} className="text-sm text-ink-primary">
                        {gap.name}
                      </li>
                    ))}
                  </ul>
                </Section>
              )}

              {(fit.tasks ?? []).length > 0 && (
                <Section heading="What you'd be doing">
                  <ul className="list-disc pl-5 space-y-1.5 text-sm text-ink-primary leading-relaxed">
                    {(fit.tasks ?? []).map((task) => (
                      <li key={task}>{task}</li>
                    ))}
                  </ul>
                </Section>
              )}

              {(fit.tech_stack ?? []).length > 0 && (
                <Section heading="Tools people use">
                  <Pills items={fit.tech_stack ?? []} />
                </Section>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
