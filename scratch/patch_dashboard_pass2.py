# -*- coding: utf-8 -*-
with open('frontend/src/components/UnifiedReviewDashboard.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update Candidate table row stages to use formatStageStatus
old_ch = "{cand.ch_status || 'Pending'}"
new_ch = "{formatStageStatus(cand.ch_status)}"
content = content.replace(old_ch, new_ch)

old_cops = "{cand.cops_status || 'Pending'}"
new_cops = "{formatStageStatus(cand.cops_status)}"
content = content.replace(old_cops, new_cops)

old_bl = "{cand.bl_status || 'Pending'}"
new_bl = "{formatStageStatus(cand.bl_status)}"
content = content.replace(old_bl, new_bl)

# 2. Panel Header: add "+ Upload Missing Document" button
old_panel_hdr = """                ) : (
                  <span style={{ fontSize: '12px', color: '#64748b' }}>
                    {documents.length} File{documents.length === 1 ? '' : 's'} Uploaded
                  </span>
                )}"""

new_panel_hdr = """                ) : (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span style={{ fontSize: '12px', color: '#64748b' }}>
                      {documents.length} File{documents.length === 1 ? '' : 's'} Uploaded
                    </span>
                    {level === 'L2' && !isFinalApproved && (
                      <button
                        type="button"
                        className="l2-btn-header-upload"
                        onClick={() => handleOpenUploadModal()}
                        style={{
                          background: '#0284c7',
                          color: '#ffffff',
                          border: 'none',
                          padding: '4px 12px',
                          borderRadius: '6px',
                          fontSize: '12px',
                          fontWeight: 600,
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '5px',
                        }}
                      >
                        <span>+</span> Upload Missing Document
                      </button>
                    )}
                  </div>
                )}"""

if old_panel_hdr.replace('\n', '\r\n') in content:
    content = content.replace(old_panel_hdr.replace('\n', '\r\n'), new_panel_hdr.replace('\n', '\r\n'))
else:
    content = content.replace(old_panel_hdr, new_panel_hdr)

# 3. Missing Appointment Card
old_missing_app = """                    ) : (
                      <div className="l2-doc-card" style={{ background: '#fef2f2', borderColor: '#fca5a5' }}>
                        <span style={{ fontSize: '13px', color: '#991b1b', fontWeight: 600 }}>
                          ✕ Missing Appointment / Offer Letter
                        </span>
                      </div>
                    )}"""

new_missing_app = """                    ) : (
                      <div className="l2-doc-card" style={{ background: '#fef2f2', borderColor: '#fca5a5', display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px' }}>
                        <span style={{ fontSize: '13px', color: '#991b1b', fontWeight: 600 }}>
                          ✕ Missing Appointment / Offer Letter
                        </span>
                        {level === 'L2' && !isFinalApproved && (
                          <button
                            type="button"
                            className="l2-btn-inline-upload"
                            onClick={() => handleOpenUploadModal('APPOINTMENT_LETTER')}
                          >
                            + Upload Appointment Letter
                          </button>
                        )}
                      </div>
                    )}"""

if old_missing_app.replace('\n', '\r\n') in content:
    content = content.replace(old_missing_app.replace('\n', '\r\n'), new_missing_app.replace('\n', '\r\n'))
else:
    content = content.replace(old_missing_app, new_missing_app)

# 4. Salary Slips missing block
old_missing_sal = """                    {salaryDocs.length === 0 && (
                      <div className="l2-doc-card" style={{ background: '#fef2f2', borderColor: '#fca5a5' }}>
                        <span style={{ fontSize: '13px', color: '#991b1b', fontWeight: 600 }}>
                          ✕ No Salary Slips uploaded
                        </span>
                      </div>
                    )}"""

new_missing_sal = """                    {salaryDocs.length < 3 && (
                      <div className="l2-doc-card" style={{ background: '#fef2f2', borderColor: '#fca5a5', display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 12px', marginTop: salaryDocs.length > 0 ? '8px' : 0 }}>
                        <span style={{ fontSize: '12.5px', color: '#991b1b', fontWeight: 600 }}>
                          ✕ {salaryDocs.length === 0 ? 'No Salary Slips uploaded (Min 3 required)' : `Only ${salaryDocs.length} of 3 required Salary Slips uploaded`}
                        </span>
                        {level === 'L2' && !isFinalApproved && (
                          <button
                            type="button"
                            className="l2-btn-inline-upload"
                            onClick={() => handleOpenUploadModal('SALARY_SLIP')}
                          >
                            + Upload Salary Slip
                          </button>
                        )}
                      </div>
                    )}"""

if old_missing_sal.replace('\n', '\r\n') in content:
    content = content.replace(old_missing_sal.replace('\n', '\r\n'), new_missing_sal.replace('\n', '\r\n'))
else:
    content = content.replace(old_missing_sal, new_missing_sal)

# 5. Bank Statements missing block
old_missing_bank = """                    {bankDocs.length === 0 && (
                      <div className="l2-doc-card" style={{ background: '#fef2f2', borderColor: '#fca5a5' }}>
                        <span style={{ fontSize: '13px', color: '#991b1b', fontWeight: 600 }}>
                          ✕ No Bank Statements uploaded
                        </span>
                      </div>
                    )}"""

new_missing_bank = """                    {(bankDocs.length === 0 || (!hasConsolidatedBank && bankDocs.length < 3)) && (
                      <div className="l2-doc-card" style={{ background: '#fef2f2', borderColor: '#fca5a5', display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 12px', marginTop: bankDocs.length > 0 ? '8px' : 0 }}>
                        <span style={{ fontSize: '12.5px', color: '#991b1b', fontWeight: 600 }}>
                          ✕ {bankDocs.length === 0 ? 'No Bank Statements uploaded (Min 3 months required)' : `Only ${bankDocs.length} of 3 required Bank Statement months uploaded`}
                        </span>
                        {level === 'L2' && !isFinalApproved && (
                          <button
                            type="button"
                            className="l2-btn-inline-upload"
                            onClick={() => handleOpenUploadModal('BANK_STATEMENT')}
                          >
                            + Upload Bank Statement
                          </button>
                        )}
                      </div>
                    )}"""

if old_missing_bank.replace('\n', '\r\n') in content:
    content = content.replace(old_missing_bank.replace('\n', '\r\n'), new_missing_bank.replace('\n', '\r\n'))
else:
    content = content.replace(old_missing_bank, new_missing_bank)

# 6. Supporting / Other Docs header
old_other_hdr = """                    {/* Supporting / Other Documents Section */}
                    {otherDocs.length > 0 && (
                      <>
                        <div className="l2-evidence-category-header">
                          <span>4. Supporting / Other Documents ({otherDocs.length})</span>
                        </div>"""

new_other_hdr = """                    {/* Supporting / Other Documents Section */}
                    <div className="l2-evidence-category-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span>4. Supporting / Other Documents ({otherDocs.length})</span>
                      {level === 'L2' && !isFinalApproved && (
                        <button
                          type="button"
                          className="l2-btn-inline-upload"
                          style={{ padding: '2px 8px', fontSize: '11px' }}
                          onClick={() => handleOpenUploadModal('OTHER_DOCUMENT')}
                        >
                          + Upload Supporting Doc
                        </button>
                      )}
                    </div>
                    {otherDocs.length > 0 && (
                      <>"""

if old_other_hdr.replace('\n', '\r\n') in content:
    content = content.replace(old_other_hdr.replace('\n', '\r\n'), new_other_hdr.replace('\n', '\r\n'))
else:
    content = content.replace(old_other_hdr, new_other_hdr)

# 7. Add L2DocumentUploadModal before </ErrorBoundary>
old_end = """        {toast && (
          <div className={`l1-audit-toast ${toast.type || ''}`} role="status">
            <span>{toast.type === 'success' ? '✓' : toast.type === 'error' ? '⚠️' : 'ℹ️'}</span>
            <span>{toast.message}</span>
          </div>
        )}
      </div>
    </ErrorBoundary>"""

new_end = """        {/* L2 Missing Document Upload Modal */}
        <L2DocumentUploadModal
          isOpen={uploadModalOpen}
          onClose={() => setUploadModalOpen(false)}
          candidateId={sel.cand}
          candidateName={candDetail ? `${candDetail.first_name || ''} ${candDetail.last_name || ''}`.trim() : ''}
          defaultDocType={uploadModalDocType}
          replaceDoc={uploadModalReplaceDoc}
          employersList={employersList}
          onSuccess={handleUploadSuccess}
        />

        {toast && (
          <div className={`l1-audit-toast ${toast.type || ''}`} role="status">
            <span>{toast.type === 'success' ? '✓' : toast.type === 'error' ? '⚠️' : 'ℹ️'}</span>
            <span>{toast.message}</span>
          </div>
        )}
      </div>
    </ErrorBoundary>"""

if old_end.replace('\n', '\r\n') in content:
    content = content.replace(old_end.replace('\n', '\r\n'), new_end.replace('\n', '\r\n'))
else:
    content = content.replace(old_end, new_end)

with open('frontend/src/components/UnifiedReviewDashboard.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("Pass 2 completed successfully")

