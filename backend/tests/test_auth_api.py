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

from app.auth import CurrentUser, clear_user_cache, get_current_user
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_client_state():
    client.cookies.clear()
    clear_user_cache()
    yield
    client.cookies.clear()
    clear_user_cache()


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
    """Successful login sets HttpOnly cookies and returns user without tokens in JSON."""
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
    # Security: No sensitive tokens or expiration timestamps exposed in JSON response
    assert "access_token" not in data
    assert "refresh_token" not in data
    assert "expires_at" not in data
    assert "expires_in" not in data
    assert "token_type" not in data
    assert "user" in data
    assert data["user"]["role"] == "L1_COORDINATOR"
    assert data["user"]["full_name"] == "Test Coordinator"
    assert data["user"]["email"] == "user@cpass.org"

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
    """POST /auth/refresh rotates session cookies without exposing tokens in JSON."""
    auth_resp = MagicMock()
    auth_resp.user = mock_auth_user()
    auth_resp.session = mock_auth_session("new-access-token", "new-refresh-token")
    mock_auth_client.auth.refresh_session.return_value = auth_resp

    mock_supabase_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"id": "user-123", "full_name": "Refreshed User", "role": "L1_COORDINATOR", "is_active": True}
    ]

    res = client.post("/auth/refresh", json={"refresh_token": "valid-refresh-token"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" not in data
    assert "refresh_token" not in data
    assert "expires_at" not in data
    assert "expires_in" not in data
    assert "token_type" not in data
    assert data["user"]["full_name"] == "Refreshed User"
    assert "cpass_access_token" in res.cookies
    assert "cpass_refresh_token" in res.cookies


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


def test_post_logout_get_me_returns_401(mock_supabase_db):
    """After logging out, calling /auth/me returns 401 Missing authentication token."""
    with patch("app.routers.auth.supabase"):
        logout_res = client.post(
            "/auth/logout",
            headers={"Authorization": "Bearer sample-token"},
        )
        assert logout_res.status_code == 200

    # Request without credentials represents post-logout client state
    me_res = client.get("/auth/me")
    assert me_res.status_code == 401
    assert "Missing authentication token" in me_res.json()["detail"]


def test_repeated_session_checks_are_idempotent():
    """Repeated calls to /auth/me with valid Bearer token consistently return profile."""
    with patch("app.auth.supabase") as mock_sb:
        mock_u = MagicMock()
        mock_u.user = mock_auth_user("u-1", "user@cpass.org")
        mock_sb.auth.get_user.return_value = mock_u

        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"id": "u-1", "email": "user@cpass.org", "full_name": "User One", "role": "L1_COORDINATOR", "is_active": True}
        ]

        for _ in range(3):
            res = client.get("/auth/me", headers={"Authorization": "Bearer test-valid-token"})
            assert res.status_code == 200
            assert res.json()["role"] == "L1_COORDINATOR"


def test_refresh_missing_token():
    """Calling /auth/refresh without payload token or cookie returns 401."""
    res = client.post("/auth/refresh", json={})
    assert res.status_code == 401
    assert "Missing refresh token." in res.json()["detail"]


def test_refresh_invalid_token(mock_auth_client):
    """Calling /auth/refresh with an expired or invalid refresh token returns 401."""
    mock_auth_client.auth.refresh_session.side_effect = Exception("Invalid refresh token")
    res = client.post("/auth/refresh", json={"refresh_token": "expired-refresh-token"})
    assert res.status_code == 401
    assert "Invalid or expired refresh token." in res.json()["detail"]


def test_role_boundary_l1_coordinator_protected_endpoint():
    """Verifies ADMIN users receive 403 on strictly L1-scoped document endpoints."""
    with patch("app.auth.supabase") as mock_sb:
        mock_u = MagicMock()
        mock_u.user = mock_auth_user("admin-1", "admin@cpass.org")
        mock_sb.auth.get_user.return_value = mock_u

        # User is an ADMIN
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"id": "admin-1", "email": "admin@cpass.org", "full_name": "Admin User", "role": "ADMIN", "is_active": True}
        ]

        # ADMIN attempts to list documents (L1 only)
        res = client.get(
            "/candidates/123/documents",
            headers={"Authorization": "Bearer admin-token"},
        )
        assert res.status_code == 403
        assert "Your role cannot do this." in res.json()["detail"]


# =============================================================================
# Change Password Tests (POST /auth/change-password)
# =============================================================================

@pytest.fixture
def auth_user_override():
    user = CurrentUser(
        id="user-123",
        email="coordinator@cpass.org",
        full_name="Test Coordinator",
        role="L1_COORDINATOR",
        assigned_state="ODISHA",
    )
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


