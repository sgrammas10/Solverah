"""Removed intake routes stay removed.

This file held the end-to-end "save an anonymous /start session onto the
account" flow (``POST /intake/claims`` mode ``session``). That mode went on
2026-11-23 with ``/start`` itself (G24, ruling C); its refusal is pinned in
``tests/test_intake_claims_api.py``.
"""


def test_early_access_route_is_gone(client):
    """G31: ``POST /intake/early-access`` had no caller after 2026-09-28.

    Its UI (``EarlyAccessModal``) was deleted then, and the route sat live,
    anonymous, and unexercised until 2026-11-23. Both mounts must answer 404 --
    a route that comes back through a merge or a stale blueprint import fails
    here rather than reopening an unwatched write path.
    """
    body = {"firstName": "Ada", "lastName": "Lovelace", "email": "ada@example.com"}
    for path in ("/api/v1/intake/early-access", "/api/intake/early-access"):
        resp = client.post(path, json=body)
        assert resp.status_code == 404, path
