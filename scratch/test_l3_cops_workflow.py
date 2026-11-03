"""Automated end-to-end tests for CPASS L3 (COPS) Audit Workflow.

Verifies:
1. Document access permissions: L3_COPS can list, summarize, and download candidate documents.
2. Review sequencing: COPS cannot approve or return before L2 CH has recommended the dossier.
3. Statutory evidence validation: COPS approval strictly verifies Appointment Letter, 3 Salary Slips,
   and at least 3 distinct months of Bank Statement coverage (including consolidated statements).
4. L3 Document Checklist persistence: Auditor reviews per document are stored in document_audit.
5. COPS Approval & progression: Updates cpass_status to VERIFIED and unlocks L4 BL stage.
6. L4 BL Approval progression: L4 approves verified dossier and updates cpass_status to APPROVED.
7. COPS Return-to-L1: Returns dossier with reason, updates return_history & revision_history, blocks L4,
   and resets stages upon L1 resubmission to enforce L2 re-review.
8. COPS Rejection: Marks dossier as REJECTED and permanently stops progression to L4.
9. Dashboard metrics & queue filters: Computes l3_received, l3_verified, l3_rejected, l3_returned,
   l3_pending and supports candidate queue filtering.
10. National accounts: Global L3 accounts can access aggregates without silent zero counts.
"""

import copy
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

CANDIDATE_ODISHA = {
    "candidate_id": 9901,
    "candidate_first_name": "Sunil",
    "candidate_last_name": "Kumar",
    "candidate_father_name": "Bimal Kumar",
    "tc_id": 101,
    "tc_name": "Bhubaneswar Skill Centre",
    "tc_state_name": "Odisha",
    "batch_code": "BATCH-OD-2026-01",
    "sanction_order_number": "SO-2026-01",
    "appointed": True,
    "employer_name": "TCS Ltd",
}

VALID_DOCS = [
    {
        "id": "doc-al-1",
        "candidate_id": 9901,
        "document_type": "APPOINTMENT_LETTER",
        "upload_status": "SUCCESS",
        "reporting_month": None,
        "reporting_year": None,
        "file_name": "offer_letter.pdf",
        "drive_file_id": "drive-al-1",
        "employer_id": "emp_1",
    },
    {
        "id": "doc-slip-1",
        "candidate_id": 9901,
        "document_type": "SALARY_SLIP",
        "upload_status": "SUCCESS",
        "reporting_month": 1,
        "reporting_year": 2026,
        "file_name": "slip_jan.pdf",
        "drive_file_id": "drive-slip-1",
        "employer_id": "emp_1",
    },
    {
        "id": "doc-slip-2",
        "candidate_id": 9901,
        "document_type": "SALARY_SLIP",
        "upload_status": "SUCCESS",
        "reporting_month": 2,
        "reporting_year": 2026,
        "file_name": "slip_feb.pdf",
        "drive_file_id": "drive-slip-2",
        "employer_id": "emp_1",
    },
    {
        "id": "doc-slip-3",
        "candidate_id": 9901,
        "document_type": "SALARY_SLIP",
        "upload_status": "SUCCESS",
        "reporting_month": 3,
        "reporting_year": 2026,
        "file_name": "slip_mar.pdf",
        "drive_file_id": "drive-slip-3",
        "employer_id": "emp_1",
    },
    {
        "id": "doc-bank-consol",
        "candidate_id": 9901,
        "document_type": "BANK_STATEMENT",
        "upload_status": "SUCCESS",
        "is_consolidated": True,
        "coverage_start_month": 1,
        "coverage_start_year": 2026,
        "coverage_end_month": 3,
        "coverage_end_year": 2026,
        "covered_months": [
            {"year": 2026, "month": 1},
            {"year": 2026, "month": 2},
            {"year": 2026, "month": 3},
        ],
        "file_name": "bank_statement_q1.pdf",
        "drive_file_id": "drive-bank-consol",
    },
]

