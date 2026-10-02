"""pilot_form -- the pre-launch pilot form for the match model.

Pre-registration Amendment 2 (Solverah_IP/PREREGISTRATION_2026-10-01_FIRST_OUTCOME_FIT.md):
before the site launches, outcome rows come from a Google Form that Sebastian sends to his
network. The form is GENERATED from the app's own item banks, and its responses are imported
into a LOCAL research database through the app's own storage doorways, so a pilot row is an
app row in every column and differs only in its provenance label.

    spec.py                  the form as data: pages, questions, options, branching -- read
                             from the live item banks, never typed by hand
    generate_form_script.py  spec -> build_form.gs (Google Apps Script) + form_mapping.json
    build_form.gs            GENERATED. Pasted into script.google.com and run once
    form_mapping.json        GENERATED. Column title -> item id, option text -> stored answer
    responses.py             pure: response CSV -> parsed respondents, or a skip reason
    import_responses.py      CLI: parsed respondents -> local solverah_pilot* database
    report_back.py           CLI: one pilot id -> the Situation Report text, words only

Everything that touches a database goes through `devfit.guard` with PILOT_DB_PREFIX: local
host only, a `solverah_pilot*` database name only, never APP_ENV=production, no override.
The repo's .env carries the PRODUCTION DATABASE_URL; nothing here reads it.

README.md is the step-by-step for running it.
"""

from __future__ import annotations

import os
import sys

#: causal_graph/v1_model -- the model modules import each other by bare name.
MODEL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MODEL_DIR not in sys.path:
    sys.path.insert(0, MODEL_DIR)

#: The repo root, so `import model` / `import assessment_form` work when these modules
#: run as `python -m causal_graph.v1_model.pilot_form.<name>`.
REPO_ROOT = os.path.dirname(os.path.dirname(MODEL_DIR))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))

#: Where everything that must NOT live in the repo goes: respondent emails, written
#: reports. A sibling of the repo, next to solverah-devfit and the verification venv.
DEFAULT_PRIVATE_DIR = os.path.join(os.path.dirname(REPO_ROOT), "solverah-pilot")

__all__ = ["MODEL_DIR", "REPO_ROOT", "PACKAGE_DIR", "DEFAULT_PRIVATE_DIR"]
