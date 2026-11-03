import sys

with open("backend/app/routers/audits.py", "rb") as f:
    raw = f.read()

content = raw.decode("utf-8").replace("\r\n", "\n")

target_start = "def extract_review_stages(audit: dict | None) -> dict[str, Any]:"
target_end = '    return {\n        "ch": {"status": ch_status},\n        "cops": {"status": cops_status},\n        "bl": {"status": bl_status},\n        "ch_status": ch_status,\n        "cops_status": cops_status,\n        "bl_status": bl_status,\n    }'

idx_start = content.find(target_start)
idx_end = content.find(target_end)

if idx_start == -1 or idx_end == -1:
    print(f"Could not locate targets: start={idx_start}, end={idx_end}")
    sys.exit(1)

old_block = content[idx_start : idx_end + len(target_end)]

replacement = """def extract_review_stages(audit: dict | None) -> dict[str, Any]:
    \"\"\"Extract and normalize persisted multi-level review stages (CH - L2, COPS - L3, BL - L4, CEO - L5).

    If explicit `review_stages` are stored in signoff_details, return them.
    Otherwise, derive backwards-compatible stage statuses from existing cpass_status and audit_status.
    \"\"\"
    if not audit:
        return {
            "ch": {"status": "Pending"},
            "cops": {"status": "Pending"},
            "bl": {"status": "Pending"},
            "ceo": {"status": "Pending"},
            "ch_status": "Pending",
            "cops_status": "Pending",
            "bl_status": "Pending",
            "ceo_status": "Pending",
        }

    signoff = audit.get("signoff_details") or {}
    stages = signoff.get("review_stages")

    raw_status = (audit.get("cpass_status") or "").upper()
    raw_audit = (audit.get("audit_status") or "").upper()

    if isinstance(stages, dict) and ("ch" in stages or "cops" in stages or "bl" in stages or "ceo" in stages):
        ch_raw = stages.get("ch")
        cops_raw = stages.get("cops")
        bl_raw = stages.get("bl")
        ceo_raw = stages.get("ceo")

        ch_obj = ch_raw if isinstance(ch_raw, dict) else {"status": str(ch_raw or "Pending")}
        cops_obj = cops_raw if isinstance(cops_raw, dict) else {"status": str(cops_raw or "Pending")}
        bl_obj = bl_raw if isinstance(bl_raw, dict) else {"status": str(bl_raw or "Pending")}
        ceo_obj = ceo_raw if isinstance(ceo_raw, dict) else {"status": str(ceo_raw or "Pending")}

        ch_st = ch_obj.get("status") or "Pending"
        if ch_st in ("Returned", "Returned to L1") or raw_audit == "RETURNED_TO_L1" or raw_status == "RETURNED_TO_L1":
            ch_st = "Returned to L1"
            ch_obj["status"] = "Returned to L1"

        return {
            "ch": ch_obj,
            "cops": cops_obj,
            "bl": bl_obj,
            "ceo": ceo_obj,
            "ch_status": ch_st,
            "cops_status": cops_obj.get("status") or "Pending",
            "bl_status": bl_obj.get("status") or "Pending",
            "ceo_status": ceo_obj.get("status") or "Pending",
        }

    # Derive from legacy status or returned status
    if raw_status == "RETURNED_TO_L1" or raw_audit == "RETURNED_TO_L1":
        return {
            "ch": {"status": "Returned to L1"},
            "cops": {"status": "Pending"},
            "bl": {"status": "Pending"},
            "ceo": {"status": "Pending"},
            "ch_status": "Returned to L1",
            "cops_status": "Pending",
            "bl_status": "Pending",
            "ceo_status": "Pending",
        }

    l2_app = signoff.get("l2_approval") or {}

    ch_status = "Pending"
    cops_status = "Pending"
    bl_status = "Pending"
    ceo_status = "Pending"

    if raw_status in {"APPROVED", "CPASS_APPROVED"}:
        ch_status = "Recommended"
        cops_status = "Verified"
        bl_status = "Approved"
        ceo_status = "Approved"
    elif raw_status == "BL_APPROVED":
        ch_status = "Recommended"
        cops_status = "Verified"
        bl_status = "Approved"
        ceo_status = "Pending"
    elif raw_status == "VERIFIED":
        ch_status = "Recommended"
        cops_status = "Verified"
        bl_status = "Pending"
        ceo_status = "Pending"
    elif raw_status == "L2_APPROVED" or l2_app.get("approved"):
        ch_status = "Recommended"
        cops_status = "Pending"
        bl_status = "Pending"
        ceo_status = "Pending"
    elif raw_status in {"REJECTED", "L2_REJECTED", "CPASS_REJECTED"} or raw_audit == "REJECTED":
        rej_stage = signoff.get("rejected_stage") or ""
        if rej_stage == "ceo" or raw_status == "L5_REJECTED":
            ch_status = "Recommended"
            cops_status = "Verified"
            bl_status = "Approved"
            ceo_status = "Rejected"
        elif rej_stage == "bl" or raw_status == "L4_REJECTED":
            ch_status = "Recommended"
            cops_status = "Verified"
            bl_status = "Rejected"
            ceo_status = "Pending"
        elif rej_stage == "cops" or raw_status == "L3_REJECTED":
            ch_status = "Recommended"
            cops_status = "Rejected"
            bl_status = "Pending"
            ceo_status = "Pending"
        else:
            ch_status = "Rejected"
            cops_status = "Pending"
            bl_status = "Pending"
            ceo_status = "Pending"

    return {
        "ch": {"status": ch_status},
        "cops": {"status": cops_status},
        "bl": {"status": bl_status},
        "ceo": {"status": ceo_status},
        "ch_status": ch_status,
        "cops_status": cops_status,
        "bl_status": bl_status,
        "ceo_status": ceo_status,
    }"""

new_content = content[:idx_start] + replacement + content[idx_start + len(old_block):]
with open("backend/app/routers/audits.py", "w", encoding="utf-8") as f:
    f.write(new_content)
print("Updated extract_review_stages successfully!")