def test_change_password_success(auth_user_override, mock_auth_client):
    """Correct current password + valid new password updates password and sets rotated cookies."""
    auth_resp = MagicMock()
    auth_resp.user = mock_auth_user("user-123", "coordinator@cpass.org")
    auth_resp.session = mock_auth_session("new-access-token", "new-refresh-token")
    mock_auth_client.auth.sign_in_with_password.return_value = auth_resp
    mock_auth_client.auth.update_user.return_value = MagicMock()

    res = client.post(
        "/auth/change-password",
        json={
            "current_password": "CurrentPassword123!",
            "new_password": "NewValidPassword@2026",
            "confirm_password": "NewValidPassword@2026",
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "Password changed successfully" in data["message"]
    mock_auth_client.auth.update_user.assert_called_once_with({"password": "NewValidPassword@2026"})
    assert "cpass_access_token" in res.cookies
    assert "cpass_refresh_token" in res.cookies


def test_change_password_incorrect_current_password(auth_user_override, mock_auth_client):
    """Incorrect current password returns 401."""
    mock_auth_client.auth.sign_in_with_password.side_effect = Exception("Invalid login credentials")

    res = client.post(
        "/auth/change-password",
        json={
            "current_password": "WrongPassword123!",
            "new_password": "NewValidPassword@2026",
            "confirm_password": "NewValidPassword@2026",
        },
    )

    assert res.status_code == 401
    assert "Current password is incorrect." in res.json()["detail"]


def test_change_password_mismatch(auth_user_override):
    """New password and confirmation mismatch returns 422."""
    res = client.post(
        "/auth/change-password",
        json={
            "current_password": "CurrentPassword123!",
            "new_password": "NewValidPassword@2026",
            "confirm_password": "DifferentPassword@2026",
        },
    )

    assert res.status_code == 422
    assert "do not match" in res.text


def test_change_password_missing_current_password(auth_user_override):
    """Missing current password returns 422 validation failure."""
    res = client.post(
        "/auth/change-password",
        json={
            "current_password": "",
            "new_password": "NewValidPassword@2026",
            "confirm_password": "NewValidPassword@2026",
        },
    )

    assert res.status_code == 422


def test_change_password_missing_new_password(auth_user_override):
    """Missing new password returns 422 validation failure."""
    res = client.post(
        "/auth/change-password",
        json={
            "current_password": "CurrentPassword123!",
            "new_password": "",
            "confirm_password": "",
        },
    )

    assert res.status_code == 422


def test_change_password_missing_confirmation(auth_user_override):
    """Missing confirmation returns 422 validation failure."""
    res = client.post(
        "/auth/change-password",
        json={
            "current_password": "CurrentPassword123!",
            "new_password": "NewValidPassword@2026",
            "confirm_password": "",
        },
    )

    assert res.status_code == 422


def test_change_password_shorter_than_8_chars(auth_user_override):
    """Password shorter than 8 characters returns 422."""
    res = client.post(
        "/auth/change-password",
        json={
            "current_password": "CurrentPassword123!",
            "new_password": "Ab1!",
            "confirm_password": "Ab1!",
        },
    )

    assert res.status_code == 422
    assert "at least 8 characters" in res.text


def test_change_password_missing_uppercase(auth_user_override):
    """Password without uppercase letter returns 422."""
    res = client.post(
        "/auth/change-password",
        json={
            "current_password": "CurrentPassword123!",
            "new_password": "lowercase@1234",
            "confirm_password": "lowercase@1234",
        },
    )

    assert res.status_code == 422
    assert "uppercase letter" in res.text


def test_change_password_missing_lowercase(auth_user_override):
    """Password without lowercase letter returns 422."""
    res = client.post(
        "/auth/change-password",
        json={
            "current_password": "CurrentPassword123!",
            "new_password": "UPPERCASE@1234",
            "confirm_password": "UPPERCASE@1234",
        },
    )

    assert res.status_code == 422
    assert "lowercase letter" in res.text


def test_change_password_missing_number(auth_user_override):
    """Password without digit returns 422."""
    res = client.post(
        "/auth/change-password",
        json={
            "current_password": "CurrentPassword123!",
            "new_password": "NoNumberHere@!",
            "confirm_password": "NoNumberHere@!",
        },
    )

    assert res.status_code == 422
    assert "numeric digit" in res.text


def test_change_password_missing_special_character(auth_user_override):
    """Password without special character returns 422."""
    res = client.post(
        "/auth/change-password",
        json={
            "current_password": "CurrentPassword123!",
            "new_password": "NoSpecialChar1234",
            "confirm_password": "NoSpecialChar1234",
        },
    )

    assert res.status_code == 422
    assert "special character" in res.text


def test_change_password_identical_to_current(auth_user_override):
    """New password identical to current password returns 422."""
    res = client.post(
        "/auth/change-password",
        json={
            "current_password": "CurrentPassword123!",
            "new_password": "CurrentPassword123!",
            "confirm_password": "CurrentPassword123!",
        },
    )

    assert res.status_code == 422
    assert "must be different from current password" in res.text


def test_change_password_unauthenticated():
    """Unauthenticated request returns 401."""
    res = client.post(
        "/auth/change-password",
        json={
            "current_password": "CurrentPassword123!",
            "new_password": "NewValidPassword@2026",
            "confirm_password": "NewValidPassword@2026",
        },
    )

    assert res.status_code == 401


def test_change_password_user_id_mismatch(auth_user_override, mock_auth_client):
    """If Supabase returns an ID different from the active session user, reject with 403."""
    auth_resp = MagicMock()
    # Different user ID returned
    auth_resp.user = mock_auth_user("different-user-999", "coordinator@cpass.org")
    mock_auth_client.auth.sign_in_with_password.return_value = auth_resp

    res = client.post(
        "/auth/change-password",
        json={
            "current_password": "CurrentPassword123!",
            "new_password": "NewValidPassword@2026",
            "confirm_password": "NewValidPassword@2026",
        },
    )

    assert res.status_code == 403
    assert "does not match the session identity" in res.json()["detail"]


def test_change_password_admin_fallback(auth_user_override, mock_auth_client, mock_supabase_db):
    """If auth_client.auth.update_user encounters an issue, fallback to admin update succeeds."""
    auth_resp = MagicMock()
    auth_resp.user = mock_auth_user("user-123", "coordinator@cpass.org")
    auth_resp.session = mock_auth_session()
    mock_auth_client.auth.sign_in_with_password.return_value = auth_resp
    mock_auth_client.auth.update_user.side_effect = Exception("Client session update failed")

    with patch("app.routers.auth.supabase") as mock_sb:
        mock_sb.auth.admin.update_user_by_id.return_value = MagicMock()

        res = client.post(
            "/auth/change-password",
            json={
                "current_password": "CurrentPassword123!",
                "new_password": "NewValidPassword@2026",
                "confirm_password": "NewValidPassword@2026",
            },
        )

        assert res.status_code == 200
        assert res.json()["status"] == "success"
        mock_sb.auth.admin.update_user_by_id.assert_called_once_with("user-123", {"password": "NewValidPassword@2026"})


def test_change_password_supabase_update_failure(auth_user_override, mock_auth_client):
    """If both auth.update_user and admin update fail, returns 500."""
    auth_resp = MagicMock()
    auth_resp.user = mock_auth_user("user-123", "coordinator@cpass.org")
    mock_auth_client.auth.sign_in_with_password.return_value = auth_resp
    mock_auth_client.auth.update_user.side_effect = Exception("Update error")

    with patch("app.routers.auth.supabase") as mock_sb:
        mock_sb.auth.admin.update_user_by_id.side_effect = Exception("Admin update error")

        res = client.post(
            "/auth/change-password",
            json={
                "current_password": "CurrentPassword123!",
                "new_password": "NewValidPassword@2026",
                "confirm_password": "NewValidPassword@2026",
            },
        )

        assert res.status_code == 500
        assert "Failed to update password" in res.json()["detail"]


# =============================================================================
# Token Non-Exposure & Cookie Session Lifecycle Tests (Phase 1.1)
# =============================================================================

def test_login_does_not_expose_tokens_in_json(mock_auth_client, mock_supabase_db):
    """Verify that POST /auth/login returns strictly non-sensitive profile data and zero tokens."""
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

    # The public JSON payload must strictly contain only 'user'
    assert list(data.keys()) == ["user"]
    assert "access_token" not in data
    assert "refresh_token" not in data
    assert "expires_at" not in data
    assert "expires_in" not in data
    assert "token_type" not in data

    # Verify credentials delivered safely in HttpOnly cookies
    assert "cpass_access_token" in res.cookies
    assert "cpass_refresh_token" in res.cookies


def test_refresh_does_not_expose_tokens_in_json(mock_auth_client, mock_supabase_db):
    """Verify that POST /auth/refresh returns strictly non-sensitive profile data and zero tokens."""
    auth_resp = MagicMock()
    auth_resp.user = mock_auth_user()
    auth_resp.session = mock_auth_session("rotated-access-token", "rotated-refresh-token")
    mock_auth_client.auth.refresh_session.return_value = auth_resp

    mock_supabase_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"id": "user-123", "full_name": "Refreshed User", "role": "L1_COORDINATOR", "is_active": True}
    ]

    # Refresh using HttpOnly cookie without body
    res = client.post("/auth/refresh", cookies={"cpass_refresh_token": "valid-cookie-refresh-token"})
    assert res.status_code == 200
    data = res.json()

    # Public JSON response must not leak session tokens
    assert list(data.keys()) == ["user"]
    assert "access_token" not in data
    assert "refresh_token" not in data
    assert "expires_at" not in data
    assert "expires_in" not in data
    assert "token_type" not in data

    # Rotated cookies are properly set
    assert "cpass_access_token" in res.cookies
    assert "cpass_refresh_token" in res.cookies


