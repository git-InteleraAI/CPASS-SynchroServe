"""Automated tests for CPASS Placement Coordinator (L1) Dashboard API.

Verifies:
1. /dashboard/summary returns real-database counts scoped to authenticated L1 coordinator's assigned state.
2. Direct state parameter tampering (e.g. TN coordinator querying KERALA) is rejected with 403 Forbidden.
3. Unassigned L1 coordinator fails closed (all counts 0).
4. Confirmed Pending formula: Pending / Remaining = Total Candidates - CPASS Uploaded Candidates.
5. /dashboard/candidates returns matching counts and records for each of the 5 filters:
   - total
   - cpass_approved
   - cpass_rejected
   - cpass_uploaded
   - pending_remaining
6. Candidate search and pagination work correctly.
7. Payslip availability endpoint (/dashboard/candidates/{id}/payslip-availability):
   - Successfully marks 'No' (Not Available) or 'Yes' (Browse).
   - Rejects conflicting state if a verified payslip document is already uploaded.
   - Blocks cross-state candidate tampering with 403.
   - Does not fabricate complete status if payslip is unavailable.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentUser, get_current_user
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
    email="unassigned.coordinator@cpass.org",
    full_name="Unassigned Coordinator",
    role="L1_COORDINATOR",
    assigned_state=None,
)

ADMIN_USER = CurrentUser(
    id="admin-uuid",
    email="admin@cpass.org",
    full_name="Administrator",
    role="ADMIN",
)

TN_CANDIDATE = {
    "candidate_id": 99001,
    "candidate_first_name": "Ravi",
    "candidate_last_name": "Chandran",
    "candidate_father_name": "Chandran K",
    "gender": "MALE",
    "mobile_number": "9876543210",
    "state_name": "TAMIL NADU",
    "tc_state_name": "TAMIL NADU",
    "tc_id": 1003461,
    "tc_name": "SynchroServe Salem",
    "kb_batch_id": 8801,
    "batch_code": "TN-SLM-2023-01",
    "sanction_order_number": "SO-TN-01",
    "appointed": True,
}

KL_CANDIDATE = {
    "candidate_id": 99002,
    "candidate_first_name": "Anil",
    "candidate_last_name": "Kurup",
    "candidate_father_name": "Kurup M",
    "gender": "MALE",
    "mobile_number": "9845123456",
    "state_name": "KERALA",
    "tc_state_name": "KERALA",
    "tc_id": 1004001,
    "tc_name": "SynchroServe Cochin",
    "kb_batch_id": 8802,
    "batch_code": "KL-COK-2023-01",
    "sanction_order_number": "SO-KL-01",
    "appointed": True,
}


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


# -----------------------------------------------------------------------------
# 1. Summary Cards and State Scoping Tests
# -----------------------------------------------------------------------------

def test_dashboard_summary_state_scoping_for_l1(auth_l1_tn):
    """L1 coordinator receives summary card counts scoped strictly to their assigned state."""
    with patch("app.routers.dashboard.supabase") as mock_sb:
        # Mock ddugky_candidates count = 50
        mock_total_res = MagicMock(count=50)
        # Mock candidate_documents: 10 candidates with documents in TN
        mock_docs_res = MagicMock(data=[
            {"candidate_id": 99001}, {"candidate_id": 99003}, {"candidate_id": 99004}
        ])
        # Mock placement_audits: candidate 99001 approved, 99004 rejected
        mock_aud_res = MagicMock(data=[
            {"candidate_id": 99001, "cpass_status": "L2_APPROVED", "audit_status": "SUBMITTED"},
            {"candidate_id": 99003, "cpass_status": "PENDING", "audit_status": "SUBMITTED"},
            {"candidate_id": 99004, "cpass_status": "REJECTED", "audit_status": "REJECTED"},
        ])
        # Mock cand_check returning these 3 candidates belong to TAMIL NADU
        mock_cand_check = MagicMock(data=[
            {"candidate_id": 99001, "state_name": "TAMIL NADU", "tc_state_name": "TAMIL NADU"},
            {"candidate_id": 99003, "state_name": "TAMIL NADU", "tc_state_name": "TAMIL NADU"},
            {"candidate_id": 99004, "state_name": "TAMIL NADU", "tc_state_name": "TAMIL NADU"},
        ])

        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                # First call: total count query
                t.select.return_value.or_.return_value.limit.return_value.execute.return_value = mock_total_res
                # Second call: candidate state check
                t.select.return_value.in_.return_value.or_.return_value.execute.return_value = mock_cand_check
            elif name == "candidate_documents":
                t.select.return_value.neq.return_value.execute.return_value = mock_docs_res
            elif name == "placement_audits":
                t.select.return_value.execute.return_value = mock_aud_res
            return t

        mock_sb.table.side_effect = table_dispatch

        res = client.get("/dashboard/summary")
        assert res.status_code == 200
        data = res.json()

        assert data["state"] == "TAMIL NADU"
        assert data["total"] == 50
        assert data["cpass_uploaded"] == 3
        # Confirmed business rule: Pending = Total - Uploaded = 50 - 3 = 47
        assert data["pending_remaining"] == 47
        assert data["cpass_approved"] == 1
        assert data["cpass_rejected"] == 1


def test_dashboard_summary_state_tampering_blocked(auth_l1_tn):
    """L1 coordinator assigned to Tamil Nadu cannot tamper query to inspect Kerala."""
    res = client.get("/dashboard/summary?state=KERALA")
    assert res.status_code == 403
    assert "forbidden" in res.json()["detail"].lower()


def test_dashboard_summary_unassigned_fails_closed(auth_l1_unassigned):
    """Unassigned L1 coordinator fails closed (all zeros)."""
    res = client.get("/dashboard/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["state"] is None
    assert data["total"] == 0
    assert data["pending_remaining"] == 0
    assert data["cpass_uploaded"] == 0


def test_confirmed_pending_formula_strict_verification(auth_l1_tn):
    """Pending count MUST equal Total - Uploaded and never Total - (Approved + Rejected)."""
    with patch("app.routers.dashboard.supabase") as mock_sb:
        # Total = 100, Uploaded = 20, Approved = 10, Rejected = 5
        mock_total_res = MagicMock(count=100)
        uploaded_cids = [1000 + i for i in range(20)]
        mock_docs_res = MagicMock(data=[{"candidate_id": cid} for cid in uploaded_cids])
        mock_aud_res = MagicMock(data=[
            {"candidate_id": uploaded_cids[0], "cpass_status": "L2_APPROVED", "audit_status": "SUBMITTED"},
            {"candidate_id": uploaded_cids[1], "cpass_status": "REJECTED", "audit_status": "REJECTED"},
        ])
        mock_cand_check = MagicMock(data=[
            {"candidate_id": cid, "state_name": "TAMIL NADU", "tc_state_name": "TAMIL NADU"}
            for cid in uploaded_cids
        ])

        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                t.select.return_value.or_.return_value.limit.return_value.execute.return_value = mock_total_res
                t.select.return_value.in_.return_value.or_.return_value.execute.return_value = mock_cand_check
            elif name == "candidate_documents":
                t.select.return_value.neq.return_value.execute.return_value = mock_docs_res
            elif name == "placement_audits":
                t.select.return_value.execute.return_value = mock_aud_res
            return t

        mock_sb.table.side_effect = table_dispatch

        res = client.get("/dashboard/summary")
        assert res.status_code == 200
        data = res.json()

        assert data["total"] == 100
        assert data["cpass_uploaded"] == 20
        # Pending MUST BE 100 - 20 = 80, NOT 100 - (10 + 5) = 85
        assert data["pending_remaining"] == 80
        assert data["pending_remaining"] == data["total"] - data["cpass_uploaded"]


# -----------------------------------------------------------------------------
# 2. Filtered Candidate List Tests
# -----------------------------------------------------------------------------

def test_dashboard_candidates_total_filter(auth_l1_tn):
    """'total' filter queries all candidates in coordinator's state."""
    with patch("app.routers.dashboard.supabase") as mock_sb:
        mock_rows = [TN_CANDIDATE]
        mock_q_res = MagicMock(count=1, data=mock_rows)

        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                # Base candidate query
                t.select.return_value.or_.return_value.order.return_value.range.return_value.execute.return_value = mock_q_res
            elif name == "candidate_documents":
                t.select.return_value.neq.return_value.execute.return_value = MagicMock(data=[])
            elif name == "placement_audits":
                t.select.return_value.execute.return_value = MagicMock(data=[])
            return t

        mock_sb.table.side_effect = table_dispatch

        res = client.get("/dashboard/candidates?filter=total&page=1&page_size=10")
        assert res.status_code == 200
        data = res.json()

        assert data["filter"] == "total"
        assert data["state"] == "TAMIL NADU"
        assert data["total_count"] == 1
        assert len(data["candidates"]) == 1
        assert data["candidates"][0]["candidate_id"] == 99001
        assert data["candidates"][0]["is_uploaded"] is False


