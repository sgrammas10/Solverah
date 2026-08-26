"""Namespace root for code that is not part of the Flask application.

``packages/`` holds libraries the API imports but does not own the lifecycle of:
today that is :mod:`packages.ml`.  It is a plain package rather than a
``sys.path`` entry or an editable install on purpose -- the repo root is already
on the path under gunicorn, pytest, and ``python -m``, so ``packages.ml.foo``
resolves everywhere with no path manipulation and no build step.
"""
