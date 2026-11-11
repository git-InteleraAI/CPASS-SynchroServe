import { useEffect, useRef, useState, useCallback, useMemo, lazy, Suspense } from 'react'
import { api, downloadDocument, fetchDocumentBlob, getDocumentPreviewUrl } from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import PlacementAuditStatement from './PlacementAuditStatement'
import ErrorBoundary from './ErrorBoundary'
import FlexibleReturnModal from './FlexibleReturnModal'
import L2DocumentUploadModal from './L2DocumentUploadModal'
import './L2DocumentUploadModal.css'
import '../pages/L2Home.css'
import {
  MONTH_NAMES,
  calculateNextSalaryPeriodForEmployer,
  getEmployerDocumentSequence,
} from '../lib/salarySequenceHelper'
import { resolveCandidateHierarchyPipeline } from '../lib/candidatePipelineHelper'

// Lazy load PdfViewer so heavy pdfjs-dist (~450 KB) is code-split and only loaded when previewing
const PdfViewer = lazy(() => import('./PdfViewer'))

const RESET = {
  state: ['tc', 'order', 'batch', 'cand'],
  tc: ['order', 'batch', 'cand'],
  order: ['batch', 'cand'],
  batch: ['cand'],
  cand: [],
}

function formatStageStatus(status) {
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
}

const LEVEL_CONFIGS = {
  L2: {
    levelName: 'L2',
    roleLabel: 'Center Head (CH)',
    roleBadge: 'Center Head Review',
    dashboardSub: 'Verify candidate placement statements and document evidence against original records.',
    stageKey: 'ch_status',
    canEditStatement: true,
    hasChecklistToggle: true,
    checklistApiEndpoint: (cid) => `/candidates/${cid}/audit/l2-review/checklist`,
    metrics: [
      {
        key: 'total',
        title: 'Total',
        icon: '👥',
        filterKey: 'total',
        className: 'total',
        getCount: (s) => (s ? s.total : '—'),
        description: 'All candidates registered in your assigned state',
      },
      {
        key: 'l2_received',
        title: 'Received',
        icon: '📥',
        filterKey: 'l2_received',
        className: 'received',
        getCount: (s) => (s ? (s.l2_received ?? s.received ?? 0) : '—'),
        description: 'Unique candidates submitted by L1 and received for CH review',
      },
      {
        key: 'l2_recommended',
        title: 'Recommended',
        icon: '🌟',
        filterKey: 'l2_recommended',
        className: 'recommended',
        getCount: (s) => (s ? (s.l2_recommended ?? s.recommended ?? 0) : '—'),
        description: 'Candidates recommended by Centre Head (CH) review',
      },
      {
        key: 'l2_rejected',
        title: 'Rejected',
        icon: '✕',
        filterKey: 'l2_rejected',
        className: 'rejected',
        getCount: (s) => (s ? (s.l2_rejected ?? s.ch_rejected ?? 0) : '—'),
        description: 'Candidates rejected by CH or returned to L1 for corrections',
      },
      {
        key: 'l2_pending',
        title: 'Pending',
        icon: '⏱',
        filterKey: 'l2_pending',
        className: 'pending',
        getCount: (s) => (s ? (s.l2_pending ?? 0) : '—'),
        description: 'Received candidates currently awaiting Centre Head review',
      },
    ],
    dockRoleTitle: 'L2 Center Manager Review',
    approvedDockTitle: '✓ Placement Statement Approved by CH',
    approveBtnText: '✓ Approve Placement Statement',
    approvedBadgeText: 'CH APPROVED',
    approveModalTitle: 'Endorse Placement Audit Approval',
    approveModalRoleName: 'Centre Manager',
    approveEndpoint: (cid) => `/candidates/${cid}/audit/l2-review/approve`,
    returnType: 'simple_l1',
    returnEndpoint: (cid) => `/candidates/${cid}/audit/l2-review/return-to-l1`,
    hasReject: false,
  },
  L3: {
    levelName: 'L3',
    roleLabel: 'COPS Audit Team',
    roleBadge: 'COPS Placement Audit Review',
    dashboardSub: 'Review Center Head recommendations, verify placement evidence and forward eligible dossiers to Business Leader.',
    stageKey: 'cops_status',
    canEditStatement: false,
    hasChecklistToggle: true,
    checklistApiEndpoint: (cid) => `/candidates/${cid}/audit/l3-review/checklist`,
    metrics: [
      {
        key: 'total',
        title: 'Total',
        icon: '👥',
        filterKey: 'total',
        className: 'total',
        getCount: (s) => (s ? s.total : '—'),
        description: 'All candidates registered across CPASS training centres',
      },
      {
        key: 'l3_received',
        title: 'Received',
        icon: '📥',
        filterKey: 'l3_received',
        className: 'received',
        getCount: (s) => (s ? (s.l3_received ?? s.cops_received ?? 0) : '—'),
        description: 'Candidates recommended by Center Head and received for COPS audit',
      },
      {
        key: 'l3_verified',
        title: 'Verified',
        icon: '🛡️',
        filterKey: 'l3_verified',
        className: 'verified',
        getCount: (s) => (s ? (s.l3_verified ?? s.cops_verified ?? 0) : '—'),
        description: 'Candidates verified & endorsed by COPS team and forwarded to BL',
      },
      {
        key: 'l3_rejected_returned',
        title: 'Rejected',
        icon: '✕',
        filterKey: 'l3_rejected_returned',
        className: 'rejected',
        getCount: (s) => (s ? (s.l3_rejected_returned ?? s.cops_rejected_returned ?? 0) : '—'),
        description: 'Candidates rejected by COPS or returned to L1 coordinator',
      },
      {
        key: 'l3_pending',
        title: 'Pending',
        icon: '⏱',
        filterKey: 'l3_pending',
        className: 'pending',
        getCount: (s) => (s ? (s.l3_pending ?? s.cops_pending ?? 0) : '—'),
        description: 'Received candidates awaiting COPS verification & endorsement',
      },
    ],
    dockRoleTitle: 'L3 COPS Placement Audit Review',
    approvedDockTitle: '✓ Placement Dossier Verified by COPS',
    approveBtnText: '✓ Verify & Endorse (Forward to BL)',
    approvedBadgeText: 'COPS VERIFIED',
    approveModalTitle: 'Verify & Endorse Dossier',
    approveModalRoleName: 'COPS Audit Reviewer',
    approveEndpoint: (cid) => `/candidates/${cid}/audit/l3-review/approve`,
    returnType: 'flexible',
    returnEndpoint: (cid) => `/candidates/${cid}/audit/l3-review/return`,
    hasReject: true,
    rejectEndpoint: (cid) => `/candidates/${cid}/audit/l3-review/reject`,
  },
  L4: {
    levelName: 'L4',
    roleLabel: 'Business Leader (BL)',
    roleBadge: 'Business Leader Review',
    dashboardSub: 'Conduct leadership review of endorsed dossiers, enforce business governance, and forward for CEO sanction.',
    stageKey: 'bl_status',
    canEditStatement: false,
    hasChecklistToggle: false,
    metrics: [
      {
        key: 'total',
        title: 'Total',
        icon: '👥',
        filterKey: 'total',
        className: 'total',
        getCount: (s) => (s ? s.total : '—'),
        description: 'All candidates registered across your assigned regional states',
      },
      {
        key: 'l4_received',
        title: 'Received',
        icon: '📥',
        filterKey: 'l4_received',
        className: 'received',
        getCount: (s) => (s ? (s.l4_received ?? s.bl_received ?? 0) : '—'),
        description: 'Candidates verified by COPS and received for Business Leader approval',
      },
      {
        key: 'l4_approved',
        title: 'BL Approved',
        icon: '🏆',
        filterKey: 'l4_approved',
        className: 'approved',
        getCount: (s) => (s ? (s.l4_approved ?? s.bl_approved ?? 0) : '—'),
        description: 'Candidates approved by Business Leader and forwarded for CEO sanction',
      },
      {
        key: 'l4_rejected_returned',
        title: 'Rejected',
        icon: '✕',
        filterKey: 'l4_rejected_returned',
        className: 'rejected',
        getCount: (s) => (s ? (s.l4_rejected_returned ?? s.bl_rejected_returned ?? 0) : '—'),
        description: 'Candidates rejected by BL or returned to earlier levels (L1/L2/L3)',
      },
      {
        key: 'l4_pending',
        title: 'Pending',
        icon: '⏱',
        filterKey: 'l4_pending',
        className: 'pending',
        getCount: (s) => (s ? (s.l4_pending ?? s.bl_pending ?? 0) : '—'),
        description: 'Candidates awaiting Business Leader review and approval',
      },
    ],
    dockRoleTitle: 'L4 Business Leader Executive Review',
    approvedDockTitle: '✓ Placement Dossier Approved by BL',
    approveBtnText: '✓ Approve & Forward to CEO',
    approvedBadgeText: 'BL APPROVED',
    approveModalTitle: 'Approve & Forward to CEO',
    approveModalRoleName: 'Business Leader',
    approveEndpoint: (cid) => `/candidates/${cid}/audit/l4-review/approve`,
    returnType: 'flexible',
    returnEndpoint: (cid) => `/candidates/${cid}/audit/l4-review/return`,
    hasReject: true,
    rejectEndpoint: (cid) => `/candidates/${cid}/audit/l4-review/reject`,
  },
  L5: {
    levelName: 'L5',
    roleLabel: 'Chief Executive Officer (CEO)',
    roleBadge: 'Executive Sanction & Final Approval',
    dashboardSub: 'Executive review and final sanction for state placement dossiers.',
    stageKey: 'ceo_status',
    canEditStatement: false,
    hasChecklistToggle: false,
    metrics: [
      {
        key: 'total',
        title: 'Total',
        icon: '👥',
        filterKey: 'total',
        className: 'total',
        getCount: (s) => (s ? s.total : '—'),
        description: 'All candidates registered across all 12 CPASS states nationwide',
      },
      {
        key: 'l5_received',
        title: 'Received',
        icon: '📥',
        filterKey: 'l5_received',
        className: 'received',
        getCount: (s) => (s ? (s.l5_received ?? s.ceo_received ?? 0) : '—'),
        description: 'Candidates approved by Business Leaders awaiting final executive sanction',
      },
      {
        key: 'l5_approved',
        title: 'Sanctioned',
        icon: '👑',
        filterKey: 'l5_approved',
        className: 'approved',
        getCount: (s) => (s ? (s.l5_approved ?? s.ceo_approved ?? 0) : '—'),
        description: 'Candidates finally sanctioned and approved by CEO. Workflow complete.',
      },
      {
        key: 'l5_rejected_returned',
        title: 'Rejected',
        icon: '✕',
        filterKey: 'l5_rejected_returned',
        className: 'rejected',
        getCount: (s) => (s ? (s.l5_rejected_returned ?? s.ceo_rejected_returned ?? 0) : '—'),
        description: 'Candidates rejected by CEO or returned to previous levels (L1/L2/L3/L4)',
      },
      {
        key: 'l5_pending',
        title: 'Pending',
        icon: '⏱',
        filterKey: 'l5_pending',
        className: 'pending',
        getCount: (s) => (s ? (s.l5_pending ?? s.ceo_pending ?? 0) : '—'),
        description: 'Candidates awaiting CEO executive sanction and final approval',
      },
    ],
    dockRoleTitle: 'L5 CEO Executive Sanction Review',
    approvedDockTitle: '👑 Dossier Sanctioned & Final Approved by CEO',
    approveBtnText: '✓ Sanction & Final Approve',
    approvedBadgeText: '👑 CEO APPROVED',
    approveModalTitle: 'Executive Sanction & Final Placement Approval',
    approveModalRoleName: 'Chief Executive Officer',
    approveEndpoint: (cid) => `/candidates/${cid}/audit/l5-review/approve`,
    returnType: 'flexible',
    returnEndpoint: (cid) => `/candidates/${cid}/audit/l5-review/return`,
    hasReject: true,
    rejectEndpoint: (cid) => `/candidates/${cid}/audit/l5-review/reject`,
  },
}

