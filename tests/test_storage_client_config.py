"""The S3 client's timeout and retry bounds, and the guard that keeps them.

Before this, ``boto3.client("s3", ...)`` was built with no ``config=`` at all,
so it inherited botocore's defaults: a 60s connect timeout, a 60s read timeout,
and the "legacy" retry mode with 5 total attempts.  A provider that accepted
connections and then stopped answering could therefore hold a request thread
for up to 5 x (60 + 60) = 600s; it is now bounded at 3 x (3 + 10) = 39s.

That matters because nothing else bounds it.  Gunicorn's 30s timeout reaps a
wedged *process*, not a thread stuck in a socket read, and prod runs gthread
with 3 workers x 8 threads -- 24 threads that a single unresponsive R2 can take
out.  These tests pin the bounds and the guard test below keeps a future client
from being constructed without them.
"""

import ast
import io
import pathlib

import pytest
from botocore.exceptions import ConnectTimeoutError, ReadTimeoutError

from solverah.infra import storage


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def _s3_env(monkeypatch):
    """The four variables ``get_s3_client`` reads.  CI supplies none of them."""
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://r2.example.test")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "test-key-id")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "test-secret-not-a-real-one")
    monkeypatch.setenv("S3_REGION", "auto")
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")


# ── The bounds reach the constructed client ────────────────────────────────


def test_client_carries_the_timeouts(_s3_env):
    """Read the values off the real client, not off the Config we passed in.

    Asserting on ``boto_config()`` alone would still pass if someone dropped
    the ``config=`` keyword from the constructor, which is exactly the bug.
    """
    config = storage.get_s3_client().meta.config

    assert config.connect_timeout == storage.CONNECT_TIMEOUT_SECONDS == 3
    assert config.read_timeout == storage.READ_TIMEOUT_SECONDS == 10


def test_client_uses_standard_retry_mode_with_three_total_attempts(_s3_env):
    """"legacy" is the default and budgets 5 attempts; "standard" is the ask.

    Asserted on ``total_max_attempts`` because that is the key botocore
    actually reports: ``max_attempts=2`` in the Config means two retries
    *after* the first request.  A test written against ``max_attempts`` here
    raises KeyError rather than telling you the real attempt count.
    """
    retries = storage.get_s3_client().meta.config.retries

    assert retries["mode"] == "standard"
    assert retries["total_max_attempts"] == storage.TOTAL_MAX_ATTEMPTS == 3


def test_worst_case_thread_hold_stays_bounded(_s3_env):
    """The point of the numbers: ~40s instead of 600s.

    Not pinned to gunicorn's 30s -- that timeout reaps a wedged process, not a
    thread in a socket read, so there is no threshold to duck under.  This is a
    ceiling on how much of a 24-thread pool one dead provider can hold, and it
    fails if someone raises a timeout or the attempt count without redoing the
    arithmetic in the module's comment.
    """
    config = storage.get_s3_client().meta.config
    worst_case = config.retries["total_max_attempts"] * (
        config.connect_timeout + config.read_timeout
    )

    assert worst_case <= 45, "worst-case thread hold is %ss" % worst_case


# ── No unbounded client can be constructed anywhere in the tree ────────────


def _python_sources():
    skip = {
        ".venv", "venv", "node_modules", "__pycache__", ".git",
        "_to_delete", "_mutation_tmp", "dist", "old_LLM",
    }
    for path in REPO_ROOT.rglob("*.py"):
        if skip & set(path.parts):
            continue
        yield path


def _boto3_constructions(tree):
    """Yield every ``boto3.client(...)`` / ``boto3.resource(...)`` Call node.

    Parsed rather than pattern-matched.  The first version of this guard was a
    regex requiring a column-0 closing paren -- so it never matched the one
    construction site that mattered, and passed against deliberately broken
    code.  An AST has no such blind spot, and it also means the
    ``boto3.client(`` inside this file's own docstrings is not a match.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr in ("client", "resource")
            and isinstance(func.value, ast.Name)
            and func.value.id == "boto3"
        ):
            yield node


def test_every_boto3_construction_site_passes_a_config():
    """A second client built without ``config=`` reintroduces the 600s hold.

    Parsed rather than imported: the offending call is at module scope in some
    scripts, so importing to check would run them.
    """
    offenders = []
    for path in _python_sources():
        source = io.open(path, encoding="utf-8").read()
        if "boto3." not in source:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:  # not ours to police
            continue
        for call in _boto3_constructions(tree):
            if not any(kw.arg == "config" for kw in call.keywords):
                offenders.append(
                    "%s:%s" % (path.relative_to(REPO_ROOT), call.lineno)
                )

    assert offenders == [], (
        "boto3 client(s) built without config=boto_config(): %s" % offenders
    )


# ── A timeout surfaces as the app's storage error, not as a hang ───────────


class _TimingOutS3:
    """Every operation raises what botocore raises when the bounds are hit."""

    def __init__(self, error):
        self._error = error

    def head_object(self, **kwargs):
        raise self._error

    def get_object(self, **kwargs):
        raise self._error

    def delete_object(self, **kwargs):
        raise self._error


def _connect_timeout():
    return ConnectTimeoutError(endpoint_url="https://r2.example.test")


def _read_timeout():
    return ReadTimeoutError(endpoint_url="https://r2.example.test")


@pytest.mark.parametrize(
    "error", [_connect_timeout(), _read_timeout()], ids=["connect", "read"]
)
def test_upload_verification_reports_a_timeout_as_a_storage_error(
    monkeypatch, _s3_env, error
):
    """A HEAD that times out must become the 400 message, not an exception."""
    from solverah.services import intake_service

    monkeypatch.setattr(
        "solverah.infra.storage.get_s3_client", lambda: _TimingOutS3(error)
    )

    problem = intake_service.verify_upload(
        "intake/abc/resume.pdf", "application/pdf", 1234
    )

    assert problem == "Upload not found in storage"


@pytest.mark.parametrize(
    "error", [_connect_timeout(), _read_timeout()], ids=["connect", "read"]
)
def test_resume_text_fetch_reports_a_timeout_as_an_empty_parse(
    monkeypatch, _s3_env, error
):
    """The documented degradation for an unreadable resume is "", not a 500."""
    from solverah.services import resume_service

    monkeypatch.setattr(
        "solverah.services.resume_service.get_s3_client",
        lambda: _TimingOutS3(error),
    )

    assert resume_service._fetch_text("resumes/x.pdf", "application/pdf") == ""


def test_resume_delete_reports_a_timeout_as_a_failed_key(monkeypatch, _s3_env):
    """Erasure must report the key as failed rather than claim success.

    D-07: a timeout is not permission to say "deleted".
    """
    from solverah.services import account_service

    monkeypatch.setattr(
        "solverah.infra.storage.get_s3_client",
        lambda: _TimingOutS3(_read_timeout()),
    )

    failed = account_service.delete_r2_objects(["resumes/x.pdf"])

    assert failed == ["resumes/x.pdf"]