def test_dashboard_candidates_pending_remaining_excludes_uploaded(auth_l1_tn):
    """'pending_remaining' filter explicitly excludes uploaded candidates via not_.in_."""
    with patch("app.routers.dashboard.supabase") as mock_sb:
        mock_docs = MagicMock(data=[{"candidate_id": 99001}])
        mock_auds = MagicMock(data=[])
        mock_cand_check = MagicMock(data=[{"candidate_id": 99001, "state_name": "TAMIL NADU"}])

        pending_cand = {**TN_CANDIDATE, "candidate_id": 99005, "candidate_first_name": "Karthik"}
        mock_pending_res = MagicMock(count=1, data=[pending_cand])

        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                t.select.return_value.in_.return_value.or_.return_value.execute.return_value = mock_cand_check
                t.select.return_value.or_.return_value.not_.in_.return_value.order.return_value.range.return_value.execute.return_value = mock_pending_res
            elif name == "candidate_documents":
                t.select.return_value.neq.return_value.execute.return_value = mock_docs_res
            elif name == "placement_audits":
                t.select.return_value.execute.return_value = mock_auds
            return t

        mock_docs_res = mock_docs
        mock_sb.table.side_effect = table_dispatch

        res = client.get("/dashboard/candidates?filter=pending_remaining")
        assert res.status_code == 200
        data = res.json()

        assert data["filter"] == "pending_remaining"
        assert data["total_count"] == 1
        assert data["candidates"][0]["candidate_id"] == 99005


