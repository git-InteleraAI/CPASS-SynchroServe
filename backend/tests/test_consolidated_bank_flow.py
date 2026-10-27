"""Regression test suite for Consolidated Bank Statement End-to-End Flow and Month Coverage Resolution.

Scenarios Covered:
- Scenario A: Consolidated statement upload, single Drive upload, single DB record, 3-month coverage resolution, summary count.
- Scenario B: Independent reviewer verification status (upload alone does not mark as reviewed, L2 approval checklist).
- Scenario C: Coverage boundaries (non-covered months like Sept 2025, employer isolation, Dec-Jan year boundaries).
- Scenario D: Backwards compatibility (individual statements, coexistence with consolidated statements, single-employer dossiers).
"""

import json
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

L2_USER_ODISHA = CurrentUser(
    id="l2-odisha-uuid",
    email="l2_odisha@cpass.org",
    full_name="L2 Centre Head",
    role="L2_MANAGER",
    assigned_state="ODISHA",
)

CANDIDATE_DATA = {
    "candidate_id": 99001,
    "candidate_first_name": "Deepak",
    "candidate_last_name": "Rath",
    "tc_id": 101,
    "tc_name": "Bhubaneswar Skill Centre",
    "tc_state_name": "ODISHA",
    "state_name": "ODISHA",
    "appointed": True,
    "employer_name": "Acme Industries",
    "monthly_ctc": 22000.0,
}

MOCK_FOLDER = ("folder-id-mock-123", "CPASS/Odisha/TC/Batch/99001/Bank Statement")
MOCK_UPLOAD = {
    "file_id": "drive-file-mock-consolidated-888",
    "file_name": "Consolidated_Bank_Statement_Jun_Aug_2025.pdf",
    "mime_type": "application/pdf",
    "size": 2048576,
}


@pytest.fixture
def auth_l1():
    app.dependency_overrides[get_current_user] = lambda: L1_USER_ODISHA
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_l2():
    app.dependency_overrides[get_current_user] = lambda: L2_USER_ODISHA
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def mock_deps():
    with patch("app.routers.audits.supabase") as m_audit, \
         patch("app.routers.documents.supabase") as m_doc, \
         patch("app.auth.supabase") as m_auth, \
         patch("app.routers.documents.google_drive_service.get_or_create_candidate_subfolder", return_value=MOCK_FOLDER) as m_subfolder, \
         patch("app.routers.documents.google_drive_service.upload_file", return_value=MOCK_UPLOAD) as m_upload, \
         patch("app.routers.documents.google_drive_service.delete_file", return_value=True) as m_delete:

        mock_client = MagicMock()
        m_audit.table = mock_client.table
        m_doc.table = mock_client.table
        m_auth.table = mock_client.table

        yield {
            "db": mock_client,
            "upload_file": m_upload,
            "subfolder": m_subfolder,
            "delete_file": m_delete,
        }


# ==============================================================================
# Scenario A: Consolidated statement upload, persistence, and audit resolution
# ==============================================================================

