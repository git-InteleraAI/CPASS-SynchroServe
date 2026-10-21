"""FastAPI router for duplicate cases review, auditable history, and candidate submission holds.

Enforces role-based permissions and centre-assignment scoping.
Preserves all candidate records intact without merging or deleting.
Distinguishes warnings from holds: warnings inform users, while only explicit holds block submissions.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import CurrentUser, allowed_tc_ids, get_current_user
from ..db import supabase

router = APIRouter(prefix="/duplicates", tags=["duplicates"])

REVIEW_ROLES = ("ADMIN", "L2_MANAGER", "L3_LEADER")
HOLD_ROLES = ("ADMIN", "L2_MANAGER", "L3_LEADER")


class DuplicateStatus(str, Enum):
    PENDING = "PENDING"
    UNDER_REVIEW = "UNDER_REVIEW"
    CONFIRMED_DUPLICATE = "CONFIRMED_DUPLICATE"
    DISTINCT_CANDIDATES = "DISTINCT_CANDIDATES"
    DATA_CORRECTION_REQUIRED = "DATA_CORRECTION_REQUIRED"
    UNRESOLVED = "UNRESOLVED"


CONSEQUENTIAL_STATUSES = {
    DuplicateStatus.CONFIRMED_DUPLICATE,
    DuplicateStatus.DISTINCT_CANDIDATES,
    DuplicateStatus.DATA_CORRECTION_REQUIRED,
    DuplicateStatus.UNRESOLVED,
}


class ReviewDecisionRequest(BaseModel):
    to_status: DuplicateStatus
    decision: str = Field(..., min_length=1, description="Decision summary")
    reason: str = Field(..., description="Mandatory rationale for consequential review decisions")


class PlaceHoldRequest(BaseModel):
    reason: str = Field(..., min_length=3, description="Mandatory reason for placing candidate on submission hold")
    case_id: str | None = None


class ReleaseHoldRequest(BaseModel):
    reason: str = Field(..., min_length=3, description="Mandatory reason for releasing candidate submission hold")


def _verify_centre_access(user: CurrentUser, tc_id: int | None) -> None:
    """Ensure user has access to this centre (or sees all).

    Raises 403 if centre is unassigned or not in user's permitted list.
    """
    if user.sees_all_centres:
        return
    if tc_id is None:
        raise HTTPException(403, "Access denied: unassigned centre context requires administrative privileges.")
    allowed = allowed_tc_ids(user)
    if allowed is not None and tc_id not in allowed:
        raise HTTPException(403, "You do not have access to this training centre.")


def _verify_case_access(user: CurrentUser, case: dict[str, Any]) -> None:
    """Verify user has access to a duplicate case.

    If case has an explicit tc_id, verifies access to that tc_id.
    If case tc_id is None (cross-centre case), verifies user has access to at least one member candidate's centre.
    """
    if user.sees_all_centres:
        return

    case_tc_id = case.get("tc_id")
    if case_tc_id is not None:
        _verify_centre_access(user, case_tc_id)
        return

    # Cross-centre case: check member candidates
    case_id = case.get("id")
    members_res = (
        supabase.table("duplicate_case_members")
        .select("candidate_id, candidates!inner(batches!inner(tc_id))")
        .eq("case_id", case_id)
        .execute()
    )
    allowed = set(allowed_tc_ids(user) or [])
    has_member_access = False
    for m in (members_res.data or []):
        cand_tc = m.get("candidates", {}).get("batches", {}).get("tc_id")
        if cand_tc in allowed:
            has_member_access = True
            break

    if not has_member_access:
        raise HTTPException(403, "You do not have access to any training centres involved in this duplicate case.")


def _get_candidate_tc_id(candidate_id: int) -> int:
    """Fetch TC_id for a candidate via their batch.

    Raises 404 if candidate does not exist or has no batch mapping.
    """
    res = (
        supabase.table("candidates")
        .select("kb_batch_id, batches!inner(tc_id)")
        .eq("candidate_id", candidate_id)
        .limit(1)
        .execute()
    )
    if not res.data or "batches" not in res.data[0] or res.data[0]["batches"].get("tc_id") is None:
        raise HTTPException(404, f"Candidate {candidate_id} not found or has no training centre mapping.")
    return res.data[0]["batches"]["tc_id"]


@router.get("/cases")
def list_duplicate_cases(
    status: DuplicateStatus | None = None,
    rule_code: str | None = None,
    user: CurrentUser = Depends(get_current_user),
):
    """List duplicate review cases scoped by the user's assigned training centres."""
    allowed = allowed_tc_ids(user)
    q = supabase.table("duplicate_cases").select(
        "id,rule_code,rule_description,status,severity,tc_id,created_at,updated_at,last_reviewed_at,last_decision"
    )

    if allowed is not None:
        if not allowed:
            return []
        q = q.in_("tc_id", allowed)

    if status:
        q = q.eq("status", status.value)
    if rule_code:
        q = q.eq("rule_code", rule_code)

    res = q.order("created_at", desc=True).execute()
    return res.data