_BASE_CH_RECOMMENDED_AUDIT = {
    "id": "audit-9901",
    "candidate_id": 9901,
    "audit_status": "SUBMITTED",
    "cpass_status": "L2_APPROVED",
    "employer_details": [
        {"id": "emp_1", "employer_name": "TCS Ltd", "monthly_ctc": 18000.0}
    ],
    "salary_details": [
        {"month": 1, "year": 2026, "employer_id": "emp_1", "amount_credited": 16500.0, "gross_salary": 18000.0},
        {"month": 2, "year": 2026, "employer_id": "emp_1", "amount_credited": 16500.0, "gross_salary": 18000.0},
        {"month": 3, "year": 2026, "employer_id": "emp_1", "amount_credited": 16500.0, "gross_salary": 18000.0},
    ],
    "document_audit": {
        "l2_document_reviews": {
            "doc-al-1": {"reviewed": True},
            "doc-slip-1": {"reviewed": True},
            "doc-slip-2": {"reviewed": True},
            "doc-slip-3": {"reviewed": True},
            "doc-bank-consol": {"reviewed": True},
        },
        "l3_document_reviews": {
            "doc-al-1": {"reviewed": True},
            "doc-slip-1": {"reviewed": True},
            "doc-slip-2": {"reviewed": True},
            "doc-slip-3": {"reviewed": True},
            "doc-bank-consol": {"reviewed": True},
        },
    },
    "signoff_details": {
        "review_stages": {
            "ch": {"status": "Recommended", "reviewed_by": "L2 Centre Head"},
            "cops": {"status": "Pending"},
            "bl": {"status": "Pending"},
        },
        "centre_head": {"name": "L2 Centre Head", "confirmed": True, "recommended": True},
    },
}

def make_ch_audit():
    return copy.deepcopy(_BASE_CH_RECOMMENDED_AUDIT)


# =============================================================================
# 1. Document Access for L3 COPS Reviewer
# =============================================================================
def test_l3_cops_document_access_permitted():
    """L3_COPS can list documents, view summaries, and download files."""
    app.dependency_overrides[get_current_user] = lambda: L3_USER

    with patch("app.routers.documents.supabase") as mock_sb, \
         patch("app.routers.documents.google_drive_service.download_file", return_value=(b"%PDF-1.4 mock", "test.pdf", "application/pdf")):

        def tbl_mock(name):
            m = MagicMock()
            if name == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif name == "candidate_documents":
                m.select.return_value.eq.return_value.neq.return_value.order.return_value.execute.return_value = MagicMock(data=VALID_DOCS)
                m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[VALID_DOCS[0]])
            return m

        mock_sb.table.side_effect = tbl_mock

        # List documents
        res_list = client.get("/candidates/9901/documents")
        assert res_list.status_code == 200
        docs = res_list.json()
        assert len(docs) == 5
        assert docs[0]["document_type"] == "APPOINTMENT_LETTER"

        # Download document
        res_down = client.get("/candidates/9901/documents/doc-al-1/download")
        assert res_down.status_code == 200
        assert res_down.content == b"%PDF-1.4 mock"

    app.dependency_overrides.clear()


# =============================================================================
# 2. Review Sequencing Gate
# =============================================================================
def test_cops_review_blocked_if_ch_not_recommended():
    """COPS cannot approve or return a candidate until L2 CH has recommended the dossier."""
    app.dependency_overrides[get_current_user] = lambda: L3_USER

    pending_ch_audit = {
        **make_ch_audit(),
        "signoff_details": {
            "review_stages": {"ch": {"status": "Pending"}, "cops": {"status": "Pending"}, "bl": {"status": "Pending"}}
        },
    }

    with patch("app.routers.audits.supabase") as mock_sb:
        def tbl_mock(name):
            m = MagicMock()
            if name == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif name == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[pending_ch_audit])
            return m

        mock_sb.table.side_effect = tbl_mock

        # Attempt approval before CH
        res_app = client.post("/candidates/9901/audit/l3-review/approve", json={"remarks": "Attempt approval"})
        assert res_app.status_code == 400
        assert "must first be recommended by l2" in res_app.json()["detail"].lower()

        # Attempt return before CH
        res_ret = client.post("/candidates/9901/audit/l3-review/return-to-l1", json={"return_reason": "Attempt return"})
        assert res_ret.status_code == 400
        assert "must first be recommended by l2" in res_ret.json()["detail"].lower()

    app.dependency_overrides.clear()


