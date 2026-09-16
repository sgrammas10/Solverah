/**
 * pathFailure.ts — the error vocabulary every Path Intelligence call speaks.
 *
 * The backend answers `{"error": "<code>"}` and `apiError.messageFrom` prefers
 * `body.error` over everything but `detail`, so the code arrives verbatim as
 * `ApiError.message`. That coupling is what lets one mapping serve the page, the
 * feedback controls and the deep-fit panel.
 *
 * Lifted out of `PathIntelligencePage` for F-6. It was a module-private function
 * there, which was right while one screen used it; three call sites is where a
 * private copy starts drifting.
 */

/**
 * `loading` is the job's pending state and four others are its terminal ones;
 * `needs_preferences` is the UI override that shows the preferences form over
 * whichever of those the job lifecycle is in.
 */
export type FetchState =
  | "loading"
  | "error"
  | "career_status_not_set"
  | "profile_incomplete"
  | "needs_preferences"
  | "success";

/**
 * Which screen a failure puts up.
 *
 * The two named codes are recoverable by the user and get their own prompts;
 * everything else is the retryable error card. They used to reach this page as
 * the `message` of a 400 and now reach it as a failed job's `error` — the same
 * strings either way, which is what lets this mapping be shared by both paths.
 *
 * **The Tier-2 codes are deliberately absent.** `invalid_onet_code`,
 * `unknown_occupation`, `unsupported_occupation` and `corpus_unavailable` are
 * facts about one card, not about the user's profile, and taking the whole
 * screen down for them would throw away nine good suggestions because the tenth
 * could not be opened. They are handled where they happen — see
 * `pathFitMessage`.
 */
export function stateForFailure(message: string): FetchState {
  if (message === "career_status_not_set") return "career_status_not_set";
  if (message === "profile_incomplete") return "profile_incomplete";
  return "error";
}

/** True when a failure is about the profile rather than about one occupation. */
export function isProfileLevelFailure(message: string): boolean {
  return stateForFailure(message) !== "error";
}

/**
 * Copy for a deep-fit failure, and whether retrying it could ever work.
 *
 * Julie owns the wording; these are best guesses and are meant to be revised on
 * the built product. The `retryable` flag is not a wording question: offering
 * "Try again" for a permanent 404 is how a user ends up pressing a button
 * forever.
 */
export function pathFitMessage(message: string): { text: string; retryable: boolean } {
  switch (message) {
    case "corpus_unavailable":
      return {
        text: "We couldn't reach the occupation data just now. Give it a moment and try again.",
        retryable: true,
      };
    case "unsupported_occupation":
      return {
        text: "There isn't enough detail about this occupation to break it down.",
        retryable: false,
      };
    case "unknown_occupation":
      return {
        text: "This path isn't available any more. Refresh your suggestions to see the current list.",
        retryable: false,
      };
    case "invalid_onet_code":
      return {
        text: "Something went wrong opening this path.",
        retryable: false,
      };
    default:
      return {
        text: "We couldn't open this path right now.",
        retryable: true,
      };
  }
}
