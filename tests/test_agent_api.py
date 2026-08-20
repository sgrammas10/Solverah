import json
import pytest
from unittest.mock import MagicMock


def _noop(*_args, **_kwargs):
    return None


def _register_and_login(client, monkeypatch):
    """Register a user, confirm email, log in, and return (client, csrf_token)."""
    import app as app_module

    monkeypatch.setattr(app_module, "send_confirmation_email", _noop)
    monkeypatch.setattr(app_module, "log_audit_event", _noop)

    client.post(
        "/api/register",
        json={"email": "agent@example.com", "password": "Strongpass1!", "name": "Agent User", "role": "job-seeker", "terms_accepted": True},
    )

    # Confirm email so login succeeds
    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email="agent@example.com").first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()

    resp = client.post(
        "/api/login",
        json={"email": "agent@example.com", "password": "Strongpass1!"},
    )
    assert resp.status_code == 200
    csrf = resp.get_json()["csrfToken"]
    return csrf


def _mock_llm_streaming(monkeypatch, reply_text="I can help with that."):
    """Patch _get_agent_client to return a mock that streams reply_text word by word."""
    import app as app_module

    words = reply_text.split()
    chunks = []
    for i, word in enumerate(words):
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = word + (" " if i < len(words) - 1 else "")
        chunks.append(chunk)

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = iter(chunks)
    monkeypatch.setattr(app_module, "_get_agent_client", lambda: mock_client)
    return mock_client


def _parse_sse(data: bytes) -> list[dict]:
    """Parse SSE response body into a list of event dicts."""
    events = []
    for line in data.decode().split("\n\n"):
        line = line.strip()
        if line.startswith("data: "):
            payload = line[6:].strip()
            if payload:
                events.append(json.loads(payload))
    return events


def test_agent_chat_unauthenticated(client):
    resp = client.post("/api/agent/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert resp.status_code == 401


def test_agent_chat_missing_messages(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _mock_llm_streaming(monkeypatch)

    resp = client.post(
        "/api/agent/chat",
        json={},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 400
    assert "messages" in resp.get_json()["error"]


def test_agent_chat_empty_messages(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _mock_llm_streaming(monkeypatch)

    resp = client.post(
        "/api/agent/chat",
        json={"messages": []},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 400


def test_agent_chat_success(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    mock_client = _mock_llm_streaming(monkeypatch, reply_text="Here are some career tips.")

    resp = client.post(
        "/api/agent/chat",
        json={"messages": [{"role": "user", "content": "What should I focus on?"}], "model": "test-model"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.content_type

    events = _parse_sse(resp.data)
    done_event = next((e for e in events if e.get("done")), None)
    assert done_event is not None
    assert done_event["model"] == "test-model"

    full_reply = "".join(e.get("chunk", "") for e in events)
    assert "career tips" in full_reply

    # Ensure Groq was called with a system message prepended
    call_args = mock_client.chat.completions.create.call_args
    messages_sent = call_args.kwargs.get("messages") or call_args.kwargs["messages"]
    assert messages_sent[0]["role"] == "system"
    assert "Solverah AI" in messages_sent[0]["content"]


def test_agent_chat_custom_model(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _mock_llm_streaming(monkeypatch)

    resp = client.post(
        "/api/agent/chat",
        json={"messages": [{"role": "user", "content": "hi"}], "model": "mistral"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.data)
    done_event = next((e for e in events if e.get("done")), None)
    assert done_event is not None
    assert done_event["model"] == "mistral"


def test_agent_chat_groq_unavailable(client, monkeypatch):
    import app as app_module

    csrf = _register_and_login(client, monkeypatch)

    def _raise_connection(*_a, **_kw):
        raise ConnectionRefusedError("Connection refused")

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = _raise_connection
    monkeypatch.setattr(app_module, "_get_agent_client", lambda: mock_client)

    resp = client.post(
        "/api/agent/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 503


def test_fetch_resume_text_caches_s3_result(monkeypatch):
    import app as app_module

    # Isolate cache state for this test
    monkeypatch.setattr(app_module, "_resume_cache", {})
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")

    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: b"resume bytes")}
    monkeypatch.setattr(app_module, "get_s3_client", lambda: mock_s3)
    monkeypatch.setattr(app_module, "_extract_resume_text", lambda _path, _mime: "Extracted resume text")

    profile = {
        "resumeKey": "users/1/resume.pdf",
        "uploadedResume": {"type": "application/pdf"},
    }

    first = app_module._fetch_resume_text(profile)
    second = app_module._fetch_resume_text(profile)

    assert first == "Extracted resume text"
    assert second == "Extracted resume text"
    assert mock_s3.get_object.call_count == 1  # S3 hit only on first call


def test_agent_chat_includes_resume_in_context(client, monkeypatch):
    import app as app_module

    csrf = _register_and_login(client, monkeypatch)
    mock_client = _mock_llm_streaming(monkeypatch)
    monkeypatch.setattr(app_module, "_fetch_resume_text", lambda _: "Worked at Acme Corp as engineer.")

    client.post(
        "/api/agent/chat",
        json={"messages": [{"role": "user", "content": "Review my resume"}]},
        headers={"X-CSRF-TOKEN": csrf},
    )

    call_args = mock_client.chat.completions.create.call_args
    system_msg = call_args.kwargs["messages"][0]["content"]
    assert "Acme Corp" in system_msg
