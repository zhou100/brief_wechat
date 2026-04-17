"""
Integration tests for /api/auth — register, login, token refresh.
Run against the live backend: docker compose exec backend pytest tests/test_auth_integration.py -v
"""
import time
import pytest
pytest.skip("Requires a live backend service; skipped in local unit-test runs", allow_module_level=True)
import httpx

BASE = "http://localhost:10000/api/auth"
_ts = int(time.time())  # unique suffix per test run


def _email(tag: str) -> str:
    return f"test_{tag}_{_ts}@example.com"


# ── Register ──────────────────────────────────────────────────────────────────

def test_register_returns_tokens():
    r = httpx.post(f"{BASE}/register", json={"email": _email("reg1"), "password": "pass1234"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


def test_register_duplicate_email_returns_400():
    email = _email("dup")
    httpx.post(f"{BASE}/register", json={"email": email, "password": "pass1234"})
    r = httpx.post(f"{BASE}/register", json={"email": email, "password": "pass1234"})
    assert r.status_code == 400
    assert "already registered" in r.json()["detail"].lower()


def test_register_missing_email_returns_422():
    r = httpx.post(f"{BASE}/register", json={"password": "pass1234"})
    assert r.status_code == 422


def test_register_missing_password_returns_422():
    r = httpx.post(f"{BASE}/register", json={"email": _email("nopw")})
    assert r.status_code == 422


def test_register_invalid_email_format_returns_422():
    r = httpx.post(f"{BASE}/register", json={"email": "not-an-email", "password": "pass1234"})
    assert r.status_code == 422


# ── Login ─────────────────────────────────────────────────────────────────────

def test_login_with_valid_credentials_returns_tokens():
    email = _email("login1")
    pw = "mypassword99"
    httpx.post(f"{BASE}/register", json={"email": email, "password": pw})

    r = httpx.post(f"{BASE}/token", data={"username": email, "password": pw})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


def test_login_wrong_password_returns_401():
    email = _email("login2")
    httpx.post(f"{BASE}/register", json={"email": email, "password": "correct"})

    r = httpx.post(f"{BASE}/token", data={"username": email, "password": "wrong"})
    assert r.status_code == 401


def test_login_unknown_email_returns_401():
    r = httpx.post(
        f"{BASE}/token",
        data={"username": "nobody_ever@example.com", "password": "pass"},
    )
    assert r.status_code == 401


def test_login_missing_fields_returns_422():
    r = httpx.post(f"{BASE}/token", data={})
    assert r.status_code == 422


# ── Token refresh ─────────────────────────────────────────────────────────────

def test_refresh_with_valid_token_returns_new_tokens():
    email = _email("refresh1")
    reg = httpx.post(f"{BASE}/register", json={"email": email, "password": "pw12345"})
    refresh_tok = reg.json()["refresh_token"]

    r = httpx.post(f"{BASE}/refresh", json={"refresh_token": refresh_tok})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "access_token" in body
    assert "refresh_token" in body


def test_refresh_with_garbage_token_returns_401():
    r = httpx.post(f"{BASE}/refresh", json={"refresh_token": "this.is.garbage"})
    assert r.status_code == 401


# ── Protected endpoint reachable after login ─────────────────────────────────

def test_access_token_authenticates_protected_endpoint():
    email = _email("prot1")
    reg = httpx.post(f"{BASE}/register", json={"email": email, "password": "pw12345"})
    token = reg.json()["access_token"]

    r = httpx.get(
        "http://localhost:10000/api/v1/entries/",
        headers={"Authorization": f"Bearer {token}"},
    )
    # 200 = authenticated; anything else indicates auth failure
    assert r.status_code == 200, r.text


def test_no_token_returns_401_on_protected_endpoint():
    r = httpx.get("http://localhost:10000/api/v1/entries/")
    assert r.status_code == 401
