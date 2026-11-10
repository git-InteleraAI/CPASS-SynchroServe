"""Automated security test suite for Phase 1.3: Authentication Cache Security.

Covers all 26 required verification scenarios:
1. SHA-256 cache key storage.
2. Bounded LRU capacity.
3. Correct LRU eviction.
4. Expiry heap cleanup.
5. Expired entry behind a fresh LRU entry.
6. Heap compaction hard bound.
7. Repeated replacement of the same token.
8. JWT expiry-aware TTL.
9. Missing or malformed JWT expiry is not cached.
10. Logout invalidates the old token locally.
11. Refresh rotation invalidates the old access token.
12. Password change invalidates the affected user's cached sessions.
13. Profile update invalidation.
14. Token invalidation during in-flight authentication.
15. User invalidation during in-flight authentication.
16. Global clear during in-flight authentication.
17. Unrelated user authentication is not disrupted.
18. Single-flight behavior for duplicate token requests.
19. Follower timeout behavior.
20. Failed leader wakes all followers.
21. Leader ticket cleanup on exceptions.
22. Concurrency limiter counts only leaders.
23. 101st unique leader receives the documented 503 response.
24. Authoritative revocation timestamp rejects old tokens on cache miss.
25. Newer token issued after revocation is accepted when otherwise valid.
26. Existing L1–L5 authentication and authorization behavior remains intact.
"""

import base64
from datetime import datetime, timezone
import hashlib
import json
import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
import pytest
from starlette.testclient import TestClient

from app.auth import (
    AuthTicket,
    BoundedSessionCache,
    CacheEntry,
    CurrentUser,
    clear_user_cache,
    get_current_user,
    session_cache,
)
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def make_jwt(payload: dict[str, Any]) -> str:
    """Helper to construct an unverified test JWT string."""
    header = {"alg": "HS256", "typ": "JWT"}
    h_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{h_b64}.{p_b64}.test_signature"


def make_ticket(cache_obj: BoundedSessionCache, token: str) -> AuthTicket:
    """Helper to create an AuthTicket matching the current cache epoch."""
    return AuthTicket(
        token_hash=cache_obj.hash_token(token),
        start_epoch=cache_obj._global_epoch,
        ticket_created_monotonic=time.monotonic(),
    )


def make_user(user_id: str = "user-1", role: str = "L1_COORDINATOR", state: str = "TAMIL NADU") -> CurrentUser:
    return CurrentUser(
        id=user_id,
        email=f"{user_id}@example.com",
        full_name="Test User",
        role=role,
        assigned_state=state,
        assigned_states=[state],
    )


# ---------------------------------------------------------------------------
# 1. SHA-256 cache key storage
# ---------------------------------------------------------------------------
def test_sha256_cache_key_storage():
    cache = BoundedSessionCache(default_ttl=20.0)
    raw_token = "secret-access-token-12345"
    expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    user = make_user("user-sha")

    ticket = make_ticket(cache, raw_token)
    cache.commit_auth(ticket, user, ttl=20.0)

    # Assert raw token is NEVER stored as a key in the cache dict or heap
    assert raw_token not in cache._entries
    assert expected_hash in cache._entries
    assert cache._expiry_heap[0][1] == expected_hash

    # Assert lookup with raw token retrieves the user via hashing
    retrieved = cache.get(raw_token)
    assert retrieved is not None
    assert retrieved.id == "user-sha"


# ---------------------------------------------------------------------------
# 2. Bounded LRU capacity
# ---------------------------------------------------------------------------
def test_bounded_lru_capacity():
    cache = BoundedSessionCache(max_cache_size=5)
    for i in range(10):
        tok = f"token-{i}"
        ticket = make_ticket(cache, tok)
        cache.commit_auth(ticket, make_user(f"user-{i}"), ttl=20.0)

    # Capacity must be strictly bounded at 5
    assert len(cache._entries) == 5
    # The first 5 should have been evicted
    for i in range(5):
        assert cache.get(f"token-{i}") is None
    # The last 5 should exist
    for i in range(5, 10):
        assert cache.get(f"token-{i}") is not None


# ---------------------------------------------------------------------------
# 3. Correct LRU eviction
# ---------------------------------------------------------------------------
def test_correct_lru_eviction():
    cache = BoundedSessionCache(max_cache_size=3)
    tokens = ["token-0", "token-1", "token-2"]
    for tok in tokens:
        cache.commit_auth(
            make_ticket(cache, tok),
            make_user(tok),
            ttl=20.0,
        )

    # Access token-0 so it becomes most recently used
    assert cache.get("token-0") is not None

    # Insert a 4th token: token-1 should be evicted (as token-0 was accessed recently)
    cache.commit_auth(
        make_ticket(cache, "token-3"),
        make_user("token-3"),
        ttl=20.0,
    )

    assert cache.get("token-0") is not None
    assert cache.get("token-1") is None
    assert cache.get("token-2") is not None
    assert cache.get("token-3") is not None


