import os

file_path = r"backend/app/routers/documents.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Define the new sync function
sync_func = '''
def sync_documents_to_placement_audit(
    candidate_id: int,
    user: CurrentUser | None = None,
    override_employer_details: list[dict[str, Any]] | None = None,
    override_salary_details: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Idempotently synchronize active candidate_documents into placement_audits.document_audit.

    Ensures a placement_audits record exists (creates baseline DRAFT if missing).
    Applies strict evidence matching rules:
    - 1. Appointment / Offer Letter: Updates availability, filename, and drive metadata.
    - 2. Salary Slips: Matches reporting month & year (and employer). Only updates the corresponding month.
    - 3. Bank Statements: Matches individual statements and consolidated bank statements across all covered months.
    - 4. Other Documents: Preserves optional documents.
    - 5. Status Consistency: Distinguishes physical file presence from reviewer compliance endorsements.
         Uploaded files become 'Available' ('Yes') while preserving reviewer verification state.
         Preserves coordinator 'No' / 'Payslip not available' unless a physical file is actually uploaded.
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Check or create placement audit record
    audit_res = (
        supabase.table("placement_audits")
        .select("*")
        .eq("candidate_id", candidate_id)
        .limit(1)
        .execute()
    )

    cand_ctx = _get_candidate_context(candidate_id, user)

    if not audit_res.data:
        # Create baseline audit draft
        first_name = cand_ctx.get("candidate_first_name") or ""
        last_name = cand_ctx.get("candidate_last_name") or ""
        full_name = f"{first_name} {last_name}".strip() or f"Candidate {candidate_id}"

        snapshot = {
            "candidate_id": candidate_id,
            "candidate_name": full_name,
            "full_name": full_name,
            "first_name": first_name or None,
            "last_name": last_name or None,
            "father_name": "Not Available",
            "dob": "Not Available",
            "date_of_birth": "Not Available",
            "gender": "Not Available",
            "mobile": "Not Available",
            "contact_number": "Not Available",
            "state": cand_ctx.get("state") or cand_ctx.get("tc_state_name") or cand_ctx.get("state_name"),
            "tc_name": cand_ctx.get("tc_name"),
            "training_centre": cand_ctx.get("tc_name"),
            "batch_code": cand_ctx.get("batch_code") or "Not Available",
            "batch_start_date": "Not Available",
            "batch_end_date": "Not Available",
            "trade_name": "Not Available",
            "trade": "Not Available",
            "sector": None,
            "candidate_email": "Not Available",
            "candidate_qualification": "Not Available",
            "address": "Not Available",
            "permanent_address": "Not Available",
            "bank_account": "Not Available",
            "masked_bank_account": "Not Available",
            "sanction_order": "Not Available",
            "aadhaar_last4": None,
            "masked_aadhaar": "Not Available",
            "aadhaar_number": "Not Available",
        }

        if override_employer_details:
            emp_details = override_employer_details
        else:
            emp_details = [{
                "id": "emp_1",
                "employer_name": cand_ctx.get("tc_name") or "Employer 1",
                "months_worked": None,
                "appointment_date": None,
                "designation": None,
                "place_of_work": cand_ctx.get("state") or None,
                "monthly_ctc": None,
                "minimum_wages": None,
            }]

        curr_y = datetime.now().year
        if override_salary_details:
            sal_details = override_salary_details
        else:
            sal_details = [
                {
                    "id": f"sal_{i}",
                    "employer_id": emp_details[0].get("id") or "emp_1",
                    "month": i,
                    "year": curr_y,
                    "working_days": 26,
                    "pay_days": 26,
                    "leave_days": 0,
                    "credit_date": None,
                    "amount_credited": None,
                    "gross_salary": None,
                    "deductions": None,
                    "net_salary": None,
                    "bank_name": None,
                }
                for i in range(1, 4)
            ]

        base_doc_audit = {
            "appointment_letter": {"available": "Pending", "compliance": "Under Verification", "remarks": ""},
            "other_document": {"available": "Pending", "compliance": "Under Verification", "remarks": ""},
        }
        for i in range(1, len(sal_details) + 1):
            base_doc_audit[f"salary_slip_{i}"] = {"available": "Pending", "compliance": "Under Verification", "remarks": ""}
            base_doc_audit[f"bank_statement_{i}"] = {"available": "Pending", "compliance": "Under Verification", "remarks": ""}

        base_signoffs = {
            "centre_head": {"name": None, "designation": None, "date": None, "confirmed": False},
            "cops_team": {"name": None, "designation": None, "date": None, "confirmed": False},
            "business_leader": {"name": None, "designation": None, "date": None, "confirmed": False},
            "review_stages": {
                "ch": {"status": "Pending"},
                "cops": {"status": "Pending"},
                "bl": {"status": "Pending"},
                "ceo": {"status": "Pending"},
            }
        }

        new_audit_payload = {
            "candidate_id": candidate_id,
            "candidate_snapshot": snapshot,
            "employer_details": emp_details,
            "salary_details": sal_details,
            "document_audit": base_doc_audit,
            "signoff_details": base_signoffs,
            "remarks": None,
            "audit_status": "DRAFT",
            "cpass_status": "PENDING",
            "created_by": user.id if user else None,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        ins_res = supabase.table("placement_audits").insert(new_audit_payload).execute()
        audit_rec = ins_res.data[0] if ins_res.data else new_audit_payload
    else:
        audit_rec = audit_res.data[0]

    # 2. Fetch all active candidate documents
    docs_res = (
        supabase.table("candidate_documents")
        .select("*")
        .eq("candidate_id", candidate_id)
        .neq("upload_status", "FAILED")
        .execute()
    )
    active_docs = docs_res.data or []
    valid_docs = [d for d in active_docs if d.get("drive_file_id") or d.get("upload_status") == "SUCCESS"]

    # 3. Synchronize document audit
    cur_doc_audit = dict(audit_rec.get("document_audit") or {})
    sal_list = list(override_salary_details if override_salary_details is not None else (audit_rec.get("salary_details") or []))
    emp_entries = list(override_employer_details if override_employer_details is not None else (audit_rec.get("employer_details") or []))

    def get_canonical_emp_id(val):
        if not val:
            return ""
        s = str(val).strip()
        if emp_entries:
            if len(emp_entries) <= 1:
                return str(emp_entries[0].get("id") or "1")
            norm = s.lower().replace("emp_", "").replace("employer_", "").strip()
            if norm.isdigit():
                idx = int(norm) - 1
                if 0 <= idx < len(emp_entries):
                    return str(emp_entries[idx].get("id") or str(idx + 1))
            for emp in emp_entries:
                e_id = str(emp.get("id") or "").strip()
                if e_id and (e_id == s or e_id.lower().replace("emp_", "") == norm):
                    return e_id
        return s

    def emp_matches(doc_emp, target_emp):
        if not doc_emp or not target_emp:
            return True
        if len(emp_entries) <= 1:
            return True
        return get_canonical_emp_id(doc_emp) == get_canonical_emp_id(target_emp)

    # If salary_details in DB has default dummy values and uploaded documents have specific months, align them
    uploaded_salary_docs = [d for d in valid_docs if d.get("document_type") == "SALARY_SLIP" and d.get("reporting_month") and d.get("reporting_year")]
    if override_salary_details is None and (not sal_list or (len(sal_list) == 3 and all(s.get("gross_salary") is None for s in sal_list))) and uploaded_salary_docs:
        sorted_sal_docs = sorted(uploaded_salary_docs, key=lambda d: (d.get("reporting_year", 0), d.get("reporting_month", 0)))
        new_sals = []
        for idx, sdoc in enumerate(sorted_sal_docs):
            new_sals.append({
                "id": f"sal_{idx + 1}",
                "employer_id": sdoc.get("employer_id") or "emp_1",
                "month": int(sdoc["reporting_month"]),
                "year": int(sdoc["reporting_year"]),
                "working_days": 26,
                "pay_days": 26,
                "leave_days": 0,
                "credit_date": None,
                "amount_credited": None,
                "gross_salary": None,
                "deductions": None,
                "net_salary": None,
                "bank_name": None,
            })
        if len(new_sals) >= 3:
            sal_list = new_sals
        elif new_sals:
            sal_list = new_sals
            while len(sal_list) < 3:
                last_m = sal_list[-1]["month"]
                last_y = sal_list[-1]["year"]
                next_m = last_m + 1
                next_y = last_y
                if next_m > 12:
                    next_m = 1
                    next_y += 1
                sal_list.append({
                    "id": f"sal_{len(sal_list) + 1}",
                    "employer_id": sal_list[-1]["employer_id"],
                    "month": next_m,
                    "year": next_y,
                    "working_days": 26,
                    "pay_days": 26,
                    "leave_days": 0,
                    "credit_date": None,
                    "amount_credited": None,
                    "gross_salary": None,
                    "deductions": None,
                    "net_salary": None,
                    "bank_name": None,
                })

    # APPOINTMENT_LETTER
    appt_docs = [d for d in valid_docs if d.get("document_type") == "APPOINTMENT_LETTER"]
    if appt_docs:
        latest_appt = appt_docs[-1]
        row = cur_doc_audit.get("appointment_letter") or {}
        row["available"] = "Yes"
        row["compliance"] = row.get("compliance") or "Compliant"
        row["file_name"] = latest_appt.get("file_name")
        row["drive_file_id"] = latest_appt.get("drive_file_id")
        row["document_id"] = latest_appt.get("id")
        cur_doc_audit["appointment_letter"] = row
    else:
        row = cur_doc_audit.get("appointment_letter") or {}
        if row.get("available") != "No":
            row["available"] = "Pending"
        cur_doc_audit["appointment_letter"] = row

    # OTHER_DOCUMENT
    other_docs = [d for d in valid_docs if d.get("document_type") == "OTHER_DOCUMENT"]
    if other_docs:
        latest_other = other_docs[-1]
        row = cur_doc_audit.get("other_document") or {}
        row["available"] = "Yes"
        row["title"] = latest_other.get("document_title") or row.get("title") or "Other Document"
        row["file_name"] = latest_other.get("file_name")
        row["drive_file_id"] = latest_other.get("drive_file_id")
        row["document_id"] = latest_other.get("id")
        cur_doc_audit["other_document"] = row
    else:
        row = cur_doc_audit.get("other_document") or {}
        if row.get("available") != "No":
            row["available"] = "Pending"
        cur_doc_audit["other_document"] = row

    # SALARY_SLIPS
    for s_idx, s_entry in enumerate(sal_list):
        slot_key = f"salary_slip_{s_idx + 1}"
        s_m = int(s_entry.get("month") or 0)
        s_y = int(s_entry.get("year") or 0)
        s_emp = s_entry.get("employer_id")

        matched_slip = next(
            (
                d for d in valid_docs
                if d.get("document_type") == "SALARY_SLIP"
                and int(d.get("reporting_month") or 0) == s_m
                and int(d.get("reporting_year") or 0) == s_y
                and emp_matches(d.get("employer_id"), s_emp)
            ),
            None
        )

        s_row = cur_doc_audit.get(slot_key) or {}
        s_row["month"] = s_m
        s_row["year"] = s_y
        if matched_slip:
            s_row["available"] = "Yes"
            s_row["file_name"] = matched_slip.get("file_name")
            s_row["drive_file_id"] = matched_slip.get("drive_file_id")
            s_row["document_id"] = matched_slip.get("id")
            s_row["compliance"] = s_row.get("compliance") or "Under Verification"
            if s_row.get("remarks") == "Payslip not available":
                s_row["remarks"] = ""
        else:
            if s_row.get("available") == "No":
                s_row["available"] = "No"
                s_row["remarks"] = s_row.get("remarks") or "Payslip not available"
                s_row["compliance"] = "Non-Compliant"
            else:
                s_row["available"] = "Pending"
                s_row["compliance"] = s_row.get("compliance") or "Under Verification"
        cur_doc_audit[slot_key] = s_row

    # BANK_STATEMENTS
    for s_idx, s_entry in enumerate(sal_list):
        slot_key = f"bank_statement_{s_idx + 1}"
        s_m = int(s_entry.get("month") or 0)
        s_y = int(s_entry.get("year") or 0)
        s_emp = s_entry.get("employer_id")

        # 1. Check individual bank statement
        matched_bank = next(
            (
                d for d in valid_docs
                if d.get("document_type") == "BANK_STATEMENT"
                and not d.get("is_consolidated")
                and int(d.get("reporting_month") or 0) == s_m
                and int(d.get("reporting_year") or 0) == s_y
                and emp_matches(d.get("employer_id"), s_emp)
            ),
            None
        )

        # 2. Check consolidated bank statement
        if not matched_bank:
            for d in valid_docs:
                if d.get("document_type") == "BANK_STATEMENT" and d.get("is_consolidated") and emp_matches(d.get("employer_id"), s_emp):
                    cov = d.get("covered_months") or []
                    if cov and isinstance(cov, list):
                        if any(int(c.get("month", 0)) == s_m and (not c.get("year") or int(c.get("year", 0)) == s_y) for c in cov if isinstance(c, dict)):
                            matched_bank = d
                            break
                    else:
                        st_m = int(d.get("coverage_start_month") or 0)
                        st_y = int(d.get("coverage_start_year") or 0)
                        end_m = int(d.get("coverage_end_month") or 0)
                        end_y = int(d.get("coverage_end_year") or 0)
                        if st_m and st_y and end_m and end_y:
                            if (st_y * 12 + st_m) <= (s_y * 12 + s_m) <= (end_y * 12 + end_m):
                                matched_bank = d
                                break

        b_row = cur_doc_audit.get(slot_key) or {}
        b_row["month"] = s_m
        b_row["year"] = s_y
        if matched_bank:
            b_row["available"] = "Yes"
            b_row["file_name"] = matched_bank.get("file_name")
            b_row["drive_file_id"] = matched_bank.get("drive_file_id")
            b_row["document_id"] = matched_bank.get("id")
            b_row["is_consolidated"] = bool(matched_bank.get("is_consolidated"))
            if matched_bank.get("is_consolidated"):
                b_row["coverage_start_month"] = matched_bank.get("coverage_start_month")
                b_row["coverage_end_month"] = matched_bank.get("coverage_end_month")
                b_row["coverage_start_year"] = matched_bank.get("coverage_start_year")
                b_row["coverage_end_year"] = matched_bank.get("coverage_end_year")
                b_row["covered_months"] = matched_bank.get("covered_months")
            b_row["compliance"] = b_row.get("compliance") or "Under Verification"
        else:
            if b_row.get("available") == "No":
                b_row["available"] = "No"
                b_row["compliance"] = "Non-Compliant"
            else:
                b_row["available"] = "Pending"
                b_row["compliance"] = b_row.get("compliance") or "Under Verification"
        cur_doc_audit[slot_key] = b_row

    # 4. Save updated document_audit & salary_details to placement_audits
    update_data = {
        "document_audit": cur_doc_audit,
        "salary_details": sal_list,
        "updated_at": now_iso,
    }
    if override_employer_details is not None:
        update_data["employer_details"] = emp_entries
    up_res = supabase.table("placement_audits").update(update_data).eq("id", audit_rec["id"]).execute()
    result_audit = up_res.data[0] if up_res.data else {**audit_rec, **update_data}
    return {
        "status": "success",
        "audit_id": audit_rec.get("id"),
        "candidate_id": candidate_id,
        "synced_documents_count": len(valid_docs),
        "audit": result_audit,
    }
'''

