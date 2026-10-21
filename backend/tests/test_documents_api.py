"""Automated tests for L1 Document Uploads, Google Drive Integration, and Business Rules.

Covers:
- Authentication & authorization on document routes.
- Allowed MIME types (PDF, PNG, JPG/JPEG) and 10MB file size limits.
- Appointment / Offer Letter single active record constraint & controlled replacement.
- Salary slips and bank statements 3-12 month bounds and duplicate period prevention.
- Google Drive folder hierarchy generation and reuse.
- Partial failure reconciliation (rollback of Drive file if database persistence fails).
- Authorized file streaming download and deletion.
"""

from io import BytesIO
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentUser, get_current_user
from app.main import app
from app.services.google_drive import (
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE_BYTES,
    GoogleDriveNotConfiguredError,
    GoogleDriveService,
)

client = TestClient(app)

AUTH_USER = CurrentUser(
    id="test-user-uuid",
    email="coordinator@cpass.org",
    full_name="Test Coordinator",
    role="L1_COORDINATOR",
)

CANDIDATE_DATA = {
    "candidate_id": 99901,
    "candidate_first_name": "Ramesh",
    "candidate_last_name": "Kumar",
    "tc_state_name": "Odisha",
    "tc_name": "Bhubaneswar Skill Centre",
    "batch_code": "BATCH-OD-2023-01",
}


@pytest.fixture
def mock_supabase():
    with patch("app.routers.documents.supabase") as mock_sb:
        yield mock_sb


@pytest.fixture
def auth_override():
    app.dependency_overrides[get_current_user] = lambda: AUTH_USER
    yield
    app.dependency_overrides.clear()


def test_unauthenticated_request_rejected():
    """Unauthenticated access to documents endpoint must return 401."""
    res = client.get("/candidates/99901/documents")
    assert res.status_code == 401


def test_list_documents_success(mock_supabase, auth_override):
    """Authenticated user can list documents for a candidate."""
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        CANDIDATE_DATA
    ]
    mock_supabase.table.return_value.select.return_value.eq.return_value.neq.return_value.order.return_value.execute.return_value.data = [
        {
            "id": "doc-1",
            "candidate_id": 99901,
            "document_type": "APPOINTMENT_LETTER",
            "file_name": "appointment.pdf",
            "upload_status": "SUCCESS",
        }
    ]

    res = client.get("/candidates/99901/documents")
    assert res.status_code == 200
    docs = res.json()
    assert len(docs) == 1
    assert docs[0]["document_type"] == "APPOINTMENT_LETTER"


def test_get_summary_calculates_eligibility(mock_supabase, auth_override):
    """Summary returns correct checklist, counting distinct months and minimum requirements."""
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        CANDIDATE_DATA
    ]
    mock_supabase.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = [
        {
            "id": "doc-app",
            "document_type": "APPOINTMENT_LETTER",
            "file_name": "offer.pdf",
            "upload_status": "SUCCESS",
        },
        {"id": "doc-s1", "document_type": "SALARY_SLIP", "reporting_month": 1, "reporting_year": 2024, "upload_status": "SUCCESS"},
        {"id": "doc-s2", "document_type": "SALARY_SLIP", "reporting_month": 2, "reporting_year": 2024, "upload_status": "SUCCESS"},
        {"id": "doc-s3", "document_type": "SALARY_SLIP", "reporting_month": 3, "reporting_year": 2024, "upload_status": "SUCCESS"},
        {"id": "doc-b1", "document_type": "BANK_STATEMENT", "reporting_month": 1, "reporting_year": 2024, "upload_status": "SUCCESS"},
        {"id": "doc-b2", "document_type": "BANK_STATEMENT", "reporting_month": 2, "reporting_year": 2024, "upload_status": "SUCCESS"},
        {"id": "doc-b3", "document_type": "BANK_STATEMENT", "reporting_month": 3, "reporting_year": 2024, "upload_status": "SUCCESS"},
    ]

    res = client.get("/candidates/99901/documents/summary")
    assert res.status_code == 200
    summary = res.json()
    assert summary["has_appointment_letter"] is True
    assert summary["salary_slip_count"] == 3
    assert summary["bank_statement_count"] == 3
    assert summary["min_requirements_met"] is True


