"""Automated tests for L1 Placement Audit Statement endpoints.

Covers:
- Authentication & authorization on audit routes.
- Candidate centre permission scoping.
- Fetching nonexistent audit (graceful null response).
- Saving and updating draft placement audits (single record preserved).
- Mandatory validations on submission (employers, salary entries, duplicate periods).
- Successful audit submission & finalization timestamp.
- Blocking draft edits on already submitted audits for L1.
- Compiled statement payload generation with calculated salary totals.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentUser, get_current_user
from app.main import app

client = TestClient(app)

L1_USER = CurrentUser(
    id="l1-coordinator-uuid",
    email="l1@cpass.org",
    full_name="Ananya Sharma",
    role="L1_COORDINATOR",
    assigned_state="ODISHA",
)


ADMIN_USER = CurrentUser(
    id="admin-uuid",
    email="admin@cpass.org",
    full_name="Admin User",
    role="ADMIN",
)

CANDIDATE_DATA = {
    "candidate_id": 10482,
    "candidate_first_name": "Rajesh",
    "candidate_last_name": "Patel",
    "candidate_father_name": "Mohan Patel",
    "date_of_birth": "2000-05-15",
    "mobile_number": "9876543210",
    "gender": "MALE",
    "category": "OBC",
    "tc_id": 101,
    "tc_name": "Bhubaneswar Skill Centre",
    "tc_state_name": "Odisha",
    "batch_code": "BATCH-OD-2023-01",
    "sanction_order_number": "SO-2023-99",
    "trade_name": "Retail Sales Associate",
    "sector": "Retail",
    "appointed": True,
    "employer_name": "Reliance Retail Ltd",
    "monthly_ctc": 16500.0,
}


@pytest.fixture
def mock_supabase():
    with patch("app.routers.audits.supabase") as mock_sb:
        yield mock_sb


@pytest.fixture
def auth_override():
    app.dependency_overrides[get_current_user] = lambda: L1_USER
    yield
    app.dependency_overrides.clear()


def test_unauthenticated_audit_request_rejected():
    """Unauthenticated access to audit endpoints returns 401."""
    res = client.get("/candidates/10482/audit")
    assert res.status_code == 401


def test_get_nonexistent_audit(auth_override, mock_supabase):
    """Retrieving nonexistent audit returns exists=False and audit=None."""
    def table_mock(tbl_name):
        mock_tbl = MagicMock()
        if tbl_name == "ddugky_candidates":
            mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
        elif tbl_name == "placement_audits":
            mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        return mock_tbl

    mock_supabase.table.side_effect = table_mock

    res = client.get("/candidates/10482/audit")
    assert res.status_code == 200
    assert res.json() == {"exists": False, "audit": None}


def test_save_audit_draft_creates_single_record(auth_override, mock_supabase):
    """Saving an initial draft creates a record with audit_status DRAFT."""
    created_audit = {
        "id": "audit-uuid-1",
        "candidate_id": 10482,
        "audit_status": "DRAFT",
        "cpass_status": "PENDING",
        "employer_details": [{"employer_name": "Reliance Retail Ltd", "monthly_ctc": 16500}],
        "salary_details": [],
        "document_audit": {},
        "signoff_details": {},
        "created_by": L1_USER.id,
    }

    def table_mock(tbl_name):
        mock_tbl = MagicMock()
        if tbl_name == "ddugky_candidates":
            mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
        elif tbl_name == "placement_audits":
            mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            mock_tbl.insert.return_value.execute.return_value = MagicMock(data=[created_audit])
        return mock_tbl

    mock_supabase.table.side_effect = table_mock

    payload = {
        "employer_details": [{"employer_name": "Reliance Retail Ltd", "monthly_ctc": 16500}],
        "salary_details": [],
        "remarks": "Draft created by coordinator",
    }

    res = client.post("/candidates/10482/audit/draft", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["message"] == "Draft audit saved successfully"
    assert data["audit"]["audit_status"] == "DRAFT"
    assert data["audit"]["candidate_id"] == 10482


def test_save_audit_draft_updates_existing_record(auth_override, mock_supabase):
    """Saving an updated draft modifies the existing record ID without duplicates."""
    existing_audit = {
        "id": "audit-uuid-1",
        "candidate_id": 10482,
        "audit_status": "DRAFT",
        "employer_details": [{"employer_name": "Reliance Retail Ltd"}],
        "created_by": L1_USER.id,
    }

    updated_audit = {
        **existing_audit,
        "remarks": "Updated second revision",
    }

    def table_mock(tbl_name):
        mock_tbl = MagicMock()
        if tbl_name == "ddugky_candidates":
            mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
        elif tbl_name == "placement_audits":
            mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[existing_audit])
            mock_tbl.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[updated_audit])
        return mock_tbl

    mock_supabase.table.side_effect = table_mock

    payload = {
        "employer_details": [{"employer_name": "Reliance Retail Ltd"}],
        "remarks": "Updated second revision",
    }

    res = client.post("/candidates/10482/audit/draft", json=payload)
    assert res.status_code == 200
    assert res.json()["audit"]["id"] == "audit-uuid-1"
    assert res.json()["audit"]["remarks"] == "Updated second revision"


def test_submit_audit_requires_employer(auth_override, mock_supabase):
    """Submitting an audit without employer details fails validation with 400."""
    def table_mock(tbl_name):
        mock_tbl = MagicMock()
        if tbl_name == "ddugky_candidates":
            mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
        elif tbl_name == "candidate_holds":
            mock_tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        return mock_tbl

    mock_supabase.table.side_effect = table_mock

    payload = {
        "employer_details": [],
        "salary_details": [
            {"month": 1, "year": 2024, "amount_credited": 15000},
            {"month": 2, "year": 2024, "amount_credited": 15000},
            {"month": 3, "year": 2024, "amount_credited": 15000},
        ],
    }

    res = client.post("/candidates/10482/audit/submit", json=payload)
    assert res.status_code == 400
    assert "At least one employer entry is required" in res.json()["detail"]


def test_submit_audit_requires_min_3_salary_months(auth_override, mock_supabase):
    """Submitting an audit with less than 3 salary months fails validation with 400."""
    def table_mock(tbl_name):
        mock_tbl = MagicMock()
        if tbl_name == "ddugky_candidates":
            mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
        elif tbl_name == "candidate_holds":
            mock_tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        return mock_tbl

    mock_supabase.table.side_effect = table_mock

    payload = {
        "employer_details": [{"employer_name": "Reliance Retail Ltd"}],
        "salary_details": [
            {"month": 1, "year": 2024, "amount_credited": 15000},
            {"month": 2, "year": 2024, "amount_credited": 15000},
        ],
    }

    res = client.post("/candidates/10482/audit/submit", json=payload)
    assert res.status_code == 400
    assert "At least 3 distinct reporting months of salary details are required" in res.json()["detail"]


def test_submit_audit_duplicate_salary_period_rejected(auth_override, mock_supabase):
    """Submitting an audit with duplicate salary periods fails validation with 400."""
    def table_mock(tbl_name):
        mock_tbl = MagicMock()
        if tbl_name == "ddugky_candidates":
            mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
        elif tbl_name == "candidate_holds":
            mock_tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        return mock_tbl

    mock_supabase.table.side_effect = table_mock

    payload = {
        "employer_details": [{"employer_name": "Reliance Retail Ltd"}],
        "salary_details": [
            {"month": 1, "year": 2024, "amount_credited": 15000},
            {"month": 1, "year": 2024, "amount_credited": 15000}, # duplicate month
            {"month": 2, "year": 2024, "amount_credited": 15000},
        ],
    }

    res = client.post("/candidates/10482/audit/submit", json=payload)
    assert res.status_code == 400
    assert "Duplicate salary reporting period detected" in res.json()["detail"]


def test_submit_audit_success(auth_override, mock_supabase):
    """Full valid submission transitions status to SUBMITTED and stamps finalization."""
    existing_draft = {
        "id": "audit-uuid-1",
        "candidate_id": 10482,
        "audit_status": "DRAFT",
    }

    submitted_record = {
        **existing_draft,
        "audit_status": "SUBMITTED",
        "cpass_status": "VERIFIED",
        "finalized_at": "2024-05-15T10:00:00Z",
    }

    def table_mock(tbl_name):
        mock_tbl = MagicMock()
        if tbl_name == "ddugky_candidates":
            mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
        elif tbl_name == "candidate_holds":
            mock_tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        elif tbl_name == "placement_audits":
            mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[existing_draft])
            mock_tbl.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[submitted_record])
        return mock_tbl

    mock_supabase.table.side_effect = table_mock

    payload = {
        "employer_details": [{"employer_name": "Reliance Retail Ltd", "monthly_ctc": 16500}],
        "salary_details": [
            {"month": 1, "year": 2024, "amount_credited": 15000, "gross_salary": 16500, "net_salary": 15000},
            {"month": 2, "year": 2024, "amount_credited": 15000, "gross_salary": 16500, "net_salary": 15000},
            {"month": 3, "year": 2024, "amount_credited": 15000, "gross_salary": 16500, "net_salary": 15000},
        ],
        "document_audit": {
            "appointment_letter_status": "Verified in Drive",
            "appointment_letter_compliant": True,
            "salary_slips_status": "3 months verified",
            "salary_slips_compliant": True,
            "bank_statements_status": "3 months verified",
            "bank_statements_compliant": True,
            "overall_compliance": True,
        },
        "signoff_details": {
            "centre_head": {"name": "Sunil Mohanty", "designation": "Centre Manager", "date": "2024-05-15", "confirmed": True},
            "cops_team": {"name": "Pooja Verma", "designation": "Quality Lead", "date": "2024-05-15", "confirmed": True},
            "business_leader": {"name": "Amit Saxena", "designation": "State Head", "date": "2024-05-15", "confirmed": True},
        },
    }

    res = client.post("/candidates/10482/audit/submit", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["message"] == "Placement Audit Statement submitted successfully"
    assert data["audit"]["audit_status"] == "SUBMITTED"
    assert data["audit"]["cpass_status"] == "VERIFIED"


def test_editing_submitted_audit_as_l1_blocked(auth_override, mock_supabase):
    """Ordinary L1 draft edits are blocked once an audit is already SUBMITTED."""
    submitted_audit = {
        "id": "audit-uuid-1",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
    }

    def table_mock(tbl_name):
        mock_tbl = MagicMock()
        if tbl_name == "ddugky_candidates":
            mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
        elif tbl_name == "placement_audits":
            mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[submitted_audit])
        return mock_tbl

    mock_supabase.table.side_effect = table_mock

    payload = {
        "employer_details": [{"employer_name": "New Company"}],
    }

    res = client.post("/candidates/10482/audit/draft", json=payload)
    assert res.status_code == 400
    assert "already been finalized/submitted" in res.json()["detail"]


def test_get_audit_statement_payload_with_salary_totals(auth_override, mock_supabase):
    """GET /statement returns compiled payload with accurate calculated salary totals."""
    mock_audit = {
        "id": "audit-uuid-1",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "salary_details": [
            {"month": 1, "year": 2024, "gross_salary": 18000, "deductions": 1500, "net_salary": 16500, "amount_credited": 16500},
            {"month": 2, "year": 2024, "gross_salary": 18000, "deductions": 1500, "net_salary": 16500, "amount_credited": 16500},
            {"month": 3, "year": 2024, "gross_salary": 18000, "deductions": 1500, "net_salary": 16500, "amount_credited": 16500},
        ],
        "employer_details": [{"employer_name": "Reliance Retail Ltd"}],
    }

    mock_docs = [
        {"id": "doc-1", "document_type": "APPOINTMENT_LETTER", "file_name": "offer.pdf", "upload_status": "SUCCESS"},
        {"id": "doc-2", "document_type": "SALARY_SLIP", "file_name": "pay_m1.pdf", "upload_status": "SUCCESS"},
    ]

    def table_mock(tbl_name):
        mock_tbl = MagicMock()
        if tbl_name == "ddugky_candidates":
            mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
        elif tbl_name == "placement_audits":
            mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[mock_audit])
        elif tbl_name == "candidate_documents":
            mock_tbl.select.return_value.eq.return_value.neq.return_value.order.return_value.execute.return_value = MagicMock(data=mock_docs)
        return mock_tbl

    mock_supabase.table.side_effect = table_mock

    res = client.get("/candidates/10482/audit/statement")
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "C-PASS Candidate Placement Audit & Sign-off Statement"
    assert data["candidate"]["full_name"] == "Rajesh Patel"
    assert data["candidate"]["candidate_name"] == "Rajesh Patel"
    assert data["salary_summary"]["total_gross"] == 54000.0
    assert data["salary_summary"]["total_deductions"] == 4500.0
    assert data["salary_summary"]["total_net"] == 49500.0
    assert data["salary_summary"]["total_credited"] == 49500.0
    assert data["salary_summary"]["average_monthly_gross"] == 18000.0
    assert data["salary_summary"]["months_count"] == 3
    assert data["salary_summary"]["month_count"] == 3
    assert len(data["employer_details"]) == 1
    assert len(data["salary_details"]) == 3


def test_candidate_dossier_mapping_and_aadhaar_masking(auth_override, mock_supabase):
    """Candidate dossier maps all training fields and masks Aadhaar securely."""
    cand_with_aadhaar = {
        **CANDIDATE_DATA,
        "aadhar": "987654321098",
        "trade_name": "Retail Sales Associate",
        "tc_name": "Bhubaneswar Skill Centre",
    }

    def table_mock(tbl_name):
        mock_tbl = MagicMock()
        if tbl_name == "ddugky_candidates":
            mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[cand_with_aadhaar])
        elif tbl_name == "placement_audits":
            mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        elif tbl_name == "candidate_documents":
            mock_tbl.select.return_value.eq.return_value.neq.return_value.order.return_value.execute.return_value = MagicMock(data=[])
        return mock_tbl

    mock_supabase.table.side_effect = table_mock

    res = client.get("/candidates/10482/audit/statement")
    assert res.status_code == 200
    data = res.json()
    cand = data["candidate"]
    assert cand["candidate_name"] == "Rajesh Patel"
    assert cand["father_name"] == "Mohan Patel"
    assert cand["training_centre"] == "Bhubaneswar Skill Centre"
    assert cand["trade_name"] == "Retail Sales Associate"
    assert cand["state"] == "Odisha"
    assert cand["batch_code"] == "BATCH-OD-2023-01"
    assert cand["contact_number"] == "9876543210"
    assert cand["masked_aadhaar"] == "XXXX-XXXX-1098"
    assert cand["aadhaar_last4"] == "1098"
    # Ensure full Aadhaar is NEVER exposed
    assert "987654321098" not in str(cand)


def test_document_evidence_cross_verification_matching(auth_override, mock_supabase):
    """Document evidence accurately matches existing Drive records and marks missing ones unavailable."""
    mock_audit = {
        "id": "audit-uuid-1",
        "candidate_id": 10482,
        "audit_status": "DRAFT",
        "salary_details": [
            {"month": 1, "year": 2026, "gross_salary": 18000, "amount_credited": 16500},
            {"month": 2, "year": 2026, "gross_salary": 18000, "amount_credited": 16500},
            {"month": 3, "year": 2026, "gross_salary": 18000, "amount_credited": 16500},
        ],
        "employer_details": [{"employer_name": "ABC Corp", "monthly_ctc": 18000}],
    }

    # Appointment letter and 3 salary slips exist, but bank statements are missing
    mock_docs = [
        {"id": "doc-1", "document_type": "APPOINTMENT_LETTER", "file_name": "appointment_letter.pdf", "upload_status": "SUCCESS"},
        {"id": "doc-2", "document_type": "SALARY_SLIP", "reporting_month": 1, "reporting_year": 2026, "file_name": "slip_m1.pdf", "upload_status": "SUCCESS"},
        {"id": "doc-3", "document_type": "SALARY_SLIP", "reporting_month": 2, "reporting_year": 2026, "file_name": "slip_m2.pdf", "upload_status": "SUCCESS"},
        {"id": "doc-4", "document_type": "SALARY_SLIP", "reporting_month": 3, "reporting_year": 2026, "file_name": "slip_m3.pdf", "upload_status": "SUCCESS"},
    ]

    def table_mock(tbl_name):
        mock_tbl = MagicMock()
        if tbl_name == "ddugky_candidates":
            mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
        elif tbl_name == "placement_audits":
            mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[mock_audit])
        elif tbl_name == "candidate_documents":
            mock_tbl.select.return_value.eq.return_value.neq.return_value.order.return_value.execute.return_value = MagicMock(data=mock_docs)
        return mock_tbl

    mock_supabase.table.side_effect = table_mock

    res = client.get("/candidates/10482/audit/statement")
    assert res.status_code == 200
    data = res.json()
    evidence = {item["code"]: item for item in data["document_evidence"]}

    # Appointment letter must be available and compliant
    assert evidence["AL / OL"]["available"] is True
    assert evidence["AL / OL"]["compliance"] == "Compliant"
    assert "Stored in Drive: appointment_letter.pdf" in evidence["AL / OL"]["repository_status"]

    # All 3 salary slips must be available
    assert evidence["PS 1"]["available"] is True
    assert evidence["PS 2"]["available"] is True
    assert evidence["PS 3"]["available"] is True
    assert "slip_m1.pdf" in evidence["PS 1"]["repository_status"]

    # Bank statements must remain missing
    assert evidence["BS 1"]["available"] is False
    assert evidence["BS 1"]["compliance"] == "Missing / Non-Compliant"
    assert evidence["BS 1"]["repository_status"] == "No verified file in database"
    assert evidence["BS 2"]["available"] is False
    assert evidence["BS 3"]["available"] is False


def test_status_and_finalization_consistency(auth_override, mock_supabase):
    """Statement status, cpass_status, and finalized_at are synchronized between top-level and audit object."""
    mock_submitted_audit = {
        "id": "audit-uuid-1",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "VERIFIED",
        "finalized_at": "2026-10-22T08:00:00Z",
        "salary_details": [
            {"month": 1, "year": 2026, "gross_salary": 15000, "amount_credited": 14000},
            {"month": 2, "year": 2026, "gross_salary": 15000, "amount_credited": 14000},
            {"month": 3, "year": 2026, "gross_salary": 15000, "amount_credited": 14000},
        ],
        "employer_details": [{"employer_name": "ABC Corp"}],
    }

    def table_mock(tbl_name):
        mock_tbl = MagicMock()
        if tbl_name == "ddugky_candidates":
            mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
        elif tbl_name == "placement_audits":
            mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[mock_submitted_audit])
        elif tbl_name == "candidate_documents":
            mock_tbl.select.return_value.eq.return_value.neq.return_value.order.return_value.execute.return_value = MagicMock(data=[])
        return mock_tbl

    mock_supabase.table.side_effect = table_mock

    res = client.get("/candidates/10482/audit/statement")
    assert res.status_code == 200
    data = res.json()
    assert data["audit_status"] == "SUBMITTED"
    assert data["cpass_status"] == "VERIFIED"
    assert data["finalized_at"] == "2026-10-22T08:00:00Z"
    assert data["audit"]["audit_status"] == "SUBMITTED"
    assert data["audit"]["cpass_status"] == "VERIFIED"
    assert data["audit"]["finalized_at"] == "2026-10-22T08:00:00Z"


L2_USER = CurrentUser(
    id="l2-manager-uuid",
    email="l2@cpass.org",
    full_name="Suresh Kumar",
    role="L2_MANAGER",
    assigned_state="ODISHA",
)



def test_l1_cannot_call_l2_review_endpoints(auth_override, mock_supabase):
    """L1 Coordinator is denied access to L2 Center Manager review endpoints."""
    res1 = client.post("/candidates/10482/audit/l2-review/checklist", json={"reviewed_documents": {}})
    assert res1.status_code == 403

    res2 = client.post("/candidates/10482/audit/l2-review/corrections", json={"employer_details": [], "salary_details": []})
    assert res2.status_code == 403

    res3 = client.post("/candidates/10482/audit/l2-review/approve", json={})
    assert res3.status_code == 403


def test_l2_checklist_update_saves_review_state(mock_supabase):
    """L2 Center Manager can mark documents as reviewed and state is persisted."""
    app.dependency_overrides[get_current_user] = lambda: L2_USER
    try:
        mock_audit = {
            "id": "audit-uuid-1",
            "candidate_id": 10482,
            "document_audit": {},
            "audit_status": "SUBMITTED",
        }
        mock_docs = [
            {"id": "doc-app-1", "document_type": "APPOINTMENT_LETTER", "file_name": "offer.pdf"}
        ]

        def table_mock(tbl_name):
            mock_tbl = MagicMock()
            if tbl_name == "ddugky_candidates":
                mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
            elif tbl_name == "placement_audits":
                mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[mock_audit])
                mock_tbl.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_audit])
            elif tbl_name == "candidate_documents":
                mock_tbl.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=mock_docs)
            return mock_tbl

        mock_supabase.table.side_effect = table_mock

        res = client.post(
            "/candidates/10482/audit/l2-review/checklist",
            json={"reviewed_documents": {"doc-app-1": True}},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["l2_document_reviews"]["doc-app-1"]["reviewed"] is True
        assert data["l2_document_reviews"]["doc-app-1"]["reviewed_by"] == "Suresh Kumar"
    finally:
        app.dependency_overrides.clear()


def test_l2_corrections_preserves_l1_original_and_appends_history(mock_supabase):
    """L2 corrections archive L1 submission in l1_original_submission and append to revision_history."""
    app.dependency_overrides[get_current_user] = lambda: L2_USER
    try:
        mock_audit = {
            "id": "audit-uuid-1",
            "candidate_id": 10482,
            "audit_status": "SUBMITTED",
            "employer_details": [{"employer_name": "Original Corp", "monthly_ctc": 15000.0}],
            "salary_details": [
                {"month": 1, "year": 2026, "amount_credited": 14000.0, "gross_salary": 15000.0},
                {"month": 2, "year": 2026, "amount_credited": 14000.0, "gross_salary": 15000.0},
                {"month": 3, "year": 2026, "amount_credited": 14000.0, "gross_salary": 15000.0},
            ],
            "signoff_details": {},
            "remarks": "Original L1 remarks",
        }

        captured_update = {}
        def table_mock(tbl_name):
            mock_tbl = MagicMock()
            if tbl_name == "ddugky_candidates":
                mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
            elif tbl_name == "placement_audits":
                mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[mock_audit])
                def do_update(payload):
                    captured_update.update(payload)
                    mock_up = MagicMock()
                    mock_up.eq.return_value.execute.return_value = MagicMock(data=[{**mock_audit, **payload}])
                    return mock_up
                mock_tbl.update.side_effect = do_update
            return mock_tbl

        mock_supabase.table.side_effect = table_mock

        res = client.post(
            "/candidates/10482/audit/l2-review/corrections",
            json={
                "employer_details": [{"employer_name": "Corrected Corp", "monthly_ctc": 16000.0}],
                "salary_details": [
                    {"month": 1, "year": 2026, "amount_credited": 15000.0, "gross_salary": 16000.0},
                    {"month": 2, "year": 2026, "amount_credited": 15000.0, "gross_salary": 16000.0},
                    {"month": 3, "year": 2026, "amount_credited": 15000.0, "gross_salary": 16000.0},
                ],
                "remarks": "L2 corrected",
                "correction_notes": "Fixed employer name and adjusted gross remuneration",
            },
        )
        assert res.status_code == 200
        assert captured_update["employer_details"][0]["employer_name"] == "Corrected Corp"
        signoff = captured_update["signoff_details"]
        assert "l1_original_submission" in signoff
        assert signoff["l1_original_submission"]["employer_details"][0]["employer_name"] == "Original Corp"
        assert len(signoff["revision_history"]) == 1
        assert signoff["revision_history"][0]["revised_by"] == "Suresh Kumar"
    finally:
        app.dependency_overrides.clear()


def test_l2_approval_blocked_if_audit_not_submitted(mock_supabase):
    """L2 approval is rejected if audit is still in DRAFT status."""
    app.dependency_overrides[get_current_user] = lambda: L2_USER
    try:
        mock_audit = {
            "id": "audit-uuid-1",
            "candidate_id": 10482,
            "audit_status": "DRAFT",
        }

        def table_mock(tbl_name):
            mock_tbl = MagicMock()
            if tbl_name == "ddugky_candidates":
                mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
            elif tbl_name == "candidate_holds":
                mock_tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            elif tbl_name == "placement_audits":
                mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[mock_audit])
            return mock_tbl

        mock_supabase.table.side_effect = table_mock

        res = client.post("/candidates/10482/audit/l2-review/approve", json={})
        assert res.status_code == 400
        assert "must first be finalized and submitted by L1" in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_l2_approval_blocked_if_mandatory_documents_unreviewed(mock_supabase):
    """L2 approval is blocked if mandatory documents (AL, 3 slips, 3 banks) are not reviewed."""
    app.dependency_overrides[get_current_user] = lambda: L2_USER
    try:
        mock_audit = {
            "id": "audit-uuid-1",
            "candidate_id": 10482,
            "audit_status": "SUBMITTED",
            "cpass_status": "VERIFIED",
            "document_audit": {"l2_document_reviews": {}}, # Empty checklist
        }
        mock_docs = [
            {"id": "doc-al", "document_type": "APPOINTMENT_LETTER", "upload_status": "SUCCESS"},
            {"id": "doc-s1", "document_type": "SALARY_SLIP", "reporting_month": 1, "upload_status": "SUCCESS"},
            {"id": "doc-s2", "document_type": "SALARY_SLIP", "reporting_month": 2, "upload_status": "SUCCESS"},
            {"id": "doc-s3", "document_type": "SALARY_SLIP", "reporting_month": 3, "upload_status": "SUCCESS"},
            {"id": "doc-b1", "document_type": "BANK_STATEMENT", "reporting_month": 1, "upload_status": "SUCCESS"},
            {"id": "doc-b2", "document_type": "BANK_STATEMENT", "reporting_month": 2, "upload_status": "SUCCESS"},
            {"id": "doc-b3", "document_type": "BANK_STATEMENT", "reporting_month": 3, "upload_status": "SUCCESS"},
        ]

        def table_mock(tbl_name):
            mock_tbl = MagicMock()
            if tbl_name == "ddugky_candidates":
                mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
            elif tbl_name == "candidate_holds":
                mock_tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            elif tbl_name == "placement_audits":
                mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[mock_audit])
            elif tbl_name == "candidate_documents":
                mock_tbl.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=mock_docs)
            return mock_tbl

        mock_supabase.table.side_effect = table_mock

        res = client.post("/candidates/10482/audit/l2-review/approve", json={})
        assert res.status_code == 400
        assert "must be explicitly checked and reviewed before approval" in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_l2_approval_success_and_idempotency(mock_supabase):
    """L2 approval records signoff endorsement, updates cpass_status to L2_APPROVED, and is idempotent."""
    app.dependency_overrides[get_current_user] = lambda: L2_USER
    try:
        mock_audit = {
            "id": "audit-uuid-1",
            "candidate_id": 10482,
            "audit_status": "SUBMITTED",
            "cpass_status": "VERIFIED",
            "document_audit": {
                "l2_document_reviews": {
                    "doc-al": {"reviewed": True},
                    "doc-s1": {"reviewed": True},
                    "doc-s2": {"reviewed": True},
                    "doc-s3": {"reviewed": True},
                    "doc-b1": {"reviewed": True},
                    "doc-b2": {"reviewed": True},
                    "doc-b3": {"reviewed": True},
                }
            },
            "signoff_details": {},
            "employer_details": [{"employer_name": "Acme"}],
            "salary_details": [{"month": 1, "year": 2026}, {"month": 2, "year": 2026}, {"month": 3, "year": 2026}],
        }
        mock_docs = [
            {"id": "doc-al", "document_type": "APPOINTMENT_LETTER", "upload_status": "SUCCESS"},
            {"id": "doc-s1", "document_type": "SALARY_SLIP", "reporting_month": 1, "upload_status": "SUCCESS"},
            {"id": "doc-s2", "document_type": "SALARY_SLIP", "reporting_month": 2, "upload_status": "SUCCESS"},
            {"id": "doc-s3", "document_type": "SALARY_SLIP", "reporting_month": 3, "upload_status": "SUCCESS"},
            {"id": "doc-b1", "document_type": "BANK_STATEMENT", "reporting_month": 1, "upload_status": "SUCCESS"},
            {"id": "doc-b2", "document_type": "BANK_STATEMENT", "reporting_month": 2, "upload_status": "SUCCESS"},
            {"id": "doc-b3", "document_type": "BANK_STATEMENT", "reporting_month": 3, "upload_status": "SUCCESS"},
        ]

        audit_in_db = dict(mock_audit)
        def table_mock(tbl_name):
            mock_tbl = MagicMock()
            if tbl_name == "ddugky_candidates":
                mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
            elif tbl_name == "candidate_holds":
                mock_tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            elif tbl_name == "placement_audits":
                mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[audit_in_db])
                def do_update(payload):
                    audit_in_db.update(payload)
                    m = MagicMock()
                    m.eq.return_value.execute.return_value = MagicMock(data=[audit_in_db])
                    return m
                mock_tbl.update.side_effect = do_update
            elif tbl_name == "candidate_documents":
                mock_tbl.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=mock_docs)
            return mock_tbl

        mock_supabase.table.side_effect = table_mock

        # First approval request
        res1 = client.post("/candidates/10482/audit/l2-review/approve", json={"remarks": "All documents verified."})
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["status"] == "success"
        assert data1["cpass_status"] == "L2_APPROVED"
        assert audit_in_db["signoff_details"]["centre_head"]["confirmed"] is True
        assert audit_in_db["signoff_details"]["centre_head"]["name"] == "Suresh Kumar"

        # Second approval request (idempotent)
        res2 = client.post("/candidates/10482/audit/l2-review/approve", json={})
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["status"] == "already_approved"
    finally:
        app.dependency_overrides.clear()


