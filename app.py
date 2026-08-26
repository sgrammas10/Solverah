"""Solverah API entrypoint.

This module exists to hand a configured WSGI application to whatever is starting
it -- ``gunicorn app:app``, ``flask run``, or a test fixture.  It holds no
routes, no configuration, and no business logic.

Everything it used to hold now lives under ``solverah/``:

    solverah/factory.py       create_app(): Flask, ProxyFix, CORS, Talisman,
                              config, extensions, error handlers, health probes,
                              blueprint registration, legacy path aliases.
    solverah/api/v1/          the 38 route handlers, grouped by resource.
    solverah/services/        business logic; owns the transaction boundary.
    solverah/repositories/    every database query.
    solverah/domain/          pure rules: validation, merges, ranking, scoring.
    solverah/infra/           adapters: object storage, email, LLM providers.
    solverah/schemas/         pydantic request/response models.
    solverah/openapi.py       the OpenAPI 3.1 generator (docs/openapi.json).
    packages/ml/             deterministic resume parsing and culture scoring.

See docs/ARCHITECTURE.md Part 3 for the layering rules and Part 8 for where this
sits in the migration.

Every route is served at two paths for the duration of the frontend cutover: the
canonical ``/api/v1/...`` and the unversioned ``/api/...`` the deployed SPA still
calls.  They are the same endpoint and the same view function, not a redirect --
see ``register_legacy_aliases`` for why that distinction matters to a
CORS-preflighted POST and to rate-limit accounting.

Environment variables are read and validated by ``solverah/config.py``; run the
app with an incomplete environment and it logs every problem at CRITICAL in one
pass rather than failing on one variable per restart.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

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

__all__ = ["app", "create_app"]

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
