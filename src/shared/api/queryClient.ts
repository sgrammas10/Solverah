/**
 * queryClient.ts — the app's single TanStack Query client and its defaults.
 *
 * Phase 4a moves ownership of cached server state out of AuthContext. Before
 * this, the only cache the client had was the `User` object in AuthProvider
 * state: a component that wanted the profile document either read it off `user`
 * — which is why the boot path had to fetch it — or called `fetchProfileData()`
 * and kept its own copy in `useState`. Neither de-duplicates, neither
 * invalidates, and the first one put a request on the critical path of every
 * page load for data the app shell does not render (P0-3).
 *
 * The transport is unchanged. `fetchWithAuth` still issues every request, still
 * attaches the CSRF token, still parses errors through `parseApiError`. What
 * changes is who holds the result.
 *
 * Retry policy is the reason this file exists rather than an inline
 * `new QueryClient()`. `parseApiError` already classifies failures — an
 * `ApiError` carries a real `status` and knows whether retrying is reasonable —
 * so the defaults below branch on that instead of blindly retrying three times.
 * Retrying a 401 or a 422 cannot succeed: the session is gone or the input is
 * wrong, and three attempts only delay the error the user needs to see.
 */
import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "./apiError";

/** Attempts after the first, for failures that can plausibly succeed later. */
const MAX_RETRIES = 2;

/**
 * How long a fetched result is served without a background refetch.
 *
 * One minute rather than zero: the profile document changes only when this user
 * edits it, and every path that edits it writes through the cache. The window
 * exists to collapse the burst of mounts that a route change produces, not to
 * hide staleness.
 */
const DEFAULT_STALE_TIME_MS = 60_000;

/**
 * Whether a failed query is worth retrying.
 *
 * `ApiError.isRetryable` is the existing classification — 429, 5xx, or a
 * network failure that never reached the server (status 0). Anything else is a
 * client error the caller has to fix, so it surfaces immediately.
 *
 * A non-`ApiError` reaching here means the failure happened outside
 * `fetchWithAuth` (a thrown `TypeError` from an offline fetch, say). Those are
 * retried, because the request never got a verdict from the server.
 */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= MAX_RETRIES) return false;
  if (error instanceof ApiError) return error.isRetryable;
  return true;
}

/**
 * Build the client.
 *
 * A factory rather than a module-level singleton so tests can create an
 * isolated client per case; `App.tsx` makes exactly one for the app.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: DEFAULT_STALE_TIME_MS,
        retry: shouldRetry,
        // The app has never refetched on focus, and turning it on here would be
        // a behaviour change smuggled in under a caching change.
        refetchOnWindowFocus: false,
      },
      mutations: {
        // A retried PATCH is a second write. `/me/profile` merges rather than
        // replaces, so a duplicate is not corrupting, but the caller — not a
        // default — should decide to send one twice.
        retry: false,
      },
    },
  });
}