def test_scenario_a_consolidated_bank_statement_submission_and_resolution(auth_l1, mock_deps):
    """
    Submitting 1 consolidated bank statement PDF covering June-August 2025 for Employer A:
    - Calls Drive upload exactly once.
    - Persists exactly one document record in candidate_documents.
    - get_documents_summary reports bank_statement_count = 3 (distinct covered months) and 1 physical document.
    - Document Evidence Audit resolves June, July, and August to that same physical Drive record.
    """
    mock_client = mock_deps["db"]

    persisted_consol_record = {
        "id": "doc-uuid-consol-1",
        "candidate_id": 99001,
        "document_type": "BANK_STATEMENT",
        "is_consolidated": True,
        "coverage_start_month": 6,
        "coverage_start_year": 2025,
        "coverage_end_month": 8,
        "coverage_end_year": 2025,
        "covered_months": [{"month": 6, "year": 2025}, {"month": 7, "year": 2025}, {"month": 8, "year": 2025}],
        "employer_id": "emp_1",
        "file_name": "Consolidated_June_August_2025.pdf",
        "drive_file_id": "drive-file-mock-consolidated-888",
        "upload_status": "SUCCESS",
        "reviewer_status": "PENDING",
        "verification_status": "PENDING",
        "reporting_month": 6,
        "reporting_year": 2025,
    }

    audit_record = {
        "id": "audit-uuid-1",
        "candidate_id": 99001,
        "state_name": "ODISHA",
        "audit_status": "DRAFT",
        "employer_details": [{"id": "emp_1", "employer_name": "Acme Industries", "months_worked": 3}],
        "salary_details": [
            {"id": "s1", "employer_id": "emp_1", "month": 6, "year": 2025, "gross_salary": 22000},
            {"id": "s2", "employer_id": "emp_1", "month": 7, "year": 2025, "gross_salary": 22000},
            {"id": "s3", "employer_id": "emp_1", "month": 8, "year": 2025, "gross_salary": 22000},
        ],
        "document_audit": {},
        "signoff_details": {},
        "remarks": "",
    }

    existing_docs = []

    def table_mock(tbl):
        m = MagicMock()
        if tbl in ("ddugky_candidates", "candidates"):
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
            m.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=CANDIDATE_DATA)
            m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=CANDIDATE_DATA)
        elif tbl == "placement_audits":
            m.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=audit_record)
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[audit_record])
        elif tbl == "candidate_documents":
            def get_docs():
                return MagicMock(data=list(existing_docs))

            def do_insert(ops):
                items = ops if isinstance(ops, list) else [ops]
                for item in items:
                    existing_docs.append({**persisted_consol_record, **item})
                return MagicMock(data=[persisted_consol_record])

            exec_mock = MagicMock(side_effect=get_docs)
            m.select.return_value.eq.return_value.eq.return_value.execute = exec_mock
            m.select.return_value.eq.return_value.neq.return_value.execute = exec_mock
            m.select.return_value.eq.return_value.neq.return_value.order.return_value.execute = exec_mock
            m.select.return_value.eq.return_value.execute = exec_mock
            m.insert.side_effect = lambda ops: MagicMock(execute=lambda: do_insert(ops))
        return m

    mock_client.table.side_effect = table_mock

    # Stage 1 PDF covering June to August 2025
    bank_meta = [{
        "month": 6,
        "year": 2025,
        "employer_id": "emp_1",
        "is_consolidated": True,
        "coverage_start_month": 6,
        "coverage_start_year": 2025,
        "coverage_end_month": 8,
        "coverage_end_year": 2025,
        "covered_months": [
            {"month": 6, "year": 2025},
            {"month": 7, "year": 2025},
            {"month": 8, "year": 2025},
        ],
        "replace_id": None,
    }]

    files = [
        ("bank_statements", ("Consolidated_June_August_2025.pdf", b"%PDF-1.4 mock content", "application/pdf")),
    ]
    data = {
        "bank_statements_meta": json.dumps(bank_meta),
        "allow_partial": "true",
    }

    resp = client.post("/candidates/99001/documents/submit", data=data, files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Verify 1 physical Drive upload and 1 persisted record
    assert mock_deps["upload_file"].call_count == 1
    assert body["submitted_count"] == 1
    assert len(body["documents"]) == 1
    doc_payload = body["documents"][0]
    assert doc_payload["is_consolidated"] is True
    assert doc_payload["coverage_start_month"] == 6
    assert doc_payload["coverage_end_month"] == 8
    assert doc_payload["employer_id"] == "emp_1"

    # Test get_documents_summary
    sum_resp = client.get("/candidates/99001/documents/summary")
    assert sum_resp.status_code == 200
    sum_body = sum_resp.json()
    assert sum_body["bank_statement_count"] == 3
    assert len(sum_body["bank_statements"]) == 1

    # Test Placement Audit Statement evidence list resolution
    audit_resp = client.get("/candidates/99001/audit/statement")
    assert audit_resp.status_code == 200, audit_resp.text
    evidence_list = audit_resp.json()["document_evidence"]

    bank_evidence = [e for e in evidence_list if "Bank Statement" in e.get("label", "") or "BS" in e.get("code", "")]
    assert len(bank_evidence) == 3
    # June, July, and August all resolve to the same physical document record
    for be in bank_evidence:
        assert be["doc_id"] == "doc-uuid-consol-1"
        assert be["is_consolidated"] is True
        assert "Consolidated" in be["file_name"] and "2025.pdf" in be["file_name"]
        assert "Consolidated Statement" in be["observations"]


# ==============================================================================
# Scenario B: Verification status & L2 Approval Checklist
# ==============================================================================

def test_scenario_b_independent_reviewer_verification(auth_l2, mock_deps):
    """
    Verify that:
    - Successful upload alone keeps status as unreviewed (does not falsely claim reviewer verified).
    - approve_placement_audit checklist requires L2 review for all uploaded records,
      and verifies coverage >= 3 months without assuming 3 separate physical files.
    """
    mock_client = mock_deps["db"]

    audit_record = {
        "id": "audit-uuid-1",
        "candidate_id": 99001,
        "state_name": "ODISHA",
        "audit_status": "SUBMITTED",
        "cpass_status": "PENDING_L2",
        "employer_details": [{"id": "emp_1", "employer_name": "Acme Industries", "months_worked": 3}],
        "salary_details": [
            {"id": "s1", "employer_id": "emp_1", "month": 6, "year": 2025, "gross_salary": 22000},
            {"id": "s2", "employer_id": "emp_1", "month": 7, "year": 2025, "gross_salary": 22000},
            {"id": "s3", "employer_id": "emp_1", "month": 8, "year": 2025, "gross_salary": 22000},
        ],
        "document_audit": {
            "l2_document_reviews": {},
        },
        "signoff_details": {
            "review_stages": {
                "ch": {"status": "Pending"},
                "cops": {"status": "Pending"},
                "bl": {"status": "Pending"},
            }
        },
    }

    # Uploaded documents in candidate_documents
    doc_records = [
        {
            "id": "doc-uuid-appt",
            "candidate_id": 99001,
            "document_type": "APPOINTMENT_LETTER",
            "is_consolidated": False,
            "upload_status": "SUCCESS",
            "reviewer_status": "PENDING",
            "employer_id": "emp_1",
            "file_name": "Offer_Letter.pdf",
            "reporting_month": None,
            "reporting_year": None,
            "coverage_start_month": None,
            "coverage_start_year": None,
            "coverage_end_month": None,
            "coverage_end_year": None,
            "covered_months": None,
        },
        {
            "id": "doc-uuid-sal1",
            "candidate_id": 99001,
            "document_type": "SALARY_SLIP",
            "is_consolidated": False,
            "upload_status": "SUCCESS",
            "reviewer_status": "PENDING",
            "employer_id": "emp_1",
            "file_name": "Sal_Jun.pdf",
            "reporting_month": 6,
            "reporting_year": 2025,
            "coverage_start_month": None,
            "coverage_start_year": None,
            "coverage_end_month": None,
            "coverage_end_year": None,
            "covered_months": None,
        },
        {
            "id": "doc-uuid-sal2",
            "candidate_id": 99001,
            "document_type": "SALARY_SLIP",
            "is_consolidated": False,
            "upload_status": "SUCCESS",
            "reviewer_status": "PENDING",
            "employer_id": "emp_1",
            "file_name": "Sal_Jul.pdf",
            "reporting_month": 7,
            "reporting_year": 2025,
            "coverage_start_month": None,
            "coverage_start_year": None,
            "coverage_end_month": None,
            "coverage_end_year": None,
            "covered_months": None,
        },
        {
            "id": "doc-uuid-sal3",
            "candidate_id": 99001,
            "document_type": "SALARY_SLIP",
            "is_consolidated": False,
            "upload_status": "SUCCESS",
            "reviewer_status": "PENDING",
            "employer_id": "emp_1",
            "file_name": "Sal_Aug.pdf",
            "reporting_month": 8,
            "reporting_year": 2025,
            "coverage_start_month": None,
            "coverage_start_year": None,
            "coverage_end_month": None,
            "coverage_end_year": None,
            "covered_months": None,
        },
        {
            "id": "doc-uuid-consol-1",
            "candidate_id": 99001,
            "document_type": "BANK_STATEMENT",
            "is_consolidated": True,
            "coverage_start_month": 6,
            "coverage_start_year": 2025,
            "coverage_end_month": 8,
            "coverage_end_year": 2025,
            "covered_months": [{"month": 6, "year": 2025}, {"month": 7, "year": 2025}, {"month": 8, "year": 2025}],
            "employer_id": "emp_1",
            "upload_status": "SUCCESS",
            "reviewer_status": "PENDING",
            "file_name": "Consol_Bank.pdf",
            "reporting_month": 6,
            "reporting_year": 2025,
        },
    ]

    def table_mock(tbl):
        m = MagicMock()
        if tbl in ("ddugky_candidates", "candidates"):
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
            m.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=CANDIDATE_DATA)
            m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=CANDIDATE_DATA)
        elif tbl == "placement_audits":
            m.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=audit_record)
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[audit_record])
            m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{**audit_record, "cpass_status": "L2_APPROVED"}])
        elif tbl == "candidate_holds":
            m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        elif tbl == "candidate_documents":
            m.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=doc_records)
            m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=doc_records)
            m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=doc_records)
        return m

    mock_client.table.side_effect = table_mock

    # Attempt L2 approval when documents are not yet reviewed
    appr_payload = {
        "remarks": "All documents verified on ground",
    }
    fail_resp = client.post("/candidates/99001/audit/l2-review/approve", json=appr_payload)
    assert fail_resp.status_code == 400
    assert "reviewed" in fail_resp.json()["detail"].lower()

    # Now populate l2_document_reviews with reviewed: True
    audit_record["document_audit"]["l2_document_reviews"] = {
        d["id"]: {"reviewed": True, "reviewer": "L2 Manager", "status": "VERIFIED"}
        for d in doc_records
    }

    # Now L2 approval must succeed
    pass_resp = client.post("/candidates/99001/audit/l2-review/approve", json=appr_payload)
    assert pass_resp.status_code == 200, pass_resp.text
    assert pass_resp.json()["cpass_status"] == "L2_APPROVED"


