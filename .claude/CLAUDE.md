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
- Keep functions under 50 lines
- Follow PEP 8
- Descriptive variable names

**React/TypeScript frontend:**
- Always type props: `interface MyComponentProps { ... }`
- Functional components with hooks
- One responsibility per component
- Component + test file side-by-side

## Before Finishing Work

**Backend:**
- backend can be run from root repo using flask run locally
- `pytest tests/` — run tests
- `mypy .` — type check (if set up)
- Test endpoint manually

**Frontend:**
- frontend can be run from root repo using npm run dev or whatever npm command is best for the specific feature u r testing locally
- `npm test` — run tests
- `npm run type-check` — TypeScript check
- Verify in browser
- Check console for errors

**Both:**
- Clear, descriptive commit message
- Ask before pushing to main

## Workflow

- Ask before big changes
- Keep code simple — no over-engineering
- Early returns over nested conditionals
- Minimal/clear comments (why, not what)
- Small, focused functions
- Ask before committing to git
- Prefer editing existing files over new ones
- If stuck: stop, re-plan, reach out early

## Testing

New code needs tests.
- Backend: at least one pytest per endpoint
- Frontend: Jest/React Testing Library for components
- Test: happy path, errors, edge cases
- Don't test: external library behavior
