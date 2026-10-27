import { useEffect, useRef, useState, useCallback } from 'react'
import { api, downloadDocument, fetchDocumentBlob } from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import PlacementAuditStatement from '../components/PlacementAuditStatement'
import ErrorBoundary from '../components/ErrorBoundary'
import PdfViewer from '../components/PdfViewer'
import './L2Home.css'
import {
  MONTH_NAMES,
  calculateNextSalaryPeriodForEmployer,
  getEmployerDocumentSequence
} from '../lib/salarySequenceHelper'

const RESET = {
  state: ['tc', 'order', 'batch', 'cand'],
  tc: ['order', 'batch', 'cand'],
  order: ['batch', 'cand'],
  batch: ['cand'],
  cand: [],
}

function getStageBadgeClass(status) {
  const s = (status || '').toLowerCase()
  if (s === 'recommended') return 'l1-stage-badge recommended'
  if (s === 'verified') return 'l1-stage-badge verified'
  if (s === 'approved') return 'l1-stage-badge approved'
  if (s.includes('return')) return 'l1-stage-badge returned'
  if (s === 'rejected') return 'l1-stage-badge rejected'
  return 'l1-stage-badge pending'
}

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

  // L2 Dashboard Summary Metrics & Filtered Candidate List
  const [summaryData, setSummaryData] = useState(null)
  const [loadingSummary, setLoadingSummary] = useState(false)
  const [summaryError, setSummaryError] = useState('')
  const [activeCardFilter, setActiveCardFilter] = useState(null)
  const [cardCandidates, setCardCandidates] = useState([])
  const [cardCandLoading, setCardCandLoading] = useState(false)
  const [cardCandPage, setCardCandPage] = useState(1)
  const [cardCandTotal, setCardCandTotal] = useState(0)
  const [cardCandPages, setCardCandPages] = useState(1)
  const [cardCandSearch, setCardCandSearch] = useState('')
  const [cardCandError, setCardCandError] = useState('')

  // Reject & Return to L1 Workflow State
  const [returnModalOpen, setReturnModalOpen] = useState(false)
  const [returnReason, setReturnReason] = useState('')
  const [returnRemarks, setReturnRemarks] = useState('')
  const [returningToL1, setReturningToL1] = useState(false)

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

  const fetchDashboardSummary = useCallback((targetState) => {
    const s = targetState || sel.state
    if (!s) {
      setSummaryData(null)
      setSummaryError('')
      return
    }
    setLoadingSummary(true)
    setSummaryError('')
    api(`/dashboard/summary?state=${encodeURIComponent(s)}`)
      .then((data) => {
        setSummaryData(data)
        setSummaryError('')
      })
      .catch((err) => {
        console.warn('Failed to load L2 dashboard summary:', err)
        setSummaryError(err?.message || 'Failed to load dashboard summary metrics.')
      })
      .finally(() => {
        setLoadingSummary(false)
      })
  }, [sel.state])

  const fetchCardCandidates = useCallback((filterType, page = 1, search = '') => {
    if (!filterType) return
    const s = sel.state
    setCardCandLoading(true)
    setCardCandError('')
    let url = `/dashboard/candidates?filter=${encodeURIComponent(filterType)}&filter_type=${encodeURIComponent(filterType)}&page=${page}&page_size=20`
    if (s) {
      url += `&state=${encodeURIComponent(s)}`
    }
    if (search && search.trim()) {
      url += `&search=${encodeURIComponent(search.trim())}`
    }
    api(url)
      .then((res) => {
        setCardCandidates(res.candidates || [])
        setCardCandTotal(res.total_count || 0)
        setCardCandPages(res.total_pages || 1)
        setCardCandPage(res.page || 1)
      })
      .catch((err) => {
        console.warn('Failed to load card candidates:', err)
        setCardCandError(err.message || 'Could not load candidates')
        setCardCandidates([])
      })
      .finally(() => {
        setCardCandLoading(false)
      })
  }, [sel.state])

  function handleCardClick(filterKey) {
    if (activeCardFilter === filterKey) {
      setActiveCardFilter(null)
      setCardCandidates([])
    } else {
      setActiveCardFilter(filterKey)
      setCardCandPage(1)
      setCardCandSearch('')
      fetchCardCandidates(filterKey, 1, '')
    }
  }

  // Close candidate list popup or return modal on Escape key press
  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        if (activeCardFilter) {
          setActiveCardFilter(null)
          setCardCandidates([])
        }
        if (returnModalOpen) {
          setReturnModalOpen(false)
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [activeCardFilter, returnModalOpen])

  // ---------------------------------------------------------------------------
  // 1. Cascading Lookups Loading
  // ---------------------------------------------------------------------------
  useEffect(() => {
    api('/lookups/states')
      .then((states) => {
        setLists((l) => ({ ...l, state: states }))
        if (profile?.assigned_state && states.includes(profile.assigned_state)) {
          setSel((s) => s.state ? s : ({ ...s, state: profile.assigned_state }))
          fetchDashboardSummary(profile.assigned_state)
          api('/lookups/centres', { state: profile.assigned_state })
            .then((centres) => setLists((l) => ({ ...l, tc: centres })))
            .catch(() => {})
        }
      })
      .catch((err) => showToast(err.message || 'Failed to load states', 'error'))
  }, [profile?.assigned_state, fetchDashboardSummary])

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

  const handleResetSelection = () => {
    if (hasUnsavedChanges) {
      if (!window.confirm('You have unsaved review marks. Are you sure you want to reset selection?')) {
        return
      }
    }
    resetBelow('state')
    setSel({ state: '', tc: '', order: '', batch: '', cand: '' })
    setSummaryData(null)
    setActiveCardFilter(null)
    setCardCandidates([])
    setCandDetail(null)
    setStatementData(null)
    setDocuments([])
  }

  const handleSelectState = (e) => {
    const val = e.target.value
    resetBelow('state')
    setSel((s) => ({ ...s, state: val }))
    if (!val) {
      setSummaryData(null)
      setActiveCardFilter(null)
      setCardCandidates([])
      return
    }
    fetchDashboardSummary(val)
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

  const handleSelectCandidateFromList = (cand) => {
    if (!cand?.candidate_id) return
    const candId = cand.candidate_id
    if (hasUnsavedChanges) {
      setPendingCandSwitch(candId)
      setSwitchConfirmModalOpen(true)
      return
    }
    setActiveCardFilter(null)
    setCardCandidates([])

    const stateName = cand.state_name || sel.state

    // Update state and selections
    setSel((s) => ({
      ...s,
      state: stateName,
      tc: cand.tc_id || s.tc,
      order: cand.sanction_order_number || s.order,
      batch: cand.kb_batch_id || s.batch,
      cand: candId,
    }))

    // Load options for the cascade in background so dropdowns show current values
    if (cand.tc_id) {
      api('/lookups/centres', { state: stateName })
        .then((centres) => setLists((l) => ({ ...l, tc: centres })))
        .catch(() => {})
      api('/lookups/sanction-orders', { tc_id: cand.tc_id })
        .then((orders) => setLists((l) => ({ ...l, order: orders })))
        .catch(() => {})
      if (cand.sanction_order_number) {
        api('/lookups/batches', { tc_id: cand.tc_id, sanction_order: cand.sanction_order_number })
          .then((batches) => setLists((l) => ({ ...l, batch: batches })))
          .catch(() => {})
      }
      if (cand.kb_batch_id) {
        api('/lookups/candidates', { kb_batch_id: cand.kb_batch_id })
          .then((cands) => setLists((l) => ({ ...l, cand: cands })))
          .catch(() => {})
      }
    }

    executeCandidateSwitch(candId)
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

  const handleAddSalary = (targetEmpId = null) => {
    if (editedData.salary_details.length >= 12) return
    const empId = targetEmpId || editedData.salary_details[editedData.salary_details.length - 1]?.employer_id || editedData.employers?.[0]?.id || 'emp_1'
    const nextPeriod = calculateNextSalaryPeriodForEmployer(empId, editedData.salary_details, 2026)
    setEditedData((prev) => ({
      ...prev,
      salary_details: [
        ...prev.salary_details,
        {
          employer_id: empId,
          month: nextPeriod.month,
          year: nextPeriod.year,
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

      // Reload updated statement & refresh summary metrics
      const updatedStmt = await api(`/candidates/${sel.cand}/audit/statement`)
      setStatementData(updatedStmt)
      if (sel.state) fetchDashboardSummary(sel.state)
    } catch (err) {
      showToast(err.message || 'Approval failed.', 'error')
    } finally {
      setApproving(false)
    }
  }

  // ---------------------------------------------------------------------------
  // 7. L2 Reject & Return to L1 Workflow
  // ---------------------------------------------------------------------------
  const handleReturnToL1 = async () => {
    if (!sel.cand) return
    const reasonClean = (returnReason || '').trim()
    if (!reasonClean) {
      showToast('Please enter a reason for returning the candidate to L1.', 'error')
      return
    }
    setReturningToL1(true)
    try {
      await api(`/candidates/${sel.cand}/audit/l2-review/return-to-l1`, null, {
        method: 'POST',
        body: JSON.stringify({
          return_reason: reasonClean,
          remarks: (returnRemarks || '').trim() || undefined,
        }),
      })

      showToast('Candidate successfully returned to L1 coordinator for corrections.', 'success')
      setReturnModalOpen(false)
      setReturnReason('')
      setReturnRemarks('')
      setHasUnsavedChanges(false)
      setIsEditMode(false)

      // Reload updated candidate data & refresh dashboard cards
      await loadCandidateData(sel.cand)
      if (sel.state) fetchDashboardSummary(sel.state)
    } catch (err) {
      showToast(err.message || 'Failed to return candidate to L1.', 'error')
    } finally {
      setReturningToL1(false)
    }
  }

  // ---------------------------------------------------------------------------
  // 8. Checklist & Approval Readiness Calculations
  // ---------------------------------------------------------------------------
  const employersList = statementData?.employer_details || (statementData?.employer_name ? [{ id: 'emp_1', employer_name: statementData.employer_name }] : [])
  const getEmployerName = (empId) => {
    if (!empId) return null
    const emp = employersList.find((e) => e.id === empId)
    return emp?.employer_name || null
  }

  const successDocs = documents.filter((d) => d.upload_status === 'SUCCESS')
  const appointmentDocs = successDocs.filter((d) => d.document_type === 'APPOINTMENT_LETTER')
  const appointmentDoc = appointmentDocs[0]
  const salaryDocs = successDocs.filter((d) => d.document_type === 'SALARY_SLIP')
  const bankDocs = successDocs.filter((d) => d.document_type === 'BANK_STATEMENT')
  const otherDocs = successDocs.filter((d) => !['APPOINTMENT_LETTER', 'SALARY_SLIP', 'BANK_STATEMENT'].includes(d.document_type))

  const requiredAppointmentCount = Math.max(1, employersList.length)
  const reviewedAppointmentCount = appointmentDocs.filter((d) => docReviews[String(d.id)]?.reviewed).length
  const allAppointmentsReviewed = appointmentDocs.length >= requiredAppointmentCount && appointmentDocs.every((d) => docReviews[String(d.id)]?.reviewed)

  const reviewedSalaryCount = salaryDocs.filter((d) => docReviews[String(d.id)]?.reviewed).length
  const reviewedBankCount = bankDocs.filter((d) => docReviews[String(d.id)]?.reviewed).length

  // Consolidated bank statements count towards month coverage
  const hasConsolidatedBank = bankDocs.some((d) => d.is_consolidated)
  const allBankReviewed = bankDocs.length > 0 && bankDocs.every((d) => docReviews[String(d.id)]?.reviewed) && (bankDocs.length >= 3 || hasConsolidatedBank)

  const allMandatoryReviewed =
    allAppointmentsReviewed &&
    reviewedSalaryCount >= 3 &&
    allBankReviewed

  const auditStatus = statementData?.audit_status || 'DRAFT'
  const cpassStatus = statementData?.cpass_status || 'PENDING'
  const isAlreadyApproved = cpassStatus === 'L2_APPROVED' || cpassStatus === 'APPROVED'
  const isReturnedToL1 = auditStatus === 'RETURNED_TO_L1' || cpassStatus === 'RETURNED_TO_L1'
  const isL1Submitted = auditStatus === 'SUBMITTED'
  const hasActiveHold = Boolean(candDetail?.has_active_hold)

  const canApprove =
    isL1Submitted &&
    !isAlreadyApproved &&
    !isReturnedToL1 &&
    allMandatoryReviewed &&
    !hasActiveHold &&
    !loadingCandidate

  return (
    <ErrorBoundary>
      <div className="l2-dashboard">
        {/* Metrics Error Banner if summaryError */}
        {summaryError && (
          <div
            className="l1-banner-warning"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '12px',
              padding: '12px 18px',
              borderRadius: '10px',
              background: '#FEF3C7',
              color: '#92400E',
              border: '1px solid #FCD34D',
              fontSize: '13.5px',
            }}
            role="alert"
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '16px' }}>⚠️</span>
              <span>
                <strong>Dashboard Metrics Unavailable:</strong> {summaryError}
              </span>
            </div>
            <button
              type="button"
              className="l2-btn-secondary"
              style={{ padding: '5px 14px', fontSize: '13px', cursor: 'pointer', whiteSpace: 'nowrap' }}
              onClick={() => fetchDashboardSummary(sel.state)}
            >
              ↻ Retry Metrics
            </button>
          </div>
        )}

        {/* --------------------------------------------------------------------
             L2 CH Dashboard Summary Cards (Top of Dashboard)
             Cards Order: 1. Total, 2. Received, 3. Recommended, 4. Rejected, 5. Pending
             -------------------------------------------------------------------- */}
        <section className="l2-compact-summary-row" aria-label="CH Candidate Review Summary">
          {/* 1. Total */}
          <div
            className={`l2-compact-card total ${activeCardFilter === 'total' ? 'active' : ''}`}
            onClick={() => handleCardClick('total')}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && handleCardClick('total')}
            aria-label={`Total candidates: ${loadingSummary ? 'Loading' : summaryData ? summaryData.total : 'Unavailable'}. Click to view list.`}
          >
            <div className="l2-compact-card-meta">
              <span className="l2-compact-card-icon">👥</span>
              <span className="l2-compact-card-title">Total</span>
            </div>
            <div className="l2-compact-card-count">
              {loadingSummary ? '…' : summaryError ? '—' : (summaryData ? summaryData.total : '—')}
            </div>
          </div>

          {/* 2. Received */}
          <div
            className={`l2-compact-card received ${activeCardFilter === 'l2_received' ? 'active' : ''}`}
            onClick={() => handleCardClick('l2_received')}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && handleCardClick('l2_received')}
            aria-label={`Received candidates: ${loadingSummary ? 'Loading' : summaryData ? (summaryData.l2_received ?? summaryData.received) : 'Unavailable'}. Click to view list.`}
          >
            <div className="l2-compact-card-meta">
              <span className="l2-compact-card-icon">📥</span>
              <span className="l2-compact-card-title">Received</span>
            </div>
            <div className="l2-compact-card-count">
              {loadingSummary ? '…' : summaryError ? '—' : (summaryData ? (summaryData.l2_received ?? summaryData.received ?? 0) : '—')}
            </div>
          </div>

          {/* 3. Recommended */}
          <div
            className={`l2-compact-card recommended ${activeCardFilter === 'l2_recommended' ? 'active' : ''}`}
            onClick={() => handleCardClick('l2_recommended')}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && handleCardClick('l2_recommended')}
            aria-label={`Recommended candidates: ${loadingSummary ? 'Loading' : summaryData ? (summaryData.l2_recommended ?? summaryData.recommended) : 'Unavailable'}. Click to view list.`}
          >
            <div className="l2-compact-card-meta">
              <span className="l2-compact-card-icon">🌟</span>
              <span className="l2-compact-card-title">Recommended</span>
            </div>
            <div className="l2-compact-card-count">
              {loadingSummary ? '…' : summaryError ? '—' : (summaryData ? (summaryData.l2_recommended ?? summaryData.recommended ?? 0) : '—')}
            </div>
          </div>

          {/* 4. Rejected */}
          <div
            className={`l2-compact-card rejected ${activeCardFilter === 'l2_rejected' ? 'active' : ''}`}
            onClick={() => handleCardClick('l2_rejected')}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && handleCardClick('l2_rejected')}
            aria-label={`Rejected candidates: ${loadingSummary ? 'Loading' : summaryData ? (summaryData.l2_rejected ?? summaryData.ch_rejected) : 'Unavailable'}. Click to view list.`}
          >
            <div className="l2-compact-card-meta">
              <span className="l2-compact-card-icon">✕</span>
              <span className="l2-compact-card-title">Rejected</span>
            </div>
            <div className="l2-compact-card-count">
              {loadingSummary ? '…' : summaryError ? '—' : (summaryData ? (summaryData.l2_rejected ?? summaryData.ch_rejected ?? 0) : '—')}
            </div>
          </div>

          {/* 5. Pending (Formula: max(0, Received - Recommended - Rejected)) */}
          <div
            className={`l2-compact-card pending ${activeCardFilter === 'l2_pending' ? 'active' : ''}`}
            onClick={() => handleCardClick('l2_pending')}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && handleCardClick('l2_pending')}
            aria-label={`Pending candidates: ${loadingSummary ? 'Loading' : summaryData ? summaryData.l2_pending : 'Unavailable'}. Click to view list.`}
          >
            <div className="l2-compact-card-meta">
              <span className="l2-compact-card-icon">⏱</span>
              <span className="l2-compact-card-title">Pending</span>
            </div>
            <div className="l2-compact-card-count">
              {loadingSummary ? '…' : summaryError ? '—' : (summaryData ? summaryData.l2_pending : '—')}
            </div>
          </div>
        </section>

        {/* --------------------------------------------------------------------
             Candidate Selection Pipeline (Matching L1 Layout & Styling)
             -------------------------------------------------------------------- */}
        <section className="l2-selector-panel">
          <div className="l2-selector-header">
            <h3>
              <span className="l2-step-indicator">1</span>
              Candidate Selection Pipeline
            </h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
              {sel.cand && statementData && (
                <>
                  <span
                    className={`l2-status-badge ${isReturnedToL1 ? 'draft' : isL1Submitted ? 'submitted' : 'draft'}`}
                    style={isReturnedToL1 ? { background: '#fef3c7', color: '#92400e', borderColor: '#fcd34d' } : {}}
                  >
                    L1 Audit: {isReturnedToL1 ? 'RETURNED_TO_L1' : auditStatus}
                  </span>
                  <span
                    className={`l2-status-badge ${isReturnedToL1 ? 'draft' : isAlreadyApproved ? 'approved' : 'pending'}`}
                    style={isReturnedToL1 ? { background: '#fef3c7', color: '#92400e', borderColor: '#fcd34d' } : {}}
                  >
                    Review: {isAlreadyApproved ? '✓ L2 APPROVED' : isReturnedToL1 ? '↩ RETURNED TO L1' : 'Pending Review'}
                  </span>
                </>
              )}
              {sel.state && (
                <button
                  type="button"
                  className="l2-btn-secondary"
                  style={{ fontSize: '12px', padding: '4px 12px' }}
                  onClick={handleResetSelection}
                >
                  Reset Selection
                </button>
              )}
            </div>
          </div>

          <div className="l2-selector-grid">
            {/* 1. State */}
            <div className="l2-select-field">
              <label className="l2-select-label" htmlFor="l2-sel-state">
                <span className="l2-step-dot">1</span> State
              </label>
              <div className="l2-select-wrapper">
                <select
                  id="l2-sel-state"
                  value={sel.state}
                  onChange={handleSelectState}
                  disabled={lists.state.length === 0}
                >
                  <option value="">
                    {lists.state.length === 0 ? 'No assigned states…' : 'Select State…'}
                  </option>
                  {lists.state.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                <span className="l2-select-icon">▼</span>
              </div>
            </div>

            {/* 2. Training Centre */}
            <div className="l2-select-field">
              <label className="l2-select-label" htmlFor="l2-sel-tc">
                <span className="l2-step-dot">2</span> Training Centre
              </label>
              <div className="l2-select-wrapper">
                <select
                  id="l2-sel-tc"
                  value={sel.tc}
                  disabled={!sel.state}
                  onChange={handleSelectTc}
                >
                  <option value="">{sel.state ? 'Select Centre…' : 'Awaiting state…'}</option>
                  {lists.tc.map((c) => (
                    <option key={c.tc_id} value={c.tc_id}>{c.name}</option>
                  ))}
                </select>
                <span className="l2-select-icon">▼</span>
              </div>
            </div>

            {/* 3. Sanction Order */}
            <div className="l2-select-field">
              <label className="l2-select-label" htmlFor="l2-sel-order">
                <span className="l2-step-dot">3</span> Sanction Order
              </label>
              <div className="l2-select-wrapper">
                <select
                  id="l2-sel-order"
                  value={sel.order}
                  disabled={!sel.tc}
                  onChange={handleSelectOrder}
                >
                  <option value="">{sel.tc ? 'Select Order…' : 'Awaiting centre…'}</option>
                  {lists.order.map((o) => (
                    <option key={o} value={o}>{o}</option>
                  ))}
                </select>
                <span className="l2-select-icon">▼</span>
              </div>
            </div>

            {/* 4. Batch */}
            <div className="l2-select-field">
              <label className="l2-select-label" htmlFor="l2-sel-batch">
                <span className="l2-step-dot">4</span> Batch
              </label>
              <div className="l2-select-wrapper">
                <select
                  id="l2-sel-batch"
                  value={sel.batch}
                  disabled={!sel.order}
                  onChange={handleSelectBatch}
                >
                  <option value="">{sel.order ? 'Select Batch…' : 'Awaiting order…'}</option>
                  {lists.batch.map((b) => (
                    <option key={b.kb_batch_id} value={b.kb_batch_id}>{b.batch_code}</option>
                  ))}
                </select>
                <span className="l2-select-icon">▼</span>
              </div>
            </div>

            {/* 5. Candidate */}
            <div className="l2-select-field">
              <label className="l2-select-label" htmlFor="l2-sel-cand">
                <span className="l2-step-dot">5</span> Candidate
              </label>
              <div className="l2-select-wrapper">
                <select
                  id="l2-sel-cand"
                  value={sel.cand}
                  disabled={!sel.batch}
                  onChange={handleSelectCandidate}
                >
                  <option value="">{sel.batch ? 'Select Candidate…' : 'Awaiting batch…'}</option>
                  {lists.cand.map((c) => (
                    <option key={c.candidate_id} value={c.candidate_id}>
                      {c.first_name} {c.last_name} ({c.candidate_id})
                    </option>
                  ))}
                </select>
                <span className="l2-select-icon">▼</span>
              </div>
            </div>
          </div>
        </section>

        

        {/* --------------------------------------------------------------------
           Candidate List Popup / Modal (Opened when an L2 card is clicked)
           -------------------------------------------------------------------- */}
        {activeCardFilter && (
          <div
            className="l1-modal-backdrop"
            onClick={(e) => {
              if (e.target === e.currentTarget) {
                setActiveCardFilter(null)
                setCardCandidates([])
              }
            }}
            role="dialog"
            aria-modal="true"
            aria-labelledby="l2-popup-title"
          >
            <div className="l1-cand-popup-dialog" onClick={(e) => e.stopPropagation()}>
              {/* Modal Header */}
              <div className="l1-cand-popup-header">
                <div className="l1-cand-popup-title-group">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className="l1-cand-popup-icon">
                      {activeCardFilter === 'total' && '👥'}
                      {activeCardFilter === 'l2_received' && '📥'}
                      {activeCardFilter === 'l2_recommended' && '🌟'}
                      {activeCardFilter === 'l2_rejected' && '✕'}
                      {activeCardFilter === 'l2_pending' && '⏱'}
                    </span>
                    <h3 id="l2-popup-title">
                      {activeCardFilter === 'total' && 'Total Candidates'}
                      {activeCardFilter === 'l2_received' && 'Received Candidates'}
                      {activeCardFilter === 'l2_recommended' && 'Recommended Candidates'}
                      {activeCardFilter === 'l2_rejected' && 'Rejected Candidates'}
                      {activeCardFilter === 'l2_pending' && 'Pending Candidates'}
                    </h3>
                    <span className="l1-cand-popup-count-badge">
                      {cardCandLoading ? '…' : cardCandTotal}
                    </span>
                  </div>
                  <p className="l1-cand-popup-sub">
                    {activeCardFilter === 'total' && 'All candidates registered in your assigned state'}
                    {activeCardFilter === 'l2_received' && 'Unique candidates submitted by L1 and received for CH review'}
                    {activeCardFilter === 'l2_recommended' && 'Candidates recommended by Centre Head (CH) review'}
                    {activeCardFilter === 'l2_rejected' && 'Candidates rejected by CH or returned to L1 for corrections'}
                    {activeCardFilter === 'l2_pending' && 'Received candidates currently awaiting Centre Head review'}
                    {sel.state ? ` (${sel.state})` : ''}
                  </p>
                </div>

                <button
                  type="button"
                  className="l1-popup-close-btn"
                  onClick={() => {
                    setActiveCardFilter(null)
                    setCardCandidates([])
                  }}
                  aria-label="Close candidate list modal"
                  title="Close (Esc)"
                >
                  ✕
                </button>
              </div>

              {/* Modal Search Toolbar */}
              <div className="l1-cand-popup-toolbar">
                <div className="l1-cand-popup-search-box">
                  <span className="l1-search-icon">🔍</span>
                  <input
                    type="text"
                    className="l1-cand-popup-search-input"
                    placeholder="Search by Candidate Name or Candidate ID…"
                    aria-label="Search by Candidate Name or Candidate ID"
                    value={cardCandSearch}
                    onChange={(e) => setCardCandSearch(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        fetchCardCandidates(activeCardFilter, 1, cardCandSearch)
                      }
                    }}
                    autoFocus
                  />
                  {cardCandSearch && (
                    <button
                      type="button"
                      className="l1-search-clear-btn"
                      onClick={() => {
                        setCardCandSearch('')
                        fetchCardCandidates(activeCardFilter, 1, '')
                      }}
                      title="Clear search"
                    >
                      ✕
                    </button>
                  )}
                </div>
                <button
                  type="button"
                  className="l1-btn-primary l1-cand-popup-search-btn"
                  onClick={() => fetchCardCandidates(activeCardFilter, 1, cardCandSearch)}
                >
                  Search
                </button>
              </div>

              {/* Modal Table Content */}
              <div className="l1-cand-popup-body">
                {cardCandLoading ? (
                  <div className="l1-cand-loading" style={{ padding: '48px 20px', textAlign: 'center' }}>
                    <p style={{ margin: 0, color: 'var(--mut)' }}>Loading candidates from database…</p>
                  </div>
                ) : cardCandError ? (
                  <div className="l1-cand-empty" style={{ color: 'var(--danger)', padding: '40px 20px', textAlign: 'center' }}>
                    <p>⚠️ {cardCandError}</p>
                    <button
                      type="button"
                      className="l1-btn-secondary"
                      style={{ marginTop: '8px' }}
                      onClick={() => fetchCardCandidates(activeCardFilter, cardCandPage, cardCandSearch)}
                    >
                      Retry
                    </button>
                  </div>
                ) : cardCandidates.length === 0 ? (
                  <div className="l1-cand-empty" style={{ padding: '48px 20px', textAlign: 'center' }}>
                    <div style={{ fontSize: '32px', marginBottom: '8px' }}>📂</div>
                    <p style={{ margin: 0, fontWeight: 600, color: 'var(--ink)' }}>No candidates found</p>
                    <p style={{ margin: '4px 0 0', fontSize: '13px', color: 'var(--mut)' }}>
                      {cardCandSearch
                        ? `No candidates match "${cardCandSearch}". Try a different keyword.`
                        : 'No candidate records match this status category in your state.'}
                    </p>
                  </div>
                ) : (
                  <div className="l1-popup-table-scroll">
                    <table className="l1-cand-table">
                      <thead>
                        <tr>
                          <th>Candidate Name &amp; ID</th>
                          <th>Father / Guardian</th>
                          <th>Training Centre</th>
                          <th>Batch Code</th>
                          <th className="l1-th-stage">CH</th>
                          <th className="l1-th-stage">COPS</th>
                          <th className="l1-th-stage">BL</th>
                          <th style={{ textAlign: 'right' }}>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {cardCandidates.map((cand) => (
                          <tr
                            key={cand.candidate_id}
                            className={sel.cand === cand.candidate_id ? 'active-row' : ''}
                          >
                            <td>
                              <strong>{cand.name}</strong>
                              <div className="l1-cand-id-small">{cand.candidate_id}</div>
                            </td>
                            <td>{cand.father_name || '—'}</td>
                            <td>{cand.tc_name || '—'}</td>
                            <td>{cand.batch_code || '—'}</td>
                            <td>
                              <span className={getStageBadgeClass(cand.ch_status)}>
                                {cand.ch_status || 'Pending'}
                              </span>
                            </td>
                            <td>
                              <span className={getStageBadgeClass(cand.cops_status)}>
                                {cand.cops_status || 'Pending'}
                              </span>
                            </td>
                            <td>
                              <span className={getStageBadgeClass(cand.bl_status)}>
                                {cand.bl_status || 'Pending'}
                              </span>
                            </td>
                            <td style={{ textAlign: 'right' }}>
                              <button
                                type="button"
                                className="l1-btn-open-dossier"
                                onClick={() => handleSelectCandidateFromList(cand)}
                              >
                                Open Dossier →
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Modal Footer with Pagination and Close */}
              <div className="l1-cand-popup-footer">
                <div className="l1-cand-pagination">
                  {cardCandPages > 1 && (
                    <>
                      <button
                        type="button"
                        className="l1-page-btn"
                        disabled={cardCandPage <= 1 || cardCandLoading}
                        onClick={() => {
                          const newPage = cardCandPage - 1
                          setCardCandPage(newPage)
                          fetchCardCandidates(activeCardFilter, newPage, cardCandSearch)
                        }}
                      >
                        ◀ Prev
                      </button>
                      <span className="l1-page-info">
                        Page {cardCandPage} of {cardCandPages}
                      </span>
                      <button
                        type="button"
                        className="l1-page-btn"
                        disabled={cardCandPage >= cardCandPages || cardCandLoading}
                        onClick={() => {
                          const newPage = cardCandPage + 1
                          setCardCandPage(newPage)
                          fetchCardCandidates(activeCardFilter, newPage, cardCandSearch)
                        }}
                      >
                        Next ▶
                      </button>
                    </>
                  )}
                </div>
                <button
                  type="button"
                  className="l1-btn-secondary"
                  onClick={() => {
                    setActiveCardFilter(null)
                    setCardCandidates([])
                  }}
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Banner if Candidate is Returned to L1 */}
        {sel.cand && isReturnedToL1 && (
          <div
            style={{
              margin: '0 24px 16px',
              padding: '12px 18px',
              background: '#fef3c7',
              border: '1px solid #fcd34d',
              borderRadius: '8px',
              color: '#92400e',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '12px',
            }}
          >
            <div>
              <strong>⚠️ Dossier Returned to L1 Coordinator for Correction</strong>
              <div style={{ fontSize: '13px', marginTop: '4px' }}>
                This candidate's placement audit has been returned to L1. It cannot be approved by L2, L3, or L4 until L1 resubmits corrected records.
                {statementData?.return_to_l1?.return_reason && (
                  <div style={{ marginTop: '2px', fontStyle: 'italic' }}>
                    Reason: "{statementData.return_to_l1.return_reason}"
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Workspace: 2-Panel Side-by-Side */}
        {!sel.cand ? (
          <section className="l2-empty-state">
            <div className="l2-empty-icon">🏢</div>
            <h3>Select a Candidate to Begin Centre Head Review</h3>
            <p>
              Select a State, Training Centre, Sanction Order, Batch, and Candidate from the pipeline above to view the placement audit statement and verify associated document evidence side-by-side.
            </p>
          </section>
        ) : loadingCandidate ? (
          <section className="l2-empty-state loading">
            <div className="l2-empty-icon">⏳</div>
            <h3>Loading Candidate Placement Dossier…</h3>
            <p>Fetching placement audit statement and verification evidence records.</p>
          </section>
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
            <section className="l2-panel l2-statement-panel" aria-label="Candidate Placement Statement">
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
                  <PdfViewer
                    fileUrl={previewBlobUrl}
                    fileName={previewDoc.file_name}
                    fileMeta={previewDoc.type || previewDoc.category || 'Document Evidence'}
                    mimeType={previewDoc.mime_type}
                    isLoading={loadingPreview}
                    errorMessage={previewError}
                    isReviewed={Boolean(docReviews[String(previewDoc.id)]?.reviewed)}
                    reviewedAt={docReviews[String(previewDoc.id)]?.reviewed_at}
                    onToggleReview={(checked) => handleToggleDocReview(previewDoc.id, checked)}
                    onDownload={() => downloadDocument(sel.cand, previewDoc.id, previewDoc.file_name)}
                    onClose={handleClosePreview}
                  />
                ) : (
                  /* Documents List */
                  <div className="l2-doc-list">
                    {/* Appointment Letter Section */}
                    <div className="l2-evidence-category-header">
                      <span>1. Appointment / Offer Letter {employersList.length > 1 ? `(${appointmentDocs.length}/${employersList.length})` : ''}</span>
                    </div>

                    {appointmentDocs.length > 0 ? (
                      appointmentDocs.map((doc) => (
                        <div key={doc.id} className="l2-doc-card">
                          <div className="l2-doc-card-top">
                            <span className="l2-doc-type-icon">✉</span>
                            <div className="l2-doc-meta">
                              <span className="l2-doc-name">{doc.file_name}</span>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', marginTop: '2px' }}>
                                <span className="l2-doc-sub">Appointment / Offer Letter • Verified in Drive</span>
                                {doc.employer_id && getEmployerName(doc.employer_id) && (
                                  <span className="l1-emp-badge">🏢 {getEmployerName(doc.employer_id)}</span>
                                )}
                              </div>
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
                      ))
                    ) : (
                      <div className="l2-doc-card" style={{ background: '#fef2f2', borderColor: '#fca5a5' }}>
                        <span style={{ fontSize: '13px', color: '#991b1b', fontWeight: 600 }}>
                          ✕ Missing Appointment / Offer Letter
                        </span>
                      </div>
                    )}

                    {/* Salary Slips Section */}
                    <div className="l2-evidence-category-header">
                      <span>2. Monthly Salary Slips (Min 3 Required)</span>
                    </div>

                    {salaryDocs.map((doc, idx) => {
                      const empSeq = getEmployerDocumentSequence(doc, successDocs)
                      return (
                      <div key={doc.id} className="l2-doc-card">
                        <div className="l2-doc-card-top">
                          <span className="l2-doc-type-icon">₹</span>
                          <div className="l2-doc-meta">
                            <span className="l2-doc-name">{doc.file_name}</span>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', marginTop: '2px' }}>
                              <span className="l2-doc-sub">
                                {doc.reporting_month ? `Month ${empSeq} — ${MONTH_NAMES[doc.reporting_month - 1] || doc.reporting_month} ${doc.reporting_year || ''}` : `Month ${empSeq}`} • Verified in Drive
                              </span>
                              {doc.employer_id && getEmployerName(doc.employer_id) && (
                                <span className="l1-emp-badge">🏢 {getEmployerName(doc.employer_id)}</span>
                              )}
                            </div>
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
                    )})}
                    {salaryDocs.length === 0 && (
                      <div className="l2-doc-card" style={{ background: '#fef2f2', borderColor: '#fca5a5' }}>
                        <span style={{ fontSize: '13px', color: '#991b1b', fontWeight: 600 }}>
                          ✕ No Salary Slips uploaded
                        </span>
                      </div>
                    )}

                    {/* Bank Statements Section */}
                    <div className="l2-evidence-category-header">
                      <span>3. Bank Statements / Passbook (Min 3 Required)</span>
                    </div>

                    {bankDocs.map((doc, idx) => (
                      <div key={doc.id} className="l2-doc-card">
                        <div className="l2-doc-card-top">
                          <span className="l2-doc-type-icon">▤</span>
                          <div className="l2-doc-meta">
                            <span className="l2-doc-name">{doc.file_name}</span>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', marginTop: '2px' }}>
                              {doc.is_consolidated ? (
                                <span className="l1-coverage-badge">
                                  📅 Consolidated: {MONTH_NAMES[(doc.coverage_start_month || 1) - 1]} {doc.coverage_start_year} – {MONTH_NAMES[(doc.coverage_end_month || 1) - 1]} {doc.coverage_end_year}
                                </span>
                              ) : (
                                <span className="l2-doc-sub">
                                  {doc.reporting_month ? `${MONTH_NAMES[doc.reporting_month - 1] || doc.reporting_month} ${doc.reporting_year || ''}` : `Month ${idx + 1}`} • Verified in Drive
                                </span>
                              )}
                              {doc.employer_id && getEmployerName(doc.employer_id) && (
                                <span className="l1-emp-badge">🏢 {getEmployerName(doc.employer_id)}</span>
                              )}
                            </div>
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

                    {/* Supporting / Other Documents Section (if any uploaded) */}
                    {otherDocs.length > 0 && (
                      <>
                        <div className="l2-evidence-category-header">
                          <span>4. Supporting / Other Documents ({otherDocs.length})</span>
                        </div>
                        {otherDocs.map((doc) => (
                          <div key={doc.id} className="l2-doc-card">
                            <div className="l2-doc-card-top">
                              <span className="l2-doc-type-icon">📎</span>
                              <div className="l2-doc-meta">
                                <span className="l2-doc-name">{doc.file_name}</span>
                                <span className="l2-doc-sub">
                                  {doc.document_title || 'Additional Supporting Document'} • Verified in Drive
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
                      </>
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
                  Checklist: {reviewedAppointmentCount + reviewedSalaryCount + reviewedBankCount} of {requiredAppointmentCount + Math.max(3, salaryDocs.length) + (hasConsolidatedBank ? bankDocs.length : Math.max(3, bankDocs.length))} Reviewed
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

              {/* Reject & Return to L1 */}
              <button
                type="button"
                className="l2-btn-return"
                disabled={!sel.cand || loadingCandidate || isAlreadyApproved || returningToL1}
                onClick={() => setReturnModalOpen(true)}
                title={
                  isAlreadyApproved
                    ? 'Statement is already approved'
                    : isReturnedToL1
                    ? 'Candidate is already returned to L1 awaiting corrections'
                    : 'Reject and return candidate dossier to L1 coordinator for corrections'
                }
              >
                ↩ Reject &amp; Return to L1
              </button>

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

        {/* Modal: Reject & Return to L1 Confirmation */}
        {returnModalOpen && (
          <div className="l2-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="l2-return-modal-title">
            <div className="l2-modal-card" style={{ maxWidth: 540 }}>
              <div className="l2-modal-header">
                <h4 id="l2-return-modal-title">Reject &amp; Return to L1 Coordinator</h4>
                <button
                  type="button"
                  onClick={() => {
                    setReturnModalOpen(false)
                    setReturnReason('')
                    setReturnRemarks('')
                  }}
                  title="Close (Esc)"
                >
                  ✕
                </button>
              </div>
              <div className="l2-modal-body">
                <p style={{ margin: '0 0 12px' }}>
                  Return placement audit dossier for <strong>{candDetail?.first_name} {candDetail?.last_name}</strong> (<code>{sel.cand}</code>) back to the L1 Placement Coordinator for corrections.
                </p>
                <div style={{ background: '#fef3c7', padding: '10px 14px', borderRadius: '6px', fontSize: '13px', color: '#92400e', marginBottom: '14px' }}>
                  ⚠️ This action will mark the CH stage as returned, set the candidate to <strong>RETURNED TO L1</strong>, and unlock the record for the L1 coordinator to edit and resubmit. It will not progress to COPS or BL until resubmitted and recommended.
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '12px' }}>
                  <label style={{ fontSize: '12px', fontWeight: 600, color: '#475569' }}>
                    Rejection / Correction Reason <span style={{ color: '#ef4444' }}>*</span>
                  </label>
                  <textarea
                    rows={3}
                    placeholder="Enter specific discrepancy or correction needed (e.g. Month 2 salary slip net pay does not match bank credit amount)."
                    value={returnReason}
                    onChange={(e) => setReturnReason(e.target.value)}
                    required
                    style={{ padding: '8px', border: '1px solid #cbd5e1', borderRadius: '6px', fontSize: '13px' }}
                  />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <label style={{ fontSize: '12px', fontWeight: 600, color: '#475569' }}>
                    Additional Remarks (Optional)
                  </label>
                  <textarea
                    rows={2}
                    placeholder="Optional additional guidance for the coordinator..."
                    value={returnRemarks}
                    onChange={(e) => setReturnRemarks(e.target.value)}
                    style={{ padding: '8px', border: '1px solid #cbd5e1', borderRadius: '6px', fontSize: '13px' }}
                  />
                </div>
              </div>
              <div className="l2-modal-footer">
                <button
                  type="button"
                  className="l1-btn-secondary"
                  onClick={() => {
                    setReturnModalOpen(false)
                    setReturnReason('')
                    setReturnRemarks('')
                  }}
                  disabled={returningToL1}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="l2-btn-return-confirm"
                  onClick={handleReturnToL1}
                  disabled={returningToL1 || !returnReason.trim()}
                >
                  {returningToL1 ? 'Returning Dossier…' : 'Confirm Reject & Return to L1'}
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
