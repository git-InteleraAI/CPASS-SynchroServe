endpoint = '''

@router.post("/sync-documents")
def sync_candidate_audit_documents(
    candidate_id: int,
    user: CurrentUser = Depends(require_roles("L1_COORDINATOR", "L2_MANAGER", "L3_COPS", "ADMIN")),
):
    """Synchronize uploaded candidate documents into placement audit evidence."""
    from .documents import sync_documents_to_placement_audit
    return sync_documents_to_placement_audit(candidate_id, user)
'''

with open("backend/app/routers/audits.py", "r", encoding="utf-8") as f:
    c = f.read()

if "/sync-documents" not in c:
    c = c.rstrip() + "\n" + endpoint
    with open("backend/app/routers/audits.py", "w", encoding="utf-8") as f:
        f.write(c)
    print("Added /sync-documents to audits.py")
else:
    print("/sync-documents already present in audits.py")