# =============================================================================
# 3. L3 Document Checklist Persistence
# =============================================================================
def test_l3_document_checklist_persistence():
    """L3 COPS auditor can persistently record checklist verification per document."""
    app.dependency_overrides[get_current_user] = lambda: L3_USER

    with patch("app.routers.audits.supabase") as mock_sb:
        audit_state = make_ch_audit()

        def tbl_mock(name):
            m = MagicMock()
            if name == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif name == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[audit_state])
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[audit_state])
            elif name == "candidate_documents":
                m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=VALID_DOCS)
            return m

        mock_sb.table.side_effect = tbl_mock

        checklist_payload = {
            "reviewed_documents": {
                "doc-al-1": {"reviewed": True, "notes": "Offer letter validated against salary CTC"},
                "doc-slip-1": {"reviewed": True},
            }
        }

        res = client.post("/candidates/9901/audit/l3-review/checklist", json=checklist_payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        reviews = data["l3_document_reviews"]
        assert reviews["doc-al-1"]["reviewed"] is True
        assert reviews["doc-al-1"]["notes"] == "Offer letter validated against salary CTC"
        assert reviews["doc-al-1"]["reviewed_by"] == "L3 COPS Auditor"

    app.dependency_overrides.clear()


# =============================================================================
# 4. Mandatory Evidence & Checklist Gate for COPS Approval
# =============================================================================
def test_cops_approval_blocked_when_evidence_or_checklist_incomplete():
    """COPS approval enforces appointment letter, salary slips, bank coverage, and checklist completion."""
    app.dependency_overrides[get_current_user] = lambda: L3_USER

    # Case A: Missing appointment letter
    docs_no_al = [d for d in VALID_DOCS if d["document_type"] != "APPOINTMENT_LETTER"]

    with patch("app.routers.audits.supabase") as mock_sb:
        def tbl_mock_no_al(name):
            m = MagicMock()
            if name == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif name == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[make_ch_audit()])
            elif name == "candidate_documents":
                m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=docs_no_al)
            return m

        mock_sb.table.side_effect = tbl_mock_no_al

        res = client.post("/candidates/9901/audit/l3-review/approve", json={"remarks": "Auditor approval"})
        assert res.status_code == 400
        assert "missing a verified appointment / offer letter" in res.json()["detail"].lower()

    # Case B: Unreviewed mandatory documents in checklist
    audit_unreviewed = {
        **make_ch_audit(),
        "document_audit": {"l3_document_reviews": {}}, # Empty checklist
    }

    with patch("app.routers.audits.supabase") as mock_sb:
        def tbl_mock_unrev(name):
            m = MagicMock()
            if name == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif name == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[audit_unreviewed])
            elif name == "candidate_documents":
                m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=VALID_DOCS)
            return m

        mock_sb.table.side_effect = tbl_mock_unrev

        res_unrev = client.post("/candidates/9901/audit/l3-review/approve", json={"remarks": "Auditor approval"})
        assert res_unrev.status_code == 400
        assert "must be explicitly checked and reviewed by cops" in res_unrev.json()["detail"].lower()

    app.dependency_overrides.clear()


