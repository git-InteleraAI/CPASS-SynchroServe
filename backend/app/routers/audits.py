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
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field

from ..auth import CurrentUser, allowed_tc_ids, check_candidate_access, get_current_user, require_roles
from ..db import TRANSIENT_ERRORS, retry_read_query, supabase

logger = logging.getLogger("cpass.audits")

router = APIRouter(prefix="/candidates/{candidate_id}/audit", tags=["audits"])


# -----------------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------------

class EmployerEntry(BaseModel):
    id: str | None = Field(None, description="Stable identifier for employer (e.g. emp_1)")
    employer_id: str | None = Field(None, description="Alternative alias for employer ID")
    employer_name: str = Field(..., min_length=1, description="Company/Employer name")
    months_worked: float | int | None = Field(None, description="Duration worked in months")
    appointment_date: str | None = Field(None, description="Date of appointment / joining")
    designation: str | None = Field(None, description="Candidate designation/role")
    place_of_work: str | None = Field(None, description="Workplace city/location")
    monthly_ctc: float | None = Field(None, ge=0, description="Monthly CTC in Rupees")
    minimum_wages: float | None = Field(None, ge=0, description="Applicable minimum wages in Rupees")


class SalaryEntry(BaseModel):
    id: str | None = Field(None, description="Unique row identifier")
    employer_id: str | None = Field(None, description="ID of employer this salary slip belongs to")
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


class StageRejectRequest(BaseModel):
    rejection_reason: str = Field(..., min_length=1, description="Mandatory reason for rejection")
    remarks: str | None = None


class StageReturnRequest(BaseModel):
    return_reason: str = Field(..., min_length=1, description="Mandatory reason for returning candidate to L1 for corrections")
    remarks: str | None = None


class StageApproveRequest(BaseModel):
    remarks: str | None = None


def extract_review_stages(audit: dict | None) -> dict[str, Any]:
    """Extract and normalize persisted multi-level review stages (CH - L2, COPS - L3, BL - L4).

    If explicit `review_stages` are stored in signoff_details, return them.
    Otherwise, derive backwards-compatible stage statuses from existing cpass_status and audit_status.
    """
    if not audit:
        return {
            "ch": {"status": "Pending"},
            "cops": {"status": "Pending"},
            "bl": {"status": "Pending"},
            "ch_status": "Pending",
            "cops_status": "Pending",
            "bl_status": "Pending",
        }

    signoff = audit.get("signoff_details") or {}
    stages = signoff.get("review_stages")

    raw_status = (audit.get("cpass_status") or "").upper()
    raw_audit = (audit.get("audit_status") or "").upper()

    if isinstance(stages, dict) and ("ch" in stages or "cops" in stages or "bl" in stages):
        ch_raw = stages.get("ch")
        cops_raw = stages.get("cops")
        bl_raw = stages.get("bl")

        ch_obj = ch_raw if isinstance(ch_raw, dict) else {"status": str(ch_raw or "Pending")}
        cops_obj = cops_raw if isinstance(cops_raw, dict) else {"status": str(cops_raw or "Pending")}
        bl_obj = bl_raw if isinstance(bl_raw, dict) else {"status": str(bl_raw or "Pending")}

        ch_st = ch_obj.get("status") or "Pending"
        if ch_st in ("Returned", "Returned to L1") or raw_audit == "RETURNED_TO_L1" or raw_status == "RETURNED_TO_L1":
            ch_st = "Returned to L1"
            ch_obj["status"] = "Returned to L1"

        return {
            "ch": ch_obj,
            "cops": cops_obj,
            "bl": bl_obj,
            "ch_status": ch_st,
            "cops_status": cops_obj.get("status") or "Pending",
            "bl_status": bl_obj.get("status") or "Pending",
        }

    # Derive from legacy status or returned status
    if raw_status == "RETURNED_TO_L1" or raw_audit == "RETURNED_TO_L1":
        return {
            "ch": {"status": "Returned to L1"},
            "cops": {"status": "Pending"},
            "bl": {"status": "Pending"},
            "ch_status": "Returned to L1",
            "cops_status": "Pending",
            "bl_status": "Pending",
        }

    l2_app = signoff.get("l2_approval") or {}

    ch_status = "Pending"
    cops_status = "Pending"
    bl_status = "Pending"

    if raw_status in {"APPROVED", "CPASS_APPROVED"}:
        ch_status = "Recommended"
        cops_status = "Verified"
        bl_status = "Approved"
    elif raw_status == "VERIFIED":
        ch_status = "Recommended"
        cops_status = "Verified"
        bl_status = "Pending"
    elif raw_status == "L2_APPROVED" or l2_app.get("approved"):
        ch_status = "Recommended"
        cops_status = "Pending"
        bl_status = "Pending"
    elif raw_status in {"REJECTED", "L2_REJECTED", "CPASS_REJECTED"} or raw_audit == "REJECTED":
        rej_stage = signoff.get("rejected_stage") or ""
        if rej_stage == "bl" or raw_status == "L4_REJECTED":
            ch_status = "Recommended"
            cops_status = "Verified"
            bl_status = "Rejected"
        elif rej_stage == "cops" or raw_status == "L3_REJECTED":
            ch_status = "Recommended"
            cops_status = "Rejected"
            bl_status = "Pending"
        else:
            ch_status = "Rejected"
            cops_status = "Pending"
            bl_status = "Pending"

    return {
        "ch": {"status": ch_status},
        "cops": {"status": cops_status},
        "bl": {"status": bl_status},
        "ch_status": ch_status,
        "cops_status": cops_status,
        "bl_status": bl_status,
    }


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def _check_candidate_centre(user: CurrentUser, candidate_id: int) -> dict[str, Any]:
    """Retrieve candidate and verify user state and centre authorization."""
    try:
        res = retry_read_query(
            lambda: supabase.table("ddugky_candidates")
            .select("*")
            .eq("candidate_id", candidate_id)
            .limit(1)
            .execute()
        )
    except TRANSIENT_ERRORS as exc:
        logger.warning("Transient error fetching candidate %s: %s", candidate_id, exc)
        raise HTTPException(
            503,
            "Candidate verification service temporarily unreachable. Please retry.",
            headers={"Retry-After": "1"},
        )

    if not res.data:
        # Fallback to legacy candidates table if present
        try:
            cand_fallback = retry_read_query(
                lambda: supabase.table("candidates")
                .select("*, batches!inner(tc_id, batch_code, sanction_order)")
                .eq("candidate_id", candidate_id)
                .limit(1)
                .execute()
            )
            if cand_fallback.data:
                c = cand_fallback.data[0]
                if "batches" in c and isinstance(c["batches"], dict):
                    c["tc_id"] = c["batches"].get("tc_id")
            else:
                raise HTTPException(404, f"Candidate {candidate_id} not found.")
        except HTTPException:
            raise
        except TRANSIENT_ERRORS as exc:
            logger.warning("Transient error on fallback fetching candidate %s: %s", candidate_id, exc)
            raise HTTPException(
                503,
                "Candidate verification service temporarily unreachable. Please retry.",
                headers={"Retry-After": "1"},
            )
        except Exception:
            raise HTTPException(404, f"Candidate {candidate_id} not found.")
    else:
        c = res.data[0]

    check_candidate_access(user, c)
    return c


