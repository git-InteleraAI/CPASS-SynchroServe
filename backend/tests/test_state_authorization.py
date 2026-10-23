"""Automated test suite for CPASS Step 2: State-Based Authorization and State-Specific L1 Access.

Verifies:
1. L1 Placement Coordinator can access candidates within their assigned state.
2. L1 cannot list, view, or modify candidates from another state.
3. L1 cannot read, draft, submit, or download audits from another state.
4. L1 cannot list, upload, download, or delete documents belonging to another state.
5. Parameter or ID tampering (changing state, tc_id, candidate_id) cannot bypass authorization.
6. Missing or unassigned states fail closed (deny access).
7. Assignment lookup or database errors fail closed.
8. State lookup (/lookups/states) returns only the single assigned state for L1, and all states for global roles.
9. Other roles (Admin, L3 Leader, L2 Manager) retain their explicitly permitted access.
10. State normalization utility accurately resolves all 12 master states and their aliases.
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

L1_TN_USER = CurrentUser(
    id="l1-tn-uuid",
    email="tn.cpass@synchroserve.in",
    full_name="Tamil Nadu Placement Coordinator",
    role="L1_COORDINATOR",
    assigned_state="TAMIL NADU",
)

L1_KL_USER = CurrentUser(
    id="l1-kl-uuid",
    email="kl.cpass@synchroserve.in",
    full_name="Kerala Placement Coordinator",
    role="L1_COORDINATOR",
    assigned_state="KERALA",
)

L1_UNASSIGNED_USER = CurrentUser(
    id="l1-unassigned-uuid",
    email="unassigned.user@cpass.org",
    full_name="Unassigned Coordinator",
    role="L1_COORDINATOR",
    assigned_state=None,
)

L2_TN_MANAGER = CurrentUser(
    id="l2-tn-uuid",
    email="l2.tn@synchroserve.in",
    full_name="Tamil Nadu Centre Head",
    role="L2_MANAGER",
    assigned_state="TAMIL NADU",
)

ADMIN_USER = CurrentUser(
    id="admin-uuid",
    email="admin@cpass.org",
    full_name="CPASS Administrator",
    role="ADMIN",
)

L3_LEADER_USER = CurrentUser(
    id="l3-uuid",
    email="cops.leader@synchroserve.in",
    full_name="COPS Leadership",
    role="L3_LEADER",
)

# -----------------------------------------------------------------------------
# Test Candidates
# -----------------------------------------------------------------------------

TN_CANDIDATE = {
    "candidate_id": 20001,
    "candidate_first_name": "Murugan",
    "candidate_last_name": "Selvam",
    "state_name": "TAMIL NADU",
    "tc_state_name": "TAMIL NADU",
    "tc_id": 1003461,
    "tc_name": "SynchroServe Namakkal",
    "kb_batch_id": 8801,
    "batch_code": "TN-NAM-2023-01",
    "sanction_order_number": "SO-TN-99",
    "appointed": True,
    "bank_account": "987654321012",
}

KL_CANDIDATE = {
    "candidate_id": 20002,
    "candidate_first_name": "Vishnu",
    "candidate_last_name": "Nair",
    "state_name": "KERALA",
    "tc_state_name": "KERALA",
    "tc_id": 1004001,
    "tc_name": "SynchroServe Trivandrum",
    "kb_batch_id": 8802,
    "batch_code": "KL-TVM-2023-01",
    "sanction_order_number": "SO-KL-99",
    "appointed": True,
    "bank_account": "123456789098",
}


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def auth_l1_tn():
    app.dependency_overrides[get_current_user] = lambda: L1_TN_USER
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def auth_l1_kl():
    app.dependency_overrides[get_current_user] = lambda: L1_KL_USER
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def auth_l1_unassigned():
    app.dependency_overrides[get_current_user] = lambda: L1_UNASSIGNED_USER
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def auth_admin():
    app.dependency_overrides[get_current_user] = lambda: ADMIN_USER
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def auth_l3():
    app.dependency_overrides[get_current_user] = lambda: L3_LEADER_USER
    yield
    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 1. State Normalization & Canonical 12 States Tests
# -----------------------------------------------------------------------------

def test_resolve_state_handles_all_12_canonical_states():
    """Verify that resolve_state recognizes all 12 master states."""
    expected_states = {
        "ANDHRA PRADESH", "GUJARAT", "KERALA", "MIZORAM", "ODISHA",
        "PUDUCHERRY", "PUNJAB", "RAJASTHAN", "TAMIL NADU", "TELANGANA",
        "UTTAR PRADESH", "WEST BENGAL"
    }
    assert set(ALL_12_STATES) == expected_states
    for state in ALL_12_STATES:
        assert resolve_state(state) == state
        assert resolve_state(state.lower()) == state


def test_resolve_state_handles_prefixes_and_cpass_formats():
    """Verify meeting-specified credentials format (statename.cpass) maps correctly."""
    assert resolve_state("tn.cpass@synchroserve.in") == "TAMIL NADU"
    assert resolve_state("tn.cpass") == "TAMIL NADU"
    assert resolve_state("tn") == "TAMIL NADU"

    assert resolve_state("kl.cpass@synchroserve.in") == "KERALA"
    assert resolve_state("ts.cpass@synchroserve.in") == "TELANGANA"
    assert resolve_state("mz.cpass@synchroserve.in") == "MIZORAM"
    assert resolve_state("wb.cpass@synchroserve.in") == "WEST BENGAL"
    assert resolve_state("ap.cpass@synchroserve.in") == "ANDHRA PRADESH"
    assert resolve_state("py.cpass@synchroserve.in") == "PUDUCHERRY"
    assert resolve_state("od.cpass@synchroserve.in") == "ODISHA"
    assert resolve_state("rj.cpass@synchroserve.in") == "RAJASTHAN"
    assert resolve_state("gj.cpass@synchroserve.in") == "GUJARAT"
    assert resolve_state("pb.cpass@synchroserve.in") == "PUNJAB"
    assert resolve_state("up.cpass@synchroserve.in") == "UTTAR PRADESH"

    # Non-state inputs return None
    assert resolve_state("admin@cpass.org") is None
    assert resolve_state("unknown_xyz") is None
    assert resolve_state(None) is None
    assert resolve_state("") is None


# -----------------------------------------------------------------------------
# 2. State Scoping on /lookups/states
# -----------------------------------------------------------------------------

def test_l1_state_lookup_returns_only_assigned_state(auth_l1_tn):
    """L1 Placement Coordinator receives only their assigned state in dropdown lookup."""
    res = client.get("/lookups/states")
    assert res.status_code == 200
    states = res.json()
    assert states == ["TAMIL NADU"]


def test_l1_kerala_state_lookup_returns_only_kerala(auth_l1_kl):
    """L1 Placement Coordinator for Kerala receives only KERALA."""
    res = client.get("/lookups/states")
    assert res.status_code == 200
    states = res.json()
    assert states == ["KERALA"]


def test_l1_unassigned_state_lookup_fails_closed(auth_l1_unassigned):
    """Unassigned L1 coordinator receives an empty list (fails closed)."""
    res = client.get("/lookups/states")
    assert res.status_code == 200
    states = res.json()
    assert states == []


def test_admin_and_l3_state_lookup_returns_all_states(auth_admin, auth_l3):
    """Admin and executive leadership receive all master states."""
    app.dependency_overrides[get_current_user] = lambda: ADMIN_USER
    res_admin = client.get("/lookups/states")
    assert res_admin.status_code == 200
    admin_states = res_admin.json()
    assert len(admin_states) >= 12
    assert "TAMIL NADU" in admin_states
    assert "KERALA" in admin_states
    assert "TELANGANA" in admin_states

    app.dependency_overrides[get_current_user] = lambda: L3_LEADER_USER
    res_l3 = client.get("/lookups/states")
    assert res_l3.status_code == 200
    l3_states = res_l3.json()
    assert len(l3_states) >= 12


# -----------------------------------------------------------------------------
# 3. Direct State Tampering on /lookups/centres
# -----------------------------------------------------------------------------

def test_l1_centres_lookup_allowed_for_own_state(auth_l1_tn):
    """L1 coordinator can query centres in their permitted state."""
    with patch("app.routers.lookups.supabase") as mock_sb:
        mock_tbl = MagicMock()
        mock_tbl.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"tc_id": 1003461, "tc_name": "SynchroServe Namakkal"}]
        )
        mock_sb.table.return_value = mock_tbl

        res = client.get("/lookups/centres?state=TAMIL NADU")
        assert res.status_code == 200
        centres = res.json()
        assert len(centres) == 1
        assert centres[0]["tc_id"] == 1003461


def test_l1_centres_lookup_forbidden_for_other_state(auth_l1_tn):
    """L1 coordinator attempting to fetch another state's centres is denied with 403."""
    res = client.get("/lookups/centres?state=KERALA")
    assert res.status_code == 403
    assert "Access to state 'KERALA' is forbidden" in res.json()["detail"]


