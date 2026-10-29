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
from ..db import retry_read_query, supabase
from .audits import extract_review_stages

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Standardized status variants recognized across CPASS placement audit workflow
APPROVED_STATUSES = {"APPROVED", "L2_APPROVED", "CPASS_APPROVED", "VERIFIED"}
REJECTED_STATUSES = {"REJECTED", "L2_REJECTED", "CPASS_REJECTED"}


def is_candidate_rejected(audit: dict | None) -> bool:
    """Return True if candidate's current workflow state indicates rejection or return by any review level (CH, COPS, BL)."""
    if not audit:
        return False
    st = (audit.get("cpass_status") or "").upper()
    ast = (audit.get("audit_status") or "").upper()

    if st in REJECTED_STATUSES or ast in REJECTED_STATUSES:
        return True
    if st == "RETURNED_TO_L1" or ast == "RETURNED_TO_L1":
        return True
    if st in {"L3_REJECTED", "L4_REJECTED"} or ast in {"L3_REJECTED", "L4_REJECTED"}:
        return True

    stages = extract_review_stages(audit)
    ch_st = (stages.get("ch_status") or "").lower()
    cops_st = (stages.get("cops_status") or "").lower()
    bl_st = (stages.get("bl_status") or "").lower()

    if ch_st in ("rejected", "returned to l1", "returned"):
        return True
    if cops_st == "rejected":
        return True
    if bl_st == "rejected":
        return True

    return False


def is_candidate_approved(audit: dict | None) -> bool:
    """Return True if candidate is approved under CPASS and not currently rejected/returned."""
    if not audit or is_candidate_rejected(audit):
        return False
    st = (audit.get("cpass_status") or "").upper()
    ast = (audit.get("audit_status") or "").upper()
    stages = extract_review_stages(audit)
    return (
        st in APPROVED_STATUSES
        or ast in {"APPROVED", "L2_APPROVED"}
        or stages.get("bl_status") == "Approved"
    )


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

def _fetch_all_pages(query_factory, page_size: int = 1000):
    """Fetch every row from a Supabase query in bounded pages.

    query_factory must return a fresh query builder each time, so filters and
    selected columns remain identical while range offsets advance.
    """
    rows = []
    offset = 0
    while True:
        response = query_factory().range(offset, offset + page_size - 1).execute()
        page = response.data or []
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return rows


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
            "cpass_uploaded": 0,
            "cpass_approved": 0,
            "cpass_rejected": 0,
            "in_progress": 0,
            "cpass_in_progress": 0,
            "pending_remaining": 0,
            "l2_received": 0,
            "received": 0,
            "l2_recommended": 0,
            "recommended": 0,
            "l2_rejected": 0,
            "ch_rejected": 0,
            "l2_pending": 0,
        }

    # 1. Total Candidates in state (Authoritative source of truth: tc_state_name)
    total_res = retry_read_query(
        lambda: supabase.table("ddugky_candidates")
        .select("candidate_id", count="exact")
        .eq("tc_state_name", target_state)
        .limit(1)
        .execute()
    )
    total_count = total_res.count or 0

    # 2. Load only candidate IDs belonging to the authorized state, then scope
    # document/audit reads to those IDs. Avoid scanning every state's records.
    state_candidate_rows = retry_read_query(
        lambda: _fetch_all_pages(
            lambda: supabase.table("ddugky_candidates")
            .select("candidate_id")
            .eq("tc_state_name", target_state)
        )
    )
    state_candidate_ids = [
        row["candidate_id"] for row in state_candidate_rows
        if row.get("candidate_id") is not None
    ]

    doc_cids: set[int] = set()
    audit_map = {}
    for start in range(0, len(state_candidate_ids), 500):
        id_chunk = state_candidate_ids[start:start + 500]
        doc_rows = retry_read_query(
            lambda id_chunk=id_chunk: _fetch_all_pages(
                lambda: supabase.table("candidate_documents")
                .select("candidate_id")
                .in_("candidate_id", id_chunk)
                .neq("upload_status", "FAILED")
            )
        )
        doc_cids.update(
            row["candidate_id"] for row in doc_rows if row.get("candidate_id") is not None
        )

        aud_rows = retry_read_query(
            lambda id_chunk=id_chunk: _fetch_all_pages(
                lambda: supabase.table("placement_audits")
                .select("candidate_id,cpass_status,audit_status,signoff_details")
                .in_("candidate_id", id_chunk)
            )
        )
        audit_map.update(
            {row["candidate_id"]: row for row in aud_rows if row.get("candidate_id") is not None}
        )

    all_uploaded_cids = doc_cids | set(audit_map.keys())

    uploaded_in_state: set[int] = set()
    if all_uploaded_cids:
        # Every candidate ID came from the state-scoped candidate query above.
        uploaded_in_state = {
            cid for cid in all_uploaded_cids if cid in set(state_candidate_ids)
        }
    uploaded_count = len(uploaded_in_state)

    # 3. Confirmed Pending / Remaining business rule:
    # Pending / Remaining = Total Candidates - CPASS Uploaded Candidates
    pending_count = max(0, total_count - uploaded_count)

    # 4. CPASS Approved Candidates in state
    approved_cids = {cid for cid in uploaded_in_state if is_candidate_approved(audit_map.get(cid))}
    approved_count = len(approved_cids)

    # 5. CPASS Rejected Candidates in state (inclusive of CH, COPS, and BL rejection/return)
    rejected_cids = {cid for cid in uploaded_in_state if is_candidate_rejected(audit_map.get(cid))}
    rejected_count = len(rejected_cids)

    # 6. In Progress Candidates in state:
    # Verification process started (uploaded) but neither approved nor rejected yet
    in_progress_count = max(0, uploaded_count - approved_count - rejected_count)

    # 7. L2 CH Multi-Level Review Metrics:
    # Received: unique candidates in assigned state submitted by L1 and available for CH review
    l2_received_cids = {
        cid for cid in uploaded_in_state
        if audit_map.get(cid)
        and (audit_map[cid].get("audit_status") or "").upper() in {
            "SUBMITTED", "APPROVED", "L2_APPROVED", "VERIFIED", "REJECTED", "RETURNED_TO_L1"
        }
    }

    l2_recommended_cids: set[int] = set()
    l2_rejected_cids: set[int] = set()

    for cid in l2_received_cids:
        audit = audit_map.get(cid)
        stages = extract_review_stages(audit)
        ch_st = stages["ch_status"]
        if ch_st == "Recommended":
            l2_recommended_cids.add(cid)
        elif ch_st in ("Rejected", "Returned to L1", "Returned") or (audit and (audit.get("audit_status") or "").upper() == "RETURNED_TO_L1"):
            l2_rejected_cids.add(cid)

    # Formula: Pending = max(0, Received - Recommended - Rejected)
    l2_pending_count = max(0, len(l2_received_cids) - len(l2_recommended_cids) - len(l2_rejected_cids))

    return {
        "state": target_state,
        "total": total_count,
        "cpass_uploaded": uploaded_count,
        "cpass_approved": approved_count,
        "cpass_rejected": rejected_count,
        "in_progress": in_progress_count,
        "cpass_in_progress": in_progress_count,
        "pending_remaining": pending_count,
        # L2 Center Head summary metrics
        "l2_received": len(l2_received_cids),
        "received": len(l2_received_cids),
        "l2_recommended": len(l2_recommended_cids),
        "recommended": len(l2_recommended_cids),
        "l2_rejected": len(l2_rejected_cids),
        "ch_rejected": len(l2_rejected_cids),
        "l2_pending": l2_pending_count,
    }


