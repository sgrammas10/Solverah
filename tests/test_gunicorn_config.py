"""The production process geometry, asserted against the file production loads.

Render runs a native Python runtime with a bare ``gunicorn app:app`` -- no
flags -- so ``gunicorn.conf.py`` in the repo root IS production's configuration.
``infra/docker/Dockerfile.api``'s CMD is *not*: that image is used only by the
backup cron. The two have drifted twice now, in the same direction each time --
a value correct in the Dockerfile and missing from the file prod actually reads:

* the 120s -> 30s request timeout (documented in ``gunicorn.conf.py`` itself), and
* ``--max-requests``, whose absence let three workers run 4.8 days without
  recycling and OOM production on 2026-09-08.

These tests exist so a third occurrence fails here instead of in production.
They assert on the *file* rather than on anything the app imports, because the
failure mode being guarded against is precisely that the file says something
different from what everyone assumes it says.

**Why the file is exec'd rather than loaded through gunicorn's own Config.**
``gunicorn.config`` imports ``grp``, which does not exist on Windows, so
importing it at module scope would ERROR the whole suite at collection on a
Windows dev machine. The value assertions therefore run everywhere, and the one
test that needs gunicorn's settings registry -- the check that no setting name
is misspelled, which is the one thing exec cannot catch -- skips where gunicorn
is unimportable and runs on CI, which is Linux, as production is.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CONF = ROOT / "gunicorn.conf.py"
DOCKERFILE = ROOT / "infra" / "docker" / "Dockerfile.api"


def _namespace() -> dict:
    """Exec ``gunicorn.conf.py`` and return its module-level names.

    This is what gunicorn does to a config file before feeding the recognised
    names into its ``Config``; doing the exec ourselves keeps the assertions
    runnable on any platform.
    """
    ns: dict = {"__file__": str(CONF)}
    exec(compile(CONF.read_text(encoding="utf-8"), str(CONF), "exec"), ns)
    return ns


@pytest.fixture(scope="module")
def conf() -> dict:
    return _namespace()


def test_workers_recycle(conf: dict) -> None:
    """Workers must retire, or an unbounded cache is an outage rather than a sawtooth.

    Regression test for the 2026-09-08 outage. Booted 09-03 19:19 UTC, SIGKILL
    09-08 14:13: three workers, never recycled, two per-worker caches with no
    eviction path (``path_cache._cache`` and ``agent_service._resume_cache``).
    Recycling does not fix the leak -- it bounds it -- but the difference
    between bounded and unbounded is the difference between a sawtooth and a
    dead service.

    Fails against the config as it stood before that date, which set no
    max_requests at all; gunicorn's default of 0 means "never recycle".
    """
    assert conf.get("max_requests", 0) > 0, (
        "gunicorn.conf.py sets no max_requests, so workers never restart and any "
        "per-worker leak grows without bound. This is what took production down "
        "on 2026-09-08."
    )


def test_recycling_is_jittered(conf: dict) -> None:
    """Staggered, so the three workers never retire in lockstep.

    With jitter at 0 every worker hits the ceiling on the same request count and
    capacity drops to zero at once, turning the fix into a periodic outage.
    """
    jitter = conf.get("max_requests_jitter", 0)
    assert jitter > 0
    assert jitter < conf["max_requests"]


def test_geometry_matches_the_dockerfile(conf: dict) -> None:
    """The two configurations must agree, because only one of them runs.

    Prod loads ``gunicorn.conf.py``; the Dockerfile's CMD documents the same
    shape for the image. When they disagree the file wins in production and the
    Dockerfile quietly misleads whoever reads it -- twice now. The expected
    values are parsed out of the CMD rather than restated here, so editing one
    side without the other fails.
    """
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    for flag, key in (
        ("--max-requests-jitter", "max_requests_jitter"),
        ("--max-requests", "max_requests"),
    ):
        assert flag in dockerfile, f"{flag} vanished from Dockerfile.api"
        # exec form: "--max-requests", "2000", \
        after = dockerfile.split(flag + '"', 1)[1]
        digits = "".join(c for c in after.split('"', 2)[1] if c.isdigit())
        assert int(digits) == conf[key], (
            f"{flag} is {digits} in Dockerfile.api but {conf[key]} in "
            "gunicorn.conf.py -- production loads the latter"
        )


def test_geometry_is_pinned(conf: dict) -> None:
    """Guard the process geometry, which is now bounded by RAM, not by load.

    ``workers`` was 3 until 2026-09-16, pinned to the load baseline. It is 1
    now, and the reason the earlier number was wrong is that the instance plan
    was never written down: the 2026-09-02 intake did not capture it, and the
    dashboard says **Starter -- 0.5 CPU, 512 MB**.

    Two per-process costs multiply by this number -- the ~150 MB pandas/numpy/
    scikit-learn baseline, and every module-global cache, each worker holding
    its own copy. Three of each is ~450 MB of a 512 MB box before serving a
    request, which is the 2026-09-15 OOM. More processes also bought almost
    nothing: the slow paths are I/O-bound and ``gthread``'s 8 threads already
    cover that concurrency, while 0.5 CPU cannot saturate even one process.

    Connection math, inside Render's max_connections of 103:
    1 worker x (pool 10 + overflow 5) = 15, and 30 during a rolling deploy
    overlap. Was 45/90.

    If this assertion fails because someone raised ``workers``, the question to
    answer first is what the instance plan is now -- not what throughput is
    wanted. RAM before workers, never the reverse.
    """
    assert conf["worker_class"] == "gthread"
    assert conf["threads"] == 8
    assert conf["workers"] == 1
    assert conf["timeout"] == 30


def test_every_setting_name_is_real() -> None:
    """No misspelled settings -- the one failure exec cannot catch.

    ``max_request = 2000`` (singular) is a valid Python assignment, a no-op to
    gunicorn, and indistinguishable from the fix by eye. Feeding every
    module-level name through gunicorn's own settings registry is what catches
    it. Skipped where gunicorn is unimportable (Windows: it needs ``grp``);
    CI is Linux, as production is.
    """
    gunicorn_config = pytest.importorskip(
        "gunicorn.config",
        reason="gunicorn.config imports grp, which is Unix-only; CI runs Linux",
    )

    cfg = gunicorn_config.Config()
    known = set(cfg.settings)

    for key, value in _namespace().items():
        if key.startswith("__"):
            continue
        assert key.lower() in known, (
            f"gunicorn.conf.py defines {key!r}, which is not a gunicorn setting. "
            "It will be silently ignored at boot."
        )
        # set() validates the value the way gunicorn would at startup.
        cfg.set(key.lower(), value)
