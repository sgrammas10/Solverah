---
name: hero-form-gaps-g26-g31
description: State of G26/G29/G30/G31 (hero intake form + account modal + early-access route), decisions made, and copy awaiting Julie
metadata:
  type: project
---

The four gaps were fixed in code on 2026-11-23 and left UNCOMMITTED for the orchestrator. All four were confirmed against source before the fix. G26 was also confirmed in jsdom, which applies constraint validation: an empty submit on HEAD never reached handleSubmit.

Decisions (best-guess, not ruled by Sebastian):
- G26: the form is `noValidate`. The link fields are `type=text inputMode=url`. A bare or `http://` link is upgraded to `https://` and sent as the parsed `href`, so the host goes out lowercased because the server compares LinkedIn hosts exactly. A client-side email shape check replaces the browser's check.
- G29: after a `sign_in` claim, the hook probes `/auth/session` to get the full flags, then calls `loginWithData` (passed in from LandingPage). If the probe fails it falls back to the claim's summary user. Every way out of the success step (Continue, X, backdrop, Escape) navigates to `/job-seeker/dashboard`. A 403 from the claim offers "Resend verification code", which goes to `/verify-email`.
- G30: `passwordProblem()` copies `validators.validate_password` (same order, same wording). A hint line sits under "Create a password".
- G31: the route, service function, schema and three test_route_surface tests are removed. The outbox topic `email.early_access` and `email.send_early_access_modal_notification` were LEFT in place (they belong to ops-crons and backend-platform, and queued prod rows may still exist).

**Why:** see [[size-gate-headroom]] for the lazy-modal side effect of this work.

**How to apply:** copy awaiting Julie: "Resend verification code", the password hint, "Please enter a valid email address.", and the LinkedIn and portfolio link messages. One gap is still open: after the 403 path's verify, ConfirmEmail sends the visitor to /login, and their hero submission is NEVER attached to the account.
