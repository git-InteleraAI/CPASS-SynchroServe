with open("backend/app/routers/audits.py", "r", encoding="utf-8") as f:
    text = f.read()

text = text.replace('return {"message": "Draft audit saved successfully", "audit": record}', 'return {"status": "saved", "message": "Draft audit saved successfully", "audit": record}')
with open("backend/app/routers/audits.py", "w", encoding="utf-8") as f:
    f.write(text)

with open("backend/app/routers/documents.py", "r", encoding="utf-8") as f:
    d_text = f.read()

old_d_return = '''    return {
        "status": "success",
        "audit_id": audit_rec.get("id"),
        "candidate_id": candidate_id,
        "synced_documents_count": len(valid_docs),
        "audit": result_audit,
    }'''

new_d_return = '''    return {
        "status": "success",
        "audit_id": audit_rec.get("id"),
        "candidate_id": candidate_id,
        "synced_documents_count": len(valid_docs),
        "audit": result_audit,
        "document_audit": cur_doc_audit,
    }'''

d_text = d_text.replace(old_d_return, new_d_return)
with open("backend/app/routers/documents.py", "w", encoding="utf-8") as f:
    f.write(d_text)

print("Updated returns successfully!")