def test_upload_invalid_document_type(mock_supabase, auth_override):
    """Uploading an unrecognized document type must return 400."""
    res = client.post(
        "/candidates/99901/documents",
        data={"document_type": "INVALID_TYPE"},
        files={"file": ("test.pdf", b"%PDF-1.4 dummy", "application/pdf")},
    )
    assert res.status_code == 400
    assert "Invalid document_type" in res.json()["detail"]


def test_upload_file_exceeds_max_size(mock_supabase, auth_override):
    """Files exceeding 10MB limit must be rejected with 400."""
    oversized = b"a" * (MAX_FILE_SIZE_BYTES + 1024)
    res = client.post(
        "/candidates/99901/documents",
        data={"document_type": "APPOINTMENT_LETTER"},
        files={"file": ("huge.pdf", oversized, "application/pdf")},
    )
    assert res.status_code == 400
    assert "File size exceeds limit" in res.json()["detail"]


def test_upload_unsupported_mime_type(mock_supabase, auth_override):
    """Unsupported file formats (e.g. .exe) must be rejected with 400."""
    res = client.post(
        "/candidates/99901/documents",
        data={"document_type": "APPOINTMENT_LETTER"},
        files={"file": ("malware.exe", b"binarycontent", "application/x-msdownload")},
    )
    assert res.status_code == 400
    assert "Unsupported file format" in res.json()["detail"]


def test_appointment_letter_enforces_single_active_constraint(mock_supabase, auth_override):
    """Uploading a second appointment letter without replace_id must be rejected with 400."""
    # Candidate lookup mock
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        CANDIDATE_DATA
    ]
    # Existing appointment letter found
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.neq.return_value.execute.return_value.data = [
        {"id": "existing-doc-1", "drive_file_id": "drive-file-123"}
    ]

    res = client.post(
        "/candidates/99901/documents",
        data={"document_type": "APPOINTMENT_LETTER"},
        files={"file": ("appointment.pdf", b"%PDF-1.4 test", "application/pdf")},
    )
    assert res.status_code == 400
    assert "already exists for this candidate" in res.json()["detail"]


def test_salary_slip_rejects_duplicate_month_year(mock_supabase, auth_override):
    """Duplicate salary slip for the same month/year without replacement must fail with 400."""
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        CANDIDATE_DATA
    ]
    # Duplicate period check returns existing row
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.neq.return_value.execute.return_value.data = [
        {"id": "doc-slip-1", "drive_file_id": "drive-slip-1"}
    ]

    res = client.post(
        "/candidates/99901/documents",
        data={"document_type": "SALARY_SLIP", "reporting_month": 4, "reporting_year": 2024},
        files={"file": ("slip4.pdf", b"%PDF-1.4 content", "application/pdf")},
    )
    assert res.status_code == 400
    assert "already exists" in res.json()["detail"]


def test_salary_slip_enforces_max_12_months(mock_supabase, auth_override):
    """Attempting to upload beyond 12 distinct months for salary slips must return 400."""
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        CANDIDATE_DATA
    ]
    # No conflict for specific period
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.neq.return_value.execute.return_value.data = []

    # But 12 distinct months already uploaded
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.neq.return_value.execute.return_value.data = [
        {"reporting_month": m, "reporting_year": 2024} for m in range(1, 13)
    ]

    res = client.post(
        "/candidates/99901/documents",
        data={"document_type": "SALARY_SLIP", "reporting_month": 1, "reporting_year": 2025},
        files={"file": ("slip13.pdf", b"%PDF-1.4 content", "application/pdf")},
    )
    assert res.status_code == 400
    assert "Maximum limit of 12 distinct months" in res.json()["detail"]


