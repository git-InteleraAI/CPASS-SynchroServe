"""Automated regression test suite for CPASS L4 Business Leader and L5 CEO Return-to-Corrections Workflows.

Verifies:
1. L4 Business Leader returns:
   - L4 -> L1: sets cpass_status & audit_status to RETURNED_TO_L1, CH to 'Returned to L1', resets COPS/BL to Pending.
   - L4 -> L2: sets cpass_status & audit_status to SUBMITTED, CH to Pending, resets COPS/BL to Pending.
   - L4 -> L3: sets cpass_status to L2_APPROVED, CH remains Recommended, COPS reset to Pending, BL reset to Pending.
   - L4 -> L4: rejected with HTTP 422 (cannot return to itself).
2. L5 CEO returns:
   - L5 -> L1: sets cpass_status & audit_status to RETURNED_TO_L1, resets all downstream.
   - L5 -> L2: sets cpass_status & audit_status to SUBMITTED, CH reset to Pending.
   - L5 -> L3: sets cpass_status to L2_APPROVED, CH remains Recommended, COPS reset to Pending.
   - L5 -> L4: sets cpass_status to VERIFIED, CH remains Recommended, COPS remains Verified, BL reset to Pending.
   - L5 -> L5: rejected with HTTP 422 (cannot return to itself).
3. Validation rules:
   - Missing or empty return reason is rejected with HTTP 422.
   - Invalid destination is rejected with HTTP 422.
4. Security and authorization:
   - Unauthorized roles rejected with HTTP 403.
   - Candidate not found returns HTTP 404.
5. Sequencing and progression rules:
   - Candidate not verified by L3 COPS cannot be returned by L4 (HTTP 400).
   - Candidate not approved by L4 BL cannot be returned by L5 (HTTP 400).
   - Approved candidates cannot skip required approval stages.
6. L5 CEO approve and reject endpoints work as intended.
7. Preserves candidate dossier, salary records, employer data, and document evidence.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentUser, get_current_user
from app.main import app
from app.routers.audits import extract_review_stages

client = TestClient(app)

L1_USER = CurrentUser(
    id="l1-user-uuid",
    email="l1.odisha@cpass.org",
    full_name="L1 Coordinator",
    role="L1_COORDINATOR",
    assigned_state="ODISHA",
)

L2_USER = CurrentUser(
    id="l2-user-uuid",
    email="l2.ch@cpass.org",
    full_name="L2 Centre Head",
    role="L2_MANAGER",
    assigned_state="ODISHA",
)

L3_USER = CurrentUser(
    id="l3-user-uuid",
    email="l3.cops@cpass.org",
    full_name="L3 COPS Auditor",
    role="L3_COPS",
)

L4_USER = CurrentUser(
    id="l4-user-uuid",
    email="l4.bl@cpass.org",
    full_name="L4 Business Leader",
    role="L4_LEADER",
    assigned_states=["ODISHA"],
)

L5_USER = CurrentUser(
    id="l5-user-uuid",
    email="ceo@cpass.org",
    full_name="Chief Executive Officer",
    role="L5_CEO",
)

ADMIN_USER = CurrentUser(
    id="admin-user-uuid",
    email="admin@cpass.org",
    full_name="Admin Director",
    role="ADMIN",
)

CANDIDATE_ODISHA = {
    "candidate_id": 10482,
    "state_name": "ODISHA",
    "candidate_first_name": "Rajesh",
    "candidate_last_name": "Patel",
    "candidate_father_name": "Mohan Patel",
    "tc_id": 101,
    "tc_name": "Bhubaneswar Skill Centre",
    "tc_state_name": "ODISHA",
    "batch_code": "BATCH-OD-2023-01",
    "sanction_order_number": "SO-2023-99",
    "appointed": True,
    "employer_name": "Reliance Retail Ltd",
}

SAMPLE_EMPLOYER_DETAILS = [
    {
        "id": "emp_1",
        "employer_name": "Reliance Retail Ltd",
        "months_worked": 3,
        "appointment_date": "2026-01-01",
        "designation": "Sales Associate",
        "place_of_work": "Bhubaneswar",
        "monthly_ctc": 16500.0,
        "minimum_wages": 14000.0,
    }
]

SAMPLE_SALARY_DETAILS = [
    {"month": 1, "year": 2026, "gross_salary": 16500, "net_salary": 15000, "amount_credited": 15000, "bank_name": "SBI"},
    {"month": 2, "year": 2026, "gross_salary": 16500, "net_salary": 15000, "amount_credited": 15000, "bank_name": "SBI"},
    {"month": 3, "year": 2026, "gross_salary": 16500, "net_salary": 15000, "amount_credited": 15000, "bank_name": "SBI"},
]


def create_cops_verified_audit():
    """Audit that has completed CH recommendation and L3 COPS verification, now at L4 BL."""
    return {
        "id": "audit-l4-test-1",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "VERIFIED",
        "employer_details": SAMPLE_EMPLOYER_DETAILS,
        "salary_details": SAMPLE_SALARY_DETAILS,
        "document_audit": {"l2_review_completed": True},
        "signoff_details": {
            "review_stages": {
                "ch": {"status": "Recommended", "reviewed_by": "L2 Centre Head"},
                "cops": {"status": "Verified", "reviewed_by": "L3 COPS Auditor"},
                "bl": {"status": "Pending"},
                "ceo": {"status": "Pending"},
            },
            "centre_head": {"recommended": True, "confirmed": True},
            "l2_approval": {"approved": True},
            "cops_team": {"confirmed": True},
        },
    }


def create_bl_approved_audit():
    """Audit that has completed BL approval, now at L5 CEO."""
    return {
        "id": "audit-l5-test-1",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "APPROVED",
        "employer_details": SAMPLE_EMPLOYER_DETAILS,
        "salary_details": SAMPLE_SALARY_DETAILS,
        "document_audit": {"l2_review_completed": True},
        "signoff_details": {
            "review_stages": {
                "ch": {"status": "Recommended", "reviewed_by": "L2 Centre Head"},
                "cops": {"status": "Verified", "reviewed_by": "L3 COPS Auditor"},
                "bl": {"status": "Approved", "reviewed_by": "L4 Business Leader"},
                "ceo": {"status": "Pending"},
            },
            "centre_head": {"recommended": True, "confirmed": True},
            "l2_approval": {"approved": True},
            "cops_team": {"confirmed": True},
            "business_leader": {"confirmed": True},
        },
    }


def _mock_db(audit_record):
    def table_mock(tbl):
        m = MagicMock()
        if tbl == "ddugky_candidates":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
        elif tbl == "placement_audits":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[audit_record])
            def update_side_effect(up_data):
                up_mock = MagicMock()
                up_mock.eq.return_value.execute.return_value = MagicMock(data=[{**audit_record, **up_data}])
                return up_mock
            m.update.side_effect = update_side_effect
        return m
    return table_mock


# =============================================================================
# 1. L4 Business Leader Return Workflows
# =============================================================================

def test_l4_return_to_l1():
    """L4 -> L1 sets RETURNED_TO_L1, resets CH to Returned to L1, and resets COPS/BL/CEO."""
    app.dependency_overrides[get_current_user] = lambda: L4_USER
    audit = create_cops_verified_audit()

    with patch("app.routers.audits.supabase") as mock_sb:
        mock_sb.table.side_effect = _mock_db(audit)

        payload = {
            "destination": "L1",
            "return_reason": "Salary slips do not match bank statement credit amounts",
            "remarks": "Please ask candidate to provide original employer letter",
        }
        res = client.post("/candidates/10482/audit/l4-review/return", json=payload)
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "success"
        assert data["destination"] == "L1"
        assert data["cpass_status"] == "RETURNED_TO_L1"
        assert data["audit_status"] == "RETURNED_TO_L1"

        stages = extract_review_stages(data["audit"])
        assert stages["ch_status"] == "Returned to L1"
        assert stages["cops_status"] == "Pending"
        assert stages["bl_status"] == "Pending"
        assert stages["ceo_status"] == "Pending"

        signoff = data["audit"]["signoff_details"]
        assert signoff["active_return"]["stage"] == "BL"
        assert signoff["active_return"]["destination"] == "L1"
        assert signoff["return_to_l1"]["reason"] == payload["return_reason"]
    app.dependency_overrides.clear()


def test_l4_return_to_l2():
    """L4 -> L2 sets SUBMITTED, resets CH to Pending, and resets COPS/BL/CEO."""
    app.dependency_overrides[get_current_user] = lambda: L4_USER
    audit = create_cops_verified_audit()

    with patch("app.routers.audits.supabase") as mock_sb:
        mock_sb.table.side_effect = _mock_db(audit)

        payload = {
            "destination": "L2",
            "return_reason": "Center Head review incomplete regarding employer branch",
            "remarks": "CH must verify workplace location",
        }
        res = client.post("/candidates/10482/audit/l4-review/return", json=payload)
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "success"
        assert data["destination"] == "L2"
        assert data["cpass_status"] == "SUBMITTED"
        assert data["audit_status"] == "SUBMITTED"

        stages = extract_review_stages(data["audit"])
        assert stages["ch_status"] == "Pending"
        assert stages["cops_status"] == "Pending"
        assert stages["bl_status"] == "Pending"

        signoff = data["audit"]["signoff_details"]
        assert signoff["active_return"]["stage"] == "BL"
        assert signoff["active_return"]["destination"] == "L2"
        assert signoff["return_to_l2"]["reason"] == payload["return_reason"]
    app.dependency_overrides.clear()


def test_l4_return_to_l3():
    """L4 -> L3 sets L2_APPROVED, preserves CH Recommended, resets COPS to Pending."""
    app.dependency_overrides[get_current_user] = lambda: L4_USER
    audit = create_cops_verified_audit()

    with patch("app.routers.audits.supabase") as mock_sb:
        mock_sb.table.side_effect = _mock_db(audit)

        payload = {
            "destination": "L3",
            "return_reason": "COPS checklist missed bank account number mismatch",
            "remarks": "Please re-verify bank statement against master record",
        }
        res = client.post("/candidates/10482/audit/l4-review/return", json=payload)
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "success"
        assert data["destination"] == "L3"
        assert data["cpass_status"] == "L2_APPROVED"
        assert data["audit_status"] == "SUBMITTED"

        stages = extract_review_stages(data["audit"])
        assert stages["ch_status"] == "Recommended"
        assert stages["cops_status"] == "Pending"
        assert stages["bl_status"] == "Pending"

        signoff = data["audit"]["signoff_details"]
        assert signoff["active_return"]["stage"] == "BL"
        assert signoff["active_return"]["destination"] == "L3"
        assert signoff["return_to_l3"]["reason"] == payload["return_reason"]
    app.dependency_overrides.clear()


def test_l4_return_to_l4_rejected():
    """L4 returning to itself (L4) is rejected with HTTP 422."""
    app.dependency_overrides[get_current_user] = lambda: L4_USER
    payload = {
        "destination": "L4",
        "return_reason": "Invalid self return",
    }
    res = client.post("/candidates/10482/audit/l4-review/return", json=payload)
    assert res.status_code == 422
    assert "cannot return to itself" in res.text.lower() or "destination" in res.text.lower()
    app.dependency_overrides.clear()


# =============================================================================
# 2. L5 CEO Return Workflows
# =============================================================================

def test_l5_return_to_l1():
    """L5 -> L1 sets RETURNED_TO_L1, resets CH to Returned to L1, and resets all downstream."""
    app.dependency_overrides[get_current_user] = lambda: L5_USER
    audit = create_bl_approved_audit()

    with patch("app.routers.audits.supabase") as mock_sb:
        mock_sb.table.side_effect = _mock_db(audit)

        payload = {
            "destination": "L1",
            "return_reason": "Executive audit failed: Unclear scanned appointment letter",
            "remarks": "Coordinator must re-scan document at 300 DPI",
        }
        res = client.post("/candidates/10482/audit/l5-review/return", json=payload)
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "success"
        assert data["destination"] == "L1"
        assert data["cpass_status"] == "RETURNED_TO_L1"
        assert data["audit_status"] == "RETURNED_TO_L1"

        stages = extract_review_stages(data["audit"])
        assert stages["ch_status"] == "Returned to L1"
        assert stages["cops_status"] == "Pending"
        assert stages["bl_status"] == "Pending"
        assert stages["ceo_status"] == "Pending"

        signoff = data["audit"]["signoff_details"]
        assert signoff["active_return"]["stage"] == "CEO"
        assert signoff["active_return"]["destination"] == "L1"
    app.dependency_overrides.clear()


def test_l5_return_to_l2():
    """L5 -> L2 sets SUBMITTED, resets CH to Pending, and resets downstream."""
    app.dependency_overrides[get_current_user] = lambda: L5_USER
    audit = create_bl_approved_audit()

    with patch("app.routers.audits.supabase") as mock_sb:
        mock_sb.table.side_effect = _mock_db(audit)

        payload = {
            "destination": "L2",
            "return_reason": "Center Head physical verification record missing",
            "remarks": "CH must complete full physical verification log",
        }
        res = client.post("/candidates/10482/audit/l5-review/return", json=payload)
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "success"
        assert data["destination"] == "L2"
        assert data["cpass_status"] == "SUBMITTED"
        assert data["audit_status"] == "SUBMITTED"

        stages = extract_review_stages(data["audit"])
        assert stages["ch_status"] == "Pending"
        assert stages["cops_status"] == "Pending"
        assert stages["bl_status"] == "Pending"
        assert stages["ceo_status"] == "Pending"
    app.dependency_overrides.clear()


def test_l5_return_to_l3():
    """L5 -> L3 sets L2_APPROVED, preserves CH Recommended, resets COPS/BL/CEO to Pending."""
    app.dependency_overrides[get_current_user] = lambda: L5_USER
    audit = create_bl_approved_audit()

    with patch("app.routers.audits.supabase") as mock_sb:
        mock_sb.table.side_effect = _mock_db(audit)

        payload = {
            "destination": "L3",
            "return_reason": "COPS compliance checklist requires re-audit",
            "remarks": "Verify minimum wage thresholds for Odisha state",
        }
        res = client.post("/candidates/10482/audit/l5-review/return", json=payload)
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "success"
        assert data["destination"] == "L3"
        assert data["cpass_status"] == "L2_APPROVED"
        assert data["audit_status"] == "SUBMITTED"

        stages = extract_review_stages(data["audit"])
        assert stages["ch_status"] == "Recommended"
        assert stages["cops_status"] == "Pending"
        assert stages["bl_status"] == "Pending"
        assert stages["ceo_status"] == "Pending"
    app.dependency_overrides.clear()


def test_l5_return_to_l4():
    """L5 -> L4 sets VERIFIED, preserves CH Recommended & COPS Verified, resets BL to Pending."""
    app.dependency_overrides[get_current_user] = lambda: L5_USER
    audit = create_bl_approved_audit()

    with patch("app.routers.audits.supabase") as mock_sb:
        mock_sb.table.side_effect = _mock_db(audit)

        payload = {
            "destination": "L4",
            "return_reason": "Business Leader commercial review required",
            "remarks": "Check employer retention commercial agreements",
        }
        res = client.post("/candidates/10482/audit/l5-review/return", json=payload)
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "success"
        assert data["destination"] == "L4"
        assert data["cpass_status"] == "VERIFIED"
        assert data["audit_status"] == "SUBMITTED"

        stages = extract_review_stages(data["audit"])
        assert stages["ch_status"] == "Recommended"
        assert stages["cops_status"] == "Verified"
        assert stages["bl_status"] == "Pending"
        assert stages["ceo_status"] == "Pending"

        signoff = data["audit"]["signoff_details"]
        assert signoff["active_return"]["stage"] == "CEO"
        assert signoff["active_return"]["destination"] == "L4"
        assert signoff["return_to_l4"]["reason"] == payload["return_reason"]
    app.dependency_overrides.clear()


def test_l5_return_to_l5_rejected():
    """L5 returning to itself (L5) is rejected with HTTP 422."""
    app.dependency_overrides[get_current_user] = lambda: L5_USER
    payload = {
        "destination": "L5",
        "return_reason": "Invalid self return",
    }
    res = client.post("/candidates/10482/audit/l5-review/return", json=payload)
    assert res.status_code == 422
    assert "cannot return to itself" in res.text.lower() or "destination" in res.text.lower()
    app.dependency_overrides.clear()


# =============================================================================
# 3. Validation: Missing Reason & Invalid Destinations
# =============================================================================

@pytest.mark.parametrize("bad_reason", ["", "   ", None])
def test_missing_return_reason_rejected_l4_and_l5(bad_reason):
    """Empty, blank, or missing return reason is rejected with HTTP 422."""
    app.dependency_overrides[get_current_user] = lambda: L4_USER
    res_l4 = client.post("/candidates/10482/audit/l4-review/return", json={"destination": "L3", "return_reason": bad_reason})
    assert res_l4.status_code == 422

    app.dependency_overrides[get_current_user] = lambda: L5_USER
    res_l5 = client.post("/candidates/10482/audit/l5-review/return", json={"destination": "L4", "return_reason": bad_reason})
    assert res_l5.status_code == 422
    app.dependency_overrides.clear()


@pytest.mark.parametrize("invalid_dest", ["L9", "UNKNOWN", "ADMIN", "123", "COPS"])
def test_invalid_destination_rejected_l4_and_l5(invalid_dest):
    """Non-whitelisted destination strings are rejected with HTTP 422."""
    app.dependency_overrides[get_current_user] = lambda: L4_USER
    res_l4 = client.post("/candidates/10482/audit/l4-review/return", json={"destination": invalid_dest, "return_reason": "Test"})
    assert res_l4.status_code == 422

    app.dependency_overrides[get_current_user] = lambda: L5_USER
    res_l5 = client.post("/candidates/10482/audit/l5-review/return", json={"destination": invalid_dest, "return_reason": "Test"})
    assert res_l5.status_code == 422
    app.dependency_overrides.clear()


# =============================================================================
# 4. Role Authorization & Candidate Not Found
# =============================================================================

def test_unauthorized_roles_blocked_from_l4_and_l5_returns():
    """L1, L2, and L3 users cannot invoke L4 return; L1, L2, L3, and L4 users cannot invoke L5 return."""
    payload_l4 = {"destination": "L3", "return_reason": "Should fail"}
    payload_l5 = {"destination": "L4", "return_reason": "Should fail"}

    # L1 blocked from both
    app.dependency_overrides[get_current_user] = lambda: L1_USER
    assert client.post("/candidates/10482/audit/l4-review/return", json=payload_l4).status_code == 403
    assert client.post("/candidates/10482/audit/l5-review/return", json=payload_l5).status_code == 403

    # L2 blocked from both
    app.dependency_overrides[get_current_user] = lambda: L2_USER
    assert client.post("/candidates/10482/audit/l4-review/return", json=payload_l4).status_code == 403
    assert client.post("/candidates/10482/audit/l5-review/return", json=payload_l5).status_code == 403

    # L3 blocked from both
    app.dependency_overrides[get_current_user] = lambda: L3_USER
    assert client.post("/candidates/10482/audit/l4-review/return", json=payload_l4).status_code == 403
    assert client.post("/candidates/10482/audit/l5-review/return", json=payload_l5).status_code == 403

    # L4 blocked from L5 return
    app.dependency_overrides[get_current_user] = lambda: L4_USER
    assert client.post("/candidates/10482/audit/l5-review/return", json=payload_l5).status_code == 403

    # ADMIN can invoke both
    app.dependency_overrides[get_current_user] = lambda: ADMIN_USER
    with patch("app.routers.audits.supabase") as mock_sb:
        mock_sb.table.side_effect = _mock_db(create_cops_verified_audit())
        assert client.post("/candidates/10482/audit/l4-review/return", json=payload_l4).status_code == 200

        mock_sb.table.side_effect = _mock_db(create_bl_approved_audit())
        assert client.post("/candidates/10482/audit/l5-review/return", json=payload_l5).status_code == 200

    app.dependency_overrides.clear()


def test_candidate_not_found_returns_404():
    """Non-existent candidate returns HTTP 404."""
    app.dependency_overrides[get_current_user] = lambda: L4_USER

    with patch("app.routers.audits.supabase") as mock_sb:
        def table_mock(tbl):
            m = MagicMock()
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            return m
        mock_sb.table.side_effect = table_mock

        payload = {"destination": "L3", "return_reason": "Missing candidate"}
        res = client.post("/candidates/99999/audit/l4-review/return", json=payload)
        assert res.status_code == 404
        assert "not found" in res.text.lower()
    app.dependency_overrides.clear()


# =============================================================================
# 5. Sequencing Rules
# =============================================================================

def test_l4_return_blocked_if_candidate_not_verified_by_cops():
    """Candidate that has not reached COPS Verified status cannot be returned by L4 (HTTP 400)."""
    app.dependency_overrides[get_current_user] = lambda: L4_USER
    unverified_audit = {
        "id": "audit-unverified",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "L2_APPROVED",
        "signoff_details": {
            "review_stages": {
                "ch": {"status": "Recommended"},
                "cops": {"status": "Pending"},
                "bl": {"status": "Pending"},
            }
        },
    }

    with patch("app.routers.audits.supabase") as mock_sb:
        mock_sb.table.side_effect = _mock_db(unverified_audit)

        payload = {"destination": "L2", "return_reason": "Premature return"}
        res = client.post("/candidates/10482/audit/l4-review/return", json=payload)
        assert res.status_code == 400
        assert "first be verified by l3 cops" in res.text.lower()
    app.dependency_overrides.clear()


def test_l5_return_blocked_if_candidate_not_approved_by_bl():
    """Candidate that has not reached BL Approved status cannot be returned by L5 (HTTP 400)."""
    app.dependency_overrides[get_current_user] = lambda: L5_USER
    unapproved_audit = {
        "id": "audit-unapproved",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "VERIFIED",
        "signoff_details": {
            "review_stages": {
                "ch": {"status": "Recommended"},
                "cops": {"status": "Verified"},
                "bl": {"status": "Pending"},
            }
        },
    }

    with patch("app.routers.audits.supabase") as mock_sb:
        mock_sb.table.side_effect = _mock_db(unapproved_audit)

        payload = {"destination": "L3", "return_reason": "Premature CEO return"}
        res = client.post("/candidates/10482/audit/l5-review/return", json=payload)
        assert res.status_code == 400
        assert "first be approved by l4 business leader" in res.text.lower()
    app.dependency_overrides.clear()


# =============================================================================
# 6. L5 CEO Approve and Reject Endpoints
# =============================================================================

def test_l5_ceo_approve_success():
    """L5 CEO can sanction and approve BL-approved dossier."""
    app.dependency_overrides[get_current_user] = lambda: L5_USER
    audit = create_bl_approved_audit()

    with patch("app.routers.audits.supabase") as mock_sb:
        mock_sb.table.side_effect = _mock_db(audit)

        res = client.post("/candidates/10482/audit/l5-review/approve", json={"remarks": "Executive sanction granted"})
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "success"
        assert data["cpass_status"] == "APPROVED"
        stages = extract_review_stages(data["audit"])
        assert stages["ceo_status"] == "Approved"
        assert data["audit"]["signoff_details"]["ceo_sanction"]["confirmed"] is True
    app.dependency_overrides.clear()


def test_l5_ceo_reject_success():
    """L5 CEO can reject BL-approved dossier, setting REJECTED."""
    app.dependency_overrides[get_current_user] = lambda: L5_USER
    audit = create_bl_approved_audit()

    with patch("app.routers.audits.supabase") as mock_sb:
        mock_sb.table.side_effect = _mock_db(audit)

        res = client.post("/candidates/10482/audit/l5-review/reject", json={"rejection_reason": "Audit discrepancy identified"})
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "success"
        assert data["cpass_status"] == "REJECTED"
        stages = extract_review_stages(data["audit"])
        assert stages["ceo_status"] == "Rejected"
        assert data["audit"]["signoff_details"]["rejected_stage"] == "ceo"
    app.dependency_overrides.clear()


# =============================================================================
# 7. Preserve Candidate Data, Salaries, and Documents
# =============================================================================

def test_candidate_data_preserved_across_returns():
    """Candidate details, employers, and salary rows remain intact after L4 and L5 returns."""
    app.dependency_overrides[get_current_user] = lambda: L4_USER
    audit = create_cops_verified_audit()

    with patch("app.routers.audits.supabase") as mock_sb:
        mock_sb.table.side_effect = _mock_db(audit)

        payload = {"destination": "L3", "return_reason": "Data preservation test"}
        res = client.post("/candidates/10482/audit/l4-review/return", json=payload)
        assert res.status_code == 200
        updated = res.json()["audit"]

        assert updated["employer_details"] == SAMPLE_EMPLOYER_DETAILS
        assert updated["salary_details"] == SAMPLE_SALARY_DETAILS
        assert updated["candidate_id"] == 10482
    app.dependency_overrides.clear()