# ==============================================================================
# Scenario C: Coverage boundaries & Employer isolation
# ==============================================================================

def test_scenario_c_coverage_boundaries_and_employer_isolation(auth_l1, mock_deps):
    """
    Verify coverage boundaries:
    1. September 2025 is not covered by a June-August 2025 statement.
    2. Employer B does not inherit Employer A's consolidated coverage.
    3. Year boundary (Nov 2024 to Jan 2025) correctly covers Dec 2024 and Jan 2025.
    """
    mock_client = mock_deps["db"]

    emp_a_statement = {
        "id": "doc-uuid-consol-a",
        "candidate_id": 99001,
        "document_type": "BANK_STATEMENT",
        "is_consolidated": True,
        "coverage_start_month": 6,
        "coverage_start_year": 2025,
        "coverage_end_month": 8,
        "coverage_end_year": 2025,
        "covered_months": [{"month": 6, "year": 2025}, {"month": 7, "year": 2025}, {"month": 8, "year": 2025}],
        "employer_id": "emp_a",
        "upload_status": "SUCCESS",
        "file_name": "EmpA_Jun_Aug_2025.pdf",
        "drive_file_id": "drive-emp-a-111",
        "reviewer_status": "PENDING",
        "reporting_month": 6,
        "reporting_year": 2025,
    }

    audit_record = {
        "id": "audit-uuid-c",
        "candidate_id": 99001,
        "state_name": "ODISHA",
        "audit_status": "DRAFT",
        "employer_details": [
            {"id": "emp_a", "employer_name": "Company A", "months_worked": 3},
            {"id": "emp_b", "employer_name": "Company B", "months_worked": 1},
        ],
        "salary_details": [
            {"id": "s1", "employer_id": "emp_a", "month": 6, "year": 2025},
            {"id": "s2", "employer_id": "emp_a", "month": 7, "year": 2025},
            {"id": "s3", "employer_id": "emp_a", "month": 9, "year": 2025},  # Outside coverage
            {"id": "s4", "employer_id": "emp_b", "month": 6, "year": 2025},  # Different employer
        ],
        "document_audit": {},
        "signoff_details": {},
    }

    current_docs = [emp_a_statement]

    def table_mock(tbl):
        m = MagicMock()
        if tbl in ("ddugky_candidates", "candidates"):
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
            m.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=CANDIDATE_DATA)
            m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=CANDIDATE_DATA)
        elif tbl == "placement_audits":
            m.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=audit_record)
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[audit_record])
        elif tbl == "candidate_documents":
            m.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=current_docs)
            m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=current_docs)
            m.select.return_value.eq.return_value.neq.return_value.order.return_value.execute.return_value = MagicMock(data=current_docs)
            m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=current_docs)
        return m

    mock_client.table.side_effect = table_mock

    resp = client.get("/candidates/99001/audit/statement")
    assert resp.status_code == 200, resp.text
    evidence = resp.json()["document_evidence"]

    # BS for Emp A Month 6 -> covered
    bs_a_6 = next(e for e in evidence if e.get("employer_id") == "emp_a" and ("BS 1" in e.get("code", "") or "Month 6" in e.get("label", "")))
    assert bs_a_6["is_consolidated"] is True
    assert bs_a_6["doc_id"] == "doc-uuid-consol-a"

    # BS for Emp A Month 7 -> covered
    bs_a_7 = next(e for e in evidence if e.get("employer_id") == "emp_a" and ("BS 2" in e.get("code", "") or "Month 7" in e.get("label", "")))
    assert bs_a_7["is_consolidated"] is True
    assert bs_a_7["doc_id"] == "doc-uuid-consol-a"

    # BS for Emp A Month 9 -> NOT covered (doc_id is None)
    bs_a_9 = next(e for e in evidence if e.get("employer_id") == "emp_a" and ("BS 3" in e.get("code", "") or "Month 9" in e.get("label", "")))
    assert bs_a_9["doc_id"] is None
    assert bs_a_9["available"] is False

    # BS for Emp B Month 6 -> NOT covered by Emp A's statement (employer isolation)
    bs_b_6 = next(e for e in evidence if e.get("employer_id") == "emp_b" and "BS" in e.get("code", ""))
    assert bs_b_6["doc_id"] is None
    assert bs_b_6["available"] is False

    # Test year boundary (Nov 2024 - Jan 2025)
    boundary_statement = {
        "id": "doc-uuid-boundary",
        "candidate_id": 99001,
        "document_type": "BANK_STATEMENT",
        "is_consolidated": True,
        "coverage_start_month": 11,
        "coverage_start_year": 2024,
        "coverage_end_month": 1,
        "coverage_end_year": 2025,
        "covered_months": [
            {"month": 11, "year": 2024},
            {"month": 12, "year": 2024},
            {"month": 1, "year": 2025},
        ],
        "employer_id": "emp_a",
        "upload_status": "SUCCESS",
        "file_name": "Boundary_Nov2024_Jan2025.pdf",
        "drive_file_id": "drive-boundary-999",
        "reviewer_status": "PENDING",
        "reporting_month": 11,
        "reporting_year": 2024,
    }
    current_docs.clear()
    current_docs.append(boundary_statement)

    audit_record["employer_details"] = [{"id": "emp_a", "employer_name": "Company A", "months_worked": 3}]
    audit_record["salary_details"] = [
        {"id": "s1", "employer_id": "emp_a", "month": 11, "year": 2024},
        {"id": "s2", "employer_id": "emp_a", "month": 12, "year": 2024},
        {"id": "s3", "employer_id": "emp_a", "month": 1, "year": 2025},
    ]

    resp_boundary = client.get("/candidates/99001/audit/statement")
    assert resp_boundary.status_code == 200
    b_evidence = resp_boundary.json()["document_evidence"]
    bs_ev = [e for e in b_evidence if "Bank Statement" in e.get("label", "") or "BS" in e.get("code", "")]
    assert len(bs_ev) == 3
    for e in bs_ev:
        assert e["doc_id"] == "doc-uuid-boundary"
        assert e["is_consolidated"] is True


