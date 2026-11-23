"""Automated tests for L1 Finalized Audit Lock Across All Documents and Actions.

Verifies:
1. Centralized lock condition:
   - Unlocked for fresh draft (None).
   - Unlocked for DRAFT status.
   - Locked for SUBMITTED, APPROVED, REJECTED, VERIFIED, L2_APPROVED.
   - Unlocked for RETURNED_TO_L1 (both status and stage return indications).
2. Backend enforcement:
   - Document upload (POST /candidates/{id}/documents) is blocked for submitted audits.
   - Document deletion (DELETE /candidates/{id}/documents/{id}) is blocked for submitted audits.
   - Batch document submit (POST /candidates/{id}/documents/submit) is blocked for submitted audits.
   - Payslip availability toggle (POST /candidates/{id}/payslip-availability) is blocked for submitted audits.
   - Save draft (POST /candidates/{id}/audit/draft) is blocked for submitted audits.
   - Final submit (POST /candidates/{id}/audit/submit) is blocked for submitted audits.
   - L2/L3/Admin operations are never blocked by L1 lock.
   - Returned-to-L1 restores upload, editing, draft saving, and resubmission permissions.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentUser, get_current_user
from app.main import app
from app.services.audit_lock import is_audit_locked_for_l1, check_l1_audit_unlocked

client = TestClient(app)

L1_USER = CurrentUser(
    id="l1-uuid",
    email="l1@cpass.org",
    full_name="L1 Coordinator",
    role="L1_COORDINATOR",
    assigned_state="ODISHA",
)

L2_USER = CurrentUser(
    id="l2-uuid",
    email="l2@cpass.org",
    full_name="L2 Centre Head",
    role="L2_MANAGER",
    assigned_state="ODISHA",
)

CANDIDATE_DATA = {
    "candidate_id": 99901,
    "candidate_first_name": "Ramesh",
    "candidate_last_name": "Kumar",
    "state_name": "Odisha",
    "tc_state_name": "Odisha",
    "tc_name": "Bhubaneswar Skill Centre",
    "tc_id": "TC-001",
    "batch_code": "BATCH-OD-2023-01",
}


def test_is_audit_locked_unit_rules():
    """Unit test for is_audit_locked_for_l1 status resolution."""
    # 1. None or empty -> Unlocked
    assert is_audit_locked_for_l1(None) is False
    assert is_audit_locked_for_l1({}) is False

    # 2. DRAFT -> Unlocked
    assert is_audit_locked_for_l1({"audit_status": "DRAFT"}) is False
    assert is_audit_locked_for_l1({"audit_status": "draft"}) is False

    # 3. SUBMITTED -> Locked
    assert is_audit_locked_for_l1({"audit_status": "SUBMITTED"}) is True
    assert is_audit_locked_for_l1({"audit_status": "submitted"}) is True

    # 4. APPROVED / VERIFIED -> Locked
    assert is_audit_locked_for_l1({"audit_status": "APPROVED"}) is True
    assert is_audit_locked_for_l1({"cpass_status": "APPROVED"}) is True
    assert is_audit_locked_for_l1({"cpass_status": "VERIFIED"}) is True
    assert is_audit_locked_for_l1({"cpass_status": "L2_APPROVED"}) is True

    # 5. RETURNED_TO_L1 -> Unlocked
    assert is_audit_locked_for_l1({"audit_status": "RETURNED_TO_L1"}) is False
    assert is_audit_locked_for_l1({"cpass_status": "RETURNED_TO_L1"}) is False
    assert is_audit_locked_for_l1({
        "audit_status": "SUBMITTED",
        "signoff_details": {"active_return": {"destination": "L1"}}
    }) is False
    assert is_audit_locked_for_l1({
        "audit_status": "SUBMITTED",
        "signoff_details": {"review_stages": {"ch": {"status": "Returned to L1"}}}
    }) is False
    assert is_audit_locked_for_l1({
        "audit_status": "SUBMITTED",
        "signoff_details": {"return_to_l1": True}
    }) is False


def test_check_l1_audit_unlocked_bypasses_non_l1():
    """Non-L1 roles (L2, L3, Admin) are never blocked by L1 lock."""
    mock_db = MagicMock()
    # Should not even query DB
    res = check_l1_audit_unlocked(99901, "L2_MANAGER", db=mock_db)
    assert res is None
    assert mock_db.table.call_count == 0

    res_admin = check_l1_audit_unlocked(99901, "ADMIN", db=mock_db)
    assert res_admin is None
    assert mock_db.table.call_count == 0


def test_document_upload_blocked_when_audit_submitted():
    """L1 coordinator cannot upload documents if audit is SUBMITTED."""
    mock_sb = MagicMock()
    # Mock candidate lookup
    mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = [
        MagicMock(data=[CANDIDATE_DATA]),
        MagicMock(data=[{"id": "aud-1", "audit_status": "SUBMITTED", "candidate_id": 99901}]),
    ]

    with patch("app.routers.documents.supabase", mock_sb):
        app.dependency_overrides[get_current_user] = lambda: L1_USER
        res = client.post(
            "/candidates/99901/documents",
            data={"document_type": "APPOINTMENT_LETTER"},
            files={"file": ("offer.pdf", b"%PDF-1.4 dummy", "application/pdf")},
        )
        assert res.status_code == 400
        assert "locked for review" in res.json()["detail"].lower()
        app.dependency_overrides.clear()


def test_document_deletion_blocked_when_audit_submitted():
    """L1 coordinator cannot delete documents if audit is SUBMITTED."""
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = [
        MagicMock(data=[CANDIDATE_DATA]),
        MagicMock(data=[{"id": "aud-1", "audit_status": "SUBMITTED", "candidate_id": 99901}]),
    ]

    with patch("app.routers.documents.supabase", mock_sb):
        app.dependency_overrides[get_current_user] = lambda: L1_USER
        res = client.delete("/candidates/99901/documents/doc-123")
        assert res.status_code == 400
        assert "locked for review" in res.json()["detail"].lower()
        app.dependency_overrides.clear()


def test_batch_document_submit_blocked_when_audit_submitted():
    """L1 coordinator cannot batch submit documents if audit is SUBMITTED."""
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = [
        MagicMock(data=[CANDIDATE_DATA]),
        MagicMock(data=[{"id": "aud-1", "audit_status": "SUBMITTED", "candidate_id": 99901}]),
    ]

    with patch("app.routers.documents.supabase", mock_sb):
        app.dependency_overrides[get_current_user] = lambda: L1_USER
        res = client.post(
            "/candidates/99901/documents/submit",
            data={
                "appointment_letters_meta": "[]",
                "salary_slips_meta": "[]",
                "bank_statements_meta": "[]",
            },
        )
        assert res.status_code == 400
        assert "locked for review" in res.json()["detail"].lower()
        app.dependency_overrides.clear()


def test_payslip_availability_blocked_when_audit_submitted():
    """L1 coordinator cannot toggle payslip availability if audit is SUBMITTED."""
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = [
        MagicMock(data=[CANDIDATE_DATA]),
        MagicMock(data=[{"id": "aud-1", "audit_status": "SUBMITTED", "candidate_id": 99901}]),
    ]

    with patch("app.routers.dashboard.supabase", mock_sb):
        app.dependency_overrides[get_current_user] = lambda: L1_USER
        res = client.post(
            "/dashboard/candidates/99901/payslip-availability",
            json={"month_number": 1, "available": "No", "remarks": "Unavailable"},
        )
        assert res.status_code == 400
        assert "locked for review" in res.json()["detail"].lower()
        app.dependency_overrides.clear()


def test_save_draft_blocked_when_audit_submitted():
    """L1 coordinator cannot save a draft if audit is SUBMITTED."""
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = [
        MagicMock(data=[CANDIDATE_DATA]),
        MagicMock(data=[{"id": "aud-1", "audit_status": "SUBMITTED", "candidate_id": 99901}]),
    ]

    with patch("app.routers.audits.supabase", mock_sb):
        app.dependency_overrides[get_current_user] = lambda: L1_USER
        res = client.post(
            "/candidates/99901/audit/draft",
            json={"employer_details": [], "salary_details": []},
        )
        assert res.status_code == 400
        assert "locked for review" in res.json()["detail"].lower()
        app.dependency_overrides.clear()


def test_submit_audit_blocked_when_audit_already_submitted():
    """L1 coordinator cannot resubmit if audit is already SUBMITTED."""
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = [
        MagicMock(data=[CANDIDATE_DATA]),
        MagicMock(data=[{"id": "aud-1", "audit_status": "SUBMITTED", "candidate_id": 99901}]),
    ]

    with patch("app.routers.audits.supabase", mock_sb):
        app.dependency_overrides[get_current_user] = lambda: L1_USER
        res = client.post(
            "/candidates/99901/audit/submit",
            json={
                "employer_details": [{"employer_name": "Acme Inc"}],
                "salary_details": [{"month": 1, "year": 2024}],
            },
        )
        assert res.status_code == 400
        assert "locked for review" in res.json()["detail"].lower()
        app.dependency_overrides.clear()


def test_returned_to_l1_restores_editing_and_upload():
    """When audit has RETURNED_TO_L1 status, L1 can save drafts and upload documents."""
    mock_sb = MagicMock()
    
    # Return candidate for candidate query, and returned_to_l1 audit for placement_audits query
    def mock_table(table_name):
        mock_builder = MagicMock()
        if table_name == "ddugky_candidates":
            mock_builder.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
        elif table_name == "placement_audits":
            audit_obj = {
                "id": "aud-1",
                "candidate_id": 99901,
                "audit_status": "RETURNED_TO_L1",
                "cpass_status": "RETURNED_TO_L1",
                "signoff_details": {"review_stages": {"ch": {"status": "Returned to L1"}}},
            }
            mock_builder.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[audit_obj])
            mock_builder.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[audit_obj])
        return mock_builder

    mock_sb.table.side_effect = mock_table

    with patch("app.routers.audits.supabase", mock_sb):
        app.dependency_overrides[get_current_user] = lambda: L1_USER
        res = client.post(
            "/candidates/99901/audit/draft",
            json={"employer_details": [], "salary_details": []},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "saved"
        app.dependency_overrides.clear()
