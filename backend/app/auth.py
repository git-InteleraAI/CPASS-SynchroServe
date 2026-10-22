from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request

from .db import supabase

ALL_CENTRE_ROLES = {"ADMIN", "L3_LEADER"}


@dataclass
class CurrentUser:
    id: str
    email: str | None
    full_name: str
    role: str

    @property
    def sees_all_centres(self) -> bool:
        return self.role in ALL_CENTRE_ROLES


def extract_token(request: Request, authorization: str | None = None) -> str:
    """Extract token from Authorization header or HttpOnly cookie."""
    auth_header = authorization or request.headers.get("authorization") or request.headers.get("Authorization")
    if auth_header and isinstance(auth_header, str) and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        if token:
            return token

    cookie_token = request.cookies.get("cpass_access_token")
    if cookie_token:
        return cookie_token.strip()

    raise HTTPException(401, "Missing authentication token")


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
) -> CurrentUser:
    """Validate Supabase access token (from Bearer header or HttpOnly cookie)

    and load the user's active CPASS profile. Role is strictly derived from the DB.
    """
    token = extract_token(request, authorization)

    try:
        auth_user = supabase.auth.get_user(token).user
    except Exception:
        raise HTTPException(401, "Invalid or expired token")
    if auth_user is None:
        raise HTTPException(401, "Invalid or expired token")

    rows = supabase.table("profiles").select("*").eq("id", auth_user.id).limit(1).execute().data
    if not rows:
        raise HTTPException(403, "No CPASS profile for this user. Ask an admin to create one.")
    p = rows[0]
    if not p["is_active"]:
        raise HTTPException(403, "This account is disabled.")
    return CurrentUser(id=p["id"], email=p.get("email"), full_name=p["full_name"], role=p["role"])


def require_roles(*roles: str):
    def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(403, "Your role cannot do this.")
        return user

    return checker


def allowed_tc_ids(user: CurrentUser) -> list[int] | None:
    """None = all centres. Otherwise the centres assigned to this user."""
    if user.sees_all_centres:
        return None
    try:
        rows = supabase.table("user_centres").select("tc_id").eq("user_id", user.id).execute().data
        if rows:
            return [r["tc_id"] for r in rows]
    except Exception:
        pass
    return None