@router.get("/cases/{case_id}")
def get_duplicate_case(case_id: str, user: CurrentUser = Depends(get_current_user)):
    """Get full details of a duplicate case, including candidate members, candidate info, and review history."""
    case_res = (
        supabase.table("duplicate_cases")
        .select("*")
        .eq("id", case_id)
        .limit(1)
        .execute()
    )
    if not case_res.data:
        raise HTTPException(404, "Duplicate case not found.")

    case = case_res.data[0]
    _verify_case_access(user, case)

    # Fetch members
    members_res = (
        supabase.table("duplicate_case_members")
        .select("candidate_id,match_metadata,candidates(candidate_id,first_name,last_name,father_name,dob,mobile,kb_batch_id,appointed)")
        .eq("case_id", case_id)
        .execute()
    )

    # Fetch audit history
    history_res = (
        supabase.table("duplicate_review_history")
        .select("id,from_status,to_status,decision,reason,acted_by,created_at,profiles(full_name,role)")
        .eq("case_id", case_id)
        .order("created_at", desc=True)
        .execute()
    )

    return {
        "case": case,
        "members": members_res.data,
        "history": history_res.data,
    }


@router.post("/cases/{case_id}/review")
def review_duplicate_case(
    case_id: str,
    payload: ReviewDecisionRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Record a review decision for a duplicate case.

    Enforces mandatory non-empty reason for consequential decisions.
    Preserves all original candidate records and IDs without merging or deleting.
    Records review action in auditable history and audit_log.
    """
    case_res = (
        supabase.table("duplicate_cases")
        .select("*")
        .eq("id", case_id)
        .limit(1)
        .execute()
    )
    if not case_res.data:
        raise HTTPException(404, "Duplicate case not found.")

    case = case_res.data[0]
    _verify_case_access(user, case)

    from_status = case["status"]
    to_status = payload.to_status.value
    cleaned_reason = payload.reason.strip()

    # Rule: Consequential review decisions require authorized reviewer roles and mandatory reason
    if payload.to_status in CONSEQUENTIAL_STATUSES:
        if user.role not in REVIEW_ROLES:
            raise HTTPException(403, f"Role '{user.role}' cannot make consequential duplicate review decisions.")
        if not cleaned_reason:
            raise HTTPException(
                422,
                f"A mandatory non-empty reason is required when transitioning a case to {to_status}.",
            )

    now_iso = datetime.now(timezone.utc).isoformat()

    # Update case status
    update_data = {
        "status": to_status,
        "last_reviewed_by": user.id,
        "last_reviewed_at": now_iso,
        "last_decision": payload.decision.strip(),
        "last_reason": cleaned_reason,
        "updated_at": now_iso,
    }
    supabase.table("duplicate_cases").update(update_data).eq("id", case_id).execute()

    # Insert into review history audit trail
    history_data = {
        "case_id": case_id,
        "from_status": from_status,
        "to_status": to_status,
        "decision": payload.decision.strip(),
        "reason": cleaned_reason,
        "acted_by": user.id,
        "created_at": now_iso,
    }
    supabase.table("duplicate_review_history").insert(history_data).execute()

    # Also log to system audit_log
    try:
        supabase.table("audit_log").insert({
            "user_id": user.id,
            "action": f"REVIEW_DUPLICATE_CASE_{to_status}",
            "entity": "duplicate_cases",
            "entity_id": case_id,
            "details": {
                "from_status": from_status,
                "to_status": to_status,
                "decision": payload.decision.strip(),
                "reason": cleaned_reason,
            },
            "created_at": now_iso,
        }).execute()
    except Exception:
        pass  # Non-fatal if audit_log table is optional

    return {
        "message": "Review decision recorded successfully.",
        "case_id": case_id,
        "from_status": from_status,
        "to_status": to_status,
        "preserved_candidates": True,
    }


@router.get("/candidates/{candidate_id}/status")
def get_candidate_duplicate_status(
    candidate_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    """Retrieve candidate duplicate warning and submission hold status.

    - Unresolved duplicate cases produce a non-blocking warning.
    - Only an active hold in candidate_holds blocks submission.
    """
    tc_id = _get_candidate_tc_id(candidate_id)
    _verify_centre_access(user, tc_id)

    # 1. Check for unresolved duplicate cases
    member_res = (
        supabase.table("duplicate_case_members")
        .select("case_id,duplicate_cases!inner(id,rule_code,rule_description,status,severity)")
        .eq("candidate_id", candidate_id)
        .in_("duplicate_cases.status", ["PENDING", "UNDER_REVIEW", "UNRESOLVED"])
        .execute()
    )
    unresolved_cases = [m["duplicate_cases"] for m in member_res.data] if member_res.data else []
    has_warning = len(unresolved_cases) > 0
    warning_msg = (
        f"Candidate has {len(unresolved_cases)} unresolved potential duplicate review case(s). Review recommended."
        if has_warning
        else None
    )

    # 2. Check for active holds
    hold_res = (
        supabase.table("candidate_holds")
        .select("id,hold_reason,placed_by,placed_at,case_id")
        .eq("candidate_id", candidate_id)
        .eq("is_active", True)
        .execute()
    )
    active_holds = hold_res.data or []
    has_hold = len(active_holds) > 0

    return {
        "candidate_id": candidate_id,
        "has_duplicate_warning": has_warning,
        "warning_message": warning_msg,
        "unresolved_cases_count": len(unresolved_cases),
        "unresolved_cases": unresolved_cases,
        "has_active_hold": has_hold,
        "active_holds": active_holds,
        # Warning alone does NOT block submission; only an active hold blocks submission
        "can_submit": not has_hold,
    }


@router.post("/candidates/{candidate_id}/hold")
def place_candidate_hold(
    candidate_id: int,
    payload: PlaceHoldRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Place an explicit submission hold on a candidate.

    Requires authorized reviewer role, valid candidate, centre access, and mandatory reason.
    """
    if user.role not in HOLD_ROLES:
        raise HTTPException(403, f"Role '{user.role}' is not authorized to place submission holds.")

    tc_id = _get_candidate_tc_id(candidate_id)
    _verify_centre_access(user, tc_id)

    cleaned_reason = payload.reason.strip()
    if not cleaned_reason:
        raise HTTPException(422, "A mandatory reason is required to place a submission hold.")

    now_iso = datetime.now(timezone.utc).isoformat()
    hold_data = {
        "candidate_id": candidate_id,
        "case_id": payload.case_id,
        "is_active": True,
        "hold_reason": cleaned_reason,
        "placed_by": user.id,
        "placed_at": now_iso,
    }
    res = supabase.table("candidate_holds").insert(hold_data).execute()

    # Log to audit_log
    try:
        supabase.table("audit_log").insert({
            "user_id": user.id,
            "action": "PLACE_SUBMISSION_HOLD",
            "entity": "candidates",
            "entity_id": str(candidate_id),
            "details": {"reason": cleaned_reason, "case_id": payload.case_id},
            "created_at": now_iso,
        }).execute()
    except Exception:
        pass

    return {
        "message": "Submission hold placed successfully.",
        "candidate_id": candidate_id,
        "hold": res.data[0] if res.data else hold_data,
        "can_submit": False,
    }


@router.post("/candidates/{candidate_id}/release-hold")
def release_candidate_hold(
    candidate_id: int,
    payload: ReleaseHoldRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Release an active submission hold on a candidate.

    Requires authorized reviewer role, valid candidate, centre access, and mandatory reason.
    """
    if user.role not in HOLD_ROLES:
        raise HTTPException(403, f"Role '{user.role}' is not authorized to release submission holds.")

    tc_id = _get_candidate_tc_id(candidate_id)
    _verify_centre_access(user, tc_id)

    cleaned_reason = payload.reason.strip()
    if not cleaned_reason:
        raise HTTPException(422, "A mandatory reason is required to release a submission hold.")

    now_iso = datetime.now(timezone.utc).isoformat()

    # Find active holds for candidate
    active_holds = (
        supabase.table("candidate_holds")
        .select("id")
        .eq("candidate_id", candidate_id)
        .eq("is_active", True)
        .execute()
    )
    if not active_holds.data:
        raise HTTPException(404, "No active submission hold found for this candidate.")

    for h in active_holds.data:
        supabase.table("candidate_holds").update({
            "is_active": False,
            "released_by": user.id,
            "released_at": now_iso,
            "release_reason": cleaned_reason,
        }).eq("id", h["id"]).execute()

    # Log to audit_log
    try:
        supabase.table("audit_log").insert({
            "user_id": user.id,
            "action": "RELEASE_SUBMISSION_HOLD",
            "entity": "candidates",
            "entity_id": str(candidate_id),
            "details": {"reason": cleaned_reason},
            "created_at": now_iso,
        }).execute()
    except Exception:
        pass

    return {
        "message": "Submission hold released successfully.",
        "candidate_id": candidate_id,
        "can_submit": True,
    }
