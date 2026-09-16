## Solverah Technical Planner

Full-stack web app: Python backend API + React/TypeScript frontend. Sprint planning and task management tool.

## Structure

```
backend/          # Python API
├── tests/        # pytest
├── models/       # Data models
└── routes/       # API endpoints

frontend/         # React + TypeScript
├── src/
│   ├── components/
│   ├── pages/
│   └── utils/
└── tests/        # Jest/React Testing Library
```

## Code Style

**Python backend:**
- Use type hints: `def get_user(user_id: int) -> User:`
- Keep functions brief if too complicated probably should be refactored into multiple functions

**React/TypeScript frontend:**
- Always type props: `interface MyComponentProps { ... }`
- Component + test file side-by-side

## Before Finishing Work

**Backend:**
- Run from repo root: `flask run`
- `pytest tests/` — run tests
- `mypy .` — type check (if set up)
- Test endpoint manually

**Frontend:**
- Run from repo root: `npm run dev` (or the appropriate npm command for the feature)
- `npm test` — run tests
- `npm run type-check` — TypeScript check
- Verify in browser, check console for errors

**Both:**
- Ask before committing to git
- Ask before pushing to main

## Workflow

- Ask before big changes
- If stuck: stop, re-plan, reach out early
- User-facing wording: make a best guess and ship it. Julie owns final copy and revises
  on the built product; never block a chunk on a copy read from Sebastian

## Testing

- Backend: at least one pytest per endpoint
- Frontend: **Vitest** + React Testing Library for components. `npm test` runs
  `vitest` (package.json). `jest`, `ts-jest` and `@types/jest` are still in
  devDependencies but nothing uses them — vestigial, don't write Jest config
  or reach for Jest-only APIs. Corrected 2026-09-16; this file said "Jest"
- Test: happy path, errors, edge cases
- Prefer real dependencies over mocks — only mock external services (APIs, databases)
- Every bug fix must include a regression test that fails without the fix
- Run the full test suite ONCE, at the end, before marking any task complete. Do not
  run a "baseline" pass first: HEAD's baseline is CI's result on that commit

**A green local suite is not a green CI suite.** `app.py` calls `load_dotenv()`, so a
developer with a populated `.env` gets `SOLVERAH_FORM_TOKEN_SECRET`, `OPENAI_API_KEY`,
`S3_*`, and the rest for free. CI sets only five variables (`APP_ENV`, `DATABASE_URL`,
`JWT_SECRET_KEY`, `JWT_COOKIE_SECURE`, `JWT_COOKIE_SAMESITE`) and has no `.env` at all.
A test that reaches code reading any other variable passes locally and fails on the
runner.

Before declaring a suite green, run it the way CI does — the app honors
`SOLVERAH_IGNORE_DOTENV` so nothing needs moving:

    SOLVERAH_IGNORE_DOTENV=1 pytest --tb=short -q

Two extra leaks that flag does NOT stop (each produced a false "CI-parity
verified" claim on 2026-09-03): this machine sets `JWT_SECRET_KEY` OS-wide,
so clear it explicitly when proving something works without it; and the
Flask CLI (`flask db ...`, `flask outbox ...`) loads `.env` itself BEFORE
app.py's guard — set `FLASK_SKIP_DOTENV=1` for any honest CLI run.

Build verification venvs OUTSIDE the repo (e.g. a sibling directory or the
session scratchpad). Guard tests walk the whole tree with rglob and a .venv
inside the repo fails them on third-party source — two agents have each
burned a full suite run rediscovering this.

Do NOT use the old `mv .env .env.off && pytest; mv .env.off .env` recipe: a
run killed between the two moves leaves `.env` gone, and everything that
reads it (S3, OpenAI, the form-token secret) silently breaks for whoever
uses this machine next. That happened on 2026-09-01; the flag can't.

Any test touching an assessment route needs the form-token secret supplied explicitly —
it is read at call time in `assessment_store.respondent_id_for_user` and has **no
default by design** (D-05):

    @pytest.fixture(autouse=True)
    def _form_token_secret(monkeypatch):
        monkeypatch.setenv("SOLVERAH_FORM_TOKEN_SECRET", "test-secret-not-a-real-one")

Do not move this into `tests/conftest.py`. `test_assessment_form.py` deliberately
deletes the variable to prove the no-default rule holds, and a suite-wide default would
make that test unable to fail.

## Agent Behavior

**Plan mode default:**
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately — don't keep pushing
- Write detailed specs upfront to reduce ambiguity

**Subagent strategy:**
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- One task per subagent for focused execution

**Self-improvement loop:**
- After ANY correction from the user: update CLAUDE.md with a rule to prevent the same mistake

**Verification before done:**
- Never mark a task complete without proving it works
- Ask yourself: "Would a staff engineer approve this?"

**Autonomous bug fixing:**
- When given a bug report: just fix it — point at logs, errors, failing tests, then resolve them

## Task Management

- Plan first: write plan with checkable items before coding
- Verify plan: check in with the user before starting implementation
- Track progress: mark items complete as you go
- Capture lessons: update CLAUDE.md after corrections

## Core Principles

- Simplicity first: minimal code impact
- No laziness: find root causes, no temporary fixes
- Minimal impact: only touch what's necessary
