"""Unit tests for app/auth.py — GoTrue calls are mocked, no network."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import app.auth as auth


@pytest.fixture(autouse=True)
def _clear_cache():
    auth._cache.clear()
    yield
    auth._cache.clear()


class _FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_verify_token_returns_user_on_200(monkeypatch):
    monkeypatch.setattr(
        auth.httpx, "get",
        lambda *a, **k: _FakeResp(200, {"id": "u1", "email": "gm@x.com"}),
    )
    assert auth.verify_token("tok")["id"] == "u1"


def test_verify_token_raises_401_on_reject(monkeypatch):
    monkeypatch.setattr(auth.httpx, "get", lambda *a, **k: _FakeResp(401, {}))
    with pytest.raises(auth.HTTPException) as ei:
        auth.verify_token("bad")
    assert ei.value.status_code == 401


def test_verify_token_caches(monkeypatch):
    calls = {"n": 0}

    def fake_get(*a, **k):
        calls["n"] += 1
        return _FakeResp(200, {"id": "u1"})

    monkeypatch.setattr(auth.httpx, "get", fake_get)
    auth.verify_token("tok")
    auth.verify_token("tok")
    assert calls["n"] == 1  # second hit served from cache


def test_user_thread_id_namespaces():
    assert auth.user_thread_id({"id": "u1"}, "gm-abc") == "u1:gm-abc"


def _protected_client(monkeypatch, user=None, reject=False):
    def fake_verify(token):
        if reject:
            raise auth.HTTPException(status_code=401, detail="bad")
        return user or {"id": "u1"}

    monkeypatch.setattr(auth, "verify_token", fake_verify)
    a = FastAPI()

    @a.get("/p")
    def p(u: dict = Depends(auth.require_auth)):
        return {"id": u["id"]}

    return TestClient(a)


def test_require_auth_rejects_missing_header(monkeypatch):
    assert _protected_client(monkeypatch).get("/p").status_code == 401


def test_require_auth_rejects_non_bearer(monkeypatch):
    c = _protected_client(monkeypatch)
    assert c.get("/p", headers={"Authorization": "Basic xx"}).status_code == 401


def test_require_auth_accepts_valid_bearer(monkeypatch):
    c = _protected_client(monkeypatch, user={"id": "u9"})
    r = c.get("/p", headers={"Authorization": "Bearer good"})
    assert r.status_code == 200 and r.json()["id"] == "u9"


def test_config_returns_public_supabase_settings(monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(main, "SUPABASE_ANON_KEY", "anon123")
    assert main.config() == {
        "supabase_url": "https://proj.supabase.co",
        "supabase_anon_key": "anon123",
    }
