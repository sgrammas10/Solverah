/**
 * authEvents.ts — what the auth slice announces, for other slices to react to.
 *
 * This is the inverted half of what used to be a direct call: AuthProvider
 * imported `seedProfileCache` from the profile slice so login could warm the
 * profile cache, which made auth and profile barrels dependencies of each other.
 * Rollup flagged the cycle on every build ("will likely lead to broken
 * execution order"), and the Phase 4 report named its death the natural end
 * state of the 4a split.
 *
 * The inversion: auth states what happened — a sign-in, and what the login
 * envelope carried — and interested slices subscribe. Auth knows nothing about
 * who listens or what they do with it. Today the one listener is the profile
 * slice's `ProfileCacheSync`, which seeds the profile query cache from the
 * login envelope's document.
 *
 * Sign-OUT is deliberately not an event: logout's cache hygiene is
 * slice-agnostic (every cached query belongs to the session that just ended),
 * so AuthProvider clears the whole query cache itself and needs no listener
 * for it.
 */
import type { ProfileData, User } from "./authContext";

export type AuthEvent = {
  type: "signed-in";
  user: User;
  /**
   * The profile document the login envelope carried, if it carried one.
   * `POST /auth/login` folds `profileData` into its user object (the wire is
   * unchanged and deliberately so — Appendix B); OTP sign-in returns the
   * summary user, which carries none. Absent means "the envelope had no
   * document", never "the document is empty".
   */
  profileData?: ProfileData;
};

type Listener = (event: AuthEvent) => void;

const listeners = new Set<Listener>();

/** Subscribe to auth announcements. Returns the unsubscribe function. */
export function onAuthEvent(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * Announce an auth event. Internal to the auth slice — only AuthProvider's
 * login paths call this; it is not part of the barrel's public surface.
 */
export function emitAuthEvent(event: AuthEvent): void {
  // Copied so a listener that unsubscribes (or subscribes) mid-dispatch cannot
  // change who this particular event reaches.
  for (const listener of [...listeners]) {
    listener(event);
  }
}
