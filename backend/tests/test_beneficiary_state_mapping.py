"""Automated regression test suite for CPASS Beneficiary State Mapping.

Verifies:
1. Candidate ownership and state-scoped candidate access uses ddugky_candidates.state_name (beneficiary state).
2. Mizoram beneficiary candidate (state_name=MIZORAM, tc_state_name=TELANGANA, tc_id=1005985):
   - Mizoram coordinator can access candidate detail, documents, audit.
   - Mizoram dashboard summary and candidate list include the candidate.
   - Training centre state remains Telangana in response metadata.
   - Telangana coordinator is rejected with HTTP 403 despite the centre being in Telangana.
3. Candidate scoping across all 12 CPASS master beneficiary states.
4. Security fail-closed rules:
   - Missing, blank, or invalid state_name fails closed (HTTP 403).
   - Cross-state tampering is denied.
   - Training centre ID restrictions (allowed_tc_ids) remain strictly enforced.
   - Admin and national roles retain global access.
5. Pending/Remaining calculation integrity is preserved exactly.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.auth import (
    ALL_12_STATES,
    CurrentUser,
    allowed_states,
    allowed_tc_ids,
    check_candidate_access,
    get_candidate_state,
    get_current_user,
    resolve_state,
)
from app.main import app

client = TestClient(app)

# -----------------------------------------------------------------------------
# Test Users
# -----------------------------------------------------------------------------

L1_MIZORAM = CurrentUser(
    id="l1-mz-uuid",
    email="mz.coord@cpass.org",
    full_name="Mizoram Placement Coordinator",
    role="L1_COORDINATOR",
    assigned_state="MIZORAM",
)

L1_TELANGANA = CurrentUser(
    id="l1-tg-uuid",
    email="tg.coord@cpass.org",
    full_name="Telangana Placement Coordinator",
    role="L1_COORDINATOR",
    assigned_state="TELANGANA",
)

L1_ODISHA = CurrentUser(
    id="l1-od-uuid",
    email="od.coord@cpass.org",
    full_name="Odisha Placement Coordinator",
    role="L1_COORDINATOR",
    assigned_state="ODISHA",
)

L1_RESTRICTED_TC = CurrentUser(
    id="l1-tc-uuid",
    email="tc.coord@cpass.org",
    full_name="TC Restricted Coordinator",
    role="L1_COORDINATOR",
    assigned_state="MIZORAM",
)

ADMIN_USER = CurrentUser(
    id="admin-uuid",
    email="admin@cpass.org",
    full_name="Administrator",
    role="ADMIN",
)

L3_COPS = CurrentUser(
    id="l3-uuid",
    email="cops@cpass.org",
    full_name="COPS Auditor",
    role="L3_COPS",
)

L4_LEADER = CurrentUser(
    id="l4-uuid",
    email="bl@cpass.org",
    full_name="Business Leader",
    role="L4_LEADER",
    assigned_states=["MIZORAM", "TELANGANA"],
)

# -----------------------------------------------------------------------------
# Test Candidate: Mizoram Beneficiary Trained in Telangana
# -----------------------------------------------------------------------------

MIZORAM_CANDIDATE = {
    "candidate_id": 1076617,
    "candidate_first_name": "Lal",
    "candidate_last_name": "Rinzuala",
    "candidate_father_name": "Zothanmawia",
    "gender": "MALE",
    "date_of_birth": "1998-04-12",
    "mobile_number": "9862123456",
    "appointed": True,
    "employer_name": "Tech Corp Pvt Ltd",
    "tc_id": 1005985,
    "tc_name": "SYNCHROSERVE - HYDERABAD",
    "state_name": "MIZORAM",
    "tc_state_name": "TELANGANA",
    "kb_batch_id": 9901,
    "batch_code": "MZ-SYN-2023-01",
    "sanction_order_number": "SO-MZ-01",
    "bank_account": "123456789012",
}


# =============================================================================
# 1. Mizoram Beneficiary Candidate Access & Telangana Blocked
# =============================================================================

def test_mizoram_coordinator_can_access_mizoram_candidate():
    """Mizoram coordinator can access candidate whose state_name=MIZORAM even if tc_state_name=TELANGANA."""
    app.dependency_overrides[get_current_user] = lambda: L1_MIZORAM

    with patch("app.routers.lookups.supabase") as mock_sb:
        mock_tbl = MagicMock()
        mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[MIZORAM_CANDIDATE]
        )
        mock_sb.table.return_value = mock_tbl

        res = client.get("/lookups/candidates/1076617")
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["candidate_id"] == 1076617
        assert data["state_name"] == "MIZORAM"
        assert data["tc_state_name"] == "TELANGANA"
        assert data["tc_name"] == "SYNCHROSERVE - HYDERABAD"

    app.dependency_overrides.clear()


def test_telangana_coordinator_blocked_from_mizoram_candidate():
    """Telangana coordinator is blocked (HTTP 403) from candidate with state_name=MIZORAM, even though tc is in Telangana."""
    app.dependency_overrides[get_current_user] = lambda: L1_TELANGANA

    with patch("app.routers.lookups.supabase") as mock_sb:
        mock_tbl = MagicMock()
        mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[MIZORAM_CANDIDATE]
        )
        mock_sb.table.return_value = mock_tbl

        res = client.get("/lookups/candidates/1076617")
        assert res.status_code == 403
        assert "access" in res.json()["detail"].lower()

    app.dependency_overrides.clear()


def test_mizoram_candidate_document_access_permitted_for_mizoram_denied_for_telangana():
    """Document access relies on candidate beneficiary state_name."""
    # Mizoram coordinator access permitted
    app.dependency_overrides[get_current_user] = lambda: L1_MIZORAM
    with patch("app.routers.documents.supabase") as mock_sb:
        mock_tbl = MagicMock()
        mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[MIZORAM_CANDIDATE]
        )
        mock_tbl.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_sb.table.return_value = mock_tbl

        res_mz = client.get("/candidates/1076617/documents")
        assert res_mz.status_code == 200

    # Telangana coordinator access denied with 403
    app.dependency_overrides[get_current_user] = lambda: L1_TELANGANA
    with patch("app.routers.documents.supabase") as mock_sb:
        mock_tbl = MagicMock()
        mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[MIZORAM_CANDIDATE]
        )
        mock_sb.table.return_value = mock_tbl

        res_tg = client.get("/candidates/1076617/documents")
        assert res_tg.status_code == 403

    app.dependency_overrides.clear()


def test_mizoram_candidate_audit_access_permitted_for_mizoram_denied_for_telangana():
    """Audit access relies on candidate beneficiary state_name."""
    # Mizoram coordinator access permitted
    app.dependency_overrides[get_current_user] = lambda: L1_MIZORAM
    with patch("app.routers.audits.supabase") as mock_sb:
        def table_mock(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[MIZORAM_CANDIDATE])
            elif tbl == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            return m
        mock_sb.table.side_effect = table_mock

        res_mz = client.get("/candidates/1076617/audit")
        assert res_mz.status_code == 200

    # Telangana coordinator access denied with 403
    app.dependency_overrides[get_current_user] = lambda: L1_TELANGANA
    with patch("app.routers.audits.supabase") as mock_sb:
        def table_mock(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[MIZORAM_CANDIDATE])
            return m
        mock_sb.table.side_effect = table_mock

        res_tg = client.get("/candidates/1076617/audit")
        assert res_tg.status_code == 403

    app.dependency_overrides.clear()


# =============================================================================
# 2. Dashboard Scoping: Summary & Candidate List
# =============================================================================

def test_dashboard_summary_queries_state_name_not_tc_state_name():
    """Dashboard summary aggregates candidates by state_name."""
    app.dependency_overrides[get_current_user] = lambda: ADMIN_USER

    captured_filters = []

    with patch("app.routers.dashboard.supabase") as mock_sb:
        def table_mock(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                def eq_mock(col, val):
                    captured_filters.append((col, val))
                    eq_obj = MagicMock()
                    eq_obj.limit.return_value.execute.return_value = MagicMock(count=192, data=[])
                    eq_obj.execute.return_value = MagicMock(data=[{"candidate_id": 1076617, "state_name": "MIZORAM", "tc_state_name": "TELANGANA"}])
                    return eq_obj
                m.select.return_value.eq.side_effect = eq_mock
                m.select.return_value.in_.return_value.eq.side_effect = eq_mock
            elif tbl == "candidate_documents":
                m.select.return_value.neq.return_value.execute.return_value = MagicMock(data=[{"candidate_id": 1076617}])
            elif tbl == "placement_audits":
                m.select.return_value.execute.return_value = MagicMock(data=[])
            return m

        mock_sb.table.side_effect = table_mock

        res = client.get("/dashboard/summary?state=MIZORAM")
        assert res.status_code == 200
        data = res.json()
        assert data["state"] == "MIZORAM"

        # Verify state_name was queried and not tc_state_name
        queried_cols = [col for col, val in captured_filters]
        assert "state_name" in queried_cols, f"Expected state_name in queried columns, got {queried_cols}"
        assert "tc_state_name" not in queried_cols, f"tc_state_name should not be queried for state scoping, got {queried_cols}"

    app.dependency_overrides.clear()


def test_dashboard_candidates_queries_state_name_and_surfaces_tc_state_name():
    """Dashboard candidates list filters by state_name and returns tc_state_name."""
    app.dependency_overrides[get_current_user] = lambda: ADMIN_USER

    with patch("app.routers.dashboard.supabase") as mock_sb:
        def table_mock(tbl):
            m = MagicMock()
            if tbl == "candidate_documents":
                m.select.return_value.neq.return_value.execute.return_value = MagicMock(data=[])
            elif tbl == "placement_audits":
                m.select.return_value.execute.return_value = MagicMock(data=[])
            elif tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value = MagicMock(
                    data=[MIZORAM_CANDIDATE]
                )
                m.select.return_value.eq.return_value.count = 1
            return m

        mock_sb.table.side_effect = table_mock

        res = client.get("/dashboard/candidates?state=MIZORAM&filter=total")
        assert res.status_code == 200
        data = res.json()
        assert data["total_count"] == 1
        cands = data["candidates"]
        assert len(cands) == 1
        cand = cands[0]
        assert cand["state_name"] == "MIZORAM"
        assert cand["tc_state_name"] == "TELANGANA"
        assert cand["tc_name"] == "SYNCHROSERVE - HYDERABAD"

    app.dependency_overrides.clear()


# =============================================================================
# 3. Lookups: Centres Dropdown Queries by Beneficiary State
# =============================================================================

def test_centres_lookup_queries_by_beneficiary_state_name():
    """Lookups /centres queries distinct centres where state_name matches."""
    app.dependency_overrides[get_current_user] = lambda: L1_MIZORAM

    captured_centre_query = []

    with patch("app.routers.lookups.supabase") as mock_sb:
        def table_mock(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                def eq_mock(col, val):
                    captured_centre_query.append((col, val))
                    eq_obj = MagicMock()
                    eq_obj.execute.return_value = MagicMock(
                        data=[{"tc_id": 1005985, "tc_name": "SYNCHROSERVE - HYDERABAD", "tc_state_name": "TELANGANA"}]
                    )
                    return eq_obj
                m.select.return_value.eq.side_effect = eq_mock
            return m

        mock_sb.table.side_effect = table_mock

        res = client.get("/lookups/centres?state=MIZORAM")
        assert res.status_code == 200
        centres = res.json()
        assert len(centres) == 1
        assert centres[0]["tc_id"] == 1005985
        assert centres[0]["name"] == "SYNCHROSERVE - HYDERABAD"
        assert centres[0]["tc_state_name"] == "TELANGANA"

        assert ("state_name", "MIZORAM") in captured_centre_query
        assert ("tc_state_name", "MIZORAM") not in captured_centre_query

    app.dependency_overrides.clear()


# =============================================================================
# 4. Scoping for All Master CPASS States
# =============================================================================

@pytest.mark.parametrize("state", sorted(ALL_12_STATES))
def test_all_master_states_use_state_name(state):
    """get_candidate_state derives state ownership from state_name for all master CPASS states."""
    candidate_record = {
        "candidate_id": 55001,
        "state_name": state,
        "tc_state_name": "OTHER_STATE",
    }
    extracted = get_candidate_state(candidate_record)
    assert extracted == resolve_state(state)

    # State coordinator of that state is authorized
    coord = CurrentUser(id="coord-id", email="coord@cpass.org", full_name="Coord", role="L1_COORDINATOR", assigned_state=state)
    check_candidate_access(coord, candidate_record)

    # Different state coordinator is blocked
    other_state = "KERALA" if resolve_state(state) != "KERALA" else "ODISHA"
    foreign_coord = CurrentUser(id="foreign-id", email="foreign@cpass.org", full_name="Foreign Coord", role="L1_COORDINATOR", assigned_state=other_state)
    with pytest.raises(Exception) as exc_info:
        check_candidate_access(foreign_coord, candidate_record)
    assert "403" in str(exc_info.value) or exc_info.value.status_code == 403


# =============================================================================
# 5. Security Tests: Fail-Closed & Centre-ID Restrictions
# =============================================================================

@pytest.mark.parametrize("bad_state", [None, "", "   ", "UNKNOWN_REGION", 12345])
def test_security_missing_or_invalid_state_name_fails_closed(bad_state):
    """Missing or invalid state_name returns None and check_candidate_access raises 403."""
    bad_cand = {
        "candidate_id": 99999,
        "state_name": bad_state,
        "tc_state_name": "ODISHA",
    }
    assert get_candidate_state(bad_cand) is None

    with pytest.raises(Exception) as exc_info:
        check_candidate_access(L1_ODISHA, bad_cand)
    assert exc_info.value.status_code == 403


def test_security_centre_id_restrictions_enforced():
    """Even if state_name matches, candidate outside allowed_tc_ids is rejected with 403."""
    cand_different_tc = {
        "candidate_id": 1076617,
        "state_name": "MIZORAM",
        "tc_state_name": "TELANGANA",
        "tc_id": 9999999,  # Not in allowed centre list [1005985]
    }
    with patch("app.auth.allowed_tc_ids", return_value=[1005985]):
        with pytest.raises(Exception) as exc_info:
            check_candidate_access(L1_RESTRICTED_TC, cand_different_tc)
    assert exc_info.value.status_code == 403
    assert "training centre" in exc_info.value.detail.lower()


def test_security_admin_and_national_roles_retain_intended_access():
    """Admin and national roles (L3_COPS, L4_LEADER) retain access across states."""
    check_candidate_access(ADMIN_USER, MIZORAM_CANDIDATE)
    check_candidate_access(L3_COPS, MIZORAM_CANDIDATE)
    check_candidate_access(L4_LEADER, MIZORAM_CANDIDATE)


# =============================================================================
# 6. Pending/Remaining Calculation Integrity & State-Scoping Status Lifecycle
# =============================================================================

def test_pending_remaining_formula_integrity():
    """Pending/Remaining must equal Total - Uploaded - In Progress across all candidate workflow stages.

    Verifies:
    1. Scenario A: Document-only candidate -> In Progress = 1, Uploaded = 0, Pending = 191
    2. Scenario B: Final audit submitted candidate -> Uploaded = 1, In Progress = 0, Pending = 191
    3. Scenario C: Not started candidate -> Uploaded = 0, In Progress = 0, Pending = 192
    4. Beneficiary state mapping (state_name=MIZORAM, tc_state_name=TELANGANA) is strictly preserved in all cases.
    5. Invariant Total == Pending + In Progress + Uploaded holds consistently.
    """
    app.dependency_overrides[get_current_user] = lambda: ADMIN_USER

    # Scenario A: Documents uploaded, no audit submission -> In Progress = 1, Uploaded = 0, Pending = 191
    with patch("app.routers.dashboard.supabase") as mock_sb:
        def table_mock(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(count=192, data=[])
                m.select.return_value.in_.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"candidate_id": 1076617, "state_name": "MIZORAM", "tc_state_name": "TELANGANA"}]
                )
            elif tbl == "candidate_documents":
                m.select.return_value.neq.return_value.execute.return_value = MagicMock(data=[{"candidate_id": 1076617}])
            elif tbl == "placement_audits":
                m.select.return_value.execute.return_value = MagicMock(data=[])
            return m

        mock_sb.table.side_effect = table_mock

        res = client.get("/dashboard/summary?state=MIZORAM")
        assert res.status_code == 200
        data = res.json()
        total = data["total"]
        uploaded = data["cpass_uploaded"]
        in_progress = data["in_progress"]
        pending = data["pending_remaining"]

        assert total == 192
        # Document-only candidate is In Progress, NOT Uploaded
        assert uploaded == 0
        assert in_progress == 1
        # Formula: pending_remaining = total - uploaded - in_progress = 192 - 0 - 1 = 191
        assert pending == 191
        assert pending == total - uploaded - in_progress
        assert total == pending + in_progress + uploaded
        assert data["state"] == "MIZORAM"

    # Scenario B: Final audit submitted -> Uploaded = 1, In Progress = 0, Pending = 191
    with patch("app.routers.dashboard.supabase") as mock_sb:
        def table_mock(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(count=192, data=[])
                m.select.return_value.in_.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"candidate_id": 1076617, "state_name": "MIZORAM", "tc_state_name": "TELANGANA"}]
                )
            elif tbl == "candidate_documents":
                m.select.return_value.neq.return_value.execute.return_value = MagicMock(data=[{"candidate_id": 1076617}])
            elif tbl == "placement_audits":
                m.select.return_value.execute.return_value = MagicMock(data=[{
                    "candidate_id": 1076617,
                    "cpass_status": "PENDING",
                    "audit_status": "SUBMITTED",
                    "signoff_details": {},
                    "finalized_at": "2026-11-08T12:00:00Z",
                }])
            return m

        mock_sb.table.side_effect = table_mock

        res = client.get("/dashboard/summary?state=MIZORAM")
        assert res.status_code == 200
        data = res.json()
        total = data["total"]
        uploaded = data["cpass_uploaded"]
        in_progress = data["in_progress"]
        pending = data["pending_remaining"]

        assert total == 192
        # Submitted candidate is Uploaded = 1, In Progress = 0
        assert uploaded == 1
        assert in_progress == 0
        assert pending == 191
        assert pending == total - uploaded - in_progress
        assert total == pending + in_progress + uploaded
        assert data["state"] == "MIZORAM"

    # Scenario C: Candidate not started -> Uploaded = 0, In Progress = 0, Pending = 192
    with patch("app.routers.dashboard.supabase") as mock_sb:
        def table_mock(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(count=192, data=[])
                m.select.return_value.in_.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            elif tbl == "candidate_documents":
                m.select.return_value.neq.return_value.execute.return_value = MagicMock(data=[])
            elif tbl == "placement_audits":
                m.select.return_value.execute.return_value = MagicMock(data=[])
            return m

        mock_sb.table.side_effect = table_mock

        res = client.get("/dashboard/summary?state=MIZORAM")
        assert res.status_code == 200
        data = res.json()
        total = data["total"]
        uploaded = data["cpass_uploaded"]
        in_progress = data["in_progress"]
        pending = data["pending_remaining"]

        assert total == 192
        assert uploaded == 0
        assert in_progress == 0
        assert pending == 192
        assert pending == total - uploaded - in_progress
        assert total == pending + in_progress + uploaded
        assert data["state"] == "MIZORAM"

    app.dependency_overrides.clear()