# We want to insert sync_func right before `@router.post("/submit")`
target_insert = '@router.post("/submit")'
if target_insert not in content:
    raise ValueError(f"Could not find {target_insert} in {file_path}")

content = content.replace(target_insert, sync_func + "\n\n" + target_insert)

# Now update batch_submit_documents signature to accept optional employer/salary details:
old_sig = '''@router.post("/submit")
async def batch_submit_documents(
    candidate_id: int,
    appointment_letter: UploadFile | None = File(None),
    appointment_replace_id: str | None = Form(None),
    appointment_employer_id: str | None = Form(None),
    appointment_letters: list[UploadFile] = File(default=[]),
    appointment_letters_meta: str = Form("[]"),
    salary_slips: list[UploadFile] = File(default=[]),
    salary_slips_meta: str = Form("[]"),
    bank_statements: list[UploadFile] = File(default=[]),
    bank_statements_meta: str = Form("[]"),
    other_document: UploadFile | None = File(None),
    other_document_title: str | None = Form(None),
    other_document_replace_id: str | None = Form(None),
    allow_partial: bool = Form(False),
    user: CurrentUser = Depends(require_roles("L1_COORDINATOR")),
):'''

new_sig = '''@router.post("/submit")
async def batch_submit_documents(
    candidate_id: int,
    appointment_letter: UploadFile | None = File(None),
    appointment_replace_id: str | None = Form(None),
    appointment_employer_id: str | None = Form(None),
    appointment_letters: list[UploadFile] = File(default=[]),
    appointment_letters_meta: str = Form("[]"),
    salary_slips: list[UploadFile] = File(default=[]),
    salary_slips_meta: str = Form("[]"),
    bank_statements: list[UploadFile] = File(default=[]),
    bank_statements_meta: str = Form("[]"),
    other_document: UploadFile | None = File(None),
    other_document_title: str | None = Form(None),
    other_document_replace_id: str | None = Form(None),
    employer_details_meta: str | None = Form(None),
    salary_details_meta: str | None = Form(None),
    allow_partial: bool = Form(False),
    user: CurrentUser = Depends(require_roles("L1_COORDINATOR")),
):'''

