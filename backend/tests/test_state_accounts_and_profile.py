"""Automated test suite for CPASS State-Wise L1 PE & L2 CH Account System,
Idempotent Provisioning, Profile Editing (Display Name Only), and Cross-State Isolation.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.auth import (
    ALL_12_STATES,
    CurrentUser,
    allowed_states,
    clear_user_cache,
    get_current_user,
    resolve_state,
)
from app.main import app
from scripts.provision_state_accounts import build_account_definitions, provision_state_accounts

client = TestClient(app)


# -----------------------------------------------------------------------------
# 1. Verification of 24 Accounts Specification
# -----------------------------------------------------------------------------
def test_24_state_account_definitions():
    """Verify that exactly 24 accounts are defined: 12 L1 PE and 12 L2 CH across all 12 states."""
    defs = build_account_definitions()
    assert len(defs) == 24, f"Expected 24 accounts, got {len(defs)}"

    l1_accounts = [a for a in defs if a["role"] == "L1_COORDINATOR"]
    l2_accounts = [a for a in defs if a["role"] == "L2_MANAGER"]

    assert len(l1_accounts) == 12, "Expected 12 L1 accounts"
    assert len(l2_accounts) == 12, "Expected 12 L2 accounts"

    l1_states = {a["state"] for a in l1_accounts}
    l2_states = {a["state"] for a in l2_accounts}

    assert l1_states == set(ALL_12_STATES), "L1 states must cover all 12 canonical states"
    assert l2_states == set(ALL_12_STATES), "L2 states must cover all 12 canonical states"

    for a in l1_accounts:
        assert a["email"].endswith("pe@synchroserve.com")
        assert a["default_password"].endswith("pe@cpass")
        assert "Placement Executive" in a["full_name"]
        assert a["role"] == "L1_COORDINATOR"

    for a in l2_accounts:
        assert a["email"].endswith("ch@synchroserve.com")
        assert a["default_password"].endswith("ch@cpass")
        assert "Centre Head" in a["full_name"]
        assert a["role"] == "L2_MANAGER"


# -----------------------------------------------------------------------------
# 2. State Suffix and Alias Normalization
# -----------------------------------------------------------------------------
def test_resolve_state_for_pe_and_ch_conventions():
    """Verify resolve_state correctly extracts state from new pe/ch emails and codes."""
    # Suffix and code resolution
    assert resolve_state("appe@synchroserve.com") == "ANDHRA PRADESH"
    assert resolve_state("apch@synchroserve.com") == "ANDHRA PRADESH"
    assert resolve_state("appe") == "ANDHRA PRADESH"
    assert resolve_state("apch") == "ANDHRA PRADESH"

    assert resolve_state("tnpe@synchroserve.com") == "TAMIL NADU"
    assert resolve_state("tnch@synchroserve.com") == "TAMIL NADU"

    assert resolve_state("tspe@synchroserve.com") == "TELANGANA"
    assert resolve_state("tsch@synchroserve.com") == "TELANGANA"

    assert resolve_state("wbpe@synchroserve.com") == "WEST BENGAL"
    assert resolve_state("wbch@synchroserve.com") == "WEST BENGAL"

    assert resolve_state("pbpe@synchroserve.com") == "PUNJAB"
    assert resolve_state("pbch@synchroserve.com") == "PUNJAB"


# -----------------------------------------------------------------------------
# 3. State Isolation for both L1 and L2
# -----------------------------------------------------------------------------
def test_allowed_states_enforcement():
    """Verify allowed_states enforces strict state scoping for both L1 and L2."""
    l1_ap = CurrentUser(id="1", email="appe@synchroserve.com", full_name="AP PE", role="L1_COORDINATOR", assigned_state="ANDHRA PRADESH")
    l2_ap = CurrentUser(id="2", email="apch@synchroserve.com", full_name="AP CH", role="L2_MANAGER", assigned_state="ANDHRA PRADESH")

    assert allowed_states(l1_ap) == ["ANDHRA PRADESH"]
    assert allowed_states(l2_ap) == ["ANDHRA PRADESH"]

    # Unassigned must fail closed (return empty list)
    l1_unassigned = CurrentUser(id="3", email="unassigned@cpass.org", full_name="Unassigned PE", role="L1_COORDINATOR", assigned_state=None)
    l2_unassigned = CurrentUser(id="4", email="unassigned_ch@cpass.org", full_name="Unassigned CH", role="L2_MANAGER", assigned_state=None)

    assert allowed_states(l1_unassigned) == []
    assert allowed_states(l2_unassigned) == []

    # Admin sees all states
    admin = CurrentUser(id="5", email="admin@cpass.org", full_name="Admin", role="ADMIN", assigned_state=None)
    assert allowed_states(admin) is None


# -----------------------------------------------------------------------------
# 4. Profile Editing (Display Name Only)
# -----------------------------------------------------------------------------
def test_update_profile_display_name_success():
    """Verify user can update their own display name."""
    clear_user_cache()
    test_user = CurrentUser(
        id="user-profile-test-1",
        email="appe@synchroserve.com",
        full_name="Original Name",
        role="L1_COORDINATOR",
        assigned_state="ANDHRA PRADESH",
    )

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with patch("app.routers.auth.supabase") as mock_sb:
            mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
                {"id": test_user.id, "full_name": "Updated Placement Executive"}
            ]
            mock_sb.auth.admin.update_user_by_id.return_value = MagicMock()

            resp = client.patch(
                "/auth/profile",
                json={"full_name": "Updated Placement Executive"},
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["full_name"] == "Updated Placement Executive"
            assert data["email"] == "appe@synchroserve.com"
            assert data["role"] == "L1_COORDINATOR"
            assert data["assigned_state"] == "ANDHRA PRADESH"

            # Verify database update was called with only full_name
            mock_sb.table.return_value.update.assert_called_with({"full_name": "Updated Placement Executive"})
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_update_profile_rejects_extra_fields():
    """Verify API strictly rejects attempts to inject email, role, or assigned_state."""
    test_user = CurrentUser(
        id="user-profile-test-2",
        email="appe@synchroserve.com",
        full_name="Original Name",
        role="L1_COORDINATOR",
        assigned_state="ANDHRA PRADESH",
    )

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        # Attempt to tamper with role
        resp = client.patch(
            "/auth/profile",
            json={"full_name": "Hacker Name", "role": "ADMIN"},
        )
        assert resp.status_code == 422  # Pydantic extra="forbid" rejects unexpected fields

        # Attempt to tamper with email
        resp2 = client.patch(
            "/auth/profile",
            json={"full_name": "Hacker Name", "email": "admin@cpass.org"},
        )
        assert resp2.status_code == 422

        # Attempt to tamper with assigned_state
        resp3 = client.patch(
            "/auth/profile",
            json={"full_name": "Hacker Name", "assigned_state": "TAMIL NADU"},
        )
        assert resp3.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_update_profile_validates_name_length():
    """Verify validation on empty, too short, or too long names."""
    test_user = CurrentUser(
        id="user-profile-test-3",
        email="apch@synchroserve.com",
        full_name="Original Name",
        role="L2_MANAGER",
        assigned_state="ANDHRA PRADESH",
    )

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        # Too short (< 2 chars)
        resp1 = client.patch(
            "/auth/profile",
            json={"full_name": "A"},
        )
        assert resp1.status_code == 422

        # Blank whitespace
        resp2 = client.patch(
            "/auth/profile",
            json={"full_name": "   "},
        )
        assert resp2.status_code == 400

        # Too long (> 100 chars)
        resp3 = client.patch(
            "/auth/profile",
            json={"full_name": "X" * 105},
        )
        assert resp3.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# -----------------------------------------------------------------------------
# 5. Role Segregation: L1 cannot L2 Review, L2 cannot L1 Submit
# -----------------------------------------------------------------------------
def test_l1_cannot_invoke_l2_review_actions():
    """Verify L1 Placement Coordinator cannot invoke L2 review actions."""
    l1_user = CurrentUser(
        id="l1-user-id",
        email="appe@synchroserve.com",
        full_name="AP Placement Executive",
        role="L1_COORDINATOR",
        assigned_state="ANDHRA PRADESH",
    )

    app.dependency_overrides[get_current_user] = lambda: l1_user
    try:
        # L2 approve
        r1 = client.post("/candidates/1001/audit/l2-review/approve", json={"notes": "test"})
        assert r1.status_code == 403

        # L2 reject
        r2 = client.post("/candidates/1001/audit/l2-review/reject", json={"reason": "test"})
        assert r2.status_code == 403

        # L2 return-to-l1
        r3 = client.post("/candidates/1001/audit/l2-review/return-to-l1", json={"reason": "test"})
        assert r3.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_l2_cannot_invoke_l1_submit_action():
    """Verify L2 Centre Head cannot invoke L1 submit audit action."""
    l2_user = CurrentUser(
        id="l2-user-id",
        email="apch@synchroserve.com",
        full_name="AP Centre Head",
        role="L2_MANAGER",
        assigned_state="ANDHRA PRADESH",
    )

    app.dependency_overrides[get_current_user] = lambda: l2_user
    try:
        r = client.post("/candidates/1001/audit/submit", json={})
        assert r.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# -----------------------------------------------------------------------------
# 6. Cross-State Dashboard Scoping Denial
# -----------------------------------------------------------------------------
def test_cross_state_dashboard_access_denied():
    """Verify an L1 or L2 assigned to Andhra Pradesh cannot access Tamil Nadu dashboard."""
    l1_ap = CurrentUser(
        id="l1-ap-id",
        email="appe@synchroserve.com",
        full_name="AP PE",
        role="L1_COORDINATOR",
        assigned_state="ANDHRA PRADESH",
    )

    app.dependency_overrides[get_current_user] = lambda: l1_ap
    try:
        resp = client.get("/dashboard/summary?state=TAMIL%20NADU")
        assert resp.status_code == 403
        assert "Access to state 'TAMIL NADU' is forbidden" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    l2_ap = CurrentUser(
        id="l2-ap-id",
        email="apch@synchroserve.com",
        full_name="AP CH",
        role="L2_MANAGER",
        assigned_state="ANDHRA PRADESH",
    )

    app.dependency_overrides[get_current_user] = lambda: l2_ap
    try:
        resp2 = client.get("/dashboard/summary?state=PUNJAB")
        assert resp2.status_code == 403
        assert "Access to state 'PUNJAB' is forbidden" in resp2.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
