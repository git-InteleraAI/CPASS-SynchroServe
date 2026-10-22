"""Cascading dropdowns for L1: State -> Centre -> Sanction order -> Batch -> Candidate.

Queries the ddugky_candidates master table with centre scoping and candidate details.
"""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException

from ..auth import CurrentUser, allowed_tc_ids, get_current_user
from ..config import settings
from ..db import supabase

router = APIRouter(prefix="/lookups", tags=["lookups"])


def _check_centre(user: CurrentUser, tc_id: int) -> None:
    allowed = allowed_tc_ids(user)
    if allowed is not None and tc_id not in allowed:
        raise HTTPException(403, "You are not assigned to this training centre.")


@router.get("/states")
def states(user: CurrentUser = Depends(get_current_user)):
    """Return all distinct states from ddugky_candidates."""
    try:
        res = supabase.rpc("get_cpass_states", {}).execute()
        return sorted(
            {
                row["state"].strip()
                for row in (res.data or [])
                if row.get("state") and row["state"].strip()
            }
        )
    except Exception as exc:
        # Log the actual error instead of silently hiding it.
        import logging
        logging.getLogger(__name__).exception(
            "Failed to retrieve CPASS states"
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve states. Check backend logs."
        ) from exc

@router.get("/centres")
def centres(state: str, user: CurrentUser = Depends(get_current_user)):
    """Return distinct training centres for the given state, respecting user centre scoping."""
    allowed = allowed_tc_ids(user)
    try:
        res = (
            supabase.table("ddugky_candidates")
            .select("tc_id,tc_name")
            .eq("tc_state_name", state)
            .execute()
        )
        tc_dict = {}
        for r in (res.data or []):
            tcid = r.get("tc_id")
            name = r.get("tc_name")
            if tcid and name:
                if allowed is None or tcid in allowed:
                    tc_dict[tcid] = name
        if tc_dict:
            return sorted(
                [{"tc_id": k, "name": v} for k, v in tc_dict.items()],
                key=lambda c: c["name"],
            )
    except Exception:
        pass

    # Fallback to training_centres table
    try:
        q = supabase.table("training_centres").select("tc_id,name").eq("state_name", state)
        if allowed is not None:
            if not allowed:
                return []
            q = q.in_("tc_id", allowed)
        rows = q.execute().data or []
        return sorted(rows, key=lambda c: c["name"])
    except Exception:
        return []


@router.get("/sanction-orders")
def sanction_orders(tc_id: int, user: CurrentUser = Depends(get_current_user)):
    """Return distinct sanction orders for the specified training centre."""
    _check_centre(user, tc_id)
    try:
        res = (
            supabase.table("ddugky_candidates")
            .select("sanction_order_number")
            .eq("tc_id", tc_id)
            .execute()
        )
        orders = {r["sanction_order_number"] for r in (res.data or []) if r.get("sanction_order_number")}
        if orders:
            return sorted(orders)
    except Exception:
        pass

    # Fallback to batches table
    try:
        rows = supabase.table("batches").select("sanction_order").eq("tc_id", tc_id).execute().data
        return sorted({r["sanction_order"] for r in (rows or []) if r.get("sanction_order")})
    except Exception:
        return []


@router.get("/batches")
def batches(tc_id: int, sanction_order: str, user: CurrentUser = Depends(get_current_user)):
    """Return distinct batches for the centre and sanction order."""
    _check_centre(user, tc_id)
    try:
        res = (
            supabase.table("ddugky_candidates")
            .select("kb_batch_id,batch_code,trade_name")
            .eq("tc_id", tc_id)
            .eq("sanction_order_number", sanction_order)
            .execute()
        )
        b_dict = {}
        for r in (res.data or []):
            kbid = r.get("kb_batch_id")
            code = r.get("batch_code")
            if kbid and code and kbid not in b_dict:
                b_dict[kbid] = {
                    "kb_batch_id": kbid,
                    "batch_code": code,
                    "trade_name": r.get("trade_name"),
                }
        if b_dict:
            return sorted(list(b_dict.values()), key=lambda b: str(b["batch_code"]))
    except Exception:
        pass

    # Fallback to batches table
    try:
        rows = (
            supabase.table("batches")
            .select("kb_batch_id,batch_code,trade_name")
            .eq("tc_id", tc_id)
            .eq("sanction_order_number", sanction_order)
            .execute()
            .data
        )
        return sorted(rows or [], key=lambda b: str(b["batch_code"]))
    except Exception:
        return []