def test_drive_not_configured_returns_503(mock_supabase, auth_override):
    """When Drive is unconfigured on the server, backend responds with 503 rather than crashing."""
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        CANDIDATE_DATA
    ]
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.neq.return_value.execute.return_value.data = []

    with patch("app.routers.documents.google_drive_service.get_or_create_candidate_subfolder", side_effect=GoogleDriveNotConfiguredError("Drive unconfigured")):
        res = client.post(
            "/candidates/99901/documents",
            data={"document_type": "APPOINTMENT_LETTER"},
            files={"file": ("appointment.pdf", b"%PDF-1.4 content", "application/pdf")},
        )
        assert res.status_code == 503
        assert "Google Drive integration is not configured" in res.json()["detail"]


def test_successful_upload_with_mocked_drive(mock_supabase, auth_override):
    """Successful Google Drive upload persists metadata into candidate_documents."""
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        CANDIDATE_DATA
    ]
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.neq.return_value.execute.return_value.data = []

    mock_folder = ("folder-id-123", "CPASS/Odisha/TC/Batch/99901/Appointment Letter")
    mock_upload = {
        "file_id": "drive-file-abc",
        "file_name": "appointment.pdf",
        "mime_type": "application/pdf",
        "size": 1024,
    }

    mock_db_inserted = {
        "id": "uuid-doc-1",
        "candidate_id": 99901,
        "document_type": "APPOINTMENT_LETTER",
        "drive_file_id": "drive-file-abc",
        "upload_status": "SUCCESS",
    }
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [mock_db_inserted]

    with patch("app.routers.documents.google_drive_service.get_or_create_candidate_subfolder", return_value=mock_folder):
        with patch("app.routers.documents.google_drive_service.upload_file", return_value=mock_upload):
            res = client.post(
                "/candidates/99901/documents",
                data={"document_type": "APPOINTMENT_LETTER"},
                files={"file": ("appointment.pdf", b"%PDF-1.4 test valid content", "application/pdf")},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["drive_file_id"] == "drive-file-abc"
            assert data["upload_status"] == "SUCCESS"


def test_partial_failure_reconciles_drive_file(mock_supabase, auth_override):
    """If Drive upload succeeds but DB insert fails, Drive file is deleted so orphans aren't left behind."""
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        CANDIDATE_DATA
    ]
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.neq.return_value.execute.return_value.data = []

    mock_folder = ("folder-id-123", "CPASS/Odisha/TC/Batch/99901/Appointment Letter")
    mock_upload = {
        "file_id": "drive-file-orphan",
        "file_name": "appointment.pdf",
        "mime_type": "application/pdf",
        "size": 1024,
    }

    mock_supabase.table.return_value.insert.return_value.execute.side_effect = Exception("DB Connection Timeout")

    with patch("app.routers.documents.google_drive_service.get_or_create_candidate_subfolder", return_value=mock_folder):
        with patch("app.routers.documents.google_drive_service.upload_file", return_value=mock_upload):
            with patch("app.routers.documents.google_drive_service.delete_file") as mock_delete:
                res = client.post(
                    "/candidates/99901/documents",
                    data={"document_type": "APPOINTMENT_LETTER"},
                    files={"file": ("appointment.pdf", b"%PDF-1.4 content", "application/pdf")},
                )
                assert res.status_code == 500
                assert "Document metadata could not be saved" in res.json()["detail"]
                # Must have deleted the orphaned file from Drive
                mock_delete.assert_called_once_with("drive-file-orphan")


def test_download_document_streams_file(mock_supabase, auth_override):
    """Authorized download returns streaming file response."""
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {
            "id": "doc-uuid-1",
            "candidate_id": 99901,
            "drive_file_id": "drive-file-xyz",
            "file_name": "appointment.pdf",
            "mime_type": "application/pdf",
        }
    ]

    with patch(
        "app.routers.documents.google_drive_service.download_file",
        return_value=(b"%PDF-1.4 payload content", "appointment.pdf", "application/pdf"),
    ):
        res = client.get("/candidates/99901/documents/doc-uuid-1/download")
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/pdf"
        assert b"%PDF-1.4 payload content" in res.content


