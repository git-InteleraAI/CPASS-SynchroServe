"""FastAPI router for backend-managed authentication with Supabase Auth.

Isolates authentication state from the service-role client.
Enforces profile existence, active status, and server-side role verification.
Issues secure HttpOnly session cookies alongside bearer token responses.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, model_validator

import logging

from ..auth import CurrentUser, clear_user_cache, extract_token, get_current_user, resolve_state, resolve_states
from ..config import settings
from ..db import TRANSIENT_ERRORS, get_auth_client, retry_read_query, supabase

logger = logging.getLogger("cpass.routers.auth")

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(..., description="User email address or username (e.g. tn.cpass, appe, apch)")
    password: str = Field(..., description="User password")
    expected_role: str | None = Field(None, description="Role selected on the client for validation")

class UserProfileResponse(BaseModel):
    id: str
    email: str | None
    full_name: str
    role: str
    assigned_state: str | None = None
    assigned_states: list[str] = Field(default_factory=list)


class UpdateProfileRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100, description="User display name")

    model_config = {
        "extra": "forbid",  # Strictly reject attempts to inject email, role, assigned_state, id, etc.
    }


class LoginResponse(BaseModel):
    user: UserProfileResponse


SPECIAL_CHARACTERS = set("!@#$%^&*")


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, description="Current password")
    new_password: str = Field(..., min_length=1, description="New password")
    confirm_password: str = Field(..., min_length=1, description="Confirm new password")

    model_config = {
        "extra": "forbid",
    }

    @model_validator(mode="after")
    def validate_password_rules(self) -> "ChangePasswordRequest":
        cur = self.current_password
        new = self.new_password
        conf = self.confirm_password

        if not cur or not cur.strip():
            raise ValueError("Current password cannot be empty.")
        if not new or not new.strip():
            raise ValueError("New password cannot be empty.")
        if not conf or not conf.strip():
            raise ValueError("Confirm password cannot be empty.")

        if new != conf:
            raise ValueError("New password and confirm password do not match.")

        if new == cur:
            raise ValueError("New password must be different from current password.")

        if len(new) < 8:
            raise ValueError("New password must be at least 8 characters long.")

        if not any(c.isupper() for c in new):
            raise ValueError("New password must contain at least one uppercase letter (A-Z).")

        if not any(c.islower() for c in new):
            raise ValueError("New password must contain at least one lowercase letter (a-z).")

        if not any(c.isdigit() for c in new):
            raise ValueError("New password must contain at least one numeric digit (0-9).")

        if not any(c in SPECIAL_CHARACTERS for c in new):
            raise ValueError("New password must contain at least one special character (!@#$%^&*).")

        return self


class ChangePasswordResponse(BaseModel):
    status: str = "success"
    message: str = "Password changed successfully."


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
    check client-selected role against DB role, and issue HttpOnly session cookies.
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
    # Allow L4_CEO and L5_CEO interchangeably.
    if payload.expected_role:
        p_role = profile["role"]
        e_role = payload.expected_role
        ceo_roles = {"L4_CEO", "L5_CEO"}
        if p_role != e_role and not (p_role in ceo_roles and e_role in ceo_roles):
            raise HTTPException(403, "This account does not have the selected role.")

    # Use only the explicit CPASS profile assignment for authorization scope.
    # Supports single state string or multi-state assignment.
    raw_states = profile.get("assigned_states") or profile.get("assigned_state")
    resolved_list = resolve_states(raw_states)
    assigned_state = resolved_list[0] if resolved_list else None

    _set_auth_cookies(
        response=response,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_in=session.expires_in,
    )

    return LoginResponse(
        user=UserProfileResponse(
            id=profile["id"],
            email=profile.get("email"),
            full_name=profile["full_name"],
            role=profile["role"],
            assigned_state=assigned_state,
            assigned_states=resolved_list,
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
        assigned_states=user.assigned_states,
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
async def refresh(request: Request, response: Response):
    """Refresh the session using HttpOnly cookie or body token."""
    refresh_token = request.cookies.get("cpass_refresh_token")
    if not refresh_token:
        try:
            body = await request.json()
            if isinstance(body, dict):
                refresh_token = body.get("refresh_token")
        except Exception:
            pass
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
    raw_states = profile.get("assigned_states") or profile.get("assigned_state")
    resolved_list = resolve_states(raw_states)
    assigned_state = resolved_list[0] if resolved_list else None

    return LoginResponse(
        user=UserProfileResponse(
            id=profile["id"],
            email=profile.get("email"),
            full_name=profile["full_name"],
            role=profile["role"],
            assigned_state=assigned_state,
            assigned_states=resolved_list,
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


@router.post("/change-password", response_model=ChangePasswordResponse)
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    user: CurrentUser = Depends(get_current_user),
):
    """Change the authenticated user's password in Supabase Auth.

    1. Verifies the user's current password against Supabase Auth.
    2. Validates that the authenticated Supabase user matches the current CPASS session.
    3. Enforces all password complexity rules (length >= 8, uppercase, lowercase, digit, special character).
    4. Updates the password in Supabase Auth.
    5. Re-authenticates to rotate tokens and update HttpOnly session cookies.
    """
    user_email = user.email
    if not user_email:
        try:
            p_res = retry_read_query(
                lambda: supabase.table("profiles").select("email").eq("id", user.id).limit(1).execute()
            )
            if p_res.data and p_res.data[0].get("email"):
                user_email = p_res.data[0]["email"]
        except Exception:
            pass

    if not user_email:
        raise HTTPException(400, "Unable to resolve email for the authenticated user.")

    auth_client = get_auth_client()

    # Step 1: Verify current password via Supabase Auth sign_in_with_password
    try:
        auth_res = auth_client.auth.sign_in_with_password({
            "email": user_email,
            "password": payload.current_password,
        })
    except HTTPException:
        raise
    except TRANSIENT_ERRORS as exc:
        logger.warning("Transient transport error during current password verification: %s", exc)
        raise HTTPException(
            503,
            "Authentication service temporarily unreachable. Please retry.",
            headers={"Retry-After": "1"},
        )
    except Exception:
        raise HTTPException(401, "Current password is incorrect.")

    if not auth_res or not auth_res.user:
        raise HTTPException(401, "Current password is incorrect.")

    # Step 2: Confirm Supabase UID matches session user ID
    if str(auth_res.user.id) != str(user.id):
        raise HTTPException(403, "Authenticated user does not match the session identity.")

    # Step 3: Update password in Supabase Auth via authenticated client
    try:
        auth_client.auth.update_user({"password": payload.new_password})
    except TRANSIENT_ERRORS as exc:
        logger.warning("Transient error updating password: %s", exc)
        raise HTTPException(
            503,
            "Authentication service temporarily unreachable. Please retry.",
            headers={"Retry-After": "1"},
        )
    except Exception as exc:
        logger.warning("auth.update_user failed, attempting admin update fallback: %s", exc)
        try:
            supabase.auth.admin.update_user_by_id(user.id, {"password": payload.new_password})
        except Exception as admin_exc:
            logger.error("Failed to update password in Supabase: %s", admin_exc)
            raise HTTPException(500, "Failed to update password. Please try again.")

    # Step 4: Re-authenticate with new password to ensure valid session continuity
    try:
        new_auth = auth_client.auth.sign_in_with_password({
            "email": user_email,
            "password": payload.new_password,
        })
        if new_auth and new_auth.session:
            _set_auth_cookies(
                response=response,
                access_token=new_auth.session.access_token,
                refresh_token=new_auth.session.refresh_token,
                expires_in=new_auth.session.expires_in,
            )
    except Exception as reauth_exc:
        logger.warning("Could not refresh session cookies after password update: %s", reauth_exc)

    clear_user_cache()

    return ChangePasswordResponse(
        status="success",
        message="Password changed successfully.",
    )