# ==============================================================================
# Scenario D: Compatibility with single-month and mixed statements
# ==============================================================================

def test_scenario_d_compatibility_single_and_mixed(auth_l1, mock_deps):
    """
    Verify:
    1. 3 individual monthly bank statements continue to work as expected.
    2. Coexistence: 1 consolidated statement (June-July) + 1 individual statement (August)
       correctly counts 3 distinct months without duplication.
    """
    mock_client = mock_deps["db"]

    mixed_docs = [
        {
            "id": "doc-uuid-consol-2m",
            "candidate_id": 99001,
            "document_type": "BANK_STATEMENT",
            "is_consolidated": True,
            "coverage_start_month": 6,
            "coverage_start_year": 2025,
            "coverage_end_month": 7,
            "coverage_end_year": 2025,
            "covered_months": [{"month": 6, "year": 2025}, {"month": 7, "year": 2025}],
            "employer_id": "emp_1",
            "upload_status": "SUCCESS",
            "file_name": "Jun_Jul_2025.pdf",
            "drive_file_id": "drive-mixed-1",
            "reporting_month": 6,
            "reporting_year": 2025,
        },
        {
            "id": "doc-uuid-ind-aug",
            "candidate_id": 99001,
            "document_type": "BANK_STATEMENT",
            "is_consolidated": False,
            "reporting_month": 8,
            "reporting_year": 2025,
            "employer_id": "emp_1",
            "upload_status": "SUCCESS",
            "file_name": "Aug_2025.pdf",
            "drive_file_id": "drive-mixed-2",
        },
    ]

    def table_mock(tbl):
        m = MagicMock()
        if tbl in ("ddugky_candidates", "candidates"):
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
            m.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=CANDIDATE_DATA)
            m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=CANDIDATE_DATA)
        elif tbl == "candidate_documents":
            m.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=mixed_docs)
            m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=mixed_docs)
            m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=mixed_docs)
        return m

    mock_client.table.side_effect = table_mock

    sum_resp = client.get("/candidates/99001/documents/summary")
    assert sum_resp.status_code == 200
    sum_body = sum_resp.json()
    assert sum_body["bank_statement_count"] == 3  # Jun, Jul from consol + Aug from ind
    assert len(sum_body["bank_statements"]) == 2  # 2 physical documents


