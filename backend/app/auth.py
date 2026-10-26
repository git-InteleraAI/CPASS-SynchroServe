from dataclasses import dataclass
import time
from typing import Any

from fastapi import Depends, Header, HTTPException, Request
import httpx

from .db import TRANSIENT_ERRORS, retry_read_query, supabase

ALL_CENTRE_ROLES = {"ADMIN", "L3_LEADER", "L3_COPS", "L4_LEADER", "L4_CEO", "L5_CEO"}
ALL_STATE_ROLES = {"ADMIN", "L3_LEADER", "L3_COPS", "L4_LEADER", "L4_CEO", "L5_CEO"}

# The canonical 12 CPASS master states
ALL_12_STATES: tuple[str, ...] = (
    "ANDHRA PRADESH",
    "GUJARAT",
    "KERALA",
    "MIZORAM",
    "ODISHA",
    "PUDUCHERRY",
    "PUNJAB",
    "RAJASTHAN",
    "TAMIL NADU",
    "TELANGANA",
    "UTTAR PRADESH",
    "WEST BENGAL",
)

STATE_ALIASES: dict[str, str] = {
    # Tamil Nadu
    "tn": "TAMIL NADU",
    "tamilnadu": "TAMIL NADU",
    "tamil nadu": "TAMIL NADU",
    "tamil_nadu": "TAMIL NADU",
    # Telangana
    "ts": "TELANGANA",
    "tg": "TELANGANA",
    "telangana": "TELANGANA",
    # Kerala
    "kl": "KERALA",
    "kerala": "KERALA",
    # Andhra Pradesh
    "ap": "ANDHRA PRADESH",
    "andhra": "ANDHRA PRADESH",
    "andhrapradesh": "ANDHRA PRADESH",
    "andhra pradesh": "ANDHRA PRADESH",
    "andhra_pradesh": "ANDHRA PRADESH",
    # Rajasthan
    "rj": "RAJASTHAN",
    "rajasthan": "RAJASTHAN",
    # Odisha
    "od": "ODISHA",
    "or": "ODISHA",
    "odisha": "ODISHA",
    "orissa": "ODISHA",
    # Gujarat
    "gj": "GUJARAT",
    "gujarat": "GUJARAT",
    # Punjab
    "pb": "PUNJAB",
    "punjab": "PUNJAB",
    # Uttar Pradesh
    "up": "UTTAR PRADESH",
    "uttarpradesh": "UTTAR PRADESH",
    "uttar pradesh": "UTTAR PRADESH",
    "uttar_pradesh": "UTTAR PRADESH",
    # Mizoram
    "mz": "MIZORAM",
    "mizoram": "MIZORAM",
    # Puducherry
    "py": "PUDUCHERRY",
    "pondy": "PUDUCHERRY",
    "puducherry": "PUDUCHERRY",
    "pondicherry": "PUDUCHERRY",
    # West Bengal
    "wb": "WEST BENGAL",
    "westbengal": "WEST BENGAL",
    "west bengal": "WEST BENGAL",
    "west_bengal": "WEST BENGAL",
    # 24 State-Specific PE and CH Account Prefixes
    "appe": "ANDHRA PRADESH",
    "apch": "ANDHRA PRADESH",
    "gjpe": "GUJARAT",
    "gjch": "GUJARAT",
    "klpe": "KERALA",
    "klch": "KERALA",
    "mzpe": "MIZORAM",
    "mzch": "MIZORAM",
    "odpe": "ODISHA",
    "odch": "ODISHA",
    "pype": "PUDUCHERRY",
    "pych": "PUDUCHERRY",
    "pbpe": "PUNJAB",
    "pbch": "PUNJAB",
    "rjpe": "RAJASTHAN",
    "rjch": "RAJASTHAN",
    "tnpe": "TAMIL NADU",
    "tnch": "TAMIL NADU",
    "tspe": "TELANGANA",
    "tsch": "TELANGANA",
    "uppe": "UTTAR PRADESH",
    "upch": "UTTAR PRADESH",
    "wbpe": "WEST BENGAL",
    "wbch": "WEST BENGAL",
}


def resolve_state(val: Any) -> str | None:
    """Normalize and resolve any state string, code, username, or email to a canonical state name."""
    if not val:
        return None
    s = str(val).strip()
    if not s:
        return None
    # Strip email domain if present
    if "@" in s:
        s = s.split("@")[0].strip()
    # Strip .cpass convention (e.g. tn.cpass -> tn)
    if ".cpass" in s.lower():
        s = s.lower().split(".cpass")[0].strip()

    clean = s.lower().replace(" ", "").replace("_", "").replace("-", "")
    if clean in STATE_ALIASES:
        return STATE_ALIASES[clean]
    # Handle role suffixes like appe -> ap, apch -> ap, etc.
    if len(clean) > 2 and (clean.endswith("pe") or clean.endswith("ch")):
        base = clean[:-2]
        if base in STATE_ALIASES:
            return STATE_ALIASES[base]
    for canon in ALL_12_STATES:
        if canon.lower().replace(" ", "") == clean:
            return canon
    return None


@dataclass
class CurrentUser:
    id: str
    email: str | None
    full_name: str
    role: str
    assigned_state: str | None = None

    def __post_init__(self):
        if self.assigned_state:
            self.assigned_state = resolve_state(self.assigned_state)
        elif self.email:
            self.assigned_state = resolve_state(self.email)

    @property
    def sees_all_centres(self) -> bool:
        return self.role in ALL_CENTRE_ROLES

    @property
    def sees_all_states(self) -> bool:
        return self.role in ALL_STATE_ROLES


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


# Short-TTL in-memory cache for validated sessions: token -> (CurrentUser, expiry_monotonic)
_USER_SESSION_CACHE: dict[str, tuple[CurrentUser, float]] = {}
_USER_CACHE_TTL_SECONDS = 45.0


