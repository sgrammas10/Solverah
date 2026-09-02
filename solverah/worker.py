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
import sys
from pathlib import Path

#: The repository root, put on ``sys.path`` before anything else is imported.
#:
#: **Without this a worker can start cleanly and then fail every task that
#: reaches a scorer**, which is the shape of failure this is here to prevent.
#:
#: ``celery`` is an installed console script, so ``sys.path[0]`` is
#: ``/usr/local/bin`` rather than the working directory -- the repository root is
#: not on the path at all. Celery still finds *this* module, because it resolves
#: ``--app`` through ``celery.utils.imports.import_from_cwd``, which adds the
#: working directory for the duration of that one import and then removes it
#: again. So every module imported while this file is being imported resolves
#: and lands in ``sys.modules``, and the worker boots looking entirely healthy.
#:
#: What does not resolve is the imports the services make *lazily, inside
#: functions* -- ``work_pulse``, ``manager_match``, ``focus_type``,
#: ``assessment_store`` and ``backend.services.*`` are all top-level modules at
#: the repository root imported at call time. Those run long after the working
#: directory has left the path, and they raise ``ModuleNotFoundError`` in the
#: task rather than at boot.
#:
#: Found by running a real job through the compose worker (Phase 3b): the job
#: was claimed, failed, and written terminal correctly -- the mechanism worked
#: and the scorer was simply unreachable. It is not new in 3b.
#: ``solverah.maintenance.backfill_culture_preferences`` has had it since 3a
#: through ``matching_service``'s lazy ``work_pulse`` import; 3b is what would
#: have made it routine rather than occasional.
#:
#: Here rather than in a ``PYTHONPATH`` on the compose file because every
#: deployment that starts a worker needs it, and an environment variable one of
#: them forgets is a worker that boots and fails its tasks.
#:
#: **The insert is unconditional, and guarding it with "if not already present"
#: is the version that does not work.**  Celery's ``cwd_in_path`` inserts the
#: working directory only when it is absent and removes it again afterwards, so
#: at the moment this module is imported the path is *already there* -- a
#: membership test skips the insert, Celery then removes its own entry, and the
#: net effect is nothing.  Inserting unconditionally leaves two entries during
#: the import; ``list.remove`` takes the first, one survives, and the worker
#: keeps the root for the lifetime of the process.  A duplicate ``sys.path``
#: entry costs one failed stat per miss and is the cheapest correct answer here.
REPO_ROOT = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, REPO_ROOT)

from dotenv import load_dotenv  # noqa: E402  -- must follow the path fix

from solverah.config import is_truthy  # noqa: E402  -- same

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
