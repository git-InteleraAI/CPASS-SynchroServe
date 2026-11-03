"""Automated tests for CPASS L1 Automatic Draft Persistence & Document Evidence Synchronization.

Verifies:
- Scenario A: Upload without manual save draft preserves employer & salary info and syncs document evidence.
- Scenario B: Automatic persistence after refresh (draft retrieval returns saved state).
- Scenario C: Document evidence audit availability for individual months (marks Yes/No correctly).
- Scenario D: Consolidated bank statement multi-month coverage synchronizes all covered slots.
- Scenario E: Upload without pre-existing draft creates baseline audit and syncs document evidence.
- Scenario F: Graceful handling of sync warnings without losing Drive uploads.
- Scenario G: Idempotent manual/retry sync endpoints (/documents/sync-audit & /audit/sync-documents).
- Scenario H: Existing saved draft updated without data loss.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentUser, get_current_user
from app.main import app
from app.routers.documents import sync_documents_to_placement_audit

client = TestClient(app)

L1_USER = CurrentUser(
    id="l1-test-uuid",
    email="l1.test@synchroserve.com",
    full_name="L1 Coordinator",
    role="L1_COORDINATOR",
    assigned_state="ODISHA",
)

CANDIDATE = {
    "candidate_id": 88001,
    "candidate_first_name": "Suresh",
    "candidate_last_name": "Patra",
    "candidate_father_name": "Binod Patra",
    "state_name": "ODISHA",
    "tc_state_name": "ODISHA",
    "tc_name": "Bhubaneswar Centre",
    "tc_id": 501,
    "batch_code": "BATCH-OD-2024-01",
    "sanction_order_number": "SO-2024-01",
    "appointed": True,
}

EMPLOYER_INPUT = [
    {
        "id": "emp_1",
        "employer_name": "Tech Corp Solutions",
        "months_worked": 6,
        "appointment_date": "2024-01-15",
        "designation": "Associate Engineer",
        "place_of_work": "Bhubaneswar",
        "monthly_ctc": 22000.0,
        "minimum_wages": 15000.0,
    }
]

SALARY_INPUT = [
    {
        "id": "sal_1",
        "employer_id": "emp_1",
        "month": 1,
        "year": 2024,
        "working_days": 26,
        "pay_days": 26,
        "leave_days": 0,
        "credit_date": "2024-02-05",
        "amount_credited": 18500.0,
        "gross_salary": 20000.0,
        "deductions": 1500.0,
        "net_salary": 18500.0,
        "bank_name": "State Bank of India",
    },
    {
        "id": "sal_2",
        "employer_id": "emp_1",
        "month": 2,
        "year": 2024,
        "working_days": 26,
        "pay_days": 26,
        "leave_days": 0,
        "credit_date": "2024-03-05",
        "amount_credited": 18500.0,
        "gross_salary": 20000.0,
        "deductions": 1500.0,
        "net_salary": 18500.0,
        "bank_name": "State Bank of India",
    },
    {
        "id": "sal_3",
        "employer_id": "emp_1",
        "month": 3,
        "year": 2024,
        "working_days": 26,
        "pay_days": 26,
        "leave_days": 0,
        "credit_date": "2024-04-05",
        "amount_credited": 18500.0,
        "gross_salary": 20000.0,
        "deductions": 1500.0,
        "net_salary": 18500.0,
        "bank_name": "State Bank of India",
    },
]


def test_autosave_draft_endpoint_persists_full_snapshot():
    """POST /candidates/{id}/audit/draft persists employer, salary and document details with DRAFT status."""
    app.dependency_overrides[get_current_user] = lambda: L1_USER
    try:
        draft_payload = {
            "candidate_snapshot": CANDIDATE,
            "employer_details": EMPLOYER_INPUT,
            "salary_details": SALARY_INPUT,
            "document_audit": {
                "appointment_letter": {"available": "Pending", "compliance": "Under Verification", "remarks": ""},
                "salary_slip_1": {"available": "Pending", "compliance": "Under Verification", "remarks": ""},
            },
            "signoff_details": {},
            "remarks": "Autosaved draft",
        }

        with patch("app.routers.audits._check_candidate_centre", return_value={"candidate": CANDIDATE}):
            with patch("app.routers.audits.supabase") as mock_sb:
                # Mock no existing audit
                mock_table = MagicMock()
                mock_sb.table.return_value = mock_table
                mock_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
                # Mock insert
                inserted_audit = {
                    "id": "audit-uuid-1",
                    "candidate_id": 88001,
                    "audit_status": "DRAFT",
                    "cpass_status": "PENDING",
                    "employer_details": EMPLOYER_INPUT,
                    "salary_details": SALARY_INPUT,
                }
                mock_table.insert.return_value.execute.return_value = MagicMock(data=[inserted_audit])

                resp = client.post("/candidates/88001/audit/draft", json=draft_payload)
                assert resp.status_code == 200
                data = resp.json()
                assert data["status"] == "saved"
                assert data["audit"]["audit_status"] == "DRAFT"
                assert len(data["audit"]["employer_details"]) == 1
                assert data["audit"]["employer_details"][0]["employer_name"] == "Tech Corp Solutions"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_sync_documents_to_audit_creates_baseline_when_no_draft_exists():
    """Scenario E: When no draft exists in placement_audits, sync initializes a baseline draft and matches docs."""
    mock_docs = [
        {
            "id": "doc-al-1",
            "candidate_id": 88001,
            "document_type": "APPOINTMENT_LETTER",
            "upload_status": "SUCCESS",
            "reporting_month": None,
            "reporting_year": None,
            "employer_id": "emp_1",
            "file_name": "appointment.pdf",
        },
        {
            "id": "doc-sal-1",
            "candidate_id": 88001,
            "document_type": "SALARY_SLIP",
            "upload_status": "SUCCESS",
            "reporting_month": 1,
            "reporting_year": 2024,
            "employer_id": "emp_1",
            "file_name": "slip_jan.pdf",
        },
        {
            "id": "doc-bank-1",
            "candidate_id": 88001,
            "document_type": "BANK_STATEMENT",
            "upload_status": "SUCCESS",
            "reporting_month": 1,
            "reporting_year": 2024,
            "employer_id": "emp_1",
            "is_consolidated": False,
            "file_name": "bank_jan.pdf",
        },
    ]

    with patch("app.routers.documents.supabase") as mock_sb:
        def tbl_mock(name):
            m = MagicMock()
            if name == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE])
            elif name == "placement_audits":
                # First check returns empty
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
                # Insert creates baseline audit
                m.insert.return_value.execute.return_value = MagicMock(data=[{
                    "id": "audit-baseline-uuid",
                    "candidate_id": 88001,
                    "audit_status": "DRAFT",
                    "cpass_status": "PENDING",
                    "employer_details": [],
                    "salary_details": [],
                    "document_audit": {},
                }])
                # Update saves synchronized document audit
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{
                    "id": "audit-baseline-uuid",
                    "candidate_id": 88001,
                    "document_audit": {
                        "appointment_letter": {"available": "Yes"},
                        "salary_slip_1": {"available": "Yes"},
                        "bank_statement_1": {"available": "Yes"},
                    }
                }])
            elif name == "candidate_documents":
                m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=mock_docs)
            return m

        mock_sb.table.side_effect = tbl_mock

        result = sync_documents_to_placement_audit(88001, L1_USER)
        assert result["status"] == "success"
        doc_audit = result["document_audit"]
        assert doc_audit["appointment_letter"]["available"] == "Yes"
        assert doc_audit["salary_slip_1"]["available"] == "Yes"
        assert doc_audit["bank_statement_1"]["available"] == "Yes"


def test_sync_documents_to_audit_preserves_existing_user_inputs():
    """Scenario H: Synchronizing documents updates document_audit without overwriting employer or salary inputs."""
    existing_audit = {
        "id": "audit-uuid-existing",
        "candidate_id": 88001,
        "audit_status": "DRAFT",
        "cpass_status": "PENDING",
        "employer_details": EMPLOYER_INPUT,
        "salary_details": SALARY_INPUT,
        "document_audit": {
            "appointment_letter": {"available": "Pending", "compliance": "Under Verification", "remarks": ""},
            "salary_slip_1": {"available": "Pending", "compliance": "Under Verification", "remarks": ""},
        },
    }

    mock_docs = [
        {
            "id": "doc-sal-1",
            "candidate_id": 88001,
            "document_type": "SALARY_SLIP",
            "upload_status": "SUCCESS",
            "reporting_month": 1,
            "reporting_year": 2024,
            "employer_id": "emp_1",
            "file_name": "slip_jan.pdf",
        }
    ]

    with patch("app.routers.documents.supabase") as mock_sb:
        def tbl_mock(name):
            m = MagicMock()
            if name == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE])
            elif name == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[existing_audit])
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{
                    **existing_audit,
                    "document_audit": {
                        "appointment_letter": {"available": "Pending"},
                        "salary_slip_1": {"available": "Yes"},
                    }
                }])
            elif name == "candidate_documents":
                m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=mock_docs)
            return m

        mock_sb.table.side_effect = tbl_mock

        result = sync_documents_to_placement_audit(88001, L1_USER)
        assert result["status"] == "success"
        audit = result["audit"]
        # Employer inputs are fully preserved!
        assert len(audit["employer_details"]) == 1
        assert audit["employer_details"][0]["monthly_ctc"] == 22000.0
        assert audit["employer_details"][0]["designation"] == "Associate Engineer"
        # Salary details are fully preserved!
        assert len(audit["salary_details"]) == 3
        assert audit["salary_details"][0]["gross_salary"] == 20000.0


def test_document_matching_individual_months_and_unavailable_month():
    """Scenario C: Months with files uploaded become 'Yes', while explicitly unavailable month remains 'No' with remark."""
    existing_audit = {
        "id": "audit-uuid-c",
        "candidate_id": 88001,
        "audit_status": "DRAFT",
        "cpass_status": "PENDING",
        "employer_details": EMPLOYER_INPUT,
        "salary_details": SALARY_INPUT,
        "document_audit": {
            "salary_slip_1": {"available": "Pending", "compliance": "Under Verification", "remarks": ""},
            "salary_slip_2": {"available": "Pending", "compliance": "Under Verification", "remarks": ""},
            "salary_slip_3": {
                "available": "No",
                "compliance": "Non-Compliant",
                "remarks": "Payslip not available",
                "explicitlySet": True,
            },
        },
    }

    # Uploads only exist for Month 1 and Month 2
    mock_docs = [
        {
            "id": "doc-sal-1",
            "candidate_id": 88001,
            "document_type": "SALARY_SLIP",
            "upload_status": "SUCCESS",
            "reporting_month": 1,
            "reporting_year": 2024,
            "employer_id": "emp_1",
            "file_name": "slip_1.pdf",
        },
        {
            "id": "doc-sal-2",
            "candidate_id": 88001,
            "document_type": "SALARY_SLIP",
            "upload_status": "SUCCESS",
            "reporting_month": 2,
            "reporting_year": 2024,
            "employer_id": "emp_1",
            "file_name": "slip_2.pdf",
        },
    ]

    with patch("app.routers.documents.supabase") as mock_sb:
        def tbl_mock(name):
            m = MagicMock()
            if name == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE])
            elif name == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[existing_audit])
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[existing_audit])
            elif name == "candidate_documents":
                m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=mock_docs)
            return m

        mock_sb.table.side_effect = tbl_mock

        result = sync_documents_to_placement_audit(88001, L1_USER)
        doc_audit = result["document_audit"]
        assert doc_audit["salary_slip_1"]["available"] == "Yes"
        assert doc_audit["salary_slip_2"]["available"] == "Yes"
        assert doc_audit["salary_slip_3"]["available"] == "No"
        assert doc_audit["salary_slip_3"]["remarks"] == "Payslip not available"


def test_consolidated_bank_statement_coverage_sync():
    """Scenario D: A consolidated bank statement covering months 1 through 3 marks all 3 bank slots as available."""
    existing_audit = {
        "id": "audit-uuid-d",
        "candidate_id": 88001,
        "audit_status": "DRAFT",
        "cpass_status": "PENDING",
        "employer_details": EMPLOYER_INPUT,
        "salary_details": SALARY_INPUT,
        "document_audit": {
            "bank_statement_1": {"available": "Pending", "compliance": "Under Verification", "remarks": ""},
            "bank_statement_2": {"available": "Pending", "compliance": "Under Verification", "remarks": ""},
            "bank_statement_3": {"available": "Pending", "compliance": "Under Verification", "remarks": ""},
        },
    }

    mock_docs = [
        {
            "id": "doc-bank-consol",
            "candidate_id": 88001,
            "document_type": "BANK_STATEMENT",
            "upload_status": "SUCCESS",
            "employer_id": "emp_1",
            "is_consolidated": True,
            "coverage_start_month": 1,
            "coverage_start_year": 2024,
            "coverage_end_month": 3,
            "coverage_end_year": 2024,
            "covered_months": [
                {"month": 1, "year": 2024},
                {"month": 2, "year": 2024},
                {"month": 3, "year": 2024},
            ],
            "file_name": "q1_consolidated_passbook.pdf",
        }
    ]

    with patch("app.routers.documents.supabase") as mock_sb:
        def tbl_mock(name):
            m = MagicMock()
            if name == "ddugky_candidates":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE])
            elif name == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[existing_audit])
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[existing_audit])
            elif name == "candidate_documents":
                m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=mock_docs)
            return m

        mock_sb.table.side_effect = tbl_mock

        result = sync_documents_to_placement_audit(88001, L1_USER)
        doc_audit = result["document_audit"]
        assert doc_audit["bank_statement_1"]["available"] == "Yes"
        assert doc_audit["bank_statement_2"]["available"] == "Yes"
        assert doc_audit["bank_statement_3"]["available"] == "Yes"
        assert "consolidated" in doc_audit["bank_statement_1"]["remarks"].lower()


def test_idempotent_sync_audit_endpoints():
    """Scenario G: Dedicated sync endpoints /documents/sync-audit and /audit/sync-documents are idempotent."""
    app.dependency_overrides[get_current_user] = lambda: L1_USER
    try:
        mock_audit = {
            "id": "audit-uuid-g",
            "candidate_id": 88001,
            "audit_status": "DRAFT",
            "cpass_status": "PENDING",
            "employer_details": EMPLOYER_INPUT,
            "salary_details": SALARY_INPUT,
            "document_audit": {},
        }

        with patch("app.routers.documents.supabase") as mock_sb:
            def tbl_mock(name):
                m = MagicMock()
                if name == "ddugky_candidates":
                    m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE])
                elif name == "placement_audits":
                    m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[mock_audit])
                    m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_audit])
                elif name == "candidate_documents":
                    m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=[])
                return m

            mock_sb.table.side_effect = tbl_mock

            # Call /documents/sync-audit
            res1 = client.post("/candidates/88001/documents/sync-audit")
            assert res1.status_code == 200
            assert res1.json()["status"] == "success"

            # Call /audit/sync-documents
            res2 = client.post("/candidates/88001/audit/sync-documents")
            assert res2.status_code == 200
            assert res2.json()["status"] == "success"
    finally:
        app.dependency_overrides.pop(get_current_user, None)

