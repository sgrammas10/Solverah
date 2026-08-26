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

## Testing

- Backend: at least one pytest per endpoint
- Frontend: Jest/React Testing Library for components
- Test: happy path, errors, edge cases
- Prefer real dependencies over mocks — only mock external services (APIs, databases)
- Every bug fix must include a regression test that fails without the fix
- Run the full test suite before marking any task complete

**A green local suite is not a green CI suite.** `app.py` calls `load_dotenv()`, so a
developer with a populated `.env` gets `SOLVERAH_FORM_TOKEN_SECRET`, `OPENAI_API_KEY`,
`S3_*`, and the rest for free. CI sets only five variables (`APP_ENV`, `DATABASE_URL`,
`JWT_SECRET_KEY`, `JWT_COOKIE_SECURE`, `JWT_COOKIE_SAMESITE`) and has no `.env` at all.
A test that reaches code reading any other variable passes locally and fails on the
runner.

Before declaring a suite green, run it the way CI does:

    mv .env .env.off && pytest --tb=short -q; mv .env.off .env

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
