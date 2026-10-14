/**
 * usePoll -- poll one resource until it says it is finished, backing off as it goes.
 *
 * Used for the two slow things CompanyLens waits on: a company research run
 * (`GET /companies/research/{run_id}`) and a pasted job posting
 * (`GET /me/job-postings/{id}`). Both can take minutes, so a fixed 3 s interval
 * would spend hundreds of requests on one wait. The first poll waits
 * `initialMs`, and each later wait is `factor` times longer, up to `maxMs`.
 *
 * Why a timer chain and not TanStack Query's `refetchInterval`: enabling a query
 * fetches at once, and the brief is "start at 3 s". A chain of `setTimeout`s also
 * makes the unmount rule plain to read -- the cleanup clears the pending timer and
 * marks the chain cancelled, so a response landing after unmount sets no state and
 * schedules nothing.
 *
 * Errors: a retryable failure (5xx, 429, a dropped connection) is retried on the same
 * schedule up to `MAX_CONSECUTIVE_FAILURES` times in a row; anything else (a 404 on
 * a stale id) stops the chain at once and is returned as `error`.
 */
import { useEffect, useRef, useState } from "react";

import { ApiError } from "../../shared/api/apiError";

export interface PollTiming {
  /** Wait before the first poll. */
  initialMs: number;
  /** Each later wait is the previous one times this. */
  factor: number;
  /** Ceiling on any one wait. */
  maxMs: number;
}

export const DEFAULT_POLL_TIMING: PollTiming = { initialMs: 3000, factor: 1.5, maxMs: 20000 };

export const MAX_CONSECUTIVE_FAILURES = 3;

/** The wait before poll number `attempt` (0-based). */
export function pollDelay(attempt: number, timing: PollTiming): number {
  return Math.min(timing.maxMs, Math.round(timing.initialMs * timing.factor ** attempt));
}

function isRetryable(error: unknown): boolean {
  // A non-ApiError is a fetch that never got a response (a TypeError from the
  // network layer): retryable, like ApiError's own status-0 case.
  return error instanceof ApiError ? error.isRetryable : true;
}

export interface PollState<T> {
  /** The newest response, or null before the first one lands. */
  data: T | null;
  /** Set when polling stopped on a failure. */
  error: unknown;
  /** True while a timer is pending or a request is in flight. */
  polling: boolean;
}

/**
 * Poll `fetcher(target)` until `isDone` says so. `target` null means "nothing to
 * poll"; changing it restarts the chain from `initialMs`.
 */
export function usePoll<T>(
  target: string | null,
  fetcher: (target: string) => Promise<T>,
  isDone: (value: T) => boolean,
  timing: PollTiming = DEFAULT_POLL_TIMING,
): PollState<T> {
  // Refs, so a new fetcher identity each render (fetchWithAuth is rebuilt with
  // the auth context) does not restart the chain.
  const fetcherRef = useRef(fetcher);
  const isDoneRef = useRef(isDone);
  fetcherRef.current = fetcher;
  isDoneRef.current = isDone;

  const [state, setState] = useState<PollState<T> & { target: string | null }>({
    target: null,
    data: null,
    error: null,
    polling: false,
  });

  const { initialMs, factor, maxMs } = timing;

  useEffect(() => {
    if (target === null) return;
    const schedule: PollTiming = { initialMs, factor, maxMs };
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;
    let failures = 0;

    setState({ target, data: null, error: null, polling: true });

    const tick = async () => {
      try {
        const value = await fetcherRef.current(target);
        if (cancelled) return;
        failures = 0;
        const done = isDoneRef.current(value);
        setState({ target, data: value, error: null, polling: !done });
        if (done) return;
      } catch (error) {
        if (cancelled) return;
        failures += 1;
        if (!isRetryable(error) || failures >= MAX_CONSECUTIVE_FAILURES) {
          setState((prev) => ({ ...prev, target, error, polling: false }));
          return;
        }
      }
      attempt += 1;
      timer = setTimeout(tick, pollDelay(attempt, schedule));
    };

    timer = setTimeout(tick, pollDelay(0, schedule));
    return () => {
      cancelled = true;
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [target, initialMs, factor, maxMs]);

  // State left over from an earlier target is never shown for a new one.
  if (target === null || state.target !== target) {
    return { data: null, error: null, polling: target !== null };
  }
  return { data: state.data, error: state.error, polling: state.polling };
}
