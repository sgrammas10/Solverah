"""Gunicorn config — loaded automatically from the working directory in prod.

Render's start command doesn't pass -c, so gunicorn picks this file up by
default. Any flags passed on the command line take precedence over values here.
"""

# Backstop for a hung worker, back at gunicorn's default. This number was
# raised to 120 for two handlers -- assessment scoring and path suggestions --
# that blocked on OpenAI and O*NET inside the request. 3b moved that work to
# the queue, 3c deleted the synchronous halves, and dropping this was the exit
# criterion for the whole of Phase 3: "no handler makes a blocking third-party
# call" (docs/ARCHITECTURE.md Phase 3, exceptions named there and in A21).
#
# The agent stream (`POST /agent/messages`) legitimately outlives 30 seconds
# and survives this setting, and that is measured rather than assumed (A21):
# under gunicorn 26.1.0 (pinned) this exact file, loaded with no command-line
# flags, reported gthread/8/timeout=30 through gunicorn's own config
# machinery, and a provider stubbed to trickle held the SSE stream open for
# 46 seconds -- 10 frames landed after the 30-second mark, the `done` frame
# arrived, and the worker was never killed. A `sync --timeout 30` control run
# survived identically, so on this gunicorn the timeout detects a hung
# *process* rather than a slow *streaming* request under either class; the
# `gthread` pin below stays for A20's original reason -- one sync worker
# serves one request at a time, streams included -- not for stream survival.
timeout = 30

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
# `gthread`, 8 threads, and 3 workers match `infra/docker/Dockerfile.api`'s
# production CMD, so the two configurations agree. The open question above is
# now answered: the 2026-09-02 prod-readiness intake
# (docs/audits/PROD_READINESS_2026-09_ANSWERS.md) confirmed Render runs a
# native Python runtime with a bare `gunicorn app:app` -- no flags at all --
# so this file IS the production geometry. Leaving `workers` unset meant prod
# ran 1 worker x 8 threads, a third of the load-tested capacity; hence the
# explicit pin. Connection math stays inside Render's max_connections=103:
# 3 workers x (pool 10 + overflow 5) = 45, 90 during a rolling overlap.
worker_class = "gthread"
threads = 8
workers = 3
