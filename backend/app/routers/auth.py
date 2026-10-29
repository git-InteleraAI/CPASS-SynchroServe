"""FastAPI router for backend-managed authentication with Supabase Auth.

Isolates authentication state from the service-role client.
Enforces profile existence, active status, and server-side role verification.
Issues secure HttpOnly session cookies alongside bearer token responses.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

import logging

from ..auth import CurrentUser, clear_user_cache, extract_token, get_current_user, resolve_state
from ..config import settings
from ..db import TRANSIENT_ERRORS, get_auth_client, retry_read_query, supabase

logger = logging.getLogger("cpass.routers.auth")

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(..., description="User email address or username (e.g. tn.cpass, appe, apch)")
    password: str = Field(..., description="User password")
    expected_role: str | None = Field(None, description="Role selected on the client for validation")


class RefreshRequest(BaseModel):
    refresh_token: str | None = Field(None, description="Refresh token if not sent via cookie")


class UserProfileResponse(BaseModel):
    id: str
    email: str | None
    full_name: str
    role: str
    assigned_state: str | None = None


class UpdateProfileRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100, description="User display name")

    model_config = {
        "extra": "forbid",  # Strictly reject attempts to inject email, role, assigned_state, id, etc.
    }


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
    samesite = (settings.cookie_samesite or ("none" if settings.cookie_secure else "lax")).lower()
    response.set_cookie(
        key="cpass_access_token",
        value=access_token,
        httponly=True,
        samesite=samesite,
        secure=settings.cookie_secure,
        max_age=max_age_access,
        path="/",
    )
    if refresh_token:
        response.set_cookie(
            key="cpass_refresh_token",
            value=refresh_token,
            httponly=True,
            samesite=samesite,
            secure=settings.cookie_secure,
            max_age=30 * 86400,  # 30 days
            path="/",
        )


def _clear_auth_cookies(response: Response):
    """Clear session cookies."""
    samesite = (settings.cookie_samesite or ("none" if settings.cookie_secure else "lax")).lower()
    response.delete_cookie(key="cpass_access_token", path="/", samesite=samesite, secure=settings.cookie_secure)
    response.delete_cookie(key="cpass_refresh_token", path="/", samesite=samesite, secure=settings.cookie_secure)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response):
    """Authenticate user with Supabase Auth via backend, verify active CPASS profile,

    check client-selected role against DB role, and issue session cookies & tokens.
    """
    auth_client = get_auth_client()

    raw_ident = payload.email.strip()
    login_email = raw_ident
    if "@" not in login_email:
        clean_ident = raw_ident.lower()
        if clean_ident.endswith("pe") or clean_ident.endswith("ch"):
            login_email = f"{login_email}@synchroserve.com"
        else:
            login_email = f"{login_email}@synchroserve.in"

    try:
        auth_res = auth_client.auth.sign_in_with_password({
            "email": login_email,
            "password": payload.password,
        })
    except HTTPException:
        raise
    except TRANSIENT_ERRORS as exc:
        logger.warning("Transient error signing in user: %s", exc)
        raise HTTPException(
            503,
            "Authentication service temporarily unreachable. Please retry.",
            headers={"Retry-After": "1"},
        )
    except Exception:
        raise HTTPException(401, "Email or password is incorrect.")

    if not auth_res or not auth_res.user or not auth_res.session:
        raise HTTPException(401, "Email or password is incorrect.")

    auth_user = auth_res.user
    session = auth_res.session

    # Verify CPASS profile in database using server service-role client
    try:
        res = retry_read_query(
            lambda: supabase.table("profiles")
            .select("*")
            .eq("id", auth_user.id)
            .limit(1)
            .execute()
        )
        profile_rows = res.data or []
    except TRANSIENT_ERRORS as exc:
        logger.warning("Transient error fetching profile for user %s: %s", auth_user.id, exc)
        raise HTTPException(
            503,
            "User profile service temporarily unreachable. Please retry.",
            headers={"Retry-After": "1"},
        )
    if not profile_rows:
        raise HTTPException(403, "No CPASS profile for this user. Ask an admin to create one.")

    profile = profile_rows[0]
    if not profile.get("is_active", True):
        raise HTTPException(403, "This account is disabled.")

    # The role picked on the login screen is only a check: the real role always comes from the backend.
    if payload.expected_role and profile["role"] != payload.expected_role:
        raise HTTPException(403, "This account does not have the selected role.")

    # Use only the explicit CPASS profile assignment for authorization scope.
    # Email/username and auth metadata are not trusted assignment sources.
    assigned_state = resolve_state(profile.get("assigned_state"))

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
            assigned_state=assigned_state,
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
        assigned_state=user.assigned_state,
    )


@router.patch("/profile", response_model=UserProfileResponse)
def update_profile(
    payload: UpdateProfileRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Update only the display name (full_name) of the authenticated user.
    Email, role, assigned_state, and authorization permissions are strictly read-only and immutable.
    """
    clean_name = payload.full_name.strip()
    if not clean_name:
        raise HTTPException(400, "Display name cannot be empty.")
    if len(clean_name) < 2:
        raise HTTPException(400, "Display name must be at least 2 characters.")
    if len(clean_name) > 100:
        raise HTTPException(400, "Display name must not exceed 100 characters.")

    # Update in database table public.profiles
    res = supabase.table("profiles").update({"full_name": clean_name}).eq("id", user.id).execute()
    if not res.data:
        raise HTTPException(404, "Profile not found.")

    # Synchronize Supabase Auth user_metadata
    try:
        supabase.auth.admin.update_user_by_id(user.id, {"user_metadata": {"full_name": clean_name}})
    except Exception as exc:
        logger.warning("Could not update auth user_metadata for %s: %s", user.id, exc)

    # Invalidate fast in-memory session cache so subsequent requests immediately reflect the updated name
    clear_user_cache()

    return UserProfileResponse(
        id=user.id,
        email=user.email,
        full_name=clean_name,
        role=user.role,
        assigned_state=user.assigned_state,
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
    except HTTPException:
        raise
    except TRANSIENT_ERRORS as exc:
        logger.warning("Transient error refreshing token: %s", exc)
        raise HTTPException(
            503,
            "Authentication service temporarily unreachable. Please retry.",
            headers={"Retry-After": "1"},
        )
    except Exception:
        raise HTTPException(401, "Invalid or expired refresh token.")

    if not auth_res or not auth_res.user or not auth_res.session:
        raise HTTPException(401, "Invalid or expired refresh token.")

    auth_user = auth_res.user
    session = auth_res.session

    try:
        res = retry_read_query(
            lambda: supabase.table("profiles")
            .select("*")
            .eq("id", auth_user.id)
            .limit(1)
            .execute()
        )
        profile_rows = res.data or []
    except TRANSIENT_ERRORS as exc:
        logger.warning("Transient error fetching profile on refresh: %s", exc)
        raise HTTPException(
            503,
            "User profile service temporarily unreachable. Please retry.",
            headers={"Retry-After": "1"},
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

    # Keep refresh behavior consistent with login: profile assignment only.
    assigned_state = resolve_state(profile.get("assigned_state"))

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
            assigned_state=assigned_state,
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