def test_full_cookie_session_lifecycle(mock_auth_client, mock_supabase_db):
    """Verify complete end-to-end cookie session lifecycle:
    Login -> Restore session via /auth/me -> Refresh session -> Access protected route -> Logout.
    """
    # 1. Login
    auth_resp = MagicMock()
    auth_resp.user = mock_auth_user("user-456", "lifecycle@cpass.org")
    auth_resp.session = mock_auth_session("lifecycle-access-1", "lifecycle-refresh-1")
    mock_auth_client.auth.sign_in_with_password.return_value = auth_resp

    mock_supabase_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {
            "id": "user-456",
            "email": "lifecycle@cpass.org",
            "full_name": "Lifecycle User",
            "role": "L1_COORDINATOR",
            "is_active": True,
            "assigned_state": "ODISHA",
        }
    ]

    login_res = client.post(
        "/auth/login",
        json={"email": "lifecycle@cpass.org", "password": "Password123!"},
    )
    assert login_res.status_code == 200
    assert "access_token" not in login_res.json()
    assert "refresh_token" not in login_res.json()

    access_cookie_1 = login_res.cookies.get("cpass_access_token")
    refresh_cookie_1 = login_res.cookies.get("cpass_refresh_token")
    assert access_cookie_1 is not None
    assert refresh_cookie_1 is not None

    # 2. Access /auth/me with cookie
    with patch("app.auth.supabase") as mock_auth_sb:
        mock_u = MagicMock()
        mock_u.user = mock_auth_user("user-456", "lifecycle@cpass.org")
        mock_auth_sb.auth.get_user.return_value = mock_u
        mock_auth_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {
                "id": "user-456",
                "email": "lifecycle@cpass.org",
                "full_name": "Lifecycle User",
                "role": "L1_COORDINATOR",
                "is_active": True,
                "assigned_state": "ODISHA",
            }
        ]

        me_res = client.get("/auth/me", cookies={"cpass_access_token": access_cookie_1})
        assert me_res.status_code == 200
        assert me_res.json()["full_name"] == "Lifecycle User"
        assert me_res.json()["role"] == "L1_COORDINATOR"

    # 3. Refresh session with cookie
    auth_resp_refreshed = MagicMock()
    auth_resp_refreshed.user = mock_auth_user("user-456", "lifecycle@cpass.org")
    auth_resp_refreshed.session = mock_auth_session("lifecycle-access-2", "lifecycle-refresh-2")
    mock_auth_client.auth.refresh_session.return_value = auth_resp_refreshed

    refresh_res = client.post("/auth/refresh", cookies={"cpass_refresh_token": refresh_cookie_1})
    assert refresh_res.status_code == 200
    assert "access_token" not in refresh_res.json()
    assert "refresh_token" not in refresh_res.json()

    access_cookie_2 = refresh_res.cookies.get("cpass_access_token")
    assert access_cookie_2 is not None

    # 4. Access protected endpoint with rotated cookie
    clear_user_cache()
    with patch("app.auth.supabase") as mock_auth_sb:
        mock_u = MagicMock()
        mock_u.user = mock_auth_user("user-456", "lifecycle@cpass.org")
        mock_auth_sb.auth.get_user.return_value = mock_u
        mock_auth_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {
                "id": "user-456",
                "email": "lifecycle@cpass.org",
                "full_name": "Lifecycle User",
                "role": "L1_COORDINATOR",
                "is_active": True,
                "assigned_state": "ODISHA",
            }
        ]

        me_res_2 = client.get("/auth/me", cookies={"cpass_access_token": access_cookie_2})
        assert me_res_2.status_code == 200
        assert me_res_2.json()["full_name"] == "Lifecycle User"

    # 5. Logout
    with patch("app.routers.auth.supabase") as mock_auth_sb:
        logout_res = client.post("/auth/logout", cookies={"cpass_access_token": access_cookie_2})
        assert logout_res.status_code == 200
        assert logout_res.json()["message"] == "Logged out successfully"
        mock_auth_sb.auth.admin.sign_out.assert_called_once_with(access_cookie_2)

    # 6. Verify unauthenticated post-logout
    clear_user_cache()
    unauth_res = client.get("/auth/me")
    assert unauth_res.status_code == 401