def test_delete_document_removes_from_drive_and_db(mock_supabase, auth_override):
    """Deleting a document deletes it from Drive and removes the database record."""
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"id": "doc-uuid-1", "drive_file_id": "drive-file-xyz"}
    ]

    with patch("app.routers.documents.google_drive_service.delete_file") as mock_delete:
        res = client.delete("/candidates/99901/documents/doc-uuid-1")
        assert res.status_code == 200
        mock_delete.assert_called_once_with("drive-file-xyz")
        mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.assert_called_once()


def test_drive_folder_hierarchy_structure():
    """Verify Google Drive folder hierarchy generation matches the required structure."""
    service = GoogleDriveService()
    service.service = MagicMock()

    # Mock get_or_create_folder to return predictable folder IDs
    mock_folders = {
        "CPASS": "f-cpass",
        "Odisha": "f-state",
        "Skill Academy": "f-tc",
        "BATCH-01": "f-batch",
        "99901 - Ramesh Kumar": "f-cand",
        "Salary Slips": "f-sal",
    }
    service.get_or_create_folder = MagicMock(side_effect=lambda name, parent_id=None: mock_folders.get(name, "f-any"))

    folder_id, path = service.get_or_create_candidate_subfolder(
        state="Odisha",
        tc_name="Skill Academy",
        batch_code="BATCH-01",
        candidate_id=99901,
        candidate_name="Ramesh Kumar",
        doc_type="SALARY_SLIP",
    )

    assert folder_id == "f-sal"
    assert path == "CPASS / Odisha / Skill Academy / BATCH-01 / 99901 - Ramesh Kumar / Salary Slips"


def test_admin_role_denied_l1_document_routes(mock_supabase):
    """Admin role must be denied access to L1 document verification operations (separation of duties)."""
    admin_user = CurrentUser(
        id="admin-uuid",
        email="admin@cpass.org",
        full_name="Admin User",
        role="ADMIN",
    )
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        res = client.get("/candidates/99901/documents")
        assert res.status_code == 403
        assert "Your role cannot do this." in res.json()["detail"]

        res2 = client.post("/candidates/99901/documents/submit")
        assert res2.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_batch_submit_missing_appointment_letter_rejected(mock_supabase, auth_override):
    """Batch submit must reject submission if appointment letter is missing."""
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        CANDIDATE_DATA
    ]
    mock_supabase.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = []

    res = client.post(
        "/candidates/99901/documents/submit",
        data={
            "salary_slips_meta": '[{"month": 1, "year": 2024}, {"month": 2, "year": 2024}, {"month": 3, "year": 2024}]',
            "bank_statements_meta": '[{"month": 1, "year": 2024}, {"month": 2, "year": 2024}, {"month": 3, "year": 2024}]',
        },
        files=[
            ("salary_slips", ("sal1.pdf", b"%PDF sal 1", "application/pdf")),
            ("salary_slips", ("sal2.pdf", b"%PDF sal 2", "application/pdf")),
            ("salary_slips", ("sal3.pdf", b"%PDF sal 3", "application/pdf")),
            ("bank_statements", ("bank1.pdf", b"%PDF bank 1", "application/pdf")),
            ("bank_statements", ("bank2.pdf", b"%PDF bank 2", "application/pdf")),
            ("bank_statements", ("bank3.pdf", b"%PDF bank 3", "application/pdf")),
        ],
    )
    assert res.status_code == 400
    assert "Appointment / Offer Letter is required" in res.json()["detail"]


