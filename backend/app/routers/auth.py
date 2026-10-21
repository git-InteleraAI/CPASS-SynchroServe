"""FastAPI router for backend-managed authentication with Supabase Auth.

Isolates authentication state from the service-role client.
Enforces profile existence, active status, and server-side role verification.
Issues secure HttpOnly session cookies alongside bearer token responses.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..auth import CurrentUser, extract_token, get_current_user
from ..config import settings
from ..db import get_auth_client, supabase

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")
    expected_role: str | None = Field(None, description="Role selected on the client for validation")


class RefreshRequest(BaseModel):
    refresh_token: str | None = Field(None, description="Refresh token if not sent via cookie")


class UserProfileResponse(BaseModel):
    id: str
    email: str | None
    full_name: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str | None
    token_type: str = "bearer"
    expires_in: int | None
    expires_at: int | None
    user: UserProfileResponse


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str | None, expires_in: int | None):
    """Set secure HttpOnly cookies for session management."""
    max_age_access = expires_in or 3600
    response.set_cookie(
        key="cpass_access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=max_age_access,
        path="/",
    )
    if refresh_token:
        response.set_cookie(
            key="cpass_refresh_token",
            value=refresh_token,
            httponly=True,
            samesite="lax",
            secure=settings.cookie_secure,
            max_age=30 * 86400,  # 30 days
            path="/",
        )


def _clear_auth_cookies(response: Response):
    """Clear session cookies."""
    response.delete_cookie(key="cpass_access_token", path="/")
    response.delete_cookie(key="cpass_refresh_token", path="/")


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response):
    """Authenticate user with Supabase Auth via backend, verify active CPASS profile,

    check client-selected role against DB role, and issue session cookies & tokens.
    """
    auth_client = get_auth_client()

    try:
        auth_res = auth_client.auth.sign_in_with_password({
            "email": payload.email.strip(),
            "password": payload.password,
        })
    except Exception:
        raise HTTPException(401, "Email or password is incorrect.")

    if not auth_res or not auth_res.user or not auth_res.session:
        raise HTTPException(401, "Email or password is incorrect.")

    auth_user = auth_res.user
    session = auth_res.session

    # Verify CPASS profile in database using server service-role client
    profile_rows = (
        supabase.table("profiles")
        .select("*")
        .eq("id", auth_user.id)
        .limit(1)
        .execute()
        .data
    )
    if not profile_rows:
        raise HTTPException(403, "No CPASS profile for this user. Ask an admin to create one.")

    profile = profile_rows[0]
    if not profile.get("is_active", True):
        raise HTTPException(403, "This account is disabled.")

    # The role picked on the login screen is only a check: the real role always comes from the backend.
    if payload.expected_role and profile["role"] != payload.expected_role:
        raise HTTPException(403, "This account does not have the selected role.")

    _set_auth_cookies(
        response=response,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_in=session.expires_in,
    )

    return LoginResponse(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        token_type="bearer",
        expires_in=session.expires_in,
        expires_at=session.expires_at,
        user=UserProfileResponse(
            id=profile["id"],
            email=profile.get("email"),
            full_name=profile["full_name"],
            role=profile["role"],
        ),
    )


@router.get("/me", response_model=UserProfileResponse)
def me(user: CurrentUser = Depends(get_current_user)):
    """Return the profile of the currently authenticated user."""
    return UserProfileResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
    )


@router.post("/refresh", response_model=LoginResponse)
def refresh(request: Request, response: Response, payload: RefreshRequest | None = None):
    """Refresh session token using refresh token from payload or HttpOnly cookie."""
    refresh_token = (payload and payload.refresh_token) or request.cookies.get("cpass_refresh_token")
    if not refresh_token:
        raise HTTPException(401, "Missing refresh token.")

    auth_client = get_auth_client()
    try:
        auth_res = auth_client.auth.refresh_session(refresh_token)
    except Exception:
        raise HTTPException(401, "Invalid or expired refresh token.")

    if not auth_res or not auth_res.user or not auth_res.session:
        raise HTTPException(401, "Invalid or expired refresh token.")

    auth_user = auth_res.user
    session = auth_res.session

    profile_rows = (
        supabase.table("profiles")
        .select("*")
        .eq("id", auth_user.id)
        .limit(1)
        .execute()
        .data
    )
    if not profile_rows:
        raise HTTPException(403, "No CPASS profile for this user.")
    profile = profile_rows[0]
    if not profile.get("is_active", True):
        raise HTTPException(403, "This account is disabled.")

    _set_auth_cookies(
        response=response,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_in=session.expires_in,
    )

    return LoginResponse(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        token_type="bearer",
        expires_in=session.expires_in,
        expires_at=session.expires_at,
        user=UserProfileResponse(
            id=profile["id"],
            email=profile.get("email"),
            full_name=profile["full_name"],
            role=profile["role"],
        ),
    )


@router.post("/logout")
def logout(request: Request, response: Response):
    """Revoke session token on Supabase and clear session cookies."""
    try:
        token = extract_token(request)
        # Revoke the session via Supabase admin endpoint
        supabase.auth.admin.sign_out(token)
    except Exception:
        pass  # Even if token is already expired or missing, proceed with cookie cleanup

    _clear_auth_cookies(response)
    return {"message": "Logged out successfully"}
