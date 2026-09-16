/**
 * RedirectIfAuthenticated.tsx — the entry-surface gate, the mirror of
 * RequireAuth for the three screens a signed-in user has no business on:
 * "/", /login and /register.
 *
 * Why it exists. The landing page renders its own LandingNav and reads no auth
 * state at all, and /login and /register never asked who was visiting. A
 * returning user whose session the boot probe had just restored therefore saw
 * a signed-out landing page, clicked "Sign In", and got a sign-in form under a
 * global Header that showed their name, the settings gear and a logout button.
 * The session was fine the whole time; the pages just never looked.
 *
 * What it does, in the same three-way shape as RequireAuth so the two read
 * together:
 *
 *   1. Session known and signed in → redirect to the dashboard.
 *   2. Probe still in flight and this browser has had a session before
 *      (`hasHadSession`) → hold the page back behind the RouteFallback
 *      skeleton. This is the returning visitor: drawing the landing page for
 *      them and then yanking it away is the flash this branch prevents.
 *   3. Otherwise → render the page. An anonymous first visit (no hint) never
 *      waits on `GET /auth/session`: the landing page is the highest-volume
 *      boot in the product and ARCHITECTURE.md 6.3 keeps it off the probe.
 *
 * The verdict is taken ONCE, the first time the session is known, and kept for
 * the life of this boundary. That is what makes it safe to wrap /login: without
 * it, the `setUser` from a sign-in completed on the page would trip the
 * redirect and unmount Login mid-`onSuccess`, pre-empting its own navigation
 * (the return-to-origin `from`, the pending-quiz `/quiz-insights` path). A
 * session that appears while the probe is still in flight can only be such an
 * explicit sign-in — the boot probe sets `user` and clears `sessionLoading` in
 * one batched render — so that case is "page" as well.
 *
 * Where the redirect goes is keyed by role. A role the map does not know
 * renders the page instead: RequireAuth bounces a wrong-role user to "/", and
 * an unconditional redirect here would turn that bounce into a loop.
 *
 * Two flows navigate to "/" as a session ENDS, and both must clear the session
 * before they arrive or this gate sends them to the dashboard instead: the
 * Header awaits `logout()` before navigating, and account deletion calls
 * `navigate("/")` and `clearSessionLocally()` in the same synchronous block so
 * React renders the two updates together.
 */
import { useRef } from "react";
import { Navigate, Outlet } from "react-router-dom";

import { useAuth } from "../features/auth/useAuth";
import { hasHadSession } from "../features/auth/sessionHint";
import { RouteFallback } from "./RouteFallback";

/** Where a signed-in visitor belongs instead of the entry surface, by role. */
const HOME_BY_ROLE: Readonly<Record<string, string>> = {
  "job-seeker": "/job-seeker/dashboard",
};

type Verdict = { kind: "home"; to: string } | { kind: "page" };

export function RedirectIfAuthenticated() {
  const { user, sessionLoading } = useAuth();

  // A ref, written during render: the latch below is idempotent for a given
  // (user, sessionLoading), so a repeated render computes the same verdict,
  // and a ref avoids the extra render pass a setState-during-render would add.
  const verdict = useRef<Verdict | null>(null);

  if (verdict.current === null) {
    if (!sessionLoading) {
      const to = user ? HOME_BY_ROLE[user.role] : undefined;
      verdict.current = to ? { kind: "home", to } : { kind: "page" };
    } else if (user) {
      // Signed in while the boot probe is still out: an explicit sign-in on
      // this page beat the probe. The page owns the navigation from here.
      verdict.current = { kind: "page" };
    }
  }

  const decided = verdict.current;
  if (decided?.kind === "home") return <Navigate to={decided.to} replace />;
  if (decided === null && hasHadSession()) return <RouteFallback />;

  return <Outlet />;
}

export default RedirectIfAuthenticated;
