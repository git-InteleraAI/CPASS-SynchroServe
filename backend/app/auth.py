import base64
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import heapq
import json
import logging
import threading
import time
from typing import Any

from fastapi import Depends, Header, HTTPException, Request
import httpx

from .db import TRANSIENT_ERRORS, retry_read_query, supabase

logger = logging.getLogger("cpass.auth")

ALL_CENTRE_ROLES = {"ADMIN", "L3_LEADER", "L3_COPS", "L4_LEADER", "L4_CEO", "L5_CEO"}
ALL_STATE_ROLES = {"ADMIN", "L3_LEADER", "L3_COPS", "L4_CEO", "L5_CEO"}

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
    "pun": "PUNJAB",
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


def resolve_states(val: Any) -> list[str]:
    """Normalize and resolve any state string, list, or comma-separated string to a list of canonical state names."""
    if not val:
        return []
    items: list[str] = []
    if isinstance(val, (list, tuple, set)):
        for item in val:
            if item:
                items.extend(str(item).split(","))
    elif isinstance(val, str):
        items = val.split(",")
    else:
        items = [str(val)]

    resolved: set[str] = set()
    for item in items:
        st = resolve_state(item.strip())
        if st:
            resolved.add(st)
    return sorted(resolved)


@dataclass
class CurrentUser:
    id: str
    email: str | None
    full_name: str
    role: str
    assigned_state: str | None = None
    assigned_states: list[str] = field(default_factory=list)

    def __post_init__(self):
        # Authorization scope must come from the explicit profile assignment,
        # never from an email address or username convention.
        if self.assigned_states:
            self.assigned_states = resolve_states(self.assigned_states)
        elif self.assigned_state:
            self.assigned_states = resolve_states(self.assigned_state)
        else:
            self.assigned_states = []

        if not self.assigned_state and self.assigned_states:
            self.assigned_state = self.assigned_states[0]
        elif self.assigned_state:
            self.assigned_state = resolve_state(self.assigned_state)

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


@dataclass
class CacheEntry:
    user: CurrentUser
    expiry_monotonic: float
    version: int


@dataclass
class AuthTicket:
    token_hash: str
    start_epoch: int
    ticket_created_monotonic: float