def test_batch_submit_fewer_than_3_salary_months_rejected(mock_supabase, auth_override):
    """Batch submit must reject submission if fewer than 3 salary months provided."""
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        CANDIDATE_DATA
    ]
    mock_supabase.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = []

    res = client.post(
        "/candidates/99901/documents/submit",
        data={
            "salary_slips_meta": '[{"month": 1, "year": 2024}, {"month": 2, "year": 2024}]',
            "bank_statements_meta": '[{"month": 1, "year": 2024}, {"month": 2, "year": 2024}, {"month": 3, "year": 2024}]',
        },
        files=[
            ("appointment_letter", ("offer.pdf", b"%PDF offer", "application/pdf")),
            ("salary_slips", ("sal1.pdf", b"%PDF sal 1", "application/pdf")),
            ("salary_slips", ("sal2.pdf", b"%PDF sal 2", "application/pdf")),
            ("bank_statements", ("bank1.pdf", b"%PDF bank 1", "application/pdf")),
            ("bank_statements", ("bank2.pdf", b"%PDF bank 2", "application/pdf")),
            ("bank_statements", ("bank3.pdf", b"%PDF bank 3", "application/pdf")),
        ],
    )
    assert res.status_code == 400
    assert "At least 3 distinct salary slip months are required" in res.json()["detail"]


def test_batch_submit_duplicate_period_rejected(mock_supabase, auth_override):
    """Batch submit must reject duplicate months for salary slips or bank statements."""
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        CANDIDATE_DATA
    ]
    mock_supabase.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = []

    res = client.post(
        "/candidates/99901/documents/submit",
        data={
            "salary_slips_meta": '[{"month": 1, "year": 2024}, {"month": 1, "year": 2024}, {"month": 2, "year": 2024}]',
            "bank_statements_meta": '[{"month": 1, "year": 2024}, {"month": 2, "year": 2024}, {"month": 3, "year": 2024}]',
        },
        files=[
            ("appointment_letter", ("offer.pdf", b"%PDF offer", "application/pdf")),
            ("salary_slips", ("sal1.pdf", b"%PDF sal 1", "application/pdf")),
            ("salary_slips", ("sal1_dup.pdf", b"%PDF sal 1 dup", "application/pdf")),
            ("salary_slips", ("sal2.pdf", b"%PDF sal 2", "application/pdf")),
            ("bank_statements", ("bank1.pdf", b"%PDF bank 1", "application/pdf")),
            ("bank_statements", ("bank2.pdf", b"%PDF bank 2", "application/pdf")),
            ("bank_statements", ("bank3.pdf", b"%PDF bank 3", "application/pdf")),
        ],
    )
    assert res.status_code == 400
    assert "Duplicate salary slip for reporting period" in res.json()["detail"]


