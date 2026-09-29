import { useEffect, useState, type ReactNode } from "react";
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

/**
 * W-18: the height kept for the narrator's sentence and its tags while they
 * are being written, so that nothing below a card moves when they land.
 *
 * W-17 measured the shift this removes: card 1 grew 253 -> 319 px when its
 * sentence and tags arrived, pushing every card below it down 66 px.
 *
 * The sentence and the tags share ONE block with one minimum height, sized for
 * the narrator's worst case rather than its median: sentences run p50 222 /
 * max 308 characters (four lines of `text-sm` at the page's 584 px card width,
 * six at phone width), and the prompt asks for "2 or 3 short tags (5-8 words
 * each)" -- three of those wrap to two rows on desktop, three at phone width.
 * The first W-18 browser run reserved a single tag row and measured the miss:
 * a card whose narrator wrote three tags still grew 34 px.
 *
 * One block rather than two slots so the slack gathers at the bottom, above
 * the divider, instead of opening a gap between a short sentence and its tags;
 * and so a fallback sentence with no tags still fills the same space. It is a
 * MINIMUM inside a grid cell, so a sentence longer than any measured grows the
 * card rather than overflowing it, and it stays after landing, because giving
 * the space back would be the same shift in the other direction.
 */
const NARRATION_BLOCK_CLASS = "grid content-start min-h-[15.25rem] sm:min-h-[10.25rem]";

interface FadeInProps {
  children: ReactNode;
  className?: string;
}

/**
 * Mounts transparent and fades to opaque on the next frame (W-18). The
 * narrator's sentence and tags are ADDED to a card someone is already reading;
 * a fade says "this just arrived" without moving anything. Reduced-motion users
 * get it at once.
 */
function FadeIn({ children, className = "" }: FadeInProps) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setShown(true));
    return () => cancelAnimationFrame(id);
  }, []);
  return (
    <div
      data-fade={shown ? "in" : "pending"}
      className={`transition-opacity duration-500 ease-out motion-reduce:transition-none ${
        shown ? "opacity-100" : "opacity-0"
      } ${className}`}
    >
      {children}
    </div>
  );
}

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
  // Optional on the wire: a payload cached before W-4 shipped carries no
  // `reasons`, and a user who has stated no wants gets an empty list. Both mean
  // the same thing and render the same way -- nothing.
  const reasons = suggestion.reasons ?? [];
  // W-18. Optional for the same reason: a payload cached before W-18, or a
  // server without the summaries sidecar, has none -- and renders no line.
  const summary = suggestion.summary ?? "";
  const pending = Boolean(suggestion.sentence_pending);
  const tags = suggestion.profile_dimensions;
  // The reserved block exists while something is coming or has come. With
  // nothing coming (the poll gave up on a card the narrator never wrote) there
  // is nothing to hold a place for.
  const narrationBlock = pending || Boolean(suggestion.why_text);

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

      {/* W-18: what the job IS, in O*NET's own words -- on the card from the
          first poll, so the card is readable before the narrator has written
          anything. Plain text and no label: it reads as the card's opening
          line, and the personal sentence below it says why it is here. */}
      {summary && (
        <p data-summary className="text-sm text-ink-secondary leading-relaxed">
          {summary}
        </p>
      )}

      {/* W-5: the reason line, where the percentage used to be (§8.5, ⚑12).
          At most two short phrases saying what is distinctive about THIS card
          against the user's own job, built only when they have said what should
          change. Absent or empty is the common case and renders nothing at all
          -- no heading, no placeholder, no "no reasons yet" -- because a card
          with nothing distinctive to say about it still has its why-text.

          Words only, and never a graded one: W-1's correction was that "Strong
          overlap" is a percentage in a costume. These phrases are absolute or
          comparative statements about the work ("Among the most people-facing
          jobs"), never a verdict on the user.

          W-18 moved it above the narrator's block: it is scored with the card
          and present from the first poll, like the summary, so everything that
          is already known sits together above everything still being written. */}
      {reasons.length > 0 && (
        <ul data-reasons className="space-y-1">
          {reasons.map((reason) => (
            <li key={reason} className="text-xs text-ink-secondary leading-relaxed">
              {reason}
            </li>
          ))}
        </ul>
      )}

      {/* W-16: the card arrives before its sentence. While the sentence is
          being written the card holds its place with a placeholder line --
          never a stand-in sentence, which would change under the reader when
          the real one lands. No pills meanwhile: the tags are written with it.

          W-18: the place is held at the sentence's and the tags' full expected
          height (NARRATION_BLOCK_CLASS), and both fade in inside it. The
          sentence is ADDED below the summary, never swapped for it. The
          placeholder is shaped like what is coming -- three thin lines and two
          tag outlines -- so the reserved space reads as "being written" rather
          than as a gap, with or without a summary above it. */}
      {narrationBlock && (
        <div data-narration-block className={NARRATION_BLOCK_CLASS}>
          {pending ? (
            <div data-sentence-pending className="space-y-3 py-1.5">
              <span className="sr-only">Writing why this path could suit you…</span>
              <div aria-hidden="true" className="space-y-2.5 animate-pulse">
                <div className="h-2.5 rounded bg-cream-muted w-full" />
                <div className="h-2.5 rounded bg-cream-muted w-11/12" />
                <div className="h-2.5 rounded bg-cream-muted w-3/5" />
              </div>
              <div aria-hidden="true" className="flex gap-2 animate-pulse">
                <div className="h-6 w-40 rounded-full border border-cream-muted" />
                <div className="h-6 w-32 rounded-full border border-cream-muted" />
              </div>
            </div>
          ) : (
            <FadeIn className="space-y-3">
              <p className="text-sm text-ink-primary leading-relaxed">{suggestion.why_text}</p>
              {tags.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {tags.map((dim) => (
                    <span
                      key={dim}
                      className="rounded-full border border-forest-light bg-white px-3 py-1 text-xs font-semibold text-forest-mid"
                    >
                      {dim}
                    </span>
                  ))}
                </div>
              )}
            </FadeIn>
          )}
        </div>
      )}
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
          // Below the button, not above it: `bottom-full` used to open the
          // tooltip upward, straight over the Interesting / Too similar / Not
          // for me row that sits above this CTA. The card has no `overflow`
          // clipping, so a tooltip hanging below the last element is fine.
          <div
            role="tooltip"
            className="absolute top-full left-0 mt-2 w-56 rounded bg-ink-primary px-3 py-2 text-xs text-white shadow-lg"
          >
            Coming soon — goal tracking is on the way
          </div>
        )}
      </div>

    </div>
  );
}
