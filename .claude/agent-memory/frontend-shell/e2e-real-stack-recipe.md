---
name: e2e-real-stack-recipe
description: How real_stack.spec.ts and feature_tour.spec.ts actually run on this machine (Flask on 5055 + VITE_API_URL, solverah_e2e on 5433); worked 2026-10-14
metadata:
  type: reference
---

The spec headers say "Flask on :5000"; ignore that (a stale server can hold :5000, see
the user-level stale-Flask memory). What worked on 2026-10-14:

- DB: `solverah_e2e` on localhost:5433 (user/pass solverah/solverah). It is NOT kept at
  head: on 2026-10-14 it was at 20260916_path_fb and had to be `flask db upgrade`d to
  20261013_pulse_company_link first. Check `alembic_version` before a run.
- API: venv `Desktop/solverah-venv311`, env `FLASK_SKIP_DOTENV=1 SOLVERAH_IGNORE_DOTENV=1
  APP_ENV=development DATABASE_URL=...solverah_e2e JWT_SECRET_KEY=<any> JWT_COOKIE_SECURE=false
  SOLVERAH_FORM_TOKEN_SECRET=<any> FLASK_APP=app.py`, then `python -m flask run --port 5055 --no-reload`.
  CORS already allows any `http://localhost:<port>`.
- Browser side: `CI= VITE_API_URL=http://localhost:5055 npx playwright test tests/e2e/real_stack.spec.ts tests/e2e/feature_tour.spec.ts`.
  Playwright's webServer rebuilds dist with that env, so rebuild with the default env
  afterwards before `npm run size` or a preview.
- Chromium is already installed under AppData/Local/ms-playwright. Playwright MCP may be
  down; the repo's own Playwright works.
- After stopping the background Flask, confirm :5055 is free (TaskStop can leave the child).

smoke.spec.ts needs none of this: it is fully stubbed by `tests/e2e/fixtures/api.ts`, and
its `api.unhandled` drift check goes red whenever a lane adds a call on the dashboard or
Work Pulse path. See [[e2e-stub-drift]].
