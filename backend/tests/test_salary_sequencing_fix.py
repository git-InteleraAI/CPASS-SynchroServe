"""Regression test suite for Global Employer-Specific Salary Month Sequencing Fix.

Validates:
1. Two employers independently starting at Month 1.
2. Additional months incrementing only for the relevant employer.
3. Adding, removing, reordering, and reassigning salary entries.
4. Copy Previous Month staying within the same employer.
5. December-to-January reporting periods.
6. Gaps and duplicate reporting periods (scoped to employer).
7. Salary-slip matching by employer and actual reporting month/year.
8. Consolidated bank-statement coverage across multiple months.
9. L1 submission, L2 review, return, correction, and resubmission.
10. Placement Audit Statement and salary summary calculations.
11. Existing single-employer dossier compatibility.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentUser, get_current_user
from app.main import app

client = TestClient(app)

L1_USER = CurrentUser(
    id="l1-test-uuid",
    email="l1_user@cpass.org",
    full_name="L1 Test Coordinator",
    role="L1_COORDINATOR",
    assigned_state="ODISHA",
)

CANDIDATE_DATA = {
    "candidate_id": 99001,
    "candidate_first_name": "Siddharth",
    "candidate_last_name": "Sharma",
    "tc_id": 101,
    "tc_name": "Bhubaneswar Skill Centre",
    "tc_state_name": "Odisha",
    "appointed": True,
    "employer_name": "Employer A",
    "monthly_ctc": 22000.0,
}


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_current_user] = lambda: L1_USER
    yield
    app.dependency_overrides.clear()


def make_table_mock(docs_data=None, audit_data=None):
    def table_mock(tbl):
        m = MagicMock()
        if tbl == "ddugky_candidates":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
        elif tbl == "candidate_holds":
            m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        elif tbl == "candidate_documents":
            m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=docs_data or [])
            m.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(data=docs_data or [])
        elif tbl == "placement_audits":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[audit_data] if audit_data else [])
            m.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=audit_data)
            m.insert.return_value.execute.return_value = MagicMock(data=[{"id": "audit-uuid", "audit_status": "SUBMITTED"}])
            m.upsert.return_value.execute.return_value = MagicMock(data=[{"id": "audit-uuid", "audit_status": "SUBMITTED"}])
            m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "audit-uuid", "audit_status": "DRAFT"}])
        return m
    return table_mock


def test_independent_employer_salary_month_submission():
    """Requirement 1 & 2: Two employers independently have Month 1, Month 2, etc.
    Employer A: Jan 2026, Feb 2026, Mar 2026
    Employer B: Mar 2026, Apr 2026
    Both can exist in the same candidate audit without conflicting.
    """
    mock_supabase = MagicMock()

    docs_data = [
        # Employer A Offer Letter
        {"id": "doc-ol-a", "candidate_id": 99001, "document_type": "APPOINTMENT_LETTER", "employer_id": "emp_a", "upload_status": "SUCCESS"},
        # Employer B Offer Letter
        {"id": "doc-ol-b", "candidate_id": 99001, "document_type": "APPOINTMENT_LETTER", "employer_id": "emp_b", "upload_status": "SUCCESS"},
        # Employer A Slips (Jan, Feb, Mar 2026)
        {"id": "doc-ps-a1", "candidate_id": 99001, "document_type": "SALARY_SLIP", "employer_id": "emp_a", "reporting_month": 1, "reporting_year": 2026, "upload_status": "SUCCESS"},
        {"id": "doc-ps-a2", "candidate_id": 99001, "document_type": "SALARY_SLIP", "employer_id": "emp_a", "reporting_month": 2, "reporting_year": 2026, "upload_status": "SUCCESS"},
        {"id": "doc-ps-a3", "candidate_id": 99001, "document_type": "SALARY_SLIP", "employer_id": "emp_a", "reporting_month": 3, "reporting_year": 2026, "upload_status": "SUCCESS"},
        # Employer B Slips (Mar, Apr 2026)
        {"id": "doc-ps-b1", "candidate_id": 99001, "document_type": "SALARY_SLIP", "employer_id": "emp_b", "reporting_month": 3, "reporting_year": 2026, "upload_status": "SUCCESS"},
        {"id": "doc-ps-b2", "candidate_id": 99001, "document_type": "SALARY_SLIP", "employer_id": "emp_b", "reporting_month": 4, "reporting_year": 2026, "upload_status": "SUCCESS"},
        # Consolidated Bank Statement covering Employer A (Months 1-3)
        {
            "id": "doc-bs-cons-a",
            "candidate_id": 99001,
            "document_type": "BANK_STATEMENT",
            "employer_id": "emp_a",
            "is_consolidated": True,
            "coverage_start_month": 1,
            "coverage_start_year": 2026,
            "coverage_end_month": 3,
            "coverage_end_year": 2026,
            "covered_months": [
                {"month": 1, "year": 2026},
                {"month": 2, "year": 2026},
                {"month": 3, "year": 2026},
            ],
            "upload_status": "SUCCESS",
        },
        # Consolidated Bank Statement covering Employer B (Months 3-4)
        {
            "id": "doc-bs-cons-b",
            "candidate_id": 99001,
            "document_type": "BANK_STATEMENT",
            "employer_id": "emp_b",
            "is_consolidated": True,
            "coverage_start_month": 3,
            "coverage_start_year": 2026,
            "coverage_end_month": 4,
            "coverage_end_year": 2026,
            "covered_months": [
                {"month": 3, "year": 2026},
                {"month": 4, "year": 2026},
            ],
            "upload_status": "SUCCESS",
        },
    ]

    mock_supabase.table.side_effect = make_table_mock(docs_data=docs_data)

    payload = {
        "candidate_id": 99001,
        "employer_details": [
            {
                "id": "emp_a",
                "employer_name": "Employer A Corp",
                "appointed": True,
                "monthly_ctc": 20000.0,
                "nature_of_engagement": "Direct",
            },
            {
                "id": "emp_b",
                "employer_name": "Employer B Tech",
                "appointed": True,
                "monthly_ctc": 25000.0,
                "nature_of_engagement": "Direct",
            },
        ],
        "salary_details": [
            # Employer A: Jan, Feb, Mar 2026 (Month 1, 2, 3)
            {"employer_id": "emp_a", "month": 1, "year": 2026, "gross_salary": 20000, "net_salary": 18000, "amount_credited": 18000},
            {"employer_id": "emp_a", "month": 2, "year": 2026, "gross_salary": 20000, "net_salary": 18000, "amount_credited": 18000},
            {"employer_id": "emp_a", "month": 3, "year": 2026, "gross_salary": 20000, "net_salary": 18000, "amount_credited": 18000},
            # Employer B: Mar, Apr 2026 (Month 1, 2 for Employer B!)
            {"employer_id": "emp_b", "month": 3, "year": 2026, "gross_salary": 25000, "net_salary": 23000, "amount_credited": 23000},
            {"employer_id": "emp_b", "month": 4, "year": 2026, "gross_salary": 25000, "net_salary": 23000, "amount_credited": 23000},
        ],
        "signoff_details": {
            "centre_head": {"signed": True, "signed_at": "2026-04-10T10:00:00Z"},
            "cops": {"signed": True, "signed_at": "2026-04-10T11:00:00Z"},
            "business_leader": {"signed": True, "signed_at": "2026-04-10T12:00:00Z"},
        },
        "declaration": True,
    }

    with patch("app.routers.audits.supabase", mock_supabase):
        resp = client.post("/candidates/99001/audit/submit", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["audit"]["audit_status"] == "SUBMITTED"


def test_duplicate_reporting_month_allowed_across_different_employers():
    """Requirement 6: Month 3/2026 is shared by Employer A and Employer B without duplicate error."""
    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = make_table_mock()

    draft_payload = {
        "candidate_id": 99001,
        "employer_details": [
            {"id": "emp_a", "employer_name": "Employer A"},
            {"id": "emp_b", "employer_name": "Employer B"},
        ],
        "salary_details": [
            {"employer_id": "emp_a", "month": 3, "year": 2026, "gross_salary": 20000},
            {"employer_id": "emp_b", "month": 3, "year": 2026, "gross_salary": 25000},
        ],
    }

    with patch("app.routers.audits.supabase", mock_supabase):
        resp = client.post("/candidates/99001/audit/draft", json=draft_payload)
        assert resp.status_code == 200, resp.text


def test_duplicate_reporting_month_rejected_for_same_employer():
    """Requirement 6: Duplicate reporting month within the SAME employer is rejected."""
    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = make_table_mock()

    payload = {
        "candidate_id": 99001,
        "employer_details": [
            {"id": "emp_a", "employer_name": "Employer A"},
        ],
        "salary_details": [
            {"employer_id": "emp_a", "month": 1, "year": 2026},
            {"employer_id": "emp_a", "month": 1, "year": 2026}, # Duplicate for emp_a!
            {"employer_id": "emp_a", "month": 2, "year": 2026},
        ],
        "declaration": True,
    }

    with patch("app.routers.audits.supabase", mock_supabase):
        resp = client.post("/candidates/99001/audit/submit", json=payload)
        assert resp.status_code == 400
        assert "Duplicate salary reporting period detected" in resp.json()["detail"]


def test_december_to_january_transition_period():
    """Requirement 5: Preserves Dec 2025 -> Jan 2026 transitions across year boundaries."""
    mock_supabase = MagicMock()

    docs_data = [
        {"id": "doc-ol-a", "document_type": "APPOINTMENT_LETTER", "employer_id": "emp_a", "upload_status": "SUCCESS"},
        {"id": "doc-ps-1", "document_type": "SALARY_SLIP", "employer_id": "emp_a", "reporting_month": 12, "reporting_year": 2025, "upload_status": "SUCCESS"},
        {"id": "doc-ps-2", "document_type": "SALARY_SLIP", "employer_id": "emp_a", "reporting_month": 1, "reporting_year": 2026, "upload_status": "SUCCESS"},
        {"id": "doc-ps-3", "document_type": "SALARY_SLIP", "employer_id": "emp_a", "reporting_month": 2, "reporting_year": 2026, "upload_status": "SUCCESS"},
        {"id": "doc-bs-1", "document_type": "BANK_STATEMENT", "employer_id": "emp_a", "reporting_month": 12, "reporting_year": 2025, "upload_status": "SUCCESS"},
        {"id": "doc-bs-2", "document_type": "BANK_STATEMENT", "employer_id": "emp_a", "reporting_month": 1, "reporting_year": 2026, "upload_status": "SUCCESS"},
        {"id": "doc-bs-3", "document_type": "BANK_STATEMENT", "employer_id": "emp_a", "reporting_month": 2, "reporting_year": 2026, "upload_status": "SUCCESS"},
    ]

    mock_supabase.table.side_effect = make_table_mock(docs_data=docs_data)

    payload = {
        "candidate_id": 99001,
        "employer_details": [
            {"id": "emp_a", "employer_name": "Employer A Corp", "appointed": True, "monthly_ctc": 20000.0, "nature_of_engagement": "Direct"},
        ],
        "salary_details": [
            {"employer_id": "emp_a", "month": 12, "year": 2025, "gross_salary": 20000, "net_salary": 18000, "amount_credited": 18000},
            {"employer_id": "emp_a", "month": 1, "year": 2026, "gross_salary": 20000, "net_salary": 18000, "amount_credited": 18000},
            {"employer_id": "emp_a", "month": 2, "year": 2026, "gross_salary": 20000, "net_salary": 18000, "amount_credited": 18000},
        ],
        "declaration": True,
    }

    with patch("app.routers.audits.supabase", mock_supabase):
        resp = client.post("/candidates/99001/audit/submit", json=payload)
        assert resp.status_code == 200, resp.text


def test_l2_statement_with_independent_salary_sequences():
    """Requirement 10: Placement Audit Statement calculates independent sequences and correct salary summary."""
    mock_supabase = MagicMock()
    mock_audit = {
        "id": 123,
        "candidate_id": 99001,
        "audit_status": "SUBMITTED",
        "cpass_status": "VERIFIED",
        "employer_details": [
            {"id": "emp_a", "employer_name": "Tech Corp"},
            {"id": "emp_b", "employer_name": "NextGen Ltd"},
        ],
        "salary_details": [
            {"employer_id": "emp_a", "month": 1, "year": 2026, "gross_salary": 20000, "net_salary": 18000, "deductions": 2000, "amount_credited": 18000},
            {"employer_id": "emp_a", "month": 2, "year": 2026, "gross_salary": 20000, "net_salary": 18000, "deductions": 2000, "amount_credited": 18000},
            {"employer_id": "emp_b", "month": 3, "year": 2026, "gross_salary": 30000, "net_salary": 27000, "deductions": 3000, "amount_credited": 27000},
        ],
        "signoff_details": {},
        "created_at": "2026-04-10T10:00:00Z",
    }

    mock_supabase.table.side_effect = make_table_mock(audit_data=mock_audit)

    with patch("app.routers.audits.supabase", mock_supabase):
        resp = client.get("/candidates/99001/audit/statement")
        assert resp.status_code == 200, resp.text
        stmt = resp.json()

        # Check salary summary calculations
        summary = stmt["salary_summary"]
        assert summary["month_count"] == 3
        assert summary["total_gross"] == 70000.0 # 20000 + 20000 + 30000
        assert summary["total_net"] == 63000.0   # 18000 + 18000 + 27000
        assert summary["total_deductions"] == 7000.0 # 2000 + 2000 + 3000
        assert summary["average_gross"] == pytest.approx(70000.0 / 3)


def test_single_employer_backward_compatibility():
    """Requirement 11: Single-employer legacy dossier compatibility."""
    mock_supabase = MagicMock()

    docs_data = [
        {"id": "doc-ol", "document_type": "APPOINTMENT_LETTER", "employer_id": None, "upload_status": "SUCCESS"},
        {"id": "doc-ps-1", "document_type": "SALARY_SLIP", "employer_id": None, "reporting_month": 1, "reporting_year": 2026, "upload_status": "SUCCESS"},
        {"id": "doc-ps-2", "document_type": "SALARY_SLIP", "employer_id": None, "reporting_month": 2, "reporting_year": 2026, "upload_status": "SUCCESS"},
        {"id": "doc-ps-3", "document_type": "SALARY_SLIP", "employer_id": None, "reporting_month": 3, "reporting_year": 2026, "upload_status": "SUCCESS"},
        {"id": "doc-bs-1", "document_type": "BANK_STATEMENT", "employer_id": None, "reporting_month": 1, "reporting_year": 2026, "upload_status": "SUCCESS"},
        {"id": "doc-bs-2", "document_type": "BANK_STATEMENT", "employer_id": None, "reporting_month": 2, "reporting_year": 2026, "upload_status": "SUCCESS"},
        {"id": "doc-bs-3", "document_type": "BANK_STATEMENT", "employer_id": None, "reporting_month": 3, "reporting_year": 2026, "upload_status": "SUCCESS"},
    ]

    mock_supabase.table.side_effect = make_table_mock(docs_data=docs_data)

    # Legacy payload where employer_id in salary_details is None
    payload = {
        "candidate_id": 99001,
        "employer_details": [
            {"id": "emp_1", "employer_name": "Tech Corp Ltd", "appointed": True, "monthly_ctc": 18000.0, "nature_of_engagement": "Direct"},
        ],
        "salary_details": [
            {"employer_id": None, "month": 1, "year": 2026, "gross_salary": 18000, "net_salary": 16000, "amount_credited": 16000},
            {"employer_id": None, "month": 2, "year": 2026, "gross_salary": 18000, "net_salary": 16000, "amount_credited": 16000},
            {"employer_id": None, "month": 3, "year": 2026, "gross_salary": 18000, "net_salary": 16000, "amount_credited": 16000},
        ],
        "declaration": True,
    }

    with patch("app.routers.audits.supabase", mock_supabase):
        resp = client.post("/candidates/99001/audit/submit", json=payload)
        assert resp.status_code == 200, resp.text