def _execute_audit_update(query: Any, candidate_id: int, action_desc: str) -> Any:
    """Execute a database update/insert query atomically with clean error translation."""
    try:
        return query.execute()
    except APIError as exc:
        code = getattr(exc, "code", None)
        msg = getattr(exc, "message", None) or str(exc)
        logger.error(
            "PostgREST database error during %s for candidate %s: code=%s message=%s",
            action_desc,
            candidate_id,
            code,
            msg,
        )
        if code == "23514":
            raise HTTPException(
                400,
                f"Database constraint violation during {action_desc}: One or more audit status values are not permitted.",
            )
        raise HTTPException(
            400,
            f"Database error during {action_desc}: {msg or 'Request could not be saved.'}",
        )
    except TRANSIENT_ERRORS as exc:
        logger.error("Network transport error during %s for candidate %s: %s", action_desc, candidate_id, exc)
        raise HTTPException(503, "Database service temporarily unreachable. Please retry.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error during %s for candidate %s: %s", action_desc, candidate_id, exc)
        raise HTTPException(500, "An unexpected error occurred while saving the placement audit.")


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
        res = retry_read_query(
            lambda: supabase.table("placement_audits")
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
    except TRANSIENT_ERRORS as exc:
        logger.warning("Transient transport error querying placement_audits for candidate %s: %s", candidate_id, exc)
        raise HTTPException(
            503,
            "Placement audit service temporarily unreachable. Please retry.",
            headers={"Retry-After": "1"},
        )
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

    signoff_dict = audit_payload.get("signoff_details") or {}
    if "review_stages" not in signoff_dict:
        signoff_dict["review_stages"] = {
            "ch": {"status": "Pending"},
            "cops": {"status": "Pending"},
            "bl": {"status": "Pending"},
        }
    audit_payload["signoff_details"] = signoff_dict

    if existing_res.data:
        existing = existing_res.data[0]
        if existing.get("audit_status") == "SUBMITTED" and user.role != "ADMIN":
            raise HTTPException(400, "This placement audit has already been finalized/submitted and cannot be edited as a draft.")

        # Section 5 read-only enforcement: preserve existing corporate signoff_details from database against L1 modifications
        if user.role == "L1_COORDINATOR":
            if existing.get("signoff_details"):
                audit_payload["signoff_details"] = existing["signoff_details"]
            else:
                for key in ("centre_head", "cops_team", "business_leader"):
                    if key in audit_payload["signoff_details"] and isinstance(audit_payload["signoff_details"][key], dict):
                        audit_payload["signoff_details"][key]["confirmed"] = False

        # Preserve historical remarks if not provided in payload
        if payload.remarks is None and existing.get("remarks"):
            audit_payload["remarks"] = existing["remarks"]

        # Update existing record
        update_q = supabase.table("placement_audits").update(audit_payload).eq("id", existing["id"])
        update_res = _execute_audit_update(update_q, candidate_id, "save draft")
        record = update_res.data[0] if update_res.data else {**existing, **audit_payload}
    else:
        # Insert new draft record
        if user.role == "L1_COORDINATOR":
            for key in ("centre_head", "cops_team", "business_leader"):
                if key in audit_payload["signoff_details"] and isinstance(audit_payload["signoff_details"][key], dict):
                    audit_payload["signoff_details"][key]["confirmed"] = False

        audit_payload["audit_status"] = "DRAFT"
        audit_payload["cpass_status"] = "PENDING"
        audit_payload["created_by"] = user.id
        audit_payload["created_at"] = now_iso

        insert_q = supabase.table("placement_audits").insert(audit_payload)
        insert_res = _execute_audit_update(insert_q, candidate_id, "create draft")
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

    # 2. Validation: At least one employer with employer_name and stable ID
    if not payload.employer_details:
        raise HTTPException(400, "At least one employer entry is required for placement audit submission.")

    for i, emp in enumerate(payload.employer_details):
        if not emp.employer_name or not emp.employer_name.strip():
            raise HTTPException(400, f"Employer #{i + 1}: Employer Name is required.")
        if not emp.id and not emp.employer_id:
            emp.id = f"emp_{i + 1}"
            emp.employer_id = f"emp_{i + 1}"
        elif not emp.id:
            emp.id = emp.employer_id
        elif not emp.employer_id:
            emp.employer_id = emp.id

    # 3. Validation: At least 3 distinct salary entries
    if len(payload.salary_details) < 3:
        raise HTTPException(400, f"At least 3 distinct reporting months of salary details are required (currently provided: {len(payload.salary_details)}).")

    single_emp_id = payload.employer_details[0].id if len(payload.employer_details) == 1 else None

    salary_periods = set()
    for s in payload.salary_details:
        if not s.employer_id and single_emp_id:
            s.employer_id = single_emp_id

        # Scoped uniqueness per employer
        key = f"{s.employer_id or ''}_{s.year}_{s.month}"
        if key in salary_periods:
            emp_obj = next((e for e in payload.employer_details if (e.id == s.employer_id or e.employer_id == s.employer_id)), None)
            emp_label = f" for employer '{emp_obj.employer_name}'" if emp_obj else ""
            raise HTTPException(400, f"Duplicate salary reporting period detected{emp_label}: {s.month}/{s.year}.")
        salary_periods.add(key)
        if s.amount_credited is not None and s.amount_credited < 0:
            raise HTTPException(400, f"Salary amount credited for {s.month}/{s.year} cannot be negative.")

    # 3b. Authoritative backend evidence validation per employer
    try:
        docs_res = (
            supabase.table("candidate_documents")
            .select("id,document_type,reporting_month,reporting_year,employer_id,is_consolidated,coverage_start_month,coverage_start_year,coverage_end_month,coverage_end_year,covered_months,upload_status")
            .eq("candidate_id", candidate_id)
            .neq("upload_status", "FAILED")
            .execute()
        )
        persisted_docs = docs_res.data if (docs_res and isinstance(docs_res.data, list)) else []
    except Exception:
        persisted_docs = []

    # Validate evidence per employer when documents are in DB or when multiple employers are specified
    if persisted_docs or len(payload.employer_details) > 1:
        for idx, emp in enumerate(payload.employer_details):
            emp_id = emp.id or emp.employer_id or f"emp_{idx + 1}"
            emp_name = emp.employer_name.strip()

            # Offer Letter validation
            has_offer = any(
                d.get("document_type") == "APPOINTMENT_LETTER" and (
                    d.get("employer_id") == emp_id or
                    (len(payload.employer_details) == 1 and not d.get("employer_id"))
                )
                for d in persisted_docs
            )
            if not has_offer:
                raise HTTPException(400, f"Missing required Appointment / Offer Letter for employer '{emp_name}'.")

            # Salary Slips validation for this employer's salary entries
            emp_salaries = [
                s for s in payload.salary_details
                if s.employer_id == emp_id or (len(payload.employer_details) == 1 and not s.employer_id)
            ]
            for s in emp_salaries:
                has_slip = any(
                    d.get("document_type") == "SALARY_SLIP" and (
                        (d.get("reporting_month") == s.month and d.get("reporting_year") == s.year) or
                        (len(payload.employer_details) == 1 and not d.get("reporting_month"))
                    ) and (
                        d.get("employer_id") == emp_id or
                        (len(payload.employer_details) == 1 and not d.get("employer_id"))
                    )
                    for d in persisted_docs
                )
                if not has_slip:
                    raise HTTPException(400, f"Missing salary slip for employer '{emp_name}' for reporting month {s.month}/{s.year}.")

                # Bank Statement coverage validation (individual or consolidated)
                covered_by_bank = False
                for d in persisted_docs:
                    if d.get("document_type") != "BANK_STATEMENT":
                        continue
                    doc_emp = d.get("employer_id")
                    if doc_emp and doc_emp != emp_id:
                        continue
                    if not doc_emp and len(payload.employer_details) > 1:
                        continue

                    if d.get("is_consolidated") or (d.get("coverage_start_month") and d.get("coverage_end_month")):
                        cov_list = d.get("covered_months") or []
                        if isinstance(cov_list, str):
                            try:
                                cov_list = json.loads(cov_list)
                            except Exception:
                                cov_list = []
                        if isinstance(cov_list, list) and any(c.get("month") == s.month and c.get("year") == s.year for c in cov_list if isinstance(c, dict)):
                            covered_by_bank = True
                            break
                        start_m = d.get("coverage_start_month")
                        start_y = d.get("coverage_start_year")
                        end_m = d.get("coverage_end_month")
                        end_y = d.get("coverage_end_year")
                        if start_m and start_y and end_m and end_y:
                            cur_val = s.year * 12 + s.month
                            st_val = start_y * 12 + start_m
                            end_val = end_y * 12 + end_m
                            if st_val <= cur_val <= end_val:
                                covered_by_bank = True
                                break
                    else:
                        if (d.get("reporting_month") == s.month and d.get("reporting_year") == s.year) or (len(payload.employer_details) == 1 and not d.get("reporting_month")):
                            covered_by_bank = True
                            break

                if not covered_by_bank:
                    raise HTTPException(400, f"Missing bank statement coverage for employer '{emp_name}' for reporting month {s.month}/{s.year}.")

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

    # Section 5 read-only enforcement: Retain existing corporate signoff endorsements from database
    existing_review_stages = None
    if existing_res.data and existing_res.data[0].get("signoff_details"):
        existing_signoff = existing_res.data[0]["signoff_details"]
        for key in ("centre_head", "cops_team", "business_leader"):
            if key in existing_signoff and existing_signoff[key]:
                signoff_dict[key] = existing_signoff[key]
        existing_review_stages = existing_signoff.get("review_stages")
    else:
        for key in ("centre_head", "cops_team", "business_leader"):
            if key in signoff_dict and isinstance(signoff_dict[key], dict):
                signoff_dict[key]["confirmed"] = False

    existing_record = existing_res.data[0] if existing_res.data else None
    existing_signoff = existing_record.get("signoff_details") or {} if existing_record else {}
    is_resubmission = existing_record and (
        existing_record.get("audit_status") == "RETURNED_TO_L1"
        or existing_record.get("cpass_status") == "RETURNED_TO_L1"
    )

    if is_resubmission:
        # Reset CH and subsequent stages to Pending for fresh review upon coordinator resubmission
        signoff_dict["review_stages"] = {
            "ch": {"status": "Pending"},
            "cops": {"status": "Pending"},
            "bl": {"status": "Pending"},
        }
        # Preserve previous return-to-L1 metadata and return history
        if "return_to_l1" in existing_signoff:
            signoff_dict["return_to_l1"] = existing_signoff["return_to_l1"]
        if "return_history" in existing_signoff:
            signoff_dict["return_history"] = existing_signoff["return_history"]
        rev_history = list(existing_signoff.get("revision_history") or [])
        rev_history.append({
            "action": "RESUBMITTED_BY_L1",
            "stage": "L1",
            "resubmitted_at": now_iso,
            "resubmitted_by": user.full_name,
            "user_id": user.id,
            "role": user.role,
        })
        signoff_dict["revision_history"] = rev_history
    elif existing_review_stages:
        signoff_dict["review_stages"] = existing_review_stages
    else:
        signoff_dict["review_stages"] = {
            "ch": {"status": "Pending"},
            "cops": {"status": "Pending"},
            "bl": {"status": "Pending"},
        }

    doc_audit_data = payload.document_audit.model_dump()

    # Submission by L1 coordinator makes candidate eligible for L2/CH review while keeping review stages Pending
    computed_cpass_status = "PENDING"

    audit_remarks = payload.remarks if payload.remarks is not None else (existing_record.get("remarks") if existing_record else None)

    audit_payload = {
        "candidate_id": candidate_id,
        "candidate_snapshot": snapshot,
        "employer_details": [e.model_dump() for e in payload.employer_details],
        "salary_details": [s.model_dump() for s in payload.salary_details],
        "document_audit": doc_audit_data,
        "signoff_details": signoff_dict,
        "cpass_status": computed_cpass_status,
        "audit_status": "SUBMITTED",
        "remarks": audit_remarks,
        "finalized_at": now_iso,
        "updated_at": now_iso,
    }

    if existing_res.data:
        existing = existing_res.data[0]
        if existing.get("cpass_status") == "APPROVED":
            raise HTTPException(400, "Cannot submit: This placement audit has already received final approval.")
        if existing.get("audit_status") == "SUBMITTED":
            raise HTTPException(400, "This placement audit has already been submitted.")

        update_q = supabase.table("placement_audits").update(audit_payload)
        if existing.get("id"):
            update_q = update_q.eq("id", existing["id"])
        else:
            update_q = update_q.eq("candidate_id", candidate_id)
        update_res = _execute_audit_update(update_q, candidate_id, "submit placement audit")
        record = update_res.data[0] if update_res.data else {**existing, **audit_payload}
    else:
        audit_payload["created_by"] = user.id
        audit_payload["created_at"] = now_iso

        insert_q = supabase.table("placement_audits").insert(audit_payload)
        insert_res = _execute_audit_update(insert_q, candidate_id, "submit placement audit")
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
    try:
        audit_res = retry_read_query(
            lambda: supabase.table("placement_audits")
            .select("*")
            .eq("candidate_id", candidate_id)
            .limit(1)
            .execute()
        )
    except TRANSIENT_ERRORS as exc:
        logger.warning("Transient error fetching placement_audits for statement %s: %s", candidate_id, exc)
        raise HTTPException(
            503,
            "Placement audit service temporarily unreachable. Please retry.",
            headers={"Retry-After": "1"},
        )
    audit = audit_res.data[0] if audit_res.data else None

    # 2. Fetch persisted documents (exclude FAILED status)
    try:
        docs_res = retry_read_query(
            lambda: supabase.table("candidate_documents")
            .select("id,document_type,reporting_month,reporting_year,file_name,file_size_bytes,upload_status,drive_file_id,document_title,created_at,employer_id,is_consolidated,coverage_start_month,coverage_start_year,coverage_end_month,coverage_end_year,covered_months")
            .eq("candidate_id", candidate_id)
            .neq("upload_status", "FAILED")
            .order("created_at")
            .execute()
        )
    except TRANSIENT_ERRORS as exc:
        logger.warning("Transient error fetching candidate_documents for statement %s: %s", candidate_id, exc)
        raise HTTPException(
            503,
            "Document service temporarily unreachable. Please retry.",
            headers={"Retry-After": "1"},
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

    saved_doc_audit = (audit and audit.get("document_audit")) or {}

    def get_row_audit(key: str) -> dict[str, Any]:
        val = saved_doc_audit.get(key)
        if isinstance(val, dict):
            return val
        return {}

    def map_avail_field(audit_val_or_row: Any, has_doc: bool) -> tuple[Any, str]:
        if isinstance(audit_val_or_row, dict):
            raw_val = audit_val_or_row.get("available")
            explicit = bool(audit_val_or_row.get("explicitlySet") or audit_val_or_row.get("explicitly_set"))
        else:
            raw_val = audit_val_or_row
            explicit = False

        if explicit and raw_val in ("No", False):
            return (False, "No")
        if explicit and raw_val == "Pending":
            return ("Pending", "Pending")
        if has_doc:
            return (True, "Yes")
        if raw_val is None or raw_val == "":
            return (False, "Missing")
        if raw_val in ("No", False):
            return (False, "No")
        if raw_val in ("Yes", True):
            return (True, "Yes")
        return ("Pending", "Pending")

    sorted_salaries = sorted(salary_entries, key=lambda s: (s.get("year") or 0, s.get("month") or 0))

    evidence_list: list[dict[str, Any]] = []

    def get_canonical_emp_id(emp_id: Any) -> str | None:
        if not emp_id:
            return str(employer_entries[0].get("id")).strip() if employer_entries else None
        s = str(emp_id).strip()
        for e in employer_entries:
            if str(e.get("id", "")).strip() == s:
                return str(e.get("id")).strip()
        norm = s[4:] if s.startswith("emp_") else s
        try:
            idx = int(norm)
            if 1 <= idx <= len(employer_entries):
                return str(employer_entries[idx - 1].get("id")).strip()
        except (ValueError, TypeError):
            pass
        if len(employer_entries) <= 1 and employer_entries:
            return str(employer_entries[0].get("id")).strip()
        return s

    def emp_matches(doc_emp: Any, target_emp: Any) -> bool:
        if len(employer_entries) <= 1:
            return True
        if not doc_emp or not target_emp:
            return True
        can_doc = get_canonical_emp_id(doc_emp)
        can_target = get_canonical_emp_id(target_emp)
        if can_doc and can_target:
            return can_doc == can_target
        return str(doc_emp).strip() == str(target_emp).strip()

    # Helper to check if bank document covers a given month/year
    def doc_covers_bank_month(doc: dict[str, Any], month: int, year: int) -> bool:
        if not doc or doc.get("document_type") != "BANK_STATEMENT":
            return False
        st_upper = str(doc.get("upload_status") or "").upper()
        if st_upper != "SUCCESS" and doc.get("upload_status") and not doc.get("drive_file_id"):
            return False
        try:
            m_val = int(month)
            y_val = int(year)
        except (ValueError, TypeError):
            return False
        is_consol = bool(
            doc.get("is_consolidated")
            or (doc.get("coverage_start_month") and doc.get("coverage_end_month"))
        )
        if is_consol:
            cov_list = doc.get("covered_months") or []
            if isinstance(cov_list, str):
                try:
                    cov_list = json.loads(cov_list)
                except Exception:
                    cov_list = []
            if isinstance(cov_list, list) and any(
                isinstance(c, dict) and int(c.get("month", 0)) == m_val and (not c.get("year") or int(c.get("year", 0)) == y_val)
                for c in cov_list
            ):
                return True
            try:
                st_m = int(doc.get("coverage_start_month") or doc.get("reporting_month") or 1)
                st_y = int(doc.get("coverage_start_year") or doc.get("reporting_year") or y_val)
                end_m = int(doc.get("coverage_end_month") or doc.get("reporting_month") or st_m)
                end_y = int(doc.get("coverage_end_year") or doc.get("reporting_year") or st_y)
                return (st_y * 12 + st_m) <= (y_val * 12 + m_val) <= (end_y * 12 + end_m)
            except (ValueError, TypeError):
                return False
        try:
            return int(doc.get("reporting_month", 0)) == m_val and (not doc.get("reporting_year") or int(doc.get("reporting_year", 0)) == y_val)
        except (ValueError, TypeError):
            return False

    if len(employer_entries) > 1:
        # Multi-Employer Evidence Organization
        for e_idx, emp in enumerate(employer_entries):
            emp_id = emp.get("id") or emp.get("employer_id") or f"emp_{e_idx + 1}"
            emp_name = emp.get("employer_name") or f"Employer {e_idx + 1}"

            # 1. Appointment Letter for this employer
            al_doc = next(
                (d for d in docs if d.get("document_type") == "APPOINTMENT_LETTER" and (str(d.get("upload_status") or "").upper() == "SUCCESS" or d.get("drive_file_id")) and emp_matches(d.get("employer_id"), emp_id)),
                None,
            )
            key_al = f"appointment_letter_{emp_id}"
            al_audit = get_row_audit(key_al)
            al_avail, al_avail_str = map_avail_field(al_audit.get("available"), bool(al_doc))
            al_comp = al_audit.get("compliance") or ("Compliant" if al_doc else "Missing / Non-Compliant")
            al_obs = al_audit.get("remarks") or (f"Appointment letter verified for {emp_name}." if al_doc else f"Offer letter pending upload for {emp_name}.")
            al_repo = f"Stored in Drive: {al_doc['file_name']}" if al_doc else ("Document marked unavailable" if al_avail_str == "No" else "No verified file in database")

            evidence_list.append({
                "code": f"AL / OL ({e_idx + 1})",
                "key": key_al,
                "label": f"Appointment / Offer Letter — {emp_name}",
                "employer_id": emp_id,
                "employer_name": emp_name,
                "available": al_avail,
                "availability_status": al_avail_str,
                "compliance": al_comp,
                "repository_status": al_repo,
                "observations": al_obs,
                "file_name": al_doc["file_name"] if al_doc else None,
                "doc_id": al_doc["id"] if al_doc else None,
                "drive_file_id": al_doc.get("drive_file_id") if al_doc else None,
            })

            # 2. Salary Slips for this employer
            emp_salaries = [s for s in sorted_salaries if emp_matches(s.get("employer_id"), emp_id)]
            for s_idx, sal in enumerate(emp_salaries):
                s_month = sal.get("month")
                s_year = sal.get("year")
                m_str = MONTH_NAMES[s_month - 1] if s_month and 1 <= s_month <= 12 else f"Month {s_month}"
                slip_doc = next(
                    (d for d in docs if d.get("document_type") == "SALARY_SLIP" and (str(d.get("upload_status") or "").upper() == "SUCCESS" or d.get("drive_file_id")) and emp_matches(d.get("employer_id"), emp_id) and d.get("reporting_month") == s_month and d.get("reporting_year") == s_year),
                    None,
                )
                key_ps = f"salary_slip_{emp_id}_{s_idx + 1}"
                s_audit = get_row_audit(key_ps)
                s_avail, s_avail_str = map_avail_field(s_audit.get("available"), bool(slip_doc))
                s_comp = s_audit.get("compliance") or ("Compliant" if slip_doc else "Missing / Non-Compliant")
                s_obs = s_audit.get("remarks") or (f"Salary slip verified for {emp_name}." if slip_doc else f"Salary slip pending upload for {emp_name}.")
                s_repo = f"Stored in Drive: {slip_doc['file_name']}" if slip_doc else ("Document marked unavailable" if s_avail_str == "No" else "No verified file in database")

                evidence_list.append({
                    "code": f"PS {s_idx + 1} ({e_idx + 1})",
                    "key": key_ps,
                    "label": f"Salary Pay Slip — {m_str} {s_year} ({emp_name})",
                    "employer_id": emp_id,
                    "employer_name": emp_name,
                    "available": s_avail,
                    "availability_status": s_avail_str,
                    "compliance": s_comp,
                    "repository_status": s_repo,
                    "observations": s_obs,
                    "file_name": slip_doc["file_name"] if slip_doc else None,
                    "doc_id": slip_doc["id"] if slip_doc else None,
                    "drive_file_id": slip_doc.get("drive_file_id") if slip_doc else None,
                    "reporting_month": s_month,
                    "reporting_year": s_year,
                })

            # 3. Bank Statements for this employer
            for b_idx, sal in enumerate(emp_salaries):
                s_month = sal.get("month")
                s_year = sal.get("year")
                m_str = MONTH_NAMES[s_month - 1] if s_month and 1 <= s_month <= 12 else f"Month {s_month}"
                bank_doc = next(
                    (d for d in docs if emp_matches(d.get("employer_id"), emp_id) and doc_covers_bank_month(d, s_month, s_year)),
                    None,
                )
                key_bs = f"bank_statement_{emp_id}_{b_idx + 1}"
                b_audit = get_row_audit(key_bs)
                b_avail, b_avail_str = map_avail_field(b_audit.get("available"), bool(bank_doc))
                b_comp = b_audit.get("compliance") or ("Compliant" if bank_doc else "Missing / Non-Compliant")
                is_consol = bool(bank_doc and (bank_doc.get("is_consolidated") or (bank_doc.get("coverage_start_month") and bank_doc.get("coverage_end_month"))))
                consol_note = " (Consolidated Statement)" if is_consol else ""
                b_obs = b_audit.get("remarks") or (f"Bank credit verified for {emp_name}{consol_note}." if bank_doc else f"Bank statement pending upload for {emp_name}.")
                b_repo = f"Stored in Drive: {bank_doc['file_name']}{consol_note}" if bank_doc else ("Document marked unavailable" if b_avail_str == "No" else "No verified file in database")
                cov_str = None
                if is_consol and bank_doc:
                    st_m = bank_doc.get("coverage_start_month")
                    st_y = bank_doc.get("coverage_start_year")
                    end_m = bank_doc.get("coverage_end_month")
                    end_y = bank_doc.get("coverage_end_year")
                    if st_m and end_m:
                        cov_str = f"{MONTH_NAMES[int(st_m) - 1]} {st_y or ''} – {MONTH_NAMES[int(end_m) - 1]} {end_y or ''}".strip()

                evidence_list.append({
                    "code": f"BS {b_idx + 1} ({e_idx + 1})",
                    "key": key_bs,
                    "label": f"Bank Statement / Passbook — {m_str} {s_year} ({emp_name}){consol_note}",
                    "employer_id": emp_id,
                    "employer_name": emp_name,
                    "is_consolidated": is_consol,
                    "coverage_period": cov_str,
                    "coverage_start_month": bank_doc.get("coverage_start_month") if is_consol else None,
                    "coverage_start_year": bank_doc.get("coverage_start_year") if is_consol else None,
                    "coverage_end_month": bank_doc.get("coverage_end_month") if is_consol else None,
                    "coverage_end_year": bank_doc.get("coverage_end_year") if is_consol else None,
                    "covered_months": bank_doc.get("covered_months") if is_consol else [],
                    "available": b_avail,
                    "availability_status": b_avail_str,
                    "compliance": b_comp,
                    "repository_status": b_repo,
                    "observations": b_obs,
                    "file_name": bank_doc["file_name"] if bank_doc else None,
                    "doc_id": bank_doc["id"] if bank_doc else None,
                    "drive_file_id": bank_doc.get("drive_file_id") if bank_doc else None,
                    "reporting_month": s_month,
                    "reporting_year": s_year,
                })

    else:
        # Single-Employer Backward-Compatible Structure (AL/OL, PS 1-3, BS 1-3)
        single_emp_name = employer_entries[0].get("employer_name") if employer_entries else None
        single_emp_id = employer_entries[0].get("id") or employer_entries[0].get("employer_id") if employer_entries else None

        al_doc = next(
            (d for d in docs if d.get("document_type") == "APPOINTMENT_LETTER" and d.get("upload_status") == "SUCCESS"),
            None,
        )
        successful_slips = sorted(
            [d for d in docs if d.get("document_type") == "SALARY_SLIP" and d.get("upload_status") == "SUCCESS"],
            key=lambda d: (d.get("reporting_year") or 0, d.get("reporting_month") or 0),
        )

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
                target_emp = sorted_salaries[idx].get("employer_id") or single_emp_id
                match = next((d for d in docs if doc_covers_bank_month(d, target_month, target_year) and emp_matches(d.get("employer_id"), target_emp)), None)
                if match:
                    return match
            return None

        def slip_label(idx: int) -> str:
            if idx < len(sorted_salaries) and sorted_salaries[idx].get("month"):
                m = sorted_salaries[idx]["month"]
                y = sorted_salaries[idx].get("year")
                m_str = MONTH_NAMES[m - 1] if 1 <= m <= 12 else f"Month {m}"
                return f"Salary Pay Slip — {m_str} {y or ''}".strip()
            return f"Salary Pay Slip — Month {idx + 1}"

        def bank_label(idx: int) -> str:
            doc = find_bank_doc(idx)
            if idx < len(sorted_salaries) and sorted_salaries[idx].get("month"):
                m = sorted_salaries[idx]["month"]
                y = sorted_salaries[idx].get("year")
                m_str = MONTH_NAMES[m - 1] if 1 <= m <= 12 else f"Month {m}"
                consol_suffix = " (Consolidated Statement)" if (doc and (doc.get("is_consolidated") or (doc.get("coverage_start_month") and doc.get("coverage_end_month")))) else ""
                return f"Bank Statement / Passbook — {m_str} {y or ''}{consol_suffix}".strip()
            return f"Bank Statement / Passbook — Month {idx + 1}"

        # AL / OL
        al_audit = get_row_audit("appointment_letter")
        al_avail, al_avail_str = map_avail_field(al_audit.get("available"), bool(al_doc))
        al_comp = al_audit.get("compliance") or ("Compliant" if al_doc else "Missing / Non-Compliant")
        al_obs = al_audit.get("remarks") or ("Appointment letter verified against candidate placement record." if al_doc else "Mandatory appointment/offer letter is pending upload.")
        al_repo = f"Stored in Drive: {al_doc['file_name']}" if al_doc else ("Document marked unavailable by coordinator" if al_avail_str == "No" else ("Document pending upload" if al_avail_str == "Pending" else "No verified file in database"))

        evidence_list.append({
            "code": "AL / OL",
            "key": "appointment_letter",
            "label": "Appointment / Offer Letter",
            "employer_id": single_emp_id,
            "employer_name": single_emp_name,
            "available": al_avail,
            "availability_status": al_avail_str,
            "compliance": al_comp,
            "repository_status": al_repo,
            "observations": al_obs,
            "file_name": al_doc["file_name"] if al_doc else None,
            "doc_id": al_doc["id"] if al_doc else None,
            "drive_file_id": al_doc.get("drive_file_id") if al_doc else None,
        })

        for i in range(max(3, len(sorted_salaries))):
            doc = find_slip_doc(i)
            key = f"salary_slip_{i + 1}"
            s_audit = get_row_audit(key)
            s_avail, s_avail_str = map_avail_field(s_audit.get("available"), bool(doc))
            s_comp = s_audit.get("compliance") or ("Compliant" if doc else "Missing / Non-Compliant")
            s_obs = s_audit.get("remarks") or ("Disbursement slip verified with gross remuneration." if doc else "Salary slip pending upload.")
            s_repo = f"Stored in Drive: {doc['file_name']}" if doc else ("Document marked unavailable by coordinator" if s_avail_str == "No" else ("Document pending upload" if s_avail_str == "Pending" else "No verified file in database"))

            evidence_list.append({
                "code": f"PS {i + 1}",
                "key": key,
                "label": slip_label(i),
                "employer_id": single_emp_id,
                "employer_name": single_emp_name,
                "available": s_avail,
                "availability_status": s_avail_str,
                "compliance": s_comp,
                "repository_status": s_repo,
                "observations": s_obs,
                "file_name": doc["file_name"] if doc else None,
                "doc_id": doc["id"] if doc else None,
                "drive_file_id": doc.get("drive_file_id") if doc else None,
                "reporting_month": doc.get("reporting_month") if doc else None,
                "reporting_year": doc.get("reporting_year") if doc else None,
            })

        for i in range(max(3, len(sorted_salaries))):
            doc = find_bank_doc(i)
            key = f"bank_statement_{i + 1}"
            b_audit = get_row_audit(key)
            b_avail, b_avail_str = map_avail_field(b_audit.get("available"), bool(doc))
            b_comp = b_audit.get("compliance") or ("Compliant" if doc else "Missing / Non-Compliant")
            is_consol = bool(doc and (doc.get("is_consolidated") or (doc.get("coverage_start_month") and doc.get("coverage_end_month"))))
            consol_note = " (Consolidated Statement)" if is_consol else ""
            b_obs = b_audit.get("remarks") or (f"Bank statement credit entry verified{consol_note}." if doc else "Mandatory bank statement is pending upload.")
            b_repo = f"Stored in Drive: {doc['file_name']}{consol_note}" if doc else ("Document marked unavailable by coordinator" if b_avail_str == "No" else ("Document pending upload" if b_avail_str == "Pending" else "No verified file in database"))
            cov_str = None
            if is_consol and doc:
                st_m = doc.get("coverage_start_month")
                st_y = doc.get("coverage_start_year")
                end_m = doc.get("coverage_end_month")
                end_y = doc.get("coverage_end_year")
                if st_m and end_m:
                    cov_str = f"{MONTH_NAMES[int(st_m) - 1]} {st_y or ''} – {MONTH_NAMES[int(end_m) - 1]} {end_y or ''}".strip()

            target_m = sorted_salaries[i].get("month") if i < len(sorted_salaries) else (doc.get("reporting_month") if doc else None)
            target_y = sorted_salaries[i].get("year") if i < len(sorted_salaries) else (doc.get("reporting_year") if doc else None)

            evidence_list.append({
                "code": f"BS {i + 1}",
                "key": key,
                "label": bank_label(i),
                "employer_id": single_emp_id,
                "employer_name": single_emp_name,
                "is_consolidated": is_consol,
                "coverage_period": cov_str,
                "coverage_start_month": doc.get("coverage_start_month") if is_consol else None,
                "coverage_start_year": doc.get("coverage_start_year") if is_consol else None,
                "coverage_end_month": doc.get("coverage_end_month") if is_consol else None,
                "coverage_end_year": doc.get("coverage_end_year") if is_consol else None,
                "covered_months": doc.get("covered_months") if is_consol else [],
                "available": b_avail,
                "availability_status": b_avail_str,
                "compliance": b_comp,
                "repository_status": b_repo,
                "observations": b_obs,
                "file_name": doc["file_name"] if doc else None,
                "doc_id": doc["id"] if doc else None,
                "drive_file_id": doc.get("drive_file_id") if doc else None,
                "reporting_month": target_m,
                "reporting_year": target_y,
            })

    # Row: Optional Other Document
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


    employer_summaries = {}
    if len(employer_entries) > 1:
        for e_idx, emp in enumerate(employer_entries):
            emp_id = emp.get("id") or emp.get("employer_id") or f"emp_{e_idx + 1}"
            emp_sals = [s for s in salary_entries if (s.get("employer_id") == emp_id or (len(employer_entries) == 1 and not s.get("employer_id")))]
            e_cred = sum(float(s.get("amount_credited") or 0) for s in emp_sals)
            e_gross = sum(float(s.get("gross_salary") or 0) for s in emp_sals)
            e_ded = sum(float(s.get("deductions") or 0) for s in emp_sals)
            e_net = sum(float(s.get("net_salary") or 0) for s in emp_sals)
            e_avg = (e_gross / len(emp_sals)) if emp_sals else 0
            employer_summaries[emp_id] = {
                "employer_name": emp.get("employer_name"),
                "total_credited": round(e_cred, 2),
                "total_gross": round(e_gross, 2),
                "total_deductions": round(e_ded, 2),
                "total_net": round(e_net, 2),
                "average_gross": round(e_avg, 2),
                "month_count": len(emp_sals),
            }

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
            "employer_summaries": employer_summaries,
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
        "return_to_l1": ((audit and audit.get("signoff_details")) or {}).get("return_to_l1") or None,
        "return_history": ((audit and audit.get("signoff_details")) or {}).get("return_history") or [],
        "review_stages": extract_review_stages(audit),
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

    # Rejection gate: cannot approve if candidate has been rejected
    current_stages = extract_review_stages(audit)
    if (
        audit.get("cpass_status") in ("REJECTED", "L2_REJECTED", "CPASS_REJECTED")
        or audit.get("audit_status") == "REJECTED"
        or current_stages["ch_status"] == "Rejected"
    ):
        raise HTTPException(400, "Approval blocked: Candidate has been rejected and cannot progress.")

    # 3. Idempotency check: Already approved by L2
    if audit.get("cpass_status") == "L2_APPROVED" and current_stages["ch_status"] == "Recommended":
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
        .select("id,document_type,reporting_month,reporting_year,file_name,upload_status,employer_id,is_consolidated,coverage_start_month,coverage_start_year,coverage_end_month,coverage_end_year,covered_months")
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

    bank_statement_months = set()
    for d in banks:
        if d.get("is_consolidated"):
            cov = d.get("covered_months") or []
            if isinstance(cov, str):
                try:
                    cov = json.loads(cov)
                except Exception:
                    cov = []
            if isinstance(cov, list) and cov:
                for c in cov:
                    if isinstance(c, dict) and c.get("year") and c.get("month"):
                        bank_statement_months.add((c["year"], c["month"]))
            else:
                st_m = d.get("coverage_start_month")
                st_y = d.get("coverage_start_year")
                end_m = d.get("coverage_end_month")
                end_y = d.get("coverage_end_year")
                if st_m and st_y and end_m and end_y:
                    cur = st_y * 12 + st_m
                    fin = end_y * 12 + end_m
                    while cur <= fin:
                        y = cur // 12
                        m = cur % 12
                        if m == 0:
                            y -= 1
                            m = 12
                        bank_statement_months.add((y, m))
                        cur += 1
        elif d.get("reporting_month"):
            bank_statement_months.add((d.get("reporting_year") or 0, d["reporting_month"]))
        else:
            bank_statement_months.add((0, len(bank_statement_months) + 1))

    if len(bank_statement_months) < 3:
        raise HTTPException(400, f"Approval blocked: At least 3 verified Bank Statement months required (found coverage for: {len(bank_statement_months)}).")

    doc_audit = audit.get("document_audit") or {}
    l2_reviews = doc_audit.get("l2_document_reviews") or {}

    unreviewed = []
    if not l2_reviews.get(str(al_doc["id"]), {}).get("reviewed"):
        unreviewed.append("Appointment / Offer Letter")

    for i, s in enumerate(slips[:3]):
        if not l2_reviews.get(str(s["id"]), {}).get("reviewed"):
            unreviewed.append(f"Salary Slip (Month {s.get('reporting_month') or (i + 1)})")

    for i, b in enumerate(banks):
        if not l2_reviews.get(str(b["id"]), {}).get("reviewed"):
            if b.get("is_consolidated"):
                st_m = b.get("coverage_start_month")
                st_y = b.get("coverage_start_year")
                end_m = b.get("coverage_end_month")
                end_y = b.get("coverage_end_year")
                unreviewed.append(f"Consolidated Bank Statement ({st_m}/{st_y} – {end_m}/{end_y})")
            else:
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
    review_stages = signoff.get("review_stages") or current_stages.get("review_stages") or {}
    review_stages["ch"] = {
        "status": "Recommended",
        "reviewed_at": now_iso,
        "reviewed_by": user.full_name,
        "user_id": user.id,
        "remarks": payload.remarks,
    }
    if "cops" not in review_stages:
        review_stages["cops"] = {"status": "Pending"}
    if "bl" not in review_stages:
        review_stages["bl"] = {"status": "Pending"}
    signoff["review_stages"] = review_stages

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

    up_q = supabase.table("placement_audits").update(update_payload).eq("id", audit["id"])
    up_res = _execute_audit_update(up_q, candidate_id, "CH approval")
    updated_record = up_res.data[0] if up_res.data else {**audit, **update_payload}

    return {
        "status": "success",
        "message": "Placement Audit Statement successfully approved by L2 Center Manager.",
        "cpass_status": "L2_APPROVED",
        "audit": updated_record,
        "approved_at": now_iso,
        "approved_by": user.full_name,
    }


@router.post("/l2-review/reject")
def reject_l2_placement_audit(
    candidate_id: int,
    payload: StageRejectRequest,
    user: CurrentUser = Depends(require_roles("L2_MANAGER", "ADMIN")),
):
    """Record L2 Center Manager rejection and stop review progression."""
    cand = _check_candidate_centre(user, candidate_id)

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

    # Cannot reject if already given final approval
    if audit.get("cpass_status") == "APPROVED":
        raise HTTPException(400, "Cannot reject: Candidate has already received final approval.")

    signoff = audit.get("signoff_details") or {}
    current_stages = extract_review_stages(audit)
    review_stages = signoff.get("review_stages") or current_stages.get("review_stages") or {}

    # Idempotent check
    if current_stages["ch_status"] == "Rejected":
        return {
            "status": "already_rejected",
            "message": "Placement audit has already been rejected at L2 CH stage.",
            "cpass_status": "REJECTED",
            "audit": audit,
        }

    now_iso = datetime.now(timezone.utc).isoformat()
    review_stages["ch"] = {
        "status": "Rejected",
        "reviewed_at": now_iso,
        "reviewed_by": user.full_name,
        "user_id": user.id,
        "rejection_reason": payload.rejection_reason,
        "remarks": payload.remarks,
    }
    if "cops" not in review_stages:
        review_stages["cops"] = {"status": "Pending"}
    if "bl" not in review_stages:
        review_stages["bl"] = {"status": "Pending"}

    signoff["review_stages"] = review_stages
    signoff["rejected_stage"] = "ch"
    signoff["rejection_reason"] = payload.rejection_reason

    history = signoff.get("revision_history") or []
    history.append({
        "action": "REJECTED_L2",
        "stage": "CH",
        "rejected_at": now_iso,
        "rejected_by": user.full_name,
        "user_id": user.id,
        "role": user.role,
        "reason": payload.rejection_reason,
        "remarks": payload.remarks,
    })
    signoff["revision_history"] = history

    update_payload = {
        "cpass_status": "REJECTED",
        "audit_status": "REJECTED",
        "signoff_details": signoff,
        "remarks": payload.remarks or audit.get("remarks") or payload.rejection_reason,
        "updated_at": now_iso,
    }

    up_q = supabase.table("placement_audits").update(update_payload).eq("id", audit["id"])
    up_res = _execute_audit_update(up_q, candidate_id, "CH rejection")
    updated_record = up_res.data[0] if up_res.data else {**audit, **update_payload}

    return {
        "status": "success",
        "message": "Placement Audit Statement rejected by L2 Center Manager.",
        "cpass_status": "REJECTED",
        "audit": updated_record,
        "rejected_at": now_iso,
        "rejected_by": user.full_name,
    }


@router.post("/l2-review/return-to-l1")
def return_l2_placement_audit(
    candidate_id: int,
    payload: StageReturnRequest,
    user: CurrentUser = Depends(require_roles("L2_MANAGER", "ADMIN")),
):
    """Return candidate placement audit to L1 Coordinator for corrections.

    - Requires explicit correction reason.
    - Preserves all uploaded documents, statement fields, and audit history.
    - Updates audit_status and cpass_status to RETURNED_TO_L1.
    - Sets review_stages.ch.status to 'Returned'.
    - Disallows L3 COPS or L4 BL progression until resubmitted and recommended by CH.
    """
    cand = _check_candidate_centre(user, candidate_id)

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

    # Cannot return if already given final approval
    if audit.get("cpass_status") == "APPROVED":
        raise HTTPException(400, "Cannot return: Candidate has already received final approval.")

    current_stages = extract_review_stages(audit)
    signoff = audit.get("signoff_details") or {}
    review_stages = signoff.get("review_stages") or current_stages.get("review_stages") or {}

    # Idempotent check: candidate is already in RETURNED_TO_L1 state
    if audit.get("audit_status") == "RETURNED_TO_L1" and current_stages["ch_status"] == "Returned to L1":
        return {
            "status": "already_returned",
            "message": "Candidate has already been returned to L1 for corrections.",
            "cpass_status": "RETURNED_TO_L1",
            "audit": audit,
        }

    reason_clean = (payload.return_reason or "").strip()
    if not reason_clean:
        raise HTTPException(422, "Rejection/correction reason cannot be empty.")

    now_iso = datetime.now(timezone.utc).isoformat()
    previous_cpass = audit.get("cpass_status")
    previous_audit = audit.get("audit_status")

    review_stages["ch"] = {
        "status": "Returned to L1",
        "returned_at": now_iso,
        "returned_by": user.full_name,
        "user_id": user.id,
        "reason": reason_clean,
        "return_reason": reason_clean,
        "remarks": payload.remarks,
    }
    review_stages["cops"] = {"status": "Pending"}
    review_stages["bl"] = {"status": "Pending"}
    signoff["review_stages"] = review_stages

    return_entry = {
        "reason": reason_clean,
        "return_reason": reason_clean,
        "remarks": payload.remarks,
        "returned_at": now_iso,
        "returned_by": user.full_name,
        "returned_by_name": user.full_name,
        "user_id": user.id,
        "role": user.role,
        "previous_cpass_status": previous_cpass,
        "previous_audit_status": previous_audit,
    }
    signoff["return_to_l1"] = return_entry

    return_hist = list(signoff.get("return_history") or [])
    return_hist.append(return_entry)
    signoff["return_history"] = return_hist

    history = list(signoff.get("revision_history") or [])
    history.append({
        "action": "RETURNED_TO_L1",
        "stage": "CH",
        "returned_at": now_iso,
        "returned_by": user.full_name,
        "user_id": user.id,
        "role": user.role,
        "reason": reason_clean,
        "remarks": payload.remarks,
        "previous_cpass_status": previous_cpass,
        "previous_audit_status": previous_audit,
    })
    signoff["revision_history"] = history

    update_payload = {
        "cpass_status": "RETURNED_TO_L1",
        "audit_status": "RETURNED_TO_L1",
        "signoff_details": signoff,
        "remarks": payload.remarks or audit.get("remarks") or reason_clean,
        "updated_at": now_iso,
    }

    up_q = supabase.table("placement_audits").update(update_payload)
    if audit.get("id"):
        up_q = up_q.eq("id", audit["id"])
    else:
        up_q = up_q.eq("candidate_id", candidate_id)
    up_res = _execute_audit_update(up_q, candidate_id, "CH return to L1")
    updated_record = up_res.data[0] if up_res.data else {**audit, **update_payload}

    return {
        "status": "success",
        "message": "Placement audit successfully returned to L1 coordinator for corrections.",
        "cpass_status": "RETURNED_TO_L1",
        "audit": updated_record,
        "returned_at": now_iso,
        "returned_by": user.full_name,
    }


@router.post("/l3-review/approve")
def approve_l3_cops_audit(
    candidate_id: int,
    payload: StageApproveRequest,
    user: CurrentUser = Depends(require_roles("L3_COPS", "L3_LEADER", "ADMIN")),
):
    """Validate CH recommendation and record L3 COPS verification."""
    cand = _check_candidate_centre(user, candidate_id)

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

    # Blocked if candidate has been returned for corrections
    current_stages = extract_review_stages(audit)
    if (
        audit.get("cpass_status") == "RETURNED_TO_L1"
        or audit.get("audit_status") == "RETURNED_TO_L1"
        or current_stages["ch_status"] == "Returned to L1"
    ):
        raise HTTPException(400, "COPS review blocked: Candidate has been returned to L1 for corrections and cannot progress until resubmitted and recommended by CH.")

    # Blocked if rejected at any stage
    if (
        audit.get("cpass_status") in ("REJECTED", "L2_REJECTED", "CPASS_REJECTED")
        or audit.get("audit_status") == "REJECTED"
        or current_stages["ch_status"] == "Rejected"
        or current_stages["cops_status"] == "Rejected"
        or current_stages["bl_status"] == "Rejected"
    ):
        raise HTTPException(400, "Review blocked: Candidate has already been rejected and cannot progress.")

    # Sequencing check: Candidate must first be recommended by CH (L2)
    if current_stages["ch_status"] != "Recommended":
        raise HTTPException(400, "COPS review blocked: Candidate must first be recommended by L2 Center Head.")

    # Idempotency check: Already verified by COPS
    if current_stages["cops_status"] == "Verified":
        return {
            "status": "already_approved",
            "message": "Placement audit has already been verified by L3 COPS.",
            "cpass_status": "VERIFIED",
            "audit": audit,
        }

    now_iso = datetime.now(timezone.utc).isoformat()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    signoff = audit.get("signoff_details") or {}
    review_stages = signoff.get("review_stages") or current_stages.get("review_stages") or {}
    review_stages["ch"] = current_stages["ch"]
    review_stages["cops"] = {
        "status": "Verified",
        "reviewed_at": now_iso,
        "reviewed_by": user.full_name,
        "user_id": user.id,
        "remarks": payload.remarks,
    }
    if "bl" not in review_stages:
        review_stages["bl"] = {"status": "Pending"}

    signoff["review_stages"] = review_stages
    signoff["cops_team"] = {
        "name": user.full_name,
        "designation": "COPS Auditor",
        "date": today_str,
        "remarks": payload.remarks or "Verified and endorsed by COPS team.",
        "confirmed": True,
        "verified_by_id": user.id,
    }

    update_payload = {
        "cpass_status": "VERIFIED",
        "signoff_details": signoff,
        "updated_at": now_iso,
    }

    up_q = supabase.table("placement_audits").update(update_payload).eq("id", audit["id"])
    up_res = _execute_audit_update(up_q, candidate_id, "COPS approval")
    updated_record = up_res.data[0] if up_res.data else {**audit, **update_payload}

    return {
        "status": "success",
        "message": "Placement Audit Statement verified by L3 COPS.",
        "cpass_status": "VERIFIED",
        "audit": updated_record,
        "verified_at": now_iso,
        "verified_by": user.full_name,
    }


@router.post("/l3-review/reject")
def reject_l3_cops_audit(
    candidate_id: int,
    payload: StageRejectRequest,
    user: CurrentUser = Depends(require_roles("L3_COPS", "L3_LEADER", "ADMIN")),
):
    """Record L3 COPS rejection and stop review progression."""
    cand = _check_candidate_centre(user, candidate_id)

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

    current_stages = extract_review_stages(audit)

    # Sequencing check: Must be recommended by CH before COPS can review
    if current_stages["ch_status"] != "Recommended":
        raise HTTPException(400, "COPS review blocked: Candidate must first be recommended by L2 Center Head.")

    # Idempotent check
    if current_stages["cops_status"] == "Rejected":
        return {
            "status": "already_rejected",
            "message": "Placement audit has already been rejected at L3 COPS stage.",
            "cpass_status": "REJECTED",
            "audit": audit,
        }

    now_iso = datetime.now(timezone.utc).isoformat()
    signoff = audit.get("signoff_details") or {}
    review_stages = signoff.get("review_stages") or current_stages.get("review_stages") or {}
    review_stages["ch"] = current_stages["ch"]
    review_stages["cops"] = {
        "status": "Rejected",
        "reviewed_at": now_iso,
        "reviewed_by": user.full_name,
        "user_id": user.id,
        "rejection_reason": payload.rejection_reason,
        "remarks": payload.remarks,
    }
    if "bl" not in review_stages:
        review_stages["bl"] = {"status": "Pending"}

    signoff["review_stages"] = review_stages
    signoff["rejected_stage"] = "cops"
    signoff["rejection_reason"] = payload.rejection_reason

    history = signoff.get("revision_history") or []
    history.append({
        "action": "REJECTED_L3",
        "stage": "COPS",
        "rejected_at": now_iso,
        "rejected_by": user.full_name,
        "user_id": user.id,
        "role": user.role,
        "reason": payload.rejection_reason,
        "remarks": payload.remarks,
    })
    signoff["revision_history"] = history

    update_payload = {
        "cpass_status": "REJECTED",
        "audit_status": "REJECTED",
        "signoff_details": signoff,
        "remarks": payload.remarks or audit.get("remarks") or payload.rejection_reason,
        "updated_at": now_iso,
    }

    up_q = supabase.table("placement_audits").update(update_payload).eq("id", audit["id"])
    up_res = _execute_audit_update(up_q, candidate_id, "COPS rejection")
    updated_record = up_res.data[0] if up_res.data else {**audit, **update_payload}

    return {
        "status": "success",
        "message": "Placement Audit Statement rejected by L3 COPS.",
        "cpass_status": "REJECTED",
        "audit": updated_record,
        "rejected_at": now_iso,
        "rejected_by": user.full_name,
    }


@router.post("/l4-review/approve")
def approve_l4_bl_audit(
    candidate_id: int,
    payload: StageApproveRequest,
    user: CurrentUser = Depends(require_roles("L4_LEADER", "ADMIN")),
):
    """Validate COPS verification and record L4 Business Leader final approval."""
    cand = _check_candidate_centre(user, candidate_id)

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

    # Blocked if candidate has been returned for corrections
    current_stages = extract_review_stages(audit)
    if (
        audit.get("cpass_status") == "RETURNED_TO_L1"
        or audit.get("audit_status") == "RETURNED_TO_L1"
        or current_stages["ch_status"] == "Returned to L1"
    ):
        raise HTTPException(400, "BL review blocked: Candidate has been returned to L1 for corrections and cannot progress until resubmitted and recommended by CH.")

    # Blocked if rejected at any stage
    if (
        audit.get("cpass_status") in ("REJECTED", "L2_REJECTED", "CPASS_REJECTED")
        or audit.get("audit_status") == "REJECTED"
        or current_stages["ch_status"] == "Rejected"
        or current_stages["cops_status"] == "Rejected"
        or current_stages["bl_status"] == "Rejected"
    ):
        raise HTTPException(400, "Review blocked: Candidate has already been rejected and cannot progress.")

    # Sequencing check: Candidate must first be verified by COPS (L3)
    if current_stages["cops_status"] != "Verified":
        raise HTTPException(400, "BL review blocked: Candidate must first be verified by L3 COPS.")

    # Idempotency check: Already approved by BL
    if current_stages["bl_status"] == "Approved":
        return {
            "status": "already_approved",
            "message": "Placement audit has already been approved by L4 Business Leader.",
            "cpass_status": "APPROVED",
            "audit": audit,
        }

    now_iso = datetime.now(timezone.utc).isoformat()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    signoff = audit.get("signoff_details") or {}
    review_stages = signoff.get("review_stages") or current_stages.get("review_stages") or {}
    review_stages["ch"] = current_stages["ch"]
    review_stages["cops"] = current_stages["cops"]
    review_stages["bl"] = {
        "status": "Approved",
        "reviewed_at": now_iso,
        "reviewed_by": user.full_name,
        "user_id": user.id,
        "remarks": payload.remarks,
    }

    signoff["review_stages"] = review_stages
    signoff["business_leader"] = {
        "name": user.full_name,
        "designation": "Business Leader",
        "date": today_str,
        "remarks": payload.remarks or "Approved and sanctioned by Business Leader.",
        "confirmed": True,
        "approved_by_id": user.id,
    }

    update_payload = {
        "cpass_status": "APPROVED",
        "signoff_details": signoff,
        "updated_at": now_iso,
    }

    up_q = supabase.table("placement_audits").update(update_payload).eq("id", audit["id"])
    up_res = _execute_audit_update(up_q, candidate_id, "BL approval")
    updated_record = up_res.data[0] if up_res.data else {**audit, **update_payload}

    return {
        "status": "success",
        "message": "Placement Audit Statement approved by L4 Business Leader.",
        "cpass_status": "APPROVED",
        "audit": updated_record,
        "approved_at": now_iso,
        "approved_by": user.full_name,
    }


@router.post("/l4-review/reject")
def reject_l4_bl_audit(
    candidate_id: int,
    payload: StageRejectRequest,
    user: CurrentUser = Depends(require_roles("L4_LEADER", "ADMIN")),
):
    """Record L4 Business Leader rejection and stop review progression."""
    cand = _check_candidate_centre(user, candidate_id)

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

    current_stages = extract_review_stages(audit)

    # Sequencing check: Must be verified by COPS before BL can review
    if current_stages["cops_status"] != "Verified":
        raise HTTPException(400, "BL review blocked: Candidate must first be verified by L3 COPS.")

    # Idempotent check
    if current_stages["bl_status"] == "Rejected":
        return {
            "status": "already_rejected",
            "message": "Placement audit has already been rejected at L4 BL stage.",
            "cpass_status": "REJECTED",
            "audit": audit,
        }

    now_iso = datetime.now(timezone.utc).isoformat()
    signoff = audit.get("signoff_details") or {}
    review_stages = signoff.get("review_stages") or current_stages.get("review_stages") or {}
    review_stages["ch"] = current_stages["ch"]
    review_stages["cops"] = current_stages["cops"]
    review_stages["bl"] = {
        "status": "Rejected",
        "reviewed_at": now_iso,
        "reviewed_by": user.full_name,
        "user_id": user.id,
        "rejection_reason": payload.rejection_reason,
        "remarks": payload.remarks,
    }

    signoff["review_stages"] = review_stages
    signoff["rejected_stage"] = "bl"
    signoff["rejection_reason"] = payload.rejection_reason

    history = signoff.get("revision_history") or []
    history.append({
        "action": "REJECTED_L4",
        "stage": "BL",
        "rejected_at": now_iso,
        "rejected_by": user.full_name,
        "user_id": user.id,
        "role": user.role,
        "reason": payload.rejection_reason,
        "remarks": payload.remarks,
    })
    signoff["revision_history"] = history

    update_payload = {
        "cpass_status": "REJECTED",
        "audit_status": "REJECTED",
        "signoff_details": signoff,
        "remarks": payload.remarks or audit.get("remarks") or payload.rejection_reason,
        "updated_at": now_iso,
    }

    up_q = supabase.table("placement_audits").update(update_payload).eq("id", audit["id"])
    up_res = _execute_audit_update(up_q, candidate_id, "BL rejection")
    updated_record = up_res.data[0] if up_res.data else {**audit, **update_payload}

    return {
        "status": "success",
        "message": "Placement Audit Statement rejected by L4 Business Leader.",
        "cpass_status": "REJECTED",
        "audit": updated_record,
        "rejected_at": now_iso,
        "rejected_by": user.full_name,
    }