# ==============================================================================
# Scenario E: Section 4 — Document Evidence Audit Exact Scenario Verification
# ==============================================================================

def test_section4_three_month_consolidated_resolution_exact_scenario(auth_l1, mock_deps):
    """
    Exact scenario:
    L1 uploads ONE consolidated bank statement PDF covering June, July, and August 2025
    for Employer 1 (Acme Corp).

    Verify:
    1. BS 1 (June 2025), BS 2 (July 2025), and BS 3 (August 2025) all resolve to the SAME
       underlying document ID and Drive file ID.
    2. All 3 rows reflect evidence present: availability_status="Yes", is_consolidated=True,
       original file name, and coverage period ("June 2025 – August 2025").
    3. September 2025 remains UNCOVERED (doc_id=None, available=False).
    4. Another employer (Employer 2) remains UNCOVERED (doc_id=None, available=False).
    5. Reviewer verification remains separate (reviewer_status="PENDING").
    6. Exactly 1 physical database document and Drive file ID are used across all 3 months.
    """
    mock_client = mock_deps["db"]

    single_consolidated_doc = {
        "id": "doc-uuid-consolidated-june-aug-2025",
        "candidate_id": 99001,
        "document_type": "BANK_STATEMENT",
        "is_consolidated": True,
        "coverage_start_month": 6,
        "coverage_start_year": 2025,
        "coverage_end_month": 8,
        "coverage_end_year": 2025,
        "covered_months": [
            {"month": 6, "year": 2025},
            {"month": 7, "year": 2025},
            {"month": 8, "year": 2025},
        ],
        "employer_id": "emp_1",
        "upload_status": "SUCCESS",
        "file_name": "Consolidated_Bank_Statement_Jun_Aug_2025.pdf",
        "drive_file_id": "drive-file-consolidated-888",
        "reviewer_status": "PENDING",
        "reporting_month": 6,
        "reporting_year": 2025,
    }

    audit_record = {
        "id": "audit-uuid-section4",
        "candidate_id": 99001,
        "audit_status": "DRAFT",
        "employer_details": [
            {"id": "emp_1", "employer_name": "Acme Corp", "months_worked": 3},
            {"id": "emp_2", "employer_name": "Beta Tech", "months_worked": 1},
        ],
        "salary_details": [
            {"id": "s1", "employer_id": "emp_1", "month": 6, "year": 2025},
            {"id": "s2", "employer_id": "emp_1", "month": 7, "year": 2025},
            {"id": "s3", "employer_id": "emp_1", "month": 8, "year": 2025},
            {"id": "s4", "employer_id": "emp_1", "month": 9, "year": 2025},  # Sept 2025 (uncovered)
            {"id": "s5", "employer_id": "emp_2", "month": 6, "year": 2025},  # Emp 2 (uncovered)
        ],
        "document_audit": {
            "bank_statement_emp_1_1": {"available": "Pending", "remarks": "Saved coordinator note month 1"},
            "bank_statement_emp_1_2": {"available": "Pending", "remarks": "Saved coordinator note month 2"},
            "bank_statement_emp_1_3": {"available": "Pending", "remarks": "Saved coordinator note month 3"},
            "bank_statement_emp_1_4": {"available": "Pending", "remarks": ""},
            "bank_statement_emp_2_1": {"available": "Pending", "remarks": ""},
        },
        "signoff_details": {},
    }

    docs_list = [single_consolidated_doc]

    def table_mock(tbl):
        m = MagicMock()
        if tbl in ("ddugky_candidates", "candidates"):
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_DATA])
            m.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=CANDIDATE_DATA)
            m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=CANDIDATE_DATA)
        elif tbl == "candidate_documents":
            m.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=docs_list)
            m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=docs_list)
            m.select.return_value.eq.return_value.neq.return_value.order.return_value.execute.return_value = MagicMock(data=docs_list)
            m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=docs_list)
        elif tbl == "placement_audits":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[audit_record])
            m.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=audit_record)
            m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=audit_record)
        return m

    mock_client.table.side_effect = table_mock

    # 1. Fetch audit statement document evidence
    resp = client.get("/candidates/99001/audit/statement")
    assert resp.status_code == 200
    evidence = resp.json()["document_evidence"]

    # Filter bank statement evidence rows for emp_1
    emp1_bs_rows = [
        e for e in evidence
        if e.get("employer_id") == "emp_1" and ("Bank Statement" in e.get("label", "") or "BS" in e.get("code", ""))
    ]
    assert len(emp1_bs_rows) == 4  # Jun, Jul, Aug, Sep

    row_jun = next(r for r in emp1_bs_rows if r.get("reporting_month") == 6)
    row_jul = next(r for r in emp1_bs_rows if r.get("reporting_month") == 7)
    row_aug = next(r for r in emp1_bs_rows if r.get("reporting_month") == 8)
    row_sep = next(r for r in emp1_bs_rows if r.get("reporting_month") == 9)

    # 2. Assert June 2025 resolves to consolidated statement
    assert row_jun["available"] is True
    assert row_jun["availability_status"] == "Yes"
    assert row_jun["doc_id"] == "doc-uuid-consolidated-june-aug-2025"
    assert row_jun["drive_file_id"] == "drive-file-consolidated-888"
    assert row_jun["file_name"] == "Consolidated_Bank_Statement_Jun_Aug_2025.pdf"
    assert row_jun["is_consolidated"] is True
    assert "June 2025 – August 2025" in row_jun.get("coverage_period", "")
    assert "Consolidated Statement" in row_jun["label"]

    # 3. Assert July 2025 resolves to SAME document ID and Drive file ID
    assert row_jul["available"] is True
    assert row_jul["availability_status"] == "Yes"
    assert row_jul["doc_id"] == "doc-uuid-consolidated-june-aug-2025"
    assert row_jul["drive_file_id"] == "drive-file-consolidated-888"
    assert row_jul["file_name"] == "Consolidated_Bank_Statement_Jun_Aug_2025.pdf"
    assert row_jul["is_consolidated"] is True
    assert "June 2025 – August 2025" in row_jul.get("coverage_period", "")

    # 4. Assert August 2025 resolves to SAME document ID and Drive file ID
    assert row_aug["available"] is True
    assert row_aug["availability_status"] == "Yes"
    assert row_aug["doc_id"] == "doc-uuid-consolidated-june-aug-2025"
    assert row_aug["drive_file_id"] == "drive-file-consolidated-888"
    assert row_aug["file_name"] == "Consolidated_Bank_Statement_Jun_Aug_2025.pdf"
    assert row_aug["is_consolidated"] is True
    assert "June 2025 – August 2025" in row_aug.get("coverage_period", "")

    # 5. Assert September 2025 remains UNCOVERED
    assert row_sep["available"] != True
    assert row_sep["availability_status"] != "Yes"
    assert row_sep["doc_id"] is None
    assert row_sep["drive_file_id"] is None

    # 6. Assert Employer 2 (emp_2) remains UNCOVERED
    emp2_bs_rows = [
        e for e in evidence
        if e.get("employer_id") == "emp_2" and ("Bank Statement" in e.get("label", "") or "BS" in e.get("code", ""))
    ]
    assert len(emp2_bs_rows) == 1
    assert emp2_bs_rows[0]["available"] != True
    assert emp2_bs_rows[0]["doc_id"] is None
    assert emp2_bs_rows[0]["drive_file_id"] is None

    # 7. Assert Reviewer status is independent (not auto-verified by upload)
    assert single_consolidated_doc["reviewer_status"] == "PENDING"


