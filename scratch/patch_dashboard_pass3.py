# -*- coding: utf-8 -*-
with open('frontend/src/components/UnifiedReviewDashboard.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update handleDecisionSubmit to always treat decision as Reject & Return with destination
old_decision = """  const handleDecisionSubmit = async ({ action, destination, reason, remarks }) => {
    if (!sel.cand) return
    setActionProcessing(true)
    try {
      if (action === 'RETURN') {
        let endpoint = ''
        let bodyPayload = {}

        if (level === 'L2') {
          endpoint = `/candidates/${sel.cand}/audit/l2-review/return-to-l1`
          bodyPayload = { return_reason: reason, remarks: remarks || undefined }
        } else if (level === 'L3') {
          endpoint = `/candidates/${sel.cand}/audit/l3-review/return-to-l1`
          bodyPayload = { return_reason: reason, remarks: remarks || undefined }
        } else if (level === 'L4') {
          endpoint = `/candidates/${sel.cand}/audit/l4-review/return`
          bodyPayload = { destination: destination || 'L3', return_reason: reason, remarks: remarks || undefined }
        } else if (level === 'L5') {
          endpoint = `/candidates/${sel.cand}/audit/l5-review/return`
          bodyPayload = { destination: destination || 'L4', return_reason: reason, remarks: remarks || undefined }
        }

        const res = await api(endpoint, null, {
          method: 'POST',
          body: JSON.stringify(bodyPayload),
        })

        showToast(res?.message || `Dossier successfully returned to Level ${destination || 'L1'}.`, 'success')
      } else {
        // Permanent Rejection
        let endpoint = ''
        if (level === 'L2') endpoint = `/candidates/${sel.cand}/audit/l2-review/reject`
        else if (level === 'L3') endpoint = `/candidates/${sel.cand}/audit/l3-review/reject`
        else if (level === 'L4') endpoint = `/candidates/${sel.cand}/audit/l4-review/reject`
        else if (level === 'L5') endpoint = `/candidates/${sel.cand}/audit/l5-review/reject`

        const res = await api(endpoint, null, {
          method: 'POST',
          body: JSON.stringify({
            rejection_reason: reason,
            remarks: remarks || undefined,
          }),
        })

        showToast(res?.message || `Placement dossier permanently rejected at ${config.roleLabel} stage.`, 'warning')
      }"""

new_decision = """  const handleDecisionSubmit = async ({ action, destination, reason, remarks }) => {
    if (!sel.cand) return
    setActionProcessing(true)
    try {
      let endpoint = ''
      let bodyPayload = {}

      if (level === 'L2') {
        endpoint = `/candidates/${sel.cand}/audit/l2-review/return-to-l1`
        bodyPayload = { return_reason: reason, remarks: remarks || undefined }
      } else if (level === 'L3') {
        endpoint = `/candidates/${sel.cand}/audit/l3-review/return-to-l1`
        bodyPayload = { return_reason: reason, remarks: remarks || undefined }
      } else if (level === 'L4') {
        endpoint = `/candidates/${sel.cand}/audit/l4-review/return`
        bodyPayload = { destination: destination || 'L3', return_reason: reason, remarks: remarks || undefined }
      } else if (level === 'L5') {
        endpoint = `/candidates/${sel.cand}/audit/l5-review/return`
        bodyPayload = { destination: destination || 'L4', return_reason: reason, remarks: remarks || undefined }
      }

      const res = await api(endpoint, null, {
        method: 'POST',
        body: JSON.stringify(bodyPayload),
      })

      showToast(res?.message || `Candidate dossier rejected and sent back to Level ${destination || 'L1'} for corrections.`, 'warning')"""

if old_decision.replace('\n', '\r\n') in content:
    content = content.replace(old_decision.replace('\n', '\r\n'), new_decision.replace('\n', '\r\n'))
else:
    content = content.replace(old_decision, new_decision)

# 2. Appointment Doc Card: add uploader badge, date, remarks, and replace button
old_app_card = """                            <div className="l2-doc-actions">
                              <button
                                type="button"
                                className="l2-btn-preview"
                                onClick={() => handlePreviewDocument(doc)}
                              >
                                <span>👁</span> Preview
                              </button>
                            </div>"""

new_app_card = """                            <div className="l2-doc-actions">
                              <button
                                type="button"
                                className="l2-btn-preview"
                                onClick={() => handlePreviewDocument(doc)}
                              >
                                <span>👁</span> Preview
                              </button>
                              {level === 'L2' && !isFinalApproved && (
                                <button
                                  type="button"
                                  className="l2-btn-replace"
                                  onClick={() => handleOpenUploadModal(doc.document_type, doc)}
                                  title="Upload a corrected replacement document"
                                >
                                  <span>🔄</span> Replace
                                </button>
                              )}
                            </div>"""

# Replace all occurrences of doc-actions preview with replace button
if old_app_card.replace('\n', '\r\n') in content:
    content = content.replace(old_app_card.replace('\n', '\r\n'), new_app_card.replace('\n', '\r\n'))
else:
    content = content.replace(old_app_card, new_app_card)

# 3. Appointment Card Meta
old_app_meta = """                              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', marginTop: '2px' }}>
                                <span className="l2-doc-sub">Appointment / Offer Letter • Verified in Drive</span>
                                {doc.employer_id && getEmployerName(doc.employer_id) && (
                                  <span className="l1-emp-badge">🏢 {getEmployerName(doc.employer_id)}</span>
                                )}
                              </div>"""

new_app_meta = """                              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', marginTop: '2px' }}>
                                <span className="l2-doc-sub">Appointment / Offer Letter • Verified in Drive</span>
                                {doc.employer_id && getEmployerName(doc.employer_id) && (
                                  <span className="l1-emp-badge">🏢 {getEmployerName(doc.employer_id)}</span>
                                )}
                                {doc.created_at && (
                                  <span style={{ fontSize: '11px', color: '#64748b' }}>
                                    📅 {new Date(doc.created_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                                  </span>
                                )}
                              </div>
                              {doc.remarks && (
                                <div style={{ marginTop: '4px', fontSize: '11.5px', color: '#334155', background: '#f1f5f9', borderLeft: '3px solid #0284c7', padding: '2px 8px', borderRadius: '3px' }}>
                                  <strong>Note:</strong> {doc.remarks}
                                </div>
                              )}"""

if old_app_meta.replace('\n', '\r\n') in content:
    content = content.replace(old_app_meta.replace('\n', '\r\n'), new_app_meta.replace('\n', '\r\n'))
else:
    content = content.replace(old_app_meta, new_app_meta)

# 4. Salary Card Meta
old_sal_meta = """                              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', marginTop: '2px' }}>
                                <span className="l2-doc-sub">
                                  {doc.reporting_month
                                    ? `Month ${empSeq} — ${MONTH_NAMES[doc.reporting_month - 1] || doc.reporting_month} ${doc.reporting_year || ''}`
                                    : `Month ${empSeq}`} • Verified in Drive
                                </span>
                                {doc.employer_id && getEmployerName(doc.employer_id) && (
                                  <span className="l1-emp-badge">🏢 {getEmployerName(doc.employer_id)}</span>
                                )}
                              </div>"""

new_sal_meta = """                              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', marginTop: '2px' }}>
                                <span className="l2-doc-sub">
                                  {doc.reporting_month
                                    ? `Month ${empSeq} — ${MONTH_NAMES[doc.reporting_month - 1] || doc.reporting_month} ${doc.reporting_year || ''}`
                                    : `Month ${empSeq}`} • Verified in Drive
                                </span>
                                {doc.employer_id && getEmployerName(doc.employer_id) && (
                                  <span className="l1-emp-badge">🏢 {getEmployerName(doc.employer_id)}</span>
                                )}
                                {doc.created_at && (
                                  <span style={{ fontSize: '11px', color: '#64748b' }}>
                                    📅 {new Date(doc.created_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                                  </span>
                                )}
                              </div>
                              {doc.remarks && (
                                <div style={{ marginTop: '4px', fontSize: '11.5px', color: '#334155', background: '#f1f5f9', borderLeft: '3px solid #0284c7', padding: '2px 8px', borderRadius: '3px' }}>
                                  <strong>Note:</strong> {doc.remarks}
                                </div>
                              )}"""

if old_sal_meta.replace('\n', '\r\n') in content:
    content = content.replace(old_sal_meta.replace('\n', '\r\n'), new_sal_meta.replace('\n', '\r\n'))
else:
    content = content.replace(old_sal_meta, new_sal_meta)

# 5. Bank Card Meta
old_bank_meta = """                              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', marginTop: '2px' }}>
                                {doc.is_consolidated ? (
                                  <span className="l1-coverage-badge">
                                    📅 Consolidated: {MONTH_NAMES[(doc.coverage_start_month || 1) - 1]} {doc.coverage_start_year} – {MONTH_NAMES[(doc.coverage_end_month || 1) - 1]} {doc.coverage_end_year}
                                  </span>
                                ) : (
                                  <span className="l2-doc-sub">
                                    {doc.reporting_month
                                      ? `${MONTH_NAMES[doc.reporting_month - 1] || doc.reporting_month} ${doc.reporting_year || ''}`
                                      : `Month ${idx + 1}`} • Verified in Drive
                                  </span>
                                )}
                                {doc.employer_id && getEmployerName(doc.employer_id) && (
                                  <span className="l1-emp-badge">🏢 {getEmployerName(doc.employer_id)}</span>
                                )}
                              </div>"""

new_bank_meta = """                              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', marginTop: '2px' }}>
                                {doc.is_consolidated ? (
                                  <span className="l1-coverage-badge">
                                    📅 Consolidated: {MONTH_NAMES[(doc.coverage_start_month || 1) - 1]} {doc.coverage_start_year} – {MONTH_NAMES[(doc.coverage_end_month || 1) - 1]} {doc.coverage_end_year}
                                  </span>
                                ) : (
                                  <span className="l2-doc-sub">
                                    {doc.reporting_month
                                      ? `${MONTH_NAMES[doc.reporting_month - 1] || doc.reporting_month} ${doc.reporting_year || ''}`
                                      : `Month ${idx + 1}`} • Verified in Drive
                                  </span>
                                )}
                                {doc.employer_id && getEmployerName(doc.employer_id) && (
                                  <span className="l1-emp-badge">🏢 {getEmployerName(doc.employer_id)}</span>
                                )}
                                {doc.created_at && (
                                  <span style={{ fontSize: '11px', color: '#64748b' }}>
                                    📅 {new Date(doc.created_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                                  </span>
                                )}
                              </div>
                              {doc.remarks && (
                                <div style={{ marginTop: '4px', fontSize: '11.5px', color: '#334155', background: '#f1f5f9', borderLeft: '3px solid #0284c7', padding: '2px 8px', borderRadius: '3px' }}>
                                  <strong>Note:</strong> {doc.remarks}
                                </div>
                              )}"""

if old_bank_meta.replace('\n', '\r\n') in content:
    content = content.replace(old_bank_meta.replace('\n', '\r\n'), new_bank_meta.replace('\n', '\r\n'))
else:
    content = content.replace(old_bank_meta, new_bank_meta)

with open('frontend/src/components/UnifiedReviewDashboard.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("Pass 3 completed successfully")