@router.get("/candidates")
def candidates(kb_batch_id: int, user: CurrentUser = Depends(get_current_user)):
    """Return candidates in a specific batch."""
    try:
        res = (
            supabase.table("ddugky_candidates")
            .select("candidate_id,candidate_first_name,candidate_last_name,candidate_father_name,appointed,tc_id")
            .eq("kb_batch_id", kb_batch_id)
            .execute()
        )
        rows = res.data or []
        if rows:
            _check_centre(user, rows[0]["tc_id"])
            cands = []
            for r in rows:
                if settings.appointed_only and not r.get("appointed"):
                    continue
                cands.append({
                    "candidate_id": r["candidate_id"],
                    "first_name": r.get("candidate_first_name"),
                    "last_name": r.get("candidate_last_name"),
                    "father_name": r.get("candidate_father_name"),
                    "appointed": bool(r.get("appointed")),
                })
            return sorted(cands, key=lambda c: (c["first_name"] or "").lower())
    except HTTPException:
        raise
    except Exception:
        pass

    # Fallback to candidates / batches tables
    batch = supabase.table("batches").select("tc_id").eq("kb_batch_id", kb_batch_id).limit(1).execute().data
    if not batch:
        raise HTTPException(404, "Batch not found.")
    _check_centre(user, batch[0]["tc_id"])

    q = supabase.table("candidates").select("candidate_id,first_name,last_name,father_name,appointed").eq(
        "kb_batch_id", kb_batch_id
    )
    if settings.appointed_only:
        q = q.eq("appointed", True)
    rows = q.execute().data or []
    return sorted(rows, key=lambda c: (c["first_name"] or "").lower())


@router.get("/candidates/{candidate_id}")
def candidate_detail(candidate_id: int, user: CurrentUser = Depends(get_current_user)):
    """Return full candidate details, duplicate warnings, and submission hold statuses."""
    # Try ddugky_candidates
    try:
        cand_res = (
            supabase.table("ddugky_candidates")
            .select("*")
            .eq("candidate_id", candidate_id)
            .limit(1)
            .execute()
        )
        if cand_res.data:
            r = cand_res.data[0]
            if r.get("tc_id"):
                _check_centre(user, r["tc_id"])

            cand = {
                "candidate_id": r["candidate_id"],
                "first_name": r.get("candidate_first_name"),
                "last_name": r.get("candidate_last_name"),
                "father_name": r.get("candidate_father_name"),
                "gender": r.get("gender"),
                "dob": r.get("date_of_birth"),
                "mobile": r.get("mobile_number"),
                "appointed": bool(r.get("appointed")),
                "employer_name": r.get("employer_name"),
                "kb_batch_id": r.get("kb_batch_id"),
                "batch_code": r.get("batch_code"),
                "tc_id": r.get("tc_id"),
                "tc_name": r.get("tc_name"),
                "tc_state_name": r.get("tc_state_name"),
                "sanction_order_number": r.get("sanction_order_number"),
                "monthly_ctc": r.get("monthly_ctc"),
                "trade_name": r.get("trade_name"),
                "aadhar": r.get("aadhar"),
                "aadhaar_number": r.get("aadhar"),
            }

            # Check duplicate warnings & holds if tables exist
            has_warning = False
            warning_text = None
            unresolved_cases = []
            has_hold = False
            active_holds = []

            try:
                member_res = (
                    supabase.table("duplicate_case_members")
                    .select("case_id,duplicate_cases!inner(id,rule_code,rule_description,status,severity)")
                    .eq("candidate_id", candidate_id)
                    .in_("duplicate_cases.status", ["PENDING", "UNDER_REVIEW", "UNRESOLVED"])
                    .execute()
                )
                unresolved_cases = [m["duplicate_cases"] for m in (member_res.data or [])]
                has_warning = len(unresolved_cases) > 0
                if has_warning:
                    warning_text = f"Candidate has {len(unresolved_cases)} unresolved potential duplicate review case(s)."
            except Exception:
                pass

            try:
                hold_res = (
                    supabase.table("candidate_holds")
                    .select("id,hold_reason,placed_by,placed_at")
                    .eq("candidate_id", candidate_id)
                    .eq("is_active", True)
                    .execute()
                )
                active_holds = hold_res.data or []
                has_hold = len(active_holds) > 0
            except Exception:
                pass

            return {
                **cand,
                "has_duplicate_warning": has_warning,
                "warning_message": warning_text,
                "unresolved_cases": unresolved_cases,
                "has_active_hold": has_hold,
                "active_holds": active_holds,
                "can_submit": not has_hold,
            }
    except HTTPException:
        raise
    except Exception:
        pass

    # Fallback to candidates table
    cand_res = (
        supabase.table("candidates")
        .select("candidate_id,first_name,last_name,father_name,gender,dob,mobile,appointed,employer_name,kb_batch_id,batches!inner(tc_id,batch_code,sanction_order)")
        .eq("candidate_id", candidate_id)
        .limit(1)
        .execute()
    )
    if not cand_res.data:
        raise HTTPException(404, "Candidate not found.")
    cand = cand_res.data[0]
    tc_id = cand["batches"]["tc_id"]
    _check_centre(user, tc_id)

    return {
        **cand,
        "has_duplicate_warning": False,
        "warning_message": None,
        "unresolved_cases": [],
        "has_active_hold": False,
        "active_holds": [],
        "can_submit": True,
    }
