---
name: first-run-career-moment
description: 2026-11-24 first-run dialog (career moment + own words) on the dashboard; PATCH /me/onboarding; migration 20261124_profile_onboarding; decisions and open threads
metadata:
  type: project
---

Built 2026-11-24 (uncommitted at hand-back): "What brings you here?" (6 moments, follow-up "Are you working right now?") and the optional "In your own words" step, as `CareerMomentDialog` on JobSeekerDashboard.

Decisions, and why:
- `career_moment` and `own_words` are profile document SCALAR_COLUMNS. That buys three things: export carries them through `load_document`, the deletion tombstone nulls them, and `update_document` invalidates the dashboard cache. Neither key is in `validators.ALLOWED_PROFILE_FIELDS`, so PATCH /me/profile can't touch them.
- `GET /me/profile` only carries the keys once they are set, because assemble drops None scalars. The dashboard is the place that sends an explicit null (`careerMoment`, plus `careerStatus` for the follow-up skip).
- The dialog opens only on `careerMoment === null`. An undefined value (an older backend, or a pre-deploy Redis entry) opens nothing. **Why:** Julie tests live against an old backend.
- A latch ref keeps the dialog open after step 1's dashboard refetch. The same ref stops the intake modal for the rest of that visit.
- `profile_service._write_status_fields` is now the shared write behind both set_career_status and save_onboarding. It drops the path caches only when career_status is written.
- I added 400s the brief didn't name: `status_conflicts_with_moment`, `no_fields`, `invalid_own_words`.

Open threads:
- Sebastian has to run the migration on `solverah_julie` and restart her 5055 backend before Julie sees the dialog.
- Every existing user has a NULL moment, so they all get the dialog once after deploy.
- Not browser-verified: Playwright MCP was down, and 5055/5188 belong to Julie.
- Out of scope, still to do: showing own_words back; Environment Report wording that depends on the moment.
- Lane DBs: `solverah_onb` (pytest), `solverah_onb_mig` (alembic chain proof; keep away from pytest).
