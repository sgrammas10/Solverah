import { useState } from "react";
import type { PathSuggestion, CareerStatus } from "../types";
import type { PathVerdict } from "../usePathFeedback";

export interface PathSuggestionCardProps {
  suggestion: PathSuggestion;
  currentTitle: string | null;
  careerStatus: CareerStatus;
  /** Open the deep-fit panel for this occupation. Omitted, the card is inert. */
  onOpen?: (onetCode: string) => void;
  /** The verdict this user has already given this card, if any. */
  verdict?: PathVerdict | null;
  /** Record a verdict. Omitted, the feedback controls are not rendered at all. */
  onVerdict?: (onetCode: string, verdict: PathVerdict) => void;
  /** A tap is in flight anywhere in the list; every control disables together. */
  feedbackPending?: boolean;
}

function buildProgressionLine(
  careerStatus: CareerStatus,
  currentTitle: string | null,
  targetTitle: string
): string {
  if (careerStatus === "first_job") {
    return `Starting out → ${targetTitle}`;
  }
  if (careerStatus === "between_jobs") {
    return `Previously ${currentTitle ?? "Last Role"} → ${targetTitle}`;
  }
  return `${currentTitle ?? "Current Role"} → ${targetTitle}`;
}

/**
 * The feedback controls (BUILD_PLAN F-6, design doc §3.2).
 *
 * **Three verdicts, and they are not three strengths of one opinion.**
 * "Too similar" is a *radius* — it tells the scorer to exclude everything at
 * least that close to the user's own job. The other two are *directions*: the
 * retrieval query rotates toward what they liked and away from what they did
 * not. Collapsing them into a thumbs up/down would throw away the distinction
 * the whole feature rests on, and would make "too similar" the only available
 * "no", which would corrupt the radius with opinions that are not about
 * distance.
 *
 * Julie owns the labels. These are best guesses; the test selects these
 * controls by `data-verdict` and `aria-pressed`, never by their text, so
 * rewording them cannot redden the suite.
 */
const VERDICT_LABELS: Record<PathVerdict, string> = {
  interesting: "Interesting",
  too_similar: "Too similar to my job",
  not_for_me: "Not for me",
};

const VERDICT_ORDER: PathVerdict[] = ["interesting", "too_similar", "not_for_me"];

export default function PathSuggestionCard({
  suggestion,
  currentTitle,
  careerStatus,
  onOpen,
  verdict = null,
  onVerdict,
  feedbackPending = false,
}: PathSuggestionCardProps) {
  const [showTooltip, setShowTooltip] = useState(false);

  const progressionLine = buildProgressionLine(careerStatus, currentTitle, suggestion.title);
  const scorePercent = Math.round(suggestion.match_score * 100);

  // The opening affordance is a button around the card's *body*, not an onClick
  // on the card itself. The feedback controls and the disabled CTA are
  // interactive, and nesting them inside a clickable region gives a keyboard
  // user a control they cannot reach and a screen reader a button containing
  // buttons. Body-as-button keeps every control a sibling.
  const body = (
    <>
      <div>
        <p className="font-display text-lg font-semibold text-ink-primary">
          {suggestion.title}
        </p>
        <p className="text-xs text-ink-secondary mt-0.5">{progressionLine}</p>
      </div>

      <p className="text-sm text-ink-primary leading-relaxed">{suggestion.why_text}</p>

      {suggestion.profile_dimensions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {suggestion.profile_dimensions.map((dim) => (
            <span
              key={dim}
              className="rounded-full border border-forest-light bg-white px-3 py-1 text-xs font-semibold text-forest-mid"
            >
              {dim}
            </span>
          ))}
        </div>
      )}

      <div>
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-ink-tertiary">Match score</span>
          <span className="text-xs font-semibold text-forest-mid">{scorePercent}%</span>
        </div>
        <div className="w-full h-1.5 bg-cream-muted rounded-full overflow-hidden">
          <div
            className="h-full bg-forest-light rounded-full"
            style={{ width: `${scorePercent}%` }}
          />
        </div>
      </div>
    </>
  );

  return (
    // `data-onet-code` is a test hook, and the only one on this card. The
    // real_stack flow (tests/e2e/path_intelligence.spec.ts) has to name a
    // specific card to tap a verdict on it and then assert that card is gone
    // after the re-rank; addressing it by its rendered TITLE would make the
    // E2E a copy test, and by its position would make it meaningless the
    // moment the list re-orders -- which is the thing being tested.
    <div
      data-onet-code={suggestion.onet_code}
      className="rounded-xl border border-cream-muted bg-white px-5 py-5 space-y-4"
    >
      {onOpen ? (
        <button
          type="button"
          onClick={() => onOpen(suggestion.onet_code)}
          aria-label={`See how ${suggestion.title} fits you`}
          className="w-full text-left space-y-4 rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-forest-light"
        >
          {body}
        </button>
      ) : (
        <div className="space-y-4">{body}</div>
      )}

      {onVerdict && (
        <div
          className="flex flex-wrap items-center gap-2 border-t border-cream-muted pt-3"
          role="group"
          aria-label="How do you feel about this path?"
        >
          {VERDICT_ORDER.map((value) => {
            const active = verdict === value;
            return (
              <button
                key={value}
                type="button"
                data-verdict={value}
                aria-pressed={active}
                disabled={feedbackPending}
                onClick={() => onVerdict(suggestion.onet_code, value)}
                className={[
                  "rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors",
                  active
                    ? "border-forest-mid bg-forest-pale text-forest-mid"
                    : "border-cream-muted text-ink-secondary hover:bg-cream-base",
                  feedbackPending ? "opacity-60 cursor-not-allowed" : "",
                ].join(" ")}
              >
                {VERDICT_LABELS[value]}
              </button>
            );
          })}
        </div>
      )}

      {/* Set as target role — disabled CTA with hover tooltip */}
      <div
        className="relative inline-block"
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
      >
        <button
          type="button"
          disabled
          className="border border-cream-muted text-ink-tertiary text-xs font-semibold px-3 py-1.5 rounded cursor-not-allowed opacity-60"
        >
          Set as target role
        </button>
        {showTooltip && (
          <div
            role="tooltip"
            className="absolute bottom-full left-0 mb-2 w-56 rounded bg-ink-primary px-3 py-2 text-xs text-white shadow-lg"
          >
            Coming soon — goal tracking is on the way
          </div>
        )}
      </div>

    </div>
  );
}
