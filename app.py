"""Solverah API entrypoint.

This module exists to hand a configured WSGI application to whatever is starting
it -- ``gunicorn app:app``, ``flask run``, or a test fixture.  It holds no
routes, no configuration, and no business logic.

Everything it used to hold now lives under ``solverah/``:

    solverah/factory.py       create_app(): Flask, ProxyFix, CORS, Talisman,
                              config, extensions, error handlers, health probes,
                              blueprint registration.
    solverah/api/v1/          every route handler, grouped by resource.
    solverah/services/        business logic; owns the transaction boundary.
    solverah/repositories/    every database query.
    solverah/domain/          pure rules: validation, merges, ranking, scoring.
    solverah/infra/           adapters: object storage, email, LLM providers.
    solverah/schemas/         pydantic request/response models.
    solverah/openapi.py       the OpenAPI 3.1 generator (docs/openapi.json).
    packages/ml/             deterministic resume parsing and culture scoring.

See docs/ARCHITECTURE.md Part 3 for the layering rules and Part 8 for where this
sits in the migration.

Every route is served at ``/api/v1/...`` and nowhere else.  Phase 1a served each
one at an unversioned ``/api/...`` alias as well so the deployed SPA kept working
while the versioned paths became canonical; Phase 1b cut the frontend over and
removed them.  ``tests/test_v1_aliasing.py`` asserts they are gone rather than
assuming it.

Environment variables are read and validated by ``solverah/config.py``; run the
app with an incomplete environment and it logs every problem at CRITICAL in one
pass rather than failing on one variable per restart.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# `solverah.config` is stdlib-only and imports nothing from this package, so it
# is safe to read before .env is loaded. Importing anything else first would
# not be: `solverah.infra.email` reads RESEND_API_KEY at module scope, so the
# whole factory import below has to happen after load_dotenv().
from solverah.config import is_truthy

#: Set to 1/true/yes/on to skip loading `.env`.
#:
#: `.env` is a developer convenience, and it is one that hides bugs. CI sets
#: exactly five variables and has no `.env` file, so a test that reaches code
#: reading any other variable passes on a developer machine -- where `.env`
#: silently supplies it -- and fails on the runner. That is not hypothetical:
#: it is how `SOLVERAH_FORM_TOKEN_SECRET` got into a test that looked green
#: locally and 500'd in CI.
#:
#: `make test-ci` sets this, which is what makes that target an honest
#: reproduction of the runner rather than an approximation of it.
#:
#: Production never sets it: unset means load `.env` if present, which is the
#: behaviour this has always had. A deployment has real environment variables
#: and no `.env`, so the flag is irrelevant there either way.
IGNORE_DOTENV_VAR = "SOLVERAH_IGNORE_DOTENV"

if not is_truthy(os.environ.get(IGNORE_DOTENV_VAR)):
    load_dotenv()

# Re-exported for the tests that address them by name, and because
# `_parse_bool_env` is used below. The underscore prefixes are preserved from
# when these lived here; they are factory internals, not app.py's own API.
from solverah.factory import (  # noqa: E402
    _apply_proxy_fix,
    _is_production,
    _parse_bool_env,
    _resolve_trusted_proxy_count,
    create_app,
)

__all__ = ["IGNORE_DOTENV_VAR", "app", "create_app"]

#: The application. `gunicorn app:app`, `flask run`, and every test fixture
#: address this name, so it stays module-level even though the factory is the
#: real entry point.
app = create_app()


if __name__ == "__main__":
    # The Werkzeug debugger exposes an interactive console that executes
    # arbitrary code on any traceback, so it is opt-in via FLASK_DEBUG and
    # bound to loopback rather than on by default.
    app.run(
        debug=_parse_bool_env(os.environ.get("FLASK_DEBUG"), False),
        host="127.0.0.1",
    )
