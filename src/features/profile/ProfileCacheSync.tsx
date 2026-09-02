/**
 * ProfileCacheSync.tsx — the profile slice's reaction to auth announcements.
 *
 * `POST /auth/login` returns the profile document inside its user envelope
 * (SessionUser in solverah/schemas/auth.py). AuthProvider used to seed this
 * slice's query cache with it directly, which required auth to import
 * `seedProfileCache` — the auth ⇄ profile barrel cycle. The direction is now
 * inverted: auth announces the sign-in and what the envelope carried
 * (`onAuthEvent`), and this component — mounted once by the app layer, inside
 * both providers — writes the document into the cache. Dropping the boot-time
 * profile fetch therefore still does not simply move that request one screen
 * later: a fresh sign-in has the document before anything asks for it.
 *
 * The truthiness guard is load-bearing and its reasoning came across with it:
 * OTP sign-in returns the summary user, which carries no profileData, and
 * `undefined` means "the envelope had no document", never "the document is
 * empty". Seeding it would pin an empty document into the cache as *resolved*,
 * suppressing the first real fetch for the whole staleTime window — consumers
 * that branch on the document (FocusTypeResultsPage, PathIntelligencePage)
 * would navigate away from results that exist on the server. The password
 * envelope does carry the field today; correctness here must not depend on it
 * continuing to.
 *
 * Logout needs no listener: AuthProvider clears the entire query cache itself,
 * which is slice-agnostic and covers this slice's document too.
 */
import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { onAuthEvent } from "../auth";
import { seedProfileCache } from "./useProfile";

export function ProfileCacheSync() {
  const queryClient = useQueryClient();

  useEffect(
    () =>
      onAuthEvent((event) => {
        if (event.type === "signed-in" && event.profileData) {
          seedProfileCache(queryClient, event.profileData);
        }
      }),
    [queryClient],
  );

  return null;
}
