"""Tests for CPASS L1 Enhancements and Lookups.

Verifies:
1. Dynamic State Lookup includes candidate recruitment states (such as MIZORAM).
2. Dynamic Centre Lookup falls back to candidate state_name if tc_state_name is missing.
3. Candidate Detail API returns extended batch and candidate profile fields (masked bank account, dates, email, etc.).
4. Placement Audit submission stamps authenticated submitter tracking into signoff_details.
5. Placement Audit Statement payload surfaces submitter, placement_executive, and batch details.
6. L2 Workflow isolation: L2 endpoints remain functional and unaffected.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentUser, get_current_user
from app.main import app

client = TestClient(app)

L1_USER = CurrentUser(
    id="l1-user-uuid-123",
    email="ananya.sharma@synchroserve.com",
    full_name="Ananya Sharma",
    role="L1_COORDINATOR",
)

L2_USER = CurrentUser(
    id="l2-user-uuid-456",
    email="ramesh.manager@synchroserve.com",
    full_name="Ramesh Patel",
    role="L2_MANAGER",
)

SAMPLE_CANDIDATE = {
    "candidate_id": 1076617,
    "candidate_first_name": "Lal",
    "candidate_last_name": "Rinzuala",
    "candidate_father_name": "Zothanmawia",
    "gender": "MALE",
    "date_of_birth": "1998-04-12",
    "mobile_number": "9862123456",
    "appointed": True,
    "employer_name": "Tech Corp Pvt Ltd",
    "kb_batch_id": 9901,
    "batch_code": "MZ-BATCH-2023-01",
    "batch_start_date": "2023-01-10",
    "batch_end_date": "2023-04-10",
    "trade_name": "Customer Care Executive",
    "tc_id": 1005985,
    "tc_name": "SYNCHROSERVE - HYDERABAD",
    "tc_state_name": "TELANGANA",
    "state_name": "MIZORAM",
    "sanction_order_number": "221 of 2019-2020",
    "monthly_ctc": 18000.0,
    "candidate_email": "lal.rinzuala@example.com",
    "candidate_qualification": "Graduate",
    "permanent_address": "House 42, Chanmari, Aizawl, Mizoram",
    "bank_account": "123456789012",
    "aadhar": "987654321234",
}


@pytest.fixture
def auth_l1():
    app.dependency_overrides[get_current_user] = lambda: L1_USER
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def auth_l2():
    app.dependency_overrides[get_current_user] = lambda: L2_USER
    yield
    app.dependency_overrides.clear()


def test_states_lookup_includes_mizoram(auth_l1):
    """RPC returns training centre states, and candidate state_name is dynamically merged."""
    with patch("app.routers.lookups.supabase") as mock_sb:
        # Mock RPC get_cpass_states returning standard TC states
        mock_sb.rpc.return_value.execute.return_value = MagicMock(
            data=[{"state": "ANDHRA PRADESH"}, {"state": "TELANGANA"}, {"state": "ODISHA"}]
        )
        # Mock missing candidate state query returning MIZORAM
        mock_tbl = MagicMock()
        mock_tbl.select.return_value.not_.in_.return_value.execute.return_value = MagicMock(
            data=[{"state_name": "MIZORAM"}]
        )
        mock_sb.table.return_value = mock_tbl

        res = client.get("/lookups/states")
        assert res.status_code == 200
        states = res.json()
        assert "MIZORAM" in states
        assert "ANDHRA PRADESH" in states
        assert "TELANGANA" in states


def test_centres_lookup_fallback_by_state_name(auth_l1):
    """When a state has no TC state records, centres() falls back to candidate state_name."""
    with patch("app.routers.lookups.supabase") as mock_sb:
        mock_tbl = MagicMock()
        # First query (by tc_state_name) returns empty list
        # Second query (fallback by state_name) returns SynchroServe Hyderabad
        mock_tbl.select.return_value.eq.return_value.execute.side_effect = [
            MagicMock(data=[]),
            MagicMock(data=[{"tc_id": 1005985, "tc_name": "SYNCHROSERVE - HYDERABAD"}]),
        ]
        mock_sb.table.return_value = mock_tbl

        res = client.get("/lookups/centres?state=MIZORAM")
        assert res.status_code == 200
        centres = res.json()
        assert len(centres) == 1
        assert centres[0]["tc_id"] == 1005985
        assert centres[0]["name"] == "SYNCHROSERVE - HYDERABAD"


def test_candidate_detail_returns_extended_fields_and_masks_bank(auth_l1):
    """Candidate detail returns batch dates, trade, email, qualification, and masked bank account."""
    with patch("app.routers.lookups.supabase") as mock_sb:
        mock_tbl = MagicMock()
        mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[SAMPLE_CANDIDATE]
        )
        mock_sb.table.return_value = mock_tbl

        res = client.get("/lookups/candidates/1076617")
        assert res.status_code == 200
        data = res.json()

        assert data["candidate_id"] == 1076617
        assert data["batch_code"] == "MZ-BATCH-2023-01"
        assert data["batch_start_date"] == "2023-01-10"
        assert data["batch_end_date"] == "2023-04-10"
        assert data["trade_name"] == "Customer Care Executive"
        assert data["candidate_email"] == "lal.rinzuala@example.com"
        assert data["candidate_qualification"] == "Graduate"
        assert data["gender"] == "MALE"
        assert data["masked_bank_account"] == "XXXX-XXXX-9012"
        assert "Chanmari, Aizawl" in data["address"]


def test_submit_audit_stamps_submitter_tracking(auth_l1):
    """Submitting placement audit records authenticated L1 submitter metadata."""
    with patch("app.routers.audits.supabase") as mock_sb:
        mock_tbl = MagicMock()

        # Mock candidate check
        mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[SAMPLE_CANDIDATE]
        )
        mock_sb.table.return_value = mock_tbl

        # Mock holds check (no holds)
        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[SAMPLE_CANDIDATE]
                )
            elif name == "candidate_holds":
                t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[]
                )
            elif name == "placement_audits":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[]
                )
                t.insert.return_value.execute.return_value = MagicMock(
                    data=[{"id": "audit-123", "audit_status": "SUBMITTED"}]
                )
            return t

        mock_sb.table.side_effect = table_dispatch

        submit_payload = {
            "employer_details": [
                {
                    "employer_name": "Tech Corp Pvt Ltd",
                    "months_worked": 6,
                    "monthly_ctc": 18000.0,
                }
            ],
            "salary_details": [
                {"month": 1, "year": 2024, "gross_salary": 18000, "net_salary": 16500, "amount_credited": 16500},
                {"month": 2, "year": 2024, "gross_salary": 18000, "net_salary": 16500, "amount_credited": 16500},
                {"month": 3, "year": 2024, "gross_salary": 18000, "net_salary": 16500, "amount_credited": 16500},
            ],
            "document_audit": {
                "overall_compliance": True,
            },
            "signoff_details": {
                "centre_head": {"confirmed": True, "name": "Centre Head"},
            },
            "remarks": None,
        }

        res = client.post("/candidates/1076617/audit/submit", json=submit_payload)
        assert res.status_code == 200
        data = res.json()
        assert data["message"] == "Placement Audit Statement submitted successfully"


def test_statement_endpoint_surfaces_submitter_and_batch_details(auth_l1):
    """get_audit_statement compiles submitter tracking and full batch/candidate fields."""
    with patch("app.routers.audits.supabase") as mock_sb:
        existing_audit = {
            "id": "audit-123",
            "candidate_id": 1076617,
            "audit_status": "SUBMITTED",
            "cpass_status": "VERIFIED",
            "signoff_details": {
                "submitter": {
                    "user_id": "l1-user-uuid-123",
                    "name": "Ananya Sharma",
                    "email": "ananya.sharma@synchroserve.com",
                    "role": "L1_COORDINATOR",
                    "role_label": "L1 (PE)",
                    "submitted_at": "2024-03-15T10:00:00Z",
                },
                "placement_executive": {
                    "name": "Ananya Sharma",
                    "designation": "Placement Executive (L1)",
                },
            },
            "employer_details": [
                {"employer_name": "Tech Corp Pvt Ltd", "months_worked": 6, "monthly_ctc": 18000.0}
            ],
            "salary_details": [
                {"month": 1, "year": 2024, "gross_salary": 18000, "amount_credited": 16500},
                {"month": 2, "year": 2024, "gross_salary": 18000, "amount_credited": 16500},
                {"month": 3, "year": 2024, "gross_salary": 18000, "amount_credited": 16500},
            ],
        }

        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[SAMPLE_CANDIDATE]
                )
            elif name == "placement_audits":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[existing_audit]
                )
            elif name == "candidate_documents":
                t.select.return_value.eq.return_value.neq.return_value.order.return_value.execute.return_value = MagicMock(
                    data=[]
                )
            return t

        mock_sb.table.side_effect = table_dispatch

        res = client.get("/candidates/1076617/audit/statement")
        assert res.status_code == 200
        data = res.json()

        assert data["submitter"]["name"] == "Ananya Sharma"
        assert data["submitter"]["role_label"] == "L1 (PE)"
        assert data["candidate"]["batch_start_date"] == "2023-01-10"
        assert data["candidate"]["batch_end_date"] == "2023-04-10"
        assert data["candidate"]["candidate_email"] == "lal.rinzuala@example.com"
        assert data["candidate"]["candidate_qualification"] == "Graduate"
        assert data["candidate"]["masked_bank_account"] == "XXXX-XXXX-9012"


def test_l2_review_isolation_unaffected(auth_l2):
    """Ensure L2 checklist and review endpoints remain untouched and operational."""
    with patch("app.routers.audits.supabase") as mock_sb:
        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[SAMPLE_CANDIDATE]
                )
            elif name == "placement_audits":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[{
                        "id": "audit-123",
                        "candidate_id": 1076617,
                        "document_audit": {},
                    }]
                )
                t.update.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"id": "audit-123"}]
                )
            elif name == "candidate_documents":
                t.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(
                    data=[{"id": "doc-1", "file_name": "offer.pdf"}]
                )
            return t

        mock_sb.table.side_effect = table_dispatch

        res = client.post("/candidates/1076617/audit/l2-review/checklist", json={
            "reviewed_documents": {"doc-1": True}
        })
        assert res.status_code == 200
        assert res.json()["status"] == "success"


def test_doc_audit_availability_and_compliance_persistence(auth_l1):
    """Document availability (Yes, No, Pending) and compliance values persist independently in draft."""
    with patch("app.routers.audits.supabase") as mock_sb:
        captured_payload = {}

        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[SAMPLE_CANDIDATE]
                )
            elif name == "placement_audits":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[]
                )
                def insert_capture(payload):
                    captured_payload.update(payload)
                    m = MagicMock()
                    m.execute.return_value = MagicMock(data=[{"id": "audit-draft-1", **payload}])
                    return m
                t.insert.side_effect = insert_capture
            return t

        mock_sb.table.side_effect = table_dispatch

        draft_payload = {
            "employer_details": [{"employer_name": "Tech Corp Pvt Ltd", "monthly_ctc": 18000.0}],
            "salary_details": [
                {"month": 1, "year": 2024, "gross_salary": 18000, "net_salary": 16500, "amount_credited": 16500},
                {"month": 2, "year": 2024, "gross_salary": 18000, "net_salary": 16500, "amount_credited": 16500},
                {"month": 3, "year": 2024, "gross_salary": 18000, "net_salary": 16500, "amount_credited": 16500},
            ],
            "document_audit": {
                "appointment_letter": {"available": "Yes", "compliance": "Compliant", "remarks": "Offer verified"},
                "salary_slip_1": {"available": "Yes", "compliance": "Compliant", "remarks": "Month 1 ok"},
                "salary_slip_2": {"available": "No", "compliance": "Non-Compliant", "remarks": "Not received from employer"},
                "salary_slip_3": {"available": "Pending", "compliance": "Under Verification", "remarks": "Awaiting HR confirmation"},
                "bank_statement_1": {"available": "Yes", "compliance": "Compliant", "remarks": "Credit verified"},
                "bank_statement_2": {"available": "No", "compliance": "Non-Compliant", "remarks": "Statement missing"},
                "bank_statement_3": {"available": "Pending", "compliance": "Under Verification", "remarks": "Passbook update requested"},
                "other_document": {"available": "Yes", "compliance": "Compliant", "remarks": "Joining report verified", "title": "Joining Report"},
                "overall_compliance": False,
            },
            "signoff_details": {
                "centre_head": {"confirmed": False, "name": "Centre Head"},
            },
            "remarks": "Partial documents draft",
        }

        res = client.post("/candidates/1076617/audit/draft", json=draft_payload)
        assert res.status_code == 200
        saved_audit = res.json()["audit"]
        saved_doc_audit = saved_audit["document_audit"]

        # 1. Independent availability persistence
        assert saved_doc_audit["appointment_letter"]["available"] == "Yes"
        assert saved_doc_audit["salary_slip_2"]["available"] == "No"
        assert saved_doc_audit["salary_slip_3"]["available"] == "Pending"
        assert saved_doc_audit["bank_statement_2"]["available"] == "No"
        assert saved_doc_audit["bank_statement_3"]["available"] == "Pending"
        assert saved_doc_audit["other_document"]["available"] == "Yes"
        assert saved_doc_audit["other_document"]["title"] == "Joining Report"

        # 2. Independent compliance persistence
        assert saved_doc_audit["appointment_letter"]["compliance"] == "Compliant"
        assert saved_doc_audit["salary_slip_2"]["compliance"] == "Non-Compliant"
        assert saved_doc_audit["salary_slip_3"]["compliance"] == "Under Verification"
        assert saved_doc_audit["bank_statement_2"]["compliance"] == "Non-Compliant"
        assert saved_doc_audit["bank_statement_3"]["compliance"] == "Under Verification"


def test_submit_allowed_with_unavailable_or_pending_documents(auth_l1):
    """L1 submission is allowed when documents are marked No or Pending, setting cpass_status to PENDING."""
    with patch("app.routers.audits.supabase") as mock_sb:
        submitted_record = {}

        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[SAMPLE_CANDIDATE]
                )
            elif name == "candidate_holds":
                t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[]
                )
            elif name == "placement_audits":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[]
                )
                def insert_capture(payload):
                    submitted_record.update(payload)
                    m = MagicMock()
                    m.execute.return_value = MagicMock(data=[{"id": "audit-submitted-1", **payload}])
                    return m
                t.insert.side_effect = insert_capture
            return t

        mock_sb.table.side_effect = table_dispatch

        submit_payload = {
            "employer_details": [
                {"employer_name": "Tech Corp Pvt Ltd", "months_worked": 3, "monthly_ctc": 18000.0}
            ],
            "salary_details": [
                {"month": 1, "year": 2024, "gross_salary": 18000, "net_salary": 16500, "amount_credited": 16500},
                {"month": 2, "year": 2024, "gross_salary": 18000, "net_salary": 16500, "amount_credited": 16500},
                {"month": 3, "year": 2024, "gross_salary": 18000, "net_salary": 16500, "amount_credited": 16500},
            ],
            "document_audit": {
                "appointment_letter": {"available": "Yes", "compliance": "Compliant"},
                "salary_slip_1": {"available": "Yes", "compliance": "Compliant"},
                "salary_slip_2": {"available": "No", "compliance": "Non-Compliant"},
                "salary_slip_3": {"available": "Pending", "compliance": "Under Verification"},
                "bank_statement_1": {"available": "Yes", "compliance": "Compliant"},
                "bank_statement_2": {"available": "No", "compliance": "Non-Compliant"},
                "bank_statement_3": {"available": "Pending", "compliance": "Under Verification"},
                "other_document": {"available": "Pending", "compliance": "Under Verification"},
            },
            "signoff_details": {
                "centre_head": {"confirmed": True, "name": "Centre Head"},
            },
            "remarks": "Submitted with partial documents awaiting later upload",
        }

        res = client.post("/candidates/1076617/audit/submit", json=submit_payload)
        assert res.status_code == 200
        data = res.json()
        assert data["message"] == "Placement Audit Statement submitted successfully"
        assert submitted_record["audit_status"] == "SUBMITTED"
        # Since some documents are No or Pending, cpass_status MUST NOT be VERIFIED
        assert submitted_record["cpass_status"] == "PENDING"


def test_other_document_upload_and_statement_synchronization(auth_l1):
    """Uploading OTHER_DOCUMENT stores title, syncs Drive folder 'Other Documents', and appears in statement."""
    with patch("app.routers.documents.supabase") as mock_sb:
        inserted_docs = []

        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[SAMPLE_CANDIDATE]
                )
            elif name == "candidate_documents":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[SAMPLE_CANDIDATE]
                )
                t.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(
                    data=[]
                )
                def insert_capture(payload):
                    doc_row = {"id": "doc-other-1", **payload}
                    inserted_docs.append(doc_row)
                    m = MagicMock()
                    m.execute.return_value = MagicMock(data=[doc_row])
                    return m
                t.insert.side_effect = insert_capture
            elif name == "placement_audits":
                t.select.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[]
                )
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[]
                )
            return t

        mock_sb.table.side_effect = table_dispatch

        with (
            patch("app.routers.documents.google_drive_service.get_or_create_candidate_subfolder") as mock_folder,
            patch("app.routers.documents.google_drive_service.upload_file") as mock_upload,
        ):
            mock_folder.return_value = ("folder-od-id", "path/to/Other Documents")
            mock_upload.return_value = {
                "file_id": "drive-od-1",
                "file_name": "joining_report.pdf",
                "mime_type": "application/pdf",
                "size": 2048,
            }

            res = client.post(
                "/candidates/1076617/documents",
                data={
                    "document_type": "OTHER_DOCUMENT",
                    "document_title": "Candidate Joining Report",
                },
                files={
                    "file": ("joining_report.pdf", b"%PDF-1.4 test other doc", "application/pdf")
                },
            )
            assert res.status_code == 200
            data = res.json()
            assert data["document_type"] == "OTHER_DOCUMENT"
            assert data["document_title"] == "Candidate Joining Report"
            assert mock_folder.call_args[1]["doc_type"] == "OTHER_DOCUMENT"
            assert len(inserted_docs) == 1
            assert inserted_docs[0]["document_type"] == "OTHER_DOCUMENT"
            assert inserted_docs[0]["document_title"] == "Candidate Joining Report"


def test_unauthorized_role_blocked_from_l1_draft_and_submit(auth_l2):
    """L2 Managers are blocked from creating/submitting L1 placement audit statements."""
    res_draft = client.post("/candidates/1076617/audit/draft", json={
        "employer_details": [{"employer_name": "Test"}],
        "salary_details": [],
        "document_audit": {},
        "signoff_details": {},
        "remarks": None,
    })
    assert res_draft.status_code == 403

    res_submit = client.post("/candidates/1076617/audit/submit", json={
        "employer_details": [{"employer_name": "Test"}],
        "salary_details": [],
        "document_audit": {},
        "signoff_details": {},
        "remarks": None,
    })
    assert res_submit.status_code == 403