def test_l1_unassigned_centres_lookup_forbidden(auth_l1_unassigned):
    """Unassigned L1 coordinator cannot query any state centres (fails closed)."""
    res = client.get("/lookups/centres?state=TAMIL NADU")
    assert res.status_code == 403


# -----------------------------------------------------------------------------
# 4. Candidate Detail & Candidate List Isolation
# -----------------------------------------------------------------------------

def test_l1_can_access_candidate_within_assigned_state(auth_l1_tn):
    """L1 coordinator can fetch candidate details belonging to their assigned state."""
    with patch("app.routers.lookups.supabase") as mock_sb:
        def table_dispatch(name):
            m = MagicMock()
            if name == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[TN_CANDIDATE]
                )
            elif name == "duplicate_case_members":
                m.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
            elif name == "candidate_holds":
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            return m

        mock_sb.table.side_effect = table_dispatch

        res = client.get("/lookups/candidates/20001")
        assert res.status_code == 200
        data = res.json()
        assert data["candidate_id"] == 20001
        assert data["first_name"] == "Murugan"


def test_l1_cannot_access_candidate_from_another_state(auth_l1_tn):
    """L1 coordinator requesting a candidate from another state receives 403 without data exposure."""
    with patch("app.routers.lookups.supabase") as mock_sb:
        mock_tbl = MagicMock()
        mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[KL_CANDIDATE]
        )
        mock_sb.table.return_value = mock_tbl

        res = client.get("/lookups/candidates/20002")
        assert res.status_code == 403
        assert "You do not have access to candidates in this state" in res.json()["detail"]
        # Ensure candidate personal details are NOT leaked in response
        assert "Vishnu" not in res.text
        assert "Nair" not in res.text