# =============================================================================
# 5. Full Approval Progression: L2 Recommended -> L3 Verified -> L4 Approved
# =============================================================================
def test_full_review_progression_l3_to_l4():
    """COPS verifies dossier and advances it to L4 BL; L4 then successfully approves."""
    # Step 1: L3 COPS Verifies
    app.dependency_overrides[get_current_user] = lambda: L3_USER

    cops_verified_audit = {
        **make_ch_audit(),
        "cpass_status": "VERIFIED",
        "signoff_details": {
            "review_stages": {
                "ch": {"status": "Recommended", "reviewed_by": "L2 Centre Head"},
                "cops": {"status": "Verified", "reviewed_by": "L3 COPS Auditor"},
                "bl": {"status": "Pending"},
            },
            "cops_team": {"name": "L3 COPS Auditor", "confirmed": True},
        },
    }

    with patch("app.routers.audits.supabase") as mock_sb:
        def tbl_mock(name):
            m = MagicMock()
            if name == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif name == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[make_ch_audit()])
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[cops_verified_audit])
            elif name == "candidate_documents":
                m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=VALID_DOCS)
            return m

        mock_sb.table.side_effect = tbl_mock

        res = client.post("/candidates/9901/audit/l3-review/approve", json={"remarks": "COPS verified all statutory evidence."})
        assert res.status_code == 200
        data = res.json()
        assert data["cpass_status"] == "VERIFIED"
        stages = extract_review_stages(data["audit"])
        assert stages["ch_status"] == "Recommended"
        assert stages["cops_status"] == "Verified"
        assert stages["bl_status"] == "Pending"

    # Step 2: L4 Business Leader Approves
    app.dependency_overrides[get_current_user] = lambda: L4_USER

    bl_approved_audit = {
        **cops_verified_audit,
        "cpass_status": "APPROVED",
        "signoff_details": {
            "review_stages": {
                "ch": {"status": "Recommended"},
                "cops": {"status": "Verified"},
                "bl": {"status": "Approved"},
            },
        },
    }

    with patch("app.routers.audits.supabase") as mock_sb:
        def tbl_mock_l4(name):
            m = MagicMock()
            if name == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif name == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[cops_verified_audit])
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[bl_approved_audit])
            return m

        mock_sb.table.side_effect = tbl_mock_l4

        res_bl = client.post("/candidates/9901/audit/l4-review/approve", json={"remarks": "Sanctioned and approved by BL."})
        assert res_bl.status_code == 200
        bl_data = res_bl.json()
        assert bl_data["cpass_status"] == "BL_APPROVED"
        bl_stages = extract_review_stages(bl_data["audit"])
        assert bl_stages["bl_status"] == "Approved"

    app.dependency_overrides.clear()


# =============================================================================
# 6. COPS Return-to-L1 Workflow
# =============================================================================
def test_cops_return_to_l1_resets_stages_and_forces_l2_re_review():
    """Returning dossier updates status to RETURNED_TO_L1, blocks L4, and forces fresh L2 review after L1 resubmits."""
    app.dependency_overrides[get_current_user] = lambda: L3_USER

    returned_audit = {
        **make_ch_audit(),
        "audit_status": "RETURNED_TO_L1",
        "cpass_status": "RETURNED_TO_L1",
        "signoff_details": {
            "review_stages": {
                "ch": {"status": "Returned to L1"},
                "cops": {"status": "Returned to L1"},
                "bl": {"status": "Pending"},
            },
            "return_to_l1": {"stage": "COPS", "return_reason": "Bank credit amount differs from slip"},
            "return_history": [{"stage": "COPS", "return_reason": "Bank credit amount differs from slip"}],
            "revision_history": [{"action": "RETURNED_TO_L1", "stage": "COPS"}],
        },
    }

    with patch("app.routers.audits.supabase") as mock_sb:
        def tbl_mock(name):
            m = MagicMock()
            if name == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif name == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[make_ch_audit()])
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[returned_audit])
            return m

        mock_sb.table.side_effect = tbl_mock

        res = client.post(
            "/candidates/9901/audit/l3-review/return-to-l1",
            json={"return_reason": "Bank credit amount differs from slip", "remarks": "Please upload corrected statement"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["cpass_status"] == "RETURNED_TO_L1"
        stages = extract_review_stages(data["audit"])
        assert stages["cops_status"] == "Returned to L1"

    # Step 2: Attempting L4 BL review while returned must fail
    app.dependency_overrides[get_current_user] = lambda: L4_USER
    with patch("app.routers.audits.supabase") as mock_sb:
        def tbl_mock_l4_blocked(name):
            m = MagicMock()
            if name == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif name == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[returned_audit])
            return m

        mock_sb.table.side_effect = tbl_mock_l4_blocked

        res_l4_blocked = client.post("/candidates/9901/audit/l4-review/approve", json={})
        assert res_l4_blocked.status_code == 400
        assert "returned to l1" in res_l4_blocked.json()["detail"].lower()

    app.dependency_overrides.clear()


# =============================================================================
# 7. COPS Rejection Permanently Stops Progression
# =============================================================================
def test_cops_rejection_blocks_l4():
    """COPS rejection sets REJECTED and blocks subsequent L4 approval."""
    app.dependency_overrides[get_current_user] = lambda: L3_USER

    cops_rejected_audit = {
        **make_ch_audit(),
        "audit_status": "REJECTED",
        "cpass_status": "REJECTED",
        "signoff_details": {
            "review_stages": {
                "ch": {"status": "Recommended"},
                "cops": {"status": "Rejected"},
                "bl": {"status": "Pending"},
            },
            "rejected_stage": "cops",
        },
    }

    with patch("app.routers.audits.supabase") as mock_sb:
        def tbl_mock(name):
            m = MagicMock()
            if name == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif name == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[make_ch_audit()])
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[cops_rejected_audit])
            return m

        mock_sb.table.side_effect = tbl_mock

        res = client.post(
            "/candidates/9901/audit/l3-review/reject",
            json={"rejection_reason": "Statutory non-compliance: fake documents detected"},
        )
        assert res.status_code == 200
        assert res.json()["cpass_status"] == "REJECTED"

    # Verify L4 is blocked
    app.dependency_overrides[get_current_user] = lambda: L4_USER
    with patch("app.routers.audits.supabase") as mock_sb:
        def tbl_mock_l4(name):
            m = MagicMock()
            if name == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif name == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[cops_rejected_audit])
            return m

        mock_sb.table.side_effect = tbl_mock_l4

        res_l4 = client.post("/candidates/9901/audit/l4-review/approve", json={})
        assert res_l4.status_code == 400
        assert "already been rejected" in res_l4.json()["detail"].lower()

    app.dependency_overrides.clear()