def test_dashboard_candidates_tampering_blocked(auth_l1_tn):
    """Direct candidate listing tampering with another state returns 403."""
    res = client.get("/dashboard/candidates?filter=total&state=KERALA")
    assert res.status_code == 403


def test_dashboard_candidates_approved_filter(auth_l1_tn):
    """'cpass_approved' filter returns approved candidates and normalizes status."""
    with patch("app.routers.dashboard.supabase") as mock_sb:
        mock_docs = MagicMock(data=[{"candidate_id": 99001}])
        mock_auds = MagicMock(data=[{"candidate_id": 99001, "cpass_status": "L2_APPROVED", "audit_status": "VERIFIED"}])
        mock_cand_check = MagicMock(data=[{"candidate_id": 99001, "state_name": "TAMIL NADU"}])

        appr_cand = {**TN_CANDIDATE, "candidate_id": 99001}
        mock_appr_res = MagicMock(count=1, data=[appr_cand])

        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                t.select.return_value.in_.return_value.or_.return_value.execute.return_value = mock_cand_check
                t.select.return_value.or_.return_value.in_.return_value.order.return_value.range.return_value.execute.return_value = mock_appr_res
            elif name == "candidate_documents":
                t.select.return_value.neq.return_value.execute.return_value = mock_docs
            elif name == "placement_audits":
                t.select.return_value.execute.return_value = mock_auds
            return t

        mock_sb.table.side_effect = table_dispatch

        # Supports filter_type param as used by frontend
        res = client.get("/dashboard/candidates?filter_type=cpass_approved")
        assert res.status_code == 200
        data = res.json()
        assert data["filter"] == "cpass_approved"
        assert data["total_count"] == 1
        assert data["candidates"][0]["cpass_status"] == "APPROVED"
        assert data["candidates"][0]["is_uploaded"] is True


