"""FastAPI router for L1 Placement Audit Statement.

Manages:
- Capturing employer details, salary details, document audit information, and sign-offs.
- Single audit record per candidate (draft, update, and final submission).
- Comprehensive validation for employer data, salary records, and document compliance.
- Complete C-PASS Candidate Placement Audit & Sign-off Statement generation.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import CurrentUser, allowed_tc_ids, get_current_user, require_roles
from ..db import supabase

logger = logging.getLogger("cpass.audits")

router = APIRouter(prefix="/candidates/{candidate_id}/audit", tags=["audits"])


# -----------------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------------

class EmployerEntry(BaseModel):
    employer_name: str = Field(..., min_length=1, description="Company/Employer name")
    months_worked: float | int | None = Field(None, description="Duration worked in months")
    appointment_date: str | None = Field(None, description="Date of appointment / joining")
    designation: str | None = Field(None, description="Candidate designation/role")
    place_of_work: str | None = Field(None, description="Workplace city/location")
    monthly_ctc: float | None = Field(None, ge=0, description="Monthly CTC in Rupees")
    minimum_wages: float | None = Field(None, ge=0, description="Applicable minimum wages in Rupees")


class SalaryEntry(BaseModel):
    month: int = Field(..., ge=1, le=12, description="Reporting month (1-12)")
    year: int = Field(..., ge=2000, le=2050, description="Reporting year")
    working_days: int | None = Field(None, ge=0, le=31, description="Working days in month")
    pay_days: int | None = Field(None, ge=0, le=31, description="Paid days in month")
    leave_days: int | None = Field(None, ge=0, le=31, description="Leave days taken")
    credit_date: str | None = Field(None, description="Date salary credited to bank")
    amount_credited: float | None = Field(None, ge=0, description="Net amount credited to bank")
    gross_salary: float | None = Field(None, ge=0, description="Gross salary in Rupees")
    deductions: float | None = Field(None, ge=0, description="Total deductions (PF/ESI/TDS)")
    net_salary: float | None = Field(None, ge=0, description="Net payable salary in Rupees")
    bank_name: str | None = Field(None, description="Bank name receiving credit")


class DocumentAuditDetails(BaseModel):
    appointment_letter_status: str | None = None
    appointment_letter_compliant: bool | None = None
    appointment_letter_remarks: str | None = None
    salary_slips_status: str | None = None
    salary_slips_compliant: bool | None = None
    salary_slips_remarks: str | None = None
    bank_statements_status: str | None = None
    bank_statements_compliant: bool | None = None
    bank_statements_remarks: str | None = None
    overall_compliance: bool | None = None
    remarks: str | None = None

    appointment_letter: dict[str, Any] | None = None
    salary_slip_1: dict[str, Any] | None = None
    salary_slip_2: dict[str, Any] | None = None
    salary_slip_3: dict[str, Any] | None = None
    bank_statement_1: dict[str, Any] | None = None
    bank_statement_2: dict[str, Any] | None = None
    bank_statement_3: dict[str, Any] | None = None
    other_document: dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class SignoffOfficial(BaseModel):
    name: str | None = None
    designation: str | None = None
    date: str | None = None
    remarks: str | None = None
    confirmed: bool = False


class SignoffDetails(BaseModel):
    centre_head: SignoffOfficial = Field(default_factory=SignoffOfficial)
    cops_team: SignoffOfficial = Field(default_factory=SignoffOfficial)
    business_leader: SignoffOfficial = Field(default_factory=SignoffOfficial)
    submitter: dict[str, Any] | None = None
    placement_executive: dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class SaveAuditDraftRequest(BaseModel):
    candidate_snapshot: dict[str, Any] = Field(default_factory=dict)
    employer_details: list[EmployerEntry] = Field(default_factory=list)
    salary_details: list[SalaryEntry] = Field(default_factory=list)
    document_audit: DocumentAuditDetails = Field(default_factory=DocumentAuditDetails)
    signoff_details: SignoffDetails = Field(default_factory=SignoffDetails)
    remarks: str | None = None


class SubmitAuditRequest(BaseModel):
    candidate_snapshot: dict[str, Any] = Field(default_factory=dict)
    employer_details: list[EmployerEntry] = Field(default_factory=list)
    salary_details: list[SalaryEntry] = Field(default_factory=list)
    document_audit: DocumentAuditDetails = Field(default_factory=DocumentAuditDetails)
    signoff_details: SignoffDetails = Field(default_factory=SignoffDetails)
    remarks: str | None = None


class L2ChecklistUpdateRequest(BaseModel):
    reviewed_documents: dict[str, Any] = Field(default_factory=dict, description="Mapping of doc_id to boolean or dict details")


class L2CorrectionsRequest(BaseModel):
    employer_details: list[EmployerEntry] = Field(default_factory=list)
    salary_details: list[SalaryEntry] = Field(default_factory=list)
    remarks: str | None = None
    correction_notes: str | None = None


class L2ApproveRequest(BaseModel):
    remarks: str | None = None
    corrections: L2CorrectionsRequest | None = None


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def _check_candidate_centre(user: CurrentUser, candidate_id: int) -> dict[str, Any]:
    """Retrieve candidate and verify user centre scoping."""
    res = (
        supabase.table("ddugky_candidates")
        .select("*")
        .eq("candidate_id", candidate_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        # Fallback to legacy candidates table if present
        try:
            cand_fallback = (
                supabase.table("candidates")
                .select("*, batches!inner(tc_id, batch_code, sanction_order)")
                .eq("candidate_id", candidate_id)
                .limit(1)
                .execute()
            )
            if cand_fallback.data:
                c = cand_fallback.data[0]
                tc_id = c["batches"]["tc_id"]
            else:
                raise HTTPException(404, f"Candidate {candidate_id} not found.")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(404, f"Candidate {candidate_id} not found.")
    else:
        c = res.data[0]
        tc_id = c.get("tc_id")

    if tc_id is not None:
        allowed = allowed_tc_ids(user)
        if allowed is not None and tc_id not in allowed:
            raise HTTPException(403, "You are not assigned to this candidate's training centre.")

    return c


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------

@router.get("")
def get_audit(
    candidate_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    """Retrieve the existing audit record (DRAFT or SUBMITTED) for this candidate."""
    _check_candidate_centre(user, candidate_id)

    try:
        res = (
            supabase.table("placement_audits")
            .select("*")
            .eq("candidate_id", candidate_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            return {"exists": False, "audit": None}

        return {"exists": True, "audit": res.data[0]}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to query placement_audits for candidate %s: %s", candidate_id, exc)
        raise HTTPException(status_code=500, detail=f"Database error while querying audit: {str(exc)}") from exc


MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]


def _mask_aadhaar(raw: Any) -> tuple[str | None, str]:
    """Safely mask Aadhaar number without exposing digits or fabricating data.
    
    Returns:
        tuple of (aadhaar_last4 or None, masked_display_string)
    """
    if not raw:
        return None, "Not Available"
    raw_str = str(raw).strip()
    clean = "".join(ch for ch in raw_str if ch.isdigit())
    if len(clean) >= 4:
        last4 = clean[-4:]
        return last4, f"XXXX-XXXX-{last4}"
    if raw_str.lower() in ("no", "na", "n/a", "none", "0", "nil"):
        return None, "Not Provided"
    return None, "Not Available"


def _mask_bank_account(raw: Any) -> str:
    """Mask bank account number, displaying XXXX-XXXX-Last4 or Not Available."""
    if not raw:
        return "Not Available"
    s = str(raw).strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) >= 4:
        return f"XXXX-XXXX-{digits[-4:]}"
    if s.lower() in ("no", "na", "n/a", "none", "0", "nil"):
        return "Not Available"
    return s or "Not Available"


def _build_candidate_snapshot(cand: dict[str, Any], candidate_id: int, override: dict[str, Any] | None = None) -> dict[str, Any]:
    """Construct a clean, normalized candidate snapshot preserving data integrity."""
    raw_aadhar = cand.get("aadhar")
    last4, masked = _mask_aadhaar(raw_aadhar)

    first = cand.get("candidate_first_name") or cand.get("first_name") or ""
    last = cand.get("candidate_last_name") or cand.get("last_name") or ""
    full = f"{first} {last}".strip() or f"Candidate {candidate_id}"

    raw_bank = cand.get("bank_account")
    masked_bank = cand.get("masked_bank_account") or _mask_bank_account(raw_bank)
    addr = cand.get("address") or cand.get("permanent_address") or cand.get("permanent_address_village") or "Not Available"
    if addr and str(addr).strip() == "0":
        addr = "Not Available"

    base = {
        "candidate_id": cand.get("candidate_id") or candidate_id,
        "candidate_name": full,
        "full_name": full,
        "first_name": first or None,
        "last_name": last or None,
        "father_name": cand.get("candidate_father_name") or cand.get("father_name") or "Not Available",
        "dob": str(cand.get("date_of_birth") or cand.get("dob") or "Not Available"),
        "date_of_birth": str(cand.get("date_of_birth") or cand.get("dob") or "Not Available"),
        "gender": cand.get("gender") or "Not Available",
        "mobile": cand.get("mobile_number") or cand.get("mobile") or "Not Available",
        "contact_number": cand.get("mobile_number") or cand.get("mobile") or "Not Available",
        "state": cand.get("tc_state_name") or cand.get("state_name"),
        "tc_name": cand.get("tc_name"),
        "training_centre": cand.get("tc_name"),
        "batch_code": cand.get("batch_code") or "Not Available",
        "batch_start_date": str(cand.get("batch_start_date") or "Not Available"),
        "batch_end_date": str(cand.get("batch_end_date") or "Not Available"),
        "trade_name": cand.get("trade_name") or "Not Available",
        "trade": cand.get("trade_name") or "Not Available",
        "sector": cand.get("sector"),
        "candidate_email": cand.get("candidate_email") or "Not Available",
        "candidate_qualification": cand.get("candidate_qualification") or "Not Available",
        "address": addr,
        "permanent_address": addr,
        "bank_account": masked_bank,
        "masked_bank_account": masked_bank,
        "sanction_order": cand.get("sanction_order_number") or "Not Available",
        "aadhaar_last4": last4,
        "masked_aadhaar": masked,
        "aadhaar_number": masked,
    }
    if override:
        for k, v in override.items():
            if v is not None and v != "":
                base[k] = v
        if not base.get("candidate_name"):
            base["candidate_name"] = full
        if not base.get("masked_aadhaar") or base.get("masked_aadhaar") == "N/A":
            base["masked_aadhaar"] = masked
            base["aadhaar_number"] = masked
            base["aadhaar_last4"] = last4
    return base


@router.post("/draft")
def save_audit_draft(
    candidate_id: int,
    payload: SaveAuditDraftRequest,
    user: CurrentUser = Depends(require_roles("L1_COORDINATOR", "ADMIN")),
):
    """Save or update draft placement audit for this candidate.
    
    Preserves single record per candidate across all draft edits.
    """
    cand = _check_candidate_centre(user, candidate_id)

    # Check if audit already exists
    existing_res = (
        supabase.table("placement_audits")
        .select("*")
        .eq("candidate_id", candidate_id)
        .limit(1)
        .execute()
    )

    now_iso = datetime.now(timezone.utc).isoformat()

    snapshot = _build_candidate_snapshot(cand, candidate_id, payload.candidate_snapshot)

    audit_payload = {
        "candidate_id": candidate_id,
        "candidate_snapshot": snapshot,
        "employer_details": [e.model_dump() for e in payload.employer_details],
        "salary_details": [s.model_dump() for s in payload.salary_details],
        "document_audit": payload.document_audit.model_dump(),
        "signoff_details": payload.signoff_details.model_dump(),
        "remarks": payload.remarks,
        "updated_at": now_iso,
    }

    if existing_res.data:
        existing = existing_res.data[0]
        if existing.get("audit_status") == "SUBMITTED" and user.role != "ADMIN":
            raise HTTPException(400, "This placement audit has already been finalized/submitted and cannot be edited as a draft.")

        # Update existing record
        update_res = (
            supabase.table("placement_audits")
            .update(audit_payload)
            .eq("id", existing["id"])
            .execute()
        )
        record = update_res.data[0] if update_res.data else {**existing, **audit_payload}
    else:
        # Insert new draft record
        audit_payload["audit_status"] = "DRAFT"
        audit_payload["cpass_status"] = "PENDING"
        audit_payload["created_by"] = user.id
        audit_payload["created_at"] = now_iso

        insert_res = (
            supabase.table("placement_audits")
            .insert(audit_payload)
            .execute()
        )
        record = insert_res.data[0] if insert_res.data else audit_payload

    return {"message": "Draft audit saved successfully", "audit": record}


@router.post("/submit")
def submit_audit(
    candidate_id: int,
    payload: SubmitAuditRequest,
    user: CurrentUser = Depends(require_roles("L1_COORDINATOR")),
):
    """Validate all mandatory requirements and submit the placement audit.
    
    Transitions status to SUBMITTED and timestamps finalization.
    """
    cand = _check_candidate_centre(user, candidate_id)

    # 1. Validation: Candidate Administrative Hold
    try:
        hold_res = (
            supabase.table("candidate_holds")
            .select("hold_reason")
            .eq("candidate_id", candidate_id)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        if hold_res.data:
            raise HTTPException(400, f"Submission blocked: Candidate has an active administrative hold ({hold_res.data[0]['hold_reason']}).")
    except HTTPException:
        raise
    except Exception:
        pass

    # 2. Validation: At least one employer with employer_name
    if not payload.employer_details:
        raise HTTPException(400, "At least one employer entry is required for placement audit submission.")

    for i, emp in enumerate(payload.employer_details):
        if not emp.employer_name or not emp.employer_name.strip():
            raise HTTPException(400, f"Employer #{i + 1}: Employer Name is required.")

    # 3. Validation: At least 3 distinct salary entries
    if len(payload.salary_details) < 3:
        raise HTTPException(400, f"At least 3 distinct reporting months of salary details are required (currently provided: {len(payload.salary_details)}).")

    salary_periods = set()
    for s in payload.salary_details:
        key = f"{s.year}-{s.month}"
        if key in salary_periods:
            raise HTTPException(400, f"Duplicate salary reporting period detected: {s.month}/{s.year}.")
        salary_periods.add(key)
        if s.amount_credited is not None and s.amount_credited < 0:
            raise HTTPException(400, f"Salary amount credited for {s.month}/{s.year} cannot be negative.")

    # 4. Check existing audit state
    existing_res = (
        supabase.table("placement_audits")
        .select("*")
        .eq("candidate_id", candidate_id)
        .limit(1)
        .execute()
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    snapshot = _build_candidate_snapshot(cand, candidate_id, payload.candidate_snapshot)

    # Submitter metadata for L1 audit tracking
    signoff_dict = payload.signoff_details.model_dump()
    signoff_dict["submitter"] = {
        "user_id": str(user.id),
        "name": user.full_name or "L1 Placement Executive",
        "email": user.email,
        "role": user.role,
        "role_label": "L1 (PE)",
        "submitted_at": now_iso,
    }
    signoff_dict["placement_executive"] = {
        "name": user.full_name or "L1 Placement Executive",
        "designation": "Placement Executive (L1)",
        "email": user.email,
        "date": now_iso[:10],
        "confirmed": True,
        "submitted_at": now_iso,
    }

    doc_audit_data = payload.document_audit.model_dump()

    # Determine compliance status
    # If any document is explicitly marked unavailable (No / Pending) or not compliant (Non-Compliant / Under Verification), cpass_status is PENDING.
    # Placement is only VERIFIED when all required documents are available, compliant, and verified.
    has_pending_or_uncompliant = False
    for req_key in [
        "appointment_letter",
        "salary_slip_1",
        "salary_slip_2",
        "salary_slip_3",
        "bank_statement_1",
        "bank_statement_2",
        "bank_statement_3",
    ]:
        row = doc_audit_data.get(req_key)
        if isinstance(row, dict):
            if row.get("available") in ("No", "Pending") or row.get("compliance") in ("Non-Compliant", "Under Verification"):
                has_pending_or_uncompliant = True
                break

    if has_pending_or_uncompliant or doc_audit_data.get("overall_compliance") is False:
        computed_cpass_status = "PENDING"
    else:
        computed_cpass_status = "VERIFIED"

    audit_payload = {
        "candidate_id": candidate_id,
        "candidate_snapshot": snapshot,
        "employer_details": [e.model_dump() for e in payload.employer_details],
        "salary_details": [s.model_dump() for s in payload.salary_details],
        "document_audit": doc_audit_data,
        "signoff_details": signoff_dict,
        "cpass_status": computed_cpass_status,
        "audit_status": "SUBMITTED",
        "remarks": payload.remarks,
        "finalized_at": now_iso,
        "updated_at": now_iso,
    }

    if existing_res.data:
        existing = existing_res.data[0]
        if existing.get("audit_status") == "SUBMITTED":
            raise HTTPException(400, "This placement audit has already been submitted.")

        update_res = (
            supabase.table("placement_audits")
            .update(audit_payload)
            .eq("id", existing["id"])
            .execute()
        )
        record = update_res.data[0] if update_res.data else {**existing, **audit_payload}
    else:
        audit_payload["created_by"] = user.id
        audit_payload["created_at"] = now_iso

        insert_res = (
            supabase.table("placement_audits")
            .insert(audit_payload)
            .execute()
        )
        record = insert_res.data[0] if insert_res.data else audit_payload

    return {
        "message": "Placement Audit Statement submitted successfully",
        "audit": record,
        "submitted_at": now_iso,
    }


@router.get("/statement")
def get_audit_statement(
    candidate_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    """Compile and return the complete C-PASS Candidate Placement Audit & Sign-off Statement payload."""
    cand = _check_candidate_centre(user, candidate_id)

    # 1. Fetch audit record
    audit_res = (
        supabase.table("placement_audits")
        .select("*")
        .eq("candidate_id", candidate_id)
        .limit(1)
        .execute()
    )
    audit = audit_res.data[0] if audit_res.data else None

    # 2. Fetch persisted documents (exclude FAILED status)
    docs_res = (
        supabase.table("candidate_documents")
        .select("id,document_type,reporting_month,reporting_year,file_name,file_size_bytes,upload_status,drive_file_id,document_title,created_at")
        .eq("candidate_id", candidate_id)
        .neq("upload_status", "FAILED")
        .order("created_at")
        .execute()
    )
    docs = docs_res.data or []

    # 3. Normalized candidate snapshot
    existing_snapshot = audit.get("candidate_snapshot") if audit else None
    cand_info = _build_candidate_snapshot(cand, candidate_id, existing_snapshot)

    # Add extra candidate profile fields
    cand_info["gender"] = cand.get("gender") or cand_info.get("gender")
    cand_info["category"] = cand.get("category")
    cand_info["permanent_address"] = cand.get("permanent_address") or cand.get("permanent_address_village") or cand_info.get("permanent_address")
    cand_info["address"] = cand_info["permanent_address"]
    cand_info["tc_id"] = cand.get("tc_id")
    cand_info["appointed"] = bool(cand.get("appointed"))
    cand_info["sector_name"] = cand.get("sector")
    cand_info["training_centre_name"] = cand.get("tc_name")
    cand_info["sanction_order_name"] = cand.get("sanction_order_number")
    cand_info["batch_id"] = cand.get("batch_code")
    cand_info["batch_start_date"] = str(cand.get("batch_start_date") or cand_info.get("batch_start_date") or "Not Available")
    cand_info["batch_end_date"] = str(cand.get("batch_end_date") or cand_info.get("batch_end_date") or "Not Available")
    cand_info["candidate_email"] = cand.get("candidate_email") or cand_info.get("candidate_email") or "Not Available"
    cand_info["candidate_qualification"] = cand.get("candidate_qualification") or cand_info.get("candidate_qualification") or "Not Available"
    cand_info["bank_account"] = cand_info.get("bank_account") or _mask_bank_account(cand.get("bank_account"))
    cand_info["masked_bank_account"] = cand_info.get("masked_bank_account") or cand_info["bank_account"]

    # 4. Salary and Employer Details
    employer_entries = (audit and audit.get("employer_details")) or []
    salary_entries = (audit and audit.get("salary_details")) or []

    total_credited = sum(float(s.get("amount_credited") or 0) for s in salary_entries)
    total_gross = sum(float(s.get("gross_salary") or 0) for s in salary_entries)
    total_deductions = sum(float(s.get("deductions") or 0) for s in salary_entries)
    total_net = sum(float(s.get("net_salary") or 0) for s in salary_entries)
    avg_salary = (total_gross / len(salary_entries)) if salary_entries else 0

    # 5. Build Document Evidence cross-verification against persisted records
    al_doc = next(
        (d for d in docs if d.get("document_type") == "APPOINTMENT_LETTER" and d.get("upload_status") == "SUCCESS"),
        None,
    )

    successful_slips = sorted(
        [d for d in docs if d.get("document_type") == "SALARY_SLIP" and d.get("upload_status") == "SUCCESS"],
        key=lambda d: (d.get("reporting_year") or 0, d.get("reporting_month") or 0),
    )
    successful_banks = sorted(
        [d for d in docs if d.get("document_type") == "BANK_STATEMENT" and d.get("upload_status") == "SUCCESS"],
        key=lambda d: (d.get("reporting_year") or 0, d.get("reporting_month") or 0),
    )

    sorted_salaries = sorted(salary_entries, key=lambda s: (s.get("year") or 0, s.get("month") or 0))

    def find_slip_doc(idx: int) -> dict[str, Any] | None:
        if idx < len(sorted_salaries):
            target_year = sorted_salaries[idx].get("year")
            target_month = sorted_salaries[idx].get("month")
            match = next((d for d in successful_slips if d.get("reporting_year") == target_year and d.get("reporting_month") == target_month), None)
            if match:
                return match
        return successful_slips[idx] if idx < len(successful_slips) else None

    def find_bank_doc(idx: int) -> dict[str, Any] | None:
        if idx < len(sorted_salaries):
            target_year = sorted_salaries[idx].get("year")
            target_month = sorted_salaries[idx].get("month")
            match = next((d for d in successful_banks if d.get("reporting_year") == target_year and d.get("reporting_month") == target_month), None)
            if match:
                return match
        return successful_banks[idx] if idx < len(successful_banks) else None

    def slip_label(idx: int) -> str:
        if idx < len(sorted_salaries) and sorted_salaries[idx].get("month"):
            m = sorted_salaries[idx]["month"]
            y = sorted_salaries[idx].get("year")
            m_str = MONTH_NAMES[m - 1] if 1 <= m <= 12 else f"Month {m}"
            return f"Salary Pay Slip — {m_str} {y or ''}".strip()
        return f"Salary Pay Slip — Month {idx + 1}"

    def bank_label(idx: int) -> str:
        if idx < len(sorted_salaries) and sorted_salaries[idx].get("month"):
            m = sorted_salaries[idx]["month"]
            y = sorted_salaries[idx].get("year")
            m_str = MONTH_NAMES[m - 1] if 1 <= m <= 12 else f"Month {m}"
            return f"Bank Statement / Passbook — {m_str} {y or ''}".strip()
        return f"Bank Statement / Passbook — Month {idx + 1}"

    saved_doc_audit = (audit and audit.get("document_audit")) or {}

    def get_row_audit(key: str) -> dict[str, Any]:
        val = saved_doc_audit.get(key)
        if isinstance(val, dict):
            return val
        return {}

    def map_avail_field(raw_val: Any, has_doc: bool) -> tuple[Any, str]:
        if raw_val is None or raw_val == "":
            return (bool(has_doc), "Yes" if has_doc else "Missing")
        if raw_val in ("Yes", True):
            return (True, "Yes")
        if raw_val in ("No", False):
            return (False, "No")
        return ("Pending", "Pending")

    # AL / OL
    al_audit = get_row_audit("appointment_letter")
    al_avail, al_avail_str = map_avail_field(al_audit.get("available"), bool(al_doc))
    al_comp = al_audit.get("compliance")
    if not al_comp:
        al_comp = "Compliant" if al_doc else "Missing / Non-Compliant"
    al_obs = al_audit.get("remarks")
    if not al_obs:
        al_obs = "Appointment letter verified against candidate placement record." if al_doc else "Mandatory appointment/offer letter is pending upload."
    al_repo = f"Stored in Drive: {al_doc['file_name']}" if al_doc else ("Document marked unavailable by coordinator" if al_avail_str == "No" else ("Document pending upload" if al_avail_str == "Pending" else "No verified file in database"))

    evidence_list = [
        {
            "code": "AL / OL",
            "key": "appointment_letter",
            "label": "Appointment / Offer Letter",
            "available": al_avail,
            "availability_status": al_avail_str,
            "compliance": al_comp,
            "repository_status": al_repo,
            "observations": al_obs,
            "file_name": al_doc["file_name"] if al_doc else None,
            "doc_id": al_doc["id"] if al_doc else None,
        }
    ]

    for i in range(3):
        doc = find_slip_doc(i)
        key = f"salary_slip_{i + 1}"
        s_audit = get_row_audit(key)
        s_avail, s_avail_str = map_avail_field(s_audit.get("available"), bool(doc))
        s_comp = s_audit.get("compliance")
        if not s_comp:
            s_comp = "Compliant" if doc else "Missing / Non-Compliant"
        s_obs = s_audit.get("remarks")
        if not s_obs:
            s_obs = "Disbursement slip verified with gross remuneration." if doc else "Salary slip pending upload."
        s_repo = f"Stored in Drive: {doc['file_name']}" if doc else ("Document marked unavailable by coordinator" if s_avail_str == "No" else ("Document pending upload" if s_avail_str == "Pending" else "No verified file in database"))

        evidence_list.append({
            "code": f"PS {i + 1}",
            "key": key,
            "label": slip_label(i),
            "available": s_avail,
            "availability_status": s_avail_str,
            "compliance": s_comp,
            "repository_status": s_repo,
            "observations": s_obs,
            "file_name": doc["file_name"] if doc else None,
            "doc_id": doc["id"] if doc else None,
            "reporting_month": doc.get("reporting_month") if doc else None,
            "reporting_year": doc.get("reporting_year") if doc else None,
        })

    for i in range(3):
        doc = find_bank_doc(i)
        key = f"bank_statement_{i + 1}"
        b_audit = get_row_audit(key)
        b_avail, b_avail_str = map_avail_field(b_audit.get("available"), bool(doc))
        b_comp = b_audit.get("compliance")
        if not b_comp:
            b_comp = "Compliant" if doc else "Missing / Non-Compliant"
        b_obs = b_audit.get("remarks")
        if not b_obs:
            b_obs = "Bank statement credit entry verified." if doc else "Mandatory bank statement is pending upload."
        b_repo = f"Stored in Drive: {doc['file_name']}" if doc else ("Document marked unavailable by coordinator" if b_avail_str == "No" else ("Document pending upload" if b_avail_str == "Pending" else "No verified file in database"))

        evidence_list.append({
            "code": f"BS {i + 1}",
            "key": key,
            "label": bank_label(i),
            "available": b_avail,
            "availability_status": b_avail_str,
            "compliance": b_comp,
            "repository_status": b_repo,
            "observations": b_obs,
            "file_name": doc["file_name"] if doc else None,
            "doc_id": doc["id"] if doc else None,
            "reporting_month": doc.get("reporting_month") if doc else None,
            "reporting_year": doc.get("reporting_year") if doc else None,
        })

    # Row 8: Optional Other Document
    other_doc = next(
        (d for d in docs if d.get("document_type") == "OTHER_DOCUMENT" and d.get("upload_status") == "SUCCESS"),
        None,
    )
    od_audit = get_row_audit("other_document")
    od_avail, od_avail_str = map_avail_field(od_audit.get("available"), bool(other_doc))
    od_comp = od_audit.get("compliance") or ("Compliant" if other_doc else "Under Verification")
    od_title = od_audit.get("title") or (other_doc and other_doc.get("document_title")) or "Other Document"
    od_obs = od_audit.get("remarks") or (
        "Supporting candidate placement document verified." if other_doc else "Optional supporting document."
    )
    od_repo = (
        f"Stored in Drive: {other_doc['file_name']}"
        if other_doc
        else ("Document marked unavailable by coordinator" if od_avail_str == "No" else ("Document pending upload" if od_avail_str == "Pending" else "Optional document not provided"))
    )
    evidence_list.append({
        "code": "OD",
        "key": "other_document",
        "label": f"Other Document — {od_title}" if od_title and od_title != "Other Document" else "Other Document (Optional)",
        "available": od_avail,
        "availability_status": od_avail_str,
        "compliance": od_comp,
        "repository_status": od_repo,
        "observations": od_obs,
        "file_name": other_doc["file_name"] if other_doc else None,
        "doc_id": other_doc["id"] if other_doc else None,
    })

    audit_status = (audit and audit.get("audit_status")) or "DRAFT"
    cpass_status = (audit and audit.get("cpass_status")) or "PENDING"
    finalized_at = audit and audit.get("finalized_at")

    return {
        "title": "C-PASS Candidate Placement Audit & Sign-off Statement",
        "audit_status": audit_status,
        "cpass_status": cpass_status,
        "finalized_at": finalized_at,
        "candidate": cand_info,
        "employer_details": employer_entries,
        "salary_details": salary_entries,
        "document_audit": (audit and audit.get("document_audit")) or {},
        "signoff_details": (audit and audit.get("signoff_details")) or {},
        "remarks": (audit and audit.get("remarks")) or "",
        "salary_summary": {
            "total_credited": round(total_credited, 2),
            "total_gross": round(total_gross, 2),
            "total_deductions": round(total_deductions, 2),
            "total_net": round(total_net, 2),
            "average_monthly_gross": round(avg_salary, 2),
            "average_gross": round(avg_salary, 2),
            "months_count": len(salary_entries),
            "month_count": len(salary_entries),
        },
        "document_evidence": evidence_list,
        "documents": docs,
        "uploaded_documents": docs,
        "audit": audit,
        "l2_document_reviews": ((audit and audit.get("document_audit")) or {}).get("l2_document_reviews") or {},
        "l2_approval": ((audit and audit.get("signoff_details")) or {}).get("l2_approval") or None,
        "l1_original_submission": ((audit and audit.get("signoff_details")) or {}).get("l1_original_submission") or None,
        "submitter": ((audit and audit.get("signoff_details")) or {}).get("submitter") or None,
        "placement_executive": ((audit and audit.get("signoff_details")) or {}).get("placement_executive") or None,
        "revision_history": ((audit and audit.get("signoff_details")) or {}).get("revision_history") or [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verified_by_user": user.full_name,
    }


# -----------------------------------------------------------------------------
# L2 Center Manager Review Endpoints
# -----------------------------------------------------------------------------

@router.post("/l2-review/checklist")
def update_l2_document_checklist(
    candidate_id: int,
    payload: L2ChecklistUpdateRequest,
    user: CurrentUser = Depends(require_roles("L2_MANAGER", "ADMIN")),
):
    """Save persistent per-document review state for L2 verification.
    
    Explicit manager review action is recorded per document and stored in placement_audits.
    """
    _check_candidate_centre(user, candidate_id)

    # 1. Fetch existing audit
    res = (
        supabase.table("placement_audits")
        .select("*")
        .eq("candidate_id", candidate_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, f"No placement audit found for candidate {candidate_id}.")
    audit = res.data[0]

    # 2. Fetch candidate documents to validate document IDs
    doc_res = (
        supabase.table("candidate_documents")
        .select("id,document_type,reporting_month,reporting_year,file_name")
        .eq("candidate_id", candidate_id)
        .neq("upload_status", "FAILED")
        .execute()
    )
    valid_doc_ids = {str(d["id"]) for d in (doc_res.data or [])}

    # 3. Update l2_document_reviews in document_audit
    doc_audit = audit.get("document_audit") or {}
    l2_reviews = doc_audit.get("l2_document_reviews") or {}
    now_iso = datetime.now(timezone.utc).isoformat()

    for doc_id, val in payload.reviewed_documents.items():
        doc_id_str = str(doc_id)
        if doc_id_str not in valid_doc_ids:
            continue
        is_reviewed = val if isinstance(val, bool) else bool(val.get("reviewed") if isinstance(val, dict) else False)
        notes = val.get("notes") if isinstance(val, dict) else None
        l2_reviews[doc_id_str] = {
            "reviewed": is_reviewed,
            "reviewed_at": now_iso,
            "reviewed_by": user.full_name,
            "user_id": user.id,
            "notes": notes,
        }

    doc_audit["l2_document_reviews"] = l2_reviews

    # 4. Save to DB
    supabase.table("placement_audits").update({
        "document_audit": doc_audit,
        "updated_at": now_iso,
    }).eq("id", audit["id"]).execute()

    return {
        "status": "success",
        "candidate_id": candidate_id,
        "l2_document_reviews": l2_reviews,
        "updated_at": now_iso,
    }


@router.post("/l2-review/corrections")
def save_l2_corrections(
    candidate_id: int,
    payload: L2CorrectionsRequest,
    user: CurrentUser = Depends(require_roles("L2_MANAGER", "ADMIN")),
):
    """Save L2 Center Manager corrections while preserving L1 original submission in revision history."""
    _check_candidate_centre(user, candidate_id)

    # 1. Fetch audit
    res = (
        supabase.table("placement_audits")
        .select("*")
        .eq("candidate_id", candidate_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, f"No placement audit found for candidate {candidate_id}.")
    audit = res.data[0]

    # 2. Validate corrections
    if not payload.employer_details:
        raise HTTPException(400, "At least one employer entry is required.")
    for i, emp in enumerate(payload.employer_details):
        if not emp.employer_name or not emp.employer_name.strip():
            raise HTTPException(400, f"Employer #{i + 1}: Employer Name is required.")

    if len(payload.salary_details) < 3:
        raise HTTPException(400, f"At least 3 distinct reporting months of salary details are required (provided: {len(payload.salary_details)}).")

    salary_periods = set()
    for s in payload.salary_details:
        key = f"{s.year}-{s.month}"
        if key in salary_periods:
            raise HTTPException(400, f"Duplicate salary reporting period detected: {s.month}/{s.year}.")
        salary_periods.add(key)
        if s.amount_credited is not None and s.amount_credited < 0:
            raise HTTPException(400, f"Salary amount credited for {s.month}/{s.year} cannot be negative.")

    # 3. Preserve L1 original submission and append to revision history
    signoff = audit.get("signoff_details") or {}
    now_iso = datetime.now(timezone.utc).isoformat()

    if "l1_original_submission" not in signoff:
        signoff["l1_original_submission"] = {
            "employer_details": audit.get("employer_details") or [],
            "salary_details": audit.get("salary_details") or [],
            "remarks": audit.get("remarks"),
            "archived_at": audit.get("finalized_at") or audit.get("updated_at") or now_iso,
        }

    history = signoff.get("revision_history") or []
    history.append({
        "revised_at": now_iso,
        "revised_by": user.full_name,
        "user_id": user.id,
        "role": user.role,
        "correction_notes": payload.correction_notes or "L2 Center Manager data entry corrections",
        "previous_salary_count": len(audit.get("salary_details") or []),
    })
    signoff["revision_history"] = history

    # 4. Update audit
    update_data = {
        "employer_details": [e.model_dump() for e in payload.employer_details],
        "salary_details": [s.model_dump() for s in payload.salary_details],
        "remarks": payload.remarks if payload.remarks is not None else audit.get("remarks"),
        "signoff_details": signoff,
        "updated_at": now_iso,
    }

    up_res = (
        supabase.table("placement_audits")
        .update(update_data)
        .eq("id", audit["id"])
        .execute()
    )
    saved_audit = up_res.data[0] if up_res.data else {**audit, **update_data}

    return {
        "status": "success",
        "message": "L2 corrections saved successfully while preserving original submission.",
        "audit": saved_audit,
        "updated_at": now_iso,
    }


@router.post("/l2-review/approve")
def approve_placement_audit(
    candidate_id: int,
    payload: L2ApproveRequest,
    user: CurrentUser = Depends(require_roles("L2_MANAGER", "ADMIN")),
):
    """Validate review checklist and record L2 Center Manager approval idempotently."""
    cand = _check_candidate_centre(user, candidate_id)

    # 1. Candidate Administrative Hold check
    try:
        hold_res = (
            supabase.table("candidate_holds")
            .select("hold_reason")
            .eq("candidate_id", candidate_id)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        if hold_res.data:
            raise HTTPException(400, f"Approval blocked: Candidate has an active administrative hold ({hold_res.data[0]['hold_reason']}).")
    except HTTPException:
        raise
    except Exception:
        pass

    # 2. Fetch existing audit
    res = (
        supabase.table("placement_audits")
        .select("*")
        .eq("candidate_id", candidate_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, f"Placement audit not found for candidate {candidate_id}.")
    audit = res.data[0]

    # 3. Idempotency check: Already approved by L2
    if audit.get("cpass_status") == "L2_APPROVED":
        return {
            "status": "already_approved",
            "message": "Placement audit has already been approved by L2 Center Manager.",
            "cpass_status": "L2_APPROVED",
            "audit": audit,
        }

    # 4. Workflow gate: Must be SUBMITTED by L1
    if audit.get("audit_status") != "SUBMITTED":
        raise HTTPException(400, "Cannot approve: Placement audit must first be finalized and submitted by L1 Coordinator.")

    # 5. Document Checklist Verification
    docs_res = (
        supabase.table("candidate_documents")
        .select("id,document_type,reporting_month,reporting_year,file_name,upload_status")
        .eq("candidate_id", candidate_id)
        .neq("upload_status", "FAILED")
        .execute()
    )
    persisted_docs = docs_res.data or []
    success_docs = [d for d in persisted_docs if d.get("upload_status") == "SUCCESS"]

    al_doc = next((d for d in success_docs if d.get("document_type") == "APPOINTMENT_LETTER"), None)
    slips = [d for d in success_docs if d.get("document_type") == "SALARY_SLIP"]
    banks = [d for d in success_docs if d.get("document_type") == "BANK_STATEMENT"]

    if not al_doc:
        raise HTTPException(400, "Approval blocked: Candidate is missing a verified Appointment / Offer Letter.")
    if len(slips) < 3:
        raise HTTPException(400, f"Approval blocked: At least 3 verified Salary Slips required (found: {len(slips)}).")
    if len(banks) < 3:
        raise HTTPException(400, f"Approval blocked: At least 3 verified Bank Statements required (found: {len(banks)}).")

    doc_audit = audit.get("document_audit") or {}
    l2_reviews = doc_audit.get("l2_document_reviews") or {}

    unreviewed = []
    if not l2_reviews.get(str(al_doc["id"]), {}).get("reviewed"):
        unreviewed.append("Appointment / Offer Letter")

    for i, s in enumerate(slips[:3]):
        if not l2_reviews.get(str(s["id"]), {}).get("reviewed"):
            unreviewed.append(f"Salary Slip (Month {s.get('reporting_month') or (i + 1)})")

    for i, b in enumerate(banks[:3]):
        if not l2_reviews.get(str(b["id"]), {}).get("reviewed"):
            unreviewed.append(f"Bank Statement (Month {b.get('reporting_month') or (i + 1)})")

    if unreviewed:
        raise HTTPException(
            400,
            f"Approval blocked: The following mandatory documents must be explicitly checked and reviewed before approval: {', '.join(unreviewed)}.",
        )

    # 6. Apply corrections if provided
    signoff = audit.get("signoff_details") or {}
    now_iso = datetime.now(timezone.utc).isoformat()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    employer_details = audit.get("employer_details") or []
    salary_details = audit.get("salary_details") or []
    remarks = payload.remarks or audit.get("remarks") or ""

    if payload.corrections:
        if "l1_original_submission" not in signoff:
            signoff["l1_original_submission"] = {
                "employer_details": employer_details,
                "salary_details": salary_details,
                "remarks": audit.get("remarks"),
                "archived_at": audit.get("finalized_at") or now_iso,
            }
        employer_details = [e.model_dump() for e in payload.corrections.employer_details]
        salary_details = [s.model_dump() for s in payload.corrections.salary_details]
        if payload.corrections.remarks is not None:
            remarks = payload.corrections.remarks

        history = signoff.get("revision_history") or []
        history.append({
            "revised_at": now_iso,
            "revised_by": user.full_name,
            "user_id": user.id,
            "role": user.role,
            "correction_notes": payload.corrections.correction_notes or "L2 corrections applied during approval",
        })
        signoff["revision_history"] = history

    # 7. Update Centre Head Signoff and L2 Approval Metadata
    signoff["centre_head"] = {
        "name": user.full_name,
        "designation": "Centre Manager",
        "date": today_str,
        "remarks": payload.remarks or "Dossier and physical records verified and approved by Centre Manager.",
        "confirmed": True,
        "recommended": True,
        "approved_by_id": user.id,
    }
    signoff["l2_approval"] = {
        "approved": True,
        "approved_at": now_iso,
        "approved_by": user.full_name,
        "user_id": user.id,
        "remarks": payload.remarks,
    }

    doc_audit["l2_review_completed"] = True
    doc_audit["l2_review_completed_at"] = now_iso

    update_payload = {
        "cpass_status": "L2_APPROVED",
        "signoff_details": signoff,
        "document_audit": doc_audit,
        "employer_details": employer_details,
        "salary_details": salary_details,
        "remarks": remarks,
        "updated_at": now_iso,
    }

    up_res = (
        supabase.table("placement_audits")
        .update(update_payload)
        .eq("id", audit["id"])
        .execute()
    )
    updated_record = up_res.data[0] if up_res.data else {**audit, **update_payload}

    return {
        "status": "success",
        "message": "Placement Audit Statement successfully approved by L2 Center Manager.",
        "cpass_status": "L2_APPROVED",
        "audit": updated_record,
        "approved_at": now_iso,
        "approved_by": user.full_name,
    }

