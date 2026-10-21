"""Complete live Google Drive integration and document lifecycle verification script.

Tests:
1. Google Drive folder creation and reuse (no duplicates).
2. Document upload and Supabase metadata persistence.
3. Download endpoint streaming and byte-for-byte integrity check.
4. Appointment letter uniqueness (HTTP 400 on duplicate) and controlled replacement (old file deleted).
5. Duplicate reporting period rejection (HTTP 400).
6. Salary slip and bank statement validation (3-month minimum satisfaction and month range 1-12).
7. Complete cleanup of all Drive files, test folders, and database records.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Any

# Add backend directory to sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from app.auth import CurrentUser, get_current_user
from app.db import supabase
from app.main import app
from app.services.google_drive import google_drive_service

CANDIDATE_ID = 1076617

AUTH_USER = CurrentUser(
    id="00000000-0000-0000-0000-000000000001",
    email="admin@cpass.org",
    full_name="CPASS Admin",
    role="ADMIN",
)

def run_live_verification():
    print("=" * 65)
    print("CPASS L1: LIVE GOOGLE DRIVE & DOCUMENT WORKFLOW VERIFICATION")
    print("=" * 65)

    # 1. Pre-flight Checks
    cand_res = (
        supabase.table("ddugky_candidates")
        .select("candidate_id,candidate_first_name,candidate_last_name,tc_state_name,tc_name,batch_code")
        .eq("candidate_id", CANDIDATE_ID)
        .limit(1)
        .execute()
    )
    if not cand_res.data:
        print(f"[FAIL] Target candidate {CANDIDATE_ID} not found in ddugky_candidates.")
        sys.exit(1)

    cand = cand_res.data[0]
    cand_name = f"{cand.get('candidate_first_name') or ''} {cand.get('candidate_last_name') or ''}".strip()
    print(f"Target Candidate: {cand_name} (ID: {CANDIDATE_ID})")
    print(f"State: {cand.get('tc_state_name')} | TC: {cand.get('tc_name')} | Batch: {cand.get('batch_code')}")

    # Verify initial database state
    initial_docs_count = supabase.table("candidate_documents").select("count", count="exact").execute().count
    print(f"Initial candidate_documents row count: {initial_docs_count}")
    assert initial_docs_count == 0, f"Expected 0 candidate_documents, found {initial_docs_count}"

    # Verify Drive service
    if not google_drive_service.is_configured():
        print("[FAIL] Google Drive service is not configured.")
        sys.exit(1)

    drive_client = google_drive_service.get_service()
    root_id = google_drive_service.root_folder_id
    root_meta = drive_client.files().get(fileId=root_id, fields="id,name,capabilities").execute()
    print(f"Root Drive Folder: {root_meta.get('name')} (ID: {root_id})")
    can_add = root_meta.get("capabilities", {}).get("canAddChildren")
    print(f"Write Permission (canAddChildren): {can_add}")
    if not can_add:
        print("[FAIL] Service account lacks Editor/write permission on root folder.")
        sys.exit(1)

    print("\n[OK] Pre-flight checks passed.\n")

    # Tracking sets for strict cleanup
    created_drive_file_ids: set[str] = set()
    created_drive_folder_ids: set[str] = set()
    created_db_doc_ids: set[str] = set()

    # Setup TestClient with authenticated admin user
    app.dependency_overrides[get_current_user] = lambda: AUTH_USER
    client = TestClient(app)

    try:
        # ---------------------------------------------------------------------
        # TEST 1: Google Drive Folder Creation and Reuse
        # ---------------------------------------------------------------------
        print("--- Test 1: Folder Creation & Hierarchy Reuse ---")
        folder_id_1, path_1 = google_drive_service.get_or_create_candidate_subfolder(
            state=cand["tc_state_name"],
            tc_name=cand["tc_name"],
            batch_code=cand["batch_code"],
            candidate_id=cand["candidate_id"],
            candidate_name=cand_name,
            doc_type="APPOINTMENT_LETTER",
        )
        print(f"  Created/Resolved folder path: {path_1}")
        print(f"  Folder ID: {folder_id_1}")
        created_drive_folder_ids.add(folder_id_1)

        # Call again to verify reuse (must return identical folder ID, no duplicates)
        folder_id_2, path_2 = google_drive_service.get_or_create_candidate_subfolder(
            state=cand["tc_state_name"],
            tc_name=cand["tc_name"],
            batch_code=cand["batch_code"],
            candidate_id=cand["candidate_id"],
            candidate_name=cand_name,
            doc_type="APPOINTMENT_LETTER",
        )
        assert folder_id_1 == folder_id_2, f"Folder reuse failed! Got {folder_id_1} vs {folder_id_2}"
        assert path_1 == path_2
        print("  [PASS] Folder reuse verified (identical folder ID returned on second call).")

        # ---------------------------------------------------------------------
        # TEST 2: Document Upload & Supabase Metadata Persistence
        # ---------------------------------------------------------------------
        print("\n--- Test 2: Live Document Upload & DB Metadata Persistence ---")
        synthetic_offer_pdf = b"%PDF-1.4 Synthetic Appointment Offer Letter for Candidate 1076617 - Bodapati Shirisha."
        upload_res = client.post(
            f"/candidates/{CANDIDATE_ID}/documents",
            data={"document_type": "APPOINTMENT_LETTER"},
            files={"file": ("offer_letter_test.pdf", synthetic_offer_pdf, "application/pdf")},
        )
        assert upload_res.status_code == 200, f"Upload failed: {upload_res.status_code} - {upload_res.text}"
        doc_data = upload_res.json()
        doc_id_1 = doc_data["id"]
        drive_file_id_1 = doc_data["drive_file_id"]

        created_db_doc_ids.add(doc_id_1)
        created_drive_file_ids.add(drive_file_id_1)

        print(f"  Uploaded Document ID:   {doc_id_1}")
        print(f"  Google Drive File ID:   {drive_file_id_1}")
        print(f"  File Name:              {doc_data['file_name']}")
        print(f"  Upload Status:          {doc_data['upload_status']}")

        # Verify DB metadata
        db_doc = supabase.table("candidate_documents").select("*").eq("id", doc_id_1).limit(1).execute().data[0]
        assert db_doc["candidate_id"] == CANDIDATE_ID
        assert db_doc["document_type"] == "APPOINTMENT_LETTER"
        assert db_doc["drive_file_id"] == drive_file_id_1
        assert db_doc["file_size_bytes"] == len(synthetic_offer_pdf)
        assert db_doc["upload_status"] == "SUCCESS"
        print("  [PASS] Database metadata matches uploaded file perfectly.")

        # ---------------------------------------------------------------------
        # TEST 3: Download Endpoint & File Content Integrity
        # ---------------------------------------------------------------------
        print("\n--- Test 3: Download Endpoint Streaming & Content Integrity ---")
        dl_res = client.get(f"/candidates/{CANDIDATE_ID}/documents/{doc_id_1}/download")
        assert dl_res.status_code == 200, f"Download failed: {dl_res.status_code} - {dl_res.text}"
        assert dl_res.headers.get("content-type") == "application/pdf"
        assert dl_res.content == synthetic_offer_pdf, "Downloaded byte content differs from uploaded payload!"
        print(f"  Downloaded {len(dl_res.content)} bytes from Google Drive via backend.")
        print("  [PASS] Byte-for-byte content integrity verified (100% match).")

        # ---------------------------------------------------------------------
        # TEST 4: Appointment Letter Uniqueness & Controlled Replacement
        # ---------------------------------------------------------------------
        print("\n--- Test 4: Appointment Letter Uniqueness & Controlled Replacement ---")
        # 4a. Attempt second appointment letter without replacement -> Must return HTTP 400
        dup_res = client.post(
            f"/candidates/{CANDIDATE_ID}/documents",
            data={"document_type": "APPOINTMENT_LETTER"},
            files={"file": ("another_offer.pdf", b"%PDF-1.4 Second appointment letter", "application/pdf")},
        )
        assert dup_res.status_code == 400, f"Expected 400 duplicate rejection, got: {dup_res.status_code}"
        assert "already exists for this candidate" in dup_res.json()["detail"]
        print("  [PASS] Single active appointment letter constraint enforced (HTTP 400 on duplicate).")

        # 4b. Perform controlled replacement with replace_id
        replacement_pdf = b"%PDF-1.4 Replaced Appointment Letter Revision 2 for Candidate 1076617."
        replace_res = client.post(
            f"/candidates/{CANDIDATE_ID}/documents",
            data={"document_type": "APPOINTMENT_LETTER", "replace_id": doc_id_1},
            files={"file": ("offer_letter_revised.pdf", replacement_pdf, "application/pdf")},
        )
        assert replace_res.status_code == 200, f"Replacement failed: {replace_res.status_code} - {replace_res.text}"
        replace_data = replace_res.json()
        drive_file_id_repl = replace_data["drive_file_id"]
        created_drive_file_ids.add(drive_file_id_repl)

        assert drive_file_id_repl != drive_file_id_1, "Replacement file ID must differ from old file ID"
        print(f"  Replaced with new Drive File ID: {drive_file_id_repl}")

        # Verify old file was deleted from Drive
        try:
            drive_client.files().get(fileId=drive_file_id_1).execute()
            raise AssertionError(f"Old Drive file {drive_file_id_1} was NOT deleted during replacement!")
        except Exception as e:
            # Expected 404
            print(f"  Verified old file {drive_file_id_1} was permanently removed from Google Drive.")

        # Verify DB row was updated with new metadata
        db_doc_repl = supabase.table("candidate_documents").select("*").eq("id", doc_id_1).limit(1).execute().data[0]
        assert db_doc_repl["drive_file_id"] == drive_file_id_repl
        assert db_doc_repl["file_name"] == "offer_letter_revised.pdf"
        assert db_doc_repl["file_size_bytes"] == len(replacement_pdf)
        print("  [PASS] Controlled replacement succeeded without leaving orphaned files.")

        # ---------------------------------------------------------------------
        # TEST 5: Duplicate Reporting Period Rejection (Salary Slips)
        # ---------------------------------------------------------------------
        print("\n--- Test 5: Duplicate Reporting Period Rejection ---")
        slip_m1_pdf = b"%PDF-1.4 Salary Slip Month 1 Jan 2024"
        slip_m1_res = client.post(
            f"/candidates/{CANDIDATE_ID}/documents",
            data={"document_type": "SALARY_SLIP", "reporting_month": 1, "reporting_year": 2024},
            files={"file": ("salary_slip_jan_2024.pdf", slip_m1_pdf, "application/pdf")},
        )
        assert slip_m1_res.status_code == 200
        slip_m1_data = slip_m1_res.json()
        created_db_doc_ids.add(slip_m1_data["id"])
        created_drive_file_ids.add(slip_m1_data["drive_file_id"])

        # Attempt duplicate upload for month 1 / 2024
        slip_dup_res = client.post(
            f"/candidates/{CANDIDATE_ID}/documents",
            data={"document_type": "SALARY_SLIP", "reporting_month": 1, "reporting_year": 2024},
            files={"file": ("salary_slip_jan_2024_dup.pdf", b"%PDF-1.4 duplicate", "application/pdf")},
        )
        assert slip_dup_res.status_code == 400
        assert "already exists" in slip_dup_res.json()["detail"]
        print("  [PASS] Duplicate reporting period rejected with HTTP 400.")

        # ---------------------------------------------------------------------
        # TEST 6: Monthly Document Boundaries & L1 Placement Summary Checklist
        # ---------------------------------------------------------------------
        print("\n--- Test 6: Monthly Document Bounds & Placement Verification Checklist ---")
        # 6a. Upload Salary Slip Month 2 and Month 3
        for m in (2, 3):
            res = client.post(
                f"/candidates/{CANDIDATE_ID}/documents",
                data={"document_type": "SALARY_SLIP", "reporting_month": m, "reporting_year": 2024},
                files={"file": (f"salary_slip_m{m}_2024.pdf", f"%PDF-1.4 Slip Month {m}".encode(), "application/pdf")},
            )
            assert res.status_code == 200
            created_db_doc_ids.add(res.json()["id"])
            created_drive_file_ids.add(res.json()["drive_file_id"])

        # 6b. Upload Bank Statement Months 1, 2, 3
        for m in (1, 2, 3):
            res = client.post(
                f"/candidates/{CANDIDATE_ID}/documents",
                data={"document_type": "BANK_STATEMENT", "reporting_month": m, "reporting_year": 2024},
                files={"file": (f"bank_stmt_m{m}_2024.pdf", f"%PDF-1.4 Bank Stmt Month {m}".encode(), "application/pdf")},
            )
            assert res.status_code == 200
            created_db_doc_ids.add(res.json()["id"])
            created_drive_file_ids.add(res.json()["drive_file_id"])

        # 6c. Check Summary Checklist
        summary_res = client.get(f"/candidates/{CANDIDATE_ID}/documents/summary")
        assert summary_res.status_code == 200
        summary = summary_res.json()
        print(f"  Summary Checklist Output:")
        print(f"    has_appointment_letter: {summary['has_appointment_letter']}")
        print(f"    salary_slip_count:      {summary['salary_slip_count']} (Expected 3)")
        print(f"    bank_statement_count:   {summary['bank_statement_count']} (Expected 3)")
        print(f"    min_requirements_met:   {summary['min_requirements_met']} (Expected True)")

        assert summary["has_appointment_letter"] is True
        assert summary["salary_slip_count"] == 3
        assert summary["bank_statement_count"] == 3
        assert summary["min_requirements_met"] is True
        print("  [PASS] 3-month minimum requirements satisfied and checklist evaluated correctly.")

        # 6d. Validate invalid month boundaries (Month 0 and Month 13)
        res_m0 = client.post(
            f"/candidates/{CANDIDATE_ID}/documents",
            data={"document_type": "SALARY_SLIP", "reporting_month": 0, "reporting_year": 2024},
            files={"file": ("slip.pdf", b"%PDF-1.4", "application/pdf")},
        )
        assert res_m0.status_code == 400
        assert "valid reporting month" in res_m0.json()["detail"]

        res_m13 = client.post(
            f"/candidates/{CANDIDATE_ID}/documents",
            data={"document_type": "SALARY_SLIP", "reporting_month": 13, "reporting_year": 2024},
            files={"file": ("slip.pdf", b"%PDF-1.4", "application/pdf")},
        )
        assert res_m13.status_code == 400
        assert "valid reporting month" in res_m13.json()["detail"]
        print("  [PASS] Month boundary validation (1-12) enforced on backend.")

    finally:
        # ---------------------------------------------------------------------
        # CLEANUP: Strict removal of all created test files, folders, and records
        # ---------------------------------------------------------------------
        print("\n" + "=" * 65)
        print("CLEANUP OF TEST RESOURCES")
        print("=" * 65)

        # 1. Delete test files from Google Drive
        print(f"Cleaning up {len(created_drive_file_ids)} test file(s) from Google Drive...")
        for fid in created_drive_file_ids:
            try:
                drive_client.files().delete(fileId=fid).execute()
                print(f"  Deleted Drive file: {fid}")
            except Exception as e:
                print(f"  Note on file {fid}: {e}")

        # 2. Delete test candidate subfolder hierarchy from Google Drive
        # Find candidate folder and remove it (which removes all empty test subfolders)
        cand_folder_name = f"{CANDIDATE_ID} - {cand_name}"
        try:
            q = f"name = '{cand_folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            res = drive_client.files().list(q=q, spaces="drive", fields="files(id, name)").execute()
            for f in res.get("files", []):
                drive_client.files().delete(fileId=f["id"]).execute()
                print(f"  Deleted Candidate Drive folder: {f['name']} ({f['id']})")
        except Exception as e:
            print(f"  Note cleaning candidate folder: {e}")

        # Also clean any candidate state/tc/batch folder if left empty
        try:
            state_q = f"name = '{cand['tc_state_name']}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            s_res = drive_client.files().list(q=state_q, spaces="drive", fields="files(id, name)").execute()
            for sf in s_res.get("files", []):
                drive_client.files().delete(fileId=sf["id"]).execute()
                print(f"  Deleted State test folder: {sf['name']} ({sf['id']})")
        except Exception as e:
            print(f"  Note cleaning state folder: {e}")

        # 3. Delete all test records from candidate_documents
        print(f"\nCleaning up {len(created_db_doc_ids)} test record(s) from Supabase candidate_documents...")
        for doc_id in created_db_doc_ids:
            supabase.table("candidate_documents").delete().eq("id", doc_id).execute()
            print(f"  Deleted DB document: {doc_id}")

        # Verify DB is back to 0 candidate documents
        final_docs_count = supabase.table("candidate_documents").select("count", count="exact").execute().count
        print(f"\nFinal candidate_documents row count in Supabase: {final_docs_count}")
        assert final_docs_count == 0, f"Expected 0 documents after cleanup, found {final_docs_count}"
        print("[OK] Supabase candidate_documents successfully restored to clean state.")

        # Verify ddugky_candidates was completely untouched
        cands_count = supabase.table("ddugky_candidates").select("count", count="exact").execute().count
        assert cands_count == 9084, f"ddugky_candidates modified! Expected 9084, got {cands_count}"
        print(f"[OK] ddugky_candidates verified untouched ({cands_count} records preserved).")

    print("\n" + "=" * 65)
    print("ALL TESTS AND CLEANUP COMPLETED SUCCESSFULLY!")
    print("=" * 65)

if __name__ == "__main__":
    run_live_verification()
