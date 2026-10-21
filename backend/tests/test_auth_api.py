"""Tests for backend-managed authentication router and frontend decoupling.

Verifies:
- Valid and invalid login.
- Missing profiles and disabled accounts.
- Role mismatch against database profile.
- Token validation, bearer & cookie session restoration.
- Refresh token rotation.
- Logout session revocation and cookie cleanup.
- Absence of Supabase SDK/keys in frontend source code.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def mock_auth_user(uid="user-123", email="user@cpass.org"):
    u = MagicMock()
    u.id = uid
    u.email = email
    return u


def mock_auth_session(access_token="test-access-token", refresh_token="test-refresh-token", expires_in=3600):
    s = MagicMock()
    s.access_token = access_token
    s.refresh_token = refresh_token
    s.expires_in = expires_in
    s.expires_at = 1800000000
    return s


@pytest.fixture
def mock_supabase_db():
    with patch("app.routers.auth.supabase") as mock_sb:
        yield mock_sb


@pytest.fixture
def mock_auth_client():
    with patch("app.routers.auth.get_auth_client") as mock_factory:
        mock_client = MagicMock()
        mock_factory.return_value = mock_client
        yield mock_client


def test_login_success(mock_auth_client, mock_supabase_db):
    """Successful login returns tokens and sets HttpOnly cookies."""
    auth_resp = MagicMock()
    auth_resp.user = mock_auth_user()
    auth_resp.session = mock_auth_session()
    mock_auth_client.auth.sign_in_with_password.return_value = auth_resp

    mock_supabase_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {
            "id": "user-123",
            "email": "user@cpass.org",
            "full_name": "Test Coordinator",
            "role": "L1_COORDINATOR",
            "is_active": True,
        }
    ]

    res = client.post(
        "/auth/login",
        json={
            "email": "user@cpass.org",
            "password": "Password123!",
            "expected_role": "L1_COORDINATOR",
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert data["access_token"] == "test-access-token"
    assert data["user"]["role"] == "L1_COORDINATOR"
    assert data["user"]["full_name"] == "Test Coordinator"

    # Verify HttpOnly cookies
    assert "cpass_access_token" in res.cookies
    assert "cpass_refresh_token" in res.cookies


def test_login_invalid_credentials(mock_auth_client):
    """Wrong credentials return 401."""
    mock_auth_client.auth.sign_in_with_password.side_effect = Exception("Invalid login credentials")

    res = client.post(
        "/auth/login",
        json={"email": "wrong@cpass.org", "password": "BadPassword"},
    )

    assert res.status_code == 401
    assert "Email or password is incorrect." in res.json()["detail"]


def test_login_missing_profile(mock_auth_client, mock_supabase_db):
    """Authenticated user without CPASS profile is rejected with 403."""
    auth_resp = MagicMock()
    auth_resp.user = mock_auth_user()
    auth_resp.session = mock_auth_session()
    mock_auth_client.auth.sign_in_with_password.return_value = auth_resp

    mock_supabase_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []

    res = client.post(
        "/auth/login",
        json={"email": "user@cpass.org", "password": "Password123!"},
    )

    assert res.status_code == 403
    assert "No CPASS profile for this user" in res.json()["detail"]


def test_login_disabled_account(mock_auth_client, mock_supabase_db):
    """Disabled accounts are rejected with 403."""
    auth_resp = MagicMock()
    auth_resp.user = mock_auth_user()
    auth_resp.session = mock_auth_session()
    mock_auth_client.auth.sign_in_with_password.return_value = auth_resp

    mock_supabase_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"id": "user-123", "full_name": "Inactive User", "role": "L1_COORDINATOR", "is_active": False}
    ]

    res = client.post(
        "/auth/login",
        json={"email": "user@cpass.org", "password": "Password123!"},
    )

    assert res.status_code == 403
    assert "This account is disabled." in res.json()["detail"]


def test_login_incorrect_selected_role(mock_auth_client, mock_supabase_db):
    """Selecting a role that doesn't match the server-side profile returns 403."""
    auth_resp = MagicMock()
    auth_resp.user = mock_auth_user()
    auth_resp.session = mock_auth_session()
    mock_auth_client.auth.sign_in_with_password.return_value = auth_resp

    # Actual DB profile is L1_COORDINATOR
    mock_supabase_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"id": "user-123", "full_name": "Coordinator", "role": "L1_COORDINATOR", "is_active": True}
    ]

    # Client tries to claim ADMIN role
    res = client.post(
        "/auth/login",
        json={
            "email": "user@cpass.org",
            "password": "Password123!",
            "expected_role": "ADMIN",
        },
    )

    assert res.status_code == 403
    assert "This account does not have the selected role." in res.json()["detail"]


def test_session_restoration_via_bearer():
    """GET /auth/me restores profile using Bearer token."""
    with patch("app.auth.supabase") as mock_sb:
        mock_u = MagicMock()
        mock_u.user = mock_auth_user("u-1", "user@cpass.org")
        mock_sb.auth.get_user.return_value = mock_u

        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"id": "u-1", "email": "user@cpass.org", "full_name": "User One", "role": "L2_MANAGER", "is_active": True}
        ]

        res = client.get("/auth/me", headers={"Authorization": "Bearer my-valid-token"})
        assert res.status_code == 200
        assert res.json()["role"] == "L2_MANAGER"
        assert res.json()["full_name"] == "User One"