export default function UnifiedReviewDashboard({ level = 'L2' }) {
  const { profile } = useAuth()
  const config = LEVEL_CONFIGS[level] || LEVEL_CONFIGS.L2

  // Determine user authorized states list based on role
  const authorizedStates = useMemo(() => {
    if (level === 'L2') {
      return profile?.assigned_state ? [profile.assigned_state] : []
    }
    if (level === 'L4') {
      if (Array.isArray(profile?.assigned_states) && profile.assigned_states.length > 0) {
        return profile.assigned_states
      }
      if (profile?.assigned_state) {
        return profile.assigned_state.split(',').map((s) => s.trim()).filter(Boolean)
      }
      return []
    }
    // L3 & L5 have access to all states
    return null
  }, [level, profile])

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
  const selRef = useRef(sel)
  selRef.current = sel

  // Selected Candidate Data States
  const [candDetail, setCandDetail] = useState(null)
  const [statementData, setStatementData] = useState(null)
  const [documents, setDocuments] = useState([])
  const [loadingCandidate, setLoadingCandidate] = useState(false)
  const [candidateError, setCandidateError] = useState(null)

  // Independent panel scrolling refs
  const statementBodyRef = useRef(null)
  const docBodyRef = useRef(null)

  // Document Verification Checklist State (doc_id -> { reviewed: boolean, reviewed_at: string, reviewed_by: string })
  const [docReviews, setDocReviews] = useState({})
  const [updatingChecklist, setUpdatingChecklist] = useState(false)

  // Document Preview State
  const [previewDoc, setPreviewDoc] = useState(null)
  const [previewBlobUrl, setPreviewBlobUrl] = useState(null)
  const [loadingPreview, setLoadingPreview] = useState(false)
  const [previewError, setPreviewError] = useState(null)

  // Edit Mode & Form States (for L2)
  const [isEditMode, setIsEditMode] = useState(false)
  const [editedData, setEditedData] = useState({
    employer_details: [],
    salary_details: [],
    signoff_details: {},
    remarks: '',
  })
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)
  const [savingCorrections, setSavingCorrections] = useState(false)

  // Dashboard Summary Metrics & Filtered Candidate List
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

  // Workflow Action Modals
  const [decisionModalOpen, setDecisionModalOpen] = useState(false)
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
  }

  const [revertModalOpen, setRevertModalOpen] = useState(false)
  const [approveModalOpen, setApproveModalOpen] = useState(false)
  const [approveRemarks, setApproveRemarks] = useState('')
  const [approving, setApproving] = useState(false)
  const [pendingCandSwitch, setPendingCandSwitch] = useState(null)
  const [switchConfirmModalOpen, setSwitchConfirmModalOpen] = useState(false)

  // Toast Notification
  const [toast, setToast] = useState(null)
  const showToast = useCallback((message, type = 'info') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 4500)
  }, [])

  // Request race-condition counter
  const loadSequenceRef = useRef(0)
  const pipelineRequestSeqRef = useRef(0)

  // Fetch Summary Figures
  const fetchDashboardSummary = useCallback((targetState) => {
    let s = targetState !== undefined ? targetState : selRef.current.state
    setLoadingSummary(true)
    setSummaryError('')
    const query = s ? `?state=${encodeURIComponent(s)}` : ''
    api(`/dashboard/summary${query}`)
      .then((data) => {
        setSummaryData(data)
        setSummaryError('')
      })
      .catch((err) => {
        console.warn(`Failed to load ${level} dashboard summary:`, err)
        setSummaryError(err?.message || 'Failed to load dashboard summary metrics.')
      })
      .finally(() => {
        setLoadingSummary(false)
      })
  }, [level])

  // Fetch Candidates for clicked Metric Card
  const fetchCardCandidates = useCallback((filterType, pageNum = 1, searchQuery = '', targetState) => {
    if (!filterType) return
    const s = targetState !== undefined ? targetState : selRef.current.state
    setCardCandLoading(true)
    setCardCandError('')
    let url = `/dashboard/candidates?filter=${encodeURIComponent(filterType)}&filter_type=${encodeURIComponent(filterType)}&page=${pageNum}&page_size=20`
    if (s) {
      url += `&state=${encodeURIComponent(s)}`
    }
    if (searchQuery && searchQuery.trim()) {
      url += `&search=${encodeURIComponent(searchQuery.trim())}`
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
  }, [])

  function handleCardClick(filterKey) {
    if (activeCardFilter === filterKey) {
      setActiveCardFilter(null)
      setCardCandidates([])
    } else {
      setActiveCardFilter(filterKey)
      setCardCandPage(1)
      setCardCandSearch('')
      fetchCardCandidates(filterKey, 1, '', sel.state)
    }
  }

  // Close modals on Escape key
  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        if (activeCardFilter) {
          setActiveCardFilter(null)
          setCardCandidates([])
        }
        if (decisionModalOpen) setDecisionModalOpen(false)
        if (approveModalOpen) setApproveModalOpen(false)
        if (revertModalOpen) setRevertModalOpen(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [activeCardFilter, decisionModalOpen, approveModalOpen, revertModalOpen])

  // ---------------------------------------------------------------------------
  // 1. Cascading Lookups Loading & State Initialization
  // ---------------------------------------------------------------------------
  useEffect(() => {
    let isMounted = true
    api('/lookups/states')
      .then((allStates) => {
        if (!isMounted) return
        let permitted = allStates
        if (authorizedStates && authorizedStates.length > 0) {
          permitted = allStates.filter((s) => authorizedStates.includes(s))
        }
        setLists((l) => ({ ...l, state: permitted }))

        // Initial state selection logic
        if (level === 'L2' && profile?.assigned_state) {
          const initSt = profile.assigned_state
          setSel((s) => s.state ? s : { ...s, state: initSt })
          fetchDashboardSummary(initSt)
          api('/lookups/centres', { state: initSt })
            .then((centres) => {
              if (isMounted) setLists((l) => ({ ...l, tc: centres }))
            })
            .catch(() => {})
        } else if (level === 'L3') {
          // L3 COPS: Default to "All States (National Scope)"
          setSel((s) => s.state ? s : { ...s, state: '' })
          fetchDashboardSummary('')
        } else if (level === 'L4') {
          // L4 BL: Default to "All Assigned States"
          setSel((s) => s.state ? s : { ...s, state: '' })
          fetchDashboardSummary('')
        } else if (level === 'L5') {
          // L5 CEO: Default to "All States (National Scope)"
          setSel((s) => s.state ? s : { ...s, state: '' })
          fetchDashboardSummary('')
        }
      })
      .catch((err) => {
        if (isMounted) showToast(err.message || 'Failed to load states', 'error')
      })

    return () => {
      isMounted = false
    }
  }, [level, profile?.assigned_state])

  const resetBelow = (levelKey) => {
    const keys = RESET[levelKey] || []
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
      if (!window.confirm('You have unsaved changes. Discard and reset?')) return
    }
    resetBelow('state')
    const defaultState = level === 'L2' ? (profile?.assigned_state || '') : ''
    setSel({ state: defaultState, tc: '', order: '', batch: '', cand: '' })
    fetchDashboardSummary(defaultState)
    setActiveCardFilter(null)
    setCardCandidates([])
    setCandDetail(null)
    setStatementData(null)
    setDocuments([])
    if (previewBlobUrl?.startsWith('blob:')) window.URL.revokeObjectURL(previewBlobUrl)
    if (previewBlobUrl) setPreviewBlobUrl(null)
    setPreviewDoc(null)
    if (defaultState) {
      api('/lookups/centres', { state: defaultState })
        .then((centres) => setLists((l) => ({ ...l, tc: centres })))
        .catch(() => {})
    } else {
      setLists((l) => ({ ...l, tc: [] }))
    }
  }

  const handleSelectState = (e) => {
    const val = e.target.value
    resetBelow('state')
    setSel((s) => ({ ...s, state: val }))

    // If candidate view was open, clear it
    if (candDetail) {
      setCandDetail(null)
      setStatementData(null)
      setDocuments([])
      setDocReviews({})
      if (previewBlobUrl?.startsWith('blob:')) window.URL.revokeObjectURL(previewBlobUrl)
      if (previewBlobUrl) setPreviewBlobUrl(null)
      setPreviewDoc(null)
    }

    // Immediately fetch fresh summary metrics
    fetchDashboardSummary(val)

    // If candidate queue modal is open, refresh candidate list with new state
    if (activeCardFilter) {
      setCardCandPage(1)
      fetchCardCandidates(activeCardFilter, 1, cardCandSearch, val)
    }

    if (!val) {
      // In aggregate mode, clear Training Centres
      setLists((l) => ({ ...l, tc: [] }))
      return
    }

    // In state mode, fetch Training Centres for selected state
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

  const handleSelectCandidateFromList = async (cand) => {
    if (!cand?.candidate_id) return
    const candId = cand.candidate_id
    if (hasUnsavedChanges) {
      setPendingCandSwitch(candId)
      setSwitchConfirmModalOpen(true)
      return
    }
    setActiveCardFilter(null)
    setCardCandidates([])

    const reqSeq = ++pipelineRequestSeqRef.current

    try {
      const result = await resolveCandidateHierarchyPipeline({
        candidateId: candId,
        initialCandidate: cand,
        currentStates: lists.state,
        apiFetch: api,
      })

      if (pipelineRequestSeqRef.current !== reqSeq) return

      // Populate all five dropdown lists and selections simultaneously
      setLists((l) => ({
        ...l,
        ...result.lists,
      }))
      setSel(result.selection)

      executeCandidateSwitch(candId)
    } catch (err) {
      if (pipelineRequestSeqRef.current === reqSeq) {
        showToast(err.message || 'Failed to resolve candidate hierarchy', 'error')
        executeCandidateSwitch(candId)
      }
    }
  }

  const executeCandidateSwitch = (candId) => {
    setSel((s) => ({ ...s, cand: candId }))
    setHasUnsavedChanges(false)
    setIsEditMode(false)
    setPendingCandSwitch(null)
    setSwitchConfirmModalOpen(false)

    // Reset independent scroll positions on candidate switch
    if (statementBodyRef.current) {
      statementBodyRef.current.scrollTop = 0
    }
    if (docBodyRef.current) {
      docBodyRef.current.scrollTop = 0
    }

    // Cleanup preview
    if (previewBlobUrl?.startsWith('blob:')) window.URL.revokeObjectURL(previewBlobUrl)
    if (previewBlobUrl) setPreviewBlobUrl(null)
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

      if (seq !== loadSequenceRef.current) return

      setCandDetail(candRes)
      setStatementData(stmtRes)
      setDocuments(docsRes || [])

      // Initialize persistent checklist reviews
      const savedReviews =
        stmtRes.l3_document_reviews ||
        stmtRes.document_audit?.l3_document_reviews ||
        stmtRes.l2_document_reviews ||
        stmtRes.document_audit?.l2_document_reviews ||
        {}
      setDocReviews(savedReviews)

      // Initialize edit form data (for L2)
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
  // 3. Document Preview Mechanism & Bounded Session Cache
  // ---------------------------------------------------------------------------
  const previewBlobCache = useRef(new Map())

  // Revoke all cached object URLs when candidate changes or component unmounts
  useEffect(() => {
    return () => {
      previewBlobCache.current.forEach((url) => {
        if (url?.startsWith('blob:')) window.URL.revokeObjectURL(url)
      })
      previewBlobCache.current.clear()
    }
  }, [sel.cand])

  const handlePreviewDocument = async (doc) => {
    if (previewDoc?.id === doc.id) return

    setPreviewDoc(doc)
    setLoadingPreview(true)
    setPreviewError(null)

    try {
      const isPdf = doc.mime_type === 'application/pdf' || /\.pdf$/i.test(doc.file_name || '')
      if (isPdf) {
        // Give PDF.js the protected API URL directly so it can issue HTTP Range
        // requests instead of waiting for a complete Blob download first.
        setPreviewBlobUrl(getDocumentPreviewUrl(sel.cand, doc.id))
      } else {
        const cachedUrl = previewBlobCache.current.get(doc.id)
        if (cachedUrl) {
          setPreviewBlobUrl(cachedUrl)
        } else {
          // Preserve credentialed Blob loading for image previews
          const blob = await fetchDocumentBlob(sel.cand, doc.id)
          const newUrl = window.URL.createObjectURL(blob)
          // Bound memory to maximum 8 documents per session
          if (previewBlobCache.current.size >= 8) {
            const firstKey = previewBlobCache.current.keys().next().value
            const oldUrl = previewBlobCache.current.get(firstKey)
            if (oldUrl?.startsWith('blob:')) window.URL.revokeObjectURL(oldUrl)
            previewBlobCache.current.delete(firstKey)
          }
          previewBlobCache.current.set(doc.id, newUrl)
          setPreviewBlobUrl(newUrl)
        }
      }
    } catch (err) {
      setPreviewError(err.message || 'Failed to load document preview.')
      showToast(err.message || 'Failed to load document preview.', 'error')
    } finally {
      setLoadingPreview(false)
    }
  }

  const handleClosePreview = () => {
    setPreviewBlobUrl(null)
    setPreviewDoc(null)
    setPreviewError(null)
  }

  // ---------------------------------------------------------------------------
  // 4. Document Verification Checklist Persistence
  // ---------------------------------------------------------------------------
  const handleToggleDocReview = async (docId, checked) => {
    if (!config.hasChecklistToggle) return
    const updated = {
      ...docReviews,
      [docId]: {
        reviewed: checked,
        reviewed_at: new Date().toISOString(),
        reviewed_by: profile?.full_name || config.roleLabel,
      },
    }
    setDocReviews(updated)

    try {
      setUpdatingChecklist(true)
      await api(config.checklistApiEndpoint(sel.cand), null, {
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
  // 5. Statement Editing Operations (L2 CH only)
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
    let updatedMonth = null
    let updatedYear = null
    setEditedData((prev) => {
      const list = [...prev.salary_details]
      const idx = typeof idOrIdx === 'number' ? idOrIdx : list.findIndex((s) => s.id === idOrIdx)
      if (idx >= 0) {
        list[idx] = { ...list[idx], [field]: value }
        if (field === 'month' || field === 'year') {
          updatedMonth = field === 'month' ? parseInt(value, 10) : list[idx].month
          updatedYear = field === 'year' ? parseInt(value, 10) : list[idx].year
        }
      }
      return { ...prev, salary_details: list }
    })
    setHasUnsavedChanges(true)

    const cId = candDetail?.candidate_id || sel.cand
    if ((field === 'month' || field === 'year') && cId && updatedMonth && updatedYear) {
      const curSal = (editedData.salary_details || [])[typeof idOrIdx === 'number' ? idOrIdx : editedData.salary_details.findIndex((s) => s.id === idOrIdx)]
      const empId = curSal?.employer_id
      const emp = (editedData.employer_details || []).find((e) => e.id === empId) || (editedData.employer_details || [])[0]
      const targetState = (emp?.work_state && (emp?.work_state_detection_status === 'IDENTIFIED' || !emp?.work_state_detection_status)) ? emp.work_state : null

      if (!targetState) {
        setEditedData((prev) => {
          const list = [...prev.salary_details]
          const idx = typeof idOrIdx === 'number' ? idOrIdx : list.findIndex((s) => s.id === idOrIdx)
          if (idx >= 0) {
            list[idx] = {
              ...list[idx],
              minimum_wage: null,
              minimum_wage_state: null,
              minimum_wage_effective_month: null,
              minimum_wage_effective_year: null,
            }
          }
          return { ...prev, salary_details: list }
        })
      } else {
        api('/minimum-wages/lookup', { candidate_id: cId, month: updatedMonth, year: updatedYear, state: targetState })
          .then((res) => {
            setEditedData((prev) => {
              const list = [...prev.salary_details]
              const idx = typeof idOrIdx === 'number' ? idOrIdx : list.findIndex((s) => s.id === idOrIdx)
              if (idx >= 0) {
                list[idx] = {
                  ...list[idx],
                  minimum_wage: res.minimum_wage,
                  minimum_wage_state: res.state,
                  minimum_wage_effective_month: res.effective_month,
                  minimum_wage_effective_year: res.effective_year,
                }
              }
              return { ...prev, salary_details: list }
            })
          })
          .catch((err) => console.warn('Could not auto-fetch minimum wage for correction:', err))
      }
    }
  }

  const handleAddSalary = (targetEmpId = null) => {
    if (editedData.salary_details.length >= 12) return
    const empId =
      targetEmpId ||
      editedData.salary_details[editedData.salary_details.length - 1]?.employer_id ||
      editedData.employers?.[0]?.id ||
      'emp_1'
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
          minimum_wage: '',
          minimum_wage_state: '',
          minimum_wage_effective_month: null,
          minimum_wage_effective_year: null,
        },
      ],
    }))
    setHasUnsavedChanges(true)

    const emp = (editedData.employer_details || []).find((e) => e.id === empId) || (editedData.employer_details || [])[0]
    const targetState = (emp?.work_state && (emp?.work_state_detection_status === 'IDENTIFIED' || !emp?.work_state_detection_status)) ? emp.work_state : null
    const cId = candDetail?.candidate_id || sel.cand
    if (cId && nextPeriod.month && nextPeriod.year && targetState) {
      api('/minimum-wages/lookup', { candidate_id: cId, month: nextPeriod.month, year: nextPeriod.year, state: targetState })
        .then((res) => {
          setEditedData((prev) => {
            const list = [...prev.salary_details]
            const lastIdx = list.length - 1
            if (lastIdx >= 0) {
              list[lastIdx] = {
                ...list[lastIdx],
                minimum_wage: res.minimum_wage,
                minimum_wage_state: res.state,
                minimum_wage_effective_month: res.effective_month,
                minimum_wage_effective_year: res.effective_year,
              }
            }
            return { ...prev, salary_details: list }
          })
        })
        .catch((err) => console.warn('Could not auto-fetch minimum wage for added row:', err))
    }
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

  const handleSaveCorrections = async () => {
    if (!sel.cand) return
    setSavingCorrections(true)
    try {
      await api(`/candidates/${sel.cand}/audit/l2-review/corrections`, null, {
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
      const updatedStmt = await api(`/candidates/${sel.cand}/audit/statement`)
      setStatementData(updatedStmt)
    } catch (err) {
      showToast(err.message || 'Failed to save corrections.', 'error')
    } finally {
      setSavingCorrections(false)
    }
  }

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
  // 6. Approval Workflow
  // ---------------------------------------------------------------------------
  const handleApprove = async () => {
    if (!sel.cand) return
    setApproving(true)
    try {
      const payload = {
        remarks: approveRemarks || `${config.roleLabel} verified and approved placement audit.`,
      }
      if (level === 'L2' && hasUnsavedChanges) {
        payload.corrections = {
          employer_details: editedData.employer_details,
          salary_details: editedData.salary_details,
          remarks: editedData.remarks,
          correction_notes: 'L2 corrections saved during approval',
        }
      }
      if (level === 'L3') {
        payload.reviewed_documents = docReviews
      }

      await api(config.approveEndpoint(sel.cand), null, {
        method: 'POST',
        body: JSON.stringify(payload),
      })

      showToast(`Placement audit ${level === 'L5' ? 'sanctioned' : 'approved'} successfully!`, 'success')
      setApproveModalOpen(false)
      setApproveRemarks('')
      setHasUnsavedChanges(false)
      setIsEditMode(false)

      // Reload updated candidate data & refresh summary
      await loadCandidateData(sel.cand)
      fetchDashboardSummary(sel.state)
    } catch (err) {
      showToast(err.message || 'Approval failed.', 'error')
    } finally {
      setApproving(false)
    }
  }

  // ---------------------------------------------------------------------------
  // 7. Unified Return / Reject Decision Workflow (L2, L3, L4, L5)
  // ---------------------------------------------------------------------------
  const handleDecisionSubmit = async ({ action, destination, reason, remarks }) => {
    if (!sel.cand) return
    setActionProcessing(true)
    try {
      let endpoint = ''
      let bodyPayload = {}

      if (level === 'L2') {
        endpoint = `/candidates/${sel.cand}/audit/l2-review/return-to-l1`
        bodyPayload = { return_reason: reason, remarks: remarks || undefined }
      } else if (level === 'L3') {
        endpoint = `/candidates/${sel.cand}/audit/l3-review/return`
        bodyPayload = { destination: destination || 'L1', return_reason: reason, remarks: remarks || undefined }
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

      const targetDest = res?.destination || destination || 'L1'
      const destLabels = {
        L1: 'L1 (Placement Coordinator)',
        L2: 'L2 (Center Head)',
        L3: 'L3 (COPS)',
        L4: 'L4 (Business Leader)',
      }
      const destLabel = destLabels[targetDest] || targetDest
      showToast(res?.message || `Candidate dossier returned to ${destLabel} for corrections.`, 'warning')

      setDecisionModalOpen(false)
      setHasUnsavedChanges(false)
      setIsEditMode(false)

      await loadCandidateData(sel.cand)
      fetchDashboardSummary(sel.state)
      if (activeCardFilter) {
        fetchCardCandidates(activeCardFilter, cardCandPage, cardCandSearch, sel.state)
      }
    } catch (err) {
      showToast(err.message || 'Action failed. Please retry.', 'error')
      throw err
    } finally {
      setActionProcessing(false)
    }
  }

  // ---------------------------------------------------------------------------
  // 10. Checklist & Approval Readiness Calculations
  // ---------------------------------------------------------------------------
  const employersList =
    statementData?.employer_details ||
    (statementData?.employer_name ? [{ id: 'emp_1', employer_name: statementData.employer_name }] : [])
  const getEmployerName = (empId) => {
    if (!empId) return null
    const emp = employersList.find((e) => e.id === empId)
    return emp?.employer_name || null
  }

  const successDocs = documents.filter((d) => d.upload_status === 'SUCCESS')
  const appointmentDocs = successDocs.filter((d) => d.document_type === 'APPOINTMENT_LETTER')
  const salaryDocs = successDocs.filter((d) => d.document_type === 'SALARY_SLIP')
  const bankDocs = successDocs.filter((d) => d.document_type === 'BANK_STATEMENT')
  const otherDocs = successDocs.filter(
    (d) => !['APPOINTMENT_LETTER', 'SALARY_SLIP', 'BANK_STATEMENT'].includes(d.document_type)
  )

  const requiredAppointmentCount = Math.max(1, employersList.length)
  const reviewedAppointmentCount = appointmentDocs.filter((d) => docReviews[String(d.id)]?.reviewed).length
  const allAppointmentsReviewed =
    appointmentDocs.length >= requiredAppointmentCount &&
    appointmentDocs.every((d) => docReviews[String(d.id)]?.reviewed)

  const reviewedSalaryCount = salaryDocs.filter((d) => docReviews[String(d.id)]?.reviewed).length
  const reviewedBankCount = bankDocs.filter((d) => docReviews[String(d.id)]?.reviewed).length

  const hasConsolidatedBank = bankDocs.some((d) => d.is_consolidated)
  const allBankReviewed =
    bankDocs.length > 0 &&
    bankDocs.every((d) => docReviews[String(d.id)]?.reviewed) &&
    (bankDocs.length >= 3 || hasConsolidatedBank)

  const allMandatoryReviewed =
    allAppointmentsReviewed && reviewedSalaryCount >= 3 && allBankReviewed

  const auditStatus = (statementData?.audit_status || '').toUpperCase()
  const cpassStatus = (statementData?.cpass_status || '').toUpperCase()
  const reviewStages = statementData?.review_stages || {}

  const activeReturn =
    statementData?.active_return ||
    (auditStatus === 'RETURNED_TO_L1' || cpassStatus === 'RETURNED_TO_L1'
      ? statementData?.return_to_l1
      : null)
  const returnDestination =
    activeReturn?.destination ||
    (auditStatus === 'RETURNED_TO_L1' || cpassStatus === 'RETURNED_TO_L1' ? 'L1' : null)

  const isReturnedToL1 =
    returnDestination === 'L1' ||
    auditStatus === 'RETURNED_TO_L1' ||
    cpassStatus === 'RETURNED_TO_L1' ||
    reviewStages.ch_status === 'Returned to L1'

  // Is candidate currently returned and awaiting action?
  const isReturned = Boolean(activeReturn || isReturnedToL1)

  // Is candidate currently returned to the current review level?
  const isReturnedToCurrentLevel = activeReturn?.destination === level

  // Is candidate returned to an upstream/downstream level and waiting there?
  const isWaitingOnOtherLevelReturn = isReturned && !isReturnedToCurrentLevel

  const isRejected =
    auditStatus.includes('REJECT') ||
    cpassStatus.includes('REJECT') ||
    Boolean(statementData?.signoff_details?.rejection_reason)

  // Stage checks
  const isL1Submitted = auditStatus === 'SUBMITTED' || auditStatus === 'RECOMMENDED' || auditStatus === 'VERIFIED' || auditStatus === 'APPROVED' || cpassStatus !== 'PENDING'
  const isL2Approved =
    cpassStatus === 'L2_APPROVED' ||
    cpassStatus === 'VERIFIED' ||
    cpassStatus === 'BL_APPROVED' ||
    cpassStatus === 'APPROVED' ||
    reviewStages.ch_status === 'Approved' ||
    reviewStages.ch_status === 'Recommended'
  const isL3Verified =
    cpassStatus === 'VERIFIED' ||
    cpassStatus === 'BL_APPROVED' ||
    cpassStatus === 'APPROVED' ||
    reviewStages.cops_status === 'Verified'
  const isL4Approved =
    cpassStatus === 'BL_APPROVED' ||
    cpassStatus === 'APPROVED' ||
    reviewStages.bl_status === 'Approved'
  const isL5Sanctioned =
    cpassStatus === 'APPROVED' &&
    auditStatus === 'APPROVED' &&
    reviewStages.ceo_status === 'Approved'
  const isFinalApproved = isL5Sanctioned

  const isAlreadyApproved =
    level === 'L2'
      ? isL2Approved
      : level === 'L3'
      ? isL3Verified
      : level === 'L4'
      ? isL4Approved
      : isL5Sanctioned

  const hasActiveHold = Boolean(candDetail?.has_active_hold)

  // Level-specific approval capability
  let canApprove = false
  let approvalBlockReason = ''

  if (loadingCandidate) {
    canApprove = false
    approvalBlockReason = 'Loading candidate placement dossier…'
  } else if (!sel.cand || !statementData) {
    canApprove = false
    approvalBlockReason = 'Select a candidate to review.'
  } else if (hasActiveHold) {
    canApprove = false
    approvalBlockReason = 'Approval blocked: Candidate has an active administrative hold.'
  } else if (isReturnedToL1) {
    canApprove = false
    approvalBlockReason = 'Candidate is returned to L1 for corrections. Awaiting coordinator resubmission.'
  } else if (isWaitingOnOtherLevelReturn) {
    canApprove = false
    approvalBlockReason = `Candidate is returned to ${returnDestination || 'earlier stage'} for corrections. Awaiting action.`
  } else if (isRejected) {
    canApprove = false
    approvalBlockReason = 'Candidate placement audit has been rejected.'
  } else if (isAlreadyApproved) {
    canApprove = false
    approvalBlockReason = `${config.roleLabel} approval already recorded.`
  } else if (level === 'L2') {
    if (!isL1Submitted) {
      canApprove = false
      approvalBlockReason = 'Waiting for L1 Coordinator to finalize and submit placement statement.'
    } else if (!allMandatoryReviewed) {
      canApprove = false
      approvalBlockReason = 'Review and mark all mandatory documents on the right before approving.'
    } else {
      canApprove = true
    }
  } else if (level === 'L3') {
    if (!isL2Approved) {
      canApprove = false
      approvalBlockReason = 'Awaiting L2 Center Head recommendation before COPS review.'
    } else if (!allMandatoryReviewed) {
      canApprove = false
      approvalBlockReason = 'Verify and mark all mandatory document evidence before endorsing.'
    } else {
      canApprove = true
    }
  } else if (level === 'L4') {
    if (!isL3Verified) {
      canApprove = false
      approvalBlockReason = 'Awaiting L3 COPS verification & endorsement before BL review.'
    } else {
      canApprove = true
    }
  } else if (level === 'L5') {
    if (!isL4Approved) {
      canApprove = false
      approvalBlockReason = 'Awaiting L4 Business Leader approval before CEO sanction.'
    } else {
      canApprove = true
    }
  }

  return (
    <ErrorBoundary>
      <div className="l2-dashboard">
        {/* Metrics Error Banner */}
        {summaryError && (
          <div
            className="l1-banner-warning l1-no-print"
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
             5 Compact Metric Cards Row
             -------------------------------------------------------------------- */}
        <section className="l2-compact-summary-row l1-no-print" aria-label={`${config.roleLabel} Candidate Review Summary`}>
          {config.metrics.map((card) => {
            const countVal = card.getCount(summaryData)
            const isActive = activeCardFilter === card.filterKey
            return (
              <div
                key={card.key}
                className={`l2-compact-card ${card.className} ${isActive ? 'active' : ''}`}
                onClick={() => handleCardClick(card.filterKey)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && handleCardClick(card.filterKey)}
                aria-label={`${card.title} candidates: ${loadingSummary ? 'Loading' : countVal}. Click to view list.`}
              >
                <div className="l2-compact-card-meta">
                  <span className="l2-compact-card-icon">{card.icon}</span>
                  <span className="l2-compact-card-title">{card.title}</span>
                </div>
                <div className="l2-compact-card-count">
                  {loadingSummary ? '…' : summaryError ? '—' : countVal}
                </div>
              </div>
            )
          })}
        </section>

        {/* --------------------------------------------------------------------
             Candidate Selection Pipeline Panel
             -------------------------------------------------------------------- */}
        <section className="l2-selector-panel l1-no-print">
          <div className="l2-selector-header">
            <h3>
              <span className="l2-step-indicator">1</span>
              {config.headerTitle}
            </h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
              {sel.cand && statementData && (
                <>
                  <span
                    className={`l2-status-badge ${isReturnedToL1 ? 'draft' : isL1Submitted ? 'submitted' : 'draft'}`}
                    style={isReturnedToL1 ? { background: '#fef3c7', color: '#92400e', borderColor: '#fcd34d' } : {}}
                  >
                    L1 Audit: {auditStatus || 'DRAFT'}
                  </span>
                  <span
                    className={`l2-status-badge ${isReturnedToL1 ? 'draft' : isAlreadyApproved ? 'approved' : 'pending'}`}
                    style={isReturnedToL1 ? { background: '#fef3c7', color: '#92400e', borderColor: '#fcd34d' } : {}}
                  >
                    Review: {isAlreadyApproved ? config.approvedBadgeText : isReturned ? `↩ RETURNED TO ${returnDestination || 'L1'}` : isRejected ? '✕ REJECTED' : 'Pending Review'}
                  </span>
                </>
              )}
              {(sel.state || sel.tc || sel.cand) && (
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
            {/* 1. State Selector */}
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
                  {level === 'L3' && (
                    <option value="">All States (National Scope)</option>
                  )}
                  {level === 'L4' && (
                    <option value="">All Assigned States</option>
                  )}
                  {level === 'L5' && (
                    <option value="">All States (National Scope)</option>
                  )}
                  {level === 'L2' && (
                    <option value="">
                      {lists.state.length === 0 ? 'No assigned states…' : 'Select State…'}
                    </option>
                  )}
                  {lists.state.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                <span className="l2-select-icon">▼</span>
              </div>
            </div>

            {/* 2. Training Centre Selector */}
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

            {/* 3. Sanction Order Selector */}
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

            {/* 4. Batch Selector */}
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

            {/* 5. Candidate Selector */}
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
             Candidate List Popup / Modal (Opened when an audit card is clicked)
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
            aria-labelledby="review-popup-title"
          >
            <div className="l1-cand-popup-dialog" onClick={(e) => e.stopPropagation()}>
              {/* Modal Header */}
              <div className="l1-cand-popup-header">
                <div className="l1-cand-popup-title-group">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className="l1-cand-popup-icon">
                      {config.metrics.find((m) => m.filterKey === activeCardFilter)?.icon || '👥'}
                    </span>
                    <h3 id="review-popup-title">
                      {config.metrics.find((m) => m.filterKey === activeCardFilter)?.title || 'Candidates'}
                    </h3>
                    <span className="l1-cand-popup-count-badge">
                      {cardCandLoading ? '…' : cardCandTotal}
                    </span>
                  </div>
                  <p className="l1-cand-popup-sub">
                    {config.metrics.find((m) => m.filterKey === activeCardFilter)?.description || 'Candidate records matching this filter.'}
                    {sel.state ? ` (${sel.state})` : (level === 'L4' ? ' (All Assigned States)' : ' (National Scope)')}
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
                    placeholder="Search by Candidate Name, Candidate ID, Batch, or Centre…"
                    aria-label="Search candidates"
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
                        : 'No candidate records match this status category in the selected scope.'}
                    </p>
                  </div>
                ) : (
                  <div className="l1-popup-table-scroll">
                    <table className="l1-cand-table">
                      <colgroup>
                        <col className="col-cand-name" />
                        <col className="col-cand-state" />
                        <col className="col-cand-stage" />
                        <col className="col-cand-stage" />
                        <col className="col-cand-stage" />
                        <col className="col-cand-action" />
                      </colgroup>
                      <thead>
                        <tr>
                          <th className="l1-th-name">Candidate Name &amp; ID</th>
                          <th className="l1-th-state">State</th>
                          <th className="l1-th-stage">CH</th>
                          <th className="l1-th-stage">COPS</th>
                          <th className="l1-th-stage">BL</th>
                          <th className="l1-th-action">Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {cardCandidates.map((cand) => (
                          <tr
                            key={cand.candidate_id}
                            className={sel.cand === cand.candidate_id ? 'active-row' : ''}
                          >
                            <td className="l1-td-name">
                              <strong>{cand.name}</strong>
                              <div className="l1-cand-id-small">{cand.candidate_id}</div>
                            </td>
                            <td className="l1-td-state">
                              <span className="l1-cand-state">{cand.state_name || cand.state || '—'}</span>
                            </td>
                            <td className="l1-td-stage">
                              <span className={getStageBadgeClass(cand.ch_status)}>
                                {formatStageStatus(cand.ch_status)}
                              </span>
                            </td>
                            <td className="l1-td-stage">
                              <span className={getStageBadgeClass(cand.cops_status)}>
                                {formatStageStatus(cand.cops_status)}
                              </span>
                            </td>
                            <td className="l1-td-stage">
                              <span className={getStageBadgeClass(cand.bl_status)}>
                                {formatStageStatus(cand.bl_status)}
                              </span>
                            </td>
                            <td className="l1-td-action">
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

              {/* Modal Footer */}
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

        {/* Banner if Candidate is Returned */}
        {sel.cand && isReturned && (
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
              <strong>
                {isReturnedToCurrentLevel
                  ? `⚠️ Candidate Dossier Returned to ${config.roleLabel} for Re-Review`
                  : `⚠️ Candidate Dossier Returned to ${returnDestination || 'L1'} for Corrections`}
              </strong>
              <div style={{ fontSize: '13px', marginTop: '4px' }}>
                {isReturnedToCurrentLevel
                  ? `This placement audit has been returned to ${config.roleLabel} by ${activeReturn?.returned_by_stage || activeReturn?.stage || 'higher authority'}. Please review, update if necessary, and submit your decision.`
                  : `This placement audit has been returned to ${returnDestination || 'earlier stage'} for corrections. Further approvals are paused until updated records are resubmitted.`}
                {(activeReturn?.return_reason || activeReturn?.reason || statementData?.return_to_l1?.return_reason || statementData?.return_reason) && (
                  <div style={{ marginTop: '2px', fontStyle: 'italic' }}>
                    Reason: "{activeReturn?.return_reason || activeReturn?.reason || statementData?.return_to_l1?.return_reason || statementData?.return_reason}"
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Banner if Candidate is Rejected */}
        {sel.cand && isRejected && (
          <div
            style={{
              margin: '0 24px 16px',
              padding: '12px 18px',
              background: '#fee2e2',
              border: '1px solid #fca5a5',
              borderRadius: '8px',
              color: '#991b1b',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '12px',
            }}
          >
            <div>
              <strong>✕ Candidate Placement Dossier Rejected</strong>
              <div style={{ fontSize: '13px', marginTop: '4px' }}>
                This candidate's placement audit has been rejected.
                {(statementData?.signoff_details?.rejection_reason || statementData?.rejection_reason) && (
                  <div style={{ marginTop: '2px', fontStyle: 'italic' }}>
                    Reason: "{statementData.signoff_details?.rejection_reason || statementData.rejection_reason}"
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* --------------------------------------------------------------------
             Workspace: 2-Panel Side-by-Side Review Workspace
             -------------------------------------------------------------------- */}
        {!sel.cand ? (
          <section className="l2-empty-state l1-no-print">
            <div className="l2-empty-icon">🏢</div>
            <h3>Select a Candidate to Begin {config.roleLabel} Review</h3>
            <p>
              Select a State, Training Centre, Sanction Order, Batch, and Candidate from the pipeline above to view the placement audit statement and verify associated document evidence side-by-side.
            </p>
          </section>
        ) : loadingCandidate ? (
          <section className="l2-empty-state loading l1-no-print">
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
            {/* Left Panel: Placement Audit Statement */}
            <section className="l2-panel l2-statement-panel" aria-label="Candidate Placement Statement">
              <div className="l2-panel-header l1-no-print">
                <h3 className="l2-panel-title">
                  <span>📄</span>
                  <span>Placement Audit Statement</span>
                  {config.canEditStatement && isEditMode ? (
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

              <div className="l2-panel-body" ref={statementBodyRef}>
                <PlacementAuditStatement
                  statementData={statementData}
                  isEditMode={config.canEditStatement ? isEditMode : false}
                  editedData={editedData}
                  onUpdateEmployer={config.canEditStatement ? handleUpdateEmployer : undefined}
                  onAddEmployer={config.canEditStatement ? handleAddEmployer : undefined}
                  onRemoveEmployer={config.canEditStatement ? handleRemoveEmployer : undefined}
                  onUpdateSalary={config.canEditStatement ? handleUpdateSalary : undefined}
                  onAddSalary={config.canEditStatement ? handleAddSalary : undefined}
                  onRemoveSalary={config.canEditStatement ? handleRemoveSalary : undefined}
                  onUpdateRemarks={config.canEditStatement ? handleUpdateRemarks : undefined}
                  l1OriginalData={statementData?.l1_original_submission || statementData?.audit?.signoff_details?.l1_original_submission}
                  hasUnsavedChanges={hasUnsavedChanges}
                  showModalWrapper={false}
                />
              </div>
            </section>

            {/* Right Panel: Candidate Documents & Inline Previewer */}
            <section className="l2-panel l2-doc-panel l1-no-print" aria-label="Candidate Document Evidence">
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
                )}
              </div>

              <div className="l2-panel-body" ref={docBodyRef} style={{ padding: previewDoc ? 0 : '16px' }}>
                {previewDoc ? (
                  <Suspense
                    fallback={
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '340px', gap: '12px' }}>
                        <div className="cpass-mini-spinner" style={{ width: '28px', height: '28px' }} />
                        <span style={{ fontSize: '13.5px', color: '#64748b', fontWeight: 500 }}>Initializing Document Viewer…</span>
                      </div>
                    }
                  >
                    <PdfViewer
                      fileUrl={previewBlobUrl}
                      fileName={previewDoc.file_name}
                      fileMeta={previewDoc.type || previewDoc.category || 'Document Evidence'}
                      mimeType={previewDoc.mime_type}
                      isLoading={loadingPreview}
                      errorMessage={previewError}
                      isReviewed={Boolean(docReviews[String(previewDoc.id)]?.reviewed)}
                      reviewedAt={docReviews[String(previewDoc.id)]?.reviewed_at}
                      onToggleReview={config.hasChecklistToggle ? (checked) => handleToggleDocReview(previewDoc.id, checked) : undefined}
                      onDownload={() => downloadDocument(sel.cand, previewDoc.id, previewDoc.file_name)}
                      onClose={handleClosePreview}
                    />
                  </Suspense>
                ) : (
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
                              )}
                            </div>
                            <div className="l2-doc-actions">
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
                            </div>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid #f1f5f9', paddingTop: '8px' }}>
                            <label className={`l2-review-checkbox-label ${docReviews[String(doc.id)]?.reviewed ? 'reviewed' : 'pending'}`}>
                              <input
                                type="checkbox"
                                checked={Boolean(docReviews[String(doc.id)]?.reviewed)}
                                disabled={!config.hasChecklistToggle}
                                onChange={(e) => handleToggleDocReview(doc.id, e.target.checked)}
                              />
                              <span>{docReviews[String(doc.id)]?.reviewed ? '✓ Verified in Audit' : 'Mark Reviewed'}</span>
                            </label>
                            {docReviews[String(doc.id)]?.reviewed && (
                              <span style={{ fontSize: '11px', color: '#166534', fontWeight: 600 }}>
                                {docReviews[String(doc.id)].reviewed_by ? `By ${docReviews[String(doc.id)].reviewed_by} on ` : 'Reviewed on '}
                                {new Date(docReviews[String(doc.id)].reviewed_at).toLocaleDateString()}
                              </span>
                            )}
                          </div>
                        </div>
                      ))
                    ) : (
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
                    )}

                    {/* Salary Slips Section */}
                    <div className="l2-evidence-category-header">
                      <span>2. Monthly Salary Slips (Min 3 Required)</span>
                    </div>

                    {salaryDocs.map((doc) => {
                      const empSeq = getEmployerDocumentSequence(doc, successDocs)
                      return (
                        <div key={doc.id} className="l2-doc-card">
                          <div className="l2-doc-card-top">
                            <span className="l2-doc-type-icon">₹</span>
                            <div className="l2-doc-meta">
                              <span className="l2-doc-name">{doc.file_name}</span>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', marginTop: '2px' }}>
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
                              )}
                            </div>
                            <div className="l2-doc-actions">
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
                            </div>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid #f1f5f9', paddingTop: '8px' }}>
                            <label className={`l2-review-checkbox-label ${docReviews[String(doc.id)]?.reviewed ? 'reviewed' : 'pending'}`}>
                              <input
                                type="checkbox"
                                checked={Boolean(docReviews[String(doc.id)]?.reviewed)}
                                disabled={!config.hasChecklistToggle}
                                onChange={(e) => handleToggleDocReview(doc.id, e.target.checked)}
                              />
                              <span>{docReviews[String(doc.id)]?.reviewed ? '✓ Verified in Audit' : 'Mark Reviewed'}</span>
                            </label>
                            {docReviews[String(doc.id)]?.reviewed && (
                              <span style={{ fontSize: '11px', color: '#166534', fontWeight: 600 }}>
                                {docReviews[String(doc.id)].reviewed_by ? `By ${docReviews[String(doc.id)].reviewed_by} on ` : 'Reviewed on '}
                                {new Date(docReviews[String(doc.id)].reviewed_at).toLocaleDateString()}
                              </span>
                            )}
                          </div>
                        </div>
                      )
                    })}
                    {salaryDocs.length < 3 && (
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
                                  {doc.reporting_month
                                    ? `${MONTH_NAMES[doc.reporting_month - 1] || doc.reporting_month} ${doc.reporting_year || ''}`
                                    : `Month ${idx + 1}`} • Verified in Drive
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
                              disabled={!config.hasChecklistToggle}
                              onChange={(e) => handleToggleDocReview(doc.id, e.target.checked)}
                            />
                            <span>{docReviews[String(doc.id)]?.reviewed ? '✓ Verified in Audit' : 'Mark Reviewed'}</span>
                          </label>
                          {docReviews[String(doc.id)]?.reviewed && (
                            <span style={{ fontSize: '11px', color: '#166534', fontWeight: 600 }}>
                              {docReviews[String(doc.id)].reviewed_by ? `By ${docReviews[String(doc.id)].reviewed_by} on ` : 'Reviewed on '}
                              {new Date(docReviews[String(doc.id)].reviewed_at).toLocaleDateString()}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                    {(bankDocs.length === 0 || (!hasConsolidatedBank && bankDocs.length < 3)) && (
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
                    )}

                    {/* Supporting / Other Documents Section */}
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
                      <>
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
                                  disabled={!config.hasChecklistToggle}
                                  onChange={(e) => handleToggleDocReview(doc.id, e.target.checked)}
                                />
                                <span>{docReviews[String(doc.id)]?.reviewed ? '✓ Verified in Audit' : 'Mark Reviewed'}</span>
                              </label>
                              {docReviews[String(doc.id)]?.reviewed && (
                                <span style={{ fontSize: '11px', color: '#166534', fontWeight: 600 }}>
                                  {docReviews[String(doc.id)].reviewed_by ? `By ${docReviews[String(doc.id)].reviewed_by} on ` : 'Reviewed on '}
                                  {new Date(docReviews[String(doc.id)].reviewed_at).toLocaleDateString()}
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

        {/* --------------------------------------------------------------------
             Fixed Bottom Review Controls Dock
             -------------------------------------------------------------------- */}
        {sel.cand && statementData && (
          <footer className="l2-bottom-dock l1-no-print">
            <div className="l2-dock-summary">
              <span className="l2-dock-title">
                {isAlreadyApproved ? (
                  <span style={{ color: '#166534' }}>{config.approvedDockTitle}</span>
                ) : (
                  <span>{config.dockRoleTitle}</span>
                )}
                <span
                  className={`l2-status-badge ${allMandatoryReviewed ? 'approved' : 'pending'}`}
                  style={{ fontSize: '11px', padding: '2px 8px' }}
                >
                  Checklist: {reviewedAppointmentCount + reviewedSalaryCount + reviewedBankCount} of{' '}
                  {requiredAppointmentCount +
                    Math.max(3, salaryDocs.length) +
                    (hasConsolidatedBank ? bankDocs.length : Math.max(3, bankDocs.length))}{' '}
                  Reviewed
                </span>
              </span>
              <span className="l2-dock-sub">
                {isAlreadyApproved
                  ? 'Audit has been officially endorsed at this stage. Records finalized.'
                  : approvalBlockReason || 'All mandatory checks satisfied. Ready for sign-off.'}
              </span>
            </div>

            <div className="l2-dock-buttons">
              {/* L2 Edit Mode Controls */}
              {config.canEditStatement && !isAlreadyApproved && (
                <button
                  type="button"
                  className="l2-btn-edit"
                  onClick={() => setIsEditMode(!isEditMode)}
                >
                  {isEditMode ? '✕ Cancel Edit' : '✏️ Edit Statement'}
                </button>
              )}

              {config.canEditStatement && hasUnsavedChanges && (
                <button
                  type="button"
                  className="l2-btn-revert"
                  onClick={() => setRevertModalOpen(true)}
                >
                  ↩ Revert Edits
                </button>
              )}

              {config.canEditStatement && hasUnsavedChanges && (
                <button
                  type="button"
                  className="l2-btn-save"
                  onClick={handleSaveCorrections}
                  disabled={savingCorrections}
                >
                  💾 {savingCorrections ? 'Saving…' : 'Save Edits'}
                </button>
              )}

              {/* Unified Return / Reject Dossier Button (L2, L3, L4, L5) */}
              <button
                type="button"
                className="l2-btn-return-reject"
                disabled={!sel.cand || loadingCandidate || isFinalApproved || isRejected || isReturned || actionProcessing}
                onClick={() => setDecisionModalOpen(true)}
                title={
                  isFinalApproved
                    ? 'Dossier has received final executive approval'
                    : isRejected
                    ? 'Candidate has been rejected and sent back for corrections'
                    : 'Reject and send back candidate dossier for corrections'
                }
              >
                ↩ Reject & Send Back
              </button>

              {/* Approve Button */}
              <button
                type="button"
                className="l2-btn-approve"
                disabled={!canApprove || approving}
                onClick={() => setApproveModalOpen(true)}
                title={isAlreadyApproved ? 'Statement already approved' : approvalBlockReason || 'Endorse placement audit'}
              >
                {isAlreadyApproved ? `✓ ${config.approvedBadgeText}` : config.approveBtnText}
              </button>
            </div>
          </footer>
        )}

        {/* --------------------------------------------------------------------
             Modal: Revert Confirmation (L2 only)
             -------------------------------------------------------------------- */}
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

        {/* --------------------------------------------------------------------
             Modal: Unsaved Changes Candidate Switch Warning
             -------------------------------------------------------------------- */}
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

        {/* --------------------------------------------------------------------
             Modal: Approval Confirmation
             -------------------------------------------------------------------- */}
        {approveModalOpen && (
          <div className="l2-modal-overlay" role="dialog" aria-modal="true">
            <div className="l2-modal-card" style={{ maxWidth: 540 }}>
              <div className="l2-modal-header">
                <h4>{config.approveModalTitle}</h4>
                <button type="button" onClick={() => setApproveModalOpen(false)}>✕</button>
              </div>
              <div className="l2-modal-body">
                <p style={{ margin: '0 0 12px' }}>
                  You are officially endorsing the placement audit for <strong>{candDetail?.first_name} {candDetail?.last_name}</strong> (<code>{sel.cand}</code>) as <strong>{config.approveModalRoleName}</strong>.
                </p>
                <div style={{ background: '#f8fafc', padding: '10px 14px', borderRadius: '6px', fontSize: '13px', marginBottom: '14px' }}>
                  <div>✓ Appointment / Offer Letter verified</div>
                  <div>✓ Monthly salary pay slips verified</div>
                  <div>✓ Bank credit entries verified</div>
                  <div>✓ Statutory compliance &amp; employer records validated</div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <label style={{ fontSize: '12px', fontWeight: 600, color: '#475569' }}>
                    Approval Remarks &amp; Compliance Notes (Optional)
                  </label>
                  <textarea
                    rows={3}
                    placeholder="Enter approval endorsement notes..."
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
                  {approving ? 'Recording Approval…' : 'Confirm Approval'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* --------------------------------------------------------------------
             Unified Decision Modal: Option A (Return) & Option B (Reject)
             -------------------------------------------------------------------- */}
        <FlexibleReturnModal
          isOpen={decisionModalOpen}
          onClose={() => setDecisionModalOpen(false)}
          onSubmit={handleDecisionSubmit}
          level={level}
          currentRole={level === 'L5' ? 'L5_CEO' : level === 'L4' ? 'L4_LEADER' : level === 'L3' ? 'L3_COPS' : 'L2_MANAGER'}
          candidateName={candDetail ? `${candDetail.first_name || ''} ${candDetail.last_name || ''}`.trim() : (statementData?.candidate_name || '')}
          candidateId={sel.cand}
        />

        {/* --------------------------------------------------------------------
             Toast Notification
             -------------------------------------------------------------------- */}
        {/* L2 Missing Document Upload Modal */}
        <L2DocumentUploadModal
          isOpen={uploadModalOpen}
          onClose={() => setUploadModalOpen(false)}
          candidateId={sel.cand}
          candidateName={candDetail ? `${candDetail.first_name || ''} ${candDetail.last_name || ''}`.trim() : (statementData?.candidate_name || '')}
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
    </ErrorBoundary>
  )
}