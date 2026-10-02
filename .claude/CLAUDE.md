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
- A session has a lane; stay in it. When Sebastian asks "what else can we work on"
  mid-task, the answer comes from the SAME lane the session is already in (on
  2026-09-17 a model-lane session was offered a frontend signup bug and told "we are
  only working on the model here"). Other lanes have their own chats. Name
  cross-lane items only if they BLOCK the lane in hand. The orchestrator session is
  the one exception: it works across lanes by design (see Orchestration below)
- When a built-in check fires, test the check before the data. On 2026-09-17 the
  priors form's "repeated question" came back 3/10 vs 8/10 and the report led with
  "her numbers are too noisy to adopt" — but the two vignettes were not the same
  question (one person NEEDS a fast pace, the other merely tolerates it), which
  Sebastian caught on a read. A check that disagrees with an expert is first a
  claim about the check: put the two items side by side and confirm they are
  equivalent BEFORE drawing any conclusion about the respondent, and never
  relegate that doubt to a caveat under the opposite headline

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
- Lane work follows the Orchestration section below

**Self-improvement loop:**
- After ANY correction from the user: update CLAUDE.md with a rule to prevent the same mistake

**Verification before done:**
- Never mark a task complete without proving it works
- Ask yourself: "Would a staff engineer approve this?"

**Autonomous bug fixing:**
- When given a bug report: just fix it — point at logs, errors, failing tests, then resolve them

## Orchestration (adopted 2026-10-02)

One orchestrator, many lane workers. The orchestrator is the **main session**, never an
agent file: subagents cannot spawn subagents, so only the main session can fan work out.
The lane agents in `.claude/agents/` are specialist workers. Each owns a set of files and
carries its lane's traps.

**Routing.** The routing table, the contended-file splits, and the model and effort
tables live in one place: `.claude/agents/dispatcher.md`. The orchestrator reads that file
directly instead of calling the dispatcher agent and relaying its answer. The dispatcher
agent stays available for a lane chat that wants a quick routing answer.

**Pick the shape by how many lanes the task touches:**
- **Small fix, two files or fewer, no shared invariant**: the orchestrator does it itself.
  Starting an agent costs more than the fix.
- **One lane**: dispatch that lane's agent directly (ruling 2026-09-29: "just give it to
  an agent urself"), then report its result briefly.
- **Two or more lanes**: write the plan first (lanes, order, what each hands the next,
  who reviews). Show it to Sebastian once, then dispatch on his go. Run lanes in parallel
  only when their file sets are disjoint. Worktree isolation is refused in this repo, so
  file ownership is the only thing keeping parallel agents apart.
- **A refactor that must prove the wire did not change**: dispatch backend-platform to
  capture the contract baseline BEFORE the feature lane starts. The window closes once
  the change lands.

**Briefs.** A lane agent starts with no context and cannot ask a question mid-task. Each
brief names the goal, the files in scope, what is already decided, the traps for this
task, whether to run the full suite or the cluster only, and what to report back. Pass the
model through the Agent tool's `model` parameter, chosen from the dispatcher's model table
and the Fable calibration: Fable only when the agent must make judgment calls the brief
cannot pre-make. Effort comes from the agent's frontmatter and cannot be set per dispatch,
so state the verification depth in the brief instead.

**The orchestrator owns:**
- Sequencing, and the joins between lanes.
- The one full CI-style suite run at the end of a multi-lane task. Workers run their
  clusters only.
- Reading each worker's diff before calling it done. A worker's "done" is a claim, not proof.
- Asking Sebastian before any commit. Workers never commit.

**Worker rules.** Every lane agent follows these when the orchestrator dispatched it. Where
they differ from that lane's definition of done, these win.
1. Do exactly the brief. Work you find in another lane is reported, not done.
2. If blocked on a decision only Sebastian or Julie can make, stop and report the question
   along with what you finished. Copy is still best-guess-and-ship.
3. Run your cluster's tests. Run the full suite only if the brief says so.
4. Never commit, never push.
5. Your final message is all the orchestrator sees. Report the files you changed, the tests
   you ran and their result, every shared file you touched (see the table below) so it can
   be reviewed, anything the next lane needs, and open questions.
6. Your lane file's "After every task" memory update still applies.

**Shared files: the feature lane edits, the infrastructure lane reviews.**

| Shared file | Feature lane may | Reviewer |
|---|---|---|
| `model.py` | edit classes in its own section; write its own migration | schema-steward |
| `App.tsx` | add its own route line and lazy import inside the existing public, `RedirectIfAuthenticated`, or `RequireAuth` block | frontend-shell |
| `docs/openapi.json`, `schema.ts` | regenerate with `python -m solverah.openapi`, then `npm run generate:api` | backend-platform |
| `solverah/api/v1/__init__.py` | register its own blueprint | backend-platform |

Structural edits to these files stay with the infrastructure lane: new layout routes,
guards, cross-section model changes, the generators, and the contract baseline. The
orchestrator dispatches the reviewer after the feature lane finishes. The reviewer reports
findings and does not rewrite. `account_service` is NOT on this list: a new user-keyed
table still goes to auth-accounts.

**Lane count.** Fifteen lanes is the ceiling. Do not split a lane or add one. If tasks keep
needing the same three or more lanes together, propose merging those lanes to Sebastian.

## Task Management

- Plan first: write plan with checkable items before coding
- Verify plan: check in with the user before starting implementation
- Track progress: mark items complete as you go
- Capture lessons: update CLAUDE.md after corrections

## Core Principles

- Simplicity first: minimal code impact
- No laziness: find root causes, no temporary fixes
- Minimal impact: only touch what's necessary
