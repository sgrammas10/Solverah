/**
 * resumeDraft -- the logic half of the shared "pick up where you left off" prompt.
 *
 * Every quiz keeps its in-progress answers in sessionStorage. Before this, a user
 * re-opening one was dropped silently at wherever the draft ended (or, worse, at
 * question 1 with the old answers still selected). The prompt makes that an explicit
 * choice; these two helpers are the bits every quiz needs to offer it.
 */
import { useCallback, useState } from "react";

/**
 * Index of the first item `isAnswered` rejects, or the last index when every item is
 * answered (so a resume of a finished-but-unsubmitted draft lands on the final question,
 * where the submit button lives). Returns 0 for an empty list.
 */
export function firstUnansweredIndex<T>(
  items: readonly T[],
  isAnswered: (item: T) => boolean,
): number {
  const idx = items.findIndex((item) => !isAnswered(item));
  if (idx !== -1) return idx;
  return Math.max(items.length - 1, 0);
}

/**
 * Whether the resume prompt is still waiting on the user.
 *
 * `hadDraftAtMount` is read ONCE, on the first render: the prompt is about a draft
 * found on arrival, so answering the first question of a fresh attempt must not
 * summon it. Callers pass a lazy initializer or a value computed from state that was
 * itself read synchronously from storage.
 */
export function useResumePrompt(hadDraftAtMount: boolean | (() => boolean)) {
  const [pending, setPending] = useState<boolean>(hadDraftAtMount);
  const dismiss = useCallback(() => setPending(false), []);
  return { showResumePrompt: pending, dismissResumePrompt: dismiss };
}
