/**
 * RequireAuth.tsx — the session gate, at the route boundary (ARCHITECTURE.md 6.3).
 *
 * This is ProtectedRoute evolved, not a rival to it. ProtectedRoute checked
 * `user` and nothing else, which was sound only because AuthProvider held the
 * ENTIRE tree behind a full-screen spinner until the session probe resolved.
 * Retiring that gate moved the waiting here: routing renders immediately,
 * public routes never wait on `GET /auth/session`, and only the subtree behind
 * this boundary holds back until the probe has answered.
 *
 * The order of the three checks is the contract:
 *
 *   1. Probe still in flight → render the in-shell skeleton. Rendering the
 *      protected content here would flash it at a visitor who turns out to be
 *      signed out; redirecting here would bounce a signed-in user to /login on
 *      every hard refresh of a protected screen. Both are wrong, so neither
 *      happens until the session is known. RequireAuth.test.tsx is the test
 *      that fails if either comes back.
 *   2. No session → redirect to SIGN_IN_ROUTE.
 *   3. Session, wrong role → redirect to "/", exactly as ProtectedRoute did.
 *
 * Used as a layout route: `<Route element={<RequireAuth allowedRoles={...}/>}>`
 * with the guarded routes as children, per the 6.3 sketch. The skeleton is the
 * same `RouteFallback` the route-level Suspense uses — to the user, "waiting
 * for the session" and "waiting for the chunk" are the same wait, in the same
 * place, under a Header that already works.
 *
 * Return-to-origin after login: the sign-in redirect carries the intercepted
 * location as `state={{ from: location }}`, and the Login page reads that state
 * to override its post-login redirect. The state is client-forgeable
 * (history.pushState), so Login — not this gate — is the side that validates it
 * before navigating. The role check below still runs when the user returns, so
 * a return to a role-forbidden path gets the normal wrong-role redirect to "/",
 * never a loop back to sign-in.
 */
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../features/auth/useAuth";
import { RouteFallback } from "./RouteFallback";

/** Where an unauthenticated visitor is sent. One constant on purpose — it is
 *  the single place a return-to-origin implementation would decorate. */
export const SIGN_IN_ROUTE = "/login";

export function RequireAuth({ allowedRoles }: { allowedRoles: string[] }) {
  const { user, sessionLoading } = useAuth();
  const location = useLocation();

  if (sessionLoading) return <RouteFallback />;
  if (!user) return <Navigate to={SIGN_IN_ROUTE} replace state={{ from: location }} />;
  if (!allowedRoles.includes(user.role)) return <Navigate to="/" replace />;

  return <Outlet />;
}

export default RequireAuth;
