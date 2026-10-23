"""FastAPI router for CPASS Placement Coordinator (L1) Dashboard.

Manages:
- 5 State-Level Summary Cards backed by real database records:
  1. Total candidates in the assigned state
  2. CPASS Approved candidates
  3. CPASS Rejected candidates
  4. CPASS Uploaded candidates
  5. Pending / Remaining candidates (Total - CPASS Uploaded)
- Filtered candidate lists corresponding to each summary card with pagination and search.
- PaySlip availability toggle ("Browse" vs "Not Available") persistence.
- Strict state-based authorization scoping for L1 Coordinators.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..auth import (
    CurrentUser,
    allowed_states,
    check_candidate_access,
    get_candidate_state,
    get_current_user,
    require_roles,
    resolve_state,
)
from ..db import supabase

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Standardized status variants recognized across CPASS placement audit workflow
APPROVED_STATUSES = {"APPROVED", "L2_APPROVED", "CPASS_APPROVED", "VERIFIED"}
REJECTED_STATUSES = {"REJECTED", "L2_REJECTED", "CPASS_REJECTED"}


class PayslipAvailabilityRequest(BaseModel):
    slot_key: str | None = Field(None, description="Salary slip slot key (e.g. salary_slip_1, salary_slip_2, salary_slip_3)")
    month_number: int | None = Field(None, ge=1, le=12, description="Month number slot index (e.g. 1, 2, 3)")
    available: str = Field(..., description="'Yes', 'No', or 'Pending'")
    remarks: str | None = Field(None, description="Optional coordinator remarks")
    month: int | None = Field(None, ge=1, le=12, description="Reporting month (1-12)")
    year: int | None = Field(None, ge=2000, le=2050, description="Reporting year")


def _get_target_state(user: CurrentUser, state_param: str | None) -> str | None:
    """Resolve and enforce state scoping for the current user.

    For L1_COORDINATOR:
    - Strictly bound to user.assigned_state.
    - If unassigned, returns None (fail-closed).
    - If state_param is provided, it must match user.assigned_state; otherwise 403.

    For Global Roles (ADMIN, L3, L4, L5):
    - Uses state_param if given, otherwise falls back to user.assigned_state or defaults to None.
    """
    permitted_st = allowed_states(user)

    if permitted_st is not None:
        if not permitted_st:
            return None  # Fail closed: unassigned coordinator sees no state
        assigned_state = permitted_st[0]
        if state_param:
            resolved_query = resolve_state(state_param) or state_param
            if resolved_query != assigned_state and state_param != assigned_state:
                raise HTTPException(403, f"Access to state '{state_param}' is forbidden. You are assigned to '{assigned_state}'.")
        return assigned_state

    # Global roles
    if state_param:
        return resolve_state(state_param) or state_param
    if user.assigned_state:
        return user.assigned_state
    return None


@router.get("/summary")
def get_dashboard_summary(
    state: str | None = None,
    user: CurrentUser = Depends(get_current_user),
):
    """Return the 5 state-level summary card figures for the coordinator's assigned state.

    Calculated from real database records:
    1. Total: Total candidates in the assigned state.
    2. CPASS Approved: Candidates approved under CPASS (cpass_status in 'L2_APPROVED', 'APPROVED').
    3. CPASS Rejected: Candidates rejected under CPASS (cpass_status in 'REJECTED', 'L2_REJECTED').
    4. CPASS Uploaded: Candidates uploaded by the Placement Coordinator.
    5. Pending / Remaining: Total Candidates - CPASS Uploaded Candidates.
    """
    target_state = _get_target_state(user, state)
    if not target_state:
        return {
            "state": None,
            "total": 0,
            "cpass_approved": 0,
            "cpass_rejected": 0,
            "cpass_uploaded": 0,
            "pending_remaining": 0,
        }

    # 1. Total Candidates in state
    total_res = (
        supabase.table("ddugky_candidates")
        .select("candidate_id", count="exact")
        .or_(f"state_name.eq.{target_state},tc_state_name.eq.{target_state}")
        .limit(1)
        .execute()
    )
    total_count = total_res.count or 0

    # 2. Uploaded Candidates (candidates in target_state having candidate_documents or placement_audits)
    docs_res = (
        supabase.table("candidate_documents")
        .select("candidate_id")
        .neq("upload_status", "FAILED")
        .execute()
    )
    doc_cids = {d["candidate_id"] for d in (docs_res.data or []) if d.get("candidate_id")}

    aud_res = (
        supabase.table("placement_audits")
        .select("candidate_id,cpass_status,audit_status")
        .execute()
    )
    aud_rows = aud_res.data or []
    audit_map = {a["candidate_id"]: a for a in aud_rows if a.get("candidate_id")}
    all_uploaded_cids = doc_cids | set(audit_map.keys())

    uploaded_in_state: set[int] = set()
    if all_uploaded_cids:
        cand_check = (
            supabase.table("ddugky_candidates")
            .select("candidate_id,state_name,tc_state_name")
            .in_("candidate_id", list(all_uploaded_cids))
            .or_(f"state_name.eq.{target_state},tc_state_name.eq.{target_state}")
            .execute()
        )
        for r in (cand_check.data or []):
            if get_candidate_state(r) == target_state:
                uploaded_in_state.add(r["candidate_id"])

    uploaded_count = len(uploaded_in_state)

    # 3. Confirmed Pending / Remaining business rule:
    # Pending / Remaining = Total Candidates - CPASS Uploaded Candidates
    pending_count = max(0, total_count - uploaded_count)

    # 4. CPASS Approved Candidates in state
    approved_count = 0
    for cid in uploaded_in_state:
        audit = audit_map.get(cid)
        if audit:
            st = (audit.get("cpass_status") or "").upper()
            ast = (audit.get("audit_status") or "").upper()
            if st in APPROVED_STATUSES or ast in {"APPROVED", "L2_APPROVED"}:
                approved_count += 1

    # 5. CPASS Rejected Candidates in state
    rejected_count = 0
    for cid in uploaded_in_state:
        audit = audit_map.get(cid)
        if audit:
            st = (audit.get("cpass_status") or "").upper()
            ast = (audit.get("audit_status") or "").upper()
            if st in REJECTED_STATUSES or ast in REJECTED_STATUSES:
                rejected_count += 1

    return {
        "state": target_state,
        "total": total_count,
        "cpass_approved": approved_count,
        "cpass_rejected": rejected_count,
        "cpass_uploaded": uploaded_count,
        "pending_remaining": pending_count,
    }


@router.get("/candidates")
def get_dashboard_candidates(
    filter: str | None = Query(None, description="Category filter (total, cpass_approved, cpass_rejected, cpass_uploaded, pending_remaining)"),
    filter_type: str | None = Query(None, description="Category filter alias"),
    state: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    user: CurrentUser = Depends(get_current_user),
):
    """Return paginated candidates corresponding to the clicked summary card.

    - total: All candidates in the assigned state.
    - cpass_approved: Candidates approved under CPASS.
    - cpass_rejected: Candidates rejected under CPASS.
    - cpass_uploaded: Candidates uploaded by Placement Coordinator.
    - pending_remaining: Candidates who have not yet been uploaded (Total - Uploaded).
    """
    raw_filter = filter or filter_type or "total"
    norm_filter = raw_filter.strip().lower()
    valid_filters = {"total", "cpass_approved", "cpass_rejected", "cpass_uploaded", "pending_remaining"}
    if norm_filter not in valid_filters:
        raise HTTPException(
            400,
            f"Invalid filter '{raw_filter}'. Allowed: {', '.join(sorted(valid_filters))}",
        )

    actual_page = int(page) if isinstance(page, (int, str)) and str(page).isdigit() and int(page) >= 1 else 1
    actual_page_size = int(page_size) if isinstance(page_size, (int, str)) and str(page_size).isdigit() and int(page_size) >= 1 else 20

    target_state = _get_target_state(user, state)
    if not target_state:
        return {
            "state": None,
            "filter": norm_filter,
            "filter_type": norm_filter,
            "total_count": 0,
            "page": actual_page,
            "page_size": actual_page_size,
            "total_pages": 0,
            "candidates": [],
        }

    # Fetch uploaded IDs and audit statuses for state
    docs_res = (
        supabase.table("candidate_documents")
        .select("candidate_id")
        .neq("upload_status", "FAILED")
        .execute()
    )
    doc_cids = {d["candidate_id"] for d in (docs_res.data or []) if d.get("candidate_id")}

    aud_res = (
        supabase.table("placement_audits")
        .select("candidate_id,cpass_status,audit_status")
        .execute()
    )
    aud_rows = aud_res.data or []
    audit_map = {a["candidate_id"]: a for a in aud_rows if a.get("candidate_id")}
    all_uploaded_cids = doc_cids | set(audit_map.keys())

    uploaded_in_state: set[int] = set()
    if all_uploaded_cids:
        cand_check = (
            supabase.table("ddugky_candidates")
            .select("candidate_id,state_name,tc_state_name")
            .in_("candidate_id", list(all_uploaded_cids))
            .or_(f"state_name.eq.{target_state},tc_state_name.eq.{target_state}")
            .execute()
        )
        for r in (cand_check.data or []):
            if get_candidate_state(r) == target_state:
                uploaded_in_state.add(r["candidate_id"])

    # Compute candidate ID sets for specific filters
    approved_in_state = {
        cid for cid in uploaded_in_state
        if (audit_map.get(cid, {}).get("cpass_status") or "").upper() in APPROVED_STATUSES
        or (audit_map.get(cid, {}).get("audit_status") or "").upper() in {"APPROVED", "L2_APPROVED"}
    }

    rejected_in_state = {
        cid for cid in uploaded_in_state
        if (audit_map.get(cid, {}).get("cpass_status") or "").upper() in REJECTED_STATUSES
        or (audit_map.get(cid, {}).get("audit_status") or "").upper() in REJECTED_STATUSES
    }

    # Build base candidate query
    columns = (
        "candidate_id,candidate_first_name,candidate_last_name,candidate_father_name,"
        "gender,date_of_birth,mobile_number,appointed,employer_name,tc_id,tc_name,"
        "state_name,tc_state_name,kb_batch_id,batch_code,sanction_order_number"
    )

    # Short-circuit empty filter sets
    if norm_filter == "cpass_approved" and not approved_in_state:
        return {
            "state": target_state,
            "filter": norm_filter,
            "filter_type": norm_filter,
            "total_count": 0,
            "page": actual_page,
            "page_size": actual_page_size,
            "total_pages": 0,
            "candidates": [],
        }

    if norm_filter == "cpass_rejected" and not rejected_in_state:
        return {
            "state": target_state,
            "filter": norm_filter,
            "filter_type": norm_filter,
            "total_count": 0,
            "page": actual_page,
            "page_size": actual_page_size,
            "total_pages": 0,
            "candidates": [],
        }

    if norm_filter == "cpass_uploaded" and not uploaded_in_state:
        return {
            "state": target_state,
            "filter": norm_filter,
            "filter_type": norm_filter,
            "total_count": 0,
            "page": actual_page,
            "page_size": actual_page_size,
            "total_pages": 0,
            "candidates": [],
        }

    q = (
        supabase.table("ddugky_candidates")
        .select(columns, count="exact")
        .or_(f"state_name.eq.{target_state},tc_state_name.eq.{target_state}")
    )

    if norm_filter == "cpass_approved":
        q = q.in_("candidate_id", list(approved_in_state))
    elif norm_filter == "cpass_rejected":
        q = q.in_("candidate_id", list(rejected_in_state))
    elif norm_filter == "cpass_uploaded":
        q = q.in_("candidate_id", list(uploaded_in_state))
    elif norm_filter == "pending_remaining":
        if uploaded_in_state:
            q = q.not_.in_("candidate_id", list(uploaded_in_state))

    # Apply search filter if provided
    if search and search.strip():
        term = search.strip()
        if term.isdigit():
            q = q.or_(f"candidate_id.eq.{term},mobile_number.ilike.%{term}%")
        else:
            q = q.or_(f"candidate_first_name.ilike.%{term}%,candidate_last_name.ilike.%{term}%,batch_code.ilike.%{term}%,tc_name.ilike.%{term}%")

    # Order and paginate
    offset = (actual_page - 1) * actual_page_size
    q = q.order("candidate_id", desc=False).range(offset, offset + actual_page_size - 1)

    res = q.execute()
    total_count = res.count or 0
    rows = res.data or []

    candidates_out: list[dict[str, Any]] = []
    for r in rows:
        cid = r["candidate_id"]
        audit = audit_map.get(cid)
        has_docs = cid in doc_cids
        is_uploaded = cid in uploaded_in_state

        raw_status = (audit and audit.get("cpass_status") or "").upper()
        raw_audit_status = (audit and audit.get("audit_status") or "").upper()
        if raw_status in APPROVED_STATUSES or raw_audit_status in {"APPROVED", "L2_APPROVED"}:
            normalized_cpass = "APPROVED"
        elif raw_status in REJECTED_STATUSES or raw_audit_status in REJECTED_STATUSES:
            normalized_cpass = "REJECTED"
        elif is_uploaded:
            normalized_cpass = "UPLOADED"
        else:
            normalized_cpass = "PENDING"

        audit_status = (audit and audit.get("audit_status")) or ("DRAFT" if is_uploaded else "NOT_STARTED")

        candidates_out.append({
            "candidate_id": cid,
            "first_name": r.get("candidate_first_name"),
            "last_name": r.get("candidate_last_name"),
            "name": f"{r.get('candidate_first_name') or ''} {r.get('candidate_last_name') or ''}".strip() or f"Candidate {cid}",
            "father_name": r.get("candidate_father_name") or "—",
            "gender": r.get("gender") or "—",
            "mobile": r.get("mobile_number") or "—",
            "batch_code": r.get("batch_code") or "—",
            "kb_batch_id": r.get("kb_batch_id"),
            "tc_id": r.get("tc_id"),
            "tc_name": r.get("tc_name") or "—",
            "sanction_order_number": r.get("sanction_order_number") or "—",
            "state_name": r.get("state_name") or r.get("tc_state_name") or target_state,
            "appointed": bool(r.get("appointed")),
            "employer_name": r.get("employer_name") or "—",
            "is_uploaded": is_uploaded,
            "has_documents": has_docs,
            "cpass_status": normalized_cpass,
            "audit_status": audit_status,
        })

    total_pages = math.ceil(total_count / actual_page_size) if total_count > 0 else 0

    return {
        "state": target_state,
        "filter": norm_filter,
        "filter_type": norm_filter,
        "total_count": total_count,
        "page": actual_page,
        "page_size": actual_page_size,
        "total_pages": total_pages,
        "candidates": candidates_out,
    }


@router.post("/candidates/{candidate_id}/payslip-availability")
def set_payslip_availability(
    candidate_id: int,
    payload: PayslipAvailabilityRequest,
    user: CurrentUser = Depends(require_roles("L1_COORDINATOR")),
):
    """Persist candidate payslip availability ('Browse'/Yes vs 'Not Available'/No).

    - Browse: Indicates payslip file will be or has been attached.
    - Not Available: Indicates payslip is unavailable for this candidate.
    - Preserves state-based authorization and prevents duplicate/conflicting states.
    - Does not fabricate candidate completion if document is unavailable.
    """
    # 1. State Scoping & Candidate Check
    res_cand = (
        supabase.table("ddugky_candidates")
        .select("candidate_id,state_name,tc_state_name,tc_id")
        .eq("candidate_id", candidate_id)
        .limit(1)
        .execute()
    )
    if not res_cand.data:
        raise HTTPException(404, f"Candidate {candidate_id} not found.")
    cand = res_cand.data[0]
    check_candidate_access(user, cand)

    norm_avail = payload.available.strip().capitalize()
    if norm_avail not in ("Yes", "No", "Pending"):
        raise HTTPException(400, "Availability must be 'Yes', 'No', or 'Pending'.")

    # Resolve slot key from slot_key or month_number
    if payload.slot_key and payload.slot_key.strip():
        slot_key = payload.slot_key.strip().lower()
    elif payload.month_number is not None:
        slot_key = f"salary_slip_{payload.month_number}"
    else:
        raise HTTPException(400, "Either slot_key or month_number must be provided.")

    # 2. Prevent conflicting document states:
    # If marking as "Not Available" (No), verify there is no conflicting verified uploaded payslip file for this month
    if norm_avail == "No" and payload.month and payload.year:
        existing_doc = (
            supabase.table("candidate_documents")
            .select("id,file_name")
            .eq("candidate_id", candidate_id)
            .eq("document_type", "SALARY_SLIP")
            .eq("reporting_month", payload.month)
            .eq("reporting_year", payload.year)
            .neq("upload_status", "FAILED")
            .limit(1)
            .execute()
            .data
        )
        if existing_doc:
            raise HTTPException(
                400,
                f"Conflicting document state: A verified payslip '{existing_doc[0]['file_name']}' is already uploaded for {payload.month}/{payload.year}. Delete or replace it before marking as Not Available.",
            )

    # 3. Fetch existing placement audit or create draft
    audit_res = (
        supabase.table("placement_audits")
        .select("*")
        .eq("candidate_id", candidate_id)
        .limit(1)
        .execute()
    )
    audit = audit_res.data[0] if audit_res.data else None

    doc_audit = (audit and audit.get("document_audit")) or {}
    prev_entry = doc_audit.get(slot_key) or {}

    doc_audit[slot_key] = {
        "available": norm_avail,
        "compliance": "Compliant" if norm_avail == "Yes" else "Non-Compliant" if norm_avail == "No" else "Under Verification",
        "remarks": payload.remarks if payload.remarks is not None else (prev_entry.get("remarks") or ("Payslip not available" if norm_avail == "No" else "")),
        "month": payload.month,
        "year": payload.year,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": user.id,
    }

    now_iso = datetime.now(timezone.utc).isoformat()

    if audit:
        # If any document is marked No or Pending, cpass_status cannot be VERIFIED or L2_APPROVED
        new_cpass = audit.get("cpass_status") or "PENDING"
        if norm_avail != "Yes" and new_cpass in ("VERIFIED", "L2_APPROVED"):
            new_cpass = "PENDING"

        supabase.table("placement_audits").update({
            "document_audit": doc_audit,
            "cpass_status": new_cpass,
            "updated_at": now_iso,
        }).eq("id", audit["id"]).execute()
    else:
        supabase.table("placement_audits").insert({
            "candidate_id": candidate_id,
            "document_audit": doc_audit,
            "audit_status": "DRAFT",
            "cpass_status": "PENDING",
            "created_by": user.id,
            "remarks": "Draft initialized via payslip availability update",
        }).execute()

    return {
        "status": "success",
        "candidate_id": candidate_id,
        "slot_key": slot_key,
        "available": norm_avail,
        "remarks": payload.remarks,
        "updated_at": now_iso,
    }