def test_batch_submit_success_with_compensation_tracking(mock_supabase, auth_override):
    """Complete successful batch submit uploads to Drive, saves DB records, and returns status: success."""
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        CANDIDATE_DATA
    ]
    mock_supabase.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = []
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{"id": "new-doc-id"}]

    with (
        patch(
            "app.routers.documents.google_drive_service.get_or_create_candidate_subfolder",
            return_value=("folder-xyz", "CPASS / Odisha / Bhubaneswar / BATCH-OD-2023-01 / 99901 - Ramesh Kumar / Subfolder"),
        ),
        patch(
            "app.routers.documents.google_drive_service.upload_file",
            return_value={"file_id": "drive-file-new", "file_name": "uploaded.pdf", "mime_type": "application/pdf", "size": 1024},
        ),
    ):
        res = client.post(
            "/candidates/99901/documents/submit",
            data={
                "salary_slips_meta": '[{"month": 1, "year": 2024}, {"month": 2, "year": 2024}, {"month": 3, "year": 2024}]',
                "bank_statements_meta": '[{"month": 1, "year": 2024}, {"month": 2, "year": 2024}, {"month": 3, "year": 2024}]',
            },
            files=[
                ("appointment_letter", ("offer.pdf", b"%PDF offer", "application/pdf")),
                ("salary_slips", ("sal1.pdf", b"%PDF sal 1", "application/pdf")),
                ("salary_slips", ("sal2.pdf", b"%PDF sal 2", "application/pdf")),
                ("salary_slips", ("sal3.pdf", b"%PDF sal 3", "application/pdf")),
                ("bank_statements", ("bank1.pdf", b"%PDF bank 1", "application/pdf")),
                ("bank_statements", ("bank2.pdf", b"%PDF bank 2", "application/pdf")),
                ("bank_statements", ("bank3.pdf", b"%PDF bank 3", "application/pdf")),
            ],
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["submitted_count"] == 7
        assert data["candidate_id"] == 99901


def test_batch_submit_database_failure_rolls_back_drive_files(mock_supabase, auth_override):
    """Database persistence failure must trigger compensation rollback of created Google Drive files."""
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        CANDIDATE_DATA
    ]
    mock_supabase.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = []
    mock_supabase.table.return_value.insert.return_value.execute.side_effect = Exception("DB Connection Lost")

    with (
        patch(
            "app.routers.documents.google_drive_service.get_or_create_candidate_subfolder",
            return_value=("folder-xyz", "path"),
        ),
        patch(
            "app.routers.documents.google_drive_service.upload_file",
            return_value={"file_id": "drive-file-created", "file_name": "uploaded.pdf", "mime_type": "application/pdf", "size": 1024},
        ),
        patch("app.routers.documents.google_drive_service.delete_file") as mock_delete,
    ):
        res = client.post(
            "/candidates/99901/documents/submit",
            data={
                "salary_slips_meta": '[{"month": 1, "year": 2024}, {"month": 2, "year": 2024}, {"month": 3, "year": 2024}]',
                "bank_statements_meta": '[{"month": 1, "year": 2024}, {"month": 2, "year": 2024}, {"month": 3, "year": 2024}]',
            },
            files=[
                ("appointment_letter", ("offer.pdf", b"%PDF offer", "application/pdf")),
                ("salary_slips", ("sal1.pdf", b"%PDF sal 1", "application/pdf")),
                ("salary_slips", ("sal2.pdf", b"%PDF sal 2", "application/pdf")),
                ("salary_slips", ("sal3.pdf", b"%PDF sal 3", "application/pdf")),
                ("bank_statements", ("bank1.pdf", b"%PDF bank 1", "application/pdf")),
                ("bank_statements", ("bank2.pdf", b"%PDF bank 2", "application/pdf")),
                ("bank_statements", ("bank3.pdf", b"%PDF bank 3", "application/pdf")),
            ],
        )
        assert res.status_code == 500
        assert "Database persistence failed" in res.json()["detail"]
        assert mock_delete.call_count >= 1


