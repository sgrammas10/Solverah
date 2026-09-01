"""Celery worker entrypoint.

    celery -A solverah.worker:celery_app worker \
        --queues=default,llm,email,scoring,maintenance --concurrency=4

This is to the worker what ``app.py`` is to the web process: it builds the
application and hands the configured object to whatever is starting it.  It
holds no tasks -- those are in ``solverah/tasks/`` -- and no configuration.

It imports ``solverah.factory`` rather than ``app``, which is not a stylistic
choice: ``tests/test_layering.py`` asserts that nothing under ``solverah/``
imports ``app``, and the reason is the cycle that used to exist when helpers
lived in the entrypoint.  The one thing this file needs from ``app.py`` is
``load_dotenv()``, so it does that itself, guarded by the same variable, so that
`SOLVERAH_IGNORE_DOTENV=1` means the same thing to a worker as it does to the API.

**Queues are named on the command line, not here.**  Splitting them is what lets
the slow ones be scaled independently -- a fleet of `llm` workers at concurrency
1 alongside two `email` workers that answer in milliseconds -- and a default that
subscribed to all five would make that a code change rather than a deploy
argument.  ``infra/docker/compose.yml`` runs one worker on all five, which is
right for a laptop and wrong for production.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from solverah.config import is_truthy

#: Same flag ``app.py`` reads, for the same reason: CI has no `.env`, so work
#: that only runs because a developer's `.env` supplied a variable must be able
#: to fail here the way it fails there.
IGNORE_DOTENV_VAR = "SOLVERAH_IGNORE_DOTENV"

if not is_truthy(os.environ.get(IGNORE_DOTENV_VAR)):
    load_dotenv()

from solverah.factory import create_app  # noqa: E402  -- must follow load_dotenv
from solverah.infra.queue import celery_app  # noqa: E402  -- same

__all__ = ["celery_app", "flask_app"]

#: The application every task runs inside. ``create_app`` calls ``init_celery``,
#: which is what points ``celery_app`` at this deployment's broker and registers
#: the tasks -- so importing this module is enough to have a usable worker.
flask_app = create_app()