def test_dashboard_candidates_rejected_filter(auth_l1_tn):
    """'cpass_rejected' filter returns rejected candidates."""
    with patch("app.routers.dashboard.supabase") as mock_sb:
        mock_docs = MagicMock(data=[{"candidate_id": 99001}])
        mock_auds = MagicMock(data=[{"candidate_id": 99001, "cpass_status": "REJECTED", "audit_status": "REJECTED"}])
        mock_cand_check = MagicMock(data=[{"candidate_id": 99001, "state_name": "TAMIL NADU"}])

        rej_cand = {**TN_CANDIDATE, "candidate_id": 99001}
        mock_rej_res = MagicMock(count=1, data=[rej_cand])

        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                t.select.return_value.in_.return_value.or_.return_value.execute.return_value = mock_cand_check
                t.select.return_value.or_.return_value.in_.return_value.order.return_value.range.return_value.execute.return_value = mock_rej_res
            elif name == "candidate_documents":
                t.select.return_value.neq.return_value.execute.return_value = mock_docs
            elif name == "placement_audits":
                t.select.return_value.execute.return_value = mock_auds
            return t

        mock_sb.table.side_effect = table_dispatch

        res = client.get("/dashboard/candidates?filter=cpass_rejected")
        assert res.status_code == 200
        data = res.json()
        assert data["filter"] == "cpass_rejected"
        assert data["total_count"] == 1
        assert data["candidates"][0]["cpass_status"] == "REJECTED"


def test_dashboard_candidates_uploaded_filter(auth_l1_tn):
    """'cpass_uploaded' filter returns all candidates with documents/audits in coordinator's state."""
    with patch("app.routers.dashboard.supabase") as mock_sb:
        mock_docs = MagicMock(data=[{"candidate_id": 99001}])
        mock_auds = MagicMock(data=[])
        mock_cand_check = MagicMock(data=[{"candidate_id": 99001, "state_name": "TAMIL NADU"}])

        upl_cand = {**TN_CANDIDATE, "candidate_id": 99001}
        mock_upl_res = MagicMock(count=1, data=[upl_cand])

        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                t.select.return_value.in_.return_value.or_.return_value.execute.return_value = mock_cand_check
                t.select.return_value.or_.return_value.in_.return_value.order.return_value.range.return_value.execute.return_value = mock_upl_res
            elif name == "candidate_documents":
                t.select.return_value.neq.return_value.execute.return_value = mock_docs
            elif name == "placement_audits":
                t.select.return_value.execute.return_value = mock_auds
            return t

        mock_sb.table.side_effect = table_dispatch

        res = client.get("/dashboard/candidates?filter_type=cpass_uploaded")
        assert res.status_code == 200
        data = res.json()
        assert data["filter"] == "cpass_uploaded"
        assert data["total_count"] == 1
        assert data["candidates"][0]["is_uploaded"] is True


def test_dashboard_candidates_search_and_pagination(auth_l1_tn):
    """Search and pagination parameters are properly processed within the filter."""
    with patch("app.routers.dashboard.supabase") as mock_sb:
        mock_rows = [TN_CANDIDATE]
        mock_q_res = MagicMock(count=45, data=mock_rows)

        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                t.select.return_value.or_.return_value.or_.return_value.order.return_value.range.return_value.execute.return_value = mock_q_res
            elif name == "candidate_documents":
                t.select.return_value.neq.return_value.execute.return_value = MagicMock(data=[])
            elif name == "placement_audits":
                t.select.return_value.execute.return_value = MagicMock(data=[])
            return t

        mock_sb.table.side_effect = table_dispatch

        res = client.get("/dashboard/candidates?filter=total&page=2&page_size=20&search=Ramesh")
        assert res.status_code == 200
        data = res.json()
        assert data["page"] == 2
        assert data["page_size"] == 20
        assert data["total_count"] == 45
        assert data["total_pages"] == 3


def test_dashboard_candidates_invalid_filter_returns_400(auth_l1_tn):
    """Invalid filter category returns 400 with a descriptive error."""
    res = client.get("/dashboard/candidates?filter=unknown_filter")
    assert res.status_code == 400
    assert "Invalid filter" in res.json()["detail"]


