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
 *
 * W-5 adds the wants panel's vocabulary at the bottom. It is the deep fit's
 * shape, not the page's: a panel that must never take the screen (design doc
 * §8.3) needs copy and a retryable flag, not a `FetchState`.
 */
import { ApiError } from "../../shared/api/apiError";

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

/**
 * True when a wants save was refused because the panel on screen is about a job
 * this user no longer holds — `422`, `errors[].code === "not_offered"`, and
 * **nothing was written**.
 *
 * Branched on by code, never by the prose in `error.message`: the server sends
 * a paragraph of `detail` there and the wording is not a contract.
 * `isFirstJobRefusal` in `useSituationReport` is the precedent.
 *
 * The realistic way to reach it is two tabs — the panel was built from the job
 * the user held when the page loaded, and they changed their job somewhere
 * else since. It is not something the user did wrong on this screen, so the
 * answer is to reload the panel, not to correct them.
 */
export function isStalePanel(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    error.fieldErrors.some((fieldError) => fieldError.code === "not_offered")
  );
}

/**
 * Copy for a refused wants save, and whether pressing the button again could
 * ever work.
 *
 * Julie owns the wording; best guesses, revised on the built product. What is
 * not a wording question: a stale panel is `retryable: false` because the body
 * that was refused would be refused identically a second time, and the 429 says
 * "in a minute" because the GET and the PUT share one 20/min bucket.
 */
export function pathWantsMessage(error: unknown): { text: string; retryable: boolean } {
  if (isStalePanel(error)) {
    return {
      text: "Your job details changed, so we've reloaded this. Have another look and press the button again.",
      retryable: false,
    };
  }
  const status = error instanceof ApiError ? error.status : 0;
  const message = error instanceof Error ? error.message : "";
  if (status === 429) {
    return {
      text: "That's a lot of changes at once. Give it a minute and try again.",
      retryable: true,
    };
  }
  if (message === "corpus_unavailable" || status === 503) {
    return {
      text: "We couldn't reach the occupation data just now. Give it a moment and try again.",
      retryable: true,
    };
  }
  return { text: "We couldn't save that just now. Try again in a moment.", retryable: true };
}