class BoundedSessionCache:
    """Thread-safe, bounded, expiry-aware in-memory session cache.
    Features:
    - SHA-256 hashed cache keys (no raw tokens in memory).
    - OrderedDict LRU storage with capacity = 1,000 entries.
    - Min-heap expiry tracking decoupled from LRU access ordering.
    - O(N) heap compaction hard-bounded at 2,000 entries.
    - JWT exp-aware dynamic TTL with 5.0-second clock skew margin.
    - No caching if JWT expiry is missing, malformed, non-numeric, or <= 0.
    - Single-flight authentication coalescing (max 100 concurrent leaders).
    - Followers wait on leader's threading.Event (timeout = 5.0s, safe 504 failure).
    - Followers never consume leader concurrency slots or spawn duplicate work.
    - Invalidation tracking via token hashes, canonical user IDs, and global epochs.
    - Authoritative database revocation check on cache miss.
    - Thread-safe via threading.RLock (zero locks held during network I/O).
    """

    MAX_CACHE_SIZE: int = 1000
    MAX_HEAP_SIZE: int = 2000
    DEFAULT_CACHE_TTL: float = 20.0
    CLOCK_SKEW_MARGIN: float = 5.0
    MAX_CONCURRENT_LEADERS: int = 100
    LEADER_TIMEOUT: float = 5.0

    def __init__(
        self,
        max_cache_size: int = 1000,
        max_heap_size: int = 2000,
        default_ttl: float = 20.0,
        clock_skew_margin: float = 5.0,
        max_concurrent_leaders: int = 100,
        leader_timeout: float = 5.0,
    ):
        self.MAX_CACHE_SIZE = max_cache_size
        self.MAX_HEAP_SIZE = max_heap_size
        self.DEFAULT_CACHE_TTL = default_ttl
        self.CLOCK_SKEW_MARGIN = clock_skew_margin
        self.MAX_CONCURRENT_LEADERS = max_concurrent_leaders
        self.LEADER_TIMEOUT = leader_timeout

        self._lock = threading.RLock()
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()
        self._expiry_heap: list[tuple[float, str, int]] = []  # (expiry_monotonic, token_hash, version)
        self._active_leaders: dict[str, threading.Event] = {}  # token_hash -> Event
        self._global_epoch: int = 0
        self._user_epochs: dict[str, float] = {}  # user_id -> monotonic timestamp
        self._token_invalidated: set[str] = set()  # token_hash set for in-flight tokens

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _purge_expired(self, now: float) -> None:
        """Purge expired entries from min-heap while top is expired."""
        while self._expiry_heap and self._expiry_heap[0][0] <= now:
            expiry, token_hash, version = heapq.heappop(self._expiry_heap)
            entry = self._entries.get(token_hash)
            if entry is not None and entry.version == version and entry.expiry_monotonic <= now:
                self._entries.pop(token_hash, None)

    def _compact_heap(self, now: float | None = None) -> None:
        """Reconstruct the min-heap strictly from active unexpired cache entries."""
        if now is None:
            now = time.monotonic()
        new_heap = [
            (entry.expiry_monotonic, token_hash, entry.version)
            for token_hash, entry in self._entries.items()
            if entry.expiry_monotonic > now
        ]
        heapq.heapify(new_heap)
        self._expiry_heap = new_heap

    def get(self, token: str) -> CurrentUser | None:
        """Look up user in fast cache by token hash. Thread-safe."""
        token_hash = self.hash_token(token)
        now = time.monotonic()
        with self._lock:
            self._purge_expired(now)
            entry = self._entries.get(token_hash)
            if entry is not None:
                if now < entry.expiry_monotonic:
                    self._entries.move_to_end(token_hash)
                    return entry.user
                else:
                    self._entries.pop(token_hash, None)
            return None

    def acquire_or_join(
        self, token: str
    ) -> tuple[bool, threading.Event | None, CurrentUser | None, AuthTicket | None]:
        """Join in-flight authentication or become the designated leader.
        Returns:
            (is_leader, event, cached_user, ticket)
        """
        token_hash = self.hash_token(token)
        now = time.monotonic()
        with self._lock:
            self._purge_expired(now)
            entry = self._entries.get(token_hash)
            if entry is not None:
                if now < entry.expiry_monotonic:
                    self._entries.move_to_end(token_hash)
                    return False, None, entry.user, None
                else:
                    self._entries.pop(token_hash, None)

            # Check if an existing leader is already authenticating this token
            if token_hash in self._active_leaders:
                return False, self._active_leaders[token_hash], None, None

            # Concurrency limit check strictly for new leaders
            if len(self._active_leaders) >= self.MAX_CONCURRENT_LEADERS:
                raise HTTPException(
                    503,
                    "Authentication service busy. Please retry.",
                    headers={"Retry-After": "1"},
                )

            # Register as new leader
            event = threading.Event()
            self._active_leaders[token_hash] = event
            ticket = AuthTicket(
                token_hash=token_hash,
                start_epoch=self._global_epoch,
                ticket_created_monotonic=now,
            )
            return True, event, None, ticket

    def release_leader(self, token_hash: str) -> None:
        """Wake all waiting followers and release leader concurrency slot in finally block."""
        with self._lock:
            event = self._active_leaders.pop(token_hash, None)
            if event is not None:
                event.set()

    def commit_auth(self, ticket: AuthTicket, user: CurrentUser, ttl: float) -> None:
        """Commit an authenticated user session to the cache."""
        now = time.monotonic()
        with self._lock:
            self._purge_expired(now)

            # Check invalidation preconditions
            if ticket.start_epoch != self._global_epoch:
                return  # Global cache clear occurred during in-flight auth
            if ticket.token_hash in self._token_invalidated:
                self._token_invalidated.discard(ticket.token_hash)
                return  # Token was explicitly invalidated
            if user.id in self._user_epochs and ticket.ticket_created_monotonic <= self._user_epochs[user.id]:
                return  # User sessions were invalidated during in-flight auth

            # LRU eviction if at capacity
            if len(self._entries) >= self.MAX_CACHE_SIZE and ticket.token_hash not in self._entries:
                self._entries.popitem(last=False)

            # Determine entry version
            version = 1
            if ticket.token_hash in self._entries:
                version = self._entries[ticket.token_hash].version + 1

            expiry = now + ttl
            self._entries[ticket.token_hash] = CacheEntry(
                user=user, expiry_monotonic=expiry, version=version
            )
            self._entries.move_to_end(ticket.token_hash)
            heapq.heappush(self._expiry_heap, (expiry, ticket.token_hash, version))

            # Compact heap if hard bound exceeded
            if len(self._expiry_heap) > self.MAX_HEAP_SIZE:
                self._compact_heap(now)

    def invalidate_token(self, token: str) -> None:
        """Invalidate a specific token locally."""
        token_hash = self.hash_token(token)
        with self._lock:
            self._entries.pop(token_hash, None)
            self._token_invalidated.add(token_hash)

    def invalidate_user(self, user_id: str) -> None:
        """Invalidate all cached sessions for the canonical user.id."""
        with self._lock:
            to_remove = [h for h, e in self._entries.items() if e.user.id == user_id]
            for h in to_remove:
                self._entries.pop(h, None)
            self._user_epochs[user_id] = time.monotonic()

    def clear_user_cache(self) -> None:
        """Clear the entire cache and increment global epoch to discard in-flight results."""
        with self._lock:
            self._entries.clear()
            self._expiry_heap.clear()
            self._global_epoch += 1
            self._user_epochs.clear()
            self._token_invalidated.clear()

    @staticmethod
    def extract_jwt_claims(token: str) -> dict[str, Any] | None:
        """Safely extract unverified claims from JWT payload.
        CRITICAL: Only called AFTER cryptographic validation by Supabase Auth!
        """
        try:
            parts = token.split(".")
            if len(parts) < 2:
                return None
            raw_payload = parts[1]
            pad = raw_payload + "=" * (-len(raw_payload) % 4)
            data = json.loads(base64.urlsafe_b64decode(pad))
            if isinstance(data, dict):
                return data
            return None
        except Exception:
            return None

    def compute_cache_ttl(self, claims: dict[str, Any] | None) -> float | None:
        """Compute cache TTL bounded by JWT exp and clock skew margin.
        Returns None if token should not be cached (e.g. missing/malformed exp or insufficient remaining lifetime).
        """
        if not claims or "exp" not in claims:
            return None
        exp = claims.get("exp")
        if not isinstance(exp, (int, float)) or isinstance(exp, bool):
            return None
        now_utc = time.time()
        remaining = float(exp) - now_utc - self.CLOCK_SKEW_MARGIN
        if remaining <= 0:
            return None
        return min(self.DEFAULT_CACHE_TTL, remaining)

    @staticmethod
    def parse_db_timestamp(ts: Any) -> float | None:
        """Parse database timestamp into UTC unix timestamp seconds."""
        if not ts:
            return None
        if isinstance(ts, (int, float)) and not isinstance(ts, bool):
            return float(ts)
        if isinstance(ts, str):
            try:
                clean = ts.replace("Z", "+00:00")
                return datetime.fromisoformat(clean).timestamp()
            except Exception:
                return None
        return None

    def check_password_revocation(
        self,
        claims: dict[str, Any] | None,
        profile: dict[str, Any],
    ) -> None:
        """Verify token iat against authoritative password_changed_at timestamp on cache miss."""
        if not claims:
            return

        iat = claims.get("iat")
        if not isinstance(iat, (int, float)) or isinstance(iat, bool):
            return

        token_iat = float(iat)
        pw_changed_at = self.parse_db_timestamp(profile.get("password_changed_at"))
        if pw_changed_at is not None:
            if token_iat < int(pw_changed_at):
                raise HTTPException(401, "Password was changed. Please log in again.")

    def check_revocation(
        self,
        claims: dict[str, Any] | None,
        profile: dict[str, Any],
    ) -> None:
        """Backward-compatible revocation check delegating to password revocation."""
        self.check_password_revocation(claims, profile)