def test_dashboard_status_variants_recognition(auth_l1_tn):
    """Verify all recognized approved variants (VERIFIED, APPROVED, L2_APPROVED, CPASS_APPROVED)
    and rejected variants (REJECTED, L2_REJECTED, CPASS_REJECTED).
    """
    with patch("app.routers.dashboard.supabase") as mock_sb:
        mock_total_res = MagicMock(count=10)
        # 4 approved candidates with different status variants
        # 3 rejected candidates with different status variants
        aud_records = [
            {"candidate_id": 99011, "cpass_status": "VERIFIED", "audit_status": "SUBMITTED"},
            {"candidate_id": 99012, "cpass_status": "APPROVED", "audit_status": "SUBMITTED"},
            {"candidate_id": 99013, "cpass_status": "L2_APPROVED", "audit_status": "APPROVED"},
            {"candidate_id": 99014, "cpass_status": "CPASS_APPROVED", "audit_status": "SUBMITTED"},
            {"candidate_id": 99015, "cpass_status": "REJECTED", "audit_status": "REJECTED"},
            {"candidate_id": 99016, "cpass_status": "L2_REJECTED", "audit_status": "REJECTED"},
            {"candidate_id": 99017, "cpass_status": "CPASS_REJECTED", "audit_status": "SUBMITTED"},
            {"candidate_id": 99018, "cpass_status": "PENDING", "audit_status": "DRAFT"},
        ]
        all_cids = [a["candidate_id"] for a in aud_records]
        mock_docs = MagicMock(data=[{"candidate_id": cid} for cid in all_cids])
        mock_auds = MagicMock(data=aud_records)
        mock_cand_check = MagicMock(data=[
            {"candidate_id": cid, "state_name": "TAMIL NADU", "tc_state_name": "TAMIL NADU"}
            for cid in all_cids
        ])

        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                t.select.return_value.or_.return_value.limit.return_value.execute.return_value = mock_total_res
                t.select.return_value.in_.return_value.or_.return_value.execute.return_value = mock_cand_check
            elif name == "candidate_documents":
                t.select.return_value.neq.return_value.execute.return_value = mock_docs
            elif name == "placement_audits":
                t.select.return_value.execute.return_value = mock_auds
            return t

        mock_sb.table.side_effect = table_dispatch

        res = client.get("/dashboard/summary")
        assert res.status_code == 200
        data = res.json()
        assert data["cpass_approved"] == 4
        assert data["cpass_rejected"] == 3
        assert data["cpass_uploaded"] == 8
        assert data["pending_remaining"] == 2  # Total 10 - Uploaded 8 = 2


def test_dashboard_uploaded_candidate_deduplication(auth_l1_tn):
    """Candidates appearing in multiple documents and an audit record are deduplicated to 1."""
    with patch("app.routers.dashboard.supabase") as mock_sb:
        mock_total_res = MagicMock(count=5)
        # Candidate 99001 appears 4 times in documents and once in placement_audits
        mock_docs = MagicMock(data=[
            {"candidate_id": 99001},
            {"candidate_id": 99001},
            {"candidate_id": 99001},
            {"candidate_id": 99001},
            {"candidate_id": 99002},
        ])
        mock_auds = MagicMock(data=[
            {"candidate_id": 99001, "cpass_status": "PENDING", "audit_status": "DRAFT"},
            {"candidate_id": 99002, "cpass_status": "PENDING", "audit_status": "DRAFT"},
        ])
        mock_cand_check = MagicMock(data=[
            {"candidate_id": 99001, "state_name": "TAMIL NADU", "tc_state_name": "TAMIL NADU"},
            {"candidate_id": 99002, "state_name": "TAMIL NADU", "tc_state_name": "TAMIL NADU"},
        ])

        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                t.select.return_value.or_.return_value.limit.return_value.execute.return_value = mock_total_res
                t.select.return_value.in_.return_value.or_.return_value.execute.return_value = mock_cand_check
            elif name == "candidate_documents":
                t.select.return_value.neq.return_value.execute.return_value = mock_docs
            elif name == "placement_audits":
                t.select.return_value.execute.return_value = mock_auds
            return t

        mock_sb.table.side_effect = table_dispatch

        res = client.get("/dashboard/summary")
        assert res.status_code == 200
        data = res.json()
        assert data["cpass_uploaded"] == 2
        assert data["pending_remaining"] == 3  # 5 - 2 = 3