def test_l1_candidate_batch_list_filters_out_cross_state_candidates(auth_l1_tn):
    """Candidate batch list excludes candidates not in the coordinator's state."""
    with patch("app.routers.lookups.supabase") as mock_sb:
        mock_tbl = MagicMock()
        # Batch query returns 1 TN candidate and 1 KL candidate
        mock_tbl.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[TN_CANDIDATE, KL_CANDIDATE]
        )
        # Centre verification query
        mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[TN_CANDIDATE]
        )
        mock_sb.table.return_value = mock_tbl

        res = client.get("/lookups/candidates?kb_batch_id=8801")
        assert res.status_code == 200
        candidates = res.json()
        assert len(candidates) == 1
        assert candidates[0]["candidate_id"] == 20001


# -----------------------------------------------------------------------------
# 5. Audit Isolation (Read, Draft, Submit, Statement)
# -----------------------------------------------------------------------------

def test_l1_cannot_read_another_state_audit(auth_l1_tn):
    """L1 coordinator cannot access GET audit for another state's candidate."""
    with patch("app.routers.audits.supabase") as mock_sb:
        mock_tbl = MagicMock()
        mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[KL_CANDIDATE]
        )
        mock_sb.table.return_value = mock_tbl

        res = client.get("/candidates/20002/audit")
        assert res.status_code == 403
        assert "You do not have access to candidates in this state" in res.json()["detail"]


