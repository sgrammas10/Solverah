"""devfit -- the local-only harness for fitting and inspecting the match model.

Three scripts and a safety catch:

    guard.py          assert_local_dev_database() -- called by every script below
                      BEFORE it opens a connection, on the URL it will actually use
    seed_synthetic.py writes N synthetic people (core sitting + environment report)
                      through the sanctioned store functions, with a planted truth
    run_fit.py        assemble -> fit_posterior -> save a model_run   (PyMC; system
                      Python 3.10 only)
    explain_user.py   the only place the model's numbers are visible, dev only

WHY THIS IS A SEPARATE PACKAGE, AND WHY IT IS NOT IMPORTABLE FROM THE APP
-------------------------------------------------------------------------
PyMC must never become a server dependency. Fitting is an offline script; the
server only ever READS saved weight rows (match_scoring.load_run_weights). So the
one module here that imports pymc (run_fit) is reachable only as `python -m`, and
nothing in the app package imports anything from `devfit`.

`explain_user.py` prints per-dimension gaps, costs and P(doing well). Decision D-15
keeps exactly those numbers off every API payload -- the Situation Report ships
words, never magnitudes. The guard is what keeps that script a dev tool: it refuses
to run against anything but a `solverah_modeldev*` database on localhost.

Run everything from the repo root with an explicit DATABASE_URL and
SOLVERAH_IGNORE_DOTENV=1 -- the repo's .env carries a Render-internal PRODUCTION
DATABASE_URL, and app.py calls load_dotenv().

    SOLVERAH_IGNORE_DOTENV=1 APP_ENV=testing \\
    DATABASE_URL=postgresql://solverah:solverah@localhost:5433/solverah_modeldev \\
    JWT_SECRET_KEY=... python -m causal_graph.v1_model.devfit.seed_synthetic --n 1200
"""

from __future__ import annotations

import os
import sys

#: causal_graph/v1_model -- match_core, build_model and assemble_training_data
#: import each other by bare name (they predate this package), so the directory
#: has to be importable the same way match_scoring.py arranges it.
MODEL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MODEL_DIR not in sys.path:
    sys.path.insert(0, MODEL_DIR)

#: The repo root, so `import match_scoring` / `import model` work when these
#: modules are run as `python -m causal_graph.v1_model.devfit.<name>` from
#: anywhere.
REPO_ROOT = os.path.dirname(os.path.dirname(MODEL_DIR))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

__all__ = ["MODEL_DIR", "REPO_ROOT"]
