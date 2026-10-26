"""Cascading dropdowns for L1: State -> Centre -> Sanction order -> Batch -> Candidate.

Queries the ddugky_candidates master table with centre scoping and candidate details.
"""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException

from ..auth import (
    ALL_12_STATES,
    CurrentUser,
    allowed_states,
    allowed_tc_ids,
    check_candidate_access,
    get_candidate_state,
    get_current_user,
    resolve_state,
)
from ..config import settings
from ..db import TRANSIENT_ERRORS, retry_read_query, supabase

router = APIRouter(prefix="/lookups", tags=["lookups"])


def _check_centre(user: CurrentUser, tc_id: int) -> None:
    permitted_st = allowed_states(user)
    if permitted_st is not None:
        if not permitted_st:
            raise HTTPException(403, "You do not have access to any states.")
        # Verify training centre belongs to user's permitted state(s)
        try:
            res = retry_read_query(
                lambda: supabase.table("ddugky_candidates")
                .select("candidate_id,tc_state_name")
                .eq("tc_id", tc_id)
                .limit(10)
                .execute()
            )
            rows = res.data or []
            if rows:
                has_permitted = any(
                    (resolve_state(r.get("tc_state_name")) in permitted_st)
                    for r in rows
                )
                if not has_permitted:
                    raise HTTPException(403, "You do not have access to this training centre.")
            else:
                raise HTTPException(404, "Training centre not found.")
        except HTTPException:
            raise
        except TRANSIENT_ERRORS as exc:
            import logging
            logging.getLogger("cpass.lookups").warning("Transient error during centre check for tc_id %s: %s", tc_id, exc)
            raise HTTPException(
                503,
                "Training centre verification service temporarily unreachable. Please retry.",
                headers={"Retry-After": "1"},
            )
        except Exception:
            raise HTTPException(403, "Authorization check failed for this training centre.")

    allowed = allowed_tc_ids(user)
    if allowed is not None and tc_id not in allowed:
        raise HTTPException(403, "You are not assigned to this training centre.")


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


@router.get("/states")
def states(user: CurrentUser = Depends(get_current_user)):
    """Return distinct states permitted for this user.
    L1 coordinators receive only their assigned state.
    Unassigned L1 receives an empty list (fail-closed).
    Admins and executive roles receive all states.
    """
    permitted = allowed_states(user)
    if permitted is not None:
        return sorted(permitted)

    try:
        res = retry_read_query(lambda: supabase.rpc("get_cpass_states", {}).execute())
        rpc_states = {
            row["state"].strip()
            for row in (res.data or [])
            if row.get("state") and row["state"].strip()
        }

        # Query ddugky_candidates for any candidate state_name not included in training centre RPC
        if rpc_states:
            try:
                missing_res = retry_read_query(
                    lambda: supabase.table("ddugky_candidates")
                    .select("tc_state_name")
                    .not_.in_("tc_state_name", tuple(rpc_states))
                    .execute()
                )
                for r in (missing_res.data or []):
                    st = (r.get("tc_state_name") or "").strip()
                    if st:
                        rpc_states.add(st)
            except Exception:
                pass

        all_states = set(ALL_12_STATES)
        all_states.update(rpc_states)
        return sorted(all_states)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception("Failed to retrieve CPASS states")
        if permitted is not None:
            return sorted(permitted)
        return sorted(ALL_12_STATES)


@router.get("/centres")
def centres(state: str, user: CurrentUser = Depends(get_current_user)):
    """Return distinct training centres for the given state, respecting user state and centre scoping.
    
    Training Centre State (tc_state_name) is the authoritative source of truth.
    """
    resolved_state = resolve_state(state) or state
    permitted_st = allowed_states(user)
    if permitted_st is not None:
        if not permitted_st or (resolved_state not in permitted_st and state not in permitted_st):
            raise HTTPException(403, f"Access to state '{state}' is forbidden.")

    allowed = allowed_tc_ids(user)
    try:
        res = retry_read_query(
            lambda: supabase.table("ddugky_candidates")
            .select("tc_id,tc_name")
            .eq("tc_state_name", resolved_state)
            .execute()
        )
        tc_dict = {}
        for r in (res.data or []):
            tcid = r.get("tc_id")
            name = r.get("tc_name")
            if tcid and name:
                if allowed is None or tcid in allowed:
                    tc_dict[tcid] = name

        return sorted(
            [{"tc_id": k, "name": v} for k, v in tc_dict.items()],
            key=lambda c: c["name"],
        )
    except HTTPException:
        raise
    except TRANSIENT_ERRORS as exc:
        import logging
        logging.getLogger("cpass.lookups").warning("Transient error querying training centres: %s", exc)
        raise HTTPException(503, "Training centres service temporarily unreachable. Please retry.", headers={"Retry-After": "1"})
    except Exception as exc:
        import logging
        logging.getLogger("cpass.lookups").exception("Failed to query training centres: %s", exc)
        raise HTTPException(500, "Failed to retrieve training centres. Please retry.")


@router.get("/sanction-orders")
def sanction_orders(tc_id: int, user: CurrentUser = Depends(get_current_user)):
    """Return distinct sanction orders for the specified training centre."""
    _check_centre(user, tc_id)
    try:
        res = retry_read_query(
            lambda: supabase.table("ddugky_candidates")
            .select("sanction_order_number")
            .eq("tc_id", tc_id)
            .execute()
        )
        orders = {r["sanction_order_number"] for r in (res.data or []) if r.get("sanction_order_number")}
        return sorted(orders)
    except HTTPException:
        raise
    except TRANSIENT_ERRORS as exc:
        import logging
        logging.getLogger("cpass.lookups").warning("Transient error querying sanction orders: %s", exc)
        raise HTTPException(503, "Sanction orders service temporarily unreachable. Please retry.", headers={"Retry-After": "1"})
    except Exception as exc:
        import logging
        logging.getLogger("cpass.lookups").exception("Failed to query sanction orders: %s", exc)
        raise HTTPException(500, "Failed to retrieve sanction orders. Please retry.")