def test_batch_submit_database_failure_restores_replaced_document(mock_supabase, auth_override):
    """If DB persistence fails during batch submission, an existing replaced document is restored, not deleted."""
    existing_app = {
        "id": "doc-app-orig",
        "candidate_id": 99901,
        "document_type": "APPOINTMENT_LETTER",
        "drive_file_id": "drive-app-orig",
        "file_name": "original_offer.pdf",
        "mime_type": "application/pdf",
        "file_size_bytes": 5000,
        "upload_status": "SUCCESS",
    }
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        CANDIDATE_DATA
    ]
    mock_supabase.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = [
        existing_app
    ]

    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{"id": "doc-app-orig"}]
    mock_supabase.table.return_value.insert.return_value.execute.side_effect = Exception("DB Insert Error")

    with (
        patch(
            "app.routers.documents.google_drive_service.get_or_create_candidate_subfolder",
            return_value=("folder-xyz", "path"),
        ),
        patch(
            "app.routers.documents.google_drive_service.upload_file",
            return_value={"file_id": "drive-file-new", "file_name": "uploaded.pdf", "mime_type": "application/pdf", "size": 1024},
        ),
        patch("app.routers.documents.google_drive_service.delete_file") as mock_delete,
    ):
        res = client.post(
            "/candidates/99901/documents/submit",
            data={
                "appointment_replace_id": "doc-app-orig",
                "salary_slips_meta": '[{"month": 1, "year": 2024}, {"month": 2, "year": 2024}, {"month": 3, "year": 2024}]',
                "bank_statements_meta": '[{"month": 1, "year": 2024}, {"month": 2, "year": 2024}, {"month": 3, "year": 2024}]',
            },
            files=[
                ("appointment_letter", ("new_offer.pdf", b"%PDF new offer", "application/pdf")),
                ("salary_slips", ("sal1.pdf", b"%PDF sal 1", "application/pdf")),
                ("salary_slips", ("sal2.pdf", b"%PDF sal 2", "application/pdf")),
                ("salary_slips", ("sal3.pdf", b"%PDF sal 3", "application/pdf")),
                ("bank_statements", ("bank1.pdf", b"%PDF bank 1", "application/pdf")),
                ("bank_statements", ("bank2.pdf", b"%PDF bank 2", "application/pdf")),
                ("bank_statements", ("bank3.pdf", b"%PDF bank 3", "application/pdf")),
            ],
        )
        assert res.status_code == 500
        assert "Database persistence failed" in res.json()["detail"]
        assert mock_supabase.table.return_value.update.called


def test_batch_submit_cleanup_warning_surfaced_when_old_drive_delete_fails(mock_supabase, auth_override):
    """When a replacement succeeds but deleting the old Drive file encounters an error, a cleanup warning is returned."""
    existing_app = {
        "id": "doc-app-orig",
        "candidate_id": 99901,
        "document_type": "APPOINTMENT_LETTER",
        "drive_file_id": "drive-app-orig",
        "file_name": "original_offer.pdf",
        "mime_type": "application/pdf",
        "file_size_bytes": 5000,
        "upload_status": "SUCCESS",
    }
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        CANDIDATE_DATA
    ]
    mock_supabase.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = [
        existing_app
    ]
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{"id": "doc-app-orig"}]
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{"id": "new-sal"}]

    def mock_del(fid):
        if fid == "drive-app-orig":
            raise Exception("Drive API Permission Denied on Old File")
        return None

    with (
        patch(
            "app.routers.documents.google_drive_service.get_or_create_candidate_subfolder",
            return_value=("folder-xyz", "path"),
        ),
        patch(
            "app.routers.documents.google_drive_service.upload_file",
            return_value={"file_id": "drive-file-new", "file_name": "uploaded.pdf", "mime_type": "application/pdf", "size": 1024},
        ),
        patch("app.routers.documents.google_drive_service.delete_file", side_effect=mock_del),
    ):
        res = client.post(
            "/candidates/99901/documents/submit",
            data={
                "appointment_replace_id": "doc-app-orig",
                "salary_slips_meta": '[{"month": 1, "year": 2024}, {"month": 2, "year": 2024}, {"month": 3, "year": 2024}]',
                "bank_statements_meta": '[{"month": 1, "year": 2024}, {"month": 2, "year": 2024}, {"month": 3, "year": 2024}]',
            },
            files=[
                ("appointment_letter", ("new_offer.pdf", b"%PDF new offer", "application/pdf")),
                ("salary_slips", ("sal1.pdf", b"%PDF sal 1", "application/pdf")),
                ("salary_slips", ("sal2.pdf", b"%PDF sal 2", "application/pdf")),
                ("salary_slips", ("sal3.pdf", b"%PDF sal 3", "application/pdf")),
                ("bank_statements", ("bank1.pdf", b"%PDF bank 1", "application/pdf")),
                ("bank_statements", ("bank2.pdf", b"%PDF bank 2", "application/pdf")),
                ("bank_statements", ("bank3.pdf", b"%PDF bank 3", "application/pdf")),
            ],
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert len(data["cleanup_warnings"]) == 1
        assert "drive-app-orig" in data["cleanup_warnings"][0]