# ---------------------------------------------------------------------------
# 4. Expiry heap cleanup
# ---------------------------------------------------------------------------
def test_expiry_heap_cleanup():
    cache = BoundedSessionCache(default_ttl=20.0)
    tok = "short-lived-token"
    # Insert with very short TTL
    cache.commit_auth(
        make_ticket(cache, tok),
        make_user("user-exp"),
        ttl=0.01,
    )
    time.sleep(0.02)
    # get() triggers _purge_expired()
    assert cache.get(tok) is None
    assert cache.hash_token(tok) not in cache._entries
    # Expiry heap top is popped
    assert len(cache._expiry_heap) == 0


# ---------------------------------------------------------------------------
# 5. Expired entry behind a fresh LRU entry
# ---------------------------------------------------------------------------
def test_expired_entry_behind_fresh_lru_entry():
    cache = BoundedSessionCache(max_cache_size=10)

    # Insert entry A with short expiry (e.g. +0.02s)
    cache.commit_auth(
        make_ticket(cache, "tok-a"),
        make_user("user-a"),
        ttl=0.02,
    )
    # Insert entry B with long expiry (e.g. +20s)
    cache.commit_auth(
        make_ticket(cache, "tok-b"),
        make_user("user-b"),
        ttl=20.0,
    )

    # Access tok-a so it moves to MRU (end of OrderedDict), behind tok-b in LRU
    assert cache.get("tok-a") is not None

    time.sleep(0.03)

    # In LRU order, tok-b is at head (least recently used), but tok-a is expired!
    # Min-heap must independently purge tok-a without needing LRU eviction
    assert cache.get("tok-a") is None
    assert cache.get("tok-b") is not None


# ---------------------------------------------------------------------------
# 6. Heap compaction hard bound
# ---------------------------------------------------------------------------
def test_heap_compaction_hard_bound():
    # Set max_cache_size=5, max_heap_size=10
    cache = BoundedSessionCache(max_cache_size=5, max_heap_size=10)
    tok = "tok-repeat"

    # Repeatedly commit same token 15 times
    for i in range(15):
        cache.commit_auth(
            make_ticket(cache, tok),
            make_user(f"user-v{i}"),
            ttl=20.0,
        )

    # Heap size must not exceed MAX_HEAP_SIZE (10) because compaction occurred
    assert len(cache._expiry_heap) <= 10
    # Active cache entries must still be exactly 1
    assert len(cache._entries) == 1
    assert cache.get(tok).id == "user-v14"


# ---------------------------------------------------------------------------
# 7. Repeated replacement of the same token
# ---------------------------------------------------------------------------
def test_repeated_replacement_of_same_token():
    cache = BoundedSessionCache()
    tok = "tok-version"
    tok_h = cache.hash_token(tok)

    for i in range(5):
        cache.commit_auth(
            make_ticket(cache, tok),
            make_user(f"ver-{i}"),
            ttl=20.0,
        )

    # Version should have incremented to 5
    assert cache._entries[tok_h].version == 5
    assert cache.get(tok).id == "ver-4"


# ---------------------------------------------------------------------------
# 8. JWT expiry-aware TTL
# ---------------------------------------------------------------------------
def test_jwt_expiry_aware_ttl():
    cache = BoundedSessionCache(default_ttl=20.0, clock_skew_margin=5.0)

    # Case 1: exp allows 15s remaining -> remaining = 15 - 5 = 10s < default 20s
    exp_time = time.time() + 15.0
    claims = {"exp": exp_time}
    ttl = cache.compute_cache_ttl(claims)
    assert ttl is not None
    assert 9.0 <= ttl <= 10.0

    # Case 2: exp allows 100s remaining -> min(20.0, 95.0) = 20.0s
    claims = {"exp": time.time() + 100.0}
    ttl = cache.compute_cache_ttl(claims)
    assert ttl == 20.0


# ---------------------------------------------------------------------------
# 9. Missing or malformed JWT expiry is not cached
# ---------------------------------------------------------------------------
def test_missing_or_malformed_jwt_expiry_not_cached():
    cache = BoundedSessionCache(default_ttl=20.0, clock_skew_margin=5.0)

    # Missing exp
    assert cache.compute_cache_ttl({}) is None
    assert cache.compute_cache_ttl(None) is None

    # String exp
    assert cache.compute_cache_ttl({"exp": "tomorrow"}) is None

    # Boolean exp
    assert cache.compute_cache_ttl({"exp": True}) is None

    # Expired or remaining <= clock skew
    assert cache.compute_cache_ttl({"exp": time.time() + 4.0}) is None  # 4 - 5 = -1 <= 0
    assert cache.compute_cache_ttl({"exp": time.time() - 10.0}) is None