@router.get("/batches")
def batches(tc_id: int, sanction_order: str, user: CurrentUser = Depends(get_current_user)):
    """Return distinct batches for the centre and sanction order."""
    _check_centre(user, tc_id)
    try:
        res = retry_read_query(
            lambda: supabase.table("ddugky_candidates")
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
        return sorted(list(b_dict.values()), key=lambda b: str(b["batch_code"]))
    except HTTPException:
        raise
    except TRANSIENT_ERRORS as exc:
        import logging
        logging.getLogger("cpass.lookups").warning("Transient error querying batches: %s", exc)
        raise HTTPException(503, "Batches service temporarily unreachable. Please retry.", headers={"Retry-After": "1"})
    except Exception as exc:
        import logging
        logging.getLogger("cpass.lookups").exception("Failed to query batches: %s", exc)
        raise HTTPException(500, "Failed to retrieve batches. Please retry.")


@router.get("/candidates")
def candidates(kb_batch_id: int, user: CurrentUser = Depends(get_current_user)):
    """Return candidates in a specific batch, filtered by user authorization."""
    permitted_st = allowed_states(user)
    if permitted_st is not None and not permitted_st:
        raise HTTPException(403, "You do not have access to any candidates.")

    try:
        res = retry_read_query(
            lambda: supabase.table("ddugky_candidates")
            .select("candidate_id,candidate_first_name,candidate_last_name,candidate_father_name,appointed,tc_id,tc_state_name")
            .eq("kb_batch_id", kb_batch_id)
            .execute()
        )
        rows = res.data or []
        if not rows:
            return []

        _check_centre(user, rows[0]["tc_id"])
        cands = []
        for r in rows:
            if settings.appointed_only and not r.get("appointed"):
                continue
            if permitted_st is not None:
                cand_st = get_candidate_state(r)
                if not cand_st or cand_st not in permitted_st:
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
    except TRANSIENT_ERRORS as exc:
        import logging
        logging.getLogger("cpass.lookups").warning("Transient error querying candidates: %s", exc)
        raise HTTPException(503, "Candidates service temporarily unreachable. Please retry.", headers={"Retry-After": "1"})
    except Exception as exc:
        import logging
        logging.getLogger("cpass.lookups").exception("Failed to query candidates: %s", exc)
        raise HTTPException(500, "Failed to retrieve candidates. Please retry.")


@router.get("/candidates/{candidate_id}")
def candidate_detail(candidate_id: int, user: CurrentUser = Depends(get_current_user)):
    """Return full candidate details, duplicate warnings, and submission hold statuses."""
    try:
        cand_res = retry_read_query(
            lambda: supabase.table("ddugky_candidates")
            .select("*")
            .eq("candidate_id", candidate_id)
            .limit(1)
            .execute()
        )
        if not cand_res.data:
            raise HTTPException(404, "Candidate not found.")

        r = cand_res.data[0]
        # State and centre authorization check
        check_candidate_access(user, r)

        # Clean and mask sensitive data
        raw_bank = r.get("bank_account")
        masked_bank = _mask_bank_account(raw_bank)
        addr = r.get("permanent_address") or r.get("permanent_address_village") or "Not Available"
        if addr and str(addr).strip() == "0":
            addr = "Not Available"

        cand = {
            "candidate_id": r["candidate_id"],
            "first_name": r.get("candidate_first_name"),
            "last_name": r.get("candidate_last_name"),
            "father_name": r.get("candidate_father_name") or "Not Available",
            "gender": r.get("gender") or "Not Available",
            "dob": str(r.get("date_of_birth") or "Not Available"),
            "date_of_birth": str(r.get("date_of_birth") or "Not Available"),
            "mobile": r.get("mobile_number") or "Not Available",
            "appointed": bool(r.get("appointed")),
            "employer_name": r.get("employer_name"),
            "kb_batch_id": r.get("kb_batch_id"),
            "batch_code": r.get("batch_code") or "Not Available",
            "batch_start_date": str(r.get("batch_start_date") or "Not Available"),
            "batch_end_date": str(r.get("batch_end_date") or "Not Available"),
            "trade_name": r.get("trade_name") or "Not Available",
            "tc_id": r.get("tc_id"),
            "tc_name": r.get("tc_name"),
            "tc_state_name": r.get("tc_state_name"),
            "state_name": r.get("state_name") or r.get("tc_state_name"),
            "sanction_order_number": r.get("sanction_order_number") or "Not Available",
            "monthly_ctc": r.get("monthly_ctc"),
            "candidate_email": r.get("candidate_email") or "Not Available",
            "candidate_qualification": r.get("candidate_qualification") or "Not Available",
            "address": addr,
            "permanent_address": addr,
            "bank_account": masked_bank,
            "masked_bank_account": masked_bank,
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
            member_res = retry_read_query(
                lambda: supabase.table("duplicate_case_members")
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
            hold_res = retry_read_query(
                lambda: supabase.table("candidate_holds")
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
    except TRANSIENT_ERRORS as exc:
        import logging
        logging.getLogger("cpass.lookups").warning("Transient error querying candidate detail: %s", exc)
        raise HTTPException(503, "Candidate details service temporarily unreachable. Please retry.", headers={"Retry-After": "1"})
    except Exception as exc:
        import logging
        logging.getLogger("cpass.lookups").exception("Failed to query candidate detail: %s", exc)
        raise HTTPException(500, "Failed to retrieve candidate detail. Please retry.")