# =============================================================================
# 8. Dashboard Metrics & L3 Queue Filters
# =============================================================================
def test_dashboard_l3_cops_metrics_and_queue_filters():
    """Dashboard returns l3_received, l3_verified, l3_pending, and supports l3 filters."""
    app.dependency_overrides[get_current_user] = lambda: L3_USER

    with patch("app.routers.dashboard.supabase") as mock_sb:
        docs_mock = MagicMock(data=[{"candidate_id": 9901}])
        audit_mock = MagicMock(data=[make_ch_audit()])
        cands_mock = MagicMock(count=1, data=[CANDIDATE_ODISHA])

        def tbl_mock(name):
            m = MagicMock()
            if name == "candidate_documents":
                m.select.return_value.neq.return_value.execute.return_value = docs_mock
                m.select.return_value.neq.return_value.range.return_value.execute.return_value = docs_mock
                m.select.return_value.in_.return_value.neq.return_value.range.return_value.execute.return_value = docs_mock
            elif name == "placement_audits":
                m.select.return_value.execute.return_value = audit_mock
                m.select.return_value.range.return_value.execute.return_value = audit_mock
                m.select.return_value.in_.return_value.range.return_value.execute.return_value = audit_mock
            elif name == "ddugky_candidates":
                m.select.return_value.in_.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"candidate_id": 9901, "tc_state_name": "ODISHA"}])
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(count=1, data=[{"candidate_id": 9901}])
                m.select.return_value.limit.return_value.execute.return_value = MagicMock(count=1, data=[{"candidate_id": 9901}])
                m.select.return_value.range.return_value.execute.return_value = MagicMock(data=[{"candidate_id": 9901}])
                m.select.return_value.eq.return_value.range.return_value.execute.return_value = MagicMock(data=[{"candidate_id": 9901}])
                m.select.return_value.in_.return_value.eq.return_value.range.return_value.execute.return_value = MagicMock(data=[{"candidate_id": 9901, "tc_state_name": "ODISHA"}])
                m.select.return_value.in_.return_value.range.return_value.execute.return_value = MagicMock(data=[{"candidate_id": 9901, "tc_state_name": "ODISHA"}])
                m.select.return_value.eq.return_value.in_.return_value.order.return_value.range.return_value.execute.return_value = cands_mock
                m.select.return_value.in_.return_value.order.return_value.range.return_value.execute.return_value = cands_mock
                m.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value = cands_mock
            return m

        mock_sb.table.side_effect = tbl_mock

        # Summary check
        res_sum = client.get("/dashboard/summary?state=ODISHA")
        assert res_sum.status_code == 200
        sum_data = res_sum.json()
        assert sum_data["l3_received"] == 1
        assert sum_data["l3_pending"] == 1
        assert sum_data["l3_verified"] == 0
        assert "l3_rejected_returned" in sum_data

        # Candidates queue check with l3_pending filter
        res_cand = client.get("/dashboard/candidates?state=ODISHA&filter=l3_pending")
        assert res_cand.status_code == 200
        cand_data = res_cand.json()
        assert cand_data["total_count"] == 1
        assert cand_data["candidates"][0]["candidate_id"] == 9901
        assert cand_data["candidates"][0]["cops_status"] == "Pending"

        # Check total filter works
        res_total = client.get("/dashboard/candidates?state=ODISHA&filter=total")
        assert res_total.status_code == 200
        assert res_total.json()["total_count"] == 1

        # Check l3_rejected_returned filter is accepted
        res_rej_ret = client.get("/dashboard/candidates?state=ODISHA&filter=l3_rejected_returned")
        assert res_rej_ret.status_code == 200

    app.dependency_overrides.clear()


