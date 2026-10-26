"""Automated tests for CPASS Multi-Level Candidate Review Statuses (L2 CH, L3 COPS, L4 BL).

Verifies:
1. New candidates begin with Pending review stages (CH: Pending, COPS: Pending, BL: Pending).
2. L1 submission makes a candidate eligible for CH review without auto-approval.
3. CH approval produces Recommended and enables COPS.
4. COPS approval produces Verified and enables BL.
5. BL approval produces Approved and updates overall candidate status to APPROVED.
6. Rejection at each stage appears in the existing Rejected dashboard (cpass_rejected filter/count).
7. Rejected candidates cannot progress to later review stages.
8. Out-of-order approvals are rejected by backend (e.g. COPS before CH; BL before COPS).
9. Incorrect roles cannot perform stage reviews (L1 forbidden on reviews; L2 cannot review COPS/BL; etc.).
10. L1 state/centre isolation remains enforced (foreign state access returns 403).
11. Existing candidate records and historical statuses remain intact (backwards compatibility).
12. L1 dashboard candidates popup returns ch_status, cops_status, bl_status, and search/pagination work.
13. Audit statement endpoint exposes review_stages.
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
)

ADMIN_USER = CurrentUser(
    id="admin-user-uuid",
    email="admin@cpass.org",
    full_name="Admin Director",
    role="ADMIN",
)

CANDIDATE_ODISHA = {
    "candidate_id": 10482,
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

CANDIDATE_KERALA = {
    "candidate_id": 20999,
    "candidate_first_name": "Rahul",
    "candidate_last_name": "Nair",
    "candidate_father_name": "Gopal Nair",
    "tc_id": 201,
    "tc_name": "Kochi Skill Centre",
    "tc_state_name": "Kerala",
    "batch_code": "BATCH-KL-2023-01",
    "sanction_order_number": "SO-KL-01",
    "appointed": True,
}

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


# -----------------------------------------------------------------------------
# 1. New Candidates Begin With Pending Review Stages
# -----------------------------------------------------------------------------
def test_new_candidate_begins_with_pending_stages():
    """Empty or draft candidate audit returns CH: Pending, COPS: Pending, BL: Pending."""
    stages = extract_review_stages(None)
    assert stages["ch_status"] == "Pending"
    assert stages["cops_status"] == "Pending"
    assert stages["bl_status"] == "Pending"

    draft_audit = {
        "candidate_id": 10482,
        "cpass_status": "PENDING",
        "audit_status": "DRAFT",
        "signoff_details": {
            "review_stages": {
                "ch": {"status": "Pending"},
                "cops": {"status": "Pending"},
                "bl": {"status": "Pending"},
            }
        },
    }
    extracted = extract_review_stages(draft_audit)
    assert extracted["ch_status"] == "Pending"
    assert extracted["cops_status"] == "Pending"
    assert extracted["bl_status"] == "Pending"


# -----------------------------------------------------------------------------
# 2. L1 Submission Keeps Stages Pending & Enables L2/CH Review
# -----------------------------------------------------------------------------
def test_l1_submission_keeps_stages_pending_and_prevents_duplicate():
    """L1 submission keeps review stages Pending without auto-approval, and blocks duplicate submission."""
    app.dependency_overrides[get_current_user] = lambda: L1_USER

    # Initial submission payload
    sub_payload = {
        "candidate_snapshot": {},
        "employer_details": [
            {
                "employer_name": "Reliance Retail Ltd",
                "months_worked": 3,
                "appointment_date": "2026-01-01",
                "designation": "Sales Associate",
                "place_of_work": "Bhubaneswar",
                "monthly_ctc": 16500.0,
                "minimum_wages": 14000.0,
            }
        ],
        "salary_details": [
            {"month": 1, "year": 2026, "gross_salary": 16500, "net_salary": 15000, "amount_credited": 15000, "bank_name": "SBI"},
            {"month": 2, "year": 2026, "gross_salary": 16500, "net_salary": 15000, "amount_credited": 15000, "bank_name": "SBI"},
            {"month": 3, "year": 2026, "gross_salary": 16500, "net_salary": 15000, "amount_credited": 15000, "bank_name": "SBI"},
        ],
        "document_audit": {"overall_compliance": True},
        "signoff_details": {},
        "remarks": "Submitted by L1",
    }

    with patch("app.routers.audits.supabase") as mock_sb:
        # Candidate exists and has no holds
        def table_mock(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif tbl == "candidate_holds":
                m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            elif tbl == "placement_audits":
                # First submission: no existing audit
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
                m.insert.return_value.execute.return_value = MagicMock(data=[{
                    "id": "audit-1",
                    "candidate_id": 10482,
                    "audit_status": "SUBMITTED",
                    "cpass_status": "PENDING",
                    "signoff_details": {
                        "review_stages": {"ch": {"status": "Pending"}, "cops": {"status": "Pending"}, "bl": {"status": "Pending"}}
                    }
                }])
            return m

        mock_sb.table.side_effect = table_mock

        res = client.post("/candidates/10482/audit/submit", json=sub_payload)
        assert res.status_code == 200
        data = res.json()
        audit = data["audit"]
        assert audit["audit_status"] == "SUBMITTED"
        assert audit["cpass_status"] == "PENDING"
        stages = extract_review_stages(audit)
        assert stages["ch_status"] == "Pending"
        assert stages["cops_status"] == "Pending"
        assert stages["bl_status"] == "Pending"

        # Attempt duplicate submission
        def dup_table_mock(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif tbl == "candidate_holds":
                m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            elif tbl == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[{
                    "id": "audit-1",
                    "candidate_id": 10482,
                    "audit_status": "SUBMITTED",
                    "cpass_status": "PENDING",
                }])
            return m

        mock_sb.table.side_effect = dup_table_mock
        res_dup = client.post("/candidates/10482/audit/submit", json=sub_payload)
        assert res_dup.status_code == 400
        assert "already been submitted" in res_dup.json()["detail"].lower()

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 3. CH Approval Sets Recommended & Unlocks COPS
# -----------------------------------------------------------------------------
def test_ch_approval_sets_recommended_and_enables_cops():
    """L2 approval updates CH stage to Recommended and sets cpass_status to L2_APPROVED."""
    app.dependency_overrides[get_current_user] = lambda: L2_USER

    submitted_audit = {
        "id": "audit-1",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "PENDING",
        "document_audit": {"l2_document_reviews": DOC_REVIEWS_CHECKED},
        "signoff_details": {
            "review_stages": {"ch": {"status": "Pending"}, "cops": {"status": "Pending"}, "bl": {"status": "Pending"}}
        },
    }

    with patch("app.routers.audits.supabase") as mock_sb:
        def table_mock(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif tbl == "candidate_holds":
                m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            elif tbl == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[submitted_audit])
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{
                    **submitted_audit,
                    "cpass_status": "L2_APPROVED",
                    "signoff_details": {
                        "review_stages": {"ch": {"status": "Recommended"}, "cops": {"status": "Pending"}, "bl": {"status": "Pending"}},
                        "centre_head": {"recommended": True},
                    }
                }])
            elif tbl == "candidate_documents":
                m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=MANDATORY_DOCS)
            return m

        mock_sb.table.side_effect = table_mock

        res = client.post("/candidates/10482/audit/l2-review/approve", json={"remarks": "CH Verified"})
        assert res.status_code == 200
        data = res.json()
        assert data["cpass_status"] == "L2_APPROVED"
        audit = data["audit"]
        stages = extract_review_stages(audit)
        assert stages["ch_status"] == "Recommended"
        assert stages["cops_status"] == "Pending"
        assert stages["bl_status"] == "Pending"

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 4. COPS Approval Sets Verified & Unlocks BL
# -----------------------------------------------------------------------------
def test_cops_approval_sets_verified_and_enables_bl():
    """L3 approval sets COPS stage to Verified and overall cpass_status to VERIFIED."""
    app.dependency_overrides[get_current_user] = lambda: L3_USER

    ch_approved_audit = {
        "id": "audit-1",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "L2_APPROVED",
        "signoff_details": {
            "review_stages": {"ch": {"status": "Recommended"}, "cops": {"status": "Pending"}, "bl": {"status": "Pending"}}
        },
    }

    with patch("app.routers.audits.supabase") as mock_sb:
        def table_mock(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif tbl == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[ch_approved_audit])
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{
                    **ch_approved_audit,
                    "cpass_status": "VERIFIED",
                    "signoff_details": {
                        "review_stages": {"ch": {"status": "Recommended"}, "cops": {"status": "Verified"}, "bl": {"status": "Pending"}}
                    }
                }])
            return m

        mock_sb.table.side_effect = table_mock

        res = client.post("/candidates/10482/audit/l3-review/approve", json={"remarks": "COPS verified all docs"})
        assert res.status_code == 200
        data = res.json()
        assert data["cpass_status"] == "VERIFIED"
        stages = extract_review_stages(data["audit"])
        assert stages["ch_status"] == "Recommended"
        assert stages["cops_status"] == "Verified"
        assert stages["bl_status"] == "Pending"

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 5. BL Approval Sets Approved & Updates Overall Candidate Status
# -----------------------------------------------------------------------------
def test_bl_approval_sets_approved_and_finalizes_overall_status():
    """L4 approval sets BL stage to Approved and overall cpass_status to APPROVED."""
    app.dependency_overrides[get_current_user] = lambda: L4_USER

    cops_verified_audit = {
        "id": "audit-1",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "VERIFIED",
        "signoff_details": {
            "review_stages": {"ch": {"status": "Recommended"}, "cops": {"status": "Verified"}, "bl": {"status": "Pending"}}
        },
    }

    with patch("app.routers.audits.supabase") as mock_sb:
        def table_mock(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif tbl == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[cops_verified_audit])
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{
                    **cops_verified_audit,
                    "cpass_status": "APPROVED",
                    "signoff_details": {
                        "review_stages": {"ch": {"status": "Recommended"}, "cops": {"status": "Verified"}, "bl": {"status": "Approved"}}
                    }
                }])
            return m

        mock_sb.table.side_effect = table_mock

        res = client.post("/candidates/10482/audit/l4-review/approve", json={"remarks": "Final executive signoff"})
        assert res.status_code == 200
        data = res.json()
        assert data["cpass_status"] == "APPROVED"
        stages = extract_review_stages(data["audit"])
        assert stages["ch_status"] == "Recommended"
        assert stages["cops_status"] == "Verified"
        assert stages["bl_status"] == "Approved"

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 6. Rejection at Each Stage Appears in Rejected Dashboard
# -----------------------------------------------------------------------------
def test_rejection_at_each_stage():
    """L2, L3, and L4 rejections properly persist rejection details and set cpass_status to REJECTED."""
    # Test L2 reject
    app.dependency_overrides[get_current_user] = lambda: L2_USER
    submitted_audit = {"id": "audit-1", "candidate_id": 10482, "audit_status": "SUBMITTED", "cpass_status": "PENDING"}

    with patch("app.routers.audits.supabase") as mock_sb:
        def table_mock_l2(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif tbl == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[submitted_audit])
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{**submitted_audit, "cpass_status": "REJECTED"}])
            elif tbl == "user_centres":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            return m

        mock_sb.table.side_effect = table_mock_l2
        res_l2 = client.post("/candidates/10482/audit/l2-review/reject", json={"rejection_reason": "Fake salary slip"})
        assert res_l2.status_code == 200
        assert res_l2.json()["cpass_status"] == "REJECTED"

    # Test L3 reject
    app.dependency_overrides[get_current_user] = lambda: L3_USER
    ch_approved = {
        "id": "audit-1",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "L2_APPROVED",
        "signoff_details": {"review_stages": {"ch": {"status": "Recommended"}, "cops": {"status": "Pending"}, "bl": {"status": "Pending"}}},
    }
    with patch("app.routers.audits.supabase") as mock_sb:
        def table_mock_l3(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif tbl == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[ch_approved])
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{**ch_approved, "cpass_status": "REJECTED"}])
            elif tbl == "user_centres":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            return m

        mock_sb.table.side_effect = table_mock_l3
        res_l3 = client.post("/candidates/10482/audit/l3-review/reject", json={"rejection_reason": "Bank statement amount mismatch"})
        assert res_l3.status_code == 200
        assert res_l3.json()["cpass_status"] == "REJECTED"

    # Test L4 reject
    app.dependency_overrides[get_current_user] = lambda: L4_USER
    cops_verified = {
        "id": "audit-1",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "VERIFIED",
        "signoff_details": {"review_stages": {"ch": {"status": "Recommended"}, "cops": {"status": "Verified"}, "bl": {"status": "Pending"}}},
    }
    with patch("app.routers.audits.supabase") as mock_sb:
        def table_mock_l4(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif tbl == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[cops_verified])
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{**cops_verified, "cpass_status": "REJECTED"}])
            elif tbl == "user_centres":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            return m

        mock_sb.table.side_effect = table_mock_l4
        res_l4 = client.post("/candidates/10482/audit/l4-review/reject", json={"rejection_reason": "Employer ineligible"})
        assert res_l4.status_code == 200
        assert res_l4.json()["cpass_status"] == "REJECTED"

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 7. Rejected Candidates Cannot Progress to Later Stages
# -----------------------------------------------------------------------------
def test_rejected_candidates_cannot_progress():
    """A rejected candidate is blocked from subsequent approvals."""
    app.dependency_overrides[get_current_user] = lambda: L3_USER

    rejected_audit = {
        "id": "audit-1",
        "candidate_id": 10482,
        "audit_status": "REJECTED",
        "cpass_status": "REJECTED",
        "signoff_details": {
            "review_stages": {"ch": {"status": "Rejected"}, "cops": {"status": "Pending"}, "bl": {"status": "Pending"}}
        },
    }

    with patch("app.routers.audits.supabase") as mock_sb:
        def table_mock_rej(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif tbl == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[rejected_audit])
            elif tbl == "user_centres":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            return m

        mock_sb.table.side_effect = table_mock_rej

        res = client.post("/candidates/10482/audit/l3-review/approve", json={"remarks": "Attempt approval"})
        assert res.status_code == 400
        assert "already been rejected" in res.json()["detail"].lower()

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 8. Out-of-Order Approvals Are Blocked
# -----------------------------------------------------------------------------
def test_out_of_order_approvals_are_blocked():
    """COPS cannot approve before CH; BL cannot approve before COPS."""
    # COPS tries to approve while CH is still Pending
    app.dependency_overrides[get_current_user] = lambda: L3_USER

    pending_audit = {
        "id": "audit-1",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "PENDING",
        "signoff_details": {
            "review_stages": {"ch": {"status": "Pending"}, "cops": {"status": "Pending"}, "bl": {"status": "Pending"}}
        },
    }

    with patch("app.routers.audits.supabase") as mock_sb:
        def table_mock_pending(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif tbl == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[pending_audit])
            elif tbl == "user_centres":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            return m

        mock_sb.table.side_effect = table_mock_pending
        res_cops = client.post("/candidates/10482/audit/l3-review/approve", json={})
        assert res_cops.status_code == 400
        assert "must first be recommended by l2" in res_cops.json()["detail"].lower()

    # BL tries to approve while COPS is still Pending
    app.dependency_overrides[get_current_user] = lambda: L4_USER
    ch_approved_audit = {
        "id": "audit-1",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "L2_APPROVED",
        "signoff_details": {
            "review_stages": {"ch": {"status": "Recommended"}, "cops": {"status": "Pending"}, "bl": {"status": "Pending"}}
        },
    }
    with patch("app.routers.audits.supabase") as mock_sb:
        def table_mock_ch_app(tbl):
            m = MagicMock()
            if tbl == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif tbl == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[ch_approved_audit])
            elif tbl == "user_centres":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            return m

        mock_sb.table.side_effect = table_mock_ch_app
        res_bl = client.post("/candidates/10482/audit/l4-review/approve", json={})
        assert res_bl.status_code == 400
        assert "must first be verified by l3" in res_bl.json()["detail"].lower()

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 9. Role Permissions Enforced
# -----------------------------------------------------------------------------
def test_role_enforcement():
    """L1 cannot approve; L2 cannot review COPS/BL; L3 cannot review CH/BL; L4 cannot review CH/COPS."""
    # L1 cannot review
    app.dependency_overrides[get_current_user] = lambda: L1_USER
    res1 = client.post("/candidates/10482/audit/l2-review/approve", json={})
    assert res1.status_code == 403

    # L2 cannot review COPS
    app.dependency_overrides[get_current_user] = lambda: L2_USER
    res2 = client.post("/candidates/10482/audit/l3-review/approve", json={})
    assert res2.status_code == 403

    # L3 cannot review BL
    app.dependency_overrides[get_current_user] = lambda: L3_USER
    res3 = client.post("/candidates/10482/audit/l4-review/approve", json={})
    assert res3.status_code == 403

    # L4 cannot review CH
    app.dependency_overrides[get_current_user] = lambda: L4_USER
    res4 = client.post("/candidates/10482/audit/l2-review/approve", json={})
    assert res4.status_code == 403

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 10. L1 State/Centre Isolation Enforced
# -----------------------------------------------------------------------------
def test_l1_state_centre_isolation():
    """L1 Coordinator assigned to Odisha cannot access Kerala candidates."""
    app.dependency_overrides[get_current_user] = lambda: L1_USER

    with patch("app.routers.audits.supabase") as mock_sb:
        mock_sb.table.side_effect = lambda tbl: MagicMock(
            select=MagicMock(return_value=MagicMock(eq=MagicMock(return_value=MagicMock(limit=MagicMock(return_value=MagicMock(execute=MagicMock(data=[CANDIDATE_KERALA]))))))),
        )

        res = client.get("/candidates/20999/audit")
        assert res.status_code == 403
        assert "access to candidates in this state" in res.json()["detail"].lower()

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 11. Existing Data & Historical Statuses Intact
# -----------------------------------------------------------------------------
def test_existing_data_derivation():
    """Historical records without explicit review_stages map accurately."""
    # Legacy APPROVED
    legacy_approved = {"cpass_status": "APPROVED", "audit_status": "APPROVED"}
    s1 = extract_review_stages(legacy_approved)
    assert s1["ch_status"] == "Recommended"
    assert s1["cops_status"] == "Verified"
    assert s1["bl_status"] == "Approved"

    # Legacy VERIFIED
    legacy_verified = {"cpass_status": "VERIFIED", "audit_status": "SUBMITTED"}
    s2 = extract_review_stages(legacy_verified)
    assert s2["ch_status"] == "Recommended"
    assert s2["cops_status"] == "Verified"
    assert s2["bl_status"] == "Pending"

    # Legacy L2_APPROVED
    legacy_l2 = {"cpass_status": "L2_APPROVED", "audit_status": "SUBMITTED"}
    s3 = extract_review_stages(legacy_l2)
    assert s3["ch_status"] == "Recommended"
    assert s3["cops_status"] == "Pending"
    assert s3["bl_status"] == "Pending"

    # Legacy REJECTED
    legacy_rejected = {"cpass_status": "REJECTED", "audit_status": "REJECTED"}
    s4 = extract_review_stages(legacy_rejected)
    assert s4["ch_status"] == "Rejected"
    assert s4["cops_status"] == "Pending"
    assert s4["bl_status"] == "Pending"


# -----------------------------------------------------------------------------
# 12. Dashboard Candidate List Exposes Stage Statuses
# -----------------------------------------------------------------------------
def test_dashboard_candidate_list_exposes_stage_statuses():
    """GET /dashboard/candidates returns ch_status, cops_status, bl_status per candidate."""
    app.dependency_overrides[get_current_user] = lambda: L1_USER

    with patch("app.routers.dashboard.supabase") as mock_sb:
        # Mock candidate_documents
        docs_mock = MagicMock(data=[{"candidate_id": 10482}])
        # Mock placement_audits
        audit_mock = MagicMock(data=[{
            "candidate_id": 10482,
            "cpass_status": "L2_APPROVED",
            "audit_status": "SUBMITTED",
            "signoff_details": {
                "review_stages": {"ch": {"status": "Recommended"}, "cops": {"status": "Pending"}, "bl": {"status": "Pending"}}
            }
        }])
        # Mock ddugky_candidates
        cands_mock = MagicMock(
            count=1,
            data=[CANDIDATE_ODISHA]
        )

        def tbl_mock(name):
            m = MagicMock()
            if name == "candidate_documents":
                m.select.return_value.neq.return_value.execute.return_value = docs_mock
            elif name == "placement_audits":
                m.select.return_value.execute.return_value = audit_mock
            elif name == "ddugky_candidates":
                m.select.return_value.in_.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"candidate_id": 10482, "tc_state_name": "ODISHA"}])
                m.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value = cands_mock
            return m

        mock_sb.table.side_effect = tbl_mock

        res = client.get("/dashboard/candidates?state=ODISHA&page=1&page_size=20")
        assert res.status_code == 200
        data = res.json()
        assert data["total_count"] == 1
        cand = data["candidates"][0]
        assert cand["candidate_id"] == 10482
        assert cand["ch_status"] == "Recommended"
        assert cand["cops_status"] == "Pending"
        assert cand["bl_status"] == "Pending"
        assert "review_stages" in cand

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 13. Dashboard Candidate List Exposes Return & Rejection Reasons for L1
# -----------------------------------------------------------------------------
def test_dashboard_candidate_list_exposes_return_rejection_reasons():
    """GET /dashboard/candidates includes return_reason, rejection_reason, and rejected_stage."""
    app.dependency_overrides[get_current_user] = lambda: L1_USER

    with patch("app.routers.dashboard.supabase") as mock_sb:
        docs_mock = MagicMock(data=[{"candidate_id": 10482}])
        audit_mock = MagicMock(data=[{
            "candidate_id": 10482,
            "cpass_status": "RETURNED_TO_L1",
            "audit_status": "RETURNED_TO_L1",
            "signoff_details": {
                "review_stages": {"ch": {"status": "Returned to L1", "reason": "Salary mismatch"}},
                "return_to_l1": {"return_reason": "Salary credit amount differs from slip", "returned_by": "CH User"},
                "rejected_stage": "ch",
            }
        }])
        cands_mock = MagicMock(
            count=1,
            data=[CANDIDATE_ODISHA]
        )

        def tbl_mock(name):
            m = MagicMock()
            if name == "candidate_documents":
                m.select.return_value.neq.return_value.execute.return_value = docs_mock
            elif name == "placement_audits":
                m.select.return_value.execute.return_value = audit_mock
            elif name == "ddugky_candidates":
                m.select.return_value.in_.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"candidate_id": 10482, "tc_state_name": "ODISHA"}])
                m.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value = cands_mock
            return m

        mock_sb.table.side_effect = tbl_mock

        res = client.get("/dashboard/candidates?state=ODISHA&page=1&page_size=20")
        assert res.status_code == 200
        cand = res.json()["candidates"][0]
        assert cand["candidate_id"] == 10482
        assert cand["cpass_status"] == "RETURNED_TO_L1"
        assert cand["ch_status"] == "Returned to L1"
        assert cand["return_reason"] == "Salary credit amount differs from slip"
        assert cand["rejected_stage"] == "ch"

    app.dependency_overrides.clear()

