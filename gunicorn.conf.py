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

# Pinned so the file Render actually loads states what the Dockerfile already
# does, rather than gunicorn's own defaults (A20, docs/ARCHITECTURE.md).
#
# There is no render.yaml in this repository, so whether Render's start command
# passes its own --worker-class cannot be answered from here. If it does not,
# gunicorn falls back to *this file*, and until this line was added that meant
# `worker_class=sync, workers=1` -- measured by loading this config through
# gunicorn's own machinery with no command-line flags. Handlers still make
# blocking third-party calls (OpenAI, Groq, O*NET, Resend, R2) and
# `POST /agent/messages` streams from Groq for the life of the request, so a
# sync worker holds one in-flight request total; a second caller queues behind
# whichever request -- ordinary or streaming -- already has the worker.
#
# `gthread` and 8 threads match `infra/docker/Dockerfile.api`'s production
# CMD, so the two configurations stop disagreeing about the one thing that
# matters here. `workers` is left unset (gunicorn's default) rather than
# copied from the Dockerfile's `--workers 3`: on the command line those flags
# always win over this file (see the module docstring), so pinning `workers`
# here only changes behaviour for a deploy that dropped the Dockerfile's flags
# entirely, at which point matching thread *behaviour* (gthread, not sync)
# matters more than matching the exact replica count.
worker_class = "gthread"
threads = 8
