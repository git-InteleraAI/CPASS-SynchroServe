import { useEffect, useRef, useState, useCallback } from 'react'
import { api, downloadDocument } from '../lib/api'
import synchroLogo from '../../assets/SynchroServeLogoHD.png'
import './L1Home.css'
import ErrorBoundary from '../components/ErrorBoundary'
import PlacementAuditStatement from '../components/PlacementAuditStatement'
import {
  MONTH_NAMES,
  getEmployerSalarySequence,
  formatEmployerSalaryLabel,
  findPreviousSalaryRecordForEmployer,
  calculateNextSalaryPeriodForEmployer
} from '../lib/salarySequenceHelper'
import {
  isDocConsolidated,
  getDocCoveredMonths,
  getBankDocumentStatus,
  isBankSlotVisible as isBankSlotVisibleHelper,
  getConsolidatedCoverage as getConsolidatedCoverageHelper
} from '../lib/bankStatementHelper'

const RESET = {
  state: ['tc', 'order', 'batch', 'cand'],
  tc: ['order', 'batch', 'cand'],
  order: ['batch', 'cand'],
  batch: ['cand'],
  cand: [],
}

const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024 // 10 MB
const ALLOWED_EXTENSIONS = ['.pdf', '.png', '.jpg', '.jpeg']

function formatFileSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatL1StageStatus(status) {
  if (!status) return 'Pending'
  const s = String(status).trim()
  if (s.toLowerCase().includes('return')) {
    return 'Rejected'
  }
  return s
}

function getStageBadgeClass(status) {
  const s = (status || '').toLowerCase()
  if (s === 'recommended') return 'l1-stage-badge recommended'
  if (s === 'verified') return 'l1-stage-badge verified'
  if (s === 'approved') return 'l1-stage-badge approved'
  if (s.includes('return') || s === 'rejected') return 'l1-stage-badge rejected'
  return 'l1-stage-badge pending'
}

function validateFile(file) {
  if (!file) return 'No file selected.'
  const ext = '.' + file.name.split('.').pop().toLowerCase()
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    return `Invalid file format (${ext}). Only PDF, PNG, and JPG files are accepted.`
  }
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return `File size (${formatFileSize(file.size)}) exceeds the maximum allowed limit of 10 MB.`
  }
  return null
}

