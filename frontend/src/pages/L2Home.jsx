import { useEffect, useRef, useState } from 'react'
import { api, downloadDocument, fetchDocumentBlob } from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import PlacementAuditStatement from '../components/PlacementAuditStatement'
import ErrorBoundary from '../components/ErrorBoundary'
import './L2Home.css'

const RESET = {
  state: ['tc', 'order', 'batch', 'cand'],
  tc: ['order', 'batch', 'cand'],
  order: ['batch', 'cand'],
  batch: ['cand'],
  cand: [],
}

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
]

export default function L2Home() {
  const { profile } = useAuth()

  // Cascading Selector States
  const [lists, setLists] = useState({
    state: [],
    tc: [],
    order: [],
    batch: [],
    cand: [],
  })
  const [sel, setSel] = useState({
    state: '',
    tc: '',
    order: '',
    batch: '',
    cand: '',
  })

  // Selected Candidate Data States
  const [candDetail, setCandDetail] = useState(null)
  const [statementData, setStatementData] = useState(null)
  const [documents, setDocuments] = useState([])
  const [loadingCandidate, setLoadingCandidate] = useState(false)
  const [candidateError, setCandidateError] = useState(null)

  // Document Verification Checklist State (doc_id -> { reviewed: boolean, reviewed_at: string, ... })
  const [docReviews, setDocReviews] = useState({})
  const [updatingChecklist, setUpdatingChecklist] = useState(false)

  // Document Preview State
  const [previewDoc, setPreviewDoc] = useState(null)
  const [previewBlobUrl, setPreviewBlobUrl] = useState(null)
  const [loadingPreview, setLoadingPreview] = useState(false)
  const [previewError, setPreviewError] = useState(null)

  // Edit Mode & Form States
  const [isEditMode, setIsEditMode] = useState(false)
  const [editedData, setEditedData] = useState({
    employer_details: [],
    salary_details: [],
    signoff_details: {},
    remarks: '',
  })
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)
  const [savingCorrections, setSavingCorrections] = useState(false)

  // Modal Dialogs
  const [revertModalOpen, setRevertModalOpen] = useState(false)
  const [approveModalOpen, setApproveModalOpen] = useState(false)
  const [approveRemarks, setApproveRemarks] = useState('')
  const [approving, setApproving] = useState(false)
  const [pendingCandSwitch, setPendingCandSwitch] = useState(null)
  const [switchConfirmModalOpen, setSwitchConfirmModalOpen] = useState(false)

  // Toast Notification
  const [toast, setToast] = useState(null)
  const showToast = (message, type = 'info') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 4000)
  }

  // Request race-condition prevention counter
  const loadSequenceRef = useRef(0)

  // ---------------------------------------------------------------------------
  // 1. Cascading Lookups Loading
  // ---------------------------------------------------------------------------
  useEffect(() => {
    api('/lookups/states')
      .then((states) => setLists((l) => ({ ...l, state: states })))
      .catch((err) => showToast(err.message || 'Failed to load states', 'error'))
  }, [])

  const resetBelow = (level) => {
    const keys = RESET[level] || []
    setSel((s) => {
      const next = { ...s }
      keys.forEach((k) => (next[k] = ''))
      return next
    })
    setLists((l) => {
      const next = { ...l }
      keys.forEach((k) => (next[k] = []))
      return next
    })
  }

  const handleSelectState = (e) => {
    const val = e.target.value
    resetBelow('state')
    setSel((s) => ({ ...s, state: val }))
    if (!val) return
    api('/lookups/centres', { state: val })
      .then((centres) => setLists((l) => ({ ...l, tc: centres })))
      .catch((err) => showToast(err.message || 'Failed to load centres', 'error'))
  }

  const handleSelectTc = (e) => {
    const val = e.target.value ? parseInt(e.target.value, 10) : ''
    resetBelow('tc')
    setSel((s) => ({ ...s, tc: val }))
    if (!val) return
    api('/lookups/sanction-orders', { tc_id: val })
      .then((orders) => setLists((l) => ({ ...l, order: orders })))
      .catch((err) => showToast(err.message || 'Failed to load sanction orders', 'error'))
  }

  const handleSelectOrder = (e) => {
    const val = e.target.value
    resetBelow('order')
    setSel((s) => ({ ...s, order: val }))
    if (!val || !sel.tc) return
    api('/lookups/batches', { tc_id: sel.tc, sanction_order: val })
      .then((batches) => setLists((l) => ({ ...l, batch: batches })))
      .catch((err) => showToast(err.message || 'Failed to load batches', 'error'))
  }

  const handleSelectBatch = (e) => {
    const val = e.target.value ? parseInt(e.target.value, 10) : ''
    resetBelow('batch')
    setSel((s) => ({ ...s, batch: val }))
    if (!val) return
    api('/lookups/candidates', { kb_batch_id: val })
      .then((cands) => setLists((l) => ({ ...l, cand: cands })))
      .catch((err) => showToast(err.message || 'Failed to load candidates', 'error'))
  }

  // ---------------------------------------------------------------------------
  // 2. Candidate Selection & Switching
  // ---------------------------------------------------------------------------
  const handleSelectCandidate = (e) => {
    const val = e.target.value ? parseInt(e.target.value, 10) : ''
    if (hasUnsavedChanges) {
      setPendingCandSwitch(val)
      setSwitchConfirmModalOpen(true)
      return
    }
    executeCandidateSwitch(val)
  }

  const executeCandidateSwitch = (candId) => {
    setSel((s) => ({ ...s, cand: candId }))
    setHasUnsavedChanges(false)
    setIsEditMode(false)
    setPendingCandSwitch(null)
    setSwitchConfirmModalOpen(false)

    // Cleanup previous preview
    if (previewBlobUrl) {
      window.URL.revokeObjectURL(previewBlobUrl)
      setPreviewBlobUrl(null)
    }
    setPreviewDoc(null)

    if (!candId) {
      setCandDetail(null)
      setStatementData(null)
      setDocuments([])
      setDocReviews({})
      return
    }

    loadCandidateData(candId)
  }

  const loadCandidateData = async (candId) => {
    const seq = ++loadSequenceRef.current
    setLoadingCandidate(true)
    setCandidateError(null)

    try {
      const [candRes, stmtRes, docsRes] = await Promise.all([
        api(`/lookups/candidates/${candId}`),
        api(`/candidates/${candId}/audit/statement`),
        api(`/candidates/${candId}/documents`),
      ])

      // Avoid race conditions if user changed candidate while requests were in flight
      if (seq !== loadSequenceRef.current) return

      setCandDetail(candRes)
      setStatementData(stmtRes)
      setDocuments(docsRes || [])

      // Initialize persistent checklist reviews
      const savedReviews = stmtRes.l2_document_reviews || stmtRes.document_audit?.l2_document_reviews || {}
      setDocReviews(savedReviews)

      // Initialize edit form data
      setEditedData({
        employer_details: JSON.parse(JSON.stringify(stmtRes.employer_details || [])),
        salary_details: JSON.parse(JSON.stringify(stmtRes.salary_details || [])),
        signoff_details: JSON.parse(JSON.stringify(stmtRes.signoff_details || {})),
        remarks: stmtRes.remarks || '',
      })
      setHasUnsavedChanges(false)
    } catch (err) {
      if (seq !== loadSequenceRef.current) return
      setCandidateError(err.message || 'Failed to load candidate audit data.')
      showToast(err.message || 'Failed to load candidate audit data.', 'error')
    } finally {
      if (seq === loadSequenceRef.current) {
        setLoadingCandidate(false)
      }
    }
  }

  // ---------------------------------------------------------------------------
  // 3. Document Preview Mechanism
  // ---------------------------------------------------------------------------
  const handlePreviewDocument = async (doc) => {
    if (previewDoc?.id === doc.id) return

    if (previewBlobUrl) {
      window.URL.revokeObjectURL(previewBlobUrl)
      setPreviewBlobUrl(null)
    }

    setPreviewDoc(doc)
    setLoadingPreview(true)
    setPreviewError(null)

    try {
      const blob = await fetchDocumentBlob(sel.cand, doc.id)
      const url = window.URL.createObjectURL(blob)
      setPreviewBlobUrl(url)
    } catch (err) {
      setPreviewError(err.message || 'Failed to load document preview.')
      showToast(err.message || 'Failed to load document preview.', 'error')
    } finally {
      setLoadingPreview(false)
    }
  }

  const handleClosePreview = () => {
    if (previewBlobUrl) {
      window.URL.revokeObjectURL(previewBlobUrl)
      setPreviewBlobUrl(null)
    }
    setPreviewDoc(null)
    setPreviewError(null)
  }

  // Clean up object URL on unmount
  useEffect(() => {
    return () => {
      if (previewBlobUrl) {
        window.URL.revokeObjectURL(previewBlobUrl)
      }
    }
  }, [previewBlobUrl])

  // ---------------------------------------------------------------------------
  // 4. Document Verification Checklist Persistence
  // ---------------------------------------------------------------------------
  const handleToggleDocReview = async (docId, checked) => {
    const updated = {
      ...docReviews,
      [docId]: {
        reviewed: checked,
        reviewed_at: new Date().toISOString(),
        reviewed_by: profile?.full_name || 'Centre Manager',
      },
    }
    setDocReviews(updated)

    try {
      setUpdatingChecklist(true)
      await api(`/candidates/${sel.cand}/audit/l2-review/checklist`, null, {
        method: 'POST',
        body: JSON.stringify({
          reviewed_documents: { [docId]: checked },
        }),
      })
      showToast(checked ? 'Document marked as verified.' : 'Document review unset.', 'info')
    } catch (err) {
      showToast(err.message || 'Failed to save review status.', 'error')
    } finally {
      setUpdatingChecklist(false)
    }
  }

  // ---------------------------------------------------------------------------
  // 5. Shared Statement Editing Operations
  // ---------------------------------------------------------------------------
  const handleUpdateEmployer = (idOrIdx, field, value) => {
    setEditedData((prev) => {
      const list = [...prev.employer_details]
      const idx = typeof idOrIdx === 'number' ? idOrIdx : list.findIndex((e) => e.id === idOrIdx)
      if (idx >= 0) {
        list[idx] = { ...list[idx], [field]: value }
      }
      return { ...prev, employer_details: list }
    })
    setHasUnsavedChanges(true)
  }

  const handleAddEmployer = () => {
    if (editedData.employer_details.length >= 5) return
    setEditedData((prev) => ({
      ...prev,
      employer_details: [
        ...prev.employer_details,
        {
          employer_name: '',
          months_worked: '',
          appointment_date: '',
          designation: '',
          place_of_work: '',
          monthly_ctc: '',
          minimum_wages: '',
        },
      ],
    }))
    setHasUnsavedChanges(true)
  }

  const handleRemoveEmployer = (idOrIdx) => {
    setEditedData((prev) => {
      const list = [...prev.employer_details]
      const idx = typeof idOrIdx === 'number' ? idOrIdx : list.findIndex((e) => e.id === idOrIdx)
      if (idx >= 0 && list.length > 1) {
        list.splice(idx, 1)
      }
      return { ...prev, employer_details: list }
    })
    setHasUnsavedChanges(true)
  }

  const handleUpdateSalary = (idOrIdx, field, value) => {
    setEditedData((prev) => {
      const list = [...prev.salary_details]
      const idx = typeof idOrIdx === 'number' ? idOrIdx : list.findIndex((s) => s.id === idOrIdx)
      if (idx >= 0) {
        list[idx] = { ...list[idx], [field]: value }
      }
      return { ...prev, salary_details: list }
    })
    setHasUnsavedChanges(true)
  }

  const handleAddSalary = () => {
    if (editedData.salary_details.length >= 12) return
    const nextMonth = ((editedData.salary_details[editedData.salary_details.length - 1]?.month || 1) % 12) + 1
    const year = editedData.salary_details[editedData.salary_details.length - 1]?.year || 2026
    setEditedData((prev) => ({
      ...prev,
      salary_details: [
        ...prev.salary_details,
        {
          month: nextMonth,
          year: year,
          working_days: 26,
          pay_days: 26,
          leave_days: 0,
          credit_date: '',
          gross_salary: '',
          deductions: '',
          net_salary: '',
          amount_credited: '',
          bank_name: '',
        },
      ],
    }))
    setHasUnsavedChanges(true)
  }

  const handleRemoveSalary = (idOrIdx) => {
    setEditedData((prev) => {
      const list = [...prev.salary_details]
      const idx = typeof idOrIdx === 'number' ? idOrIdx : list.findIndex((s) => s.id === idOrIdx)
      if (idx >= 0 && list.length > 3) {
        list.splice(idx, 1)
      }
      return { ...prev, salary_details: list }
    })
    setHasUnsavedChanges(true)
  }

  const handleUpdateRemarks = (val) => {
    setEditedData((prev) => ({ ...prev, remarks: val }))
    setHasUnsavedChanges(true)
  }

  // Save L2 Corrections
  const handleSaveCorrections = async () => {
    if (!sel.cand) return
    setSavingCorrections(true)
    try {
      const res = await api(`/candidates/${sel.cand}/audit/l2-review/corrections`, null, {
        method: 'POST',
        body: JSON.stringify({
          employer_details: editedData.employer_details,
          salary_details: editedData.salary_details,
          remarks: editedData.remarks,
          correction_notes: 'L2 Center Manager data entry revisions',
        }),
      })
      showToast('L2 corrections saved successfully.', 'success')
      setHasUnsavedChanges(false)
      setIsEditMode(false)
      // Reload updated statement
      const updatedStmt = await api(`/candidates/${sel.cand}/audit/statement`)
      setStatementData(updatedStmt)
    } catch (err) {
      showToast(err.message || 'Failed to save corrections.', 'error')
    } finally {
      setSavingCorrections(false)
    }
  }

  // Revert Unsaved Edits
  const handleConfirmRevert = () => {
    if (statementData) {
      setEditedData({
        employer_details: JSON.parse(JSON.stringify(statementData.employer_details || [])),
        salary_details: JSON.parse(JSON.stringify(statementData.salary_details || [])),
        signoff_details: JSON.parse(JSON.stringify(statementData.signoff_details || {})),
        remarks: statementData.remarks || '',
      })
    }
    setHasUnsavedChanges(false)
    setIsEditMode(false)
    setRevertModalOpen(false)
    showToast('Unsaved edits discarded.', 'info')
  }

  // ---------------------------------------------------------------------------
  // 6. L2 Approval Workflow
  // ---------------------------------------------------------------------------
  const handleApprove = async () => {
    if (!sel.cand) return
    setApproving(true)
    try {
      const payload = {
        remarks: approveRemarks || 'Dossier and physical records verified and approved by Centre Manager.',
      }
      if (hasUnsavedChanges) {
        payload.corrections = {
          employer_details: editedData.employer_details,
          salary_details: editedData.salary_details,
          remarks: editedData.remarks,
          correction_notes: 'L2 corrections saved during approval',
        }
      }

      const res = await api(`/candidates/${sel.cand}/audit/l2-review/approve`, null, {
        method: 'POST',
        body: JSON.stringify(payload),
      })

      showToast('Placement Audit Statement approved successfully!', 'success')
      setApproveModalOpen(false)
      setHasUnsavedChanges(false)
      setIsEditMode(false)

      // Reload updated statement
      const updatedStmt = await api(`/candidates/${sel.cand}/audit/statement`)
      setStatementData(updatedStmt)
    } catch (err) {
      showToast(err.message || 'Approval failed.', 'error')
    } finally {
      setApproving(false)
    }
  }

  // ---------------------------------------------------------------------------
  // 7. Checklist & Approval Readiness Calculations
  // ---------------------------------------------------------------------------
  const successDocs = documents.filter((d) => d.upload_status === 'SUCCESS')
  const appointmentDoc = successDocs.find((d) => d.document_type === 'APPOINTMENT_LETTER')
  const salaryDocs = successDocs.filter((d) => d.document_type === 'SALARY_SLIP')
  const bankDocs = successDocs.filter((d) => d.document_type === 'BANK_STATEMENT')

  const isAppointmentReviewed = appointmentDoc && docReviews[String(appointmentDoc.id)]?.reviewed
  const reviewedSalaryCount = salaryDocs.filter((d) => docReviews[String(d.id)]?.reviewed).length
  const reviewedBankCount = bankDocs.filter((d) => docReviews[String(d.id)]?.reviewed).length

  const allMandatoryReviewed =
    Boolean(appointmentDoc && isAppointmentReviewed) &&
    reviewedSalaryCount >= 3 &&
    reviewedBankCount >= 3

  const auditStatus = statementData?.audit_status || 'DRAFT'
  const cpassStatus = statementData?.cpass_status || 'PENDING'
  const isAlreadyApproved = cpassStatus === 'L2_APPROVED'
  const isL1Submitted = auditStatus === 'SUBMITTED'
  const hasActiveHold = Boolean(candDetail?.has_active_hold)

  const canApprove =
    isL1Submitted &&
    !isAlreadyApproved &&
    allMandatoryReviewed &&
    !hasActiveHold &&
    !loadingCandidate

  return (
    <ErrorBoundary>
      <div className="l2-dashboard">
        {/* Top Control Bar */}
        <header className="l2-topbar">
          <div className="l2-topbar-selectors">
            {/* State */}
            <div className="l2-select-group">
              <label>State</label>
              <select value={sel.state} onChange={handleSelectState}>
                <option value="">Select State</option>
                {lists.state.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>

            {/* Centre */}
            <div className="l2-select-group">
              <label>Training Centre</label>
              <select value={sel.tc} onChange={handleSelectTc} disabled={!sel.state}>
                <option value="">Select Centre</option>
                {lists.tc.map((c) => (
                  <option key={c.tc_id} value={c.tc_id}>{c.name}</option>
                ))}
              </select>
            </div>

            {/* Sanction Order */}
            <div className="l2-select-group">
              <label>Sanction Order</label>
              <select value={sel.order} onChange={handleSelectOrder} disabled={!sel.tc}>
                <option value="">Select Order</option>
                {lists.order.map((o) => (
                  <option key={o} value={o}>{o}</option>
                ))}
              </select>
            </div>

            {/* Batch */}
            <div className="l2-select-group">
              <label>Batch</label>
              <select value={sel.batch} onChange={handleSelectBatch} disabled={!sel.order}>
                <option value="">Select Batch</option>
                {lists.batch.map((b) => (
                  <option key={b.kb_batch_id} value={b.kb_batch_id}>{b.batch_code}</option>
                ))}
              </select>
            </div>

            {/* Candidate */}
            <div className="l2-select-group">
              <label>Candidate</label>
              <select value={sel.cand} onChange={handleSelectCandidate} disabled={!sel.batch}>
                <option value="">Select Candidate</option>
                {lists.cand.map((c) => (
                  <option key={c.candidate_id} value={c.candidate_id}>
                    {c.first_name} {c.last_name} ({c.candidate_id})
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="l2-topbar-meta">
            {sel.cand && statementData && (
              <>
                <span className={`l2-status-badge ${isL1Submitted ? 'submitted' : 'draft'}`}>
                  L1 Audit: {auditStatus}
                </span>
                <span className={`l2-status-badge ${isAlreadyApproved ? 'approved' : 'pending'}`}>
                  Review: {isAlreadyApproved ? '✓ L2 APPROVED' : 'Pending Review'}
                </span>
              </>
            )}
          </div>
        </header>

        {/* Workspace: 2-Panel Side-by-Side */}
        {!sel.cand ? (
          <div style={{ display: 'grid', placeItems: 'center', height: '60vh', color: '#64748b' }}>
            <div style={{ textAlign: 'center', maxWidth: 460 }}>
              <span style={{ fontSize: '44px', display: 'block', marginBottom: '12px' }}>🏢</span>
              <h3 style={{ margin: '0 0 8px', color: '#0f172a' }}>L2 Center Manager Dashboard</h3>
              <p style={{ margin: 0, fontSize: '14px', lineHeight: 1.5 }}>
                Select a state, training centre, batch, and candidate above to view the placement audit statement and verify associated document evidence side-by-side.
              </p>
            </div>
          </div>
        ) : loadingCandidate ? (
          <div style={{ display: 'grid', placeItems: 'center', height: '60vh', color: '#64748b' }}>
            <div style={{ textAlign: 'center' }}>
              <span style={{ fontSize: '32px', display: 'block', marginBottom: '10px' }}>⏳</span>
              <p style={{ margin: 0, fontSize: '15px', fontWeight: 600 }}>Loading Candidate Placement Dossier &amp; Documents…</p>
            </div>
          </div>
        ) : candidateError ? (
          <div style={{ margin: '30px auto', maxWidth: 600, padding: '24px', background: '#fee2e2', borderRadius: '8px', border: '1px solid #fca5a5' }}>
            <h4 style={{ margin: '0 0 8px', color: '#991b1b' }}>Failed to Load Candidate Audit</h4>
            <p style={{ margin: '0 0 14px', fontSize: '14px', color: '#7f1d1d' }}>{candidateError}</p>
            <button
              type="button"
              className="l2-btn-edit"
              onClick={() => loadCandidateData(sel.cand)}
            >
              🔄 Retry
            </button>
          </div>
        ) : (
          <main className="l2-workspace">
            {/* Left Panel: Shared Placement Audit Statement */}
            <section className="l2-panel" aria-label="Candidate Placement Statement">
              <div className="l2-panel-header l1-no-print">
                <h3 className="l2-panel-title">
                  <span>📄</span>
                  <span>Placement Audit Statement</span>
                  {isEditMode ? (
                    <span style={{ fontSize: '11px', background: '#f59e0b', color: '#fff', padding: '2px 8px', borderRadius: '4px' }}>
                      Editing
                    </span>
                  ) : (
                    <span style={{ fontSize: '11px', background: '#e2e8f0', color: '#475569', padding: '2px 8px', borderRadius: '4px' }}>
                      Read-Only
                    </span>
                  )}
                  {hasUnsavedChanges && (
                    <span style={{ fontSize: '11px', background: '#dc2626', color: '#fff', padding: '2px 8px', borderRadius: '4px' }}>
                      Unsaved Changes
                    </span>
                  )}
                </h3>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    type="button"
                    className="l1-btn-secondary"
                    onClick={() => window.print()}
                    style={{ padding: '5px 12px', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '4px' }}
                    title="Print or export as PDF"
                  >
                    <span>🖨️</span> Print / PDF
                  </button>
                </div>
              </div>

              <div className="l2-panel-body">
                <PlacementAuditStatement
                  statementData={statementData}
                  isEditMode={isEditMode}
                  editedData={editedData}
                  onUpdateEmployer={handleUpdateEmployer}
                  onAddEmployer={handleAddEmployer}
                  onRemoveEmployer={handleRemoveEmployer}
                  onUpdateSalary={handleUpdateSalary}
                  onAddSalary={handleAddSalary}
                  onRemoveSalary={handleRemoveSalary}
                  onUpdateRemarks={handleUpdateRemarks}
                  l1OriginalData={statementData?.l1_original_submission || statementData?.audit?.signoff_details?.l1_original_submission}
                  hasUnsavedChanges={hasUnsavedChanges}
                  showModalWrapper={false}
                />
              </div>
            </section>

            {/* Right Panel: Candidate Documents & Inline Previewer */}
            <section className="l2-panel l2-doc-panel" aria-label="Candidate Document Evidence">
              <div className="l2-panel-header">
                <h3 className="l2-panel-title">
                  <span>📁</span>
                  <span>
                    {previewDoc ? `Preview: ${previewDoc.file_name}` : 'Document Verification Evidence'}
                  </span>
                </h3>
                {previewDoc ? (
                  <button
                    type="button"
                    className="l1-btn-secondary"
                    onClick={handleClosePreview}
                    style={{ padding: '4px 10px', fontSize: '12px' }}
                  >
                    ✕ Back to Document List
                  </button>
                ) : (
                  <span style={{ fontSize: '12px', color: '#64748b' }}>
                    {documents.length} File{documents.length === 1 ? '' : 's'} Uploaded
                  </span>
                )}
              </div>

              <div className="l2-panel-body" style={{ padding: previewDoc ? 0 : '16px' }}>
                {previewDoc ? (
                  /* Inline Document Viewer */
                  <div className="l2-viewer-container">
                    <div className="l2-viewer-toolbar l1-no-print">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <label className={`l2-review-checkbox-label ${docReviews[String(previewDoc.id)]?.reviewed ? 'reviewed' : 'pending'}`}>
                          <input
                            type="checkbox"
                            checked={Boolean(docReviews[String(previewDoc.id)]?.reviewed)}
                            onChange={(e) => handleToggleDocReview(previewDoc.id, e.target.checked)}
                          />
                          <span>
                            {docReviews[String(previewDoc.id)]?.reviewed ? '✓ Verified by Manager' : 'Mark as Reviewed'}
                          </span>
                        </label>
                      </div>
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <button
                          type="button"
                          className="l2-btn-preview"
                          onClick={() => downloadDocument(sel.cand, previewDoc.id, previewDoc.file_name)}
                          title="Download original file"
                        >
                          ⬇ Download
                        </button>
                        <button
                          type="button"
                          className="l1-btn-secondary"
                          onClick={handleClosePreview}
                          style={{ padding: '4px 10px', fontSize: '12px' }}
                        >
                          ✕ Close
                        </button>
                      </div>
                    </div>

                    <div className="l2-viewer-content">
                      {loadingPreview ? (
                        <div style={{ color: '#fff', textAlign: 'center' }}>
                          <span style={{ fontSize: '28px', display: 'block', marginBottom: '8px' }}>⏳</span>
                          <p>Retrieving secure document stream from Google Drive…</p>
                        </div>
                      ) : previewError ? (
                        <div className="l2-viewer-fallback">
                          <p style={{ color: '#fca5a5', marginBottom: '12px' }}>{previewError}</p>
                          <button
                            type="button"
                            className="l2-btn-preview"
                            onClick={() => downloadDocument(sel.cand, previewDoc.id, previewDoc.file_name)}
                          >
                            Download Document Directly
                          </button>
                        </div>
                      ) : previewBlobUrl ? (
                        previewDoc.mime_type === 'application/pdf' || previewDoc.file_name?.toLowerCase().endsWith('.pdf') ? (
                          <iframe
                            src={previewBlobUrl}
                            title={previewDoc.file_name}
                            className="l2-viewer-iframe"
                          />
                        ) : (
                          <img
                            src={previewBlobUrl}
                            alt={previewDoc.file_name}
                            className="l2-viewer-img"
                          />
                        )
                      ) : (
                        <div className="l2-viewer-fallback">
                          <p>Preview format not supported in browser.</p>
                          <button
                            type="button"
                            className="l2-btn-preview"
                            onClick={() => downloadDocument(sel.cand, previewDoc.id, previewDoc.file_name)}
                          >
                            Download File
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  /* Documents List */
                  <div className="l2-doc-list">
                    {/* Appointment Letter Section */}
                    <div style={{ marginBottom: '8px' }}>
                      <span style={{ fontSize: '12px', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                        1. Appointment / Offer Letter
                      </span>
                    </div>

                    {appointmentDoc ? (
                      <div className="l2-doc-card">
                        <div className="l2-doc-card-top">
                          <span className="l2-doc-type-icon">✉</span>
                          <div className="l2-doc-meta">
                            <span className="l2-doc-name">{appointmentDoc.file_name}</span>
                            <span className="l2-doc-sub">Appointment / Offer Letter • Verified in Drive</span>
                          </div>
                          <div className="l2-doc-actions">
                            <button
                              type="button"
                              className="l2-btn-preview"
                              onClick={() => handlePreviewDocument(appointmentDoc)}
                            >
                              <span>👁</span> Preview
                            </button>
                          </div>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid #f1f5f9', paddingTop: '8px' }}>
                          <label className={`l2-review-checkbox-label ${docReviews[String(appointmentDoc.id)]?.reviewed ? 'reviewed' : 'pending'}`}>
                            <input
                              type="checkbox"
                              checked={Boolean(docReviews[String(appointmentDoc.id)]?.reviewed)}
                              onChange={(e) => handleToggleDocReview(appointmentDoc.id, e.target.checked)}
                            />
                            <span>{docReviews[String(appointmentDoc.id)]?.reviewed ? '✓ Verified by Manager' : 'Mark Reviewed'}</span>
                          </label>
                          {docReviews[String(appointmentDoc.id)]?.reviewed && (
                            <span style={{ fontSize: '11px', color: '#166534', fontWeight: 600 }}>
                              Reviewed on {new Date(docReviews[String(appointmentDoc.id)].reviewed_at).toLocaleDateString()}
                            </span>
                          )}
                        </div>
                      </div>
                    ) : (
                      <div className="l2-doc-card" style={{ background: '#fef2f2', borderColor: '#fca5a5' }}>
                        <span style={{ fontSize: '13px', color: '#991b1b', fontWeight: 600 }}>
                          ✕ Missing Appointment / Offer Letter
                        </span>
                      </div>
                    )}

                    {/* Salary Slips Section */}
                    <div style={{ marginTop: '14px', marginBottom: '8px' }}>
                      <span style={{ fontSize: '12px', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                        2. Monthly Salary Slips (Min 3 Required)
                      </span>
                    </div>

                    {salaryDocs.map((doc, idx) => (
                      <div key={doc.id} className="l2-doc-card">
                        <div className="l2-doc-card-top">
                          <span className="l2-doc-type-icon">₹</span>
                          <div className="l2-doc-meta">
                            <span className="l2-doc-name">{doc.file_name}</span>
                            <span className="l2-doc-sub">
                              {doc.reporting_month ? `${MONTH_NAMES[doc.reporting_month - 1] || doc.reporting_month} ${doc.reporting_year || ''}` : `Month ${idx + 1}`} • Verified in Drive
                            </span>
                          </div>
                          <div className="l2-doc-actions">
                            <button
                              type="button"
                              className="l2-btn-preview"
                              onClick={() => handlePreviewDocument(doc)}
                            >
                              <span>👁</span> Preview
                            </button>
                          </div>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid #f1f5f9', paddingTop: '8px' }}>
                          <label className={`l2-review-checkbox-label ${docReviews[String(doc.id)]?.reviewed ? 'reviewed' : 'pending'}`}>
                            <input
                              type="checkbox"
                              checked={Boolean(docReviews[String(doc.id)]?.reviewed)}
                              onChange={(e) => handleToggleDocReview(doc.id, e.target.checked)}
                            />
                            <span>{docReviews[String(doc.id)]?.reviewed ? '✓ Verified by Manager' : 'Mark Reviewed'}</span>
                          </label>
                          {docReviews[String(doc.id)]?.reviewed && (
                            <span style={{ fontSize: '11px', color: '#166534', fontWeight: 600 }}>
                              Reviewed on {new Date(docReviews[String(doc.id)].reviewed_at).toLocaleDateString()}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                    {salaryDocs.length === 0 && (
                      <div className="l2-doc-card" style={{ background: '#fef2f2', borderColor: '#fca5a5' }}>
                        <span style={{ fontSize: '13px', color: '#991b1b', fontWeight: 600 }}>
                          ✕ No Salary Slips uploaded
                        </span>
                      </div>
                    )}

                    {/* Bank Statements Section */}
                    <div style={{ marginTop: '14px', marginBottom: '8px' }}>
                      <span style={{ fontSize: '12px', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                        3. Bank Statements / Passbook (Min 3 Required)
                      </span>
                    </div>

                    {bankDocs.map((doc, idx) => (
                      <div key={doc.id} className="l2-doc-card">
                        <div className="l2-doc-card-top">
                          <span className="l2-doc-type-icon">▤</span>
                          <div className="l2-doc-meta">
                            <span className="l2-doc-name">{doc.file_name}</span>
                            <span className="l2-doc-sub">
                              {doc.reporting_month ? `${MONTH_NAMES[doc.reporting_month - 1] || doc.reporting_month} ${doc.reporting_year || ''}` : `Month ${idx + 1}`} • Verified in Drive
                            </span>
                          </div>
                          <div className="l2-doc-actions">
                            <button
                              type="button"
                              className="l2-btn-preview"
                              onClick={() => handlePreviewDocument(doc)}
                            >
                              <span>👁</span> Preview
                            </button>
                          </div>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid #f1f5f9', paddingTop: '8px' }}>
                          <label className={`l2-review-checkbox-label ${docReviews[String(doc.id)]?.reviewed ? 'reviewed' : 'pending'}`}>
                            <input
                              type="checkbox"
                              checked={Boolean(docReviews[String(doc.id)]?.reviewed)}
                              onChange={(e) => handleToggleDocReview(doc.id, e.target.checked)}
                            />
                            <span>{docReviews[String(doc.id)]?.reviewed ? '✓ Verified by Manager' : 'Mark Reviewed'}</span>
                          </label>
                          {docReviews[String(doc.id)]?.reviewed && (
                            <span style={{ fontSize: '11px', color: '#166534', fontWeight: 600 }}>
                              Reviewed on {new Date(docReviews[String(doc.id)].reviewed_at).toLocaleDateString()}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                    {bankDocs.length === 0 && (
                      <div className="l2-doc-card" style={{ background: '#fef2f2', borderColor: '#fca5a5' }}>
                        <span style={{ fontSize: '13px', color: '#991b1b', fontWeight: 600 }}>
                          ✕ No Bank Statements uploaded
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </section>
          </main>
        )}

        {/* Fixed Bottom Review Controls */}
        {sel.cand && statementData && (
          <footer className="l2-bottom-dock l1-no-print">
            <div className="l2-dock-summary">
              <span className="l2-dock-title">
                {isAlreadyApproved ? (
                  <span style={{ color: '#166534' }}>✓ Placement Statement Approved by L2</span>
                ) : (
                  <span>L2 Center Manager Review</span>
                )}
                <span className={`l2-status-badge ${allMandatoryReviewed ? 'approved' : 'pending'}`} style={{ fontSize: '11px', padding: '2px 8px' }}>
                  Checklist: {(appointmentDoc && isAppointmentReviewed ? 1 : 0) + reviewedSalaryCount + reviewedBankCount} of 7 Reviewed
                </span>
              </span>
              <span className="l2-dock-sub">
                {isAlreadyApproved
                  ? 'Audit has been officially endorsed. Records are finalized.'
                  : !isL1Submitted
                  ? 'Waiting for L1 Coordinator to finalize and submit the placement statement.'
                  : !allMandatoryReviewed
                  ? 'Check and review all required documents on the right before approving.'
                  : hasActiveHold
                  ? 'Approval blocked: Candidate has an active administrative hold.'
                  : 'All mandatory checks satisfied. Ready for Centre Manager approval.'}
              </span>
            </div>

            <div className="l2-dock-buttons">
              {/* Edit Toggle */}
              {!isAlreadyApproved && (
                <button
                  type="button"
                  className="l2-btn-edit"
                  onClick={() => setIsEditMode(!isEditMode)}
                >
                  {isEditMode ? '✕ Cancel Edit' : '✏️ Edit Statement'}
                </button>
              )}

              {/* Revert Changes */}
              {hasUnsavedChanges && (
                <button
                  type="button"
                  className="l2-btn-revert"
                  onClick={() => setRevertModalOpen(true)}
                >
                  ↩ Revert Edits
                </button>
              )}

              {/* Save Changes */}
              {hasUnsavedChanges && (
                <button
                  type="button"
                  className="l2-btn-save"
                  onClick={handleSaveCorrections}
                  disabled={savingCorrections}
                >
                  💾 {savingCorrections ? 'Saving…' : 'Save Edits'}
                </button>
              )}

              {/* Approve Statement */}
              <button
                type="button"
                className="l2-btn-approve"
                disabled={!canApprove || approving}
                onClick={() => setApproveModalOpen(true)}
                title={
                  !isL1Submitted
                    ? 'Audit statement not yet submitted by L1'
                    : isAlreadyApproved
                    ? 'Statement is already approved'
                    : !allMandatoryReviewed
                    ? 'Review all mandatory documents first'
                    : 'Endorse and approve placement statement'
                }
              >
                {isAlreadyApproved ? '✓ Statement Approved' : '✓ Approve Placement Statement'}
              </button>
            </div>
          </footer>
        )}

        {/* Modal: Revert Confirmation */}
        {revertModalOpen && (
          <div className="l2-modal-overlay" role="dialog" aria-modal="true">
            <div className="l2-modal-card">
              <div className="l2-modal-header">
                <h4>Discard Unsaved Changes?</h4>
                <button type="button" onClick={() => setRevertModalOpen(false)}>✕</button>
              </div>
              <div className="l2-modal-body">
                <p>Are you sure you want to discard your edits and restore the last saved placement statement? Any unsaved modifications to employer or salary rows will be lost.</p>
              </div>
              <div className="l2-modal-footer">
                <button type="button" className="l1-btn-secondary" onClick={() => setRevertModalOpen(false)}>
                  Keep Editing
                </button>
                <button type="button" className="l2-btn-revert" onClick={handleConfirmRevert}>
                  Discard &amp; Revert
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Modal: Unsaved Changes Candidate Switch Warning */}
        {switchConfirmModalOpen && (
          <div className="l2-modal-overlay" role="dialog" aria-modal="true">
            <div className="l2-modal-card">
              <div className="l2-modal-header">
                <h4>Unsaved Changes Warning</h4>
                <button type="button" onClick={() => setSwitchConfirmModalOpen(false)}>✕</button>
              </div>
              <div className="l2-modal-body">
                <p>You have unsaved edits on the current placement statement. Switching to another candidate now will discard these edits.</p>
              </div>
              <div className="l2-modal-footer">
                <button type="button" className="l1-btn-secondary" onClick={() => setSwitchConfirmModalOpen(false)}>
                  Cancel &amp; Stay
                </button>
                <button
                  type="button"
                  className="l2-btn-revert"
                  onClick={() => executeCandidateSwitch(pendingCandSwitch)}
                >
                  Discard &amp; Switch
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Modal: L2 Approval Confirmation */}
        {approveModalOpen && (
          <div className="l2-modal-overlay" role="dialog" aria-modal="true">
            <div className="l2-modal-card" style={{ maxWidth: 540 }}>
              <div className="l2-modal-header">
                <h4>Endorse Placement Audit Approval</h4>
                <button type="button" onClick={() => setApproveModalOpen(false)}>✕</button>
              </div>
              <div className="l2-modal-body">
                <p style={{ margin: '0 0 12px' }}>
                  You are officially endorsing the placement audit for <strong>{candDetail?.first_name} {candDetail?.last_name}</strong> as <strong>Centre Manager</strong>.
                </p>
                <div style={{ background: '#f8fafc', padding: '10px 14px', borderRadius: '6px', fontSize: '13px', marginBottom: '14px' }}>
                  <div>✓ Appointment / Offer Letter verified</div>
                  <div>✓ Minimum 3 monthly salary pay slips verified</div>
                  <div>✓ Minimum 3 bank credit entries verified</div>
                  <div>✓ Placement employer &amp; salary details validated</div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <label style={{ fontSize: '12px', fontWeight: 600, color: '#475569' }}>
                    Approval Remarks &amp; Compliance Notes (Optional)
                  </label>
                  <textarea
                    rows={3}
                    placeholder="e.g. Dossier physically verified against employer payroll and bank statements. Approved."
                    value={approveRemarks}
                    onChange={(e) => setApproveRemarks(e.target.value)}
                    style={{ padding: '8px', border: '1px solid #cbd5e1', borderRadius: '6px', fontSize: '13px' }}
                  />
                </div>
              </div>
              <div className="l2-modal-footer">
                <button type="button" className="l1-btn-secondary" onClick={() => setApproveModalOpen(false)}>
                  Cancel
                </button>
                <button
                  type="button"
                  className="l2-btn-approve"
                  onClick={handleApprove}
                  disabled={approving}
                >
                  {approving ? 'Recording Approval…' : 'Confirm L2 Approval'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Toast Notification */}
        {toast && (
          <div className={`l1-audit-toast ${toast.type || ''}`} role="status">
            <span>{toast.type === 'success' ? '✓' : toast.type === 'error' ? '⚠️' : 'ℹ️'}</span>
            <span>{toast.message}</span>
          </div>
        )}
      </div>
    </ErrorBoundary>
  )
}
