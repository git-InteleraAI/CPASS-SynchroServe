"""FastAPI router for candidate documents with Google Drive integration.

Manages:
- At most one active Appointment/Offer Letter per candidate.
- Salary Slips (min 3, max 12 distinct reporting months).
- Bank Statements (min 3, max 12 distinct reporting months).
- Duplicate prevention per reporting period.
- Controlled document replacement.
- Secure authorized preview/download streaming.
- Atomic batch submission with rollback compensation for staged documents.
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..auth import CurrentUser, get_current_user, require_roles
from ..db import supabase
from ..services.google_drive import (
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE_BYTES,
    GoogleDriveNotConfiguredError,
    GoogleDriveService,
    google_drive_service,
)

logger = logging.getLogger("cpass.documents")

router = APIRouter(prefix="/candidates/{candidate_id}/documents", tags=["documents"])

VALID_DOCUMENT_TYPES = {"APPOINTMENT_LETTER", "SALARY_SLIP", "BANK_STATEMENT"}


def _get_candidate_context(candidate_id: int) -> dict[str, Any]:
    """Retrieve candidate context from ddugky_candidates for folder organization."""
    res = (
        supabase.table("ddugky_candidates")
        .select("candidate_id,candidate_first_name,candidate_last_name,tc_state_name,state_name,tc_name,batch_code")
        .eq("candidate_id", candidate_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, f"Candidate {candidate_id} not found.")
    c = res.data[0]
    return {
        "candidate_id": c["candidate_id"],
        "candidate_name": f"{c.get('candidate_first_name') or ''} {c.get('candidate_last_name') or ''}".strip() or f"Candidate {candidate_id}",
        "state": c.get("tc_state_name") or c.get("state_name") or "State",
        "tc_name": c.get("tc_name") or "Centre",
        "batch_code": c.get("batch_code") or "Batch",
    }


def _validate_file_upload(file_name: str, content: bytes, mime_type: str | None) -> str:
    """Validate format and size of uploaded file, returning normalized mime_type."""
    if not content:
        raise HTTPException(400, f"File '{file_name}' is empty.")
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(400, f"File size exceeds limit: '{file_name}' exceeds size limit of {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB.")
    mime = (mime_type or "application/octet-stream").lower()
    if mime not in ALLOWED_MIME_TYPES:
        ext = file_name.split(".")[-1].lower() if "." in file_name else ""
        if ext == "pdf":
            mime = "application/pdf"
        elif ext in ("jpg", "jpeg"):
            mime = "image/jpeg"
        elif ext == "png":
            mime = "image/png"
        else:
            raise HTTPException(400, f"Unsupported file format for '{file_name}'. Allowed formats: PDF, PNG, JPG/JPEG.")
    return mime


@router.get("")
def list_documents(
    candidate_id: int,
    user: CurrentUser = Depends(require_roles("L1_COORDINATOR")),
):
    """List all documents uploaded for this candidate."""
    _get_candidate_context(candidate_id)
    res = (
        supabase.table("candidate_documents")
        .select("id,candidate_id,document_type,reporting_month,reporting_year,drive_file_id,drive_folder_path,file_name,mime_type,file_size_bytes,upload_status,created_at,updated_at")
        .eq("candidate_id", candidate_id)
        .neq("upload_status", "FAILED")
        .order("created_at")
        .execute()
    )
    return res.data or []


@router.get("/summary")
def get_documents_summary(
    candidate_id: int,
    user: CurrentUser = Depends(require_roles("L1_COORDINATOR")),
):
    """Get the L1 checklist summary for a candidate.

    Computes:
    - Appointment letter status
    - Salary slips count (min 3, max 12)
    - Bank statements count (min 3, max 12)
    - Whether all minimum placement requirements are satisfied.
    """
    _get_candidate_context(candidate_id)
    res = (
        supabase.table("candidate_documents")
        .select("id,document_type,reporting_month,reporting_year,file_name,mime_type,file_size_bytes,upload_status,created_at")
        .eq("candidate_id", candidate_id)
        .neq("upload_status", "FAILED")
        .execute()
    )
    docs = res.data or []

    appointment_doc = next((d for d in docs if d["document_type"] == "APPOINTMENT_LETTER"), None)
    has_appointment = appointment_doc is not None

    salary_slips = sorted(
        [d for d in docs if d["document_type"] == "SALARY_SLIP"],
        key=lambda d: (d.get("reporting_year") or 0, d.get("reporting_month") or 0),
    )
    salary_slip_months = {(d["reporting_year"], d["reporting_month"]) for d in salary_slips if d.get("reporting_month") and d.get("reporting_year")}
    salary_count = len(salary_slip_months)

    bank_statements = sorted(
        [d for d in docs if d["document_type"] == "BANK_STATEMENT"],
        key=lambda d: (d.get("reporting_year") or 0, d.get("reporting_month") or 0),
    )
    bank_statement_months = {(d["reporting_year"], d["reporting_month"]) for d in bank_statements if d.get("reporting_month") and d.get("reporting_year")}
    bank_count = len(bank_statement_months)

    min_satisfied = has_appointment and salary_count >= 3 and bank_count >= 3

    checklist = [
        {
            "item": "Appointment / Offer Letter",
            "required": True,
            "satisfied": has_appointment,
            "detail": f"Uploaded: {appointment_doc['file_name']}" if has_appointment else "Missing",
        },
        {
            "item": "Salary Slips",
            "required": True,
            "min_required": 3,
            "max_allowed": 12,
            "count": salary_count,
            "satisfied": salary_count >= 3,
            "detail": f"{salary_count} of 3 minimum months uploaded (max 12)" if salary_count < 3 else f"{salary_count} months uploaded",
        },
        {
            "item": "Bank Statements",
            "required": True,
            "min_required": 3,
            "max_allowed": 12,
            "count": bank_count,
            "satisfied": bank_count >= 3,
            "detail": f"{bank_count} of 3 minimum months uploaded (max 12)" if bank_count < 3 else f"{bank_count} months uploaded",
        },
    ]

    return {
        "candidate_id": candidate_id,
        "has_appointment_letter": has_appointment,
        "appointment_letter": appointment_doc,
        "salary_slip_count": salary_count,
        "salary_slips": salary_slips,
        "bank_statement_count": bank_count,
        "bank_statements": bank_statements,
        "min_requirements_met": min_satisfied,
        "checklist": checklist,
    }


@router.post("")
async def upload_document(
    candidate_id: int,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    reporting_month: int | None = Form(None),
    reporting_year: int | None = Form(None),
    replace_id: str | None = Form(None),
    user: CurrentUser = Depends(require_roles("L1_COORDINATOR")),
):
    """Upload a candidate document to Google Drive and persist metadata in candidate_documents."""
    doc_type = document_type.strip().upper()
    if doc_type not in VALID_DOCUMENT_TYPES:
        raise HTTPException(
            400,
            f"Invalid document_type '{document_type}'. Allowed types: {', '.join(sorted(VALID_DOCUMENT_TYPES))}",
        )

    content = await file.read()
    mime_type = _validate_file_upload(file.filename or "document.pdf", content, file.content_type)
    cand_ctx = _get_candidate_context(candidate_id)

    # Document-specific business rules
    if doc_type == "APPOINTMENT_LETTER":
        reporting_month = None
        reporting_year = None
        existing = (
            supabase.table("candidate_documents")
            .select("id,drive_file_id")
            .eq("candidate_id", candidate_id)
            .eq("document_type", "APPOINTMENT_LETTER")
            .neq("upload_status", "FAILED")
            .execute()
            .data
        )
        if existing and not replace_id:
            raise HTTPException(
                400,
                "An active appointment/offer letter already exists for this candidate. Use replacement to update it.",
            )
        if existing and replace_id and existing[0]["id"] != replace_id:
            raise HTTPException(400, "Replacement target does not match existing appointment letter.")

    elif doc_type in ("SALARY_SLIP", "BANK_STATEMENT"):
        if not reporting_month or reporting_month < 1 or reporting_month > 12:
            raise HTTPException(400, "A valid reporting month (1-12) is required.")
        if not reporting_year or reporting_year < 2000 or reporting_year > 2050:
            raise HTTPException(400, "A valid reporting year (e.g. 2023) is required.")

        existing_period = (
            supabase.table("candidate_documents")
            .select("id,drive_file_id")
            .eq("candidate_id", candidate_id)
            .eq("document_type", doc_type)
            .eq("reporting_month", reporting_month)
            .eq("reporting_year", reporting_year)
            .neq("upload_status", "FAILED")
            .execute()
            .data
        )
        if existing_period and not replace_id:
            doc_name = "Salary slip" if doc_type == "SALARY_SLIP" else "Bank statement"
            raise HTTPException(
                400,
                f"{doc_name} for month {reporting_month}/{reporting_year} already exists. Use replacement to update it.",
            )

        if not replace_id and not existing_period:
            all_for_type = (
                supabase.table("candidate_documents")
                .select("reporting_month,reporting_year")
                .eq("candidate_id", candidate_id)
                .eq("document_type", doc_type)
                .neq("upload_status", "FAILED")
                .execute()
                .data
            )
            distinct_months = {(d["reporting_year"], d["reporting_month"]) for d in (all_for_type or [])}
            if len(distinct_months) >= 12:
                raise HTTPException(
                    400,
                    f"Maximum limit of 12 distinct months reached for {doc_type.replace('_', ' ').title()}.",
                )

    old_drive_file_id = None
    if replace_id:
        existing_doc = (
            supabase.table("candidate_documents")
            .select("drive_file_id")
            .eq("id", replace_id)
            .limit(1)
            .execute()
            .data
        )
        if existing_doc and existing_doc[0].get("drive_file_id"):
            old_drive_file_id = existing_doc[0]["drive_file_id"]

    try:
        dest_folder_id, folder_path = google_drive_service.get_or_create_candidate_subfolder(
            state=cand_ctx["state"],
            tc_name=cand_ctx["tc_name"],
            batch_code=cand_ctx["batch_code"],
            candidate_id=cand_ctx["candidate_id"],
            candidate_name=cand_ctx["candidate_name"],
            doc_type=doc_type,
        )
        drive_res = google_drive_service.upload_file(
            content_bytes=content,
            file_name=file.filename or f"doc_{candidate_id}_{doc_type}",
            mime_type=mime_type,
            destination_folder_id=dest_folder_id,
        )
    except GoogleDriveNotConfiguredError:
        raise HTTPException(
            503,
            "Google Drive integration is not configured on the backend. "
            "Please configure GOOGLE_SERVICE_ACCOUNT_FILE or OAuth credentials in backend/.env.",
        )
    except Exception as e:
        raise HTTPException(502, f"Failed to upload document to Google Drive: {e}")

    doc_payload: dict[str, Any] = {
        "candidate_id": candidate_id,
        "document_type": doc_type,
        "reporting_month": reporting_month,
        "reporting_year": reporting_year,
        "drive_file_id": drive_res["file_id"],
        "drive_folder_id": dest_folder_id,
        "drive_folder_path": folder_path,
        "file_name": drive_res["file_name"],
        "mime_type": drive_res["mime_type"],
        "file_size_bytes": drive_res["size"],
        "upload_status": "SUCCESS",
        "uploaded_by": user.id,
        "error_message": None,
    }

    try:
        if replace_id:
            db_res = (
                supabase.table("candidate_documents")
                .update(doc_payload)
                .eq("id", replace_id)
                .execute()
            )
            if old_drive_file_id and old_drive_file_id != drive_res["file_id"]:
                google_drive_service.delete_file(old_drive_file_id)
        else:
            db_res = (
                supabase.table("candidate_documents")
                .insert(doc_payload)
                .execute()
            )
    except Exception as e:
        google_drive_service.delete_file(drive_res["file_id"])
        raise HTTPException(500, f"Document metadata could not be saved to the database: {e}")

    return db_res.data[0] if db_res.data else doc_payload


@router.post("/submit")
async def batch_submit_documents(
    candidate_id: int,
    appointment_letter: UploadFile | None = File(None),
    appointment_replace_id: str | None = Form(None),
    salary_slips: list[UploadFile] = File(default=[]),
    salary_slips_meta: str = Form("[]"),
    bank_statements: list[UploadFile] = File(default=[]),
    bank_statements_meta: str = Form("[]"),
    user: CurrentUser = Depends(require_roles("L1_COORDINATOR")),
):
    """Atomic batch final submission of all staged candidate documents.

    Validates complete placement package requirements before any external uploads.
    Includes Google Drive upload rollback if database persistence fails.
    """
    cand_ctx = _get_candidate_context(candidate_id)

    # 1. Parse metadata
    try:
        salary_meta = json.loads(salary_slips_meta)
    except Exception:
        raise HTTPException(400, "Invalid salary_slips_meta JSON format.")
    try:
        bank_meta = json.loads(bank_statements_meta)
    except Exception:
        raise HTTPException(400, "Invalid bank_statements_meta JSON format.")

    if len(salary_slips) != len(salary_meta):
        raise HTTPException(
            400,
            f"Count mismatch: {len(salary_slips)} salary slip files provided for {len(salary_meta)} metadata entries.",
        )
    if len(bank_statements) != len(bank_meta):
        raise HTTPException(
            400,
            f"Count mismatch: {len(bank_statements)} bank statement files provided for {len(bank_meta)} metadata entries.",
        )

    # 2. Query existing documents in DB
    existing_docs = (
        supabase.table("candidate_documents")
        .select("*")
        .eq("candidate_id", candidate_id)
        .neq("upload_status", "FAILED")
        .execute()
        .data or []
    )
    existing_docs_by_id = {d["id"]: dict(d) for d in existing_docs}
    existing_appointment = next((d for d in existing_docs if d["document_type"] == "APPOINTMENT_LETTER"), None)

    # 3. Validate Appointment Letter
    if not existing_appointment and not appointment_letter:
        raise HTTPException(400, "An Appointment / Offer Letter is required for placement verification.")
    if existing_appointment and appointment_letter and not appointment_replace_id:
        raise HTTPException(400, "An active appointment letter already exists. Specify replacement ID to update it.")
    if existing_appointment and appointment_letter and appointment_replace_id and existing_appointment["id"] != appointment_replace_id:
        raise HTTPException(400, "Replacement target does not match existing appointment letter.")

    # 4. Validate Salary Slips
    replaced_salary_ids = {m["replace_id"] for m in salary_meta if m.get("replace_id")}
    retained_salary_months = {
        (d["reporting_year"], d["reporting_month"])
        for d in existing_docs
        if d["document_type"] == "SALARY_SLIP" and d["id"] not in replaced_salary_ids and d.get("reporting_month") and d.get("reporting_year")
    }
    incoming_salary_months = set()
    for m in salary_meta:
        month = m.get("month")
        year = m.get("year")
        if not month or month < 1 or month > 12:
            raise HTTPException(400, f"Invalid reporting month '{month}' for salary slip. Must be 1-12.")
        if not year or year < 2000 or year > 2050:
            raise HTTPException(400, f"Invalid reporting year '{year}' for salary slip. Must be 2000-2050.")
        period = (year, month)
        if period in incoming_salary_months or period in retained_salary_months:
            raise HTTPException(400, f"Duplicate salary slip for reporting period {month}/{year}.")
        incoming_salary_months.add(period)

    total_salary_months = len(retained_salary_months | incoming_salary_months)
    if total_salary_months < 3:
        raise HTTPException(400, f"At least 3 distinct salary slip months are required (current total: {total_salary_months}).")
    if total_salary_months > 12:
        raise HTTPException(400, f"Maximum of 12 distinct salary slip months allowed (current total: {total_salary_months}).")

    # 5. Validate Bank Statements
    replaced_bank_ids = {m["replace_id"] for m in bank_meta if m.get("replace_id")}
    retained_bank_months = {
        (d["reporting_year"], d["reporting_month"])
        for d in existing_docs
        if d["document_type"] == "BANK_STATEMENT" and d["id"] not in replaced_bank_ids and d.get("reporting_month") and d.get("reporting_year")
    }
    incoming_bank_months = set()
    for m in bank_meta:
        month = m.get("month")
        year = m.get("year")
        if not month or month < 1 or month > 12:
            raise HTTPException(400, f"Invalid reporting month '{month}' for bank statement. Must be 1-12.")
        if not year or year < 2000 or year > 2050:
            raise HTTPException(400, f"Invalid reporting year '{year}' for bank statement. Must be 2000-2050.")
        period = (year, month)
        if period in incoming_bank_months or period in retained_bank_months:
            raise HTTPException(400, f"Duplicate bank statement for reporting period {month}/{year}.")
        incoming_bank_months.add(period)

    total_bank_months = len(retained_bank_months | incoming_bank_months)
    if total_bank_months < 3:
        raise HTTPException(400, f"At least 3 distinct bank statement months are required (current total: {total_bank_months}).")
    if total_bank_months > 12:
        raise HTTPException(400, f"Maximum of 12 distinct bank statement months allowed (current total: {total_bank_months}).")

    # 6. Read and pre-validate all file buffers
    staged_uploads: list[dict[str, Any]] = []

    if appointment_letter:
        app_bytes = await appointment_letter.read()
        app_mime = _validate_file_upload(appointment_letter.filename or "appointment.pdf", app_bytes, appointment_letter.content_type)
        staged_uploads.append({
            "doc_type": "APPOINTMENT_LETTER",
            "file_name": appointment_letter.filename or f"appointment_{candidate_id}.pdf",
            "bytes": app_bytes,
            "mime_type": app_mime,
            "month": None,
            "year": None,
            "replace_id": appointment_replace_id,
        })

    for f, m in zip(salary_slips, salary_meta):
        f_bytes = await f.read()
        f_mime = _validate_file_upload(f.filename or "salary_slip.pdf", f_bytes, f.content_type)
        staged_uploads.append({
            "doc_type": "SALARY_SLIP",
            "file_name": f.filename or f"salary_slip_{candidate_id}_{m['month']}_{m['year']}.pdf",
            "bytes": f_bytes,
            "mime_type": f_mime,
            "month": m["month"],
            "year": m["year"],
            "replace_id": m.get("replace_id"),
        })

    for f, m in zip(bank_statements, bank_meta):
        f_bytes = await f.read()
        f_mime = _validate_file_upload(f.filename or "bank_statement.pdf", f_bytes, f.content_type)
        staged_uploads.append({
            "doc_type": "BANK_STATEMENT",
            "file_name": f.filename or f"bank_statement_{candidate_id}_{m['month']}_{m['year']}.pdf",
            "bytes": f_bytes,
            "mime_type": f_mime,
            "month": m["month"],
            "year": m["year"],
            "replace_id": m.get("replace_id"),
        })

    if not staged_uploads:
        raise HTTPException(400, "No new files were provided for submission.")

    # 7. Execute Drive Uploads with Compensation Tracking
    created_drive_file_ids: list[str] = []
    old_drive_files_to_delete: list[str] = []
    db_operations: list[dict[str, Any]] = []

    try:
        for item in staged_uploads:
            if item["replace_id"]:
                old_row = next((d for d in existing_docs if d["id"] == item["replace_id"]), None)
                if old_row and old_row.get("drive_file_id"):
                    old_drive_files_to_delete.append(old_row["drive_file_id"])

            dest_folder_id, folder_path = google_drive_service.get_or_create_candidate_subfolder(
                state=cand_ctx["state"],
                tc_name=cand_ctx["tc_name"],
                batch_code=cand_ctx["batch_code"],
                candidate_id=cand_ctx["candidate_id"],
                candidate_name=cand_ctx["candidate_name"],
                doc_type=item["doc_type"],
            )

            drive_res = google_drive_service.upload_file(
                content_bytes=item["bytes"],
                file_name=item["file_name"],
                mime_type=item["mime_type"],
                destination_folder_id=dest_folder_id,
            )
            created_drive_file_ids.append(drive_res["file_id"])

            db_operations.append({
                "replace_id": item["replace_id"],
                "payload": {
                    "candidate_id": candidate_id,
                    "document_type": item["doc_type"],
                    "reporting_month": item["month"],
                    "reporting_year": item["year"],
                    "drive_file_id": drive_res["file_id"],
                    "drive_folder_id": dest_folder_id,
                    "drive_folder_path": folder_path,
                    "file_name": drive_res["file_name"],
                    "mime_type": drive_res["mime_type"],
                    "file_size_bytes": drive_res["size"],
                    "upload_status": "SUCCESS",
                    "uploaded_by": user.id,
                    "error_message": None,
                },
            })
    except GoogleDriveNotConfiguredError:
        for fid in created_drive_file_ids:
            google_drive_service.delete_file(fid)
        raise HTTPException(503, "Google Drive integration is not configured on the backend.")
    except Exception as e:
        for fid in created_drive_file_ids:
            google_drive_service.delete_file(fid)
        raise HTTPException(502, f"Failed to upload document to Google Drive: {e}")

    # 8. Persist Database Records with Compensation
    persisted_inserted_ids: list[str] = []
    persisted_updated_ids: list[str] = []
    try:
        for op in db_operations:
            if op["replace_id"]:
                db_res = (
                    supabase.table("candidate_documents")
                    .update(op["payload"])
                    .eq("id", op["replace_id"])
                    .execute()
                )
                if db_res.data:
                    persisted_updated_ids.append(op["replace_id"])
            else:
                db_res = (
                    supabase.table("candidate_documents")
                    .insert(op["payload"])
                    .execute()
                )
                if db_res.data:
                    persisted_inserted_ids.append(db_res.data[0]["id"])
    except Exception as e:
        logger.exception("Database persistence failed during batch submission for candidate %s: %s", candidate_id, e)
        # Roll back newly created Drive files
        drive_cleanup_failures: list[str] = []
        for fid in created_drive_file_ids:
            try:
                google_drive_service.delete_file(fid)
            except Exception as d_err:
                logger.error("Failed to delete newly created Drive file %s during rollback: %s", fid, d_err)
                drive_cleanup_failures.append(fid)

        # Roll back newly inserted database rows
        for doc_id in persisted_inserted_ids:
            try:
                supabase.table("candidate_documents").delete().eq("id", doc_id).execute()
            except Exception as sb_err:
                logger.error("Failed to delete inserted document %s during rollback: %s", doc_id, sb_err)

        # Restore updated/replaced rows to their previous valid state so existing documents are NEVER deleted
        for doc_id in persisted_updated_ids:
            orig = existing_docs_by_id.get(doc_id)
            if orig:
                try:
                    restore_payload = {
                        k: v for k, v in orig.items()
                        if k not in ("id", "created_at", "updated_at")
                    }
                    supabase.table("candidate_documents").update(restore_payload).eq("id", doc_id).execute()
                except Exception as sb_err:
                    logger.error("Failed to restore replaced document %s during rollback: %s", doc_id, sb_err)

        err_detail = f"Database persistence failed: {e}. Staged changes have been rolled back."
        if drive_cleanup_failures:
            err_detail += f" Warning: {len(drive_cleanup_failures)} newly created Drive files could not be cleaned up."
        raise HTTPException(500, err_detail)

    # 9. Cleanup old replaced files in Google Drive
    cleanup_warnings: list[str] = []
    for old_fid in old_drive_files_to_delete:
        try:
            google_drive_service.delete_file(old_fid)
        except Exception as e:
            logger.warning("Failed to delete replaced Google Drive file %s: %s", old_fid, e)
            cleanup_warnings.append(f"Replaced Drive file {old_fid} could not be automatically deleted: {e}")

    # 10. Return updated summary
    summary = get_documents_summary(candidate_id, user)
    return {
        "status": "success",
        "message": f"Successfully submitted {len(staged_uploads)} documents for placement verification.",
        "candidate_id": candidate_id,
        "submitted_count": len(staged_uploads),
        "cleanup_warnings": cleanup_warnings,
        "summary": summary,
    }


@router.get("/{document_id}/download")
def download_document(
    candidate_id: int,
    document_id: str,
    user: CurrentUser = Depends(require_roles("L1_COORDINATOR")),
):
    """Download/stream a document file securely from Google Drive."""
    res = (
        supabase.table("candidate_documents")
        .select("id,candidate_id,drive_file_id,file_name,mime_type")
        .eq("id", document_id)
        .eq("candidate_id", candidate_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "Document not found.")

    doc = res.data[0]
    drive_file_id = doc.get("drive_file_id")
    if not drive_file_id:
        raise HTTPException(404, "File identifier is missing from document record.")

    try:
        file_bytes, file_name, mime_type = google_drive_service.download_file(drive_file_id)
    except GoogleDriveNotConfiguredError:
        raise HTTPException(503, "Google Drive integration is not configured.")
    except Exception as e:
        raise HTTPException(502, f"Failed to retrieve document from Google Drive: {e}")

    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type=mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{file_name}"'},
    )


@router.delete("/{document_id}")
def delete_document(
    candidate_id: int,
    document_id: str,
    user: CurrentUser = Depends(require_roles("L1_COORDINATOR")),
):
    """Delete an uploaded document record and remove its file from Google Drive."""
    res = (
        supabase.table("candidate_documents")
        .select("id,drive_file_id")
        .eq("id", document_id)
        .eq("candidate_id", candidate_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "Document not found.")

    drive_file_id = res.data[0].get("drive_file_id")
    if drive_file_id:
        google_drive_service.delete_file(drive_file_id)

    supabase.table("candidate_documents").delete().eq("id", document_id).execute()
    return {"status": "deleted", "id": document_id}