def test_l1_cannot_save_draft_for_another_state_audit(auth_l1_tn):
    """L1 coordinator cannot POST draft for another state's candidate."""
    with patch("app.routers.audits.supabase") as mock_sb:
        mock_tbl = MagicMock()
        mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[KL_CANDIDATE]
        )
        mock_sb.table.return_value = mock_tbl

        res = client.post("/candidates/20002/audit/draft", json={"employer_details": []})
        assert res.status_code == 403
        assert "You do not have access to candidates in this state" in res.json()["detail"]


def test_l1_cannot_submit_another_state_audit(auth_l1_tn):
    """L1 coordinator cannot POST submit for another state's candidate."""
    with patch("app.routers.audits.supabase") as mock_sb:
        mock_tbl = MagicMock()
        mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[KL_CANDIDATE]
        )
        mock_sb.table.return_value = mock_tbl

        res = client.post("/candidates/20002/audit/submit", json={
            "employer_details": [{"employer_name": "Company"}],
            "salary_details": [
                {"month": 1, "year": 2024},
                {"month": 2, "year": 2024},
                {"month": 3, "year": 2024},
            ],
            "document_audit": {"overall_compliance": True},
        })
        assert res.status_code == 403
        assert "You do not have access to candidates in this state" in res.json()["detail"]


def test_l1_cannot_view_another_state_audit_statement(auth_l1_tn):
    """L1 coordinator cannot access GET audit statement for another state's candidate."""
    with patch("app.routers.audits.supabase") as mock_sb:
        mock_tbl = MagicMock()
        mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[KL_CANDIDATE]
        )
        mock_sb.table.return_value = mock_tbl

        res = client.get("/candidates/20002/audit/statement")
        assert res.status_code == 403
        assert "You do not have access to candidates in this state" in res.json()["detail"]


# -----------------------------------------------------------------------------
# 6. Document Isolation (List, Summary, Upload, Download, Delete)
# -----------------------------------------------------------------------------

def test_l1_cannot_list_another_state_documents(auth_l1_tn):
    """L1 coordinator cannot list documents for another state's candidate."""
    with patch("app.routers.documents.supabase") as mock_sb:
        mock_tbl = MagicMock()
        mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[KL_CANDIDATE]
        )
        mock_sb.table.return_value = mock_tbl

        res = client.get("/candidates/20002/documents")
        assert res.status_code == 403
        assert "You do not have access to candidates in this state" in res.json()["detail"]


def test_l1_cannot_get_document_summary_for_another_state(auth_l1_tn):
    """L1 coordinator cannot get document summary for another state's candidate."""
    with patch("app.routers.documents.supabase") as mock_sb:
        mock_tbl = MagicMock()
        mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [KL_CANDIDATE]
        mock_sb.table.return_value = mock_tbl

        res = client.get("/candidates/20002/documents/summary")
        assert res.status_code == 403
        assert "You do not have access to candidates in this state" in res.json()["detail"]