def test_dashboard_empty_approved_and_rejected_short_circuit(auth_l1_tn):
    """When a state has 0 approved or 0 rejected candidates (like Andhra Pradesh),
    the endpoint immediately short-circuits returning an empty list with total_count=0.
    """
    with patch("app.routers.dashboard.supabase") as mock_sb:
        # 6 uploaded candidates, but none approved or rejected
        cids = [1076609, 1076615, 1076617, 1076623, 1076642, 2766629]
        mock_docs = MagicMock(data=[{"candidate_id": c} for c in cids[:5]])
        mock_auds = MagicMock(data=[
            {"candidate_id": c, "cpass_status": "PENDING", "audit_status": "SUBMITTED"}
            for c in [1076609, 1076617, 1076623, 1076642, 2766629]
        ])
        mock_cand_check = MagicMock(data=[
            {"candidate_id": c, "state_name": "TAMIL NADU", "tc_state_name": "TAMIL NADU"}
            for c in cids
        ])

        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                t.select.return_value.in_.return_value.or_.return_value.execute.return_value = mock_cand_check
            elif name == "candidate_documents":
                t.select.return_value.neq.return_value.execute.return_value = mock_docs
            elif name == "placement_audits":
                t.select.return_value.execute.return_value = mock_auds
            return t

        mock_sb.table.side_effect = table_dispatch

        res_appr = client.get("/dashboard/candidates?filter=cpass_approved")
        assert res_appr.status_code == 200
        data_appr = res_appr.json()
        assert data_appr["total_count"] == 0
        assert data_appr["candidates"] == []

        res_rej = client.get("/dashboard/candidates?filter=cpass_rejected")
        assert res_rej.status_code == 200
        data_rej = res_rej.json()
        assert data_rej["total_count"] == 0
        assert data_rej["candidates"] == []


# -----------------------------------------------------------------------------
# 3. PaySlip Availability Tests ("Browse" vs "Not Available")
# -----------------------------------------------------------------------------

def test_set_payslip_not_available_persists_in_audit(auth_l1_tn):
    """Coordinator can mark payslip as Not Available, persisting 'No' in document_audit."""
    with patch("app.routers.dashboard.supabase") as mock_sb:
        captured_payloads = []

        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[TN_CANDIDATE]
                )
            elif name == "candidate_documents":
                # No conflicting uploaded file
                t.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.neq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[]
                )
            elif name == "placement_audits":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[]
                )
                def insert_capture(payload):
                    captured_payloads.append(payload)
                    m = MagicMock()
                    m.execute.return_value = MagicMock(data=[{"id": "new-audit-id", **payload}])
                    return m
                t.insert.side_effect = insert_capture
            return t

        mock_sb.table.side_effect = table_dispatch

        res = client.post("/dashboard/candidates/99001/payslip-availability", json={
            "slot_key": "salary_slip_1",
            "available": "No",
            "month": 1,
            "year": 2026,
            "remarks": "Employer does not issue slips",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["available"] == "No"
        assert len(captured_payloads) == 1
        saved_audit = captured_payloads[0]
        # Availability is 'No'
        assert saved_audit["document_audit"]["salary_slip_1"]["available"] == "No"
        # Candidate is NOT marked verified or approved
        assert saved_audit["cpass_status"] == "PENDING"


def test_payslip_not_available_rejects_conflicting_active_document(auth_l1_tn):
    """Coordinator cannot mark Not Available if an active verified payslip file is already uploaded."""
    with patch("app.routers.dashboard.supabase") as mock_sb:
        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[TN_CANDIDATE]
                )
            elif name == "candidate_documents":
                # Conflicting file exists
                t.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.neq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[{"id": "doc-ps1", "file_name": "jan_payslip.pdf"}]
                )
            return t

        mock_sb.table.side_effect = table_dispatch

        res = client.post("/dashboard/candidates/99001/payslip-availability", json={
            "slot_key": "salary_slip_1",
            "available": "No",
            "month": 1,
            "year": 2026,
        })
        assert res.status_code == 400
        assert "conflicting document state" in res.json()["detail"].lower()