# ---------------------------------------------------------------------------
# 10. Logout invalidates the old token locally
# ---------------------------------------------------------------------------
def test_logout_invalidates_old_token_locally(client: TestClient):
    tok = make_jwt({"sub": "user-logout-1", "exp": time.time() + 60, "iat": time.time()})
    session_cache.commit_auth(
        make_ticket(session_cache, tok),
        make_user("user-logout-1"),
        ttl=20.0,
    )
    assert session_cache.get(tok) is not None

    with patch("app.routers.auth.supabase.table") as mock_table:
        mock_table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[{"token_hash": "..."}])
        with patch("app.routers.auth.supabase.auth.admin.sign_out") as mock_sign_out:
            res = client.post(
                "/auth/logout",
                headers={"Authorization": f"Bearer {tok}", "X-Requested-With": "XMLHttpRequest"},
            )
            assert res.status_code == 200
            mock_sign_out.assert_called_once_with(tok, scope="local")

    # Token must be invalidated locally
    assert session_cache.get(tok) is None


# ---------------------------------------------------------------------------
# 11. Refresh rotation invalidates the old access token
# ---------------------------------------------------------------------------
def test_refresh_rotation_invalidates_old_access_token(client: TestClient):
    old_tok = make_jwt({"sub": "user-ref-1", "exp": time.time() + 60, "iat": time.time()})
    session_cache.commit_auth(
        make_ticket(session_cache, old_tok),
        make_user("user-ref-1"),
        ttl=20.0,
    )
    assert session_cache.get(old_tok) is not None

    # Mock refresh session
    mock_auth_res = MagicMock()
    mock_auth_res.user.id = "user-ref-1"
    mock_auth_res.session.access_token = "new-access-token"
    mock_auth_res.session.refresh_token = "new-refresh-token"
    mock_auth_res.session.expires_in = 3600

    mock_profile_res = MagicMock()
    mock_profile_res.data = [{
        "id": "user-ref-1",
        "email": "ref@test.com",
        "full_name": "Ref User",
        "role": "L1_COORDINATOR",
        "is_active": True,
        "assigned_state": "TAMIL NADU",
    }]

    with patch("app.routers.auth.get_auth_client") as mock_get_auth:
        mock_get_auth.return_value.auth.refresh_session.return_value = mock_auth_res
        with patch("app.routers.auth.supabase.table") as mock_table:
            mock_table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_profile_res
            mock_table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[{"token_hash": "..."}])
            client.cookies.set("cpass_access_token", old_tok)
            client.cookies.set("cpass_refresh_token", "dummy-refresh")
            res = client.post(
                "/auth/refresh",
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            assert res.status_code == 200

    # Old access token must be invalidated locally
    assert session_cache.get(old_tok) is None
    # New access token must NOT be pre-warmed in session_cache
    assert session_cache.get("new-access-token") is None


# ---------------------------------------------------------------------------
# 12. Password change invalidates affected user's cached sessions
# ---------------------------------------------------------------------------
def test_password_change_invalidates_affected_user_sessions(client: TestClient):
    tok = make_jwt({"sub": "user-pw-1", "exp": time.time() + 60, "iat": time.time()})
    session_cache.commit_auth(
        make_ticket(session_cache, tok),
        make_user("user-pw-1"),
        ttl=20.0,
    )
    assert session_cache.get(tok) is not None

    mock_auth = MagicMock()
    mock_auth.user.id = "user-pw-1"
    mock_auth.session.access_token = "new-pw-tok"
    mock_auth.session.refresh_token = "new-pw-ref"
    mock_auth.session.expires_in = 3600

    with patch("app.routers.auth.get_auth_client") as mock_get_client:
        mock_client_inst = MagicMock()
        mock_get_client.return_value = mock_client_inst
        mock_client_inst.auth.sign_in_with_password.return_value = mock_auth
        mock_client_inst.auth.update_user.return_value = None

        with patch("app.routers.auth.supabase.table") as mock_table:
            mock_table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "user-pw-1"}])
            client.cookies.set("cpass_access_token", tok)
            res = client.post(
                "/auth/change-password",
                json={
                    "current_password": "OldPassword1!",
                    "new_password": "NewPassword2@",
                    "confirm_password": "NewPassword2@",
                },
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            assert res.status_code == 200

    # Cached session for user-pw-1 must be invalidated
    assert session_cache.get(tok) is None


# ---------------------------------------------------------------------------
# 13. Profile update invalidation
# ---------------------------------------------------------------------------
def test_profile_update_invalidation(client: TestClient):
    user_a_tok = make_jwt({"sub": "user-prof-a", "exp": time.time() + 60, "iat": time.time()})
    user_b_tok = make_jwt({"sub": "user-prof-b", "exp": time.time() + 60, "iat": time.time()})

    session_cache.commit_auth(
        make_ticket(session_cache, user_a_tok),
        make_user("user-prof-a"),
        ttl=20.0,
    )
    session_cache.commit_auth(
        make_ticket(session_cache, user_b_tok),
        make_user("user-prof-b"),
        ttl=20.0,
    )

    with patch("app.routers.auth.supabase.table") as mock_table:
        mock_table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "user-prof-a"}])
        with patch("app.routers.auth.supabase.auth.admin.update_user_by_id"):
            client.cookies.set("cpass_access_token", user_a_tok)
            res = client.patch(
                "/auth/profile",
                json={"full_name": "Updated Name"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            assert res.status_code == 200

    # User A session is invalidated
    assert session_cache.get(user_a_tok) is None
    # User B session remains intact
    assert session_cache.get(user_b_tok) is not None


# ---------------------------------------------------------------------------
# 14. Token invalidation during in-flight authentication
# ---------------------------------------------------------------------------
def test_token_invalidation_during_inflight_auth():
    cache = BoundedSessionCache()
    tok = "inflight-token"
    tok_h = cache.hash_token(tok)

    is_leader, event, _, ticket = cache.acquire_or_join(tok)
    assert is_leader is True

    # Invalidate this token while authentication is in flight
    cache.invalidate_token(tok)

    # Leader finishes and attempts to commit
    cache.commit_auth(ticket, make_user("user-inf"), ttl=20.0)
    cache.release_leader(tok_h)

    # Cache must NOT contain the invalidated token
    assert cache.get(tok) is None


# ---------------------------------------------------------------------------
# 15. User invalidation during in-flight authentication
# ---------------------------------------------------------------------------
def test_user_invalidation_during_inflight_auth():
    cache = BoundedSessionCache()
    tok = "user-inflight-token"
    tok_h = cache.hash_token(tok)

    is_leader, event, _, ticket = cache.acquire_or_join(tok)
    assert is_leader is True

    # Invalidate user while authentication is in flight
    time.sleep(0.005)
    cache.invalidate_user("user-target")

    # Leader finishes and attempts to commit
    cache.commit_auth(ticket, make_user("user-target"), ttl=20.0)
    cache.release_leader(tok_h)

    # Cache must NOT store the result because ticket was created before user invalidation
    assert cache.get(tok) is None


# ---------------------------------------------------------------------------
# 16. Global clear during in-flight authentication
# ---------------------------------------------------------------------------
def test_global_clear_during_inflight_auth():
    cache = BoundedSessionCache()
    tok = "global-inflight-token"
    tok_h = cache.hash_token(tok)

    is_leader, event, _, ticket = cache.acquire_or_join(tok)
    assert is_leader is True

    # Global clear occurs while in flight
    cache.clear_user_cache()

    # Leader finishes and attempts to commit
    cache.commit_auth(ticket, make_user("user-glob"), ttl=20.0)
    cache.release_leader(tok_h)

    assert cache.get(tok) is None


# ---------------------------------------------------------------------------
# 17. Unrelated user authentication is not disrupted
# ---------------------------------------------------------------------------
def test_unrelated_user_auth_not_disrupted():
    cache = BoundedSessionCache()
    tok_a = "tok-alice"
    tok_b = "tok-bob"

    cache.commit_auth(
        make_ticket(cache, tok_a),
        make_user("user-alice"),
        ttl=20.0,
    )
    cache.commit_auth(
        make_ticket(cache, tok_b),
        make_user("user-bob"),
        ttl=20.0,
    )

    # Invalidate Alice
    cache.invalidate_user("user-alice")

    # Alice is evicted, Bob is completely intact
    assert cache.get(tok_a) is None
    assert cache.get(tok_b) is not None
    assert cache.get(tok_b).id == "user-bob"


# ---------------------------------------------------------------------------
# 18. Single-flight behavior for duplicate token requests
# ---------------------------------------------------------------------------
def test_single_flight_duplicate_token_requests():
    cache = BoundedSessionCache()
    tok = "shared-duplicate-token"
    results = []

    # Acquire leader
    is_leader, leader_event, _, ticket = cache.acquire_or_join(tok)
    assert is_leader is True

    def follower_thread():
        is_l, evt, _, _ = cache.acquire_or_join(tok)
        assert is_l is False
        assert evt is leader_event
        evt.wait(timeout=2.0)
        u = cache.get(tok)
        results.append(u)

    threads = [threading.Thread(target=follower_thread) for _ in range(5)]
    for t in threads:
        t.start()

    time.sleep(0.05)
    # Leader commits and releases
    cache.commit_auth(ticket, make_user("user-single-flight"), ttl=20.0)
    cache.release_leader(ticket.token_hash)

    for t in threads:
        t.join()

    assert len(results) == 5
    for r in results:
        assert r is not None
        assert r.id == "user-single-flight"


# ---------------------------------------------------------------------------
# 19. Follower timeout behavior
# ---------------------------------------------------------------------------
def test_follower_timeout_behavior():
    cache = BoundedSessionCache(leader_timeout=0.05)
    tok = "stalled-leader-token"

    # Leader acquires and stalls without releasing
    is_leader, event, _, ticket = cache.acquire_or_join(tok)
    assert is_leader is True

    # Follower waiting on leader
    is_l, f_event, _, _ = cache.acquire_or_join(tok)
    assert is_l is False
    signaled = f_event.wait(timeout=0.05)
    assert signaled is False  # Timed out safely

    # Clean up stalled leader
    cache.release_leader(ticket.token_hash)


# ---------------------------------------------------------------------------
# 20. Failed leader wakes all followers
# ---------------------------------------------------------------------------
def test_failed_leader_wakes_all_followers():
    cache = BoundedSessionCache()
    tok = "failing-leader-token"
    tok_h = cache.hash_token(tok)

    is_leader, leader_event, _, ticket = cache.acquire_or_join(tok)
    assert is_leader is True

    woken = []

    def follower():
        is_l, evt, _, _ = cache.acquire_or_join(tok)
        evt.wait(timeout=2.0)
        # Check cache: must be None since leader failed
        woken.append(cache.get(tok))

    threads = [threading.Thread(target=follower) for _ in range(3)]
    for t in threads:
        t.start()

    time.sleep(0.02)
    # Leader fails without committing, but signals in finally
    cache.release_leader(tok_h)

    for t in threads:
        t.join()

    assert len(woken) == 3
    assert all(w is None for w in woken)


# ---------------------------------------------------------------------------
# 21. Leader ticket cleanup on exceptions
# ---------------------------------------------------------------------------
def test_leader_ticket_cleanup_on_exceptions():
    cache = BoundedSessionCache()
    tok = "exc-cleanup-token"
    tok_h = cache.hash_token(tok)

    is_leader, event, _, ticket = cache.acquire_or_join(tok)
    assert is_leader is True
    assert tok_h in cache._active_leaders

    try:
        try:
            raise ValueError("Simulated network failure")
        finally:
            cache.release_leader(tok_h)
    except ValueError:
        pass

    assert tok_h not in cache._active_leaders
    assert event.is_set()


# ---------------------------------------------------------------------------
# 22. Concurrency limiter counts only leaders
# ---------------------------------------------------------------------------
def test_concurrency_limiter_counts_only_leaders():
    cache = BoundedSessionCache(max_concurrent_leaders=2)
    tok_a = "token-a"
    tok_b = "token-b"

    # Leader 1
    is_l1, evt1, _, ticket1 = cache.acquire_or_join(tok_a)
    assert is_l1 is True

    # 10 followers on Token A
    for _ in range(10):
        is_l, evt, _, _ = cache.acquire_or_join(tok_a)
        assert is_l is False
        assert evt is evt1

    # Active leaders is still exactly 1
    assert len(cache._active_leaders) == 1

    # Leader 2
    is_l2, evt2, _, ticket2 = cache.acquire_or_join(tok_b)
    assert is_l2 is True
    assert len(cache._active_leaders) == 2

    # Cleanup
    cache.release_leader(ticket1.token_hash)
    cache.release_leader(ticket2.token_hash)


# ---------------------------------------------------------------------------
# 23. 101st unique leader receives 503 response
# ---------------------------------------------------------------------------
def test_101st_unique_leader_receives_503():
    cache = BoundedSessionCache(max_concurrent_leaders=100)
    tickets = []

    # Fill 100 unique leaders
    for i in range(100):
        tok = f"leader-tok-{i}"
        is_leader, _, _, ticket = cache.acquire_or_join(tok)
        assert is_leader is True
        tickets.append(ticket)

    assert len(cache._active_leaders) == 100

    # 101st unique leader must receive 503
    with pytest.raises(HTTPException) as exc_info:
        cache.acquire_or_join("leader-tok-101")

    assert exc_info.value.status_code == 503
    assert exc_info.value.headers.get("Retry-After") == "1"

    # Release leaders
    for t in tickets:
        cache.release_leader(t.token_hash)
    assert len(cache._active_leaders) == 0


# ---------------------------------------------------------------------------
# 24. Authoritative revocation timestamp rejects old tokens on cache miss
# ---------------------------------------------------------------------------
def test_authoritative_revocation_timestamp_rejects_old_tokens():
    cache = BoundedSessionCache()
    # Token issued at T = 1000
    claims = {"sub": "user-rev-test", "iat": 1000, "exp": 2000}

    # Profile shows password_changed_at T = 1050 (issued before password change)
    profile = {
        "id": "user-rev-test",
        "password_changed_at": datetime.fromtimestamp(1050, tz=timezone.utc).isoformat(),
    }

    with pytest.raises(HTTPException) as exc_info:
        cache.check_password_revocation(claims, profile)
    assert exc_info.value.status_code == 401
    assert "Password was changed" in exc_info.value.detail


# ---------------------------------------------------------------------------
# 25. Newer token issued after revocation is accepted
# ---------------------------------------------------------------------------
def test_newer_token_after_revocation_accepted():
    cache = BoundedSessionCache()
    # Token issued at T = 1100 (issued after password change at T = 1040)
    claims = {"sub": "user-rev-test", "iat": 1100, "exp": 2000}

    profile = {
        "id": "user-rev-test",
        "password_changed_at": datetime.fromtimestamp(1040, tz=timezone.utc).isoformat(),
    }

    # Should not raise exception
    cache.check_password_revocation(claims, profile)


# ---------------------------------------------------------------------------
# 26. Existing L1–L5 authentication and authorization behavior intact
# ---------------------------------------------------------------------------
def test_existing_l1_l5_auth_intact():
    clear_user_cache()

    # Verify L1 Coordinator role & state parsing
    l1 = make_user("l1-user", role="L1_COORDINATOR", state="TAMIL NADU")
    assert l1.role == "L1_COORDINATOR"
    assert l1.assigned_state == "TAMIL NADU"
    assert l1.sees_all_states is False
    assert l1.sees_all_centres is False

    # Verify L3 Leader sees all centres and states
    l3 = make_user("l3-user", role="L3_LEADER", state=None)
    assert l3.sees_all_states is True
    assert l3.sees_all_centres is True

    # Verify L4 CEO sees all centres and states
    l4 = make_user("l4-user", role="L4_CEO", state=None)
    assert l4.sees_all_states is True
    assert l4.sees_all_centres is True


# ===========================================================================
# CORRECTION F: ENDPOINT-LEVEL ASGI INTEGRATION TESTS
# ===========================================================================

# ---------------------------------------------------------------------------
# 27. Revoked token presented to GET /auth/me returns HTTP 401
# ---------------------------------------------------------------------------
def test_revoked_token_via_get_me_returns_401(client: TestClient):
    clear_user_cache()
    revoked_token = make_jwt({"sub": "user-rev-1", "exp": time.time() + 300, "iat": time.time()})
    rev_hash = session_cache.hash_token(revoked_token)

    with patch("app.auth.supabase") as mock_sb:
        mock_u = MagicMock()
        mock_u.user.id = "user-rev-1"
        mock_sb.auth.get_user.return_value = mock_u

        # Profile is active
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = [
            MagicMock(data=[{"id": "user-rev-1", "full_name": "Rev User", "role": "L1_COORDINATOR", "is_active": True}]),
            MagicMock(data=[{"token_hash": rev_hash}]),  # revoked_tokens hit
        ]

        res = client.get("/auth/me", headers={"Authorization": f"Bearer {revoked_token}"})
        assert res.status_code == 401
        assert "revoked" in res.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 28. Non-revoked token remains usable
# ---------------------------------------------------------------------------
def test_non_revoked_token_remains_usable(client: TestClient):
    clear_user_cache()
    valid_token = make_jwt({"sub": "user-valid-1", "exp": time.time() + 300, "iat": time.time()})

    with patch("app.auth.supabase") as mock_sb:
        mock_u = MagicMock()
        mock_u.user.id = "user-valid-1"
        mock_sb.auth.get_user.return_value = mock_u

        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = [
            MagicMock(data=[{"id": "user-valid-1", "full_name": "Valid User", "role": "L1_COORDINATOR", "is_active": True, "assigned_state": "TAMIL NADU"}]),
            MagicMock(data=[]),  # revoked_tokens miss
        ]

        res = client.get("/auth/me", headers={"Authorization": f"Bearer {valid_token}"})
        assert res.status_code == 200
        assert res.json()["full_name"] == "Valid User"


# ---------------------------------------------------------------------------
# 29. Refresh revokes the old access token in database
# ---------------------------------------------------------------------------
def test_refresh_revokes_old_access_token_in_database(client: TestClient):
    clear_user_cache()
    old_tok = make_jwt({"sub": "user-ref-rot", "exp": time.time() + 300, "iat": time.time()})
    old_hash = session_cache.hash_token(old_tok)

    mock_auth_res = MagicMock()
    mock_auth_res.user.id = "user-ref-rot"
    mock_auth_res.session.access_token = "new-fresh-tok"
    mock_auth_res.session.refresh_token = "new-fresh-ref"
    mock_auth_res.session.expires_in = 3600

    upsert_calls = []

    with patch("app.routers.auth.get_auth_client") as mock_auth_client:
        mock_auth_client.return_value.auth.refresh_session.return_value = mock_auth_res
        with patch("app.routers.auth.supabase.table") as mock_table:
            # Profile select
            mock_table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[{"id": "user-ref-rot", "full_name": "Ref User", "role": "L1_COORDINATOR", "is_active": True}]
            )
            # Revocation upsert
            def record_upsert(payload):
                upsert_calls.append(payload)
                return MagicMock(execute=lambda: MagicMock(data=[payload]))
            mock_table.return_value.upsert.side_effect = record_upsert

            client.cookies.set("cpass_access_token", old_tok)
            client.cookies.set("cpass_refresh_token", "sample-refresh-token")
            res = client.post("/auth/refresh", headers={"X-Requested-With": "XMLHttpRequest"})
            assert res.status_code == 200

    # Verify old token hash was persisted to revoked_tokens
    assert len(upsert_calls) == 1
    assert upsert_calls[0]["token_hash"] == old_hash
    assert upsert_calls[0]["user_id"] == "user-ref-rot"


# ---------------------------------------------------------------------------
# 30. Newly issued token remains usable after refresh
# ---------------------------------------------------------------------------
def test_newly_issued_token_usable_after_refresh(client: TestClient):
    clear_user_cache()
    new_tok = make_jwt({"sub": "user-new-tok", "exp": time.time() + 300, "iat": time.time()})
    new_hash = session_cache.hash_token(new_tok)

    with patch("app.auth.supabase") as mock_sb:
        mock_u = MagicMock()
        mock_u.user.id = "user-new-tok"
        mock_sb.auth.get_user.return_value = mock_u

        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = [
            MagicMock(data=[{"id": "user-new-tok", "full_name": "New User", "role": "L2_MANAGER", "is_active": True, "assigned_state": "KERALA"}]),
            MagicMock(data=[]),  # Not in revoked_tokens
        ]

        res = client.get("/auth/me", headers={"Authorization": f"Bearer {new_tok}"})
        assert res.status_code == 200
        assert res.json()["role"] == "L2_MANAGER"


# ---------------------------------------------------------------------------
# 31. Revoking one session does not revoke a different session for same user
# ---------------------------------------------------------------------------
def test_revoking_one_session_does_not_revoke_different_session(client: TestClient):
    clear_user_cache()
    user_id = "user-dual-device"
    # Session A (laptop) and Session B (mobile)
    tok_a = make_jwt({"sub": user_id, "exp": time.time() + 300, "iat": time.time()})
    tok_b = make_jwt({"sub": user_id, "exp": time.time() + 300, "iat": time.time()})
    hash_a = session_cache.hash_token(tok_a)
    hash_b = session_cache.hash_token(tok_b)

    # Logout Session A
    with patch("app.routers.auth.supabase.table") as mock_table:
        mock_table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[{"token_hash": hash_a}])
        with patch("app.routers.auth.supabase.auth.admin.sign_out") as mock_sign_out:
            res_logout = client.post(
                "/auth/logout",
                headers={"Authorization": f"Bearer {tok_a}", "X-Requested-With": "XMLHttpRequest"},
            )
            assert res_logout.status_code == 200
            mock_sign_out.assert_called_once_with(tok_a, scope="local")

    # Session A is revoked in local cache
    assert session_cache.get(tok_a) is None

    # Session B accesses /auth/me on a cache miss:
    # Only hash_a is in revoked_tokens, hash_b is NOT revoked!
    with patch("app.auth.supabase") as mock_sb:
        mock_u = MagicMock()
        mock_u.user.id = user_id
        mock_sb.auth.get_user.return_value = mock_u

        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = [
            MagicMock(data=[{"id": user_id, "full_name": "Multi User", "role": "L1_COORDINATOR", "is_active": True, "assigned_state": "PUNJAB"}]),
            MagicMock(data=[]),  # hash_b not in revoked_tokens
        ]

        res_b = client.get("/auth/me", headers={"Authorization": f"Bearer {tok_b}"})
        assert res_b.status_code == 200
        assert res_b.json()["full_name"] == "Multi User"