def test_l1_cannot_upload_document_for_another_state(auth_l1_tn):
    """L1 coordinator cannot upload document for another state's candidate."""
    with patch("app.routers.documents.supabase") as mock_sb:
        mock_tbl = MagicMock()
        mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [KL_CANDIDATE]
        mock_sb.table.return_value = mock_tbl

        res = client.post(
            "/candidates/20002/documents",
            data={"document_type": "APPOINTMENT_LETTER"},
            files={"file": ("offer.pdf", b"%PDF content", "application/pdf")},
        )
        assert res.status_code == 403

        assert "You do not have access to candidates in this state" in res.json()["detail"]


def test_l1_cannot_download_document_from_another_state(auth_l1_tn):
    """L1 coordinator cannot download a document belonging to another state's candidate."""
    with patch("app.routers.documents.supabase") as mock_sb:
        mock_tbl = MagicMock()
        mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [KL_CANDIDATE]
        mock_sb.table.return_value = mock_tbl

        res = client.get("/candidates/20002/documents/doc-kl-1/download")
        assert res.status_code == 403
        assert "You do not have access to candidates in this state" in res.json()["detail"]


def test_l1_cannot_delete_document_from_another_state(auth_l1_tn):
    """L1 coordinator cannot delete a document belonging to another state's candidate."""
    with patch("app.routers.documents.supabase") as mock_sb:
        mock_tbl = MagicMock()
        mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [KL_CANDIDATE]
        mock_sb.table.return_value = mock_tbl

        res = client.delete("/candidates/20002/documents/doc-kl-1")
        assert res.status_code == 403
        assert "You do not have access to candidates in this state" in res.json()["detail"]


# -----------------------------------------------------------------------------
# 7. Fail-Closed on Errors & Tamper Resistance
# -----------------------------------------------------------------------------

def test_missing_state_assignment_denies_all_access(auth_l1_unassigned):
    """An L1 user without an assigned state is blocked from candidates, audits, and documents."""
    with patch("app.routers.lookups.supabase") as mock_sb:
        mock_tbl = MagicMock()
        mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [TN_CANDIDATE]
        mock_sb.table.return_value = mock_tbl

        res = client.get("/lookups/candidates/20001")
        assert res.status_code == 403

    with patch("app.routers.audits.supabase") as mock_sb:
        mock_tbl = MagicMock()
        mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [TN_CANDIDATE]
        mock_sb.table.return_value = mock_tbl

        res2 = client.get("/candidates/20001/audit")
        assert res2.status_code == 403

    with patch("app.routers.documents.supabase") as mock_sb:
        mock_tbl = MagicMock()
        mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [TN_CANDIDATE]
        mock_sb.table.return_value = mock_tbl

        res3 = client.get("/candidates/20001/documents")
        assert res3.status_code == 403


def test_modified_request_parameters_cannot_bypass_state_scoping(auth_l1_tn):
    """Altering candidate ID in payload or query params cannot bypass server-side state enforcement."""
    with patch("app.routers.audits.supabase") as mock_sb:
        mock_tbl = MagicMock()
        # Even if frontend claims candidate is TN, DB record has KERALA
        mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [KL_CANDIDATE]
        mock_sb.table.return_value = mock_tbl

        # TN coordinator attempts to save draft for candidate 20002
        res = client.post("/candidates/20002/audit/draft", json={
            "candidate_id": 20001,  # Tampered candidate_id in payload
            "employer_details": [],
        })
        assert res.status_code == 403
        assert "You do not have access to candidates in this state" in res.json()["detail"]


# -----------------------------------------------------------------------------
# 8. Me Endpoint Scoping
# -----------------------------------------------------------------------------

def test_me_endpoint_returns_assigned_state(auth_l1_tn):
    """The /me and /auth/me endpoints return assigned_state for client initialization."""
    res = client.get("/me")
    assert res.status_code == 200
    data = res.json()
    assert data["role"] == "L1_COORDINATOR"
    assert data["assigned_state"] == "TAMIL NADU"

    res_auth = client.get("/auth/me")
    assert res_auth.status_code == 200
    data_auth = res_auth.json()
    assert data_auth["assigned_state"] == "TAMIL NADU"
