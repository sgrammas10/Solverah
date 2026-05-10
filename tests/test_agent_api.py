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
        json={"email": "agent@example.com", "password": "Strongpass1!", "name": "Agent User", "role": "job-seeker"},
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


def _mock_ollama(monkeypatch, reply_text="I can help with that."):
    """Patch _get_ollama_client to return a mock that produces reply_text."""
    import app as app_module

    mock_choice = MagicMock()
    mock_choice.message.content = reply_text

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    monkeypatch.setattr(app_module, "_get_ollama_client", lambda: mock_client)
    return mock_client


def test_agent_chat_unauthenticated(client):
    resp = client.post("/api/agent/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert resp.status_code == 401


def test_agent_chat_missing_messages(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _mock_ollama(monkeypatch)

    resp = client.post(
        "/api/agent/chat",
        json={},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 400
    assert "messages" in resp.get_json()["error"]


def test_agent_chat_empty_messages(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _mock_ollama(monkeypatch)

    resp = client.post(
        "/api/agent/chat",
        json={"messages": []},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 400


def test_agent_chat_success(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    mock_client = _mock_ollama(monkeypatch, reply_text="Here are some career tips.")

    resp = client.post(
        "/api/agent/chat",
        json={"messages": [{"role": "user", "content": "What should I focus on?"}]},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["reply"] == "Here are some career tips."
    assert payload["model"] == "llama3"

    # Ensure Ollama was called with a system message prepended
    call_args = mock_client.chat.completions.create.call_args
    messages_sent = call_args.kwargs.get("messages") or call_args.args[0] if call_args.args else call_args.kwargs["messages"]
    assert messages_sent[0]["role"] == "system"
    assert "Solverah AI" in messages_sent[0]["content"]


def test_agent_chat_custom_model(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _mock_ollama(monkeypatch)

    resp = client.post(
        "/api/agent/chat",
        json={"messages": [{"role": "user", "content": "hi"}], "model": "mistral"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200
    assert resp.get_json()["model"] == "mistral"


def test_agent_chat_ollama_unavailable(client, monkeypatch):
    import app as app_module

    csrf = _register_and_login(client, monkeypatch)

    def _raise_connection(*_a, **_kw):
        raise ConnectionRefusedError("Connection refused")

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = _raise_connection
    monkeypatch.setattr(app_module, "_get_ollama_client", lambda: mock_client)

    resp = client.post(
        "/api/agent/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 503