# Global bounded session cache instance
session_cache = BoundedSessionCache()


def clear_user_cache():
    """Clear in-memory user session cache (used in tests or on user update)."""
    session_cache.clear_user_cache()


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
) -> CurrentUser:
    """Validate Supabase access token (from Bearer header or HttpOnly cookie)
    and load the user's active CPASS profile. Role and state are strictly derived from the DB/server.
    """
    token = extract_token(request, authorization)

    # Fast cache lookup
    cached_user = session_cache.get(token)
    if cached_user is not None:
        return cached_user

    # Concurrency control: acquire leader or join as follower
    is_leader, event, fast_user, ticket = session_cache.acquire_or_join(token)
    if fast_user is not None:
        return fast_user

    if not is_leader:
        # Follower path: wait on existing leader event
        assert event is not None
        signaled = event.wait(timeout=session_cache.LEADER_TIMEOUT)
        if not signaled:
            raise HTTPException(
                504,
                "Authentication gateway timeout. Please retry.",
                headers={"Retry-After": "1"},
            )
        # Check cache after leader finished
        cached = session_cache.get(token)
        if cached is not None:
            return cached
        # Leader failed or did not cache
        raise HTTPException(401, "Invalid or expired token")

    # Leader path: execute network authentication outside lock
    assert ticket is not None
    token_hash = ticket.token_hash
    try:
        # Bounded retry on token verification for transient socket/connection errors
        auth_user = None
        for attempt in range(3):
            try:
                auth_user = supabase.auth.get_user(token).user
                break
            except TRANSIENT_ERRORS as exc:
                if attempt == 2:
                    logger.warning("Supabase auth transport failed after 3 attempts: %s", exc)
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
            logger.warning("Supabase profile lookup transport failed: %s", exc)
            raise HTTPException(
                503,
                "User profile service temporarily unreachable. Please retry.",
                headers={"Retry-After": "1"},
            )

        if not rows:
            raise HTTPException(403, "No CPASS profile for this user. Ask an admin to create one.")
        p = rows[0]
        if not p.get("is_active", True):
            raise HTTPException(403, "This account is disabled.")

        # Extract claims safely AFTER Supabase verified cryptographic signature
        claims = session_cache.extract_jwt_claims(token)

        # Check authoritative user-level password revocation timestamp
        session_cache.check_password_revocation(claims, p)

        # Final authoritative token-level revocation check against public.revoked_tokens immediately prior to commit
        try:
            rev_res = retry_read_query(
                lambda: supabase.table("revoked_tokens")
                .select("token_hash")
                .eq("token_hash", token_hash)
                .limit(1)
                .execute()
            )
            if rev_res.data and any(isinstance(r, dict) and r.get("token_hash") == token_hash for r in rev_res.data):
                raise HTTPException(401, "Session token has been revoked. Please log in again.")
        except HTTPException:
            raise
        except Exception as exc:
            err_str = str(exc)
            if "PGRST205" in err_str or "schema cache" in err_str or "does not exist" in err_str:
                logger.error("Revocation table public.revoked_tokens unavailable: %s", exc)
                raise HTTPException(
                    503,
                    "Authentication service configuration error: Revocation schema pending deployment.",
                    headers={"Retry-After": "5"},
                )
            logger.warning("Could not verify revoked_tokens: %s", exc)
            raise HTTPException(
                503,
                "Authentication revocation verification temporarily unreachable. Please retry.",
                headers={"Retry-After": "1"},
            )

        # The CPASS profile's explicit assignment is authoritative. Supports single
        # state string or multi-state assignment (e.g. comma-separated string or array).
        raw_states = p.get("assigned_states") or p.get("assigned_state")
        resolved_list = resolve_states(raw_states)
        assigned_state = resolved_list[0] if resolved_list else None

        user = CurrentUser(
            id=p["id"],
            email=p.get("email"),
            full_name=p["full_name"],
            role=p["role"],
            assigned_state=assigned_state,
            assigned_states=resolved_list,
        )

        # Compute cache TTL and commit if valid
        ttl = session_cache.compute_cache_ttl(claims)
        if ttl is not None and ttl > 0:
            session_cache.commit_auth(ticket, user, ttl)

        return user
    finally:
        session_cache.release_leader(token_hash)


def require_roles(*roles: str):
    def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(403, "Your role cannot do this.")
        return user

    return checker


def allowed_states(user: CurrentUser) -> list[str] | None:
    """None = unrestricted (sees all states).
    Otherwise returns list of permitted canonical state names.
    For L1_COORDINATOR and L2_MANAGER: strictly limited to assigned state(s), else [] (fails closed).
    For L4_LEADER: strictly limited to their assigned multi-state list, else [] (fails closed).
    """
    if user.sees_all_states:
        return None
    if user.assigned_states:
        return user.assigned_states
    if user.assigned_state:
        return [user.assigned_state]
    return []  # Fail closed: no explicit state assignment means no state access


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
    
    Beneficiary State (state_name) is the authoritative source of truth
    for candidate ownership and state-scoped candidate access.
    Fails safely (fail-closed) if state_name is missing or invalid.
    """
    st = cand.get("state_name")
    if st:
        resolved = resolve_state(st)
        if resolved:
            return resolved
        import logging
        logging.getLogger("cpass.auth").warning(
            "Candidate %s has unresolvable state_name: %r", cand.get("candidate_id"), st
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
