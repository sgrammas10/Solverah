import { useEffect, useState } from "react";
import type { PathSuggestion, CareerStatus } from "../types";
import type { PathFeedbackMap, PathVerdict } from "../usePathFeedback";
import PathSuggestionCard from "./PathSuggestionCard";

export interface PathSuggestionListProps {
  suggestions: PathSuggestion[];
  currentTitle: string | null;
  careerStatus: CareerStatus;
  onOpen?: (onetCode: string) => void;
  /**
   * The codes of the cards actually on screen, reported after each render that
   * changes them (W-9). The page uses it to warm those cards' deep fits.
   *
   * The list owns this rather than the page because the list owns the paging:
   * `PAGE_SIZE` is three and "Show more" reveals three more, so "what is
   * rendered" is a fact only this component has. Warming all ten would spend
   * seven requests on cards nobody has scrolled to.
   *
   * It is an effect dependency, so a callback that changes identity every
   * render fires it every render. That is harmless rather than fine —
   * `usePrefetchPathFits` skips any code already in the cache — but pass a
   * `useCallback` anyway.
   */
  onVisibleCodes?: (onetCodes: string[]) => void;
  /** Every judgement standing for this user, keyed by O*NET code. */
  feedback?: PathFeedbackMap;
  onVerdict?: (onetCode: string, verdict: PathVerdict) => void;
  feedbackPending?: boolean;
}

const PAGE_SIZE = 3;

export default function PathSuggestionList({
  suggestions,
  currentTitle,
  careerStatus,
  onOpen,
  onVisibleCodes,
  feedback,
  onVerdict,
  feedbackPending = false,
}: PathSuggestionListProps) {
  // Paging state is deliberately NOT keyed to the suggestions: a re-rank
  // replaces the list under the user's cursor, and collapsing it back to three
  // cards would punish them for giving feedback. They keep however much of the
  // list they had opened.
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const visible = suggestions.slice(0, visibleCount);
  const remaining = suggestions.length - visibleCount;
  const nextBatch = Math.min(PAGE_SIZE, remaining);

  // `useEffect`, not `useLayoutEffect` and not inline: the report happens after
  // the browser has the cards, so nothing the page does with it can delay them.
  // The dependency is the joined string rather than the array, because
  // `slice()` returns a new array on every render and an array dependency would
  // fire this on each one.
  const visibleKey = visible.map((s) => s.onet_code).join(",");
  useEffect(() => {
    if (!onVisibleCodes || !visibleKey) return;
    onVisibleCodes(visibleKey.split(","));
  }, [visibleKey, onVisibleCodes]);

  return (
    <div className="space-y-4">
      {visible.map((suggestion) => (
        <PathSuggestionCard
          key={suggestion.onet_code}
          suggestion={suggestion}
          currentTitle={currentTitle}
          careerStatus={careerStatus}
          onOpen={onOpen}
          verdict={feedback?.[suggestion.onet_code] ?? null}
          onVerdict={onVerdict}
          feedbackPending={feedbackPending}
        />
      ))}

      {nextBatch > 0 && (
        <button
          type="button"
          onClick={() => setVisibleCount((n) => n + PAGE_SIZE)}
          className="w-full rounded-xl border border-cream-muted bg-white px-5 py-3 text-sm font-semibold text-forest-mid hover:bg-cream-base transition-colors"
        >
          Show {nextBatch} more path{nextBatch !== 1 ? "s" : ""}
        </button>
      )}
    </div>
  );
}
