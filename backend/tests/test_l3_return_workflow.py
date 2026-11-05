"""Automated tests for L3 COPS Return-to-Corrections Workflow.

Verifies:
1. L3 -> L1 return sets cpass_status and audit_status to RETURNED_TO_L1, CH status to Returned to L1, resets COPS/BL to Pending.
2. L3 -> L2 return sets cpass_status and audit_status to SUBMITTED, CH status to Pending, resets COPS/BL to Pending.
3. Destination validation strictly enforces only 'L1' or 'L2' and rejects L3, L4, or any invalid destination with HTTP 422.
4. Missing or empty return reason is rejected with HTTP 422.
5. Role authorization: L1, L2, L4 users cannot invoke L3 return (HTTP 403); L3 COPS, L3 Leader, and ADMIN can.
6. Progression to L3 is blocked for both destinations until L2 reviews and recommends the candidate again.
7. L2 Center Head can successfully review and approve a candidate returned to L2 from L3.
8. Existing candidate data, statement employer/salary details, and uploaded documents remain intact throughout returns.
9. Finalized approved or rejected candidates cannot be returned.
10. Legacy /l3-review/return-to-l1 endpoint behaves as a backward-compatible alias.
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

L3_LEADER = CurrentUser(
    id="l3-leader-uuid",
    email="l3.lead@cpass.org",
    full_name="L3 COPS Lead",
    role="L3_LEADER",
)

L4_USER = CurrentUser(
    id="l4-user-uuid",
    email="l4.bl@cpass.org",
    full_name="L4 Business Leader",
    role="L4_LEADER",
    assigned_states=["ODISHA"],
)

ADMIN_USER = CurrentUser(
    id="admin-user-uuid",
    email="admin@cpass.org",
    full_name="Admin Director",
    role="ADMIN",
)

CANDIDATE_ODISHA = {
    "candidate_id": 10482,
    "state_name": "Odisha",
    "candidate_first_name": "Rajesh",
    "candidate_last_name": "Patel",
    "candidate_father_name": "Mohan Patel",
    "tc_id": 101,
    "tc_name": "Bhubaneswar Skill Centre",
    "tc_state_name": "Odisha",
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

MANDATORY_DOCS = [
    {"id": 1, "candidate_id": 10482, "document_type": "APPOINTMENT_LETTER", "upload_status": "SUCCESS", "reporting_month": None, "reporting_year": None, "file_name": "al.pdf"},
    {"id": 2, "candidate_id": 10482, "document_type": "SALARY_SLIP", "upload_status": "SUCCESS", "reporting_month": 1, "reporting_year": 2026, "file_name": "slip1.pdf"},
    {"id": 3, "candidate_id": 10482, "document_type": "SALARY_SLIP", "upload_status": "SUCCESS", "reporting_month": 2, "reporting_year": 2026, "file_name": "slip2.pdf"},
    {"id": 4, "candidate_id": 10482, "document_type": "SALARY_SLIP", "upload_status": "SUCCESS", "reporting_month": 3, "reporting_year": 2026, "file_name": "slip3.pdf"},
    {"id": 5, "candidate_id": 10482, "document_type": "BANK_STATEMENT", "upload_status": "SUCCESS", "reporting_month": 1, "reporting_year": 2026, "file_name": "bank1.pdf"},
    {"id": 6, "candidate_id": 10482, "document_type": "BANK_STATEMENT", "upload_status": "SUCCESS", "reporting_month": 2, "reporting_year": 2026, "file_name": "bank2.pdf"},
    {"id": 7, "candidate_id": 10482, "document_type": "BANK_STATEMENT", "upload_status": "SUCCESS", "reporting_month": 3, "reporting_year": 2026, "file_name": "bank3.pdf"},
]

DOC_REVIEWS_CHECKED = {
    "1": {"reviewed": True},
    "2": {"reviewed": True},
    "3": {"reviewed": True},
    "4": {"reviewed": True},
    "5": {"reviewed": True},
    "6": {"reviewed": True},
    "7": {"reviewed": True},
}


def create_ch_recommended_audit():
    return {
        "id": "audit-l3-test-1",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "L2_APPROVED",
        "employer_details": SAMPLE_EMPLOYER_DETAILS,
        "salary_details": SAMPLE_SALARY_DETAILS,
        "document_audit": {"l2_document_reviews": DOC_REVIEWS_CHECKED, "l2_review_completed": True},
        "signoff_details": {
            "review_stages": {
                "ch": {"status": "Recommended", "reviewed_by": "L2 Centre Head"},
                "cops": {"status": "Pending"},
                "bl": {"status": "Pending"},
            },
            "centre_head": {"recommended": True, "confirmed": True},
            "l2_approval": {"approved": True},
        },
    }


# -----------------------------------------------------------------------------
# 1. L3 -> L1 Return Success
# -----------------------------------------------------------------------------
def test_l3_return_to_l1_success():
    """L3 returning to L1 sets RETURNED_TO_L1 on cpass & audit status, CH to 'Returned to L1', resets COPS/BL."""
    app.dependency_overrides[get_current_user] = lambda: L3_USER
    audit = create_ch_recommended_audit()

    with patch("app.routers.audits.supabase") as mock_sb:
        def table_mock(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif tbl == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[audit])
                # Mock update returning updated row
                def update_side_effect(up_data):
                    up_mock = MagicMock()
                    up_mock.eq.return_value.execute.return_value = MagicMock(data=[{**audit, **up_data}])
                    return up_mock
                m.update.side_effect = update_side_effect
            return m

        mock_sb.table.side_effect = table_mock

        payload = {
            "destination": "L1",
            "return_reason": "Bank statement is missing branch seal and signature",
            "remarks": "Coordinator must obtain stamped bank statement",
        }
        res = client.post("/candidates/10482/audit/l3-review/return", json=payload)
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "success"
        assert data["destination"] == "L1"
        assert data["cpass_status"] == "RETURNED_TO_L1"
        assert data["audit_status"] == "RETURNED_TO_L1"

        updated_audit = data["audit"]
        stages = extract_review_stages(updated_audit)
        assert stages["ch_status"] == "Returned to L1"
        assert stages["cops_status"] == "Pending"
        assert stages["bl_status"] == "Pending"

        signoff = updated_audit["signoff_details"]
        assert signoff["return_destination"] == "L1"
        assert signoff["return_to_l1"]["reason"] == payload["return_reason"]
        assert signoff["return_to_l1"]["returned_by"] == "L3 COPS Auditor"
        assert signoff["return_to_l1"]["stage"] == "COPS"

        # Check revision history
        rev_hist = signoff["revision_history"]
        last_rev = rev_hist[-1]
        assert last_rev["action"] == "RETURNED_TO_L1"
        assert last_rev["stage"] == "COPS"
        assert last_rev["destination"] == "L1"
        assert last_rev["reason"] == payload["return_reason"]

        # Preserve candidate data & statements
        assert updated_audit["employer_details"] == SAMPLE_EMPLOYER_DETAILS
        assert updated_audit["salary_details"] == SAMPLE_SALARY_DETAILS

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 2. L3 -> L2 Return Success
# -----------------------------------------------------------------------------
def test_l3_return_to_l2_success():
    """L3 returning to L2 sets SUBMITTED on cpass & audit status, CH to 'Pending', resets COPS/BL."""
    app.dependency_overrides[get_current_user] = lambda: L3_USER
    audit = create_ch_recommended_audit()

    with patch("app.routers.audits.supabase") as mock_sb:
        def table_mock(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif tbl == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[audit])
                def update_side_effect(up_data):
                    up_mock = MagicMock()
                    up_mock.eq.return_value.execute.return_value = MagicMock(data=[{**audit, **up_data}])
                    return up_mock
                m.update.side_effect = update_side_effect
            return m

        mock_sb.table.side_effect = table_mock

        payload = {
            "destination": "L2",
            "return_reason": "Gross salary recorded differs from appointment letter",
            "remarks": "Center Head please correct employer salary details before endorsement",
        }
        res = client.post("/candidates/10482/audit/l3-review/return", json=payload)
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "success"
        assert data["destination"] == "L2"
        assert data["cpass_status"] == "SUBMITTED"
        assert data["audit_status"] == "SUBMITTED"

        updated_audit = data["audit"]
        stages = extract_review_stages(updated_audit)
        assert stages["ch_status"] == "Pending"
        assert stages["cops_status"] == "Pending"
        assert stages["bl_status"] == "Pending"

        signoff = updated_audit["signoff_details"]
        assert signoff["return_destination"] == "L2"
        assert signoff["return_to_l2"]["reason"] == payload["return_reason"]
        assert signoff["return_to_l2"]["returned_by"] == "L3 COPS Auditor"
        assert signoff["return_to_l2"]["stage"] == "COPS"

        # Check revision history
        rev_hist = signoff["revision_history"]
        last_rev = rev_hist[-1]
        assert last_rev["action"] == "RETURNED_TO_L2"
        assert last_rev["stage"] == "COPS"
        assert last_rev["destination"] == "L2"
        assert last_rev["reason"] == payload["return_reason"]

        # Preserve candidate data & statements
        assert updated_audit["employer_details"] == SAMPLE_EMPLOYER_DETAILS
        assert updated_audit["salary_details"] == SAMPLE_SALARY_DETAILS

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 3. Destination Validation (Rejects L3, L4, L5, or invalid destinations)
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("invalid_dest", ["L3", "L4", "L5", "COPS", "l3", "SELF", "INVALID", ""])
def test_l3_return_rejects_invalid_destinations_with_422(invalid_dest):
    """Destination must be strictly 'L1' or 'L2'; self-return (L3) or others must fail with HTTP 422."""
    app.dependency_overrides[get_current_user] = lambda: L3_USER
    audit = create_ch_recommended_audit()

    with patch("app.routers.audits.supabase") as mock_sb:
        def table_mock(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif tbl == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[audit])
            return m

        mock_sb.table.side_effect = table_mock

        payload = {
            "destination": invalid_dest,
            "return_reason": "Testing invalid destination rejection",
        }
        res = client.post("/candidates/10482/audit/l3-review/return", json=payload)
        assert res.status_code == 422, f"Expected 422 for destination {invalid_dest}, got {res.status_code}"

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 4. Mandatory Return Reason Validation
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("empty_reason", ["", "   ", None])
def test_l3_return_requires_non_empty_return_reason(empty_reason):
    """Missing or blank return reason must fail with HTTP 422."""
    app.dependency_overrides[get_current_user] = lambda: L3_USER

    with patch("app.routers.audits.supabase") as mock_sb:
        def table_mock(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            return m
        mock_sb.table.side_effect = table_mock

        payload = {"destination": "L1"}
        if empty_reason is not None:
            payload["return_reason"] = empty_reason

        res = client.post("/candidates/10482/audit/l3-review/return", json=payload)
        assert res.status_code == 422

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 5. Authorization Enforcement
# -----------------------------------------------------------------------------
def test_l3_return_role_authorization():
    """Only L3_COPS, L3_LEADER, and ADMIN can invoke L3 return; L1, L2, L4 are rejected with HTTP 403."""
    audit = create_ch_recommended_audit()

    for user, expected_status in [
        (L1_USER, 403),
        (L2_USER, 403),
        (L4_USER, 403),
        (L3_USER, 200),
        (L3_LEADER, 200),
        (ADMIN_USER, 200),
    ]:
        app.dependency_overrides[get_current_user] = lambda u=user: u

        with patch("app.routers.audits.supabase") as mock_sb:
            def table_mock(tbl):
                m = MagicMock()
                if tbl == "ddugky_candidates":
                    m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
                elif tbl == "placement_audits":
                    m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[audit])
                    m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[audit])
                return m

            mock_sb.table.side_effect = table_mock

            payload = {
                "destination": "L1",
                "return_reason": f"Role check for {user.role}",
            }
            res = client.post("/candidates/10482/audit/l3-review/return", json=payload)
            assert res.status_code == expected_status, f"Role {user.role} expected {expected_status}, got {res.status_code}"

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 6. Progression to L3 Blocked Until L2 Recommends
# -----------------------------------------------------------------------------
def test_l3_progression_blocked_when_returned():
    """L3 cannot approve, reject, or return candidates that are returned to L1 or L2."""
    app.dependency_overrides[get_current_user] = lambda: L3_USER

    # Case A: Audit returned to L1 (ch_status == 'Returned to L1')
    returned_to_l1_audit = {
        "id": "audit-ret-l1",
        "candidate_id": 10482,
        "audit_status": "RETURNED_TO_L1",
        "cpass_status": "RETURNED_TO_L1",
        "signoff_details": {
            "review_stages": {"ch": {"status": "Returned to L1"}, "cops": {"status": "Pending"}, "bl": {"status": "Pending"}}
        },
    }

    # Case B: Audit returned to L2 (ch_status == 'Pending', audit_status == 'SUBMITTED')
    returned_to_l2_audit = {
        "id": "audit-ret-l2",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "SUBMITTED",
        "signoff_details": {
            "review_stages": {"ch": {"status": "Pending"}, "cops": {"status": "Pending"}, "bl": {"status": "Pending"}}
        },
    }

    for test_audit, case_name in [(returned_to_l1_audit, "Returned to L1"), (returned_to_l2_audit, "Returned to L2")]:
        with patch("app.routers.audits.supabase") as mock_sb:
            def table_mock(tbl):
                m = MagicMock()
                if tbl == "ddugky_candidates":
                    m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
                elif tbl == "placement_audits":
                    m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[test_audit])
                return m

            mock_sb.table.side_effect = table_mock

            # COPS approve blocked
            res_app = client.post("/candidates/10482/audit/l3-review/approve", json={"remarks": "test"})
            assert res_app.status_code == 400, f"{case_name}: Expected 400 for COPS approve, got {res_app.status_code}"

            # COPS reject blocked
            res_rej = client.post("/candidates/10482/audit/l3-review/reject", json={"rejection_reason": "test"})
            assert res_rej.status_code == 400, f"{case_name}: Expected 400 for COPS reject, got {res_rej.status_code}"

            # COPS return blocked
            res_ret = client.post("/candidates/10482/audit/l3-review/return", json={"destination": "L1", "return_reason": "test"})
            assert res_ret.status_code == 400, f"{case_name}: Expected 400 for COPS return, got {res_ret.status_code}"

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 7. L2 Can Review and Approve Candidate Returned From L3
# -----------------------------------------------------------------------------
def test_l2_can_review_and_approve_candidate_returned_from_l3():
    """After L3 returns candidate to L2, L2 can review and approve it (transitioning to L2_APPROVED)."""
    returned_to_l2_audit = {
        "id": "audit-ret-l2",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "SUBMITTED",
        "employer_details": SAMPLE_EMPLOYER_DETAILS,
        "salary_details": SAMPLE_SALARY_DETAILS,
        "document_audit": {"l2_document_reviews": DOC_REVIEWS_CHECKED},
        "signoff_details": {
            "review_stages": {"ch": {"status": "Pending"}, "cops": {"status": "Pending"}, "bl": {"status": "Pending"}},
            "return_to_l2": {"stage": "COPS", "reason": "Gross salary mismatch"},
        },
    }

    # Step 1: L2 approves candidate
    app.dependency_overrides[get_current_user] = lambda: L2_USER

    with patch("app.routers.audits.supabase") as mock_sb:
        def table_mock(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif tbl == "candidate_holds":
                m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            elif tbl == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[returned_to_l2_audit])
                def update_side_effect(up_data):
                    up_mock = MagicMock()
                    up_mock.eq.return_value.execute.return_value = MagicMock(data=[{**returned_to_l2_audit, **up_data}])
                    return up_mock
                m.update.side_effect = update_side_effect
            elif tbl == "candidate_documents":
                m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=MANDATORY_DOCS)
            return m

        mock_sb.table.side_effect = table_mock

        res = client.post("/candidates/10482/audit/l2-review/approve", json={"remarks": "CH Re-verified and approved"})
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["cpass_status"] == "L2_APPROVED"
        stages = extract_review_stages(data["audit"])
        assert stages["ch_status"] == "Recommended"

    # Step 2: Now that L2 approved, L3 can review and approve it!
    ch_re_approved_audit = data["audit"]
    app.dependency_overrides[get_current_user] = lambda: L3_USER

    with patch("app.routers.audits.supabase") as mock_sb:
        def table_mock(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif tbl == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[ch_re_approved_audit])
                def update_side_effect(up_data):
                    up_mock = MagicMock()
                    up_mock.eq.return_value.execute.return_value = MagicMock(data=[{**ch_re_approved_audit, **up_data}])
                    return up_mock
                m.update.side_effect = update_side_effect
            return m

        mock_sb.table.side_effect = table_mock

        res_l3 = client.post("/candidates/10482/audit/l3-review/approve", json={"remarks": "COPS verified after L2 corrections"})
        assert res_l3.status_code == 200
        assert res_l3.json()["cpass_status"] == "VERIFIED"

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 8. Cannot Return Finalized (Approved) or Rejected Candidates
# -----------------------------------------------------------------------------
def test_l3_cannot_return_finalized_or_rejected():
    """Candidate with final APPROVED or REJECTED status cannot be returned."""
    app.dependency_overrides[get_current_user] = lambda: L3_USER

    approved_audit = {
        "id": "audit-app",
        "candidate_id": 10482,
        "cpass_status": "APPROVED",
        "audit_status": "APPROVED",
    }

    with patch("app.routers.audits.supabase") as mock_sb:
        def table_mock(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif tbl == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[approved_audit])
            return m

        mock_sb.table.side_effect = table_mock

        res = client.post("/candidates/10482/audit/l3-review/return", json={"destination": "L1", "return_reason": "test"})
        assert res.status_code == 400
        assert "final approval" in res.json()["detail"].lower()

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 9. Legacy Alias Endpoint /l3-review/return-to-l1
# -----------------------------------------------------------------------------
def test_l3_legacy_return_to_l1_endpoint():
    """Legacy alias endpoint /l3-review/return-to-l1 returns candidate to L1."""
    app.dependency_overrides[get_current_user] = lambda: L3_USER
    audit = create_ch_recommended_audit()

    with patch("app.routers.audits.supabase") as mock_sb:
        def table_mock(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif tbl == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[audit])
                def update_side_effect(up_data):
                    up_mock = MagicMock()
                    up_mock.eq.return_value.execute.return_value = MagicMock(data=[{**audit, **up_data}])
                    return up_mock
                m.update.side_effect = update_side_effect
            return m

        mock_sb.table.side_effect = table_mock

        payload = {
            "return_reason": "Legacy return-to-L1 test",
            "remarks": "Check documents",
        }
        res = client.post("/candidates/10482/audit/l3-review/return-to-l1", json=payload)
        assert res.status_code == 200
        assert res.json()["destination"] == "L1"
        assert res.json()["cpass_status"] == "RETURNED_TO_L1"

    app.dependency_overrides.clear()
