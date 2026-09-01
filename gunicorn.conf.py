"""Gunicorn config — loaded automatically from the working directory in prod.

Render's start command doesn't pass -c, so gunicorn picks this file up by
default. Any flags passed on the command line take precedence over values here.
"""

# Backstop for slow requests. /api/intelligence/path-suggestions fans out to
# O*NET and OpenAI; after the embedding batching fix it finishes well inside
# the default 30s, but a slow upstream day shouldn't turn into a worker kill
# and a 500 for the user.
#
# STILL 120, deliberately, after Phase 3a. Dropping this to 30s is the exit
# criterion for the whole of Phase 3, and it is a claim about every handler
# rather than about most of them: "no handler makes a blocking third-party
# call" (docs/ARCHITECTURE.md Phase 3). 3a moved resume parsing and all email
# off the request path. Assessment scoring and path suggestions -- the two
# handlers this number was actually raised for -- are still synchronous until
# 3b, so lowering it now would kill exactly the requests it was raised to
# protect, and the queue that makes it safe would get the credit for the
# outage.
timeout = 120