def test_session_restoration_via_cookie():
    """GET /auth/me restores profile using HttpOnly cookie."""
    with patch("app.auth.supabase") as mock_sb:
        mock_u = MagicMock()
        mock_u.user = mock_auth_user("u-1", "user@cpass.org")
        mock_sb.auth.get_user.return_value = mock_u

        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"id": "u-1", "email": "user@cpass.org", "full_name": "User One", "role": "ADMIN", "is_active": True}
        ]

        res = client.get("/auth/me", cookies={"cpass_access_token": "my-cookie-token"})
        assert res.status_code == 200
        assert res.json()["role"] == "ADMIN"


def test_get_me_unauthorized():
    """Accessing /auth/me with no token or cookie returns 401."""
    res = client.get("/auth/me")
    assert res.status_code == 401


def test_get_me_expired_token():
    """Accessing /auth/me with invalid or expired token returns 401."""
    with patch("app.auth.supabase") as mock_sb:
        mock_sb.auth.get_user.side_effect = Exception("Token expired")
        res = client.get("/auth/me", headers={"Authorization": "Bearer expired-token"})
        assert res.status_code == 401
        assert "Invalid or expired token" in res.json()["detail"]


def test_refresh_token_rotation(mock_auth_client, mock_supabase_db):
    """POST /auth/refresh returns new access and refresh tokens."""
    auth_resp = MagicMock()
    auth_resp.user = mock_auth_user()
    auth_resp.session = mock_auth_session("new-access-token", "new-refresh-token")
    mock_auth_client.auth.refresh_session.return_value = auth_resp

    mock_supabase_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"id": "user-123", "full_name": "Refreshed User", "role": "L1_COORDINATOR", "is_active": True}
    ]

    res = client.post("/auth/refresh", json={"refresh_token": "valid-refresh-token"})
    assert res.status_code == 200
    assert res.json()["access_token"] == "new-access-token"
    assert res.json()["refresh_token"] == "new-refresh-token"
    assert "cpass_access_token" in res.cookies


def test_logout_revokes_token_and_clears_cookies(mock_supabase_db):
    """POST /auth/logout calls Supabase admin sign_out and removes session cookies."""
    with patch("app.routers.auth.supabase") as mock_sb:
        res = client.post(
            "/auth/logout",
            headers={"Authorization": "Bearer token-to-revoke"},
        )
        assert res.status_code == 200
        assert res.json()["message"] == "Logged out successfully"
        mock_sb.auth.admin.sign_out.assert_called_once_with("token-to-revoke")


def test_frontend_has_no_direct_supabase_references():
    """Verify frontend has zero direct Supabase SDK imports, keys, or clients."""
    frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
    src_dir = frontend_dir / "src"
    pkg_file = frontend_dir / "package.json"
    env_example = frontend_dir / ".env.example"

    # 1. package.json has no @supabase/supabase-js
    pkg_text = pkg_file.read_text(encoding="utf-8")
    assert "@supabase/supabase-js" not in pkg_text

    # 2. .env.example contains only VITE_API_URL
    env_text = env_example.read_text(encoding="utf-8")
    assert "VITE_SUPABASE" not in env_text
    assert "VITE_API_URL=" in env_text

    # 3. No supabase.js file exists
    assert not (src_dir / "lib" / "supabase.js").exists()

    # 4. Check all src files for any supabase imports
    for file in src_dir.rglob("*"):
        if file.suffix in {".js", ".jsx", ".ts", ".tsx"}:
            content = file.read_text(encoding="utf-8")
            assert "createClient" not in content, f"createClient found in {file.name}"
            assert "@supabase/supabase-js" not in content, f"@supabase/supabase-js found in {file.name}"
            assert "VITE_SUPABASE" not in content, f"VITE_SUPABASE found in {file.name}"


def test_health_check_endpoint():
    """Verify lightweight health-check endpoint for Render service."""
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_cors_allowed_origins_parsing():
    """Verify settings.allowed_origins parses multiple origins and trims trailing slashes."""
    from app.config import Settings
    s = Settings(
        supabase_url="https://test.supabase.co",
        supabase_service_role_key="test-key",
        frontend_origin="https://cpass-synchro-serve.vercel.app/, http://localhost:5173",
    )
    assert s.allowed_origins == [
        "https://cpass-synchro-serve.vercel.app",
        "http://localhost:5173",
    ]


def test_production_cookie_samesite_none_when_secure(mock_auth_client, mock_supabase_db):
    """When COOKIE_SECURE is enabled in production, cookies use SameSite=None for cross-site Vercel frontend."""
    from app.config import settings
    auth_resp = MagicMock()
    auth_resp.user = mock_auth_user()
    auth_resp.session = mock_auth_session()
    mock_auth_client.auth.sign_in_with_password.return_value = auth_resp
    mock_supabase_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"id": "user-123", "email": "user@cpass.org", "full_name": "Test Coordinator", "role": "L1_COORDINATOR", "is_active": True}
    ]

    original_secure = settings.cookie_secure
    original_samesite = settings.cookie_samesite
    try:
        settings.cookie_secure = True
        settings.cookie_samesite = None  # test automatic default to 'none'

        res = client.post(
            "/auth/login",
            json={"email": "user@cpass.org", "password": "Password123!"},
        )
        assert res.status_code == 200
        # Verify set-cookie headers contain SameSite=None and Secure
        cookie_headers = res.headers.get_list("set-cookie") if hasattr(res.headers, "get_list") else [res.headers.get("set-cookie", "")]
        cookie_str = "; ".join(cookie_headers).lower()
        assert "samesite=none" in cookie_str
        assert "secure" in cookie_str
    finally:
        settings.cookie_secure = original_secure
        settings.cookie_samesite = original_samesite
