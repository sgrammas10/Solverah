/**
 * sessionHint.ts — the one bit this browser keeps about whether it has had a
 * session, and the two readers that want it.
 *
 * Not a credential and not a claim to be signed in — the refresh cookie is
 * HttpOnly and cross-origin, so nothing on this page can read or forge its way
 * to a session. All this decides is whether a boot-time wait is worth spending:
 *
 *   AuthProvider — present means "a 401 on the probe is worth one refresh",
 *     absent means "this visitor has never signed in here, do not ask". An
 *     anonymous landing page is the highest-volume boot in the product and it
 *     has no refresh cookie to exchange, so without the gate every visitor
 *     would spend a second request on a guaranteed 401 — against a
 *     rate-limited endpoint.
 *
 *   RedirectIfAuthenticated — the gate on "/", /login and /register holds a
 *     returning visitor behind a skeleton while the probe is out rather than
 *     flashing the landing page at them, and for the same reason as above
 *     never makes a first-time visitor wait.
 *
 * Forging it costs the forger one extra 401. Losing it (private window, cleared
 * site data) costs a returning user one sign-in. Both are the right failure.
 *
 * Its own module, rather than an export off AuthContext.tsx, so that file keeps
 * exporting only a component and Fast Refresh keeps working on it.
 */
const SESSION_HINT_KEY = "solverah.hasSession";

export function hasHadSession(): boolean {
  try {
    return globalThis.localStorage?.getItem(SESSION_HINT_KEY) === "1";
  } catch {
    // Safari in private mode, and any browser configured to block site data,
    // throws on access rather than returning null. A visitor whose storage is
    // unreadable simply signs in again.
    return false;
  }
}

export function rememberSession(remembered: boolean): void {
  try {
    if (remembered) globalThis.localStorage?.setItem(SESSION_HINT_KEY, "1");
    else globalThis.localStorage?.removeItem(SESSION_HINT_KEY);
  } catch {
    // See hasHadSession: unreadable storage is not a reason to fail a sign-in.
  }
}