// -----------------------------------------------------------------------------
// Accessible Custom File Upload Control Component
// -----------------------------------------------------------------------------
function FileUploadControl({
  file,
  fileName,
  fileSize,
  error,
  onSelect,
  onRemove,
  label = 'Choose Document',
  helperText = 'PDF, PNG, JPG (up to 10MB)',
  stagedLabel = 'Staged locally',
  disabled = false,
  isUnavailable = false,
  onMarkNotAvailable,
  onResetAvailability,
  disableNotAvailable = false,
  notAvailableTitle,
}) {
  const [isDragOver, setIsDragOver] = useState(false)
  const inputRef = useRef(null)

  const handleDragOver = (e) => {
    e.preventDefault()
    if (!disabled && !isUnavailable) setIsDragOver(true)
  }

  const handleDragLeave = (e) => {
    e.preventDefault()
    setIsDragOver(false)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setIsDragOver(false)
    if (disabled || isUnavailable) return
    const droppedFile = e.dataTransfer?.files?.[0]
    if (droppedFile) onSelect(droppedFile)
  }

  if (file) {
    return (
      <div className="l1-staged-file-card">
        <div className="l1-file-info">
          <div className="l1-file-icon-box">📄</div>
          <div className="l1-file-details">
            <span className="title" title={fileName}>{fileName}</span>
            <span className="meta">{formatFileSize(fileSize)} · <strong style={{ color: 'var(--blue)' }}>{stagedLabel}</strong></span>
          </div>
        </div>
        <div className="l1-btn-group">
          <button
            type="button"
            className="l1-btn-danger-ghost"
            onClick={onRemove}
            title="Remove staged file"
          >
            ✕ Remove
          </button>
        </div>
      </div>
    )
  }

  if (isUnavailable) {
    return (
      <div>
        <div
          className="l1-upload-zone unavailable"
          role="region"
          aria-label={`${label}. Recorded as Not Available.`}
        >
          <div className="l1-upload-prompt">
            <div className="l1-upload-icon na-icon">⚠️</div>
            <div className="l1-upload-text">
              <span className="main">{label}</span>
              <span className="hint">Recorded as Not Available (Candidate status remains Pending)</span>
            </div>
          </div>
          <div className="l1-upload-actions">
            <span className="l1-na-status-badge">⚠️ Not Available</span>
            {onResetAvailability && (
              <button
                type="button"
                className="l1-btn-change-upload"
                onClick={(e) => {
                  e.stopPropagation()
                  onResetAvailability()
                }}
                disabled={disabled}
              >
                Change to Upload
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div
        className={`l1-upload-zone ${isDragOver ? 'dragover' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !disabled && inputRef.current?.click()}
        role="button"
        tabIndex={disabled ? -1 : 0}
        onKeyDown={(e) => {
          if ((e.key === 'Enter' || e.key === ' ') && !disabled) {
            e.preventDefault()
            inputRef.current?.click()
          }
        }}
        aria-label={`${label}. Click or drag file to attach.`}
      >
        <div className="l1-upload-prompt">
          <div className="l1-upload-icon">↑</div>
          <div className="l1-upload-text">
            <span className="main">{label}</span>
            <span className="hint">{helperText}</span>
          </div>
        </div>
        <div className="l1-upload-actions">
          {onMarkNotAvailable && (
            <button
              type="button"
              className="l1-btn-not-available"
              onClick={(e) => {
                e.stopPropagation()
                onMarkNotAvailable()
              }}
              disabled={disabled || disableNotAvailable}
              title={notAvailableTitle || 'Record that payslip is unavailable'}
            >
              Not Available
            </button>
          )}
          <button
            type="button"
            className="l1-btn-choose"
            tabIndex={-1}
            onClick={(e) => {
              e.stopPropagation()
              if (!disabled) inputRef.current?.click()
            }}
          >
            Browse File
          </button>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg"
          style={{ display: 'none' }}
          disabled={disabled}
          onChange={(e) => {
            if (e.target.files?.[0]) {
              onSelect(e.target.files[0])
              e.target.value = '' // Reset so same file can be re-selected if needed
            }
          }}
        />
      </div>
      {error && (
        <div className="error" style={{ fontSize: '0.82rem', marginTop: '4px', color: 'var(--danger)' }}>
          {error}
        </div>
      )}
    </div>
  )
}

// -----------------------------------------------------------------------------
// Placement Audit Default State Creators
// -----------------------------------------------------------------------------
function createDefaultEmployer(detail, idOverride) {
  return {
    id: idOverride || `emp_${Date.now()}_1`,
    employer_name: detail?.employer_name || '',
    months_worked: '',
    appointment_date: detail?.appointed_date || '',
    designation: detail?.designation || '',
    place_of_work: detail?.work_location || '',
    monthly_ctc: detail?.monthly_ctc || '',
    minimum_wages: '',
  }
}

function createDefaultSalaryList(year, employerId = 'emp_1') {
  const y = year || new Date().getFullYear()
  return [
    {
      id: `sal_${Date.now()}_1`,
      employer_id: employerId,
      month: 1,
      year: y,
      working_days: 26,
      pay_days: 26,
      leave_days: 0,
      credit_date: '',
      amount_credited: '',
      gross_salary: '',
      deductions: '',
      net_salary: '',
      bank_name: '',
    },
    {
      id: `sal_${Date.now()}_2`,
      employer_id: employerId,
      month: 2,
      year: y,
      working_days: 26,
      pay_days: 26,
      leave_days: 0,
      credit_date: '',
      amount_credited: '',
      gross_salary: '',
      deductions: '',
      net_salary: '',
      bank_name: '',
    },
    {
      id: `sal_${Date.now()}_3`,
      employer_id: employerId,
      month: 3,
      year: y,
      working_days: 26,
      pay_days: 26,
      leave_days: 0,
      credit_date: '',
      amount_credited: '',
      gross_salary: '',
      deductions: '',
      net_salary: '',
      bank_name: '',
    },
  ]
}

function createDefaultDocAudit() {
  return {
    appointment_letter: { available: 'Pending', compliance: 'Under Verification', remarks: '' },
    salary_slip_1: { available: 'Pending', compliance: 'Under Verification', remarks: '' },
    salary_slip_2: { available: 'Pending', compliance: 'Under Verification', remarks: '' },
    salary_slip_3: { available: 'Pending', compliance: 'Under Verification', remarks: '' },
    bank_statement_1: { available: 'Pending', compliance: 'Under Verification', remarks: '' },
    bank_statement_2: { available: 'Pending', compliance: 'Under Verification', remarks: '' },
    bank_statement_3: { available: 'Pending', compliance: 'Under Verification', remarks: '' },
    other_document: { available: 'Pending', compliance: 'Under Verification', remarks: '', title: '' },
    overall_compliance: false,
    remarks: '',
  }
}

function normalizeDocAudit(data) {
  const defaults = createDefaultDocAudit()
  if (!data || typeof data !== 'object') return defaults

  const out = { ...defaults }
  for (const [k, v] of Object.entries(data)) {
    if (v && typeof v === 'object') {
      out[k] = {
        available: v.available || 'Pending',
        compliance: v.compliance || 'Under Verification',
        remarks: v.remarks || '',
        title: v.title || '',
        explicitlySet: Boolean(v.explicitlySet),
      }
    } else {
      out[k] = v
    }
  }
  return out
}

function createDefaultSignoffs() {
  const today = new Date().toISOString().split('T')[0]
  return {
    centre_head: {
      name: '',
      designation: 'Centre Head',
      date: today,
      remarks: 'Candidate verification and placement documents verified.',
      confirmed: false,
    },
    cops_team: {
      name: '',
      designation: 'COPS Lead / Coordinator',
      date: today,
      remarks: 'Salary credits and document compliance verified.',
      confirmed: false,
    },
    business_leader: {
      name: '',
      designation: 'Business Head',
      date: today,
      remarks: 'Placement audit endorsed for formal sign-off.',
      confirmed: false,
    },
  }
}

export default function L1Home() {
  const currentYear = new Date().getFullYear()
  const years = [currentYear - 2, currentYear - 1, currentYear, currentYear + 1]

  // Dropdown cascading navigation state
  const [lists, setLists] = useState({ state: [], tc: [], order: [], batch: [], cand: [] })
  const [sel, setSel] = useState({ state: '', tc: '', order: '', batch: '', cand: '' })
  const [candDetail, setCandDetail] = useState(null)
  const [loadingDetail, setLoadingDetail] = useState(false)

  // Persisted documents from Supabase / Drive
  const [docSummary, setDocSummary] = useState(null)
  const [documents, setDocuments] = useState([])
  const [loadingDocs, setLoadingDocs] = useState(false)
  const [error, setError] = useState('')

  // Primary Workflow Tab ('audit' | 'docs')

  // Placement Audit States
  const [auditRecord, setAuditRecord] = useState(null)
  const [loadingAudit, setLoadingAudit] = useState(false)
  const [auditLoadError, setAuditLoadError] = useState('')
  const [auditSavingDraft, setAuditSavingDraft] = useState(false)
  const [auditSubmitting, setAuditSubmitting] = useState(false)
  const [auditToast, setAuditToast] = useState(null) // { message, type }

  const [employerList, setEmployerList] = useState(() => [createDefaultEmployer(null)])
  const [salaryDetailList, setSalaryDetailList] = useState(() => createDefaultSalaryList(currentYear))
  const [documentAudit, setDocumentAudit] = useState(createDefaultDocAudit)
  const [signoffDetails, setSignoffDetails] = useState(createDefaultSignoffs)

  // Statement View Modal State
  const [statementModalOpen, setStatementModalOpen] = useState(false)
  const [statementData, setStatementData] = useState(null)
  const [loadingStatement, setLoadingStatement] = useState(false)

  // Auto-dismiss toast notification
  useEffect(() => {
    if (auditToast) {
      const t = setTimeout(() => setAuditToast(null), 4000)
      return () => clearTimeout(t)
    }
  }, [auditToast])

  // Browser-Only Document Staging State (NEVER uploaded prematurely)
  // Appointment letter staging: { file, fileName, fileSize, replaceId } | null
  const [stagedAppointment, setStagedAppointment] = useState(null)
  const [replacingAppointment, setReplacingAppointment] = useState(false)
  const [appointmentError, setAppointmentError] = useState('')

  // Multi-employer appointment letter staging: { [empId]: { file, fileName, fileSize, replaceId } }
  const [stagedAppointments, setStagedAppointments] = useState({})
  const [replacingAppointments, setReplacingAppointments] = useState({})
  const [appointmentErrors, setAppointmentErrors] = useState({})

  // Multi-month Consolidated Bank Statement Staging:
  const [stagedConsolidatedBankDocs, setStagedConsolidatedBankDocs] = useState([])
  const [showConsolidatedModal, setShowConsolidatedModal] = useState(false)
  const [consolidatedForm, setConsolidatedForm] = useState({
    employer_id: '',
    start_month: 1,
    start_year: currentYear,
    end_month: 3,
    end_year: currentYear,
    file: null,
    fileName: '',
    fileSize: 0,
    error: '',
  })

  // Other document staging: { file, fileName, fileSize, replaceId } | null
  const [stagedOtherDoc, setStagedOtherDoc] = useState(null)
  const [otherDocTitle, setOtherDocTitle] = useState('')
  const [replacingOtherDoc, setReplacingOtherDoc] = useState(false)
  const [otherDocError, setOtherDocError] = useState('')

  // Monthly document staging: Array of { id, month, year, file, fileName, fileSize, replaceId, error, notAvailable }
  // EXACTLY 3 rows by default
  const createDefaultRows = (defaultOffset = 0) => [
    { id: `row_${Date.now()}_1`, month: 1 + defaultOffset, year: currentYear, file: null, fileName: '', fileSize: 0, replaceId: null, error: '', notAvailable: false },
    { id: `row_${Date.now()}_2`, month: 2 + defaultOffset, year: currentYear, file: null, fileName: '', fileSize: 0, replaceId: null, error: '', notAvailable: false },
    { id: `row_${Date.now()}_3`, month: 3 + defaultOffset, year: currentYear, file: null, fileName: '', fileSize: 0, replaceId: null, error: '', notAvailable: false },
  ]

  const [salaryRows, setSalaryRows] = useState(() => createDefaultRows(0))
  const [bankRows, setBankRows] = useState(() => createDefaultRows(0))

  // Staged replacements for existing persisted documents
  // Keyed by persisted document ID: { file, fileName, fileSize, month, year, error }
  const [stagedSalaryReplacements, setStagedSalaryReplacements] = useState({})
  const [stagedBankReplacements, setStagedBankReplacements] = useState({})
  const [activeReplaceIds, setActiveReplaceIds] = useState(new Set())

  // Modal dialog states
  const [showReviewModal, setShowReviewModal] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [submitSuccessData, setSubmitSuccessData] = useState(null)
  const [downloadingDocId, setDownloadingDocId] = useState(null)
  const [finalSubmitSuccessData, setFinalSubmitSuccessData] = useState(null)

  // L1 Dashboard Summary Cards & Filtered Candidate List State
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

  const selStateRef = useRef(sel.state)
  useEffect(() => {
    selStateRef.current = sel.state
  }, [sel.state])

  const fetchDashboardSummary = useCallback((targetState) => {
    const s = targetState || selStateRef.current
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
        console.warn('Failed to load dashboard summary:', err)
        setSummaryError(err?.message || 'Failed to load dashboard summary metrics.')
      })
      .finally(() => {
        setLoadingSummary(false)
      })
  }, [])

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

  // Close candidate list popup on Escape key press
  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === 'Escape' && activeCardFilter) {
        setActiveCardFilter(null)
        setCardCandidates([])
      }
    }
    if (activeCardFilter) {
      window.addEventListener('keydown', handleKeyDown)
      return () => window.removeEventListener('keydown', handleKeyDown)
    }
  }, [activeCardFilter])

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

  function handleSelectCandidateFromList(cand) {
    if (!cand?.candidate_id) return
    setError('')
    setActiveCardFilter(null)
    setCardCandidates([])
    setLoadingDetail(true)
    setSel((prev) => ({
      ...prev,
      state: cand.state_name || prev.state,
      cand: cand.candidate_id,
    }))
    api(`/lookups/candidates/${cand.candidate_id}`)
      .then((detail) => {
        setCandDetail(detail)
        refreshDocuments(cand.candidate_id)
        loadAudit(cand.candidate_id, detail)
      })
      .catch((e) => setError(e.message))
      .finally(() => {
        setLoadingDetail(false)
        setTimeout(() => {
          const el = document.getElementById('candidate-dossier-anchor')
          if (el) el.scrollIntoView({ behavior: 'smooth' })
        }, 150)
      })
  }

  async function handleMarkPayslipNotAvailable(monthNumber, rowId) {
    if (!sel.cand) return
    const row = salaryRows.find((r) => r.id === rowId)
    updateRowField('SALARY', rowId, 'file', null)
    try {
      const payload = {
        slot_key: `salary_slip_${monthNumber}`,
        month_number: monthNumber,
        available: 'No',
        month: row?.month || null,
        year: row?.year || null,
        remarks: 'Payslip not available',
      }
      await api(`/dashboard/candidates/${sel.cand}/payslip-availability`, null, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      setSalaryRows((prev) =>
        prev.map((r) => (r.id === rowId ? { ...r, notAvailable: true, file: null, fileName: '', fileSize: 0 } : r))
      )
      setDocumentAudit((prev) => ({
        ...prev,
        [`salary_slip_${monthNumber}`]: {
          ...(prev[`salary_slip_${monthNumber}`] || {}),
          available: 'No',
          month: row?.month || null,
          year: row?.year || null,
        },
      }))
      setAuditToast({ message: `Month ${monthNumber} PaySlip recorded as Not Available.`, type: 'info' })
      fetchDashboardSummary(sel.state)
    } catch (err) {
      const errMsg = err?.message && err.message !== '[object Object]' ? err.message : 'Failed to update payslip availability.'
      setAuditToast({ message: errMsg, type: 'error' })
    }
  }

  async function handleResetPayslipAvailability(monthNumber, rowId) {
    if (!sel.cand) return
    const row = salaryRows.find((r) => r.id === rowId)
    try {
      const payload = {
        slot_key: `salary_slip_${monthNumber}`,
        month_number: monthNumber,
        available: 'Pending',
        month: row?.month || null,
        year: row?.year || null,
      }
      await api(`/dashboard/candidates/${sel.cand}/payslip-availability`, null, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      setSalaryRows((prev) =>
        prev.map((r) => (r.id === rowId ? { ...r, notAvailable: false } : r))
      )
      setDocumentAudit((prev) => ({
        ...prev,
        [`salary_slip_${monthNumber}`]: {
          ...(prev[`salary_slip_${monthNumber}`] || {}),
          available: 'Pending',
        },
      }))
      setAuditToast({ message: `Month ${monthNumber} PaySlip reset to Browse / Upload mode.`, type: 'info' })
      fetchDashboardSummary(sel.state)
    } catch (err) {
      const errMsg = err?.message && err.message !== '[object Object]' ? err.message : 'Failed to reset payslip availability.'
      setAuditToast({ message: errMsg, type: 'error' })
    }
  }

  const fill = (key, promise) => {
    return promise
      .then((rows) => {
        const rowsArr = Array.isArray(rows) ? rows : []
        setLists((l) => ({ ...l, [key]: rowsArr }))
        return rowsArr
      })
      .catch((e) => {
        setLists((l) => ({ ...l, [key]: [] }))
        setError(e?.message || `Failed to load ${key} options.`)
      })
  }

  useEffect(() => {
    let isCancelled = false
    api('/lookups/states')
      .then((rows) => {
        if (isCancelled) return
        const stateList = Array.isArray(rows) ? rows : []
        setLists((l) => ({ ...l, state: stateList }))
        if (stateList.length === 1) {
          const singleState = stateList[0]
          setSel((s) => ({ ...s, state: singleState }))
          fill('tc', api('/lookups/centres', { state: singleState }))
          fetchDashboardSummary(singleState)
        }
      })
      .catch((e) => {
        if (!isCancelled) setError(e?.message || 'Failed to initialize assigned state.')
      })
    return () => {
      isCancelled = true
    }
  }, [fetchDashboardSummary])

  async function handleDownloadFile(docId, fileName) {
    if (!sel.cand || !docId) return
    setDownloadingDocId(docId)
    try {
      await downloadDocument(sel.cand, docId, fileName)
    } catch (err) {
      setError(err.message || 'Failed to download file.')
      setAuditToast({ message: err.message || 'Download failed.', type: 'error' })
    } finally {
      setDownloadingDocId(null)
    }
  }

  function resetAuditForm() {
    setAuditRecord(null)
    setAuditLoadError('')
    setEmployerList([createDefaultEmployer(null)])
    setSalaryDetailList(createDefaultSalaryList(currentYear))
    setDocumentAudit(createDefaultDocAudit())
    setSignoffDetails(createDefaultSignoffs())
    setStatementModalOpen(false)
    setStatementData(null)
  }

  function clearStagedFiles() {
    setStagedAppointment(null)
    setReplacingAppointment(false)
    setAppointmentError('')
    setStagedAppointments({})
    setReplacingAppointments({})
    setAppointmentErrors({})
    setStagedConsolidatedBankDocs([])
    setStagedOtherDoc(null)
    setOtherDocTitle('')
    setReplacingOtherDoc(false)
    setOtherDocError('')
    setSalaryRows(createDefaultRows(0))
    setBankRows(createDefaultRows(0))
    setStagedSalaryReplacements({})
    setStagedBankReplacements({})
    setActiveReplaceIds(new Set())
    setShowReviewModal(false)
  }

  async function refreshDocuments(candidateId) {
    if (!candidateId) return
    setLoadingDocs(true)
    try {
      const [summaryRes, docsRes] = await Promise.allSettled([
        api(`/candidates/${candidateId}/documents/summary`),
        api(`/candidates/${candidateId}/documents`),
      ])
      if (summaryRes.status === 'fulfilled') {
        setDocSummary(summaryRes.value)
      }
      if (docsRes.status === 'fulfilled') {
        const rawDocs = docsRes.value
        setDocuments(Array.isArray(rawDocs) ? rawDocs : (Array.isArray(rawDocs?.documents) ? rawDocs.documents : []))
      } else {
        console.warn('Could not load documents:', docsRes.reason)
        setDocuments([])
      }
    } catch (e) {
      console.warn('Error refreshing documents:', e)
      setDocuments([])
    } finally {
      setLoadingDocs(false)
    }
  }

  function loadAudit(candidateId, detail) {
    if (!candidateId) return
    setLoadingAudit(true)
    setAuditLoadError('')
    api(`/candidates/${candidateId}/audit`)
      .then((res) => {
        if (res?.exists && res.audit) {
          const a = res.audit
          setAuditRecord(a)
          if (Array.isArray(a.employer_details) && a.employer_details.length > 0) {
            setEmployerList(
              a.employer_details.map((e, idx) => ({
                id: e.id || `emp_${idx + 1}`,
                employer_name: e.employer_name || '',
                months_worked: e.months_worked ?? '',
                appointment_date: e.appointment_date || '',
                designation: e.designation || '',
                place_of_work: e.place_of_work || '',
                monthly_ctc: e.monthly_ctc ?? '',
                minimum_wages: e.minimum_wages ?? '',
              }))
            )
          } else {
            setEmployerList([createDefaultEmployer(detail, 'emp_1')])
          }

          if (Array.isArray(a.salary_details) && a.salary_details.length > 0) {
            const firstEmpId = (a.employer_details && a.employer_details[0]?.id) || 'emp_1'
            const loadedSalaryList = a.salary_details.map((s, idx) => ({
              id: s.id || `sal_${idx + 1}`,
              employer_id: s.employer_id || firstEmpId,
              month: s.month,
              year: s.year,
              working_days: s.working_days ?? '',
              pay_days: s.pay_days ?? '',
              leave_days: s.leave_days ?? '',
              credit_date: s.credit_date || '',
              amount_credited: s.amount_credited ?? '',
              gross_salary: s.gross_salary ?? '',
              deductions: s.deductions ?? '',
              net_salary: s.net_salary ?? '',
              bank_name: s.bank_name || '',
            }))
            setSalaryDetailList(loadedSalaryList)

            // Requirement 3: Automatically synchronize loaded salary periods into salaryRows and bankRows
            setSalaryRows((prev) =>
              loadedSalaryList.map((s, idx) => {
                const existing = prev[idx]
                return {
                  id: existing?.id || `sal_slot_${idx + 1}`,
                  month: s.month,
                  year: s.year,
                  employer_id: s.employer_id,
                  file: existing?.file || null,
                  fileName: existing?.fileName || '',
                  fileSize: existing?.fileSize || 0,
                  replaceId: existing?.replaceId || null,
                  error: existing?.error || '',
                  notAvailable: existing?.notAvailable || false,
                }
              })
            )
            setBankRows((prev) =>
              loadedSalaryList.map((s, idx) => {
                const existing = prev[idx]
                return {
                  id: existing?.id || `bank_slot_${idx + 1}`,
                  month: s.month,
                  year: s.year,
                  employer_id: s.employer_id,
                  file: existing?.file || null,
                  fileName: existing?.fileName || '',
                  fileSize: existing?.fileSize || 0,
                  replaceId: existing?.replaceId || null,
                  error: existing?.error || '',
                  notAvailable: existing?.notAvailable || false,
                }
              })
            )
          } else {
            setSalaryDetailList(createDefaultSalaryList(currentYear))
            setSalaryRows(createDefaultRows(0))
            setBankRows(createDefaultRows(0))
          }

          if (a.document_audit) {
            const norm = normalizeDocAudit(a.document_audit)
            setDocumentAudit(norm)
            setSalaryRows((prev) =>
              prev.map((r, idx) => ({
                ...r,
                notAvailable: norm[`salary_slip_${idx + 1}`]?.available === 'No',
              }))
            )
          }
          if (a.signoff_details) {
            setSignoffDetails({
              centre_head: { ...createDefaultSignoffs().centre_head, ...(a.signoff_details.centre_head || {}) },
              cops_team: { ...createDefaultSignoffs().cops_team, ...(a.signoff_details.cops_team || {}) },
              business_leader: { ...createDefaultSignoffs().business_leader, ...(a.signoff_details.business_leader || {}) },
            })
          }
        } else {
          setAuditRecord(null)
          setEmployerList([createDefaultEmployer(detail)])
          setSalaryDetailList(createDefaultSalaryList(currentYear))
          setSalaryRows(createDefaultRows(0))
          setBankRows(createDefaultRows(0))
          setDocumentAudit(createDefaultDocAudit())
          setSignoffDetails(createDefaultSignoffs())
        }
      })
      .catch((err) => {
        console.warn('Could not load candidate audit:', err)
        setAuditLoadError(err.message || 'Could not load placement audit record.')
        setAuditRecord(null)
        setEmployerList([createDefaultEmployer(detail)])
        setSalaryDetailList(createDefaultSalaryList(currentYear))
        setSalaryRows(createDefaultRows(0))
        setBankRows(createDefaultRows(0))
        setDocumentAudit(createDefaultDocAudit())
        setSignoffDetails(createDefaultSignoffs())
      })
      .finally(() => {
        setLoadingAudit(false)
      })
  }

  function pick(level, value) {
    setError('')
    setSel((s) => ({ ...s, ...Object.fromEntries(RESET[level].map((k) => [k, ''])), [level]: value }))
    setLists((l) => ({ ...l, ...Object.fromEntries(RESET[level].map((k) => [k, []])) }))
    setCandDetail(null)
    setDocSummary(null)
    setDocuments([])
    clearStagedFiles()
    resetAuditForm()

    if (!value) {
      if (level === 'state') {
        setSummaryData(null)
        setActiveCardFilter(null)
        setCardCandidates([])
      }
      return
    }
    if (level === 'state') {
      fill('tc', api('/lookups/centres', { state: value }))
      fetchDashboardSummary(value)
    }
    if (level === 'tc') fill('order', api('/lookups/sanction-orders', { tc_id: value }))
    if (level === 'order') fill('batch', api('/lookups/batches', { tc_id: sel.tc, sanction_order: value }))
    if (level === 'batch') fill('cand', api('/lookups/candidates', { kb_batch_id: value }))
    if (level === 'cand') {
      setLoadingDetail(true)
      api(`/lookups/candidates/${value}`)
        .then((detail) => {
          setCandDetail(detail)
          refreshDocuments(value)
          loadAudit(value, detail)
        })
        .catch((e) => setError(e.message))
        .finally(() => setLoadingDetail(false))
    }
  }

  // --- Audit Employer List Handlers ---
  function handleAddEmployerRow() {
    if (auditRecord?.audit_status === 'SUBMITTED') return
    const newRow = {
      id: `emp_${Date.now()}_${Math.random().toString(36).substr(2, 4)}`,
      employer_name: '',
      months_worked: '',
      appointment_date: '',
      designation: '',
      place_of_work: '',
      monthly_ctc: '',
      minimum_wages: '',
    }
    setEmployerList((prev) => [...prev, newRow])
  }

  function handleRemoveEmployerRow(id) {
    if (auditRecord?.audit_status === 'SUBMITTED') return
    if (employerList.length <= 1) return
    setEmployerList((prev) => prev.filter((e) => e.id !== id))
  }

  function handleUpdateEmployerField(id, field, value) {
    if (auditRecord?.audit_status === 'SUBMITTED') return
    setEmployerList((prev) =>
      prev.map((e) => (e.id === id ? { ...e, [field]: value } : e))
    )
  }

  // --- Audit Salary List Handlers ---
  function handleAddSalaryRow(targetEmpId = null) {
    if (auditRecord?.audit_status === 'SUBMITTED') return
    if (salaryDetailList.length >= 12) {
      setAuditToast({ message: 'Maximum 12 monthly salary entries allowed.', type: 'info' })
      return
    }

    const defaultEmpId = targetEmpId || employerList[0]?.id || 'emp_1'
    const nextPeriod = calculateNextSalaryPeriodForEmployer(defaultEmpId, salaryDetailList, currentYear)
    const nextMonth = nextPeriod.month
    const nextYear = nextPeriod.year

    const newId = `sal_${Date.now()}_${Math.random().toString(36).substr(2, 4)}`
    const newRow = {
      id: newId,
      employer_id: defaultEmpId,
      month: nextMonth,
      year: nextYear,
      working_days: 26,
      pay_days: 26,
      leave_days: 0,
      credit_date: '',
      amount_credited: '',
      gross_salary: '',
      deductions: '',
      net_salary: '',
      bank_name: '',
    }
    setSalaryDetailList((prev) => [...prev, newRow])

    // Requirement 3: Automatically synchronize newly added salary records to Salary Slips & Bank Statements
    const slotId = `slot_${Date.now()}_${Math.random().toString(36).substr(2, 4)}`
    setSalaryRows((prev) => [
      ...prev,
      {
        id: `sal_${slotId}`,
        month: nextMonth,
        year: nextYear,
        employer_id: defaultEmpId,
        file: null,
        fileName: '',
        fileSize: 0,
        replaceId: null,
        error: '',
        notAvailable: false,
      },
    ])
    setBankRows((prev) => [
      ...prev,
      {
        id: `bank_${slotId}`,
        month: nextMonth,
        year: nextYear,
        employer_id: defaultEmpId,
        file: null,
        fileName: '',
        fileSize: 0,
        replaceId: null,
        error: '',
        notAvailable: false,
      },
    ])
  }

  function handleRemoveSalaryRow(id) {
    if (auditRecord?.audit_status === 'SUBMITTED') return
    if (salaryDetailList.length <= 3) {
      setAuditToast({ message: 'At least 3 monthly salary entries are required.', type: 'info' })
      return
    }
    const removeIdx = salaryDetailList.findIndex((s) => s.id === id)
    if (removeIdx === -1) return

    // Requirement 4: Protect existing verified documents in Drive
    const targetSalaryDoc = salarySlips[removeIdx]
    const targetBankDoc = bankStatements[removeIdx]
    if (targetSalaryDoc || targetBankDoc) {
      setAuditToast({
        message: 'Cannot remove salary month: An active verified document is already uploaded in Drive for this slot.',
        type: 'error',
      })
      return
    }

    setSalaryDetailList((prev) => prev.filter((s) => s.id !== id))
    setSalaryRows((prev) => prev.filter((_, idx) => idx !== removeIdx))
    setBankRows((prev) => prev.filter((_, idx) => idx !== removeIdx))
  }

  function handleUpdateSalaryField(id, field, value) {
    if (auditRecord?.audit_status === 'SUBMITTED') return
    setSalaryDetailList((prev) => {
      const sIndex = prev.findIndex((s) => s.id === id)
      const updatedList = prev.map((s) => {
        if (s.id !== id) return s
        const updated = { ...s, [field]: value }
        if (field === 'gross_salary' || field === 'deductions') {
          const g = parseFloat(field === 'gross_salary' ? value : s.gross_salary) || 0
          const d = parseFloat(field === 'deductions' ? value : s.deductions) || 0
          if (g > 0) {
            updated.net_salary = Math.max(0, g - d).toString()
          }
        }
        return updated
      })

      // Requirement 3: Automatically synchronize Month and Year to corresponding Salary Slips & Bank Statements slots
      if ((field === 'month' || field === 'year') && sIndex !== -1) {
        const numVal = parseInt(value, 10) || value
        setSalaryRows((prevRows) =>
          prevRows.map((r, rIdx) => (rIdx === sIndex ? { ...r, [field]: numVal } : r))
        )
        setBankRows((prevRows) =>
          prevRows.map((r, rIdx) => (rIdx === sIndex ? { ...r, [field]: numVal } : r))
        )
      }

      return updatedList
    })
  }

  // --- Copy Previous Month (Same Employer) ---
  function handleCopyPreviousMonth(targetSalId) {
    if (auditRecord?.audit_status === 'SUBMITTED') return
    const targetIdx = salaryDetailList.findIndex((s) => s.id === targetSalId)
    if (targetIdx === -1) return
    const target = salaryDetailList[targetIdx]
    const targetEmpId = target.employer_id || employerList[0]?.id || 'emp_1'

    // Look for immediately preceding chronological period for the SAME employer
    const prevRecord = findPreviousSalaryRecordForEmployer(target, salaryDetailList)

    if (!prevRecord) {
      const targetEmp = employerList.find((e) => e.id === targetEmpId)
      setAuditToast({
        message: `No previous salary record found for "${targetEmp?.employer_name || 'this employer'}" to copy from.`,
        type: 'info',
      })
      return
    }

    // Safety check: confirm if user already entered data in target row
    const hasData =
      (target.working_days !== '' && target.working_days !== 26 && target.working_days !== null) ||
      (target.gross_salary !== '' && target.gross_salary !== 0 && target.gross_salary !== '0' && target.gross_salary !== null) ||
      (target.deductions !== '' && target.deductions !== 0 && target.deductions !== '0' && target.deductions !== null) ||
      (target.bank_name && target.bank_name.trim().length > 0)

    if (hasData) {
      const prevMonthName = MONTH_NAMES[(prevRecord.month || 1) - 1] || `Month ${prevRecord.month}`
      const targetMonthName = MONTH_NAMES[(target.month || 1) - 1] || `Month ${target.month}`
      const confirmed = window.confirm(
        `Overwrite current salary fields for ${targetMonthName} ${target.year} with reusable details from ${prevMonthName} ${prevRecord.year}?`
      )
      if (!confirmed) return
    }

    // Copy eligible fields only:
    // working_days, pay_days, leave_days, gross_salary, deductions, net_salary, bank_name
    // Never copy credit_date, amount_credited, file attachments, remarks, or approval states.
    const grossVal = prevRecord.gross_salary !== '' && prevRecord.gross_salary !== null ? prevRecord.gross_salary : ''
    const dedVal = prevRecord.deductions !== '' && prevRecord.deductions !== null ? prevRecord.deductions : ''
    let netVal = prevRecord.net_salary !== '' && prevRecord.net_salary !== null ? prevRecord.net_salary : ''
    if (grossVal !== '') {
      const g = parseFloat(grossVal) || 0
      const d = parseFloat(dedVal) || 0
      netVal = Math.max(0, g - d).toString()
    }

    setSalaryDetailList((prev) =>
      prev.map((s) =>
        s.id === targetSalId
          ? {
              ...s,
              working_days: prevRecord.working_days ?? 26,
              pay_days: prevRecord.pay_days ?? 26,
              leave_days: prevRecord.leave_days ?? 0,
              gross_salary: grossVal,
              deductions: dedVal,
              net_salary: netVal,
              bank_name: prevRecord.bank_name || '',
            }
          : s
      )
    )

    const prevMonthName = MONTH_NAMES[(prevRecord.month || 1) - 1] || `Month ${prevRecord.month}`
    setAuditToast({
      message: `✓ Reusable salary fields copied from ${prevMonthName} ${prevRecord.year}. Edit and verify as needed.`,
      type: 'success',
    })
  }

  function handleUpdateDocAudit(docKey, field, value) {
    if (auditRecord?.audit_status === 'SUBMITTED') return
    setDocumentAudit((prev) => {
      const prevDoc = prev?.[docKey] && typeof prev[docKey] === 'object' ? prev[docKey] : {}
      return {
        ...prev,
        [docKey]: {
          available: prevDoc.available || 'Pending',
          compliance: prevDoc.compliance || 'Under Verification',
          remarks: prevDoc.remarks || '',
          title: prevDoc.title || '',
          ...prevDoc,
          [field]: value,
          ...(field === 'available' ? { explicitlySet: true } : {}),
        },
      }
    })
  }

  function prepareDocumentAuditPayload() {
    const currentItems = (
      salaryDetailList.length > 0
        ? [
            (() => {
              const apptEv = resolveEvidence('APPOINTMENT_LETTER', null, null, employerList[0]?.id)
              return { key: 'appointment_letter', resolved: apptEv }
            })(),
            ...salaryDetailList.map((sal, idx) => {
              const resSal = resolveEvidence('SALARY_SLIP', sal.month, sal.year, sal.employer_id)
              return { key: `salary_slip_${idx + 1}`, resolved: resSal }
            }),
            ...salaryDetailList.map((sal, idx) => {
              const resBank = resolveEvidence('BANK_STATEMENT', sal.month, sal.year, sal.employer_id)
              return { key: `bank_statement_${idx + 1}`, resolved: resBank }
            }),
            { key: 'other_document', resolved: null }
          ]
        : [
            (() => {
              const apptEv = resolveEvidence('APPOINTMENT_LETTER', null, null, employerList[0]?.id)
              return { key: 'appointment_letter', resolved: apptEv }
            })(),
            ...[1, 2, 3].map((mIdx) => ({
              key: `salary_slip_${mIdx}`,
              resolved: resolveEvidence('SALARY_SLIP', mIdx, currentYear, employerList[0]?.id)
            })),
            ...[1, 2, 3].map((mIdx) => ({
              key: `bank_statement_${mIdx}`,
              resolved: resolveEvidence('BANK_STATEMENT', mIdx, currentYear, employerList[0]?.id)
            })),
            { key: 'other_document', resolved: null }
          ]
    )

    const merged = { ...documentAudit }
    for (const item of currentItems) {
      const entry = merged[item.key] && typeof merged[item.key] === 'object' ? merged[item.key] : {}
      const isPresent = item.resolved ? (item.resolved.status === 'PERSISTED' || item.resolved.status === 'STAGED') : false
      if (!entry.explicitlySet && isPresent) {
        merged[item.key] = {
          ...entry,
          available: 'Yes',
          compliance: entry.compliance || 'Under Verification',
          remarks: entry.remarks || '',
          title: entry.title || '',
        }
      }
    }
    return merged
  }

  // --- Audit Draft & Submit Handlers ---
  async function handleSaveDraft(isSilent = false) {
    if (!sel.cand || !candDetail) return
    if (auditLoadError) {
      setError('Cannot save draft while audit record failed to load. Please retry loading first.')
      if (!isSilent) setAuditToast({ message: 'Cannot save draft: please retry loading first.', type: 'error' })
      return
    }
    if (auditRecord?.audit_status === 'SUBMITTED') {
      if (!isSilent) setAuditToast({ message: 'This placement audit is already submitted and locked against editing.', type: 'info' })
      return
    }
    setAuditSavingDraft(true)
    setError('')
    try {
      const payloadDocAudit = prepareDocumentAuditPayload()
      setDocumentAudit(payloadDocAudit)
      const payload = {
        candidate_snapshot: {
          candidate_id: candDetail.candidate_id,
          first_name: candDetail.first_name,
          last_name: candDetail.last_name,
          father_name: candDetail.father_name,
          dob: candDetail.dob,
          mobile: candDetail.mobile,
          state: sel.state,
          tc_name: lists.tc.find((c) => c.tc_id === sel.tc)?.name || sel.tc,
          batch_code: lists.batch.find((b) => b.kb_batch_id === sel.batch)?.batch_code || sel.batch,
          sanction_order: sel.order,
        },
        employer_details: employerList
          .filter((e) => e.employer_name && e.employer_name.trim())
          .map((e) => ({
            id: e.id,
            employer_name: e.employer_name.trim(),
            months_worked: e.months_worked !== '' && e.months_worked !== null ? parseFloat(e.months_worked) : null,
            appointment_date: e.appointment_date || null,
            designation: e.designation || null,
            place_of_work: e.place_of_work || null,
            monthly_ctc: e.monthly_ctc !== '' && e.monthly_ctc !== null ? parseFloat(e.monthly_ctc) : null,
            minimum_wages: e.minimum_wages !== '' && e.minimum_wages !== null ? parseFloat(e.minimum_wages) : null,
          })),
        salary_details: salaryDetailList.map((s) => ({
          id: s.id,
          employer_id: s.employer_id || (employerList[0]?.id || 'emp_1'),
          month: parseInt(s.month, 10),
          year: parseInt(s.year, 10),
          working_days: s.working_days !== '' && s.working_days !== null ? parseInt(s.working_days, 10) : null,
          pay_days: s.pay_days !== '' && s.pay_days !== null ? parseInt(s.pay_days, 10) : null,
          leave_days: s.leave_days !== '' && s.leave_days !== null ? parseInt(s.leave_days, 10) : null,
          credit_date: s.credit_date || null,
          amount_credited: s.amount_credited !== '' && s.amount_credited !== null ? parseFloat(s.amount_credited) : null,
          gross_salary: s.gross_salary !== '' && s.gross_salary !== null ? parseFloat(s.gross_salary) : null,
          deductions: s.deductions !== '' && s.deductions !== null ? parseFloat(s.deductions) : null,
          net_salary: s.net_salary !== '' && s.net_salary !== null ? parseFloat(s.net_salary) : null,
          bank_name: s.bank_name || null,
        })),
        document_audit: payloadDocAudit,
        signoff_details: signoffDetails,
        remarks: auditRecord?.remarks || null,
      }

      const res = await api(`/candidates/${sel.cand}/audit/draft`, null, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      setAuditRecord(res.audit)
      if (!isSilent) {
        setAuditToast({ message: '✓ Draft placement audit saved successfully.', type: 'success' })
      }
      return res.audit
    } catch (err) {
      setError(err.message || 'Failed to save audit draft.')
      if (!isSilent) {
        setAuditToast({ message: err.message || 'Failed to save draft.', type: 'error' })
      }
      throw err
    } finally {
      setAuditSavingDraft(false)
    }
  }

  async function handleSubmitAuditStatement() {
    if (!sel.cand || !candDetail) return
    if (auditLoadError) {
      setError('Cannot submit statement while audit record failed to load. Please retry loading first.')
      setAuditToast({ message: 'Cannot submit statement: please retry loading first.', type: 'error' })
      return
    }
    if (auditRecord?.audit_status === 'SUBMITTED') {
      setAuditToast({ message: 'This placement audit has already been submitted.', type: 'info' })
      handleOpenStatementModal()
      return
    }

    if (candDetail.has_active_hold) {
      setError(`Cannot submit placement audit: ${candDetail.active_holds?.[0]?.hold_reason || 'Administrative hold in effect'}.`)
      return
    }

    const validEmployers = employerList.filter((e) => e.employer_name && e.employer_name.trim())
    if (validEmployers.length === 0) {
      setError('At least one Employer Name is required to finalize placement audit.')
      setAuditToast({ message: 'Employer name is required.', type: 'error' })
      return
    }

    if (salaryDetailList.length < 3) {
      setError('At least 3 distinct monthly salary records are required to finalize placement audit.')
      setAuditToast({ message: 'Min 3 salary entries required.', type: 'error' })
      return
    }

    // Duplicate reporting period check scoped per employer
    const periods = new Set(salaryDetailList.map((s) => `${s.employer_id || ''}-${s.month}-${s.year}`))
    if (periods.size < salaryDetailList.length) {
      setError('Duplicate reporting month and year found for the same employer in salary details. Each reporting month per employer must be unique.')
      setAuditToast({ message: 'Duplicate reporting months per employer found.', type: 'error' })
      return
    }

    // Check appointment letter per employer when multiple employers exist
    if (validEmployers.length > 1) {
      for (const emp of validEmployers) {
        const hasPersisted = safeDocs.some(
          (d) => d.document_type === 'APPOINTMENT_LETTER' && (d.employer_id === emp.id || !d.employer_id)
        )
        const hasStaged = Boolean(stagedAppointments[emp.id]?.file)
        if (!hasPersisted && !hasStaged) {
          setError(`Appointment / Offer Letter is missing for employer: "${emp.employer_name}". Every employer must have an offer letter.`)
          setAuditToast({ message: `Offer letter missing for ${emp.employer_name}`, type: 'error' })
          return
        }
      }
    }

    // Validate that documents explicitly marked "Yes" have physical evidence in Drive or browser staging
    for (let idx = 0; idx < salaryDetailList.length; idx++) {
      const sal = salaryDetailList[idx]
      const salKey = `salary_slip_${idx + 1}`
      const salRow = documentAudit?.[salKey]
      const salEv = resolveEvidence('SALARY_SLIP', sal.month, sal.year, sal.employer_id)
      if (salRow?.available === 'Yes' && salEv.status === 'MISSING') {
        const mName = MONTH_NAMES[(sal.month || 1) - 1] || `Month ${sal.month}`
        setError(`"Salary Slip Month ${idx + 1} (${mName} ${sal.year || ''})" is marked as "Yes" (Available), but no physical file has been uploaded to Drive or staged. Please attach the file or mark availability as "Pending" or "No".`)
        setAuditToast({ message: `Physical file missing for Salary Slip Month ${idx + 1}`, type: 'error' })
        return
      }

      const bankKey = `bank_statement_${idx + 1}`
      const bankRow = documentAudit?.[bankKey]
      const bankEv = resolveEvidence('BANK_STATEMENT', sal.month, sal.year, sal.employer_id)
      if (bankRow?.available === 'Yes' && bankEv.status === 'MISSING') {
        const mName = MONTH_NAMES[(sal.month || 1) - 1] || `Month ${sal.month}`
        setError(`"Bank Statement Month ${idx + 1} (${mName} ${sal.year || ''})" is marked as "Yes" (Available), but no physical file has been uploaded to Drive or staged. Please attach the file or mark availability as "Pending" or "No".`)
        setAuditToast({ message: `Physical file missing for Bank Statement Month ${idx + 1}`, type: 'error' })
        return
      }
    }

    const apptRow = documentAudit?.appointment_letter
    const apptEv = resolveEvidence('APPOINTMENT_LETTER', null, null, employerList[0]?.id)
    if (apptRow?.available === 'Yes' && apptEv.status === 'MISSING') {
      setError('"Appointment / Offer Letter" is marked as "Yes" (Available), but no physical file has been uploaded to Drive or staged. Please attach the file or mark availability as "Pending" or "No".')
      setAuditToast({ message: 'Physical file missing for Appointment / Offer Letter', type: 'error' })
      return
    }

    setError('')
    // Save draft first so the statement preview has all latest inputs
    try {
      await handleSaveDraft(true)
      // Open statement modal for coordinator preview BEFORE submission!
      await handleOpenStatementModal()
    } catch {
      // Error handled in handleSaveDraft
    }
  }

  async function handleConfirmFinalSubmit() {
    if (!sel.cand || !candDetail) return
    setAuditSubmitting(true)
    setError('')
    try {
      const validEmployers = employerList.filter((e) => e.employer_name && e.employer_name.trim())
      const payloadDocAudit = prepareDocumentAuditPayload()
      setDocumentAudit(payloadDocAudit)
      const payload = {
        candidate_snapshot: {
          candidate_id: candDetail.candidate_id,
          first_name: candDetail.first_name,
          last_name: candDetail.last_name,
          father_name: candDetail.father_name,
          dob: candDetail.dob,
          mobile: candDetail.mobile,
          state: sel.state,
          tc_name: lists.tc.find((c) => c.tc_id === sel.tc)?.name || sel.tc,
          batch_code: lists.batch.find((b) => b.kb_batch_id === sel.batch)?.batch_code || sel.batch,
          sanction_order: sel.order,
        },
        employer_details: validEmployers.map((e) => ({
          id: e.id,
          employer_name: e.employer_name.trim(),
          months_worked: e.months_worked !== '' && e.months_worked !== null ? parseFloat(e.months_worked) : null,
          appointment_date: e.appointment_date || null,
          designation: e.designation || null,
          place_of_work: e.place_of_work || null,
          monthly_ctc: e.monthly_ctc !== '' && e.monthly_ctc !== null ? parseFloat(e.monthly_ctc) : null,
          minimum_wages: e.minimum_wages !== '' && e.minimum_wages !== null ? parseFloat(e.minimum_wages) : null,
        })),
        salary_details: salaryDetailList.map((s) => ({
          id: s.id,
          employer_id: s.employer_id || (employerList[0]?.id || 'emp_1'),
          month: parseInt(s.month, 10),
          year: parseInt(s.year, 10),
          working_days: s.working_days !== '' && s.working_days !== null ? parseInt(s.working_days, 10) : null,
          pay_days: s.pay_days !== '' && s.pay_days !== null ? parseInt(s.pay_days, 10) : null,
          leave_days: s.leave_days !== '' && s.leave_days !== null ? parseInt(s.leave_days, 10) : null,
          credit_date: s.credit_date || null,
          amount_credited: s.amount_credited !== '' && s.amount_credited !== null ? parseFloat(s.amount_credited) : null,
          gross_salary: s.gross_salary !== '' && s.gross_salary !== null ? parseFloat(s.gross_salary) : null,
          deductions: s.deductions !== '' && s.deductions !== null ? parseFloat(s.deductions) : null,
          net_salary: s.net_salary !== '' && s.net_salary !== null ? parseFloat(s.net_salary) : null,
          bank_name: s.bank_name || null,
        })),
        document_audit: payloadDocAudit,
        signoff_details: signoffDetails,
        remarks: auditRecord?.remarks || null,
      }

      const res = await api(`/candidates/${sel.cand}/audit/submit`, null, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      setAuditRecord(res.audit)
      setStatementModalOpen(false)
      setFinalSubmitSuccessData({
        candidateId: candDetail.candidate_id,
        candidateName: `${candDetail.first_name} ${candDetail.last_name}`,
        batch: lists.batch.find((b) => b.kb_batch_id === sel.batch)?.batch_code || sel.batch,
        submittedAt: res.submitted_at || new Date().toISOString(),
      })
      setAuditToast({ message: '✓ Placement Audit Statement submitted successfully!', type: 'success' })
      fetchDashboardSummary(sel.state)
    } catch (err) {
      setError(err.message || 'Failed to submit placement audit statement.')
      setAuditToast({ message: err.message || 'Submission failed.', type: 'error' })
    } finally {
      setAuditSubmitting(false)
    }
  }

  function handleFinalSubmissionCompleteReset() {
    setFinalSubmitSuccessData(null)
    setSubmitSuccessData(null)
    clearStagedFiles()
    setSel({ state: '', tc: '', order: '', batch: '', cand: '' })
    setLists((l) => ({ ...l, tc: [], order: [], batch: [], cand: [] }))
    setCandDetail(null)
    setDocSummary(null)
    setDocuments([])
    resetAuditForm()
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function handleOpenStatementModal() {
    if (!sel.cand) return
    setLoadingStatement(true)
    try {
      const res = await api(`/candidates/${sel.cand}/audit/statement`)
      setStatementData(res)
      setStatementModalOpen(true)
    } catch (err) {
      setError(err.message || 'Failed to load placement statement.')
      setAuditToast({ message: err.message || 'Failed to load statement.', type: 'error' })
    } finally {
      setLoadingStatement(false)
    }
  }

  // Calculated totals for salary details
  const computedSalaryTotals = salaryDetailList.reduce(
    (acc, row) => {
      const gross = parseFloat(row.gross_salary) || 0
      const ded = parseFloat(row.deductions) || 0
      const net = parseFloat(row.net_salary) || 0
      const cred = parseFloat(row.amount_credited) || 0
      acc.gross += gross
      acc.deductions += ded
      acc.net += net
      acc.credited += cred
      if (gross > 0) acc.validMonths += 1
      return acc
    },
    { gross: 0, deductions: 0, net: 0, credited: 0, validMonths: 0 }
  )
  const computedAvgGross =
    computedSalaryTotals.validMonths > 0 ? computedSalaryTotals.gross / computedSalaryTotals.validMonths : 0
  const isAuditSubmitted = auditRecord?.audit_status === 'SUBMITTED'

  // Rejection & Return state computation for currently loaded candidate dossier
  const rawAuditStatus = (auditRecord?.audit_status || '').toUpperCase()
  const rawCpassStatus = (auditRecord?.cpass_status || '').toUpperCase()
  const signoffObj = auditRecord?.signoff_details || {}
  const reviewStagesObj = signoffObj?.review_stages || {}

  const chStage = (reviewStagesObj?.ch?.status || '').toLowerCase()
  const copsStage = (reviewStagesObj?.cops?.status || '').toLowerCase()
  const blStage = (reviewStagesObj?.bl?.status || '').toLowerCase()

  // True if candidate is CURRENTLY returned to L1 awaiting resubmission
  const isReturnedToL1 = rawAuditStatus === 'RETURNED_TO_L1' || rawCpassStatus === 'RETURNED_TO_L1' || chStage.includes('return')

  // Rejection by stage
  const isCHRejected = isReturnedToL1 || chStage === 'rejected'
  const isCOPSRejected = copsStage === 'rejected'
  const isBLRejected = blStage === 'rejected'
  const isAuditReturnedOrRejected = isCHRejected || isCOPSRejected || isBLRejected || rawAuditStatus === 'REJECTED' || rawCpassStatus === 'REJECTED'

  // Determine reviewing authority, reasons, and metadata
  let rejectionAuthorityName = 'Reviewing Authority'
  let rejectionStageLabel = 'L2 Centre Head'
  let rejectionReason = ''
  let rejectionRemarks = ''
  let returnedByName = ''
  let returnedAtDate = ''

  if (isBLRejected) {
    rejectionAuthorityName = 'Business Leader (BL — L4)'
    rejectionStageLabel = 'L4 Business Leader'
    rejectionReason = reviewStagesObj?.bl?.rejection_reason || signoffObj?.rejection_reason || ''
    rejectionRemarks = reviewStagesObj?.bl?.remarks || signoffObj?.business_leader?.remarks || ''
    returnedByName = reviewStagesObj?.bl?.reviewed_by || signoffObj?.business_leader?.name || ''
    returnedAtDate = reviewStagesObj?.bl?.reviewed_at || auditRecord?.updated_at || ''
  } else if (isCOPSRejected) {
    rejectionAuthorityName = 'COPS Audit Team (COPS — L3)'
    rejectionStageLabel = 'L3 COPS Team'
    rejectionReason = reviewStagesObj?.cops?.rejection_reason || signoffObj?.rejection_reason || ''
    rejectionRemarks = reviewStagesObj?.cops?.remarks || signoffObj?.cops_team?.remarks || ''
    returnedByName = reviewStagesObj?.cops?.reviewed_by || signoffObj?.cops_team?.name || ''
    returnedAtDate = reviewStagesObj?.cops?.reviewed_at || auditRecord?.updated_at || ''
  } else if (isCHRejected) {
    rejectionAuthorityName = 'Centre Head (CH — L2)'
    rejectionStageLabel = 'L2 Centre Head'
    const retInfo = signoffObj?.return_to_l1 || {}
    rejectionReason = retInfo.return_reason || retInfo.reason || reviewStagesObj?.ch?.reason || reviewStagesObj?.ch?.return_reason || reviewStagesObj?.ch?.rejection_reason || signoffObj?.rejection_reason || ''
    rejectionRemarks = retInfo.remarks || reviewStagesObj?.ch?.remarks || signoffObj?.centre_head?.remarks || ''
    returnedByName = retInfo.returned_by_name || retInfo.returned_by || reviewStagesObj?.ch?.returned_by || reviewStagesObj?.ch?.reviewed_by || signoffObj?.centre_head?.name || ''
    returnedAtDate = retInfo.returned_at || reviewStagesObj?.ch?.returned_at || reviewStagesObj?.ch?.reviewed_at || auditRecord?.updated_at || ''
  }


  const name = (c) => {
    if (!c) return ''
    return `${c.first_name ?? ''} ${c.last_name ?? ''}`.trim()
  }
  const safeDocs = Array.isArray(documents) ? documents : []
  const appointmentDocs = safeDocs.filter((d) => d.document_type === 'APPOINTMENT_LETTER')
  const appointmentDoc = appointmentDocs[0] || null
  const salarySlips = safeDocs.filter((d) => d.document_type === 'SALARY_SLIP')
  const bankStatements = safeDocs.filter((d) => d.document_type === 'BANK_STATEMENT')
  const consolidatedBankDocs = safeDocs.filter((d) => isDocConsolidated(d))
  const individualBankDocs = safeDocs.filter((d) => d.document_type === 'BANK_STATEMENT' && !isDocConsolidated(d))
  const otherDoc = safeDocs.find((d) => d.document_type === 'OTHER_DOCUMENT')

  // --- Staging Handlers for Appointment Letter (Multi-Employer Aware) ---
  function handleSelectAppointment(file, isReplacement = false) {
    setAppointmentError('')
    if (!file) return
    const err = validateFile(file)
    if (err) {
      setAppointmentError(err)
      return
    }
    setStagedAppointment({
      file,
      fileName: file.name,
      fileSize: file.size,
      replaceId: isReplacement && appointmentDoc ? appointmentDoc.id : null,
    })
  }

  function handleRemoveStagedAppointment() {
    setStagedAppointment(null)
    setAppointmentError('')
    setReplacingAppointment(false)
  }

  function handleSelectAppointmentForEmployer(empId, file, isReplacement = false) {
    if (!file) return
    const err = validateFile(file)
    setAppointmentErrors((prev) => ({ ...prev, [empId]: err || '' }))
    if (err) return
    const existingDoc = appointmentDocs.find((d) => d.employer_id === empId || (!d.employer_id && employerList.length === 1))
    setStagedAppointments((prev) => ({
      ...prev,
      [empId]: {
        file,
        fileName: file.name,
        fileSize: file.size,
        replaceId: isReplacement && existingDoc ? existingDoc.id : null,
      },
    }))
    if (employerList.length <= 1 || empId === employerList[0]?.id) {
      setStagedAppointment({
        file,
        fileName: file.name,
        fileSize: file.size,
        replaceId: isReplacement && existingDoc ? existingDoc.id : null,
      })
    }
  }

  function handleRemoveStagedAppointmentForEmployer(empId) {
    setStagedAppointments((prev) => {
      const copy = { ...prev }
      delete copy[empId]
      return copy
    })
    setAppointmentErrors((prev) => {
      const copy = { ...prev }
      delete copy[empId]
      return copy
    })
    setReplacingAppointments((prev) => ({ ...prev, [empId]: false }))
    if (employerList.length <= 1 || empId === employerList[0]?.id) {
      setStagedAppointment(null)
      setAppointmentError('')
      setReplacingAppointment(false)
    }
  }

  // Employer matching helper: resolves any employer ID (e.g. "emp_1", "emp_1793083463814_1", 1, etc.)
  // to its canonical employer in employerList.
  function getCanonicalEmployerId(empId) {
    if (!empId) return employerList[0]?.id || ''
    const s = String(empId).trim()
    // 1. Direct match by ID in employerList
    const direct = employerList.find((e) => String(e.id).trim() === s)
    if (direct) return String(direct.id).trim()
    // 2. Match sequence identifier: "emp_1", "emp_2", "1", "2"
    const norm = s.startsWith('emp_') ? s.slice(4) : s
    const idx = parseInt(norm, 10)
    if (!isNaN(idx) && idx >= 1 && idx <= employerList.length) {
      return String(employerList[idx - 1]?.id).trim()
    }
    // 3. If there is only one employer in the list, any employer ID refers to it
    if (employerList.length <= 1 && employerList[0]) {
      return String(employerList[0].id).trim()
    }
    return s
  }

  function matchesEmployer(docEmpId, targetEmpId) {
    if (employerList.length <= 1) return true
    if (!docEmpId || !targetEmpId) return true
    const canDoc = getCanonicalEmployerId(docEmpId)
    const canTarget = getCanonicalEmployerId(targetEmpId)
    if (canDoc && canTarget) {
      return canDoc === canTarget
    }
    return String(docEmpId).trim() === String(targetEmpId).trim()
  }

  // --- Consolidated Bank Statement Coverage Check ---
  function getConsolidatedCoverage(month, year, empId) {
    return getConsolidatedCoverageHelper(month, year, empId, {
      safeDocs,
      docSummary,
      stagedConsolidatedBankDocs,
      employerList,
    })
  }

  // --- Unified Employer-Aware Evidence Resolver ---
  function resolveEvidence(docType, month, year, empId) {
    if (docType === 'SALARY_SLIP') {
      const targetM = Number(month)
      const targetY = Number(year)
      const persistedDoc = safeDocs.find(
        (d) =>
          d.document_type === 'SALARY_SLIP' &&
          (!d.upload_status || String(d.upload_status).toUpperCase() === 'SUCCESS' || Boolean(d.drive_file_id)) &&
          Number(d.reporting_month) === targetM &&
          Number(d.reporting_year) === targetY &&
          matchesEmployer(d.employer_id, empId)
      )
      if (persistedDoc) {
        return {
          status: 'PERSISTED',
          doc: persistedDoc,
          isConsolidated: false,
          isReviewerVerified: !!(persistedDoc.reviewer_status === 'VERIFIED' || persistedDoc.verification_status === 'VERIFIED'),
          fileName: persistedDoc.file_name,
          periodText: `${MONTH_NAMES[(targetM || 1) - 1]} ${targetY || ''}`,
          stagedFile: null,
          source: 'INDIVIDUAL',
        }
      }
      const stagedRow = salaryRows.find(
        (r) =>
          r.file &&
          Number(r.month) === targetM &&
          Number(r.year) === targetY &&
          matchesEmployer(r.employer_id || empId, empId)
      )
      if (stagedRow) {
        return {
          status: 'STAGED',
          doc: null,
          isConsolidated: false,
          isReviewerVerified: false,
          fileName: stagedRow.fileName,
          periodText: `${MONTH_NAMES[(targetM || 1) - 1]} ${targetY || ''}`,
          stagedFile: stagedRow.file,
          source: 'STAGED_INDIVIDUAL',
        }
      }
      return {
        status: 'MISSING',
        doc: null,
        isConsolidated: false,
        isReviewerVerified: false,
        fileName: '',
        periodText: `${MONTH_NAMES[(targetM || 1) - 1]} ${targetY || ''}`,
        stagedFile: null,
        source: 'NONE',
      }
    }

    if (docType === 'BANK_STATEMENT') {
      const targetM = Number(month)
      const targetY = Number(year)

      // 1. Check individual bank statement in Drive
      const persistedInd = safeDocs.find(
        (d) =>
          d.document_type === 'BANK_STATEMENT' &&
          !isDocConsolidated(d) &&
          (!d.upload_status || String(d.upload_status).toUpperCase() === 'SUCCESS' || Boolean(d.drive_file_id)) &&
          Number(d.reporting_month) === targetM &&
          Number(d.reporting_year) === targetY &&
          matchesEmployer(d.employer_id, empId)
      )
      if (persistedInd) {
        return {
          status: 'PERSISTED',
          doc: persistedInd,
          isConsolidated: false,
          isReviewerVerified: !!(persistedInd.reviewer_status === 'VERIFIED' || persistedInd.verification_status === 'VERIFIED'),
          fileName: persistedInd.file_name,
          periodText: `${MONTH_NAMES[(targetM || 1) - 1]} ${targetY || ''}`,
          stagedFile: null,
          source: 'INDIVIDUAL',
        }
      }

      // 2. Check consolidated bank statement in Drive
      const consol = getConsolidatedCoverage(targetM, targetY, empId)
      if (consol && consol.persisted) {
        return {
          status: 'PERSISTED',
          doc: consol.doc,
          isConsolidated: true,
          isReviewerVerified: !!(consol.doc?.reviewer_status === 'VERIFIED' || consol.doc?.verification_status === 'VERIFIED'),
          fileName: consol.fileName,
          periodText: consol.periodText,
          stagedFile: null,
          source: 'CONSOLIDATED',
        }
      }

      // 3. Check staged individual bank statement
      const stagedRow = bankRows.find(
        (r) =>
          r.file &&
          Number(r.month) === targetM &&
          Number(r.year) === targetY &&
          matchesEmployer(r.employer_id || empId, empId)
      )
      if (stagedRow) {
        return {
          status: 'STAGED',
          doc: null,
          isConsolidated: false,
          isReviewerVerified: false,
          fileName: stagedRow.fileName,
          periodText: `${MONTH_NAMES[(targetM || 1) - 1]} ${targetY || ''}`,
          stagedFile: stagedRow.file,
          source: 'STAGED_INDIVIDUAL',
        }
      }

      // 4. Check staged consolidated bank statement
      if (consol && !consol.persisted) {
        return {
          status: 'STAGED',
          doc: null,
          isConsolidated: true,
          isReviewerVerified: false,
          fileName: consol.fileName,
          periodText: consol.periodText,
          stagedFile: true,
          source: 'STAGED_CONSOLIDATED',
        }
      }

      return {
        status: 'MISSING',
        doc: null,
        isConsolidated: false,
        isReviewerVerified: false,
        fileName: '',
        periodText: `${MONTH_NAMES[(targetM || 1) - 1]} ${targetY || ''}`,
        stagedFile: null,
        source: 'NONE',
      }
    }

    if (docType === 'APPOINTMENT_LETTER') {
      const persistedDoc = safeDocs.find(
        (d) =>
          d.document_type === 'APPOINTMENT_LETTER' &&
          (!d.upload_status || String(d.upload_status).toUpperCase() === 'SUCCESS' || Boolean(d.drive_file_id)) &&
          matchesEmployer(d.employer_id, empId)
      )
      if (persistedDoc) {
        return {
          status: 'PERSISTED',
          doc: persistedDoc,
          isConsolidated: false,
          isReviewerVerified: !!(persistedDoc.reviewer_status === 'VERIFIED' || persistedDoc.verification_status === 'VERIFIED'),
          fileName: persistedDoc.file_name,
          periodText: '',
          stagedFile: null,
          source: 'INDIVIDUAL',
        }
      }
      const staged = stagedAppointments[empId]?.file
        ? stagedAppointments[empId]
        : (employerList.length <= 1 && stagedAppointment?.file ? stagedAppointment : null)
      if (staged) {
        return {
          status: 'STAGED',
          doc: null,
          isConsolidated: false,
          isReviewerVerified: false,
          fileName: staged.fileName,
          periodText: '',
          stagedFile: staged.file,
          source: 'STAGED_INDIVIDUAL',
        }
      }
      return {
        status: 'MISSING',
        doc: null,
        isConsolidated: false,
        isReviewerVerified: false,
        fileName: '',
        periodText: '',
        stagedFile: null,
        source: 'NONE',
      }
    }


    return {
      status: 'MISSING',
      doc: null,
      isConsolidated: false,
      isReviewerVerified: false,
      fileName: '',
      periodText: '',
      stagedFile: null,
      source: 'NONE',
    }
  }

  // --- Phase 2: Visibility filters for monthly upload slots ---
  function isSalarySlotVisible(row, index) {
    if (row.file) return true // Keep genuinely staged files visible
    if (row.notAvailable) return true // Keep explicit payslip availability toggle visible
    const matchedSal = salaryDetailList[index]
    const sEmpId = matchedSal?.employer_id || employerList[0]?.id
    const targetMonth = row.month || matchedSal?.month
    const targetYear = row.year || matchedSal?.year
    const ev = resolveEvidence('SALARY_SLIP', targetMonth, targetYear, sEmpId)
    // Redundant if already persisted in Drive
    return ev.status !== 'PERSISTED'
  }

  function isBankSlotVisible(row, index) {
    return isBankSlotVisibleHelper(row, index, {
      bankRows,
      salaryDetailList,
      employerList,
      safeDocs,
      stagedConsolidatedBankDocs,
      docSummary,
    })
  }

  function handleSelectOtherDoc(file) {
    if (!file) {
      setStagedOtherDoc(null)
      setOtherDocError('')
      return
    }
    const err = validateFile(file)
    if (err) {
      setOtherDocError(err)
      return
    }
    setOtherDocError('')
    setStagedOtherDoc({
      file,
      fileName: file.name,
      fileSize: file.size,
      replaceId: replacingOtherDoc && otherDoc ? otherDoc.id : null,
    })
  }

  function handleRemoveStagedOtherDoc() {
    setStagedOtherDoc(null)
    setOtherDocError('')
    setReplacingOtherDoc(false)
  }

  // --- Staging Handlers for Monthly Rows (Salary / Bank) ---
  function updateRowField(type, rowId, field, value) {
    const setter = type === 'SALARY' ? setSalaryRows : setBankRows
    setter((prev) =>
      prev.map((r) => {
        if (r.id !== rowId) return r
        const updated = { ...r, [field]: value }
        if (field === 'file') {
          if (value) {
            const err = validateFile(value)
            updated.error = err || ''
            updated.fileName = value.name
            updated.fileSize = value.size
          } else {
            updated.fileName = ''
            updated.fileSize = 0
            updated.error = ''
          }
        }
        return updated
      })
    )
  }

  function handleRemoveRow(type, rowId) {
    const rows = type === 'SALARY' ? salaryRows : bankRows
    const idx = rows.findIndex((r) => r.id === rowId)
    if (idx === -1) return
    if (rows.length > 3 && idx < salaryDetailList.length) {
      handleRemoveSalaryRow(salaryDetailList[idx].id)
    } else {
      updateRowField(type, rowId, 'file', null)
    }
  }

  function handleAddRow(type) {
    handleAddSalaryRow()
  }

  // --- Handlers for Replacing Persisted Documents ---
  function toggleReplaceMode(docId) {
    setActiveReplaceIds((prev) => {
      const next = new Set(prev)
      if (next.has(docId)) {
        next.delete(docId)
        setStagedSalaryReplacements((r) => {
          const c = { ...r }
          delete c[docId]
          return c
        })
        setStagedBankReplacements((r) => {
          const c = { ...r }
          delete c[docId]
          return c
        })
      } else {
        next.add(docId)
      }
      return next
    })
  }

  function handleSelectReplacement(doc, file) {
    if (!file) return
    const err = validateFile(file)
    const isConsol = Boolean(isDocConsolidated(doc))
    const payload = {
      file,
      fileName: file.name,
      fileSize: file.size,
      month: doc.reporting_month || doc.coverage_start_month || 1,
      year: doc.reporting_year || doc.coverage_start_year || currentYear,
      replaceId: doc.id,
      employer_id: doc.employer_id,
      is_consolidated: isConsol,
      coverage_start_month: doc.coverage_start_month || doc.reporting_month || null,
      coverage_start_year: doc.coverage_start_year || doc.reporting_year || null,
      coverage_end_month: doc.coverage_end_month || doc.reporting_month || null,
      coverage_end_year: doc.coverage_end_year || doc.reporting_year || null,
      covered_months: doc.covered_months || null,
      error: err || '',
    }
    if (doc.document_type === 'SALARY_SLIP') {
      setStagedSalaryReplacements((prev) => ({ ...prev, [doc.id]: payload }))
    } else {
      setStagedBankReplacements((prev) => ({ ...prev, [doc.id]: payload }))
    }
  }

  // --- Submission Pre-Validation ---
  function validateSubmissionPackage() {
    // Check if staged files have validation errors
    if (stagedAppointment && appointmentError) {
      return `Appointment letter validation failed: ${appointmentError}`
    }
    for (const [empId, err] of Object.entries(appointmentErrors)) {
      if (err) return `Appointment letter error for employer: ${err}`
    }
    if (stagedOtherDoc && otherDocError) {
      return `Other document validation failed: ${otherDocError}`
    }

    const stagedSalaryEntries = [
      ...salaryRows.filter((r) => r.file),
      ...Object.values(stagedSalaryReplacements).filter((r) => r.file),
    ]
    const stagedSalaryMonths = new Set()
    for (const item of stagedSalaryEntries) {
      if (item.error) {
        return `Salary slip error for ${MONTH_NAMES[item.month - 1]} ${item.year}: ${item.error}`
      }
      const key = `${item.year}-${item.month}`
      if (stagedSalaryMonths.has(key)) {
        return `Duplicate reporting period selected for Salary Slips: ${MONTH_NAMES[item.month - 1]} ${item.year}.`
      }
      stagedSalaryMonths.add(key)
    }

    const stagedBankEntries = [
      ...bankRows.filter((r) => r.file),
      ...Object.values(stagedBankReplacements).filter((r) => r.file),
    ]
    const stagedBankMonths = new Set()
    for (const item of stagedBankEntries) {
      if (item.error) {
        return `Bank statement error for ${MONTH_NAMES[(item.month || 1) - 1]} ${item.year}: ${item.error}`
      }
      if (!item.replaceId && !item.is_consolidated) {
        const key = `${item.year}-${item.month}`
        if (stagedBankMonths.has(key)) {
          return `Duplicate reporting period selected for Bank Statements: ${MONTH_NAMES[(item.month || 1) - 1]} ${item.year}.`
        }
        stagedBankMonths.add(key)
      }
    }

    const stagedApptEntries = Object.entries(stagedAppointments).filter(([_, v]) => v?.file)
    const stagedApptCount = stagedApptEntries.length || (stagedAppointment?.file ? 1 : 0)
    const stagedConsolidatedCount = stagedConsolidatedBankDocs.filter((c) => c.file).length

    const totalFilesToSubmit =
      stagedApptCount +
      stagedSalaryEntries.length +
      stagedBankEntries.length +
      stagedConsolidatedCount +
      (stagedOtherDoc?.file ? 1 : 0)

    if (totalFilesToSubmit === 0) {
      return 'No new or replacement files have been staged for upload.'
    }

    return null
  }

  function handleOpenReviewModal() {
    const validationError = validateSubmissionPackage()
    if (validationError) {
      setError(validationError)
      window.scrollTo({ top: 0, behavior: 'smooth' })
      return
    }
    setError('')
    setShowReviewModal(true)
  }

  // --- Final Atomic Submission Execution ---
  async function handleFinalSubmit() {
    setSubmitting(true)
    setError('')

    try {
      const formData = new FormData()

      // Appointment Letters (Multi-Employer Support)
      const stagedApptList = Object.entries(stagedAppointments).filter(([_, v]) => v?.file)
      if (stagedApptList.length > 0) {
        const apptMeta = []
        for (const [empId, staged] of stagedApptList) {
          formData.append('appointment_letters', staged.file)
          apptMeta.push({
            employer_id: empId,
            replace_id: staged.replaceId || null,
          })
        }
        formData.append('appointment_letters_meta', JSON.stringify(apptMeta))
      } else if (stagedAppointment?.file) {
        formData.append('appointment_letter', stagedAppointment.file)
        if (stagedAppointment.replaceId) {
          formData.append('appointment_replace_id', stagedAppointment.replaceId)
        }
        if (employerList[0]?.id) {
          formData.append('appointment_employer_id', employerList[0].id)
        }
      }

      // Salary Slips
      const salaryMeta = []
      for (let i = 0; i < salaryRows.length; i++) {
        const row = salaryRows[i]
        if (row.file) {
          const matchedSal = salaryDetailList[i]
          const empId = matchedSal?.employer_id || employerList[0]?.id || null
          formData.append('salary_slips', row.file)
          salaryMeta.push({
            month: Number(row.month),
            year: Number(row.year),
            employer_id: empId,
            replace_id: null,
          })
        }
      }
      for (const [replaceId, repl] of Object.entries(stagedSalaryReplacements)) {
        if (repl.file) {
          const origDoc = salarySlips.find((d) => d.id === replaceId)
          formData.append('salary_slips', repl.file)
          salaryMeta.push({
            month: Number(repl.month),
            year: Number(repl.year),
            employer_id: origDoc?.employer_id || employerList[0]?.id || null,
            replace_id: replaceId,
          })
        }
      }
      formData.append('salary_slips_meta', JSON.stringify(salaryMeta))

      // Bank Statements
      const bankMeta = []
      for (let i = 0; i < bankRows.length; i++) {
        const row = bankRows[i]
        if (row.file) {
          const matchedSal = salaryDetailList[i]
          const empId = matchedSal?.employer_id || employerList[0]?.id || null
          formData.append('bank_statements', row.file)
          bankMeta.push({
            month: Number(row.month),
            year: Number(row.year),
            employer_id: empId,
            is_consolidated: false,
            replace_id: null,
          })
        }
      }
      for (const [replaceId, repl] of Object.entries(stagedBankReplacements)) {
        if (repl.file) {
          const origDoc = bankStatements.find((d) => d.id === replaceId)
          const isConsol = Boolean(repl.is_consolidated ?? isDocConsolidated(origDoc))
          formData.append('bank_statements', repl.file)
          bankMeta.push({
            month: Number(repl.month || origDoc?.coverage_start_month || origDoc?.reporting_month || 1),
            year: Number(repl.year || origDoc?.coverage_start_year || origDoc?.reporting_year || currentYear),
            employer_id: repl.employer_id || origDoc?.employer_id || employerList[0]?.id || null,
            is_consolidated: isConsol,
            coverage_start_month: isConsol ? Number(repl.coverage_start_month || origDoc?.coverage_start_month || origDoc?.reporting_month || repl.month) : null,
            coverage_start_year: isConsol ? Number(repl.coverage_start_year || origDoc?.coverage_start_year || origDoc?.reporting_year || repl.year) : null,
            coverage_end_month: isConsol ? Number(repl.coverage_end_month || origDoc?.coverage_end_month || origDoc?.reporting_month || repl.month) : null,
            coverage_end_year: isConsol ? Number(repl.coverage_end_year || origDoc?.coverage_end_year || origDoc?.reporting_year || repl.year) : null,
            covered_months: isConsol ? (repl.covered_months || origDoc?.covered_months || null) : null,
            replace_id: replaceId,
          })
        }
      }
      // Consolidated Multi-Month Bank Statements
      for (const c of stagedConsolidatedBankDocs) {
        if (c.file) {
          formData.append('bank_statements', c.file)
          let covered = c.covered_months
          if (!covered || !covered.length) {
            covered = []
            let sm = Number(c.coverage_start_month)
            let sy = Number(c.coverage_start_year)
            let em = Number(c.coverage_end_month)
            let ey = Number(c.coverage_end_year)
            let curY = sy
            let curM = sm
            while (curY < ey || (curY === ey && curM <= em)) {
              covered.push({ month: curM, year: curY })
              curM++
              if (curM > 12) {
                curM = 1
                curY++
              }
            }
          }
          bankMeta.push({
            month: Number(c.coverage_start_month),
            year: Number(c.coverage_start_year),
            employer_id: c.employer_id || employerList[0]?.id || null,
            is_consolidated: true,
            coverage_start_month: Number(c.coverage_start_month),
            coverage_start_year: Number(c.coverage_start_year),
            coverage_end_month: Number(c.coverage_end_month),
            coverage_end_year: Number(c.coverage_end_year),
            covered_months: covered,
            replace_id: null,
          })
        }
      }
      formData.append('bank_statements_meta', JSON.stringify(bankMeta))

      if (stagedOtherDoc?.file) {
        formData.append('other_document', stagedOtherDoc.file)
        if (otherDocTitle && otherDocTitle.trim()) {
          formData.append('other_document_title', otherDocTitle.trim())
        }
        if (stagedOtherDoc.replaceId) {
          formData.append('other_document_replace_id', stagedOtherDoc.replaceId)
        }
      }
      formData.append('allow_partial', 'true')

      const res = await api(`/candidates/${sel.cand}/documents/submit`, null, {
        method: 'POST',
        body: formData,
      })

      setShowReviewModal(false)
      clearStagedFiles()
      await refreshDocuments(sel.cand)
      if (candDetail) {
        await loadAudit(sel.cand, candDetail)
      }

      const individualBankMonths = bankMeta
        .filter((m) => !m.is_consolidated)
        .map((m) => `${MONTH_NAMES[m.month - 1]} ${m.year}`)

      const consolidatedBankStatements = bankMeta
        .filter((m) => m.is_consolidated)
        .map((m) => {
          let months = []
          if (Array.isArray(m.covered_months) && m.covered_months.length > 0) {
            months = m.covered_months.map((cm) => `${MONTH_NAMES[cm.month - 1]} ${cm.year}`)
          } else {
            let sm = Number(m.coverage_start_month)
            let sy = Number(m.coverage_start_year)
            let em = Number(m.coverage_end_month)
            let ey = Number(m.coverage_end_year)
            let curY = sy
            let curM = sm
            while (curY < ey || (curY === ey && curM <= em)) {
              months.push(`${MONTH_NAMES[curM - 1]} ${curY}`)
              curM++
              if (curM > 12) {
                curM = 1
                curY++
              }
            }
          }
          const emp = employerList.find((e) => String(e.id) === String(m.employer_id))
          return {
            employerName: emp?.employer_name || null,
            months,
            startText: `${MONTH_NAMES[m.coverage_start_month - 1]} ${m.coverage_start_year}`,
            endText: `${MONTH_NAMES[m.coverage_end_month - 1]} ${m.coverage_end_year}`,
          }
        })

      setSubmitSuccessData({
        candidateId: sel.cand,
        candidateName: `${candDetail.first_name} ${candDetail.last_name}`,
        appointmentUploaded: !!stagedAppointment?.file || Object.values(stagedAppointments).some((a) => a?.file),
        salaryMonths: salaryMeta.map((m) => `${MONTH_NAMES[m.month - 1]} ${m.year}`),
        bankMonths: individualBankMonths,
        individualBankMonths,
        consolidatedBankStatements,
        totalSubmitted: res.submitted_count,
      })
      setAuditToast({
        message: `✓ Successfully synced ${res.submitted_count} file(s) to Google Drive. Candidate and form data preserved.`,
        type: 'success',
      })
      fetchDashboardSummary(sel.state)
    } catch (err) {
      setShowReviewModal(false)
      setError(err.message || 'Submission failed. Any created Google Drive files were safely cleaned up.')
      setAuditToast({
        message: err.message || 'Drive sync failed. Staged files preserved for retry.',
        type: 'error',
      })
    } finally {
      setSubmitting(false)
    }
  }

  // Dismiss Drive upload confirmation modal without resetting the form or candidate
  function handleDismissUploadSuccess() {
    setSubmitSuccessData(null)
  }

  // Calculations for Checklist & Progress
  const stagedSalaryCount = salaryRows.filter((r) => r.file).length + Object.values(stagedSalaryReplacements).filter((r) => r.file).length
  const stagedConsolidatedCount = stagedConsolidatedBankDocs.filter((c) => c.file).length
  const stagedBankCount = bankRows.filter((r) => r.file).length + Object.values(stagedBankReplacements).filter((r) => r.file).length + stagedConsolidatedCount
  const otherDocStagedCount = stagedOtherDoc?.file ? 1 : 0
  const stagedApptCount = Object.values(stagedAppointments).filter((a) => a?.file).length || (stagedAppointment?.file ? 1 : 0)
  const totalStagedFiles = stagedApptCount + stagedSalaryCount + stagedBankCount + otherDocStagedCount

  // Candidate initials
  const candInitials = candDetail
    ? `${candDetail.first_name?.[0] || ''}${candDetail.last_name?.[0] || ''}`.toUpperCase() || 'CP'
    : 'CP'

  return (
    <div className="l1-dashboard">
      {/* Dashboard Summary Error Banner with Retry */}
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
            marginBottom: '16px',
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
            className="l1-btn-secondary"
            style={{ padding: '5px 14px', fontSize: '13px', cursor: 'pointer', whiteSpace: 'nowrap' }}
            onClick={() => fetchDashboardSummary(sel.state)}
          >
            ↻ Retry Metrics
          </button>
        </div>
      )}

      {/* --------------------------------------------------------------------
         1. Compact Dashboard Summary Cards (Top of Dashboard)
         -------------------------------------------------------------------- */}
      <section className="l1-compact-summary-row" aria-label="Candidate Summary Statistics">
        {/* 1. Total */}
        <div
          className={`l1-compact-card total ${activeCardFilter === 'total' ? 'active' : ''}`}
          onClick={() => handleCardClick('total')}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && handleCardClick('total')}
          aria-label={`Total candidates: ${loadingSummary ? 'Loading' : summaryData ? summaryData.total : 'Unavailable'}. Click to view list.`}
        >
          <div className="l1-compact-card-meta">
            <span className="l1-compact-card-icon">👥</span>
            <span className="l1-compact-card-title">Total</span>
          </div>
          <div className="l1-compact-card-count">
            {loadingSummary ? '…' : summaryError ? '—' : (summaryData ? summaryData.total : '—')}
          </div>
        </div>

        {/* 2. Uploaded */}
        <div
          className={`l1-compact-card uploaded ${activeCardFilter === 'cpass_uploaded' ? 'active' : ''}`}
          onClick={() => handleCardClick('cpass_uploaded')}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && handleCardClick('cpass_uploaded')}
          aria-label={`Uploaded candidates: ${loadingSummary ? 'Loading' : summaryData ? summaryData.cpass_uploaded : 'Unavailable'}. Click to view list.`}
        >
          <div className="l1-compact-card-meta">
            <span className="l1-compact-card-icon">⬆</span>
            <span className="l1-compact-card-title">Uploaded</span>
          </div>
          <div className="l1-compact-card-count">
            {loadingSummary ? '…' : summaryError ? '—' : (summaryData ? summaryData.cpass_uploaded : '—')}
          </div>
        </div>

        {/* 3. Approved */}
        <div
          className={`l1-compact-card approved ${activeCardFilter === 'cpass_approved' ? 'active' : ''}`}
          onClick={() => handleCardClick('cpass_approved')}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && handleCardClick('cpass_approved')}
          aria-label={`Approved candidates: ${loadingSummary ? 'Loading' : summaryData ? summaryData.cpass_approved : 'Unavailable'}. Click to view list.`}
        >
          <div className="l1-compact-card-meta">
            <span className="l1-compact-card-icon">✓</span>
            <span className="l1-compact-card-title">Approved</span>
          </div>
          <div className="l1-compact-card-count">
            {loadingSummary ? '…' : summaryError ? '—' : (summaryData ? summaryData.cpass_approved : '—')}
          </div>
        </div>

        {/* 4. Rejected */}
        <div
          className={`l1-compact-card rejected ${activeCardFilter === 'cpass_rejected' ? 'active' : ''}`}
          onClick={() => handleCardClick('cpass_rejected')}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && handleCardClick('cpass_rejected')}
          aria-label={`Rejected candidates: ${loadingSummary ? 'Loading' : summaryData ? summaryData.cpass_rejected : 'Unavailable'}. Click to view list.`}
        >
          <div className="l1-compact-card-meta">
            <span className="l1-compact-card-icon">✕</span>
            <span className="l1-compact-card-title">Rejected</span>
          </div>
          <div className="l1-compact-card-count">
            {loadingSummary ? '…' : summaryError ? '—' : (summaryData ? summaryData.cpass_rejected : '—')}
          </div>
        </div>

        {/* 5. In Progress */}
        <div
          className={`l1-compact-card in-progress ${activeCardFilter === 'in_progress' ? 'active' : ''}`}
          onClick={() => handleCardClick('in_progress')}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && handleCardClick('in_progress')}
          aria-label={`In Progress candidates: ${loadingSummary ? 'Loading' : summaryData ? (summaryData.in_progress ?? summaryData.cpass_in_progress ?? 0) : 'Unavailable'}. Click to view list.`}
        >
          <div className="l1-compact-card-meta">
            <span className="l1-compact-card-icon">🔄</span>
            <span className="l1-compact-card-title">In Progress</span>
          </div>
          <div className="l1-compact-card-count">
            {loadingSummary ? '…' : summaryError ? '—' : (summaryData ? (summaryData.in_progress ?? summaryData.cpass_in_progress ?? 0) : '—')}
          </div>
        </div>

        {/* 6. Pending */}
        <div
          className={`l1-compact-card pending ${activeCardFilter === 'pending_remaining' ? 'active' : ''}`}
          onClick={() => handleCardClick('pending_remaining')}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && handleCardClick('pending_remaining')}
          aria-label={`Pending candidates: ${loadingSummary ? 'Loading' : summaryData ? summaryData.pending_remaining : 'Unavailable'}. Click to view list.`}
        >
          <div className="l1-compact-card-meta">
            <span className="l1-compact-card-icon">⏱</span>
            <span className="l1-compact-card-title">Pending</span>
          </div>
          <div className="l1-compact-card-count">
            {loadingSummary ? '…' : summaryError ? '—' : (summaryData ? summaryData.pending_remaining : '—')}
          </div>
        </div>
      </section>

      {/* Global Error Banner */}
      {error && (
        <div className="l1-banner-danger" role="alert">
          <strong style={{ minWidth: '70px' }}>Notice:</strong>
          <div>{error}</div>
        </div>
      )}

      {/* --------------------------------------------------------------------
         Candidate List Popup / Modal (Opened when a card is clicked)
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
          aria-labelledby="l1-popup-title"
        >
          <div className="l1-cand-popup-dialog" onClick={(e) => e.stopPropagation()}>
            {/* Modal Header */}
            <div className="l1-cand-popup-header">
              <div className="l1-cand-popup-title-group">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="l1-cand-popup-icon">
                    {activeCardFilter === 'total' && '👥'}
                    {activeCardFilter === 'cpass_uploaded' && '⬆'}
                    {activeCardFilter === 'cpass_approved' && '✓'}
                    {activeCardFilter === 'cpass_rejected' && '✕'}
                    {activeCardFilter === 'in_progress' && '🔄'}
                    {activeCardFilter === 'pending_remaining' && '⏱'}
                  </span>
                  <h3 id="l1-popup-title">
                    {activeCardFilter === 'total' && 'Total Candidates'}
                    {activeCardFilter === 'cpass_uploaded' && 'Uploaded Candidates'}
                    {activeCardFilter === 'cpass_approved' && 'Approved Candidates'}
                    {activeCardFilter === 'cpass_rejected' && 'Rejected Candidates'}
                    {activeCardFilter === 'in_progress' && 'In Progress Candidates'}
                    {activeCardFilter === 'pending_remaining' && 'Pending Candidates'}
                  </h3>
                  <span className="l1-cand-popup-count-badge">
                    {cardCandLoading ? '…' : cardCandTotal}
                  </span>
                </div>
                <p className="l1-cand-popup-sub">
                  {activeCardFilter === 'total' && 'All candidates registered in your assigned state'}
                  {activeCardFilter === 'cpass_uploaded' && 'Candidates uploaded by Placement Coordinator'}
                  {activeCardFilter === 'cpass_approved' && 'Candidates approved during CPASS placement verification'}
                  {activeCardFilter === 'cpass_rejected' && 'Candidates rejected during CPASS placement verification'}
                  {activeCardFilter === 'in_progress' && 'Candidates whose verification process has started but is not yet completed, approved, or rejected'}
                  {activeCardFilter === 'pending_remaining' && 'Candidates not yet uploaded by Placement Coordinator (Total − Uploaded)'}
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
                            {(cand.return_reason || cand.rejection_reason) && (
                              <div
                                className="l1-cand-return-note"
                                title={`Reason: ${cand.return_reason || cand.rejection_reason}`}
                              >
                                ⚠️ {cand.return_reason || cand.rejection_reason}
                              </div>
                            )}
                          </td>
                          <td>{cand.father_name || '—'}</td>
                          <td title={cand.tc_name || ''}>{cand.tc_name || '—'}</td>
                          <td>{cand.batch_code || '—'}</td>
                          <td>
                            <span
                              className={getStageBadgeClass(cand.ch_status)}
                              title={cand.ch_status === 'Returned to L1' ? `Returned for corrections by CH: ${cand.return_reason || 'See dossier'}` : cand.ch_status}
                            >
                              {formatL1StageStatus(cand.ch_status)}
                            </span>
                          </td>
                          <td>
                            <span
                              className={getStageBadgeClass(cand.cops_status)}
                              title={cand.cops_status === 'Rejected' ? `Rejected by COPS: ${cand.rejection_reason || 'See dossier'}` : cand.cops_status}
                            >
                              {formatL1StageStatus(cand.cops_status)}
                            </span>
                          </td>
                          <td>
                            <span
                              className={getStageBadgeClass(cand.bl_status)}
                              title={cand.bl_status === 'Rejected' ? `Rejected by BL: ${cand.rejection_reason || 'See dossier'}` : cand.bl_status}
                            >
                              {formatL1StageStatus(cand.bl_status)}
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
                      ← Previous
                    </button>
                    <span className="l1-page-info">
                      Page <strong>{cardCandPage}</strong> of <strong>{cardCandPages}</strong> ({cardCandTotal} items)
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
                      Next →
                    </button>
                  </>
                )}
                {cardCandPages <= 1 && (
                  <span className="l1-page-info" style={{ color: 'var(--mut)' }}>
                    Showing <strong>{cardCandidates.length}</strong> of <strong>{cardCandTotal}</strong> candidates
                  </span>
                )}
              </div>

              <button
                type="button"
                className="l1-btn-secondary"
                style={{ padding: '7px 16px', fontSize: '13px' }}
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

      {/* --------------------------------------------------------------------
         Cascading Selector Stepper Toolbar (5 Levels)
         -------------------------------------------------------------------- */}
      <section className="l1-selector-panel">
        <div className="l1-selector-header">
          <h3>
            <span className="l1-step-indicator">1</span>
            Candidate Selection Pipeline
          </h3>
          {sel.state && (
            <button
              type="button"
              className="l1-btn-secondary"
              style={{ fontSize: '12px', padding: '4px 12px' }}
              onClick={() => pick('state', '')}
            >
              Reset Selection
            </button>
          )}
        </div>

        <div className="l1-selector-grid">
          {/* 1. State */}
          <div className="l1-select-field">
            <label className="l1-select-label" htmlFor="sel-state">
              <span className="l1-step-dot">1</span> State
            </label>
            <div className="l1-select-wrapper">
              <select
                id="sel-state"
                value={sel.state}
                onChange={(e) => pick('state', e.target.value)}
                disabled={lists.state.length === 0}
              >
                <option value="">
                  {lists.state.length === 0 ? 'No assigned states…' : 'Select State…'}
                </option>
                {lists.state.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
              <span className="l1-select-icon">▼</span>
            </div>
          </div>

          {/* 2. Training Centre */}
          <div className="l1-select-field">
            <label className="l1-select-label" htmlFor="sel-tc">
              <span className="l1-step-dot">2</span> Training Centre
            </label>
            <div className="l1-select-wrapper">
              <select
                id="sel-tc"
                value={sel.tc}
                disabled={!sel.state}
                onChange={(e) => pick('tc', e.target.value)}
              >
                <option value="">{sel.state ? 'Select Centre…' : 'Awaiting state…'}</option>
                {lists.tc.map((c) => (
                  <option key={c.tc_id} value={c.tc_id}>{c.name}</option>
                ))}
              </select>
              <span className="l1-select-icon">▼</span>
            </div>
          </div>

          {/* 3. Sanction Order */}
          <div className="l1-select-field">
            <label className="l1-select-label" htmlFor="sel-order">
              <span className="l1-step-dot">3</span> Sanction Order
            </label>
            <div className="l1-select-wrapper">
              <select
                id="sel-order"
                value={sel.order}
                disabled={!sel.tc}
                onChange={(e) => pick('order', e.target.value)}
              >
                <option value="">{sel.tc ? 'Select Order…' : 'Awaiting centre…'}</option>
                {lists.order.map((o) => (
                  <option key={o} value={o}>{o}</option>
                ))}
              </select>
              <span className="l1-select-icon">▼</span>
            </div>
          </div>

          {/* 4. Batch */}
          <div className="l1-select-field">
            <label className="l1-select-label" htmlFor="sel-batch">
              <span className="l1-step-dot">4</span> Batch
            </label>
            <div className="l1-select-wrapper">
              <select
                id="sel-batch"
                value={sel.batch}
                disabled={!sel.order}
                onChange={(e) => pick('batch', e.target.value)}
              >
                <option value="">{sel.order ? 'Select Batch…' : 'Awaiting order…'}</option>
                {lists.batch.map((b) => (
                  <option key={b.kb_batch_id} value={b.kb_batch_id}>{b.batch_code}</option>
                ))}
              </select>
              <span className="l1-select-icon">▼</span>
            </div>
          </div>

          {/* 5. Candidate */}
          <div className="l1-select-field">
            <label className="l1-select-label" htmlFor="sel-cand">
              <span className="l1-step-dot">5</span> Candidate
            </label>
            <div className="l1-select-wrapper">
              <select
                id="sel-cand"
                value={sel.cand}
                disabled={!sel.batch}
                onChange={(e) => pick('cand', e.target.value)}
              >
                <option value="">{sel.batch ? 'Select Candidate…' : 'Awaiting batch…'}</option>
                {lists.cand.map((c) => (
                  <option key={c.candidate_id} value={c.candidate_id}>
                    {name(c)} (Father: {c.father_name || '—'}) [ID: {c.candidate_id}]
                  </option>
                ))}
              </select>
              <span className="l1-select-icon">▼</span>
            </div>
          </div>
        </div>
      </section>

      {/* Loading detail indicator */}
      {loadingDetail && (
        <div className="l1-doc-workspace" style={{ textAlign: 'center', padding: '32px' }}>
          <p className="muted" style={{ margin: 0, fontSize: '14.5px' }}>
            Loading candidate placement records & verification history…
          </p>
        </div>
      )}

      <div id="candidate-dossier-anchor" />
      {candDetail && (
        <section className="l1-cand-summary-card">
          <div className="l1-cand-header">
            <div className="l1-cand-identity">
              <div className="l1-cand-avatar" style={{ background: 'linear-gradient(135deg, #0284C7 0%, #0369A1 100%)' }}>📦</div>
              <div className="l1-cand-names">
                <h2>Batch Details</h2>
                <div className="l1-cand-id-badge">
                  Batch Code: <strong>{candDetail.batch_code || lists.batch.find((b) => b.kb_batch_id === sel.batch)?.batch_code || sel.batch || '—'}</strong>
                </div>
              </div>
            </div>
            <div>
              <span className="l1-status-pill info">
                {candDetail.state_name || sel.state || 'DDU-GKY'}
              </span>
            </div>
          </div>

          <div className="l1-cand-meta-grid">
            <div className="l1-meta-item">
              <span className="l1-meta-label">Batch Code / ID</span>
              <span className="l1-meta-val">{candDetail.batch_code || lists.batch.find((b) => b.kb_batch_id === sel.batch)?.batch_code || sel.batch || '—'}</span>
            </div>
            <div className="l1-meta-item">
              <span className="l1-meta-label">Batch Start Date</span>
              <span className="l1-meta-val">{candDetail.batch_start_date || '—'}</span>
            </div>
            <div className="l1-meta-item">
              <span className="l1-meta-label">Batch End Date</span>
              <span className="l1-meta-val">{candDetail.batch_end_date || '—'}</span>
            </div>
            <div className="l1-meta-item">
              <span className="l1-meta-label">Trade / Course Name</span>
              <span className="l1-meta-val">{candDetail.trade_name || '—'}</span>
            </div>
            <div className="l1-meta-item">
              <span className="l1-meta-label">Sanction Order</span>
              <span className="l1-meta-val">{candDetail.sanction_order_number || sel.order || '—'}</span>
            </div>
            <div className="l1-meta-item">
              <span className="l1-meta-label">Training Centre</span>
              <span className="l1-meta-val">{candDetail.tc_name || lists.tc.find((c) => c.tc_id === sel.tc)?.name || sel.tc}</span>
            </div>
            <div className="l1-meta-item">
              <span className="l1-meta-label">Centre State</span>
              <span className="l1-meta-val">{candDetail.tc_state_name || sel.state || '—'}</span>
            </div>
          </div>
        </section>
      )}


      {/* --------------------------------------------------------------------
         Unified Continuous L1 Placement Verification & Audit Workflow
         -------------------------------------------------------------------- */}
      {sel.cand && (
        <ErrorBoundary title="Placement Audit Statement Workflow">
          <div className="l1-audit-workflow-container" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {/* Audit Header Actions Bar */}
            <div className="l1-audit-actions-bar">
              <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
                <span className={`l1-audit-status-badge ${isAuditReturnedOrRejected ? 'rejected' : (isAuditSubmitted ? 'submitted' : 'draft')
                  }`}>
                  <span style={{ fontSize: '10px' }}>●</span>
                  {isAuditReturnedOrRejected
                    ? 'REJECTED'
                    : (isAuditSubmitted ? 'SUBMITTED & FINALIZED' : 'AUDIT DRAFT IN PROGRESS')}
                </span>
                {auditRecord?.updated_at && (
                  <span style={{ fontSize: '13px', color: 'var(--mut)' }}>
                    Last saved: {new Date(auditRecord.updated_at).toLocaleString('en-IN')}
                  </span>
                )}
              </div>

              <div className="l1-audit-btn-group">
                {auditRecord && (
                  <button
                    type="button"
                    className="l1-btn-secondary"
                    onClick={handleOpenStatementModal}
                    disabled={loadingStatement}
                    style={{ padding: '8px 16px', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}
                  >
                    <span>📄</span> {loadingStatement ? 'Loading...' : 'Preview Statement'}
                  </button>
                )}
                {!isAuditSubmitted && (
                  <>
                    <button
                      type="button"
                      className="l1-btn-secondary"
                      onClick={() => handleSaveDraft(false)}
                      disabled={auditSavingDraft || auditSubmitting || !candDetail || Boolean(auditLoadError)}
                      style={{ padding: '8px 16px', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}
                    >
                      <span>💾</span> {auditSavingDraft ? 'Saving Draft...' : 'Save Draft'}
                    </button>
                    <button
                      type="button"
                      className="l1-btn-primary-action"
                      onClick={handleSubmitAuditStatement}
                      disabled={auditSubmitting || auditSavingDraft || !candDetail || candDetail?.has_active_hold || Boolean(auditLoadError)}
                      style={{ padding: '8px 18px', fontSize: '13px' }}
                    >
                      {auditSubmitting ? 'Preparing Statement…' : 'Preview & Submit →'}
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Audit Load Error Notice Banner */}
            {auditLoadError && (
              <div style={{ background: '#FFF7ED', border: '1px solid #FED7AA', borderRadius: '14px', padding: '14px 18px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span style={{ fontSize: '20px' }}>⚠️</span>
                  <div style={{ fontSize: '13.5px', color: '#9A3412' }}>
                    <strong>Audit Record Notice:</strong> {auditLoadError} Showing editable draft form.
                  </div>
                </div>
                {candDetail && (
                  <button
                    type="button"
                    className="l1-btn-secondary"
                    onClick={() => loadAudit(sel.cand, candDetail)}
                    disabled={loadingAudit}
                    style={{ padding: '6px 14px', fontSize: '12.5px' }}
                  >
                    {loadingAudit ? 'Retrying...' : '↻ Retry Loading'}
                  </button>
                )}
              </div>
            )}

            {loadingDetail ? (
              <div className="l1-audit-card" style={{ textAlign: 'center', padding: '48px 24px' }}>
                <div style={{ fontSize: '28px', marginBottom: '12px' }}>⏳</div>
                <h3 style={{ margin: 0, fontSize: '16px', color: 'var(--txt)' }}>Loading Candidate Dossier…</h3>
                <p className="muted" style={{ margin: '6px 0 0', fontSize: '13.5px' }}>
                  Retrieving candidate placement records and verification history from master database.
                </p>
              </div>
            ) : !candDetail ? (
              <div className="l1-audit-card" style={{ textAlign: 'center', padding: '48px 24px' }}>
                <div style={{ fontSize: '28px', marginBottom: '12px' }}>⚠️</div>
                <h3 style={{ margin: 0, fontSize: '16px', color: 'var(--txt)' }}>Candidate Profile Not Loaded</h3>
                <p className="muted" style={{ margin: '6px 0 16px', fontSize: '13.5px' }}>
                  Unable to load candidate details. Please verify your connection and retry.
                </p>
                <button
                  type="button"
                  className="l1-btn-secondary"
                  onClick={() => {
                    if (sel.cand) {
                      setLoadingDetail(true)
                      api(`/lookups/candidates/${sel.cand}`)
                        .then((detail) => {
                          setCandDetail(detail)
                          refreshDocuments(sel.cand)
                          loadAudit(sel.cand, detail)
                        })
                        .catch((e) => setError(e.message))
                        .finally(() => setLoadingDetail(false))
                    }
                  }}
                  style={{ padding: '8px 16px', fontSize: '13px' }}
                >
                  ↻ Retry Loading Candidate
                </button>
              </div>
            ) : (
              <>
                {/* Rejection / Return Notice Banner */}
                {isAuditReturnedOrRejected && (
                  <div className="l1-rejection-banner">
                    <div className="l1-rejection-banner-content">
                      <span className="l1-rejection-icon">⚠️</span>
                      <div style={{ flex: 1 }}>
                        <div className="l1-rejection-title">
                          <strong>Placement Audit Rejected by {rejectionAuthorityName}</strong>
                          <span className="l1-stage-badge rejected" style={{ marginLeft: '8px' }}>Rejected</span>
                        </div>
                        <div className="l1-rejection-desc">
                          {isReturnedToL1
                            ? 'This candidate placement dossier was returned to L1 coordinator for corrections. Please review the reason and remarks below, update any necessary employment records, salary details, or payslips, and resubmit the statement for Centre Head review.'
                            : 'This candidate placement audit was rejected during verification and review.'}
                        </div>
                        {rejectionReason && (
                          <div className="l1-rejection-reason">
                            <strong>Rejection Reason:</strong> "{rejectionReason}"
                          </div>
                        )}
                        {rejectionRemarks && rejectionRemarks !== rejectionReason && (
                          <div className="l1-rejection-remarks">
                            <strong>Reviewer Remarks:</strong> {rejectionRemarks}
                          </div>
                        )}
                        {returnedByName && (
                          <div className="l1-rejection-meta">
                            Returned / Rejected by <strong>{returnedByName}</strong> ({rejectionStageLabel})
                            {returnedAtDate ? ` on ${new Date(returnedAtDate).toLocaleString('en-IN')}` : ''}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {/* Status Notice if Submitted */}
                {isAuditSubmitted && !isAuditReturnedOrRejected && (
                  <div style={{ background: '#F0FDF4', border: '1px solid #BBF7D0', borderRadius: '16px', padding: '16px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <span style={{ fontSize: '24px' }}>🔒</span>
                      <div>
                        <strong style={{ color: '#166534', fontSize: '14.5px' }}>Placement Audit Statement Finalized</strong>
                        <div style={{ fontSize: '13px', color: '#15803D', marginTop: '2px' }}>
                          This audit was submitted on {new Date(auditRecord?.finalized_at || auditRecord?.updated_at).toLocaleString('en-IN')}. It is permanently recorded and locked for coordinator review.
                        </div>
                      </div>
                    </div>
                    <button
                      type="button"
                      className="l1-btn-primary-action"
                      onClick={handleOpenStatementModal}
                      style={{ padding: '8px 16px', fontSize: '13px' }}
                    >
                      📄 View &amp; Print Official Statement
                    </button>
                  </div>
                )}

                {/* Hold Warning if Active */}
                {candDetail?.has_active_hold && (
                  <div style={{ background: '#FFF1F2', border: '1px solid #FECDD3', borderRadius: '14px', padding: '14px 18px', display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <span style={{ fontSize: '20px' }}>⚠️</span>
                    <div style={{ fontSize: '13.5px', color: '#9F1239' }}>
                      <strong>Administrative Hold Active:</strong> {candDetail.active_holds?.[0]?.hold_reason || 'Hold placed by manager'}. You can save drafts, but final statement submission is blocked.
                    </div>
                  </div>
                )}


                {/* Section 1: Candidate Placement Dossier */}
                <div className="l1-audit-card">
                  <div className="l1-audit-card-header">
                    <div className="l1-audit-card-title">
                      <span style={{ fontSize: '20px' }}>👤</span>
                      <div>
                        <h3>1. Candidate Placement Dossier</h3>
                        <p>Verified candidate registration and batch allocation records from DDU-GKY Master</p>
                      </div>
                    </div>
                    <div>
                      <span className={`l1-status-pill ${candDetail?.appointed ? 'success' : 'info'}`}>
                        {candDetail?.appointed ? '✓ Placed & Appointed' : '● Under Training / Pending Placement'}
                      </span>
                    </div>
                  </div>

                  {/* Informational Duplicate Warning */}
                  {candDetail?.has_duplicate_warning && (
                    <div className="l1-banner-warning" role="status" style={{ margin: '0 0 16px 0' }}>
                      <span style={{ fontSize: '16px' }}>ℹ️</span>
                      <div>
                        <strong>Informational Notice:</strong> Possible duplicate candidate record under administrative review. This notice does not block placement verification or file submission.
                      </div>
                    </div>
                  )}

                  {/* Blocking Submission Hold */}
                  {candDetail?.has_active_hold && (
                    <div className="l1-banner-danger" role="alert" style={{ margin: '0 0 16px 0' }}>
                      <span style={{ fontSize: '18px' }}>⚠️</span>
                      <div>
                        <strong>Placement Submission Blocked:</strong> Administrative hold in effect ({candDetail.active_holds?.[0]?.hold_reason || 'Under review hold placed by centre manager'}). Final document upload is locked until the hold is resolved.
                      </div>
                    </div>
                  )}

                  <div className="cpass-dossier-grid">
                    <div className="cpass-dossier-item">
                      <span className="k">Candidate Name</span>
                      <span className="v">{name(candDetail) || 'Not Available'}</span>
                    </div>
                    <div className="cpass-dossier-item">
                      <span className="k">Candidate ID</span>
                      <span className="v">{candDetail?.candidate_id || sel.cand || 'Not Available'}</span>
                    </div>
                    <div className="cpass-dossier-item">
                      <span className="k">State</span>
                      <span className="v">{candDetail?.state_name || sel.state || 'Not Available'}</span>
                    </div>
                    <div className="cpass-dossier-item">
                      <span className="k">Training Centre</span>
                      <span className="v">{candDetail?.tc_name || lists.tc.find((c) => c.tc_id === sel.tc)?.name || sel.tc || 'Not Available'}</span>
                    </div>
                    <div className="cpass-dossier-item">
                      <span className="k">Sanction Order</span>
                      <span className="v">{candDetail?.sanction_order_number || sel.order || 'Not Available'}</span>
                    </div>
                    <div className="cpass-dossier-item">
                      <span className="k">Batch Code / KB Batch ID</span>
                      <span className="v">
                        {candDetail?.batch_code || lists.batch.find((b) => b.kb_batch_id === sel.batch)?.batch_code || (candDetail?.kb_batch_id ? String(candDetail.kb_batch_id) : 'Not Available')}
                      </span>
                    </div>
                    <div className="cpass-dossier-item">
                      <span className="k">Course / Trade Name</span>
                      <span className="v">{candDetail?.trade_name || candDetail?.course_name || 'Not Available'}</span>
                    </div>
                    <div className="cpass-dossier-item">
                      <span className="k">Batch Start Date</span>
                      <span className="v">{candDetail?.batch_start_date || 'Not Available'}</span>
                    </div>
                    <div className="cpass-dossier-item">
                      <span className="k">Batch End Date</span>
                      <span className="v">{candDetail?.batch_end_date || 'Not Available'}</span>
                    </div>
                    <div className="cpass-dossier-item">
                      <span className="k">Father's Name</span>
                      <span className="v">{candDetail?.father_name || candDetail?.candidate_father_name || 'Not Available'}</span>
                    </div>
                    <div className="cpass-dossier-item">
                      <span className="k">Gender</span>
                      <span className="v">{candDetail?.gender || 'Not Available'}</span>
                    </div>
                    <div className="cpass-dossier-item">
                      <span className="k">Date of Birth</span>
                      <span className="v">{candDetail?.dob || candDetail?.date_of_birth || 'Not Available'}</span>
                    </div>
                    <div className="cpass-dossier-item">
                      <span className="k">Mobile Number</span>
                      <span className="v">{candDetail?.mobile || candDetail?.mobile_number || 'Not Available'}</span>
                    </div>
                    <div className="cpass-dossier-item">
                      <span className="k">Candidate Email</span>
                      <span className="v">{candDetail?.candidate_email || 'Not Available'}</span>
                    </div>
                    <div className="cpass-dossier-item">
                      <span className="k">Qualification</span>
                      <span className="v">{candDetail?.candidate_qualification || candDetail?.qualification || 'Not Available'}</span>
                    </div>
                    <div className="cpass-dossier-item">
                      <span className="k">Aadhaar (Masked)</span>
                      <span className="v">
                        {candDetail?.masked_aadhaar || (candDetail?.aadhaar_number ? `XXXX-XXXX-${String(candDetail.aadhaar_number).slice(-4)}` : (candDetail?.aadhar ? `XXXX-XXXX-${String(candDetail.aadhar).slice(-4)}` : 'Not Available'))}
                      </span>
                    </div>
                    <div className="cpass-dossier-item">
                      <span className="k">Bank Account (Masked)</span>
                      <span className="v">
                        {candDetail?.masked_bank_account || (candDetail?.bank_account ? `XXXX-XXXX-${String(candDetail.bank_account).slice(-4)}` : 'Not Available')}
                      </span>
                    </div>
                    <div className="cpass-dossier-item" style={{ gridColumn: 'span 2' }}>
                      <span className="k">Address</span>
                      <span className="v" title={candDetail?.address || candDetail?.permanent_address}>
                        {candDetail?.address || candDetail?.permanent_address || 'Not Available'}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Section 2: Employer Details Card */}
                <div className="l1-audit-card">
                  <div className="l1-audit-card-header">
                    <div className="l1-audit-card-title">
                      <span style={{ fontSize: '20px' }}>🏢</span>
                      <div>
                        <h3>2. Placement &amp; Employer Information</h3>
                        <p>Details of employing organization, job role, appointment date, CTC, and minimum wages</p>
                      </div>
                    </div>
                    {!isAuditSubmitted && employerList.length < 5 && (
                      <button
                        type="button"
                        className="l1-btn-add-employer"
                        onClick={handleAddEmployerRow}
                      >
                        <span>+</span> Add Another Employer
                      </button>
                    )}
                  </div>

                  <div className="l1-table-responsive">
                    <table className="l1-audit-table">
                      <thead>
                        <tr>
                          <th style={{ width: '40px' }}>#</th>
                          <th>Employer Name *</th>
                          <th style={{ width: '130px' }}>Months Worked</th>
                          <th style={{ width: '150px' }}>Appointment Date</th>
                          <th>Designation</th>
                          <th>Place of Work</th>
                          <th style={{ width: '130px' }}>Monthly CTC (₹)</th>
                          <th style={{ width: '130px' }}>Minimum Wages (₹)</th>
                          {!isAuditSubmitted && employerList.length > 1 && <th style={{ width: '60px', textAlign: 'center' }}>Action</th>}
                        </tr>
                      </thead>
                      <tbody>
                        {employerList.map((emp, idx) => (
                          <tr key={emp.id || idx}>
                            <td>{idx + 1}</td>
                            <td>
                              <input
                                type="text"
                                placeholder="e.g. Acme Tech Solutions"
                                value={emp.employer_name || ''}
                                onChange={(e) => handleUpdateEmployerField(emp.id, 'employer_name', e.target.value)}
                                disabled={isAuditSubmitted}
                              />
                            </td>
                            <td>
                              <input
                                type="number"
                                step="0.5"
                                min="0"
                                placeholder="e.g. 6"
                                value={emp.months_worked ?? ''}
                                onChange={(e) => handleUpdateEmployerField(emp.id, 'months_worked', e.target.value)}
                                disabled={isAuditSubmitted}
                              />
                            </td>
                            <td>
                              <input
                                type="date"
                                value={emp.appointment_date || ''}
                                onChange={(e) => handleUpdateEmployerField(emp.id, 'appointment_date', e.target.value)}
                                disabled={isAuditSubmitted}
                              />
                            </td>
                            <td>
                              <input
                                type="text"
                                placeholder="e.g. Junior Technician"
                                value={emp.designation || ''}
                                onChange={(e) => handleUpdateEmployerField(emp.id, 'designation', e.target.value)}
                                disabled={isAuditSubmitted}
                              />
                            </td>
                            <td>
                              <input
                                type="text"
                                placeholder="e.g. Hyderabad, Telangana"
                                value={emp.place_of_work || ''}
                                onChange={(e) => handleUpdateEmployerField(emp.id, 'place_of_work', e.target.value)}
                                disabled={isAuditSubmitted}
                              />
                            </td>
                            <td>
                              <input
                                type="number"
                                placeholder="0"
                                min="0"
                                value={emp.monthly_ctc ?? ''}
                                onChange={(e) => handleUpdateEmployerField(emp.id, 'monthly_ctc', e.target.value)}
                                disabled={isAuditSubmitted}
                              />
                            </td>
                            <td>
                              <input
                                type="number"
                                placeholder="0"
                                min="0"
                                value={emp.minimum_wages ?? ''}
                                onChange={(e) => handleUpdateEmployerField(emp.id, 'minimum_wages', e.target.value)}
                                disabled={isAuditSubmitted}
                              />
                            </td>
                            {!isAuditSubmitted && employerList.length > 1 && (
                              <td style={{ textAlign: 'center' }}>
                                <button
                                  type="button"
                                  className="l1-btn-table-danger"
                                  onClick={() => handleRemoveEmployerRow(emp.id)}
                                  title={`Remove Employer ${emp.employer_name ? `"${emp.employer_name}"` : idx + 1}`}
                                  aria-label={`Remove Employer ${emp.employer_name ? `"${emp.employer_name}"` : idx + 1}`}
                                >
                                  🗑️
                                </button>
                              </td>
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Section 3: Monthly Salary Disbursement Record */}
                <div className="l1-audit-card">
                  <div className="l1-audit-card-header">
                    <div className="l1-audit-card-title">
                      <span style={{ fontSize: '20px' }}>💰</span>
                      <div>
                        <h3>3. Monthly Salary Disbursement Record</h3>
                        <p>Monthly payroll details (at least 3 distinct months required to submit audit statement)</p>
                      </div>
                    </div>
                    {!isAuditSubmitted && salaryDetailList.length < 12 && (
                      <button
                        type="button"
                        className="l1-btn-add-month-header"
                        onClick={handleAddSalaryRow}
                      >
                        <span>+</span> Add Salary Month
                      </button>
                    )}
                  </div>

                  <div className="l1-salary-records-container">
                    {salaryDetailList.map((sal, idx) => {
                      const empSeq = getEmployerSalarySequence(sal, salaryDetailList)
                      const monthObj = MONTH_NAMES[(sal.month || 1) - 1] || `Month ${sal.month}`
                      const sEmpId = sal.employer_id || employerList[0]?.id
                      const matchedEmp = employerList.find((e) => e.id === sEmpId) || employerList[0]
                      const matchedEmpName = matchedEmp?.employer_name || `Employer 1`
                      const prevRecord = findPreviousSalaryRecordForEmployer(sal, salaryDetailList)
                      const hasPrev = !!prevRecord

                      return (
                        <div key={sal.id || idx} className="l1-salary-month-card">
                          <div className="l1-salary-month-header">
                            <div className="l1-salary-card-header-left">
                              <div className="l1-salary-badge-lockup">
                                <span className="l1-salary-month-badge">Month {empSeq}</span>
                                <span className="l1-salary-month-period-title">
                                  · {monthObj} {sal.year || 2024}
                                </span>
                              </div>
                            </div>

                            {employerList.length > 1 && (
                              <div className="l1-salary-card-header-mid">
                                <div className="l1-emp-picker-wrap" title={`Assigned Employer: ${matchedEmpName}`}>
                                  <label htmlFor={`emp-select-${sal.id || idx}`}>Employer:</label>
                                  <select
                                    id={`emp-select-${sal.id || idx}`}
                                    className="l1-emp-picker-select"
                                    value={sal.employer_id || employerList[0]?.id}
                                    onChange={(e) => handleUpdateSalaryField(sal.id, 'employer_id', e.target.value)}
                                    disabled={isAuditSubmitted}
                                    aria-label={`Month ${empSeq} Employer`}
                                    title={matchedEmpName}
                                  >
                                    {employerList.map((emp, eIdx) => (
                                      <option key={emp.id || eIdx} value={emp.id}>
                                        {emp.employer_name || `Employer ${eIdx + 1}`}
                                      </option>
                                    ))}
                                  </select>
                                </div>
                              </div>
                            )}

                            <div className="l1-salary-card-header-right">
                              <span
                                className="l1-salary-sync-chip"
                                title="Reporting period is synchronized across Salary Slips, Bank Statements, and Audit Evidence"
                              >
                                <span className="l1-sync-dot">●</span> Synced
                              </span>
                              {!isAuditSubmitted && (
                                <button
                                  type="button"
                                  className={`l1-btn-copy-prev ${!hasPrev ? 'is-disabled' : ''}`}
                                  onClick={() => handleCopyPreviousMonth(sal.id)}
                                  disabled={!hasPrev}
                                  title={
                                    hasPrev
                                      ? `Copy reusable salary fields from previous month (${MONTH_NAMES[(prevRecord.month || 1) - 1]} ${prevRecord.year}) for ${matchedEmpName}`
                                      : `No previous month exists for "${matchedEmpName}" to copy from`
                                  }
                                >
                                  <span className="l1-btn-icon">📋</span>
                                  <span>Copy Prev</span>
                                </button>
                              )}
                              {!isAuditSubmitted && salaryDetailList.length > 3 && (
                                <button
                                  type="button"
                                  className="l1-btn-remove-month"
                                  onClick={() => handleRemoveSalaryRow(sal.id)}
                                  title={`Remove Month ${empSeq} (${monthObj} ${sal.year})`}
                                >
                                  <span className="l1-btn-icon">🗑️</span>
                                  <span>Remove</span>
                                </button>
                              )}
                            </div>
                          </div>

                          <div className="l1-salary-six-col-grid">
                            {/* Row 1 (Cols 1-6) */}
                            <div className="l1-salary-col">
                              <label className="l1-salary-label">Month</label>
                              <select
                                className="l1-salary-control"
                                value={sal.month || 1}
                                onChange={(e) => handleUpdateSalaryField(sal.id, 'month', parseInt(e.target.value, 10))}
                                disabled={isAuditSubmitted}
                                aria-label={`Month ${empSeq} Month`}
                              >
                                <option value={1}>01 - January</option>
                                <option value={2}>02 - February</option>
                                <option value={3}>03 - March</option>
                                <option value={4}>04 - April</option>
                                <option value={5}>05 - May</option>
                                <option value={6}>06 - June</option>
                                <option value={7}>07 - July</option>
                                <option value={8}>08 - August</option>
                                <option value={9}>09 - September</option>
                                <option value={10}>10 - October</option>
                                <option value={11}>11 - November</option>
                                <option value={12}>12 - December</option>
                              </select>
                            </div>

                            <div className="l1-salary-col">
                              <label className="l1-salary-label">Year</label>
                              <input
                                type="number"
                                className="l1-salary-control"
                                min="2020"
                                max="2035"
                                value={sal.year || 2024}
                                onChange={(e) => handleUpdateSalaryField(sal.id, 'year', parseInt(e.target.value, 10))}
                                disabled={isAuditSubmitted}
                                aria-label={`Month ${empSeq} Year`}
                              />
                            </div>

                            <div className="l1-salary-col">
                              <label className="l1-salary-label">Work Days</label>
                              <input
                                type="number"
                                className="l1-salary-control"
                                placeholder="26"
                                min="0"
                                max="31"
                                value={sal.working_days ?? ''}
                                onChange={(e) => handleUpdateSalaryField(sal.id, 'working_days', e.target.value)}
                                disabled={isAuditSubmitted}
                                aria-label={`Month ${empSeq} Work Days`}
                              />
                            </div>

                            <div className="l1-salary-col">
                              <label className="l1-salary-label">Pay Days</label>
                              <input
                                type="number"
                                className="l1-salary-control"
                                placeholder="26"
                                min="0"
                                max="31"
                                value={sal.pay_days ?? ''}
                                onChange={(e) => handleUpdateSalaryField(sal.id, 'pay_days', e.target.value)}
                                disabled={isAuditSubmitted}
                                aria-label={`Month ${empSeq} Pay Days`}
                              />
                            </div>

                            <div className="l1-salary-col">
                              <label className="l1-salary-label">Leave Days</label>
                              <input
                                type="number"
                                className="l1-salary-control"
                                placeholder="0"
                                min="0"
                                max="31"
                                value={sal.leave_days ?? ''}
                                onChange={(e) => handleUpdateSalaryField(sal.id, 'leave_days', e.target.value)}
                                disabled={isAuditSubmitted}
                                aria-label={`Month ${empSeq} Leave Days`}
                              />
                            </div>

                            <div className="l1-salary-col">
                              <label className="l1-salary-label">Credit Date</label>
                              <input
                                type="date"
                                className="l1-salary-control"
                                value={sal.credit_date || ''}
                                onChange={(e) => handleUpdateSalaryField(sal.id, 'credit_date', e.target.value)}
                                disabled={isAuditSubmitted}
                                aria-label={`Month ${empSeq} Credit Date`}
                              />
                            </div>

                            {/* Row 2 (Cols 1-6) */}
                            <div className="l1-salary-col">
                              <label className="l1-salary-label">Gross Salary (₹)</label>
                              <input
                                type="number"
                                className="l1-salary-control"
                                placeholder="0"
                                min="0"
                                value={sal.gross_salary ?? ''}
                                onChange={(e) => handleUpdateSalaryField(sal.id, 'gross_salary', e.target.value)}
                                disabled={isAuditSubmitted}
                                aria-label={`Month ${empSeq} Gross Salary`}
                              />
                            </div>

                            <div className="l1-salary-col">
                              <label className="l1-salary-label">Deductions (₹)</label>
                              <input
                                type="number"
                                className="l1-salary-control"
                                placeholder="0"
                                min="0"
                                value={sal.deductions ?? ''}
                                onChange={(e) => handleUpdateSalaryField(sal.id, 'deductions', e.target.value)}
                                disabled={isAuditSubmitted}
                                aria-label={`Month ${empSeq} Deductions`}
                              />
                            </div>

                            <div className="l1-salary-col">
                              <label className="l1-salary-label">
                                Net Salary (₹) <span className="l1-calc-tag">Auto</span>
                              </label>
                              <input
                                type="number"
                                className="l1-salary-control calculated-field"
                                placeholder="0"
                                min="0"
                                value={sal.net_salary ?? ''}
                                onChange={(e) => handleUpdateSalaryField(sal.id, 'net_salary', e.target.value)}
                                disabled={isAuditSubmitted}
                                aria-label={`Month ${empSeq} Net Salary`}
                              />
                            </div>

                            <div className="l1-salary-col">
                              <label className="l1-salary-label">Credited (₹)</label>
                              <input
                                type="number"
                                className="l1-salary-control"
                                placeholder="0"
                                min="0"
                                value={sal.amount_credited ?? ''}
                                onChange={(e) => handleUpdateSalaryField(sal.id, 'amount_credited', e.target.value)}
                                disabled={isAuditSubmitted}
                                aria-label={`Month ${empSeq} Amount Credited`}
                              />
                            </div>

                            <div className="l1-salary-col l1-salary-col-span-2">
                              <label className="l1-salary-label">Bank Name</label>
                              <input
                                type="text"
                                className="l1-salary-control"
                                placeholder="e.g. State Bank of India, HDFC"
                                value={sal.bank_name || ''}
                                onChange={(e) => handleUpdateSalaryField(sal.id, 'bank_name', e.target.value)}
                                disabled={isAuditSubmitted}
                                aria-label={`Month ${empSeq} Bank Name`}
                              />
                            </div>
                          </div>
                        </div>
                      )
                    })}
                  </div>

                  {/* Salary Summary Bar */}
                  <div className="l1-salary-summary-bar">
                    <div className="l1-salary-stat">
                      <span className="label">Total Gross</span>
                      <span className="val highlight">₹{computedSalaryTotals.gross.toLocaleString('en-IN')}</span>
                    </div>
                    <div className="l1-salary-stat">
                      <span className="label">Total Deductions</span>
                      <span className="val">₹{computedSalaryTotals.deductions.toLocaleString('en-IN')}</span>
                    </div>
                    <div className="l1-salary-stat">
                      <span className="label">Total Net</span>
                      <span className="val">₹{computedSalaryTotals.net.toLocaleString('en-IN')}</span>
                    </div>
                    <div className="l1-salary-stat">
                      <span className="label">Total Credited</span>
                      <span className="val highlight">₹{computedSalaryTotals.credited.toLocaleString('en-IN')}</span>
                    </div>
                    <div className="l1-salary-stat">
                      <span className="label">Avg Gross / Mo</span>
                      <span className="val">₹{computedAvgGross.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</span>
                    </div>
                  </div>
                </div>



                {/* ================================================================
             SECTION 1: APPOINTMENT / OFFER LETTER
             ================================================================ */}
                <section className="l1-doc-workspace">
                  <div className="l1-workspace-header">
                    <div className="l1-workspace-title-box">
                      <span className="l1-step-badge">1</span>
                      <div>
                        <h3>Appointment / Offer Letter</h3>
                        <p>Attach the official signed appointment or offer letter. Exactly 1 active document per candidate.</p>
                      </div>
                    </div>
                    <span className={`l1-status-pill ${appointmentDoc ? 'success' : stagedAppointment?.file ? 'info' : 'danger'}`}>
                      {appointmentDoc ? '✓ Persisted in Drive' : stagedAppointment?.file ? '● Staged (Pending Submit)' : 'Required'}
                    </span>
                  </div>

                  {employerList.length > 1 ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      {employerList.map((emp, eIdx) => {
                        const empDoc = appointmentDocs.find((d) => d.employer_id === emp.id)
                        const stagedEmp = stagedAppointments[emp.id]
                        const isReplacing = replacingAppointments[emp.id]
                        const empErr = appointmentErrors[emp.id]

                        return (
                          <div key={emp.id || eIdx} style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: '8px', padding: '12px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <span className="l1-emp-badge" style={{ fontSize: '12px', padding: '3px 8px' }}>
                                  🏢 {emp.employer_name || `Employer ${eIdx + 1}`}
                                </span>
                                <span style={{ fontSize: '12px', color: '#64748B' }}>
                                  Appointment / Offer Letter
                                </span>
                              </div>
                              <span className={`l1-status-pill ${empDoc ? 'success' : stagedEmp?.file ? 'info' : 'danger'}`}>
                                {empDoc ? '✓ Persisted in Drive' : stagedEmp?.file ? '● Staged (Pending Submit)' : 'Required'}
                              </span>
                            </div>

                            {empDoc && (
                              <div className={`l1-doc-item-card persisted ${isReplacing ? 'replacing' : ''}`} style={{ marginBottom: '6px' }}>
                                <div className="l1-doc-item-row">
                                  <div className="l1-file-info">
                                    <div className="l1-file-icon-box">✓</div>
                                    <div className="l1-file-details">
                                      <span className="title">{empDoc.file_name}</span>
                                      <span className="meta">
                                        Size: {formatFileSize(empDoc.file_size_bytes)} · Persisted: {new Date(empDoc.created_at).toLocaleDateString()}
                                      </span>
                                    </div>
                                  </div>
                                  <div className="l1-btn-group">
                                    <button
                                      type="button"
                                      className="l1-btn-outline"
                                      onClick={() => handleDownloadFile(empDoc.id, empDoc.file_name)}
                                      disabled={downloadingDocId === empDoc.id}
                                    >
                                      {downloadingDocId === empDoc.id ? 'Downloading…' : 'Download / Preview'}
                                    </button>
                                    <button
                                      type="button"
                                      className="l1-btn-secondary"
                                      onClick={() => {
                                        if (isReplacing) {
                                          handleRemoveStagedAppointmentForEmployer(emp.id)
                                        } else {
                                          setReplacingAppointments((prev) => ({ ...prev, [emp.id]: true }))
                                        }
                                      }}
                                    >
                                      {isReplacing ? 'Cancel Replacement' : 'Replace Letter'}
                                    </button>
                                  </div>
                                </div>
                              </div>
                            )}

                            {(!empDoc || isReplacing) && (
                              <FileUploadControl
                                file={stagedEmp?.file}
                                fileName={stagedEmp?.fileName}
                                fileSize={stagedEmp?.fileSize}
                                error={empErr}
                                label={empDoc ? `Attach Replacement Offer Letter for ${emp.employer_name || 'Employer'}` : `Choose Offer Letter for ${emp.employer_name || 'Employer'}`}
                                helperText="PDF, PNG, JPG (up to 10MB) · Staged locally until Final Submit"
                                stagedLabel={empDoc ? 'Staged Replacement' : 'Staged (Pending Submit)'}
                                onSelect={(file) => handleSelectAppointmentForEmployer(emp.id, file, !!empDoc)}
                                onRemove={() => handleRemoveStagedAppointmentForEmployer(emp.id)}
                              />
                            )}
                          </div>
                        )
                      })}
                    </div>
                  ) : (
                    <>
                      {/* Display Persisted Appointment Letter if exists */}
                      {appointmentDoc && (
                        <div className={`l1-doc-item-card persisted ${replacingAppointment ? 'replacing' : ''}`}>
                          <div className="l1-doc-item-row">
                            <div className="l1-file-info">
                              <div className="l1-file-icon-box">✓</div>
                              <div className="l1-file-details">
                                <span className="title">{appointmentDoc.file_name}</span>
                                <span className="meta">
                                  Size: {formatFileSize(appointmentDoc.file_size_bytes)} · Persisted: {new Date(appointmentDoc.created_at).toLocaleDateString()}
                                </span>
                              </div>
                            </div>
                            <div className="l1-btn-group">
                              <button
                                type="button"
                                className="l1-btn-outline"
                                onClick={() => handleDownloadFile(appointmentDoc.id, appointmentDoc.file_name)}
                                disabled={downloadingDocId === appointmentDoc.id}
                              >
                                {downloadingDocId === appointmentDoc.id ? 'Downloading…' : 'Download / Preview'}
                              </button>
                              <button
                                type="button"
                                className="l1-btn-secondary"
                                onClick={() => {
                                  if (replacingAppointment) {
                                    handleRemoveStagedAppointment()
                                  } else {
                                    setReplacingAppointment(true)
                                  }
                                }}
                              >
                                {replacingAppointment ? 'Cancel Replacement' : 'Replace Letter'}
                              </button>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Staging Dropzone (New Upload or Replacement) */}
                      {(!appointmentDoc || replacingAppointment) && (
                        <div style={{ marginTop: '4px' }}>
                          <FileUploadControl
                            file={stagedAppointment?.file}
                            fileName={stagedAppointment?.fileName}
                            fileSize={stagedAppointment?.fileSize}
                            error={appointmentError}
                            label={appointmentDoc ? 'Attach Replacement Appointment Letter' : 'Choose Appointment / Offer Letter'}
                            helperText="PDF, PNG, JPG (up to 10MB) · Staged locally until Final Submit"
                            stagedLabel={appointmentDoc ? 'Staged Replacement' : 'Staged (Pending Submit)'}
                            onSelect={(file) => handleSelectAppointment(file, !!appointmentDoc)}
                            onRemove={handleRemoveStagedAppointment}
                          />
                        </div>
                      )}
                    </>
                  )}
                </section>

                {/* ================================================================
             SECTION 2: SALARY SLIPS
             ================================================================ */}
                <section className="l1-doc-workspace">
                  <div className="l1-workspace-header">
                    <div className="l1-workspace-title-box">
                      <span className="l1-step-badge">2</span>
                      <div>
                        <h3>Salary Slips</h3>
                        <p>At least 3 distinct reporting months required. You may add up to 12 months for extended placements.</p>
                      </div>
                    </div>
                    <div className="l1-doc-counter-badge" aria-label={`Salary slips: ${salarySlips.length} Persisted, ${stagedSalaryCount} Staged`}>
                      <div className="l1-counter-segment">
                        <span className={`l1-counter-dot ${salarySlips.length > 0 ? 'persisted' : 'empty'}`}>●</span>
                        <span className="l1-counter-count">{salarySlips.length}</span>
                        <span className="l1-counter-label">Persisted</span>
                      </div>
                      <div className="l1-counter-divider" aria-hidden="true" />
                      <div className="l1-counter-segment">
                        <span className={`l1-counter-dot ${stagedSalaryCount > 0 ? 'staged' : 'empty'}`}>●</span>
                        <span className="l1-counter-count">{stagedSalaryCount}</span>
                        <span className="l1-counter-label">Staged</span>
                      </div>
                    </div>
                  </div>

                  {/* Persisted Salary Slips */}
                  {salarySlips.length > 0 && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--mut)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                        Persisted Salary Slips ({salarySlips.length})
                      </span>
                      {salarySlips.map((doc) => {
                        const isReplacing = activeReplaceIds.has(doc.id)
                        const stagedRepl = stagedSalaryReplacements[doc.id]
                        const empObj = employerList.find((e) => e.id === doc.employer_id)

                        return (
                          <div key={doc.id} className={`l1-doc-item-card persisted ${isReplacing ? 'replacing' : ''}`}>
                            <div className="l1-doc-item-row">
                              <div className="l1-file-info">
                                <div className="l1-file-icon-box">₹</div>
                                <div className="l1-file-details">
                                  <span className="title">
                                    {MONTH_NAMES[doc.reporting_month - 1]} {doc.reporting_year} — {doc.file_name}
                                  </span>
                                  <span className="meta">
                                    {empObj && <span className="l1-emp-badge" style={{ marginRight: '6px' }}>🏢 {empObj.employer_name}</span>}
                                    Size: {formatFileSize(doc.file_size_bytes)} · Verified in Drive
                                  </span>
                                </div>
                              </div>
                              <div className="l1-btn-group">
                                <button
                                  type="button"
                                  className="l1-btn-outline"
                                  onClick={() => handleDownloadFile(doc.id, doc.file_name)}
                                  disabled={downloadingDocId === doc.id}
                                >
                                  {downloadingDocId === doc.id ? 'Downloading…' : 'Download / Preview'}
                                </button>
                                <button
                                  type="button"
                                  className="l1-btn-secondary"
                                  onClick={() => toggleReplaceMode(doc.id)}
                                >
                                  {isReplacing ? 'Cancel Replacement' : 'Replace'}
                                </button>
                              </div>
                            </div>

                            {/* Inline Staged Replacement */}
                            {isReplacing && (
                              <div style={{ marginTop: '6px', paddingTop: '10px', borderTop: '1px dashed var(--line)' }}>
                                <FileUploadControl
                                  file={stagedRepl?.file}
                                  fileName={stagedRepl?.fileName}
                                  fileSize={stagedRepl?.fileSize}
                                  error={stagedRepl?.error}
                                  label={`Attach Replacement for ${MONTH_NAMES[doc.reporting_month - 1]} ${doc.reporting_year}`}
                                  stagedLabel="Staged Replacement"
                                  onSelect={(file) => handleSelectReplacement(doc, file)}
                                  onRemove={() => toggleReplaceMode(doc.id)}
                                />
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )}

                  {/* Pending / Staged Monthly Slots */}
                  {(() => {
                    const visibleSalaryRows = salaryRows.filter((r, idx) => isSalarySlotVisible(r, idx))
                    return (
                      <div style={{ marginTop: '8px' }}>
                        <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--mut)', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block', marginBottom: '8px' }}>
                          Pending / Staged Monthly Slots ({visibleSalaryRows.length})
                        </span>

                        {visibleSalaryRows.length > 0 ? (
                          visibleSalaryRows.map((row) => {
                            const index = salaryRows.findIndex((r) => r.id === row.id)
                            const matchedSal = salaryDetailList[index >= 0 ? index : 0]
                            const sEmpId = matchedSal?.employer_id || employerList[0]?.id
                            const matchedEmp = employerList.find((e) => e.id === sEmpId) || employerList[0]
                            const empSeq = matchedSal ? getEmployerSalarySequence(matchedSal, salaryDetailList) : (index + 1)

                            return (
                              <div key={row.id} className={`l1-slot-row ${row.file ? 'staged' : ''}`}>
                                <div className="l1-slot-top">
                                  <span className="l1-slot-badge">
                                    <span className="l1-step-dot">{index + 1}</span>
                                    {matchedEmp && employerList.length > 1
                                      ? `${matchedEmp.employer_name} • Month ${empSeq}`
                                      : `Monthly Slot ${index + 1} (Month ${empSeq})`}
                                  </span>
                                  <button
                                    type="button"
                                    className="l1-btn-danger-ghost"
                                    onClick={() => handleRemoveRow('SALARY', row.id)}
                                  >
                                    {salaryRows.length > 3 ? '✕ Remove Slot' : row.file ? 'Clear File' : 'Reset'}
                                  </button>
                                </div>

                                <div className="l1-slot-controls">
                                  <div className="l1-period-picker l1-period-synchronized">
                                    <div className="l1-sync-period-pill" title="Synchronized with Section 3 Monthly Salary Disbursement Record">
                                      <span className="l1-sync-period-icon">📅</span>
                                      <span className="l1-sync-period-text">
                                        {MONTH_NAMES[(row.month || 1) - 1]} {row.year}
                                      </span>
                                    </div>
                                    {employerList.length > 1 && (
                                      <span className="l1-emp-badge" style={{ marginLeft: '6px' }}>
                                        🏢 {matchedEmp?.employer_name || 'Employer 1'}
                                      </span>
                                    )}
                                  </div>

                                  <FileUploadControl
                                    file={row.file}
                                    fileName={row.fileName}
                                    fileSize={row.fileSize}
                                    error={row.error}
                                    label={`Attach Salary Slip (${MONTH_NAMES[row.month - 1]} ${row.year})`}
                                    helperText="PDF, PNG, JPG (up to 10MB)"
                                    stagedLabel="Staged (Pending Submit)"
                                    disabled={isAuditSubmitted}
                                    isUnavailable={row.notAvailable}
                                    onMarkNotAvailable={() => handleMarkPayslipNotAvailable(index + 1, row.id)}
                                    onResetAvailability={() => handleResetPayslipAvailability(index + 1, row.id)}
                                    disableNotAvailable={!!salarySlips[index]}
                                    notAvailableTitle={
                                      salarySlips[index]
                                        ? 'Cannot mark as Not Available: a verified payslip is already uploaded in Drive'
                                        : 'Record that payslip is unavailable'
                                    }
                                    onSelect={(file) => updateRowField('SALARY', row.id, 'file', file)}
                                    onRemove={() => updateRowField('SALARY', row.id, 'file', null)}
                                  />
                                </div>
                              </div>
                            )
                          })
                        ) : (
                          <div style={{ padding: '12px 16px', background: '#F0FDF4', border: '1px solid #BBF7D0', borderRadius: '8px', color: '#166534', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                            <span>✓</span>
                            <span>All current reporting months have verified salary slips persisted in Drive. Use the action below to add the next month if required.</span>
                          </div>
                        )}

                        {salaryRows.length + salarySlips.length < 12 && (
                          <button
                            type="button"
                            className="l1-btn-add-slot"
                            onClick={handleAddSalaryRow}
                          >
                            + Add Salary Month (Synchronized)
                          </button>
                        )}
                      </div>
                    )
                  })()}
                </section>

                {/* ================================================================
             SECTION 3: BANK STATEMENTS
             ================================================================ */}
                <section className="l1-doc-workspace">
                  <div className="l1-workspace-header">
                    <div className="l1-workspace-title-box">
                      <span className="l1-step-badge">3</span>
                      <div>
                        <h3>Bank Statements</h3>
                        <p>At least 3 distinct reporting months required showing direct salary credits. Up to 12 months maximum.</p>
                      </div>
                    </div>
                    <div className="l1-doc-counter-badge" aria-label={`Bank statements: ${bankStatements.length} Persisted, ${stagedBankCount} Staged`}>
                      <div className="l1-counter-segment">
                        <span className={`l1-counter-dot ${bankStatements.length > 0 ? 'persisted' : 'empty'}`}>●</span>
                        <span className="l1-counter-count">{bankStatements.length}</span>
                        <span className="l1-counter-label">Persisted</span>
                      </div>
                      <div className="l1-counter-divider" aria-hidden="true" />
                      <div className="l1-counter-segment">
                        <span className={`l1-counter-dot ${stagedBankCount > 0 ? 'staged' : 'empty'}`}>●</span>
                        <span className="l1-counter-count">{stagedBankCount}</span>
                        <span className="l1-counter-label">Staged</span>
                      </div>
                    </div>
                  </div>

                  {/* Consolidated Multi-Month Bank Statement Box */}
                  <div className="l1-consolidated-box">
                    <div className="l1-consolidated-box-header">
                      <div className="l1-consolidated-title">
                        <span className="l1-consolidated-icon">📑</span>
                        <div>
                          <strong>Consolidated Multi-Month Bank Statement</strong>
                          <span className="l1-consolidated-subtitle">
                            Single PDF covering multiple consecutive months for an employer
                          </span>
                        </div>
                      </div>
                      <button
                        type="button"
                        className="l1-btn-consolidated-toggle"
                        onClick={() => setShowConsolidatedModal((v) => !v)}
                        aria-expanded={showConsolidatedModal}
                      >
                        {showConsolidatedModal ? '✕ Close Uploader' : '+ Upload Consolidated Statement (e.g. 3-Month PDF)'}
                      </button>
                    </div>

                    <p className="l1-consolidated-note">
                      Upload a single PDF covering multiple consecutive months for an employer. The file is stored once in Drive and satisfies coverage for all included months.
                    </p>

                    {showConsolidatedModal && (
                      <div className="l1-consolidated-modal-panel">
                        <div className="l1-consolidated-range-form">
                          {employerList.length > 1 && (
                            <div className="l1-consolidated-col-emp">
                              <label className="l1-salary-label">Employer</label>
                              <select
                                className="l1-salary-control"
                                value={consolidatedForm.employer_id || employerList[0]?.id}
                                onChange={(e) => setConsolidatedForm((prev) => ({ ...prev, employer_id: e.target.value }))}
                              >
                                {employerList.map((emp, eIdx) => (
                                  <option key={emp.id || eIdx} value={emp.id}>
                                    {emp.employer_name || `Employer ${eIdx + 1}`}
                                  </option>
                                ))}
                              </select>
                            </div>
                          )}

                          <div className="l1-consolidated-col-period">
                            <label className="l1-salary-label">Coverage Start</label>
                            <div className="l1-period-input-lockup">
                              <select
                                className="l1-salary-control"
                                value={consolidatedForm.start_month}
                                onChange={(e) => setConsolidatedForm((prev) => ({ ...prev, start_month: parseInt(e.target.value, 10) }))}
                              >
                                {MONTH_NAMES.map((m, idx) => (
                                  <option key={idx + 1} value={idx + 1}>{m}</option>
                                ))}
                              </select>
                              <input
                                type="number"
                                className="l1-salary-control l1-year-short-input"
                                value={consolidatedForm.start_year}
                                onChange={(e) => setConsolidatedForm((prev) => ({ ...prev, start_year: parseInt(e.target.value, 10) }))}
                              />
                            </div>
                          </div>

                          <div className="l1-consolidated-col-period">
                            <label className="l1-salary-label">Coverage End</label>
                            <div className="l1-period-input-lockup">
                              <select
                                className="l1-salary-control"
                                value={consolidatedForm.end_month}
                                onChange={(e) => setConsolidatedForm((prev) => ({ ...prev, end_month: parseInt(e.target.value, 10) }))}
                              >
                                {MONTH_NAMES.map((m, idx) => (
                                  <option key={idx + 1} value={idx + 1}>{m}</option>
                                ))}
                              </select>
                              <input
                                type="number"
                                className="l1-salary-control l1-year-short-input"
                                value={consolidatedForm.end_year}
                                onChange={(e) => setConsolidatedForm((prev) => ({ ...prev, end_year: parseInt(e.target.value, 10) }))}
                              />
                            </div>
                          </div>

                          <div className="l1-coverage-preview-lockup">
                            <span className="l1-coverage-badge">
                              📅 Declared Coverage: {MONTH_NAMES[consolidatedForm.start_month - 1]} {consolidatedForm.start_year} – {MONTH_NAMES[consolidatedForm.end_month - 1]} {consolidatedForm.end_year}
                            </span>
                          </div>
                        </div>

                        <FileUploadControl
                          file={consolidatedForm.file}
                          fileName={consolidatedForm.fileName}
                          fileSize={consolidatedForm.fileSize}
                          error={consolidatedForm.error}
                          label="Attach Consolidated Multi-Month Bank Statement PDF"
                          helperText="PDF up to 10MB · Staged locally until Final Submit"
                          stagedLabel="Staged Consolidated Statement"
                          onSelect={(file) => {
                            const err = validateFile(file)
                            setConsolidatedForm((prev) => ({
                              ...prev,
                              file,
                              fileName: file?.name || '',
                              fileSize: file?.size || 0,
                              error: err || '',
                            }))
                          }}
                          onRemove={() => {
                            setConsolidatedForm((prev) => ({
                              ...prev,
                              file: null,
                              fileName: '',
                              fileSize: 0,
                              error: '',
                            }))
                          }}
                        />

                        {consolidatedForm.file && !consolidatedForm.error && (
                          <div className="l1-consolidated-actions">
                            <button
                              type="button"
                              className="l1-btn-primary-action"
                              style={{ padding: '8px 20px', fontSize: '13px' }}
                              onClick={() => {
                                const empId = consolidatedForm.employer_id || employerList[0]?.id || 'emp_1'
                                const newDoc = {
                                  id: `consol_${Date.now()}`,
                                  file: consolidatedForm.file,
                                  fileName: consolidatedForm.fileName,
                                  fileSize: consolidatedForm.fileSize,
                                  employer_id: empId,
                                  coverage_start_month: consolidatedForm.start_month,
                                  coverage_start_year: consolidatedForm.start_year,
                                  coverage_end_month: consolidatedForm.end_month,
                                  coverage_end_year: consolidatedForm.end_year,
                                }
                                setStagedConsolidatedBankDocs((prev) => [...prev, newDoc])
                                setConsolidatedForm((prev) => ({
                                  ...prev,
                                  file: null,
                                  fileName: '',
                                  fileSize: 0,
                                  error: '',
                                }))
                                setShowConsolidatedModal(false)
                                setAuditToast({
                                  message: `✓ Staged consolidated bank statement covering ${MONTH_NAMES[consolidatedForm.start_month - 1]} ${consolidatedForm.start_year} – ${MONTH_NAMES[consolidatedForm.end_month - 1]} ${consolidatedForm.end_year}.`,
                                  type: 'success',
                                })
                              }}
                            >
                              ✓ Stage Consolidated Statement
                            </button>
                            <button
                              type="button"
                              className="l1-btn-secondary"
                              onClick={() => {
                                setConsolidatedForm((prev) => ({
                                  ...prev,
                                  file: null,
                                  fileName: '',
                                  fileSize: 0,
                                  error: '',
                                }))
                                setShowConsolidatedModal(false)
                              }}
                            >
                              Cancel
                            </button>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Display Persisted Consolidated Statements */}
                    {consolidatedBankDocs.length > 0 && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '12px' }}>
                        <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--mut)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                          Consolidated Statement{consolidatedBankDocs.length > 1 ? `s (${consolidatedBankDocs.length})` : ''}
                        </span>
                        {consolidatedBankDocs.map((doc) => {
                          const empObj = employerList.find((e) => e.id === doc.employer_id)
                          const startM = doc.coverage_start_month || doc.reporting_month
                          const startY = doc.coverage_start_year || doc.reporting_year
                          const endM = doc.coverage_end_month || doc.reporting_month
                          const endY = doc.coverage_end_year || doc.reporting_year
                          const statusObj = getBankDocumentStatus(doc)
                          const coveredMonths = getDocCoveredMonths(doc)
                          const isReplacing = activeReplaceIds.has(doc.id)
                          const stagedRepl = stagedBankReplacements[doc.id]

                          return (
                            <div key={doc.id} className={`l1-consolidated-card persisted ${isReplacing ? 'replacing' : ''}`}>
                              <div className="l1-consolidated-header">
                                <div className="l1-consolidated-file-info">
                                  <div className="l1-consolidated-icon">📑</div>
                                  <div className="l1-consolidated-meta">
                                    <span className="l1-consolidated-filename" title={doc.file_name}>{doc.file_name}</span>
                                    <div className="l1-consolidated-submeta">
                                      {empObj && (
                                        <span className="l1-emp-badge" title={empObj.employer_name}>
                                          🏢 {empObj.employer_name}
                                        </span>
                                      )}
                                      {doc.file_size_bytes && (
                                        <span>{formatFileSize(doc.file_size_bytes)}</span>
                                      )}
                                      <span>
                                        📅 Coverage: {MONTH_NAMES[(startM || 1) - 1]} {startY} – {MONTH_NAMES[(endM || 1) - 1]} {endY}
                                      </span>
                                      <span className={`l1-status-pill ${statusObj.className}`}>
                                        ✓ {statusObj.label}
                                      </span>
                                    </div>
                                  </div>
                                </div>

                                <div className="l1-btn-group">
                                  <button
                                    type="button"
                                    className="l1-btn-outline"
                                    onClick={() => handleDownloadFile(doc.id, doc.file_name)}
                                    disabled={downloadingDocId === doc.id}
                                    title="Download or view statement"
                                  >
                                    {downloadingDocId === doc.id ? 'Downloading…' : 'View / Preview'}
                                  </button>
                                  <button
                                    type="button"
                                    className="l1-btn-secondary"
                                    onClick={() => toggleReplaceMode(doc.id)}
                                  >
                                    {isReplacing ? 'Cancel' : 'Replace'}
                                  </button>
                                </div>
                              </div>

                              {coveredMonths.length > 0 && (
                                <div className="l1-month-tags-row">
                                  <span className="l1-month-tags-label">Covered months:</span>
                                  {coveredMonths.map((m) => (
                                    <span key={`${m.year}-${m.month}`} className="l1-month-tag persisted">
                                      ✓ {m.label}
                                    </span>
                                  ))}
                                </div>
                              )}

                              {/* Inline Staged Replacement for Consolidated Statement */}
                              {isReplacing && (
                                <div style={{ marginTop: '10px', paddingTop: '10px', borderTop: '1px dashed var(--line)' }}>
                                  <FileUploadControl
                                    file={stagedRepl?.file}
                                    fileName={stagedRepl?.fileName}
                                    fileSize={stagedRepl?.fileSize}
                                    error={stagedRepl?.error}
                                    label={`Attach Replacement Consolidated Statement (${MONTH_NAMES[(startM || 1) - 1]} ${startY} – ${MONTH_NAMES[(endM || 1) - 1]} ${endY})`}
                                    stagedLabel="Staged Replacement"
                                    helperText="Replacing preserves document ID, employer association, coverage metadata, and audit history."
                                    onSelect={(file) => handleSelectReplacement(doc, file)}
                                    onRemove={() => toggleReplaceMode(doc.id)}
                                  />
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    )}

                    {/* Display Locally Staged Consolidated Statements */}
                    {stagedConsolidatedBankDocs.length > 0 && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '12px' }}>
                        <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--mut)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                          Staged Consolidated Statements ({stagedConsolidatedBankDocs.length})
                        </span>
                        {stagedConsolidatedBankDocs.map((c) => {
                          const empObj = employerList.find((e) => e.id === c.employer_id)
                          const coveredMonths = getDocCoveredMonths(c)
                          return (
                            <div key={c.id} className="l1-consolidated-card staged">
                              <div className="l1-consolidated-header">
                                <div className="l1-consolidated-file-info">
                                  <div className="l1-consolidated-icon" style={{ color: '#0284c7', background: '#e0f2fe' }}>📑</div>
                                  <div className="l1-consolidated-meta">
                                    <span className="l1-consolidated-filename" title={c.fileName}>{c.fileName}</span>
                                    <div className="l1-consolidated-submeta">
                                      {empObj && (
                                        <span className="l1-emp-badge" title={empObj.employer_name}>
                                          🏢 {empObj.employer_name}
                                        </span>
                                      )}
                                      {c.fileSize && <span>{formatFileSize(c.fileSize)}</span>}
                                      <span>
                                        📅 Coverage: {MONTH_NAMES[(c.coverage_start_month || 1) - 1]} {c.coverage_start_year} – {MONTH_NAMES[(c.coverage_end_month || 1) - 1]} {c.coverage_end_year}
                                      </span>
                                      <span className="l1-status-pill info">
                                        ⏳ Staged (Pending Submit)
                                      </span>
                                    </div>
                                  </div>
                                </div>

                                <button
                                  type="button"
                                  className="l1-btn-danger-ghost"
                                  onClick={() => setStagedConsolidatedBankDocs((prev) => prev.filter((item) => item.id !== c.id))}
                                >
                                  ✕ Remove
                                </button>
                              </div>

                              {coveredMonths.length > 0 && (
                                <div className="l1-month-tags-row">
                                  <span className="l1-month-tags-label">Covered months:</span>
                                  {coveredMonths.map((m) => (
                                    <span key={`${m.year}-${m.month}`} className="l1-month-tag">
                                      {m.label}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>

                  {/* Persisted Monthly Bank Statements */}
                  {individualBankDocs.length > 0 && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '12px' }}>
                      <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--mut)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                        Persisted Monthly Bank Statements ({individualBankDocs.length})
                      </span>
                      {individualBankDocs.map((doc) => {
                        const isReplacing = activeReplaceIds.has(doc.id)
                        const stagedRepl = stagedBankReplacements[doc.id]
                        const empObj = employerList.find((e) => e.id === doc.employer_id)
                        const statusObj = getBankDocumentStatus(doc)

                        return (
                          <div key={doc.id} className={`l1-doc-item-card persisted ${isReplacing ? 'replacing' : ''}`}>
                            <div className="l1-doc-item-row">
                              <div className="l1-file-info">
                                <div className="l1-file-icon-box">▤</div>
                                <div className="l1-file-details">
                                  <span className="title">
                                    {MONTH_NAMES[(doc.reporting_month || 1) - 1]} {doc.reporting_year} — {doc.file_name}
                                  </span>
                                  <span className="meta">
                                    {empObj && <span className="l1-emp-badge" style={{ marginRight: '6px' }}>🏢 {empObj.employer_name}</span>}
                                    Size: {formatFileSize(doc.file_size_bytes)} · <span className={`l1-status-pill ${statusObj.className}`} style={{ fontSize: '11px', padding: '1px 6px' }}>✓ {statusObj.label}</span>
                                  </span>
                                </div>
                              </div>
                              <div className="l1-btn-group">
                                <button
                                  type="button"
                                  className="l1-btn-outline"
                                  onClick={() => handleDownloadFile(doc.id, doc.file_name)}
                                  disabled={downloadingDocId === doc.id}
                                >
                                  {downloadingDocId === doc.id ? 'Downloading…' : 'View / Preview'}
                                </button>
                                <button
                                  type="button"
                                  className="l1-btn-secondary"
                                  onClick={() => toggleReplaceMode(doc.id)}
                                >
                                  {isReplacing ? 'Cancel' : 'Replace'}
                                </button>
                              </div>
                            </div>

                            {/* Inline Staged Replacement */}
                            {isReplacing && (
                              <div style={{ marginTop: '6px', paddingTop: '10px', borderTop: '1px dashed var(--line)' }}>
                                <FileUploadControl
                                  file={stagedRepl?.file}
                                  fileName={stagedRepl?.fileName}
                                  fileSize={stagedRepl?.fileSize}
                                  error={stagedRepl?.error}
                                  label={`Attach Replacement for ${MONTH_NAMES[(doc.reporting_month || 1) - 1]} ${doc.reporting_year}`}
                                  stagedLabel="Staged Replacement"
                                  onSelect={(file) => handleSelectReplacement(doc, file)}
                                  onRemove={() => toggleReplaceMode(doc.id)}
                                />
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )}

                  {/* Pending / Staged Monthly Slots */}
                  {(() => {
                    const visibleBankRows = bankRows.filter((r, idx) => isBankSlotVisible(r, idx))
                    return (
                      <div style={{ marginTop: '8px' }}>
                        {visibleBankRows.length > 0 && (
                          <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--mut)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                            Pending / Staged Monthly Slots ({visibleBankRows.length})
                          </span>
                        )}

                        {visibleBankRows.length > 0 ? (
                          visibleBankRows.map((row) => {
                            const index = bankRows.findIndex((r) => r.id === row.id)
                            const matchedSal = salaryDetailList[index >= 0 ? index : 0]
                            const sEmpId = matchedSal?.employer_id || employerList[0]?.id
                            const matchedEmp = employerList.find((e) => e.id === sEmpId) || employerList[0]
                            const empSeq = matchedSal ? getEmployerSalarySequence(matchedSal, salaryDetailList) : (index + 1)

                            return (
                              <div key={row.id} className={`l1-slot-row ${row.file ? 'staged' : ''}`}>
                                <div className="l1-slot-top">
                                  <span className="l1-slot-badge">
                                    <span className="l1-step-dot">{index + 1}</span>
                                    {matchedEmp && employerList.length > 1
                                      ? `${matchedEmp.employer_name} • Month ${empSeq}`
                                      : `Monthly Slot ${index + 1} (Month ${empSeq})`}
                                  </span>
                                  <button
                                    type="button"
                                    className="l1-btn-danger-ghost"
                                    onClick={() => handleRemoveRow('BANK', row.id)}
                                  >
                                    {bankRows.length > 3 ? '✕ Remove Slot' : row.file ? 'Clear File' : 'Reset'}
                                  </button>
                                </div>

                                <div className="l1-slot-controls">
                                  <div className="l1-period-picker l1-period-synchronized">
                                    <div className="l1-sync-period-pill" title="Synchronized with Section 3 Monthly Salary Disbursement Record">
                                      <span className="l1-sync-period-icon">📅</span>
                                      <span className="l1-sync-period-text">
                                        {MONTH_NAMES[(row.month || 1) - 1]} {row.year}
                                      </span>
                                    </div>
                                    {employerList.length > 1 && (
                                      <span className="l1-emp-badge" style={{ marginLeft: '6px' }}>
                                        🏢 {matchedEmp?.employer_name || 'Employer 1'}
                                      </span>
                                    )}
                                  </div>

                                  <FileUploadControl
                                    file={row.file}
                                    fileName={row.fileName}
                                    fileSize={row.fileSize}
                                    error={row.error}
                                    label={`Attach Bank Statement (${MONTH_NAMES[(row.month || 1) - 1]} ${row.year})`}
                                    helperText="PDF, PNG, JPG (up to 10MB)"
                                    stagedLabel="Staged (Pending Submit)"
                                    onSelect={(file) => updateRowField('BANK', row.id, 'file', file)}
                                    onRemove={() => updateRowField('BANK', row.id, 'file', null)}
                                  />
                                </div>
                              </div>
                            )
                          })
                        ) : (
                          <div className="l1-all-covered-banner">
                            <span>✓</span>
                            <span>All current reporting months have bank statement coverage saved.</span>
                          </div>
                        )}

                        {bankRows.length + bankStatements.length < 12 && (
                          <button
                            type="button"
                            className="l1-btn-add-slot"
                            onClick={handleAddSalaryRow}
                          >
                            + Add Salary Month (Synchronized)
                          </button>
                        )}
                      </div>
                    )
                  })()}
                </section>

                {/* Section 4: Other Document (Optional) Workspace */}
                <section className="l1-doc-workspace">
                  <div className="l1-workspace-header">
                    <div className="l1-workspace-title">
                      <span className="l1-step-badge">4</span>
                      <div>
                        <h3>Other Document (Optional)</h3>
                        <p>Upload an optional supporting candidate document (e.g. joining report, id card, certification).</p>
                      </div>
                    </div>
                    <div className="l1-workspace-status">
                      {otherDoc ? (
                        <span className="l1-status-pill success">
                          ✓ Uploaded ({otherDoc.document_title || otherDoc.file_name})
                        </span>
                      ) : stagedOtherDoc?.file ? (
                        <span className="l1-status-pill info">
                          1 File Staged (Optional)
                        </span>
                      ) : (
                        <span className="l1-status-pill secondary">
                          Optional — Not Provided
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="l1-workspace-body">
                    {otherDoc && !replacingOtherDoc && (
                      <div className="l1-persisted-card" style={{ marginBottom: '14px' }}>
                        <div className="l1-persisted-meta">
                          <div className="l1-persisted-title">
                            <strong>{otherDoc.document_title || 'Other Supporting Document'}</strong>
                            <span className="l1-status-pill success" style={{ fontSize: '11px', padding: '2px 8px' }}>
                              ✓ Stored in Drive
                            </span>
                          </div>
                          <div className="l1-persisted-sub">
                            File: <code>{otherDoc.file_name}</code> ({formatFileSize(otherDoc.file_size_bytes)})
                            {otherDoc.created_at && (
                              <span> • Uploaded {new Date(otherDoc.created_at).toLocaleDateString('en-IN')}</span>
                            )}
                          </div>
                        </div>
                        <div className="l1-persisted-actions">
                          <button
                            type="button"
                            className="l1-btn-download"
                            onClick={() => handleDownloadFile(otherDoc.id, otherDoc.file_name)}
                            disabled={downloadingDocId === otherDoc.id}
                            title="Download file from Google Drive"
                          >
                            {downloadingDocId === otherDoc.id ? 'Downloading…' : '⬇ Download'}
                          </button>
                          <button
                            type="button"
                            className="l1-btn-replace"
                            onClick={() => {
                              setReplacingOtherDoc(true)
                              setOtherDocTitle(otherDoc.document_title || '')
                            }}
                            title="Replace existing file in Drive"
                          >
                            Replace File
                          </button>
                        </div>
                      </div>
                    )}

                    {(!otherDoc || replacingOtherDoc) && (
                      <div className="l1-staged-box">
                        {replacingOtherDoc && (
                          <div className="l1-replace-banner">
                            <span>Replacing <strong>{otherDoc?.document_title || otherDoc?.file_name}</strong></span>
                            <button
                              type="button"
                              className="l1-btn-cancel-replace"
                              onClick={() => {
                                setReplacingOtherDoc(false)
                                handleRemoveStagedOtherDoc()
                              }}
                            >
                              Cancel Replacement
                            </button>
                          </div>
                        )}

                        <div className="l1-field-group" style={{ marginBottom: '12px' }}>
                          <label style={{ fontSize: '12.5px', fontWeight: 600, color: 'var(--txt)', marginBottom: '4px', display: 'block' }}>
                            Document Title / Description (Optional)
                          </label>
                          <input
                            type="text"
                            className="l1-input"
                            placeholder="e.g. Joining Report, ID Card Copy, Transfer Certificate"
                            value={otherDocTitle}
                            onChange={(e) => setOtherDocTitle(e.target.value)}
                            style={{ maxWidth: '400px' }}
                          />
                        </div>

                        <FileUploadControl
                          file={stagedOtherDoc?.file}
                          fileName={stagedOtherDoc?.fileName}
                          fileSize={stagedOtherDoc?.fileSize}
                          error={otherDocError}
                          label={replacingOtherDoc ? 'Attach Replacement File' : 'Attach Other Supporting Document (Optional)'}
                          helperText="PDF, PNG, JPG (up to 10MB) — Optional"
                          stagedLabel="Staged (Pending Submit)"
                          onSelect={handleSelectOtherDoc}
                          onRemove={handleRemoveStagedOtherDoc}
                        />
                      </div>
                    )}
                  </div>
                </section>

                {/* Staging / Sync Dock */}
                <div className="l1-audit-card l1-staging-sync-dock" style={{
                  background: 'linear-gradient(135deg, rgba(2, 132, 199, 0.04) 0%, rgba(11, 79, 184, 0.06) 100%)',
                  border: '1.5px dashed rgba(11, 79, 184, 0.25)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: '16px',
                  padding: '18px 24px',
                }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span style={{ fontSize: '20px' }}>☁️</span>
                      <strong style={{ fontSize: '15px', color: 'var(--ink)' }}>
                        Document Staging &amp; Google Drive Synchronization
                      </strong>
                      <span className={`l1-status-pill ${totalStagedFiles > 0 ? 'info' : 'secondary'}`} style={{ fontSize: '12px', padding: '3px 10px' }}>
                        {totalStagedFiles} Staged {totalStagedFiles === 1 ? 'file' : 'files'}
                      </span>
                    </div>
                    <p style={{ margin: 0, fontSize: '13px', color: 'var(--mut)' }}>
                      {totalStagedFiles > 0
                        ? 'Files are safely staged in browser memory. You can upload and sync them to Google Drive now, or proceed to complete the audit statement below.'
                        : 'All document slots are synchronized. You can mark availability and compliance in Section 4 below.'}
                    </p>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    {totalStagedFiles > 0 ? (
                      <button
                        type="button"
                        className="l1-btn-primary-action"
                        onClick={handleOpenReviewModal}
                        disabled={submitting}
                        style={{ padding: '10px 20px', fontSize: '13.5px', display: 'flex', alignItems: 'center', gap: '8px' }}
                      >
                        <span>☁️</span> Review &amp; Upload to Drive ({totalStagedFiles}) →
                      </button>
                    ) : (
                      <span className="l1-status-pill success" style={{ padding: '6px 14px', fontSize: '12.5px' }}>
                        ✓ Staging Area Clean
                      </span>
                    )}
                  </div>
                </div>

                {/* Section 4: Document Evidence Audit */}
                <div className="l1-audit-card">
                  <div className="l1-audit-card-header">
                    <div className="l1-audit-card-title">
                      <span style={{ fontSize: '20px' }}>📑</span>
                      <div>
                        <h3>4. Document Evidence Audit</h3>
                        <p>Verification of candidate placement evidence (AL/OL, PS1-PS3, BS1-BS3)</p>
                      </div>
                    </div>
                    <span className="l1-status-pill info">Evidence Cross-Verification</span>
                  </div>

                  <div className="l1-table-responsive">
                    <table className="l1-audit-table">
                      <thead>
                        <tr>
                          <th style={{ width: '80px' }}>Code</th>
                          <th>Document Evidence</th>
                          <th style={{ width: '130px' }}>Availability</th>
                          <th style={{ width: '170px' }}>Drive Status</th>
                          <th>Coordinator Remarks</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(salaryDetailList && salaryDetailList.length > 0
                          ? [
                              (() => {
                                const apptEv = resolveEvidence('APPOINTMENT_LETTER', null, null, employerList[0]?.id)
                                return { code: 'AL / OL', label: 'Appointment / Offer Letter', key: 'appointment_letter', fileDoc: apptEv.doc, staged: apptEv.stagedFile, resolved: apptEv }
                              })(),
                              ...salaryDetailList.map((sal, idx) => {
                                const empSeq = getEmployerSalarySequence(sal, salaryDetailList)
                                const emp = employerList.find((e) => e.id === sal.employer_id) || employerList[0]
                                const mName = MONTH_NAMES[(sal.month || 1) - 1] || `Month ${sal.month}`
                                const empPrefix = employerList.length > 1 ? `${emp?.employer_name || 'Employer'} • ` : ''
                                const resSal = resolveEvidence('SALARY_SLIP', sal.month, sal.year, sal.employer_id)
                                return {
                                  code: `PS ${empSeq}`,
                                  label: `Salary Pay Slip — ${empPrefix}Month ${empSeq} (${mName} ${sal.year || ''})`,
                                  key: `salary_slip_${idx + 1}`,
                                  resolved: resSal,
                                  fileDoc: resSal.doc,
                                  staged: resSal.stagedFile,
                                }
                              }),
                              ...salaryDetailList.map((sal, idx) => {
                                const empSeq = getEmployerSalarySequence(sal, salaryDetailList)
                                const emp = employerList.find((e) => e.id === sal.employer_id) || employerList[0]
                                const mName = MONTH_NAMES[(sal.month || 1) - 1] || `Month ${sal.month}`
                                const empPrefix = employerList.length > 1 ? `${emp?.employer_name || 'Employer'} • ` : ''
                                const resBank = resolveEvidence('BANK_STATEMENT', sal.month, sal.year, sal.employer_id)
                                return {
                                  code: `BS ${empSeq}`,
                                  label: `Bank Statement / Passbook — ${empPrefix}Month ${empSeq} (${mName} ${sal.year || ''})`,
                                  key: `bank_statement_${idx + 1}`,
                                  resolved: resBank,
                                  fileDoc: resBank.doc,
                                  staged: resBank.stagedFile,
                                }
                              }),
                              { code: 'OD', label: `Other Document ${otherDocTitle || otherDoc?.document_title ? `— ${otherDocTitle || otherDoc?.document_title}` : '(Optional)'}`, key: 'other_document', fileDoc: otherDoc, staged: stagedOtherDoc?.file, isOptional: true },
                            ]
                          : [
                              (() => {
                                const apptEv = resolveEvidence('APPOINTMENT_LETTER', null, null, employerList[0]?.id)
                                return { code: 'AL / OL', label: 'Appointment / Offer Letter', key: 'appointment_letter', fileDoc: apptEv.doc, staged: apptEv.stagedFile, resolved: apptEv }
                              })(),
                              ...[1, 2, 3].map((mIdx) => {
                                const resSal = resolveEvidence('SALARY_SLIP', mIdx, currentYear, employerList[0]?.id)
                                return { code: `PS ${mIdx}`, label: `Salary Pay Slip — Month ${mIdx}`, key: `salary_slip_${mIdx}`, fileDoc: resSal.doc, staged: resSal.stagedFile, resolved: resSal }
                              }),
                              ...[1, 2, 3].map((mIdx) => {
                                const resBank = resolveEvidence('BANK_STATEMENT', mIdx, currentYear, employerList[0]?.id)
                                return { code: `BS ${mIdx}`, label: `Bank Statement / Passbook — Month ${mIdx}`, key: `bank_statement_${mIdx}`, fileDoc: resBank.doc, staged: resBank.stagedFile, resolved: resBank }
                              }),
                              { code: 'OD', label: `Other Document ${otherDocTitle || otherDoc?.document_title ? `— ${otherDocTitle || otherDoc?.document_title}` : '(Optional)'}`, key: 'other_document', fileDoc: otherDoc, staged: stagedOtherDoc?.file, isOptional: true },
                            ]
                        ).map((item) => {
                          const entry = (documentAudit && typeof documentAudit[item.key] === 'object' && documentAudit[item.key]) || { available: 'Pending', compliance: 'Under Verification', remarks: '' }
                          const isPersisted = item.resolved ? item.resolved.status === 'PERSISTED' : !!item.fileDoc
                          const isStaged = item.resolved ? item.resolved.status === 'STAGED' : !!item.staged
                          const effectiveAvailable = entry.explicitlySet
                            ? (entry.available || 'Pending')
                            : (isPersisted || isStaged ? 'Yes' : (entry.available || 'Pending'))
                          return (
                            <tr key={item.key}>
                              <td><strong>{item.code}</strong></td>
                              <td>
                                <span>{item.label}</span>
                              </td>
                              <td>
                                <select
                                  className="l1-audit-table-select"
                                  value={effectiveAvailable}
                                  onChange={(e) => handleUpdateDocAudit(item.key, 'available', e.target.value)}
                                  disabled={isAuditSubmitted}
                                  aria-label={`${item.label} Availability`}
                                >
                                  <option value="Yes">Yes</option>
                                  <option value="No">No</option>
                                  <option value="Pending">Pending</option>
                                </select>
                              </td>
                              <td>
                                {isPersisted ? (
                                  <span
                                    className="l1-status-pill success"
                                    style={{ fontSize: '11px', padding: '2px 8px' }}
                                  >
                                    Available
                                  </span>
                                ) : isStaged ? (
                                  <span
                                    className="l1-status-pill info"
                                    style={{ fontSize: '11px', padding: '2px 8px' }}
                                  >
                                    Pending
                                  </span>
                                ) : item.isOptional ? (
                                  <span
                                    className="l1-status-pill secondary"
                                    style={{ fontSize: '11px', padding: '2px 8px' }}
                                  >
                                    Optional / Omitted
                                  </span>
                                ) : (
                                  <span
                                    className="l1-status-pill danger"
                                    style={{ fontSize: '11px', padding: '2px 8px' }}
                                  >
                                    Missing
                                  </span>
                                )}
                              </td>
                              <td>
                                <input
                                  type="text"
                                  className="l1-audit-table-input"
                                  placeholder="Coordinator observations..."
                                  value={entry.remarks || ''}
                                  onChange={(e) => handleUpdateDocAudit(item.key, 'remarks', e.target.value)}
                                  disabled={isAuditSubmitted}
                                  aria-label={`${item.label} Coordinator Remarks`}
                                />
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Section 5: Authorizations & Sign-off Details */}
                {/* Section 5: Authorizations & Sign-off Details */}
                <div className="l1-audit-card">
                  <div className="l1-audit-card-header">
                    <div className="l1-audit-card-title">
                      <span style={{ fontSize: '20px' }}>✍️</span>
                      <div>
                        <h3>5. Authorizations &amp; Sign-off Endorsements</h3>
                        <p>Sign-offs and recommendation statements from Centre Head, COPS Team, and Business Leader</p>
                      </div>
                    </div>
                    <span className="l1-status-pill secondary">Read-Only (Corporate Endorsements)</span>
                  </div>

                  <div className="l1-signoff-grid">
                    {/* Centre Head */}
                    <div className="l1-signoff-card">
                      <div className="l1-signoff-header">
                        <span className="l1-signoff-role">Centre Head</span>
                        {isCHRejected ? (
                          <span className="l1-stage-badge rejected">Rejected</span>
                        ) : (
                          <label className="l1-checkbox-label">
                            <input
                              type="checkbox"
                              checked={!!signoffDetails.centre_head?.recommended}
                              disabled={true}
                              readOnly
                            />
                            Recommended
                          </label>
                        )}
                      </div>
                      <div className="l1-field-group">
                        <label>Officer Name</label>
                        <input
                          type="text"
                          placeholder="Name of Centre Head"
                          value={signoffDetails.centre_head?.name || ''}
                          disabled={true}
                          readOnly
                        />
                      </div>
                      <div className="l1-field-group">
                        <label>Verification Date</label>
                        <input
                          type="date"
                          value={signoffDetails.centre_head?.date || ''}
                          disabled={true}
                          readOnly
                        />
                      </div>
                      <div className="l1-field-group">
                        <label>Remarks</label>
                        <input
                          type="text"
                          placeholder="e.g. Dossier physically verified"
                          value={signoffDetails.centre_head?.remarks || ''}
                          disabled={true}
                          readOnly
                        />
                      </div>
                    </div>

                    {/* COPS Team */}
                    <div className="l1-signoff-card">
                      <div className="l1-signoff-header">
                        <span className="l1-signoff-role">COPS Audit Team</span>
                        {isCOPSRejected ? (
                          <span className="l1-stage-badge rejected">Rejected</span>
                        ) : (
                          <label className="l1-checkbox-label">
                            <input
                              type="checkbox"
                              checked={!!signoffDetails.cops_team?.verified}
                              disabled={true}
                              readOnly
                            />
                            Verified
                          </label>
                        )}
                      </div>
                      <div className="l1-field-group">
                        <label>Auditor Name</label>
                        <input
                          type="text"
                          placeholder="Name of COPS Auditor"
                          value={signoffDetails.cops_team?.name || ''}
                          disabled={true}
                          readOnly
                        />
                      </div>
                      <div className="l1-field-group">
                        <label>Audit Date</label>
                        <input
                          type="date"
                          value={signoffDetails.cops_team?.date || ''}
                          disabled={true}
                          readOnly
                        />
                      </div>
                      <div className="l1-field-group">
                        <label>Remarks</label>
                        <input
                          type="text"
                          placeholder="e.g. Salary credits verified"
                          value={signoffDetails.cops_team?.remarks || ''}
                          disabled={true}
                          readOnly
                        />
                      </div>
                    </div>

                    {/* Business Leader */}
                    <div className="l1-signoff-card">
                      <div className="l1-signoff-header">
                        <span className="l1-signoff-role">Business Leader</span>
                        {isBLRejected ? (
                          <span className="l1-stage-badge rejected">Rejected</span>
                        ) : (
                          <label className="l1-checkbox-label">
                            <input
                              type="checkbox"
                              checked={!!signoffDetails.business_leader?.approved}
                              disabled={true}
                              readOnly
                            />
                            Approved
                          </label>
                        )}
                      </div>
                      <div className="l1-field-group">
                        <label>Leader Name</label>
                        <input
                          type="text"
                          placeholder="Name of Business Leader"
                          value={signoffDetails.business_leader?.name || ''}
                          disabled={true}
                          readOnly
                        />
                      </div>
                      <div className="l1-field-group">
                        <label>Approval Date</label>
                        <input
                          type="date"
                          value={signoffDetails.business_leader?.date || ''}
                          disabled={true}
                          readOnly
                        />
                      </div>
                      <div className="l1-field-group">
                        <label>Remarks</label>
                        <input
                          type="text"
                          placeholder="e.g. Placement compliance approved"
                          value={signoffDetails.business_leader?.remarks || ''}
                          disabled={true}
                          readOnly
                        />
                      </div>
                    </div>
                  </div>
                </div>

              </>
            )}
          </div>
        </ErrorBoundary>
      )}

      {/* Placement Audit Statement Workflow Section (Normal Document Flow) */}
      {sel.cand && (
        <div className="l1-submit-dock l1-no-print">
          <div className="l1-dock-info">
            <span className="l1-dock-title">
              {isAuditSubmitted ? 'Placement Statement Finalized' : 'Placement Audit Statement Workflow'}
              <span className={`l1-status-pill ${isAuditSubmitted ? 'success' : 'warning'}`} style={{ fontSize: '12px', padding: '3px 10px' }}>
                {isAuditSubmitted ? 'SUBMITTED' : 'DRAFT'}
              </span>
            </span>
            <p className="l1-dock-desc">
              {isAuditSubmitted
                ? 'This audit statement has been submitted and locked for official record keeping.'
                : 'Save draft at any time. Submit statement once at least 1 employer and 3 monthly salary records are complete.'}
            </p>
          </div>
          <div className="l1-dock-actions" style={{ display: 'flex', gap: '10px' }}>
            {auditRecord && (
              <button
                type="button"
                className="l1-btn-secondary"
                onClick={handleOpenStatementModal}
                disabled={loadingStatement}
                style={{ padding: '10px 18px', fontSize: '13.5px', display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                <span>📄</span> Preview Statement
              </button>
            )}
            {!isAuditSubmitted && (
              <>
                <button
                  type="button"
                  className="l1-btn-secondary"
                  onClick={() => handleSaveDraft(false)}
                  disabled={auditSavingDraft || auditSubmitting || !candDetail || Boolean(auditLoadError)}
                  style={{ padding: '10px 18px', fontSize: '13.5px', display: 'flex', alignItems: 'center', gap: '6px' }}
                >
                  <span>💾</span> {auditSavingDraft ? 'Saving Draft...' : 'Save Draft'}
                </button>
                <button
                  type="button"
                  className="l1-btn-primary-action"
                  onClick={handleSubmitAuditStatement}
                  disabled={auditSubmitting || auditSavingDraft || !candDetail || candDetail?.has_active_hold || Boolean(auditLoadError)}
                  style={{ padding: '10px 20px', fontSize: '13.5px' }}
                >
                  {auditSubmitting ? 'Preparing Statement…' : 'Preview & Submit Statement →'}
                </button>
              </>
            )}
          </div>
        </div>
      )}
      {/* --------------------------------------------------------------------
         Empty Workspace Guidance (When No Candidate Selected)
         -------------------------------------------------------------------- */}
      {!sel.cand && !loadingDetail && (
        <section className="l1-empty-state">
          <div className="l1-empty-icon">📁</div>
          <h3>Select a Candidate to Begin Verification</h3>
          <p>
            Choose a State, Training Centre, Sanction Order, and Batch from the selection bar above to load a candidate and manage their placement documentation.
          </p>
        </section>
      )}

      {/* ====================================================================
         REVIEW & CONFIRMATION MODAL
         ==================================================================== */}
      {showReviewModal && candDetail && (
        <div className="l1-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="review-modal-title">
          <div className="l1-modal-card">
            <div className="l1-modal-header">
              <h3 id="review-modal-title">Review Placement Document Submission</h3>
              <button
                type="button"
                className="l1-modal-close-btn"
                onClick={() => !submitting && setShowReviewModal(false)}
                disabled={submitting}
                aria-label="Close dialog"
              >
                ✕
              </button>
            </div>

            <div className="l1-modal-body">
              {/* Candidate recap box */}
              <div style={{ background: 'var(--soft)', padding: '12px 16px', borderRadius: '12px', border: '1px solid rgba(11, 79, 184, 0.1)' }}>
                <strong style={{ fontSize: '15px', color: 'var(--ink)' }}>
                  {candDetail.first_name} {candDetail.last_name}
                </strong>
                <div style={{ fontSize: '13px', color: 'var(--mut)', marginTop: '2px' }}>
                  Candidate ID: <strong>{candDetail.candidate_id}</strong> · State: {sel.state} · Batch: {lists.batch.find((b) => b.kb_batch_id === sel.batch)?.batch_code || sel.batch}
                </div>
              </div>

              {/* 1. Appointment Letter Summary */}
              <div>
                <strong style={{ display: 'block', marginBottom: '6px', fontSize: '13.5px' }}>
                  1. Appointment / Offer Letter:
                </strong>
                {stagedAppointment?.file ? (
                  <div style={{ padding: '8px 12px', background: '#F0FDF4', border: '1px solid #BBF7D0', borderRadius: '8px', fontSize: '13px' }}>
                    {stagedAppointment.replaceId ? '🔄 Replacement File: ' : '📄 New Staged File: '}
                    <strong>{stagedAppointment.fileName}</strong> ({formatFileSize(stagedAppointment.fileSize)})
                  </div>
                ) : appointmentDoc ? (
                  <div style={{ padding: '8px 12px', background: '#F8FAFC', border: '1px solid var(--line)', borderRadius: '8px', fontSize: '13px' }}>
                    ✓ Retaining verified file: <strong>{appointmentDoc.file_name}</strong>
                  </div>
                ) : (
                  <div style={{ padding: '8px 12px', background: '#FEF2F2', border: '1px solid #FECACA', borderRadius: '8px', color: 'var(--danger)', fontSize: '13px' }}>
                    Missing appointment letter
                  </div>
                )}
              </div>

              {/* 2. Salary Slips Summary */}
              <div>
                <strong style={{ display: 'block', marginBottom: '6px', fontSize: '13.5px' }}>
                  2. Salary Slips to Submit:
                </strong>
                {salaryRows.filter((r) => r.file).length === 0 && Object.keys(stagedSalaryReplacements).length === 0 ? (
                  <div style={{ fontSize: '13px', color: 'var(--mut)' }}>
                    (No new salary slips staged; retaining {salarySlips.length} existing verified months)
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {salaryRows.filter((r) => r.file).map((r) => (
                      <div key={r.id} style={{ padding: '6px 12px', background: '#F0F9FF', border: '1px solid #BAE6FD', borderRadius: '8px', fontSize: '13px' }}>
                        📅 <strong>{MONTH_NAMES[r.month - 1]} {r.year}:</strong> {r.fileName} ({formatFileSize(r.fileSize)})
                      </div>
                    ))}
                    {Object.entries(stagedSalaryReplacements).filter(([, r]) => r.file).map(([id, r]) => (
                      <div key={id} style={{ padding: '6px 12px', background: '#FFFBEB', border: '1px solid #FDE68A', borderRadius: '8px', fontSize: '13px' }}>
                        🔄 Replacement for <strong>{MONTH_NAMES[r.month - 1]} {r.year}:</strong> {r.fileName} ({formatFileSize(r.fileSize)})
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* 3. Bank Statements Summary */}
              <div>
                <strong style={{ display: 'block', marginBottom: '6px', fontSize: '13.5px' }}>
                  3. Bank Statements to Submit:
                </strong>
                {bankRows.filter((r) => r.file).length === 0 && Object.keys(stagedBankReplacements).length === 0 && stagedConsolidatedBankDocs.filter((c) => c.file).length === 0 ? (
                  <div style={{ fontSize: '13px', color: 'var(--mut)' }}>
                    (No new bank statements staged; retaining {bankStatements.length} existing verified months)
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {stagedConsolidatedBankDocs.filter((c) => c.file).map((c) => (
                      <div key={c.id} style={{ padding: '6px 12px', background: '#F0FDF4', border: '1px solid #BBF7D0', borderRadius: '8px', fontSize: '13px' }}>
                        📑 <strong>Consolidated Bank Statement:</strong> {c.fileName} ({formatFileSize(c.fileSize)}) — Covers {MONTH_NAMES[c.coverage_start_month - 1]} {c.coverage_start_year} – {MONTH_NAMES[c.coverage_end_month - 1]} {c.coverage_end_year}
                      </div>
                    ))}
                    {bankRows.filter((r) => r.file).map((r) => (
                      <div key={r.id} style={{ padding: '6px 12px', background: '#F0F9FF', border: '1px solid #BAE6FD', borderRadius: '8px', fontSize: '13px' }}>
                        📅 <strong>{MONTH_NAMES[r.month - 1]} {r.year}:</strong> {r.fileName} ({formatFileSize(r.fileSize)})
                      </div>
                    ))}
                    {Object.entries(stagedBankReplacements).filter(([, r]) => r.file).map(([id, r]) => (
                      <div key={id} style={{ padding: '6px 12px', background: '#FFFBEB', border: '1px solid #FDE68A', borderRadius: '8px', fontSize: '13px' }}>
                        🔄 Replacement {r.is_consolidated ? 'Consolidated Statement' : `for ${MONTH_NAMES[(r.month || 1) - 1]} ${r.year}`}: <strong>{r.fileName}</strong> ({formatFileSize(r.fileSize)})
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* 4. Other Document Summary */}
              {stagedOtherDoc?.file && (
                <div>
                  <strong style={{ display: 'block', marginBottom: '6px', fontSize: '13.5px' }}>
                    4. Other Document:
                  </strong>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <div style={{ padding: '6px 12px', background: '#F0F9FF', border: '1px solid #BAE6FD', borderRadius: '8px', fontSize: '13px' }}>
                      {otherDocTitle || otherDoc?.document_title || 'Other Supporting Document'}: {stagedOtherDoc.fileName} ({formatFileSize(stagedOtherDoc.fileSize)})
                    </div>
                  </div>
                </div>
              )}

              <div className="l1-banner-warning" style={{ margin: '4px 0 0 0' }}>
                <span style={{ fontSize: '16px' }}>☁️</span>
                <div>
                  <strong>Drive Sync Confirmation:</strong> Upon confirmation, all staged files will be uploaded directly to the candidate's Google Drive folder hierarchy and permanently registered in CPASS.
                </div>
              </div>
            </div>

            <div className="l1-modal-footer">
              <button
                type="button"
                className="l1-btn-secondary"
                disabled={submitting}
                onClick={() => setShowReviewModal(false)}
              >
                Back to Editing
              </button>
              <button
                type="button"
                className="l1-btn-primary-action"
                disabled={submitting}
                onClick={handleFinalSubmit}
              >
                {submitting ? 'Uploading to Drive…' : 'Confirm & Upload to Drive'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ====================================================================
         SUCCESS MODAL & WORKFLOW RESET
         ==================================================================== */}
      {submitSuccessData && (
        <div className="l1-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="success-modal-title">
          <div className="l1-modal-card" style={{ maxWidth: '520px' }}>
            <div className="l1-modal-header" style={{ background: '#F0FDF4', borderBottom: '1px solid #BBF7D0' }}>
              <h3 id="success-modal-title" style={{ color: '#166534', display: 'flex', alignItems: 'center', gap: '8px' }}>
                ✓ Submission Complete!
              </h3>
            </div>

            <div className="l1-modal-body">
              <p style={{ margin: 0, fontSize: '14.5px', color: 'var(--ink)', lineHeight: 1.5 }}>
                All staged placement verification documents have been successfully uploaded to Google Drive and registered in the database for:
              </p>

              <div style={{ background: 'var(--soft)', padding: '12px 16px', borderRadius: '12px', border: '1px solid rgba(11, 79, 184, 0.1)' }}>
                <strong style={{ fontSize: '15px' }}>{submitSuccessData.candidateName}</strong>
                <div style={{ fontSize: '13px', color: 'var(--mut)', marginTop: '2px' }}>
                  Candidate ID: <strong>{submitSuccessData.candidateId}</strong>
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '13.5px' }}>
                <strong>Uploaded Package Breakdown:</strong>
                {submitSuccessData.appointmentUploaded && (
                  <div style={{ color: '#166534' }}>✓ Appointment / Offer Letter uploaded & verified</div>
                )}
                {submitSuccessData.salaryMonths.length > 0 && (
                  <div style={{ color: '#166534' }}>
                    ✓ Salary Slips ({submitSuccessData.salaryMonths.length} months): {submitSuccessData.salaryMonths.join(', ')}
                  </div>
                )}
                {submitSuccessData.consolidatedBankStatements?.map((cs, idx) => (
                  <div key={idx} style={{ color: '#166534' }}>
                    ✓ Consolidated Bank Statement ({cs.months.length} months): {cs.months.join(', ')}
                    {cs.employerName ? ` [${cs.employerName}]` : ''}
                  </div>
                ))}
                {submitSuccessData.individualBankMonths?.length > 0 && (
                  <div style={{ color: '#166534' }}>
                    ✓ Bank Statements ({submitSuccessData.individualBankMonths.length} months): {submitSuccessData.individualBankMonths.join(', ')}
                  </div>
                )}
                <div style={{ marginTop: '4px', fontWeight: 700, color: '#166534' }}>
                  Total files streamed and persisted: {submitSuccessData.totalSubmitted}
                </div>
              </div>
            </div>

            <div className="l1-modal-footer">
              <button
                type="button"
                className="l1-btn-primary-action"
                style={{ width: '100%', justifyContent: 'center' }}
                onClick={handleDismissUploadSuccess}
              >
                Continue Placement Audit
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ====================================================================
         FINAL PLACEMENT STATEMENT SUBMISSION CONFIRMATION MODAL
         ==================================================================== */}
      {finalSubmitSuccessData && (
        <div className="l1-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="final-submit-title">
          <div className="l1-modal-card" style={{ maxWidth: '520px' }}>
            <div className="l1-modal-header" style={{ background: '#F0FDF4', borderBottom: '1px solid #BBF7D0' }}>
              <h3 id="final-submit-title" style={{ color: '#166534', display: 'flex', alignItems: 'center', gap: '8px' }}>
                ✓ Placement Statement Finalized &amp; Submitted!
              </h3>
            </div>

            <div className="l1-modal-body">
              <p style={{ margin: 0, fontSize: '14.5px', color: 'var(--ink)', lineHeight: 1.5 }}>
                The official Placement Audit Statement for candidate <strong>{finalSubmitSuccessData.candidateName}</strong> (ID: <strong>{finalSubmitSuccessData.candidateId}</strong>) has been finalized and submitted for L2 verification.
              </p>

              <div style={{ background: 'var(--soft)', padding: '12px 16px', borderRadius: '12px', border: '1px solid rgba(11, 79, 184, 0.1)', marginTop: '8px' }}>
                <div style={{ fontSize: '13px', color: 'var(--mut)' }}>
                  Batch: <strong>{finalSubmitSuccessData.batch}</strong>
                </div>
                <div style={{ fontSize: '12.5px', color: 'var(--mut)', marginTop: '4px' }}>
                  Submitted on: <strong>{new Date(finalSubmitSuccessData.submittedAt).toLocaleString('en-IN')}</strong>
                </div>
              </div>
            </div>

            <div className="l1-modal-footer">
              <button
                type="button"
                className="l1-btn-primary-action"
                style={{ width: '100%', justifyContent: 'center' }}
                onClick={handleFinalSubmissionCompleteReset}
              >
                Done / Verify Next Candidate
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ====================================================================
         C-PASS CANDIDATE PLACEMENT AUDIT & SIGN-OFF STATEMENT MODAL
         ==================================================================== */}
      {statementModalOpen && statementData && (
        <PlacementAuditStatement
          statementData={statementData}
          showModalWrapper={true}
          onClose={() => setStatementModalOpen(false)}
          extraFooterActions={
            !isAuditSubmitted ? (
              <>
                <button
                  type="button"
                  className="l1-btn-secondary"
                  onClick={() => setStatementModalOpen(false)}
                  style={{ padding: '8px 16px', fontSize: '13px' }}
                >
                  ← Back to Edit
                </button>
                <button
                  type="button"
                  className="l1-btn-primary-action"
                  disabled={auditSubmitting}
                  onClick={handleConfirmFinalSubmit}
                  style={{ padding: '8px 18px', fontSize: '13px' }}
                >
                  {auditSubmitting ? 'Finalizing Submission…' : 'Confirm & Final Submit Statement →'}
                </button>
              </>
            ) : null
          }
        />
      )}

      {/* Floating Audit Toast Notification */}
      {auditToast && (
        <div className={`l1-audit-toast ${auditToast.type || ''}`} role="status">
          <span>{auditToast.type === 'success' ? '✓' : auditToast.type === 'error' ? '⚠️' : 'ℹ️'}</span>
          <span>{auditToast.message}</span>
        </div>
      )}
    </div>
  )
}