def clear_user_cache():
    """Clear in-memory user session cache (used in tests or on user update)."""
    _USER_SESSION_CACHE.clear()


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
) -> CurrentUser:
    """Validate Supabase access token (from Bearer header or HttpOnly cookie)
    and load the user's active CPASS profile. Role and state are strictly derived from the DB/server.
    """
    token = extract_token(request, authorization)

    # Check fast in-memory cache to avoid redundant remote Supabase calls
    now = time.monotonic()
    cached = _USER_SESSION_CACHE.get(token)
    if cached:
        cached_user, expiry = cached
        if now < expiry:
            return cached_user
        _USER_SESSION_CACHE.pop(token, None)

    # Bounded retry on token verification for transient socket/connection errors
    auth_user = None
    for attempt in range(3):
        try:
            auth_user = supabase.auth.get_user(token).user
            break
        except TRANSIENT_ERRORS as exc:
            if attempt == 2:
                import logging
                logging.getLogger("cpass.auth").warning("Supabase auth transport failed after 3 attempts: %s", exc)
                raise HTTPException(
                    503,
                    "Authentication service temporarily unreachable. Please retry.",
                    headers={"Retry-After": "1"},
                )
            time.sleep(0.1 * (attempt + 1))
        except Exception:
            raise HTTPException(401, "Invalid or expired token")

    if auth_user is None:
        raise HTTPException(401, "Invalid or expired token")

    try:
        res = retry_read_query(
            lambda: supabase.table("profiles").select("*").eq("id", auth_user.id).limit(1).execute()
        )
        rows = res.data or []
    except TRANSIENT_ERRORS as exc:
        import logging
        logging.getLogger("cpass.auth").warning("Supabase profile lookup transport failed: %s", exc)
        raise HTTPException(
            503,
            "User profile service temporarily unreachable. Please retry.",
            headers={"Retry-After": "1"},
        )

    if not rows:
        raise HTTPException(403, "No CPASS profile for this user. Ask an admin to create one.")
    p = rows[0]
    if not p["is_active"]:
        raise HTTPException(403, "This account is disabled.")

    meta = auth_user.user_metadata or {}
    assigned_state = (
        resolve_state(p.get("assigned_state"))
        or resolve_state(p.get("state"))
        or resolve_state(meta.get("assigned_state"))
        or resolve_state(meta.get("state"))
        or resolve_state(p.get("email"))
        or resolve_state(auth_user.email)
    )

    user = CurrentUser(
        id=p["id"],
        email=p.get("email"),
        full_name=p["full_name"],
        role=p["role"],
        assigned_state=assigned_state,
    )

    # Cache valid session
    _USER_SESSION_CACHE[token] = (user, now + _USER_CACHE_TTL_SECONDS)
    return user


def require_roles(*roles: str):
    def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(403, "Your role cannot do this.")
        return user

    return checker


def allowed_states(user: CurrentUser) -> list[str] | None:
    """None = unrestricted (sees all states).
    Otherwise returns list of permitted canonical state names.
    For L1_COORDINATOR and L2_MANAGER: strictly limited to [user.assigned_state] if assigned, else [] (fails closed).
    """
    if user.sees_all_states:
        return None
    if user.role in ("L1_COORDINATOR", "L2_MANAGER"):
        if user.assigned_state:
            return [user.assigned_state]
        return []  # Fail-closed: unassigned coordinator or manager sees zero states
    if user.assigned_state:
        return [user.assigned_state]
    return None


def allowed_tc_ids(user: CurrentUser) -> list[int] | None:
    """None = all centres permitted within user's permitted state(s).
    Otherwise explicit list of permitted tc_ids.
    Fails closed: if user is not in ALL_CENTRE_ROLES and has no state or centre assignments, returns [].
    """
    if user.sees_all_centres:
        return None
    try:
        rows = supabase.table("user_centres").select("tc_id").eq("user_id", user.id).execute().data
        if rows and isinstance(rows, list) and isinstance(rows[0], dict) and "tc_id" in rows[0]:
            return [r["tc_id"] for r in rows]
    except Exception:
        pass

    # If user has a valid assigned state, centre access is governed by state boundaries
    if user.assigned_state:
        return None

    # Missing state and centre assignments fail closed
    return []


def get_candidate_state(cand: dict[str, Any]) -> str | None:
    """Extract and resolve canonical state name from candidate record.
    
    Training Centre State (tc_state_name) is the authoritative source of truth
    for state ownership and L1 coordinator scoping.
    Fails safely if tc_state_name is missing or invalid.
    """
    tc_st = cand.get("tc_state_name")
    if tc_st:
        resolved = resolve_state(tc_st)
        if resolved:
            return resolved
        import logging
        logging.getLogger("cpass.auth").warning(
            "Candidate %s has unresolvable tc_state_name: %r", cand.get("candidate_id"), tc_st
        )
    return None


def check_candidate_access(user: CurrentUser, cand: dict[str, Any]) -> None:
    """Verify that user is authorized to view or edit this candidate.
    Enforces state-based authorization for L1 Placement Coordinators and any state-scoped user.
    Fails closed on missing or mismatched assignments.
    """
    permitted_st = allowed_states(user)
    if permitted_st is not None:
        cand_state = get_candidate_state(cand)
        if not cand_state or cand_state not in permitted_st:
            raise HTTPException(403, "You do not have access to candidates in this state.")

    permitted_tcs = allowed_tc_ids(user)
    if permitted_tcs is not None:
        tc_id = cand.get("tc_id")
        if tc_id is not None and tc_id not in permitted_tcs:
            raise HTTPException(403, "You are not assigned to this candidate's training centre.")