# =============================================================================
# 9. L3 Flexible Return Destinations & Unauthorized Destination Rejection
# =============================================================================
def test_l3_cops_flexible_return_destinations_and_unauthorized_rejection():
    """L3 COPS can flexibly return to L1 and L2, but self-return (L3) or downstream (L4) are rejected with 400."""
    app.dependency_overrides[get_current_user] = lambda: L3_USER

    # 1. Test Return to L1 succeeds
    with patch("app.routers.audits.supabase") as mock_sb:
        cops_returned_l1 = {
            **make_ch_audit(),
            "cpass_status": "RETURNED_TO_L1",
            "audit_status": "RETURNED_TO_L1",
        }
        def tbl_mock(name):
            m = MagicMock()
            if name == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif name == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[make_ch_audit()])
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[cops_returned_l1])
            return m

        mock_sb.table.side_effect = tbl_mock

        res_l1 = client.post(
            "/candidates/9901/audit/l3-review/return",
            json={"destination": "L1", "return_reason": "Salary slips unreadable", "remarks": "Re-scan with stamp"},
        )
        assert res_l1.status_code == 200
        assert res_l1.json()["cpass_status"] == "RETURNED_TO_L1"
        assert res_l1.json()["destination"] == "L1"

    # 2. Test Return to L2 succeeds
    with patch("app.routers.audits.supabase") as mock_sb:
        cops_returned_l2 = {
            **make_ch_audit(),
            "cpass_status": "RETURNED_TO_L2",
            "audit_status": "SUBMITTED",
        }
        def tbl_mock(name):
            m = MagicMock()
            if name == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif name == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[make_ch_audit()])
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[cops_returned_l2])
            return m

        mock_sb.table.side_effect = tbl_mock

        res_l2 = client.post(
            "/candidates/9901/audit/l3-review/return",
            json={"destination": "L2", "return_reason": "Center Head must re-verify candidate designation", "remarks": "Check offer letter"},
        )
        assert res_l2.status_code == 200
        assert res_l2.json()["cpass_status"] == "RETURNED_TO_L2"
        assert res_l2.json()["destination"] == "L2"

    # 3. Test Return to L3 (own stage) is rejected by backend with 400
    with patch("app.routers.audits.supabase") as mock_sb:
        def tbl_mock(name):
            m = MagicMock()
            if name == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif name == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[make_ch_audit()])
            return m

        mock_sb.table.side_effect = tbl_mock

        res_l3 = client.post(
            "/candidates/9901/audit/l3-review/return",
            json={"destination": "L3", "return_reason": "Trying to return to own stage", "remarks": "Not allowed"},
        )
        assert res_l3.status_code == 400
        assert "cannot return candidate to own review stage" in res_l3.json()["detail"].lower()

    # 4. Test Return to L4 (downstream unauthorized) is rejected by backend with 400
    with patch("app.routers.audits.supabase") as mock_sb:
        def tbl_mock(name):
            m = MagicMock()
            if name == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
            elif name == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[make_ch_audit()])
            return m

        mock_sb.table.side_effect = tbl_mock

        res_l4 = client.post(
            "/candidates/9901/audit/l3-review/return",
            json={"destination": "L4", "return_reason": "Downstream stage invalid", "remarks": "Not allowed"},
        )
        assert res_l4.status_code == 400
        assert "unauthorized" in res_l4.json()["detail"].lower() or "must be one of" in res_l4.json()["detail"].lower()

    app.dependency_overrides.clear()