def test_payslip_availability_cross_state_tampering_blocked(auth_l1_tn):
    """Coordinator cannot update payslip availability for a candidate in another state."""
    with patch("app.routers.dashboard.supabase") as mock_sb:
        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                # Returns Kerala candidate
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[KL_CANDIDATE]
                )
            return t

        mock_sb.table.side_effect = table_dispatch

        res = client.post("/dashboard/candidates/99002/payslip-availability", json={
            "slot_key": "salary_slip_1",
            "available": "No",
            "month": 1,
            "year": 2026,
        })
        assert res.status_code == 403


def test_payslip_availability_with_month_number_only(auth_l1_tn):
    """Payload providing only month_number (without slot_key) succeeds and maps to salary_slip_{month_number}."""
    with patch("app.routers.dashboard.supabase") as mock_sb:
        captured_payloads = []

        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[TN_CANDIDATE]
                )
            elif name == "candidate_documents":
                t.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.neq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[]
                )
            elif name == "placement_audits":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[]
                )
                def insert_capture(payload):
                    captured_payloads.append(payload)
                    m = MagicMock()
                    m.execute.return_value = MagicMock(data=[{"id": "new-audit-id", **payload}])
                    return m
                t.insert.side_effect = insert_capture
            return t

        mock_sb.table.side_effect = table_dispatch

        res = client.post("/dashboard/candidates/99001/payslip-availability", json={
            "month_number": 2,
            "available": "No",
            "month": 2,
            "year": 2026,
        })
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["slot_key"] == "salary_slip_2"
        assert data["available"] == "No"
        assert len(captured_payloads) == 1
        assert "salary_slip_2" in captured_payloads[0]["document_audit"]
        assert captured_payloads[0]["document_audit"]["salary_slip_2"]["available"] == "No"


def test_payslip_availability_reset_to_pending(auth_l1_tn):
    """Coordinator can reset a payslip slot back to Pending ('Change to Upload')."""
    with patch("app.routers.dashboard.supabase") as mock_sb:
        captured_updates = []

        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[TN_CANDIDATE]
                )
            elif name == "candidate_documents":
                t.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.neq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[]
                )
            elif name == "placement_audits":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[{
                        "id": "audit-123",
                        "candidate_id": 99001,
                        "document_audit": {
                            "salary_slip_1": {"available": "No", "compliance": "Non-Compliant"}
                        },
                        "cpass_status": "PENDING",
                    }]
                )
                def update_capture(payload):
                    captured_updates.append(payload)
                    m = MagicMock()
                    m.eq.return_value.execute.return_value = MagicMock(data=[{"id": "audit-123", **payload}])
                    return m
                t.update.side_effect = update_capture
            return t

        mock_sb.table.side_effect = table_dispatch

        res = client.post("/dashboard/candidates/99001/payslip-availability", json={
            "slot_key": "salary_slip_1",
            "month_number": 1,
            "available": "Pending",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["available"] == "Pending"
        assert len(captured_updates) == 1
        assert captured_updates[0]["document_audit"]["salary_slip_1"]["available"] == "Pending"


def test_payslip_availability_missing_slot_identifier_returns_400(auth_l1_tn):
    """Request with neither slot_key nor month_number returns 400 with a descriptive error."""
    with patch("app.routers.dashboard.supabase") as mock_sb:
        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[TN_CANDIDATE]
                )
            return t

        mock_sb.table.side_effect = table_dispatch

        res = client.post("/dashboard/candidates/99001/payslip-availability", json={
            "available": "No",
        })
        assert res.status_code == 400
        assert "Either slot_key or month_number must be provided" in res.json()["detail"]


def test_payslip_availability_invalid_status_returns_400(auth_l1_tn):
    """Request with invalid available status returns 400."""
    with patch("app.routers.dashboard.supabase") as mock_sb:
        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[TN_CANDIDATE]
                )
            return t

        mock_sb.table.side_effect = table_dispatch

        res = client.post("/dashboard/candidates/99001/payslip-availability", json={
            "slot_key": "salary_slip_1",
            "available": "InvalidStatus",
        })
        assert res.status_code == 400
        assert "Availability must be 'Yes', 'No', or 'Pending'" in res.json()["detail"]
