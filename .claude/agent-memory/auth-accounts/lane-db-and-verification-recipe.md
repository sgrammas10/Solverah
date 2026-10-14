---
name: lane-db-and-verification-recipe
description: Working pytest invocation for the auth cluster (solverah_fx_auth on 5433, venv311, env -u JWT_SECRET_KEY) and the frontend commands; during a multi-lane wave, type-check and full vitest failures in other lanes' modified files are theirs
metadata:
  type: reference
---

Backend cluster, from Git Bash (worked 2026-10-02, 165 passed in ~4 min including `test_frontend_contract.py` and `test_schema_conformance.py`):

`cd "/c/Users/Sebastian Grammas/Desktop/Solverah" && env -u JWT_SECRET_KEY PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 SOLVERAH_IGNORE_DOTENV=1 APP_ENV=testing DATABASE_URL=postgresql://solverah:solverah@localhost:5433/solverah_fx_auth JWT_SECRET_KEY=test-jwt-secret-not-a-real-one-32-bytes-min JWT_COOKIE_SECURE=false JWT_COOKIE_SAMESITE=Lax "/c/Users/Sebastian Grammas/Desktop/solverah-venv311/Scripts/python" -m pytest -p no:cacheprovider --tb=short -q <files>`

`solverah_fx_auth` is the auth lane's fix-wave DB (the lane file's `solverah_auth` is the standing one). Frontend, PowerShell: prepend `C:\Users\Sebastian Grammas\AppData\Roaming\fnm\node-versions\v22.13.1\installation;` to PATH, then `npm test -- --run src/features/auth` and `npm run type-check`.

**How to apply:** in a parallel wave, check `git status` first; a `tsc -b` error or vitest failure inside a file another lane has modified is theirs to report, not yours to fix. Always run the new tests once BEFORE wiring the fix so the report can say they fail without it.