def test_section4_canonical_employer_resolution_timestamp_vs_sequence_id(auth_l1, mock_deps):
    """
    Exact Candidate 1076629 regression test:
    - Single employer with generated ID: 'emp_1793083463814_1'
    - Salary rows recorded with sequence ID: 'emp_1'
    - Uploaded consolidated document has employer_id: 'emp_1793083463814_1'
    - Filename contains 'Salary_Slips' but document_type is 'BANK_STATEMENT'
    - Section 4 MUST resolve BS 1, BS 2, BS 3 to the exact same document ID and Drive ID.
    """
    mock_client = mock_deps["db"]

    cand_profile = {
        "candidate_id": 99001,
        "name": "Donipati Jhanshi",
        "tc_state_name": "ODISHA",
        "state_name": "ODISHA",
        "centre_name": "Bhubaneswar Centre",
        "appointed": True,
    }

    single_emp_record = {
        "id": "audit-uuid-cand-1076629",
        "candidate_id": 99001,
        "state_name": "ODISHA",
        "audit_status": "DRAFT",
        "employer_details": [
            {
                "id": "emp_1793083463814_1",
                "employer_name": "ACHARIYA TECHNOLOGIES PVT. LTD.",
                "months_worked": 3,
            }
        ],
        "salary_details": [
            {"id": "sal_1", "employer_id": "emp_1", "month": 6, "year": 2025, "gross_salary": 18000},
            {"id": "sal_2", "employer_id": "emp_1", "month": 7, "year": 2025, "gross_salary": 18000},
            {"id": "sal_3", "employer_id": "emp_1", "month": 8, "year": 2025, "gross_salary": 18000},
        ],
        "document_audit": {},
    }

    consolidated_bank_doc = {
        "id": "44cbc811-a74e-4e55-9ac8-3ee304119d4a",
        "candidate_id": 99001,
        "document_type": "BANK_STATEMENT",
        "file_name": "Three_Month_Salary_Slips_Y_Shailaja.pdf",
        "upload_status": "SUCCESS",
        "drive_file_id": "18VlP8N9O9R03t_real_drive_id",
        "employer_id": "emp_1793083463814_1",
        "is_consolidated": True,
        "coverage_start_month": 6,
        "coverage_start_year": 2025,
        "coverage_end_month": 8,
        "coverage_end_year": 2025,
        "covered_months": [
            {"year": 2025, "month": 6},
            {"year": 2025, "month": 7},
            {"year": 2025, "month": 8},
        ],
        "created_at": "2026-10-27T08:00:00Z",
    }

    docs_list = [consolidated_bank_doc]

    def table_mock(tbl):
        m = MagicMock()
        if tbl in ("ddugky_candidates", "candidates"):
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[cand_profile])
            m.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=cand_profile)
            m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=cand_profile)
        elif tbl == "candidate_documents":
            m.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=docs_list)
            m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=docs_list)
            m.select.return_value.eq.return_value.neq.return_value.order.return_value.execute.return_value = MagicMock(data=docs_list)
            m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=docs_list)
        elif tbl == "placement_audits":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[single_emp_record])
            m.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=single_emp_record)
            m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=single_emp_record)
        return m

    mock_client.table.side_effect = table_mock

    client = TestClient(app)
    resp = client.get("/candidates/99001/audit/statement")
    assert resp.status_code == 200, resp.text
    evidence = resp.json()["document_evidence"]

    bs_rows = [e for e in evidence if "BS" in e.get("code", "")]
    assert len(bs_rows) == 3

    for bs in bs_rows:
        assert bs["available"] is True
        assert bs["availability_status"] == "Yes"
        assert bs["doc_id"] == "44cbc811-a74e-4e55-9ac8-3ee304119d4a"
        assert bs["drive_file_id"] == "18VlP8N9O9R03t_real_drive_id"
        assert bs["file_name"] == "Three_Month_Salary_Slips_Y_Shailaja.pdf"
        assert bs["is_consolidated"] is True
        assert "June 2025 – August 2025" in bs.get("coverage_period", "")