if old_sig not in content:
    raise ValueError("Could not find old_sig in content")
content = content.replace(old_sig, new_sig)

# Now replace step 10 in batch_submit_documents:
# From `# 10. Synchronize placement audit document availability if audit exists`
# to `return {`
old_step_10_start = '    # 10. Synchronize placement audit document availability if audit exists'
old_step_10_end = '    # 11. Return updated summary\n    summary = get_documents_summary(candidate_id, user)\n    return {\n        "status": "success",\n        "message": f"Successfully submitted {len(staged_uploads)} documents for placement verification.",\n        "candidate_id": candidate_id,\n        "submitted_count": len(staged_uploads),\n        "cleanup_warnings": cleanup_warnings,\n        "summary": summary,\n        "documents": [op["payload"] for op in db_operations],\n    }'

# Let's see what is between old_step_10_start and old_step_10_end in content
idx_start = content.find(old_step_10_start)
idx_end = content.find(old_step_10_end)

if idx_start == -1 or idx_end == -1:
    raise ValueError(f"Could not locate step 10 block: start={idx_start}, end={idx_end}")

new_step_10 = '''    # 10. Synchronize placement audit document availability
    parsed_override_emps = None
    if employer_details_meta:
        try:
            parsed_override_emps = json.loads(employer_details_meta)
        except Exception:
            pass
    parsed_override_sals = None
    if salary_details_meta:
        try:
            parsed_override_sals = json.loads(salary_details_meta)
        except Exception:
            pass

    audit_sync_status = "SUCCESS"
    audit_sync_message = "Placement audit document evidence synchronized successfully."
    synced_audit = None
    try:
        sync_res = sync_documents_to_placement_audit(
            candidate_id=candidate_id,
            user=user,
            override_employer_details=parsed_override_emps,
            override_salary_details=parsed_override_sals,
        )
        synced_audit = sync_res.get("audit")
        audit_sync_status = "SUCCESS"
    except Exception as audit_sync_err:
        audit_sync_status = "WARNING"
        audit_sync_message = f"Document evidence synchronization failed: {audit_sync_err}. Files remain safe in Google Drive and can be synchronized via retry."
        logger.exception("Could not synchronize placement audit document state for candidate %s: %s", candidate_id, audit_sync_err)

    # 11. Return updated summary
    summary = get_documents_summary(candidate_id, user)
    return {
        "status": "success",
        "message": f"Successfully submitted {len(staged_uploads)} documents for placement verification.",
        "candidate_id": candidate_id,
        "submitted_count": len(staged_uploads),
        "cleanup_warnings": cleanup_warnings,
        "audit_sync_status": audit_sync_status,
        "audit_sync_message": audit_sync_message,
        "audit": synced_audit,
        "summary": summary,
        "documents": [op["payload"] for op in db_operations],
    }'''

content = content[:idx_start] + new_step_10 + content[idx_end + len(old_step_10_end):]

# Add sync-audit endpoint at the bottom of documents.py
sync_endpoint = '''

@router.post("/sync-audit")
def sync_documents_audit_endpoint(
    candidate_id: int,
    user: CurrentUser = Depends(require_roles("L1_COORDINATOR", "L2_MANAGER", "L3_COPS", "ADMIN")),
):
    """Explicitly synchronize candidate documents into placement audit document evidence."""
    return sync_documents_to_placement_audit(candidate_id, user)
'''

content = content + sync_endpoint

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Successfully patched backend/app/routers/documents.py")

