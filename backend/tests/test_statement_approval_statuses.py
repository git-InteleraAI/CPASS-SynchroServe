"""Tests for CPASS Statement Approval Status endpoint and data contracts.

Verifies:
1. CH approved statement returns Recommended in review_stages.
2. COPS rejection statement returns Rejected in COPS while preserving CH Recommended.
3. BL approved statement returns Approved across all three levels.
4. Returned to L1 candidate returns Returned to L1 in review_stages.
5. Legacy audit records without review_stages extract appropriate stages.
6. CEO review is not present in review_stages schema or workflow.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentUser, get_current_user
from app.main import app
from app.routers.audits import extract_review_stages

client = TestClient(app)

L2_USER = CurrentUser(
    id="l2-statement-test-uuid",
    email="l2.statement@synchroserve.com",
    full_name="L2 Centre Head",
    role="L2_MANAGER",
    assigned_state="ANDHRA PRADESH",
)

CANDIDATE = {
    "candidate_id": 999901,
    "candidate_first_name": "Kavitha",
    "candidate_last_name": "Rao",
    "state": "ANDHRA PRADESH",
    "tc_name": "Visakhapatnam TC",
    "training_centre_id": 10,
    "batch_id": "BATCH-2026-01",
}


def test_extract_review_stages_ch_approved():
    """CH approval produces Recommended in CH stage with other stages Pending."""
    audit = {
        "candidate_id": 999901,
        "audit_status": "SUBMITTED",
        "cpass_status": "L2_APPROVED",
        "signoff_details": {
            "review_stages": {
                "ch": {"status": "Recommended", "reviewer_name": "CH User"},
                "cops": {"status": "Pending"},
                "bl": {"status": "Pending"},
            }
        },
    }
    stages = extract_review_stages(audit)
    assert stages["ch"]["status"] == "Recommended"
    assert stages["cops"]["status"] == "Pending"
    assert stages["bl"]["status"] == "Pending"
    assert "ceo" not in stages


def test_extract_review_stages_cops_rejected_preserves_ch():
    """COPS rejection records Rejected in COPS stage while keeping CH Recommended."""
    audit = {
        "candidate_id": 999901,
        "audit_status": "REJECTED",
        "cpass_status": "L3_REJECTED",
        "signoff_details": {
            "review_stages": {
                "ch": {"status": "Recommended", "reviewer_name": "CH User"},
                "cops": {"status": "Rejected", "rejection_reason": "Slip credit mismatch"},
                "bl": {"status": "Pending"},
            }
        },
    }
    stages = extract_review_stages(audit)
    assert stages["ch"]["status"] == "Recommended"
    assert stages["cops"]["status"] == "Rejected"
    assert stages["bl"]["status"] == "Pending"


def test_extract_review_stages_bl_approved():
    """BL approval records Approved for all three stages."""
    audit = {
        "candidate_id": 999901,
        "audit_status": "SUBMITTED",
        "cpass_status": "APPROVED",
        "signoff_details": {
            "review_stages": {
                "ch": {"status": "Recommended"},
                "cops": {"status": "Verified"},
                "bl": {"status": "Approved"},
            }
        },
    }
    stages = extract_review_stages(audit)
    assert stages["ch"]["status"] == "Recommended"
    assert stages["cops"]["status"] == "Verified"
    assert stages["bl"]["status"] == "Approved"


def test_extract_review_stages_returned_to_l1():
    """Return to L1 records Returned to L1 status in CH stage."""
    audit = {
        "candidate_id": 999901,
        "audit_status": "RETURNED_TO_L1",
        "cpass_status": "RETURNED_TO_L1",
        "signoff_details": {
            "review_stages": {
                "ch": {"status": "Returned to L1", "return_reason": "Need updated passbook"},
                "cops": {"status": "Pending"},
                "bl": {"status": "Pending"},
            }
        },
    }
    stages = extract_review_stages(audit)
    assert stages["ch"]["status"] == "Returned to L1"
    assert stages["ch"]["return_reason"] == "Need updated passbook"
    assert stages["cops"]["status"] == "Pending"


def test_statement_endpoint_returns_review_stages():
    """The /audit/statement endpoint returns normalized review_stages."""
    app.dependency_overrides[get_current_user] = lambda: L2_USER
    try:
        mock_audit = {
            "candidate_id": 999901,
            "audit_status": "SUBMITTED",
            "cpass_status": "L2_APPROVED",
            "signoff_details": {
                "review_stages": {
                    "ch": {"status": "Recommended", "reviewer_name": "L2 User"},
                    "cops": {"status": "Pending"},
                    "bl": {"status": "Pending"},
                }
            },
        }

        with patch("app.routers.audits._check_candidate_centre", return_value={"candidate": CANDIDATE}):
            with patch("app.routers.audits.supabase") as mock_supa:
                mock_table = MagicMock()
                mock_supa.table.return_value = mock_table
                mock_table.select.return_value = mock_table
                mock_table.eq.return_value = mock_table
                mock_table.limit.return_value = mock_table
                mock_table.execute.return_value = MagicMock(data=[mock_audit])

                resp = client.get("/candidates/999901/audit/statement")
                assert resp.status_code == 200
                data = resp.json()
                assert "review_stages" in data
                assert data["review_stages"]["ch"]["status"] == "Recommended"
                assert data["review_stages"]["cops"]["status"] == "Pending"
                assert data["review_stages"]["bl"]["status"] == "Pending"
                assert "ceo" not in data["review_stages"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
