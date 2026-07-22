"""Gunicorn config — loaded automatically from the working directory in prod.

Render's start command doesn't pass -c, so gunicorn picks this file up by
default. Any flags passed on the command line take precedence over values here.
"""

# Backstop for slow requests. /api/intelligence/path-suggestions fans out to
# O*NET and OpenAI; after the embedding batching fix it finishes well inside
# the default 30s, but a slow upstream day shouldn't turn into a worker kill
# and a 500 for the user.
timeout = 120
