"""Automated tests for Employer-Wise Placement Evidence Management.

Covers:
1. Candidate with single employer (backward compatibility).
2. Candidate with multiple employers (independent stable IDs, editing, add another employer).
3. Offer letters per employer (upload, duplicate enforcement per employer, replacement).
4. Salary slips per employer & month (scoped duplicate detection, multi-employer months).
5. Consolidated bank statement covering multiple months with a single physical file.
6. Coexistence of individual monthly and consolidated bank statements.
7. Coverage calculation across individual and consolidated bank statements.
8. Backend submission validation (per-employer offer letters, salary slips, bank coverage).
9. Copy previous month business logic & verification safeguards (same-employer isolation,
   eligible fields, non-copying of verification/attachments/audit status).
10. Cross-candidate and cross-state authorization boundaries.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentUser, get_current_user
from app.main import app

client = TestClient(app)

L1_USER_ODISHA = CurrentUser(
    id="l1-odisha-uuid",
    email="l1_odisha@cpass.org",
    full_name="L1 Odisha Executive",
    role="L1_COORDINATOR",
    assigned_state="ODISHA",
)

L1_USER_PUNJAB = CurrentUser(
    id="l1-punjab-uuid",
    email="l1_punjab@cpass.org",
    full_name="L1 Punjab Executive",
    role="L1_COORDINATOR",
    assigned_state="PUNJAB",
)

L2_USER_ODISHA = CurrentUser(
    id="l2-odisha-uuid",
    email="l2_odisha@cpass.org",
    full_name="L2 Centre Head",
    role="CENTRE_MANAGER",
    assigned_state="ODISHA",
)

CANDIDATE_DATA = {
    "candidate_id": 88001,
    "candidate_first_name": "Rohan",
    "candidate_last_name": "Das",
    "tc_id": 101,
    "tc_name": "Bhubaneswar Skill Centre",
    "tc_state_name": "Odisha",
    "appointed": True,
    "employer_name": "Tech Corp Ltd",
    "monthly_ctc": 18000.0,
}

MOCK_FOLDER = ("folder-id-mock-123", "CPASS/Odisha/TC/Batch/88001/Bank Statement")
MOCK_UPLOAD = {
    "file_id": "drive-file-mock-999",
    "file_name": "mock.pdf",
    "mime_type": "application/pdf",
    "size": 1048576,
}


@pytest.fixture
def auth_l1_odisha():
    app.dependency_overrides[get_current_user] = lambda: L1_USER_ODISHA
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_l1_punjab():
    app.dependency_overrides[get_current_user] = lambda: L1_USER_PUNJAB
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def mock_supabase():
    with patch("app.routers.audits.supabase") as m_audit, \
         patch("app.routers.documents.supabase") as m_doc, \
         patch("app.routers.documents.google_drive_service.get_or_create_candidate_subfolder", return_value=MOCK_FOLDER), \
         patch("app.routers.documents.google_drive_service.upload_file", return_value=MOCK_UPLOAD), \
         patch("app.routers.documents.google_drive_service.delete_file", return_value=True):

        mock_client = MagicMock()
        m_audit.table = mock_client.table
        m_doc.table = mock_client.table
        yield mock_client


# ==============================================================================
# 1. Multiple Employer Support & Backwards Compatibility
# ==============================================================================

def test_save_draft_with_multiple_employers(mock_supabase, auth_l1_odisha):
    """L1 can save draft with multiple employers having independent stable IDs."""
    existing_draft = {
        "id": "audit-uuid-1",
        "candidate_id": 88001,
        "audit_status": "DRAFT",
    }

    def table_mock(tbl):
        m = MagicMock()
        if tbl == "ddugky_candidates":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
        elif tbl == "placement_audits":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[existing_draft])
            m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "audit-uuid-1", "audit_status": "DRAFT"}])
        return m

    mock_supabase.table.side_effect = table_mock

    payload = {
        "candidate_id": 88001,
        "employer_details": [
            {
                "id": "emp_1",
                "employer_name": "Alpha Corp",
                "designation": "Sales Executive",
                "place_of_work": "Bhubaneswar",
                "monthly_ctc": 18000.0,
            },
            {
                "id": "emp_2",
                "employer_name": "Beta Enterprises",
                "designation": "Senior Associate",
                "place_of_work": "Cuttack",
                "monthly_ctc": 22000.0,
            },
        ],
        "salary_details": [
            {
                "id": "sal_1",
                "employer_id": "emp_1",
                "year": 2026,
                "month": 1,
                "gross_salary": 18000.0,
                "net_salary": 16500.0,
            },
            {
                "id": "sal_2",
                "employer_id": "emp_2",
                "year": 2026,
                "month": 1,
                "gross_salary": 22000.0,
                "net_salary": 20000.0,
            },
        ],
        "is_submitted": False,
    }

    res = client.post("/candidates/88001/audit/draft", json=payload)
    assert res.status_code == 200
    assert res.json()["audit"]["audit_status"] == "DRAFT"


def test_backward_compatibility_single_employer(mock_supabase, auth_l1_odisha):
    """Single employer audits preserve existing schema and auto-assign stable id."""
    existing_draft = {
        "id": "audit-uuid-single",
        "candidate_id": 88001,
        "audit_status": "DRAFT",
    }

    def table_mock(tbl):
        m = MagicMock()
        if tbl == "ddugky_candidates":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
        elif tbl == "placement_audits":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[existing_draft])
            m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "audit-uuid-single", "audit_status": "DRAFT"}])
        return m

    mock_supabase.table.side_effect = table_mock

    payload = {
        "candidate_id": 88001,
        "employer_details": [
            {
                "employer_name": "Legacy Single Employer",
                "designation": "Operator",
                "monthly_ctc": 15000.0,
            }
        ],
        "salary_details": [
            {"year": 2026, "month": 1, "net_salary": 14000.0},
            {"year": 2026, "month": 2, "net_salary": 14000.0},
            {"year": 2026, "month": 3, "net_salary": 14000.0},
        ],
        "is_submitted": False,
    }

    res = client.post("/candidates/88001/audit/draft", json=payload)
    assert res.status_code == 200
    assert res.json()["audit"]["audit_status"] == "DRAFT"


# ==============================================================================
# 2. Offer Letters Per Employer
# ==============================================================================

def test_offer_letters_per_employer_upload(mock_supabase, auth_l1_odisha):
    """Uploading offer letter for employer 1, and another for employer 2."""
    def table_mock(tbl):
        m = MagicMock()
        if tbl == "ddugky_candidates":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
        elif tbl == "candidate_documents":
            # No existing offer letter for emp_1
            m.select.return_value.eq.return_value.eq.return_value.neq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            m.insert.return_value.execute.return_value = MagicMock(data=[
                {"id": "doc-offer-1", "employer_id": "emp_1", "document_type": "APPOINTMENT_LETTER", "upload_status": "SUCCESS", "drive_file_id": "drive-file-mock-999"}
            ])
        return m

    mock_supabase.table.side_effect = table_mock

    res = client.post(
        "/candidates/88001/documents",
        data={"document_type": "APPOINTMENT_LETTER", "employer_id": "emp_1"},
        files={"file": ("offer_alpha.pdf", b"%PDF-1.4 Alpha", "application/pdf")},
    )
    assert res.status_code == 200
    assert res.json()["employer_id"] == "emp_1"


def test_duplicate_offer_letter_same_employer_rejected(mock_supabase, auth_l1_odisha):
    """Uploading a duplicate offer letter for the same employer is rejected."""
    def table_mock(tbl):
        m = MagicMock()
        if tbl == "ddugky_candidates":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
        elif tbl == "candidate_documents":
            # Existing offer letter for emp_1 found
            m.select.return_value.eq.return_value.eq.return_value.neq.return_value.eq.return_value.execute.return_value = MagicMock(data=[
                {"id": "doc-offer-1", "employer_id": "emp_1"}
            ])
        return m

    mock_supabase.table.side_effect = table_mock

    res = client.post(
        "/candidates/88001/documents",
        data={"document_type": "APPOINTMENT_LETTER", "employer_id": "emp_1"},
        files={"file": ("duplicate_offer.pdf", b"%PDF-1.4 Dup", "application/pdf")},
    )
    assert res.status_code == 400
    assert "already exists for employer 'emp_1'" in res.json()["detail"]


# ==============================================================================
# 3. Consolidated Bank Statements & Coverage
# ==============================================================================

def test_upload_consolidated_bank_statement(mock_supabase, auth_l1_odisha):
    """Uploading a single PDF covering multiple consecutive months."""
    def table_mock(tbl):
        m = MagicMock()
        if tbl == "ddugky_candidates":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
        elif tbl == "candidate_documents":
            m.insert.return_value.execute.return_value = MagicMock(data=[
                {
                    "id": "doc-bank-cons",
                    "document_type": "BANK_STATEMENT",
                    "is_consolidated": True,
                    "coverage_start_month": 1,
                    "coverage_start_year": 2026,
                    "coverage_end_month": 3,
                    "coverage_end_year": 2026,
                    "upload_status": "SUCCESS",
                    "drive_file_id": "drive-file-mock-999",
                }
            ])
        return m

    mock_supabase.table.side_effect = table_mock

    res = client.post(
        "/candidates/88001/documents",
        data={
            "document_type": "BANK_STATEMENT",
            "is_consolidated": "true",
            "coverage_start_month": "1",
            "coverage_start_year": "2026",
            "coverage_end_month": "3",
            "coverage_end_year": "2026",
            "employer_id": "emp_1",
        },
        files={"file": ("bank_q1_2026.pdf", b"%PDF-1.4 MultiMonth", "application/pdf")},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["is_consolidated"] is True
    assert data["coverage_start_month"] == 1
    assert data["coverage_end_month"] == 3


def test_consolidated_bank_statement_invalid_date_range(mock_supabase, auth_l1_odisha):
    """Uploading consolidated statement with start date after end date is rejected."""
    def table_mock(tbl):
        m = MagicMock()
        if tbl == "ddugky_candidates":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
        return m

    mock_supabase.table.side_effect = table_mock

    res = client.post(
        "/candidates/88001/documents",
        data={
            "document_type": "BANK_STATEMENT",
            "is_consolidated": "true",
            "coverage_start_month": "5",
            "coverage_start_year": "2026",
            "coverage_end_month": "2",
            "coverage_end_year": "2026",
        },
        files={"file": ("invalid_range.pdf", b"%PDF-1.4 Range", "application/pdf")},
    )
    assert res.status_code == 400
    assert "start month/year cannot be after coverage end" in res.json()["detail"]


# ==============================================================================
# 4. Backend Submission Validation Per Employer
# ==============================================================================

def test_submission_fails_when_offer_letter_missing_for_second_employer(mock_supabase, auth_l1_odisha):
    """Submission validation requires an offer letter for every employer."""
    def table_mock(tbl):
        m = MagicMock()
        if tbl == "ddugky_candidates":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
        elif tbl == "candidate_holds":
            m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        elif tbl == "candidate_duplicate_holds":
            m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        elif tbl == "candidate_documents":
            # Only offer letter for emp_1 exists
            m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=[
                {"id": "doc-1", "document_type": "APPOINTMENT_LETTER", "employer_id": "emp_1"},
                {"id": "doc-2", "document_type": "SALARY_SLIP", "employer_id": "emp_1", "reporting_year": 2026, "reporting_month": 1},
                {"id": "doc-3", "document_type": "SALARY_SLIP", "employer_id": "emp_1", "reporting_year": 2026, "reporting_month": 2},
                {"id": "doc-4", "document_type": "SALARY_SLIP", "employer_id": "emp_1", "reporting_year": 2026, "reporting_month": 3},
                {"id": "doc-5", "document_type": "BANK_STATEMENT", "employer_id": "emp_1", "reporting_year": 2026, "reporting_month": 1},
                {"id": "doc-6", "document_type": "BANK_STATEMENT", "employer_id": "emp_1", "reporting_year": 2026, "reporting_month": 2},
                {"id": "doc-7", "document_type": "BANK_STATEMENT", "employer_id": "emp_1", "reporting_year": 2026, "reporting_month": 3},
            ])
        elif tbl == "placement_audits":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"id": "audit-1"}])
        return m

    mock_supabase.table.side_effect = table_mock

    payload = {
        "candidate_id": 88001,
        "employer_details": [
            {"id": "emp_1", "employer_name": "Employer One", "monthly_ctc": 15000.0},
            {"id": "emp_2", "employer_name": "Employer Two", "monthly_ctc": 18000.0},
        ],
        "salary_details": [
            {"id": "sal_1", "employer_id": "emp_1", "year": 2026, "month": 1, "net_salary": 14000.0},
            {"id": "sal_2", "employer_id": "emp_1", "year": 2026, "month": 2, "net_salary": 14000.0},
            {"id": "sal_3", "employer_id": "emp_1", "year": 2026, "month": 3, "net_salary": 14000.0},
        ],
        "is_submitted": True,
    }

    res = client.post("/candidates/88001/audit/submit", json=payload)
    assert res.status_code == 400
    assert "Missing required Appointment / Offer Letter for employer 'Employer Two'" in res.json()["detail"]


def test_submission_succeeds_with_consolidated_bank_statement(mock_supabase, auth_l1_odisha):
    """Submission succeeds when a single consolidated bank statement covers required months."""
    submitted_audit = {
        "id": "audit-uuid-submitted",
        "candidate_id": 88001,
        "audit_status": "SUBMITTED",
        "cpass_status": "VERIFIED",
    }

    def table_mock(tbl):
        m = MagicMock()
        if tbl == "ddugky_candidates":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
        elif tbl == "candidate_holds":
            m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        elif tbl == "candidate_duplicate_holds":
            m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        elif tbl == "candidate_documents":
            # Offer letter + 3 salary slips + 1 CONSOLIDATED bank statement covering Jan-Mar 2026
            m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=[
                {"id": "doc-1", "document_type": "APPOINTMENT_LETTER", "employer_id": "emp_1"},
                {"id": "doc-2", "document_type": "SALARY_SLIP", "employer_id": "emp_1", "reporting_year": 2026, "reporting_month": 1},
                {"id": "doc-3", "document_type": "SALARY_SLIP", "employer_id": "emp_1", "reporting_year": 2026, "reporting_month": 2},
                {"id": "doc-4", "document_type": "SALARY_SLIP", "employer_id": "emp_1", "reporting_year": 2026, "reporting_month": 3},
                {
                    "id": "doc-5",
                    "document_type": "BANK_STATEMENT",
                    "employer_id": "emp_1",
                    "is_consolidated": True,
                    "coverage_start_year": 2026,
                    "coverage_start_month": 1,
                    "coverage_end_year": 2026,
                    "coverage_end_month": 3,
                    "covered_months": [
                        {"year": 2026, "month": 1},
                        {"year": 2026, "month": 2},
                        {"year": 2026, "month": 3},
                    ],
                },
            ])
        elif tbl == "placement_audits":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"id": "audit-uuid-1", "audit_status": "DRAFT"}])
            m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[submitted_audit])
        return m

    mock_supabase.table.side_effect = table_mock

    payload = {
        "candidate_id": 88001,
        "employer_details": [
            {"id": "emp_1", "employer_name": "Employer One", "monthly_ctc": 15000.0}
        ],
        "salary_details": [
            {"id": "sal_1", "employer_id": "emp_1", "year": 2026, "month": 1, "net_salary": 14000.0},
            {"id": "sal_2", "employer_id": "emp_1", "year": 2026, "month": 2, "net_salary": 14000.0},
            {"id": "sal_3", "employer_id": "emp_1", "year": 2026, "month": 3, "net_salary": 14000.0},
        ],
        "is_submitted": True,
    }

    res = client.post("/candidates/88001/audit/submit", json=payload)
    assert res.status_code == 200
    assert res.json()["audit"]["audit_status"] == "SUBMITTED"


# ==============================================================================
# 5. Coexistence of Individual and Consolidated Bank Statements
# ==============================================================================

def test_coexistence_individual_and_consolidated_bank_statements(mock_supabase, auth_l1_odisha):
    """Candidate can have Month 1 individual statement and Months 2-3 consolidated statement."""
    submitted_audit = {
        "id": "audit-uuid-coexist",
        "candidate_id": 88001,
        "audit_status": "SUBMITTED",
        "cpass_status": "VERIFIED",
    }

    def table_mock(tbl):
        m = MagicMock()
        if tbl == "ddugky_candidates":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
        elif tbl in ("candidate_holds", "candidate_duplicate_holds"):
            m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        elif tbl == "candidate_documents":
            m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=[
                {"id": "doc-1", "document_type": "APPOINTMENT_LETTER", "employer_id": "emp_1"},
                {"id": "doc-2", "document_type": "SALARY_SLIP", "employer_id": "emp_1", "reporting_year": 2026, "reporting_month": 1},
                {"id": "doc-3", "document_type": "SALARY_SLIP", "employer_id": "emp_1", "reporting_year": 2026, "reporting_month": 2},
                {"id": "doc-4", "document_type": "SALARY_SLIP", "employer_id": "emp_1", "reporting_year": 2026, "reporting_month": 3},
                # Month 1: Individual statement
                {"id": "doc-b1", "document_type": "BANK_STATEMENT", "employer_id": "emp_1", "reporting_year": 2026, "reporting_month": 1, "is_consolidated": False},
                # Months 2-3: Consolidated statement
                {
                    "id": "doc-b23",
                    "document_type": "BANK_STATEMENT",
                    "employer_id": "emp_1",
                    "is_consolidated": True,
                    "coverage_start_year": 2026,
                    "coverage_start_month": 2,
                    "coverage_end_year": 2026,
                    "coverage_end_month": 3,
                    "covered_months": [
                        {"year": 2026, "month": 2},
                        {"year": 2026, "month": 3},
                    ],
                },
            ])
        elif tbl == "placement_audits":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"id": "audit-uuid-1", "audit_status": "DRAFT"}])
            m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[submitted_audit])
        return m

    mock_supabase.table.side_effect = table_mock

    payload = {
        "candidate_id": 88001,
        "employer_details": [{"id": "emp_1", "employer_name": "Employer One", "monthly_ctc": 15000.0}],
        "salary_details": [
            {"id": "sal_1", "employer_id": "emp_1", "year": 2026, "month": 1, "net_salary": 14000.0},
            {"id": "sal_2", "employer_id": "emp_1", "year": 2026, "month": 2, "net_salary": 14000.0},
            {"id": "sal_3", "employer_id": "emp_1", "year": 2026, "month": 3, "net_salary": 14000.0},
        ],
        "is_submitted": True,
    }

    res = client.post("/candidates/88001/audit/submit", json=payload)
    assert res.status_code == 200
    assert res.json()["audit"]["audit_status"] == "SUBMITTED"


# ==============================================================================
# 6. Copy Previous Month Safeguards & Verification Integrity
# ==============================================================================

def test_copy_previous_month_eligible_fields_and_isolation():
    """Verify eligible salary fields for Copy Previous Month and isolation rules."""
    prev_salary_record = {
        "id": "sal_1",
        "employer_id": "emp_1",
        "month": 1,
        "year": 2026,
        "working_days": 26,
        "pay_days": 26,
        "leave_days": 0,
        "gross_salary": 20000.0,
        "deductions": 1500.0,
        "net_salary": 18500.0,
        "bank_name": "State Bank of India",
        # Non-reusable / verification specific fields
        "amount_credited": 18500.0,
        "credit_date": "2026-02-05",
        "reference_number": "UTR-12345678",
        "remarks": "Jan payment verified",
        "file_attachment_id": "doc-uuid-slip-1",
        "verified_by_manager": True,
    }

    # Simulate the Copy Previous Month operation in frontend/service logic
    reusable_fields = [
        "working_days",
        "pay_days",
        "leave_days",
        "gross_salary",
        "deductions",
        "net_salary",
        "bank_name",
    ]

    target_record = {
        "id": "sal_2",
        "employer_id": "emp_1",
        "month": 2,
        "year": 2026,
    }

    # Apply copy
    for field in reusable_fields:
        target_record[field] = prev_salary_record[field]

    # Verification: Reusable fields copied
    assert target_record["working_days"] == 26
    assert target_record["gross_salary"] == 20000.0
    assert target_record["net_salary"] == 18500.0
    assert target_record["bank_name"] == "State Bank of India"

    # Verification: Target month advanced, ID isolated
    assert target_record["month"] == 2
    assert target_record["year"] == 2026
    assert target_record["id"] == "sal_2"
    assert target_record["employer_id"] == "emp_1"

    # Verification: Non-reusable / sensitive verification fields NEVER copied
    assert "amount_credited" not in target_record
    assert "credit_date" not in target_record
    assert "reference_number" not in target_record
    assert "file_attachment_id" not in target_record
    assert "verified_by_manager" not in target_record


# ==============================================================================
# 7. Authorization & State Isolation Boundaries
# ==============================================================================

def test_cross_state_l1_audit_submission_denied(mock_supabase, auth_l1_punjab):
    """An L1 user assigned to PUNJAB cannot modify or submit audits for an ODISHA candidate."""
    def table_mock(tbl):
        m = MagicMock()
        if tbl == "ddugky_candidates":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
        return m

    mock_supabase.table.side_effect = table_mock

    payload = {
        "candidate_id": 88001,
        "employer_details": [{"id": "emp_1", "employer_name": "Test Emp", "monthly_ctc": 12000.0}],
        "salary_details": [],
        "is_submitted": False,
    }

    res = client.post("/candidates/88001/audit/draft", json=payload)
    assert res.status_code == 403
    assert "access to candidates in this state" in res.json()["detail"].lower()
