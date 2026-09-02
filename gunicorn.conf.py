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