# ---------------------------------------------------------------------------
# 32. Logout clears cookies when database revocation succeeds
# ---------------------------------------------------------------------------
def test_logout_clears_cookies_when_database_revocation_succeeds(client: TestClient):
    tok = make_jwt({"sub": "user-logout-ok", "exp": time.time() + 300, "iat": time.time()})

    with patch("app.routers.auth.supabase.table") as mock_table:
        mock_table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[{"token_hash": "..."}])
        with patch("app.routers.auth.supabase.auth.admin.sign_out"):
            client.cookies.set("cpass_access_token", tok)
            client.cookies.set("cpass_refresh_token", "sample-refresh")
            res = client.post("/auth/logout", headers={"X-Requested-With": "XMLHttpRequest"})
            assert res.status_code == 200
            # Both auth cookies should be instructed to delete (max-age=0 or empty)
            assert res.cookies.get("cpass_access_token") is None or res.cookies.get("cpass_access_token") == ""


# ---------------------------------------------------------------------------
# 33. Logout clears cookies and returns error when revocation persistence fails
# ---------------------------------------------------------------------------
def test_logout_clears_cookies_and_returns_error_when_revocation_fails(client: TestClient):
    tok = make_jwt({"sub": "user-logout-fail", "exp": time.time() + 300, "iat": time.time()})

    with patch("app.routers.auth.supabase.table") as mock_table:
        mock_table.return_value.upsert.return_value.execute.side_effect = Exception("Database connection lost")
        client.cookies.set("cpass_access_token", tok)
        client.cookies.set("cpass_refresh_token", "sample-refresh")
        res = client.post("/auth/logout", headers={"X-Requested-With": "XMLHttpRequest"})

        # Must fail closed: HTTP 500 error returned
        assert res.status_code == 500
        assert "Failed to record session revocation" in res.json()["detail"]
        # Cookies are still cleared on response
        assert res.cookies.get("cpass_access_token") is None or res.cookies.get("cpass_access_token") == ""


