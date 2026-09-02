/**
 * Public surface of the auth slice — the only legal import path for other
 * feature slices (ARCHITECTURE.md 6.4).
 *
 * The auth route pages are NOT exported here: they are consumed only by the
 * app layer (src/app), which deep-imports by design — route-level lazy() must
 * reach the component module directly so a barrel never sits inside a chunk
 * boundary. `AuthProvider` is exported for other slices' tests, which wrap
 * their render trees in the real provider.
 */
export { useAuth } from "./useAuth";
// What auth announces (a sign-in, and what the login envelope carried), for
// other slices to react to. Subscribe-only on purpose: emitting is the auth
// slice's own business, so `emitAuthEvent` is not re-exported here.
export { onAuthEvent } from "./authEvents";
export type { AuthEvent } from "./authEvents";
// Explicit .tsx: this directory also holds authContext.ts, and on a
// case-insensitive filesystem an extensionless "./AuthContext" resolves to
// authContext.ts (the .ts candidate is tried before .tsx). Same reason
// App.tsx imports the provider with its extension spelled out.
export { AuthProvider } from "./AuthContext.tsx";
export type {
  AuthContextType,
  ProfileData,
  SessionResponse,
  User,
} from "./authContext";
