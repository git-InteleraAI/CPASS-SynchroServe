"""Centralized L1 placement audit finalization & lock helper.

Enforces a consistent, authoritative read-only lock for finalized L1 audits across
all document uploads, replacements, deletions, payslip availability changes,
draft saves, and resubmissions.
"""

from typing import Any
from fastapi import HTTPException
from ..db import supabase, retry_read_query


def is_audit_locked_for_l1(audit: dict[str, Any] | None) -> bool:
    """Determine whether a candidate's placement audit is locked against L1 modifications.

    Rules:
    - If no audit record exists, it is a new unfinalized draft -> UNLOCKED (False).
    - If audit_status or cpass_status is 'RETURNED_TO_L1' (or reviewer stage indicates
      returned to L1), editing and corrections are permitted -> UNLOCKED (False).
    - If audit_status is 'DRAFT', it is editable -> UNLOCKED (False).
    - If audit_status is 'SUBMITTED', 'APPROVED', 'REJECTED' or finalized_at is set
      (and not returned to L1), all L1 modifications are forbidden -> LOCKED (True).
    """
    if not audit or not isinstance(audit, dict):
        return False

    raw_audit = (audit.get("audit_status") or "").upper().strip()
    raw_status = (audit.get("cpass_status") or "").upper().strip()
    signoff = audit.get("signoff_details") or {}
    stages = signoff.get("review_stages") or {}
    ch_status = (stages.get("ch", {}).get("status") or "").lower().strip()
    active_return = signoff.get("active_return") or {}
    return_dest = signoff.get("return_destination") or active_return.get("destination")

    # Authoritative return-to-L1 detection: unlocks editing for L1 corrections
    if (
        raw_audit == "RETURNED_TO_L1"
        or raw_status == "RETURNED_TO_L1"
        or return_dest == "L1"
        or bool(signoff.get("return_to_l1"))
        or ch_status in ("returned", "returned to l1")
    ):
        return False

    # Standard unsubmitted draft
    if raw_audit == "DRAFT":
        return False

    # Finalized, submitted, or under-review states
    if (
        raw_audit in ("SUBMITTED", "APPROVED", "REJECTED")
        or raw_status in ("APPROVED", "VERIFIED", "L2_APPROVED", "REJECTED")
        or bool(audit.get("finalized_at"))
    ):
        return True

    return False


def check_l1_audit_unlocked(
    candidate_id: int,
    user_role: str,
    action_description: str = "modify audit or documents",
    db: Any = None,
) -> dict[str, Any] | None:
    """Enforce backend lock on finalized audits for L1 coordinators.

    Allows L2/L3/Admin operations to proceed without interference.
    Raises HTTPException(400) if an L1 coordinator attempts to mutate a finalized audit.
    """
    if user_role != "L1_COORDINATOR":
        return None

    client = db if db is not None else supabase
    res = retry_read_query(
        lambda: client.table("placement_audits")
        .select("id,candidate_id,audit_status,cpass_status,signoff_details,finalized_at")
        .eq("candidate_id", candidate_id)
        .limit(1)
        .execute()
    )
    audit = res.data[0] if (res and getattr(res, "data", None)) else None

    if is_audit_locked_for_l1(audit):
        if action_description == "save audit draft":
            detail = (
                "This placement audit has already been finalized/submitted and is locked for review. "
                "Corrections can be made after it is returned to L1."
            )
        else:
            detail = (
                "This placement audit has already been submitted and is locked for review. "
                "Corrections can be made after it is returned to L1."
            )
        raise HTTPException(
            status_code=400,
            detail=detail,
        )

    return audit
