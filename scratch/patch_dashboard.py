# -*- coding: utf-8 -*-
with open('frontend/src/components/UnifiedReviewDashboard.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Imports and formatStageStatus
old_import = "import FlexibleReturnModal from './FlexibleReturnModal'\nimport '../pages/L2Home.css'"
new_import = "import FlexibleReturnModal from './FlexibleReturnModal'\nimport L2DocumentUploadModal from './L2DocumentUploadModal'\nimport './L2DocumentUploadModal.css'\nimport '../pages/L2Home.css'"

content = content.replace(old_import, new_import)

old_badge_func = """function getStageBadgeClass(status) {
  const s = (status || '').toLowerCase()
  if (s === 'recommended') return 'l1-stage-badge recommended'
  if (s === 'verified') return 'l1-stage-badge verified'
  if (s === 'approved') return 'l1-stage-badge approved'
  if (s.includes('return')) return 'l1-stage-badge returned'
  if (s === 'rejected') return 'l1-stage-badge rejected'
  return 'l1-stage-badge pending'
}"""

new_badge_func = """function formatStageStatus(status) {
  if (!status) return 'Pending'
  const s = String(status).trim()
  if (s.toLowerCase().includes('return') || s.toLowerCase().includes('reject')) return 'Rejected'
  if (s.toLowerCase() === 'recommended') return 'Recommended'
  if (s.toLowerCase() === 'verified') return 'Verified'
  if (s.toLowerCase() === 'approved') return 'Approved'
  return s
}

function getStageBadgeClass(status) {
  const s = (status || '').toLowerCase()
  if (s === 'recommended') return 'l1-stage-badge recommended'
  if (s === 'verified') return 'l1-stage-badge verified'
  if (s === 'approved') return 'l1-stage-badge approved'
  if (s.includes('return') || s.includes('reject')) return 'l1-stage-badge rejected'
  return 'l1-stage-badge pending'
}"""

# Handle CRLF
if old_badge_func.replace('\n', '\r\n') in content:
    content = content.replace(old_badge_func.replace('\n', '\r\n'), new_badge_func.replace('\n', '\r\n'))
else:
    content = content.replace(old_badge_func, new_badge_func)

# 2. Metric card titles for L3, L4, L5: Rejected / Returned -> Rejected
content = content.replace("title: 'Rejected / Returned'", "title: 'Rejected'")

# 3. State variables for L2 upload modal
old_state_anchor = "  const [decisionModalOpen, setDecisionModalOpen] = useState(false)\n  const [actionProcessing, setActionProcessing] = useState(false)"
new_state_anchor = """  const [decisionModalOpen, setDecisionModalOpen] = useState(false)
  const [actionProcessing, setActionProcessing] = useState(false)

  // L2 Missing Document Upload Modal State
  const [uploadModalOpen, setUploadModalOpen] = useState(false)
  const [uploadModalDocType, setUploadModalDocType] = useState('APPOINTMENT_LETTER')
  const [uploadModalReplaceDoc, setUploadModalReplaceDoc] = useState(null)

  const handleOpenUploadModal = (docType = 'APPOINTMENT_LETTER', replaceDoc = null) => {
    setUploadModalDocType(docType)
    setUploadModalReplaceDoc(replaceDoc)
    setUploadModalOpen(true)
  }

  const handleUploadSuccess = (_newDoc) => {
    showToast(
      uploadModalReplaceDoc
        ? 'Document replacement uploaded successfully.'
        : 'Document uploaded successfully to Google Drive.',
      'success'
    )
    if (sel.cand) {
      loadCandidateData(sel.cand)
    }
  }"""

if old_state_anchor.replace('\n', '\r\n') in content:
    content = content.replace(old_state_anchor.replace('\n', '\r\n'), new_state_anchor.replace('\n', '\r\n'))
else:
    content = content.replace(old_state_anchor, new_state_anchor)

# 4. Dock button text
content = content.replace("↩ / ✕ Return / Reject Dossier", "↩ Reject & Send Back")

with open('frontend/src/components/UnifiedReviewDashboard.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("Pass 1 completed successfully")

