/**
 * usePathFeedback.ts — the inline card feedback loop and the deep fit on click.
 *
 * Three mutations, all synchronous on the server and all returning what the
 * screen needs rather than a handle to poll:
 *
 *   POST   /me/path-feedback         one judgement, then the re-ranked list
 *   DELETE /me/path-feedback         clear every judgement, then the default list
 *   POST   /me/path-fit/{onet_code}  the Tier-2 analysis of one occupation
 *
 * ── WHY NONE OF THESE IS A JOB/POLL PAIR ───────────────────────────────────
 *
 * `POST /me/path-suggestion-jobs` is queued because its fan-out is slow. These
 * are not: a re-rank is one matrix product plus, at most, a narrative for the
 * two to six cards that are new, and a deep fit is four cached O*NET calls.
 * Measured server-side: a deep fit is 844 ms in the common case (another user
 * has opened the same card), 2.4 s cold, 12 ms once this user has opened it.
 * A job handle the client had to poll would cost more round trips than it saved.
 *
 * ── NOTHING HERE RETRIES ───────────────────────────────────────────────────
 *
 * The global mutation default is `retry: false` and that is correct for all
 * three: every one of them carries a rate limit precisely because it can reach
 * a provider, and a client-side retry spends somebody's budget on a request the
 * user did not make twice.
 */
import { useMutation } from "@tanstack/react-query";

import { useAuth } from "../auth";
import type { components } from "../../shared/api/schema";

type PathFeedbackResponse = components["schemas"]["PathFeedbackResponse"];
type PathFitResponseSchema = components["schemas"]["PathFitResponse"];

/** The three verdicts a card can carry. Mirrors the server's closed vocabulary. */
export type PathVerdict = "too_similar" | "interesting" | "not_for_me";

export const PATH_VERDICTS: readonly PathVerdict[] = [
  "interesting",
  "too_similar",
  "not_for_me",
] as const;

/** Every judgement standing for this user, as `onet_code -> verdict`. */
export type PathFeedbackMap = Record<string, PathVerdict>;

export type PathFeedbackResult = PathFeedbackResponse;
export type PathFit = PathFitResponseSchema;

/**
 * How long the deep-fit panel expects to wait, in milliseconds.
 *
 * Sized to the **common** case rather than the best one: 844 ms is a card
 * another user has already opened, which is what most clicks are once a
 * shortlist has been seen by more than one person. The warm-for-this-user case
 * is 12 ms and the cold one is 2.4 s. A spinner tuned to 12 ms would be a flash
 * on nearly every real click; one tuned to 2.4 s would leave the panel looking
 * hung for a second after the content was ready.
 *
 * Exported so the panel and its test agree on the number rather than each
 * hard-coding it.
 */
export const PATH_FIT_EXPECTED_MS = 850;

/** `POST /me/path-feedback` — store one judgement, get the re-ranked list back. */
export function useRecordPathFeedback() {
  const { fetchWithAuth } = useAuth();

  return useMutation({
    mutationFn: (body: { onet_code: string; verdict: PathVerdict }) =>
      fetchWithAuth<PathFeedbackResponse>("/me/path-feedback", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}

/**
 * `DELETE /me/path-feedback` — clear every judgement, get the default list back.
 *
 * A DELETE that returns a body, and the body is the point: the alternative is a
 * 204 and a second round trip to find out what the user is now looking at.
 */
export function useClearPathFeedback() {
  const { fetchWithAuth } = useAuth();

  return useMutation({
    mutationFn: () =>
      fetchWithAuth<PathFeedbackResponse>("/me/path-feedback", {
        method: "DELETE",
      }),
  });
}

/**
 * `POST /me/path-fit/{onet_code}` — the Tier-2 analysis of one occupation.
 *
 * POST rather than GET because it is a per-click provider spend with a stored
 * side effect, which also puts it behind the CSRF guard every other write on
 * this blueprint sits behind. No request body: the analysis reads the caller's
 * stored profile.
 */
export function usePathFit() {
  const { fetchWithAuth } = useAuth();

  return useMutation({
    mutationFn: (onetCode: string) =>
      fetchWithAuth<PathFitResponseSchema>(`/me/path-fit/${onetCode}`, {
        method: "POST",
      }),
  });
}
