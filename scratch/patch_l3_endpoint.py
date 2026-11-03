path = 'frontend/src/components/UnifiedReviewDashboard.jsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

target = """      } else if (level === 'L3') {
        endpoint = `/candidates/${sel.cand}/audit/l3-review/return-to-l1`
        bodyPayload = { return_reason: reason, remarks: remarks || undefined }"""

target_crlf = target.replace('\n', '\r\n')

replacement = """      } else if (level === 'L3') {
        endpoint = `/candidates/${sel.cand}/audit/l3-review/return`
        bodyPayload = { destination: destination || 'L1', return_reason: reason, remarks: remarks || undefined }"""

replacement_crlf = replacement.replace('\n', '\r\n')

if target_crlf in content:
    content = content.replace(target_crlf, replacement_crlf)
    print("Found CRLF match, replaced!")
elif target in content:
    content = content.replace(target, replacement)
    print("Found LF match, replaced!")
else:
    print("Target not found!")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

