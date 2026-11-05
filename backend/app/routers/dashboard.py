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
APPROVED_STATUSES = {"APPROVED", "L2_APPROVED", "CPASS_APPROVED", "VERIFIED", "FINAL_APPROVED"}
REJECTED_STATUSES = {"REJECTED", "L2_REJECTED", "CPASS_REJECTED", "L3_REJECTED", "L4_REJECTED", "L5_REJECTED"}


def is_candidate_rejected(audit: dict | None) -> bool:
    """Return True if candidate's current workflow state indicates rejection or return by any review level (CH, COPS, BL, CEO)."""
    if not audit:
        return False
    st = (audit.get("cpass_status") or "").upper()
    ast = (audit.get("audit_status") or "").upper()

    if st in REJECTED_STATUSES or ast in REJECTED_STATUSES:
        return True
    if st in ("RETURNED_TO_L1", "RETURNED_TO_L2", "RETURNED_TO_L3", "RETURNED_TO_L4") or ast == "RETURNED_TO_L1":
        return True
    if st in {"L3_REJECTED", "L4_REJECTED", "L5_REJECTED"} or ast in {"L3_REJECTED", "L4_REJECTED", "L5_REJECTED"}:
        return True

    stages = extract_review_stages(audit)
    ch_st = (stages.get("ch_status") or "").lower()
    cops_st = (stages.get("cops_status") or "").lower()
    bl_st = (stages.get("bl_status") or "").lower()
    ceo_st = (stages.get("ceo_status") or "").lower()

    if ch_st in ("rejected", "returned to l1", "returned"):
        return True
    if cops_st == "rejected":
        return True
    if bl_st == "rejected":
        return True
    if ceo_st == "rejected":
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
        or stages.get("ceo_status") == "Approved"
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

    For L1_COORDINATOR, L2_MANAGER, and L4_LEADER:
    - Strictly bound to user permitted state(s).
    - If state_param is provided:
        - If "ALL", returns None (will be filtered by user's permitted states in DB queries).
        - Otherwise must resolve to one of permitted states, else 403.
    - If state_param is not provided:
        - If user has exactly one permitted state, returns that state.
        - If user has multiple permitted states, returns None (will query across all permitted states).

    For Global Roles (ADMIN, L3_COPS, L3_LEADER, L4_CEO, L5_CEO):
    - Uses state_param if given (unless "ALL", which returns None for national view).
    - Otherwise defaults to user.assigned_state or None.
    """
    permitted_st = allowed_states(user)

    if permitted_st is not None:
        if not permitted_st:
            return None  # Fail closed: unassigned user sees no state
        if state_param:
            clean = state_param.strip()
            if clean.upper() in ("ALL", "ALL STATES", "ALL AUTHORIZED STATES"):
                return None  # Will be scoped to permitted_st in queries
            resolved_query = resolve_state(clean) or clean
            if resolved_query not in permitted_st and clean not in permitted_st:
                raise HTTPException(
                    403,
                    f"Access to state '{state_param}' is forbidden. Your authorized state(s): {', '.join(permitted_st)}."
                )
            return resolved_query
        # If no state_param given
        if len(permitted_st) == 1:
            return permitted_st[0]
        return None

    # Global roles (national access)
    if state_param:
        clean = state_param.strip()
        if clean.upper() in ("ALL", "ALL STATES"):
            return None
        return resolve_state(clean) or clean
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
    permitted_st = allowed_states(user)
    target_state = _get_target_state(user, state)
    if not target_state and not user.sees_all_states and not permitted_st:
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
            "l3_received": 0,
            "cops_received": 0,
            "l3_verified": 0,
            "cops_verified": 0,
            "l3_rejected": 0,
            "cops_rejected": 0,
            "l3_returned": 0,
            "cops_returned": 0,
            "l3_rejected_returned": 0,
            "cops_rejected_returned": 0,
            "l3_pending": 0,
            "cops_pending": 0,
            "l4_received": 0,
            "bl_received": 0,
            "l4_approved": 0,
            "bl_approved": 0,
            "l4_rejected": 0,
            "bl_rejected": 0,
            "l4_returned": 0,
            "bl_returned": 0,
            "l4_rejected_returned": 0,
            "bl_rejected_returned": 0,
            "l4_pending": 0,
            "bl_pending": 0,
            "l5_received": 0,
            "ceo_received": 0,
            "l5_approved": 0,
            "ceo_approved": 0,
            "l5_rejected": 0,
            "ceo_rejected": 0,
            "l5_returned": 0,
            "ceo_returned": 0,
            "l5_rejected_returned": 0,
            "ceo_rejected_returned": 0,
            "l5_pending": 0,
            "ceo_pending": 0,
        }

    # 1. Total Candidates in state or national aggregate (Authoritative source of truth: state_name)
    if target_state:
        total_res = retry_read_query(
            lambda: supabase.table("ddugky_candidates")
            .select("candidate_id", count="exact")
            .eq("state_name", target_state)
            .limit(1)
            .execute()
        )
    elif permitted_st is not None:
        total_res = retry_read_query(
            lambda: supabase.table("ddugky_candidates")
            .select("candidate_id", count="exact")
            .in_("state_name", permitted_st)
            .limit(1)
            .execute()
        )
    else:
        total_res = retry_read_query(
            lambda: supabase.table("ddugky_candidates")
            .select("candidate_id", count="exact")
            .limit(1)
            .execute()
        )
    total_count = total_res.count or 0

    # 2. Uploaded Candidates (candidates in target_state having candidate_documents or placement_audits)
    docs_res = retry_read_query(
        lambda: supabase.table("candidate_documents")
        .select("candidate_id")
        .neq("upload_status", "FAILED")
        .execute()
    )
    doc_cids = {d["candidate_id"] for d in (docs_res.data or []) if d.get("candidate_id")}

    aud_res = retry_read_query(
        lambda: supabase.table("placement_audits")
        .select("candidate_id,cpass_status,audit_status,signoff_details")
        .execute()
    )
    aud_rows = aud_res.data or []
    audit_map = {a["candidate_id"]: a for a in aud_rows if a.get("candidate_id")}
    all_uploaded_cids = doc_cids | set(audit_map.keys())

    uploaded_in_state: set[int] = set()
    if all_uploaded_cids:
        if target_state:
            cand_check = retry_read_query(
                lambda: supabase.table("ddugky_candidates")
                .select("candidate_id,tc_state_name,state_name")
                .in_("candidate_id", list(all_uploaded_cids))
                .eq("state_name", target_state)
                .execute()
            )
        elif permitted_st is not None:
            cand_check = retry_read_query(
                lambda: supabase.table("ddugky_candidates")
                .select("candidate_id,tc_state_name,state_name")
                .in_("candidate_id", list(all_uploaded_cids))
                .in_("state_name", permitted_st)
                .execute()
            )
        else:
            cand_check = retry_read_query(
                lambda: supabase.table("ddugky_candidates")
                .select("candidate_id,tc_state_name,state_name")
                .in_("candidate_id", list(all_uploaded_cids))
                .execute()
            )
        for r in (cand_check.data or []):
            st = get_candidate_state(r)
            if target_state:
                if st == target_state:
                    uploaded_in_state.add(r["candidate_id"])
            elif permitted_st is not None:
                if st in permitted_st:
                    uploaded_in_state.add(r["candidate_id"])
            else:
                uploaded_in_state.add(r["candidate_id"])
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

    # 8. L3 COPS Multi-Level Review Metrics:
    l3_received_cids: set[int] = set()
    l3_verified_cids: set[int] = set()
    l3_rejected_cids: set[int] = set()
    l3_returned_cids: set[int] = set()
    l3_pending_cids: set[int] = set()

    for cid in uploaded_in_state:
        audit = audit_map.get(cid)
        if not audit:
            continue
        stages = extract_review_stages(audit)
        ch_st = stages["ch_status"]
        cops_st = stages["cops_status"]
        cpass_st = (audit.get("cpass_status") or "").upper()
        audit_st = (audit.get("audit_status") or "").upper()
        signoff = audit.get("signoff_details") or {}
        ret_to_l1 = signoff.get("return_to_l1") or {}
        ret_to_l2 = signoff.get("return_to_l2") or {}

        is_received_by_cops = (
            ch_st == "Recommended"
            or cops_st in ("Verified", "Rejected", "Returned to L1")
            or cpass_st in ("VERIFIED", "APPROVED", "L3_REJECTED", "L4_REJECTED")
            or signoff.get("rejected_stage") in ("cops", "bl")
            or (ret_to_l1.get("stage") == "COPS" and audit_st == "RETURNED_TO_L1")
            or (ret_to_l2.get("stage") == "COPS" and ch_st == "Pending" and audit_st == "SUBMITTED")
        )

        if is_received_by_cops:
            l3_received_cids.add(cid)
            if cops_st == "Verified" or cpass_st in ("VERIFIED", "APPROVED") or stages.get("bl_status") == "Approved":
                if not is_candidate_rejected(audit):
                    l3_verified_cids.add(cid)
                else:
                    l3_rejected_cids.add(cid)
            elif cops_st == "Rejected" or signoff.get("rejected_stage") == "cops" or cpass_st == "L3_REJECTED":
                l3_rejected_cids.add(cid)
            elif (
                cops_st in ("Returned to L1", "Returned")
                or (ret_to_l1.get("stage") == "COPS" and (audit_st == "RETURNED_TO_L1" or cpass_st == "RETURNED_TO_L1"))
                or (ret_to_l2.get("stage") == "COPS" and ch_st == "Pending" and audit_st == "SUBMITTED")
            ):
                l3_returned_cids.add(cid)
            elif cops_st == "Pending" and ch_st == "Recommended" and not is_candidate_rejected(audit):
                l3_pending_cids.add(cid)
            else:
                if is_candidate_rejected(audit):
                    l3_rejected_cids.add(cid)
                else:
                    l3_pending_cids.add(cid)

    l3_pending_count = len(l3_pending_cids)

    # 9. L4 Business Leader (BL) Multi-Level Review Metrics:
    l4_received_cids: set[int] = set()
    l4_approved_cids: set[int] = set()
    l4_rejected_cids: set[int] = set()
    l4_returned_cids: set[int] = set()
    l4_pending_cids: set[int] = set()

    # 10. L5 CEO Multi-Level Review Metrics:
    l5_received_cids: set[int] = set()
    l5_approved_cids: set[int] = set()
    l5_rejected_cids: set[int] = set()
    l5_returned_cids: set[int] = set()
    l5_pending_cids: set[int] = set()

    for cid in uploaded_in_state:
        audit = audit_map.get(cid)
        if not audit:
            continue
        stages = extract_review_stages(audit)
        cops_st = stages["cops_status"]
        bl_st = stages["bl_status"]
        ceo_st = stages["ceo_status"]
        cpass_st = (audit.get("cpass_status") or "").upper()
        audit_st = (audit.get("audit_status") or "").upper()
        signoff = audit.get("signoff_details") or {}
        active_ret = signoff.get("active_return") or {}

        # BL Reception check
        is_received_by_bl = (
            cops_st == "Verified"
            or bl_st in ("Approved", "Rejected", "Returned")
            or cpass_st in ("BL_APPROVED", "APPROVED", "L4_REJECTED", "L5_REJECTED", "RETURNED_TO_L4")
            or signoff.get("rejected_stage") in ("bl", "ceo")
            or active_ret.get("stage") in ("BL", "CEO")
        )

        if is_received_by_bl:
            l4_received_cids.add(cid)
            if bl_st == "Rejected" or signoff.get("rejected_stage") == "bl" or cpass_st == "L4_REJECTED":
                l4_rejected_cids.add(cid)
            elif active_ret.get("stage") == "BL":
                l4_returned_cids.add(cid)
            elif bl_st == "Approved" or cpass_st in ("BL_APPROVED", "APPROVED") or ceo_st == "Approved":
                if not is_candidate_rejected(audit):
                    l4_approved_cids.add(cid)
                else:
                    l4_rejected_cids.add(cid)
            elif bl_st == "Pending" and cops_st == "Verified" and not is_candidate_rejected(audit) and not active_ret:
                l4_pending_cids.add(cid)
            else:
                if is_candidate_rejected(audit):
                    l4_rejected_cids.add(cid)
                else:
                    l4_pending_cids.add(cid)

        # CEO Reception check
        is_received_by_ceo = (
            bl_st == "Approved"
            or cpass_st in ("BL_APPROVED", "APPROVED", "L5_REJECTED")
            or ceo_st in ("Approved", "Rejected", "Returned")
            or signoff.get("rejected_stage") == "ceo"
            or active_ret.get("stage") == "CEO"
        )

        if is_received_by_ceo:
            l5_received_cids.add(cid)
            if ceo_st == "Rejected" or signoff.get("rejected_stage") == "ceo" or cpass_st == "L5_REJECTED":
                l5_rejected_cids.add(cid)
            elif active_ret.get("stage") == "CEO":
                l5_returned_cids.add(cid)
            elif ceo_st == "Approved" or (cpass_st == "APPROVED" and audit_st == "APPROVED"):
                if not is_candidate_rejected(audit):
                    l5_approved_cids.add(cid)
                else:
                    l5_rejected_cids.add(cid)
            elif ceo_st == "Pending" and bl_st == "Approved" and not is_candidate_rejected(audit) and not active_ret:
                l5_pending_cids.add(cid)
            else:
                if is_candidate_rejected(audit):
                    l5_rejected_cids.add(cid)
                else:
                    l5_pending_cids.add(cid)

    l4_pending_count = len(l4_pending_cids)
    l5_pending_count = len(l5_pending_cids)

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
        # L3 COPS summary metrics
        "l3_received": len(l3_received_cids),
        "cops_received": len(l3_received_cids),
        "l3_verified": len(l3_verified_cids),
        "cops_verified": len(l3_verified_cids),
        "l3_rejected": len(l3_rejected_cids),
        "cops_rejected": len(l3_rejected_cids),
        "l3_returned": len(l3_returned_cids),
        "cops_returned": len(l3_returned_cids),
        "l3_rejected_returned": len(l3_rejected_cids | l3_returned_cids),
        "cops_rejected_returned": len(l3_rejected_cids | l3_returned_cids),
        "l3_pending": l3_pending_count,
        "cops_pending": l3_pending_count,
        # L4 Business Leader summary metrics
        "l4_received": len(l4_received_cids),
        "bl_received": len(l4_received_cids),
        "l4_approved": len(l4_approved_cids),
        "bl_approved": len(l4_approved_cids),
        "l4_rejected": len(l4_rejected_cids),
        "bl_rejected": len(l4_rejected_cids),
        "l4_returned": len(l4_returned_cids),
        "bl_returned": len(l4_returned_cids),
        "l4_rejected_returned": len(l4_rejected_cids | l4_returned_cids),
        "bl_rejected_returned": len(l4_rejected_cids | l4_returned_cids),
        "l4_pending": l4_pending_count,
        "bl_pending": l4_pending_count,
        # L5 CEO summary metrics
        "l5_received": len(l5_received_cids),
        "ceo_received": len(l5_received_cids),
        "l5_approved": len(l5_approved_cids),
        "ceo_approved": len(l5_approved_cids),
        "l5_rejected": len(l5_rejected_cids),
        "ceo_rejected": len(l5_rejected_cids),
        "l5_returned": len(l5_returned_cids),
        "ceo_returned": len(l5_returned_cids),
        "l5_rejected_returned": len(l5_rejected_cids | l5_returned_cids),
        "ceo_rejected_returned": len(l5_rejected_cids | l5_returned_cids),
        "l5_pending": l5_pending_count,
        "ceo_pending": l5_pending_count,
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
        # L3 COPS filters
        "l3_received", "cops_received",
        "l3_verified", "cops_verified",
        "l3_rejected", "cops_rejected",
        "l3_returned", "cops_returned",
        "l3_rejected_returned", "cops_rejected_returned",
        "l3_pending", "cops_pending",
        # L4 Business Leader filters
        "l4_received", "bl_received",
        "l4_approved", "bl_approved",
        "l4_rejected", "bl_rejected",
        "l4_returned", "bl_returned",
        "l4_rejected_returned", "bl_rejected_returned",
        "l4_pending", "bl_pending",
        # L5 CEO filters
        "l5_received", "ceo_received",
        "l5_approved", "ceo_approved",
        "l5_rejected", "ceo_rejected",
        "l5_returned", "ceo_returned",
        "l5_rejected_returned", "ceo_rejected_returned",
        "l5_pending", "ceo_pending",
    }
    if norm_filter not in valid_filters:
        raise HTTPException(
            400,
            f"Invalid filter '{raw_filter}'. Allowed: {', '.join(sorted(valid_filters))}",
        )

    actual_page = int(page) if isinstance(page, (int, str)) and str(page).isdigit() and int(page) >= 1 else 1
    actual_page_size = int(page_size) if isinstance(page_size, (int, str)) and str(page_size).isdigit() and int(page_size) >= 1 else 20

    permitted_st = allowed_states(user)
    target_state = _get_target_state(user, state)
    if not target_state and not user.sees_all_states and not permitted_st:
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
    docs_res = retry_read_query(
        lambda: supabase.table("candidate_documents")
        .select("candidate_id")
        .neq("upload_status", "FAILED")
        .execute()
    )
    doc_cids = {d["candidate_id"] for d in (docs_res.data or []) if d.get("candidate_id")}

    aud_res = retry_read_query(
        lambda: supabase.table("placement_audits")
        .select("candidate_id,cpass_status,audit_status,signoff_details")
        .execute()
    )
    aud_rows = aud_res.data or []
    audit_map = {a["candidate_id"]: a for a in aud_rows if a.get("candidate_id")}
    all_uploaded_cids = doc_cids | set(audit_map.keys())

    uploaded_in_state: set[int] = set()
    if all_uploaded_cids:
        if target_state:
            cand_check = retry_read_query(
                lambda: supabase.table("ddugky_candidates")
                .select("candidate_id,tc_state_name,state_name")
                .in_("candidate_id", list(all_uploaded_cids))
                .eq("state_name", target_state)
                .execute()
            )
        elif permitted_st is not None:
            cand_check = retry_read_query(
                lambda: supabase.table("ddugky_candidates")
                .select("candidate_id,tc_state_name,state_name")
                .in_("candidate_id", list(all_uploaded_cids))
                .in_("state_name", permitted_st)
                .execute()
            )
        else:
            cand_check = retry_read_query(
                lambda: supabase.table("ddugky_candidates")
                .select("candidate_id,tc_state_name,state_name")
                .in_("candidate_id", list(all_uploaded_cids))
                .execute()
            )
        for r in (cand_check.data or []):
            st = get_candidate_state(r)
            if target_state:
                if st == target_state:
                    uploaded_in_state.add(r["candidate_id"])
            elif permitted_st is not None:
                if st in permitted_st:
                    uploaded_in_state.add(r["candidate_id"])
            else:
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

    # L3 COPS candidate ID sets
    l3_received_in_state: set[int] = set()
    l3_verified_in_state: set[int] = set()
    l3_rejected_in_state: set[int] = set()
    l3_returned_in_state: set[int] = set()
    l3_pending_in_state: set[int] = set()

    for cid in uploaded_in_state:
        audit = audit_map.get(cid)
        if not audit:
            continue
        stages = extract_review_stages(audit)
        ch_st = stages["ch_status"]
        cops_st = stages["cops_status"]
        cpass_st = (audit.get("cpass_status") or "").upper()
        audit_st = (audit.get("audit_status") or "").upper()
        signoff = audit.get("signoff_details") or {}
        ret_to_l1 = signoff.get("return_to_l1") or {}
        ret_to_l2 = signoff.get("return_to_l2") or {}

        is_received_by_cops = (
            ch_st == "Recommended"
            or cops_st in ("Verified", "Rejected", "Returned to L1")
            or cpass_st in ("VERIFIED", "APPROVED", "L3_REJECTED", "L4_REJECTED")
            or signoff.get("rejected_stage") in ("cops", "bl")
            or (ret_to_l1.get("stage") == "COPS" and audit_st == "RETURNED_TO_L1")
            or (ret_to_l2.get("stage") == "COPS" and ch_st == "Pending" and audit_st == "SUBMITTED")
        )

        if is_received_by_cops:
            l3_received_in_state.add(cid)
            if cops_st == "Verified" or cpass_st in ("VERIFIED", "APPROVED") or stages.get("bl_status") == "Approved":
                if not is_candidate_rejected(audit):
                    l3_verified_in_state.add(cid)
                else:
                    l3_rejected_in_state.add(cid)
            elif cops_st == "Rejected" or signoff.get("rejected_stage") == "cops" or cpass_st == "L3_REJECTED":
                l3_rejected_in_state.add(cid)
            elif (
                cops_st in ("Returned to L1", "Returned")
                or (ret_to_l1.get("stage") == "COPS" and (audit_st == "RETURNED_TO_L1" or cpass_st == "RETURNED_TO_L1"))
                or (ret_to_l2.get("stage") == "COPS" and ch_st == "Pending" and audit_st == "SUBMITTED")
            ):
                l3_returned_in_state.add(cid)
            elif cops_st == "Pending" and ch_st == "Recommended" and not is_candidate_rejected(audit):
                l3_pending_in_state.add(cid)
            else:
                if is_candidate_rejected(audit):
                    l3_rejected_in_state.add(cid)
                else:
                    l3_pending_in_state.add(cid)

    # L4 BL candidate ID sets
    l4_received_in_state: set[int] = set()
    l4_approved_in_state: set[int] = set()
    l4_rejected_in_state: set[int] = set()
    l4_returned_in_state: set[int] = set()
    l4_pending_in_state: set[int] = set()

    # L5 CEO candidate ID sets
    l5_received_in_state: set[int] = set()
    l5_approved_in_state: set[int] = set()
    l5_rejected_in_state: set[int] = set()
    l5_returned_in_state: set[int] = set()
    l5_pending_in_state: set[int] = set()

    for cid in uploaded_in_state:
        audit = audit_map.get(cid)
        if not audit:
            continue
        stages = extract_review_stages(audit)
        cops_st = stages["cops_status"]
        bl_st = stages["bl_status"]
        ceo_st = stages["ceo_status"]
        cpass_st = (audit.get("cpass_status") or "").upper()
        audit_st = (audit.get("audit_status") or "").upper()
        signoff = audit.get("signoff_details") or {}
        active_ret = signoff.get("active_return") or {}

        # BL check
        is_received_by_bl = (
            cops_st == "Verified"
            or bl_st in ("Approved", "Rejected", "Returned")
            or cpass_st in ("BL_APPROVED", "APPROVED", "L4_REJECTED", "L5_REJECTED", "RETURNED_TO_L4")
            or signoff.get("rejected_stage") in ("bl", "ceo")
            or active_ret.get("stage") in ("BL", "CEO")
        )

        if is_received_by_bl:
            l4_received_in_state.add(cid)
            if bl_st == "Rejected" or signoff.get("rejected_stage") == "bl" or cpass_st == "L4_REJECTED":
                l4_rejected_in_state.add(cid)
            elif active_ret.get("stage") == "BL":
                l4_returned_in_state.add(cid)
            elif bl_st == "Approved" or cpass_st in ("BL_APPROVED", "APPROVED") or ceo_st == "Approved":
                if not is_candidate_rejected(audit):
                    l4_approved_in_state.add(cid)
                else:
                    l4_rejected_in_state.add(cid)
            elif bl_st == "Pending" and cops_st == "Verified" and not is_candidate_rejected(audit) and not active_ret:
                l4_pending_in_state.add(cid)
            else:
                if is_candidate_rejected(audit):
                    l4_rejected_in_state.add(cid)
                else:
                    l4_pending_in_state.add(cid)

        # CEO check
        is_received_by_ceo = (
            bl_st == "Approved"
            or cpass_st in ("BL_APPROVED", "APPROVED", "L5_REJECTED")
            or ceo_st in ("Approved", "Rejected", "Returned")
            or signoff.get("rejected_stage") == "ceo"
            or active_ret.get("stage") == "CEO"
        )

        if is_received_by_ceo:
            l5_received_in_state.add(cid)
            if ceo_st == "Rejected" or signoff.get("rejected_stage") == "ceo" or cpass_st == "L5_REJECTED":
                l5_rejected_in_state.add(cid)
            elif active_ret.get("stage") == "CEO":
                l5_returned_in_state.add(cid)
            elif ceo_st == "Approved" or (cpass_st == "APPROVED" and audit_st == "APPROVED"):
                if not is_candidate_rejected(audit):
                    l5_approved_in_state.add(cid)
                else:
                    l5_rejected_in_state.add(cid)
            elif ceo_st == "Pending" and bl_st == "Approved" and not is_candidate_rejected(audit) and not active_ret:
                l5_pending_in_state.add(cid)
            else:
                if is_candidate_rejected(audit):
                    l5_rejected_in_state.add(cid)
                else:
                    l5_pending_in_state.add(cid)

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

    if norm_filter in {"l3_received", "cops_received"} and not l3_received_in_state:
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

    if norm_filter in {"l3_verified", "cops_verified"} and not l3_verified_in_state:
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

    if norm_filter in {"l3_rejected", "cops_rejected"} and not l3_rejected_in_state:
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

    if norm_filter in {"l3_returned", "cops_returned"} and not l3_returned_in_state:
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

    if norm_filter in {"l3_pending", "cops_pending"} and not l3_pending_in_state:
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

    if norm_filter in {"l3_rejected_returned", "cops_rejected_returned"} and not (l3_rejected_in_state | l3_returned_in_state):
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

    # L4 BL short-circuits
    if norm_filter in {"l4_received", "bl_received"} and not l4_received_in_state:
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

    if norm_filter in {"l4_approved", "bl_approved"} and not l4_approved_in_state:
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

    if norm_filter in {"l4_rejected", "bl_rejected"} and not l4_rejected_in_state:
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

    if norm_filter in {"l4_returned", "bl_returned"} and not l4_returned_in_state:
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

    if norm_filter in {"l4_rejected_returned", "bl_rejected_returned"} and not (l4_rejected_in_state | l4_returned_in_state):
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

    if norm_filter in {"l4_pending", "bl_pending"} and not l4_pending_in_state:
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

    # L5 CEO short-circuits
    if norm_filter in {"l5_received", "ceo_received"} and not l5_received_in_state:
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

    if norm_filter in {"l5_approved", "ceo_approved"} and not l5_approved_in_state:
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

    if norm_filter in {"l5_rejected", "ceo_rejected"} and not l5_rejected_in_state:
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

    if norm_filter in {"l5_returned", "ceo_returned"} and not l5_returned_in_state:
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

    if norm_filter in {"l5_rejected_returned", "ceo_rejected_returned"} and not (l5_rejected_in_state | l5_returned_in_state):
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

    if norm_filter in {"l5_pending", "ceo_pending"} and not l5_pending_in_state:
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

    if target_state:
        q = (
            supabase.table("ddugky_candidates")
            .select(columns, count="exact")
            .eq("state_name", target_state)
        )
    elif permitted_st is not None:
        q = (
            supabase.table("ddugky_candidates")
            .select(columns, count="exact")
            .in_("state_name", permitted_st)
        )
    else:
        q = (
            supabase.table("ddugky_candidates")
            .select(columns, count="exact")
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
    elif norm_filter in {"l3_received", "cops_received"}:
        q = q.in_("candidate_id", list(l3_received_in_state))
    elif norm_filter in {"l3_verified", "cops_verified"}:
        q = q.in_("candidate_id", list(l3_verified_in_state))
    elif norm_filter in {"l3_rejected", "cops_rejected"}:
        q = q.in_("candidate_id", list(l3_rejected_in_state))
    elif norm_filter in {"l3_returned", "cops_returned"}:
        q = q.in_("candidate_id", list(l3_returned_in_state))
    elif norm_filter in {"l3_rejected_returned", "cops_rejected_returned"}:
        q = q.in_("candidate_id", list(l3_rejected_in_state | l3_returned_in_state))
    elif norm_filter in {"l3_pending", "cops_pending"}:
        q = q.in_("candidate_id", list(l3_pending_in_state))
    elif norm_filter in {"l4_received", "bl_received"}:
        q = q.in_("candidate_id", list(l4_received_in_state))
    elif norm_filter in {"l4_approved", "bl_approved"}:
        q = q.in_("candidate_id", list(l4_approved_in_state))
    elif norm_filter in {"l4_rejected", "bl_rejected"}:
        q = q.in_("candidate_id", list(l4_rejected_in_state))
    elif norm_filter in {"l4_returned", "bl_returned"}:
        q = q.in_("candidate_id", list(l4_returned_in_state))
    elif norm_filter in {"l4_rejected_returned", "bl_rejected_returned"}:
        q = q.in_("candidate_id", list(l4_rejected_in_state | l4_returned_in_state))
    elif norm_filter in {"l4_pending", "bl_pending"}:
        q = q.in_("candidate_id", list(l4_pending_in_state))
    elif norm_filter in {"l5_received", "ceo_received"}:
        q = q.in_("candidate_id", list(l5_received_in_state))
    elif norm_filter in {"l5_approved", "ceo_approved"}:
        q = q.in_("candidate_id", list(l5_approved_in_state))
    elif norm_filter in {"l5_rejected", "ceo_rejected"}:
        q = q.in_("candidate_id", list(l5_rejected_in_state))
    elif norm_filter in {"l5_returned", "ceo_returned"}:
        q = q.in_("candidate_id", list(l5_returned_in_state))
    elif norm_filter in {"l5_rejected_returned", "ceo_rejected_returned"}:
        q = q.in_("candidate_id", list(l5_rejected_in_state | l5_returned_in_state))
    elif norm_filter in {"l5_pending", "ceo_pending"}:
        q = q.in_("candidate_id", list(l5_pending_in_state))

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

        if raw_status in ("RETURNED_TO_L1", "RETURNED_TO_L2", "RETURNED_TO_L3", "RETURNED_TO_L4") or raw_audit_status == "RETURNED_TO_L1" or stages["ch_status"] == "Returned to L1":
            normalized_cpass = raw_status if raw_status.startswith("RETURNED_TO_") else "RETURNED_TO_L1"
        elif is_candidate_rejected(audit):
            normalized_cpass = "REJECTED"
        elif is_candidate_approved(audit):
            normalized_cpass = "APPROVED"
        elif raw_status == "BL_APPROVED":
            normalized_cpass = "BL_APPROVED"
        elif raw_status == "VERIFIED":
            normalized_cpass = "VERIFIED"
        elif raw_status == "L2_APPROVED":
            normalized_cpass = "L2_APPROVED"
        elif is_uploaded:
            normalized_cpass = "IN_PROGRESS"
        else:
            normalized_cpass = "PENDING"

        audit_status = (audit and audit.get("audit_status")) or ("DRAFT" if is_uploaded else "NOT_STARTED")
        signoff = (audit and audit.get("signoff_details")) or {}
        return_to_l1 = signoff.get("return_to_l1") or {}
        active_return = signoff.get("active_return") or {}
        ret_reason = active_return.get("return_reason") or active_return.get("reason") or return_to_l1.get("return_reason") or return_to_l1.get("reason")
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
            "state_name": resolve_state(r.get("state_name")) or r.get("state_name") or "—",
            "tc_state_name": r.get("tc_state_name") or "—",
            "appointed": bool(r.get("appointed")),
            "employer_name": r.get("employer_name") or "—",
            "is_uploaded": is_uploaded,
            "has_documents": has_docs,
            "cpass_status": normalized_cpass,
            "audit_status": audit_status,
            "ch_status": stages["ch_status"],
            "cops_status": stages["cops_status"],
            "bl_status": stages["bl_status"],
            "ceo_status": stages["ceo_status"],
            "review_stages": stages,
            "active_return": active_return if active_return else None,
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
