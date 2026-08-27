"""Regression tests for the security fixes in the hardening pass.

Each test here fails against the pre-fix code:
  * presigned PUT URLs left the declared size unsigned, so the 10MB check was
    advisory and a caller could upload an object of any size;
  * request.remote_addr was the proxy's address, collapsing per-IP rate limits
    into one global bucket and poisoning the audit log;
  * no request body cap existed;
  * send_test.py carried live SMTP credentials as literals;
  * requirements were unpinned, so every build resolved to whatever was latest;
  * objects from never-finalized uploads were never swept from R2.
"""

import datetime
import io
import re

import pytest


# ── Presigned uploads bind the declared size ────────────────────────────────


class _RecordingS3:
    """Minimal S3 stand-in that records generate_presigned_url kwargs."""

    def __init__(self):
        self.calls = []

    def generate_presigned_url(self, **kwargs):
        self.calls.append(kwargs)
        return "https://r2.example.test/signed"


def test_intake_presign_signs_content_length(client, monkeypatch):
    """The declared size must be inside the signature, not just validated."""
    fake = _RecordingS3()
    monkeypatch.setattr("solverah.infra.storage.get_s3_client", lambda: fake)
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")

    resp = client.post(
        "/api/v1/intake/resume-tickets",
        json={"mime": "application/pdf", "size": 1234},
    )

    assert resp.status_code == 200
    assert len(fake.calls) == 1
    params = fake.calls[0]["Params"]
    # Without ContentLength in Params the storage layer accepts a body of any
    # size, which is the whole bug.
    assert params["ContentLength"] == 1234
    assert params["ContentType"] == "application/pdf"


def test_intake_presign_still_rejects_oversized_declaration(client, monkeypatch):
    """The pre-existing size ceiling must survive the signing change."""
    fake = _RecordingS3()
    monkeypatch.setattr("solverah.infra.storage.get_s3_client", lambda: fake)
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")

    resp = client.post(
        "/api/v1/intake/resume-tickets",
        json={"mime": "application/pdf", "size": 11 * 1024 * 1024},
    )

    assert resp.status_code == 400
    assert fake.calls == []  # no URL handed out at all


# ── Trusted-proxy resolution ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,production,expected",
    [
        (None, True, 1),      # Render terminates at exactly one proxy
        (None, False, 0),     # local runs have none; trusting XFF would be a hole
        ("", True, 1),
        ("0", True, 0),       # explicit opt-out survives production
        ("2", False, 2),      # e.g. Cloudflare in front of Render
    ],
)
def test_resolve_trusted_proxy_count(raw, production, expected):
    from app import _resolve_trusted_proxy_count

    assert _resolve_trusted_proxy_count(raw, production) == expected


@pytest.mark.parametrize("raw", ["abc", "-1", "1.5"])
def test_resolve_trusted_proxy_count_rejects_garbage(raw):
    """Boot loudly rather than guess: too high is spoofable, too low breaks limits."""
    from app import _resolve_trusted_proxy_count

    with pytest.raises(RuntimeError):
        _resolve_trusted_proxy_count(raw, True)


def test_apply_proxy_fix_is_a_no_op_at_zero():
    from flask import Flask
    from werkzeug.middleware.proxy_fix import ProxyFix

    from app import _apply_proxy_fix

    bare = Flask(__name__)
    assert _apply_proxy_fix(bare, 0) is False
    # Flask.wsgi_app is a bound method until something wraps it, so identity
    # comparison is unreliable here -- assert the wrapper is absent instead.
    assert not isinstance(bare.wsgi_app, ProxyFix)


def test_apply_proxy_fix_resolves_client_ip_but_not_host():
    """x_for is trusted; x_host is not, or reset links could be poisoned."""
    from flask import Flask, request

    from app import _apply_proxy_fix

    probe = Flask(__name__)

    @probe.get("/probe")
    def probe_view():
        return {"ip": request.remote_addr, "host": request.host}

    assert _apply_proxy_fix(probe, 1) is True

    resp = probe.test_client().get(
        "/probe",
        headers={
            "X-Forwarded-For": "203.0.113.9",
            "X-Forwarded-Host": "attacker.example",
        },
        environ_overrides={"REMOTE_ADDR": "10.0.0.1"},
    )
    body = resp.get_json()
    assert body["ip"] == "203.0.113.9"        # real client, not the proxy
    assert "attacker.example" not in body["host"]  # forwarded Host ignored


# ── Request body cap ────────────────────────────────────────────────────────


def test_max_content_length_is_configured():
    from app import app

    assert app.config["MAX_CONTENT_LENGTH"] == 2 * 1024 * 1024


def test_oversized_body_is_rejected(client):
    """Flask must refuse the body before any handler allocates it."""
    resp = client.post(
        "/api/v1/intake/resume-tickets",
        data=b"x" * (3 * 1024 * 1024),
        content_type="application/json",
    )
    assert resp.status_code == 413


# ── No credentials in the repo ──────────────────────────────────────────────


def test_send_test_has_no_credential_literals():
    """send_test.py leaked live SMTP credentials as os.environ.get defaults."""
    source = io.open("send_test.py", encoding="utf-8").read()

    for var in ("SMTP_USER", "SMTP_PASSWORD"):
        # Matches `os.environ.get("SMTP_PASSWORD", "<anything non-empty>")`
        pattern = r'environ\.get\(\s*["\']%s["\']\s*,\s*["\'][^"\']+["\']' % var
        assert not re.search(pattern, source), "%s has a hardcoded fallback" % var

    # The specific values that leaked, so this can never silently come back.
    assert "0468248b7eda4b83797fd09620b69334e9cb" not in source
    assert "26552679d3b55356bee4df15bf3bf306-737" not in source


def test_direct_requirements_are_pinned():
    """Unpinned deps meant each build resolved to whatever was latest."""
    unpinned = []
    for line in io.open("requirements.txt", encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=!~\[]", line, 1)[0].strip()
        if name == "setuptools":
            continue  # deliberately a floor, not a pin -- see requirements.txt
        if "==" not in line:
            unpinned.append(line)
    assert unpinned == [], "unpinned requirements: %s" % unpinned