@router.get("/candidates")
def get_dashboard_candidates(
    filter: str | None = Query(None, description="Category filter (total, cpass_approved, cpass_rejected, cpass_uploaded, pending_remaining, received, recommended, rejected, pending)"),
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
    - received / l2_received: Candidates submitted by L1 and available for CH review.
    - recommended / l2_recommended: Candidates recommended by CH.
    - rejected / l2_rejected / ch_rejected: Candidates rejected or returned by CH.
    - pending / l2_pending: Received candidates awaiting CH review.
    """
    raw_filter = filter or filter_type or "total"
    norm_filter = raw_filter.strip().lower()
    valid_filters = {
        "total", "cpass_approved", "cpass_rejected", "cpass_uploaded",
        "in_progress", "cpass_in_progress", "pending_remaining",
        "received", "l2_received",
        "recommended", "l2_recommended",
        "rejected", "l2_rejected", "ch_rejected",
        "pending", "l2_pending",
    }
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
    doc_rows = retry_read_query(
        lambda: _fetch_all_pages(
            lambda: supabase.table("candidate_documents")
            .select("candidate_id")
            .neq("upload_status", "FAILED")
        )
    )
    doc_cids = {d["candidate_id"] for d in doc_rows if d.get("candidate_id")}

    aud_rows = retry_read_query(
        lambda: _fetch_all_pages(
            lambda: supabase.table("placement_audits")
            .select("candidate_id,cpass_status,audit_status,signoff_details")
        )
    )
    audit_map = {a["candidate_id"]: a for a in aud_rows if a.get("candidate_id")}
    all_uploaded_cids = doc_cids | set(audit_map.keys())

    uploaded_in_state: set[int] = set()
    if all_uploaded_cids:
        # Bound each IN clause and paginate each chunk so large candidate sets
        # do not create oversized requests or silently stop at the API row limit.
        candidate_ids = list(all_uploaded_cids)
        for start in range(0, len(candidate_ids), 500):
            id_chunk = candidate_ids[start:start + 500]
            cand_check_rows = retry_read_query(
                lambda id_chunk=id_chunk: _fetch_all_pages(
                    lambda: supabase.table("ddugky_candidates")
                    .select("candidate_id,tc_state_name")
                    .in_("candidate_id", id_chunk)
                    .eq("tc_state_name", target_state)
                )
            )
            for r in cand_check_rows:
                if get_candidate_state(r) == target_state:
                    uploaded_in_state.add(r["candidate_id"])

    # Compute candidate ID sets for specific filters
    approved_in_state = {cid for cid in uploaded_in_state if is_candidate_approved(audit_map.get(cid))}
    rejected_in_state = {cid for cid in uploaded_in_state if is_candidate_rejected(audit_map.get(cid))}
    in_progress_in_state = uploaded_in_state - approved_in_state - rejected_in_state

    # L2 Multi-Level Review candidate ID sets
    l2_received_in_state = {
        cid for cid in uploaded_in_state
        if audit_map.get(cid)
        and (audit_map[cid].get("audit_status") or "").upper() in {
            "SUBMITTED", "APPROVED", "L2_APPROVED", "VERIFIED", "REJECTED", "RETURNED_TO_L1"
        }
    }

    l2_recommended_in_state: set[int] = set()
    l2_rejected_in_state: set[int] = set()
    l2_pending_in_state: set[int] = set()

    for cid in l2_received_in_state:
        audit = audit_map.get(cid)
        stages = extract_review_stages(audit)
        ch_st = stages["ch_status"]
        if ch_st == "Recommended":
            l2_recommended_in_state.add(cid)
        elif ch_st in ("Rejected", "Returned to L1", "Returned") or (audit and (audit.get("audit_status") or "").upper() == "RETURNED_TO_L1"):
            l2_rejected_in_state.add(cid)
        else:
            l2_pending_in_state.add(cid)

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

    if norm_filter in {"in_progress", "cpass_in_progress"} and not in_progress_in_state:
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

    if norm_filter in {"received", "l2_received"} and not l2_received_in_state:
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

    if norm_filter in {"recommended", "l2_recommended"} and not l2_recommended_in_state:
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

    if norm_filter in {"rejected", "l2_rejected", "ch_rejected"} and not l2_rejected_in_state:
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

    if norm_filter in {"pending", "l2_pending"} and not l2_pending_in_state:
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
        .eq("tc_state_name", target_state)
    )

    if norm_filter == "cpass_approved":
        q = q.in_("candidate_id", list(approved_in_state))
    elif norm_filter == "cpass_rejected":
        q = q.in_("candidate_id", list(rejected_in_state))
    elif norm_filter in {"in_progress", "cpass_in_progress"}:
        q = q.in_("candidate_id", list(in_progress_in_state))
    elif norm_filter == "cpass_uploaded":
        q = q.in_("candidate_id", list(uploaded_in_state))
    elif norm_filter == "pending_remaining":
        if uploaded_in_state:
            q = q.not_.in_("candidate_id", list(uploaded_in_state))
    elif norm_filter in {"received", "l2_received"}:
        q = q.in_("candidate_id", list(l2_received_in_state))
    elif norm_filter in {"recommended", "l2_recommended"}:
        q = q.in_("candidate_id", list(l2_recommended_in_state))
    elif norm_filter in {"rejected", "l2_rejected", "ch_rejected"}:
        q = q.in_("candidate_id", list(l2_rejected_in_state))
    elif norm_filter in {"pending", "l2_pending"}:
        q = q.in_("candidate_id", list(l2_pending_in_state))

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

    res = retry_read_query(lambda: q.execute())
    raw_count = getattr(res, "count", None)
    total_count = raw_count if isinstance(raw_count, int) else (len(res.data or []) if getattr(res, "data", None) else 0)
    rows = res.data or []

    candidates_out: list[dict[str, Any]] = []
    for r in rows:
        cid = r["candidate_id"]
        audit = audit_map.get(cid)
        has_docs = cid in doc_cids
        is_uploaded = cid in uploaded_in_state

        raw_status = (audit and audit.get("cpass_status") or "").upper()
        raw_audit_status = (audit and audit.get("audit_status") or "").upper()
        stages = extract_review_stages(audit)

        if raw_status == "RETURNED_TO_L1" or raw_audit_status == "RETURNED_TO_L1" or stages["ch_status"] == "Returned to L1":
            normalized_cpass = "RETURNED_TO_L1"
        elif is_candidate_rejected(audit):
            normalized_cpass = "REJECTED"
        elif is_candidate_approved(audit):
            normalized_cpass = "APPROVED"
        elif is_uploaded:
            normalized_cpass = "IN_PROGRESS"
        else:
            normalized_cpass = "PENDING"

        audit_status = (audit and audit.get("audit_status")) or ("DRAFT" if is_uploaded else "NOT_STARTED")
        signoff = (audit and audit.get("signoff_details")) or {}
        return_to_l1 = signoff.get("return_to_l1") or {}
        ret_reason = return_to_l1.get("return_reason") or return_to_l1.get("reason")
        rej_reason = signoff.get("rejection_reason") or ret_reason
        rej_stage = signoff.get("rejected_stage") or ("ch" if normalized_cpass == "RETURNED_TO_L1" else None)

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
            "ch_status": stages["ch_status"],
            "cops_status": stages["cops_status"],
            "bl_status": stages["bl_status"],
            "review_stages": stages,
            "return_reason": ret_reason,
            "rejection_reason": rej_reason,
            "rejected_stage": rej_stage,
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