# ---------------------------------------------------------------------------
# 34. Password change fails when revocation persistence fails
# ---------------------------------------------------------------------------
def test_password_change_fails_when_revocation_persistence_fails(client: TestClient):
    clear_user_cache()
    tok = make_jwt({"sub": "user-pw-fail", "exp": time.time() + 300, "iat": time.time()})
    session_cache.commit_auth(make_ticket(session_cache, tok), make_user("user-pw-fail"), ttl=20.0)

    mock_auth = MagicMock()
    mock_auth.user.id = "user-pw-fail"
    mock_auth.session.access_token = "new-pw-tok"
    mock_auth.session.refresh_token = "new-pw-ref"

    with patch("app.routers.auth.get_auth_client") as mock_auth_client:
        mock_inst = MagicMock()
        mock_auth_client.return_value = mock_inst
        mock_inst.auth.sign_in_with_password.return_value = mock_auth
        mock_inst.auth.update_user.return_value = None

        with patch("app.routers.auth.supabase.table") as mock_table:
            # Simulate failure updating password_changed_at in profiles
            mock_table.return_value.update.return_value.eq.return_value.execute.side_effect = Exception("DB update failed")

            client.cookies.set("cpass_access_token", tok)
            res = client.post(
                "/auth/change-password",
                json={
                    "current_password": "OldPassword1!",
                    "new_password": "NewPassword2@",
                    "confirm_password": "NewPassword2@",
                },
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            # Must return HTTP 500 and NOT report success
            assert res.status_code == 500
            assert "Failed to record password revocation state" in res.json()["detail"]


# ---------------------------------------------------------------------------
# 35. Token cannot be cached after a concurrent revocation
# ---------------------------------------------------------------------------
def test_token_cannot_be_cached_after_concurrent_revocation(client: TestClient):
    clear_user_cache()
    token = make_jwt({"sub": "user-race-1", "exp": time.time() + 300, "iat": time.time()})
    token_hash = session_cache.hash_token(token)

    # Simulate Worker B: validates with Supabase and reads profile,
    # but concurrent revocation from Worker A committed to revoked_tokens
    with patch("app.auth.supabase") as mock_sb:
        mock_u = MagicMock()
        mock_u.user.id = "user-race-1"
        mock_sb.auth.get_user.return_value = mock_u

        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = [
            MagicMock(data=[{"id": "user-race-1", "full_name": "Race User", "role": "L1_COORDINATOR", "is_active": True}]),
            MagicMock(data=[{"token_hash": token_hash}]),  # Final check finds revoked_tokens record!
        ]

        res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 401
        assert "revoked" in res.json()["detail"].lower()

    # Crucial assertion: Token must NOT be in cache!
    assert session_cache.get(token) is None


# ---------------------------------------------------------------------------
# 36. Worker cache miss checks the shared revocation table
# ---------------------------------------------------------------------------
def test_worker_cache_miss_checks_shared_revocation_table(client: TestClient):
    clear_user_cache()
    token = make_jwt({"sub": "user-miss-1", "exp": time.time() + 300, "iat": time.time()})
    token_hash = session_cache.hash_token(token)

    queried_tables = []

    with patch("app.auth.supabase") as mock_sb:
        mock_u = MagicMock()
        mock_u.user.id = "user-miss-1"
        mock_sb.auth.get_user.return_value = mock_u

        def track_table(table_name):
            queried_tables.append(table_name)
            m = MagicMock()
            if table_name == "profiles":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[{"id": "user-miss-1", "full_name": "Miss User", "role": "L1_COORDINATOR", "is_active": True, "assigned_state": "RAJASTHAN"}]
                )
            elif table_name == "revoked_tokens":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            return m

        mock_sb.table.side_effect = track_table

        res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200

    # Assert that both profiles and revoked_tokens were queried during cache miss
    assert "profiles" in queried_tables
    assert "revoked_tokens" in queried_tables

