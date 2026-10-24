import { useEffect, useRef, useState, useCallback } from 'react'
import { api, downloadDocument } from '../lib/api'
import synchroLogo from '../../assets/SynchroServeLogo.png'
import './L1Home.css'
import ErrorBoundary from '../components/ErrorBoundary'
import PlacementAuditStatement from '../components/PlacementAuditStatement'

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

const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024 // 10 MB
const ALLOWED_EXTENSIONS = ['.pdf', '.png', '.jpg', '.jpeg']

function formatFileSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
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
function createDefaultEmployer(detail) {
  return {
    id: `emp_${Date.now()}_1`,
    employer_name: detail?.employer_name || '',
    months_worked: '',
    appointment_date: detail?.appointed_date || '',
    designation: detail?.designation || '',
    place_of_work: detail?.work_location || '',
    monthly_ctc: detail?.monthly_ctc || '',
    minimum_wages: '',
  }
}

function createDefaultSalaryList(year) {
  const y = year || new Date().getFullYear()
  return [
    {
      id: `sal_${Date.now()}_1`,
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

  const out = { ...defaults, ...data }
  const docKeys = [
    'appointment_letter',
    'salary_slip_1',
    'salary_slip_2',
    'salary_slip_3',
    'bank_statement_1',
    'bank_statement_2',
    'bank_statement_3',
    'other_document',
  ]
  for (const k of docKeys) {
    const raw = data[k]
    if (raw && typeof raw === 'object') {
      out[k] = {
        available: raw.available || 'Pending',
        compliance: raw.compliance || 'Under Verification',
        remarks: raw.remarks || '',
        title: raw.title || '',
      }
    } else {
      out[k] = { ...defaults[k] }
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
                id: `emp_${idx + 1}`,
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
            setEmployerList([createDefaultEmployer(detail)])
          }

          if (Array.isArray(a.salary_details) && a.salary_details.length > 0) {
            const loadedSalaryList = a.salary_details.map((s, idx) => ({
              id: `sal_${idx + 1}`,
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
  function handleAddSalaryRow() {
    if (auditRecord?.audit_status === 'SUBMITTED') return
    if (salaryDetailList.length >= 12) {
      setAuditToast({ message: 'Maximum 12 monthly salary entries allowed.', type: 'info' })
      return
    }
    // Find next unused month in currentYear if possible to avoid duplicate month-year
    const usedMonths = new Set(salaryDetailList.filter((s) => s.year === currentYear).map((s) => s.month))
    let nextMonth = 1
    for (let m = 1; m <= 12; m++) {
      if (!usedMonths.has(m)) {
        nextMonth = m
        break
      }
    }
    if (usedMonths.size >= 12) {
      nextMonth = ((salaryDetailList.length) % 12) + 1
    }

    const newId = `sal_${Date.now()}_${Math.random().toString(36).substr(2, 4)}`
    const newRow = {
      id: newId,
      month: nextMonth,
      year: currentYear,
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
        year: currentYear,
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
        year: currentYear,
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
        },
      }
    })
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
            employer_name: e.employer_name.trim(),
            months_worked: e.months_worked !== '' && e.months_worked !== null ? parseFloat(e.months_worked) : null,
            appointment_date: e.appointment_date || null,
            designation: e.designation || null,
            place_of_work: e.place_of_work || null,
            monthly_ctc: e.monthly_ctc !== '' && e.monthly_ctc !== null ? parseFloat(e.monthly_ctc) : null,
            minimum_wages: e.minimum_wages !== '' && e.minimum_wages !== null ? parseFloat(e.minimum_wages) : null,
          })),
        salary_details: salaryDetailList.map((s) => ({
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
        document_audit: documentAudit,
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

    const periods = new Set(salaryDetailList.map((s) => `${s.month}-${s.year}`))
    if (periods.size < salaryDetailList.length) {
      setError('Duplicate reporting month and year found in salary details. Each reporting month must be unique.')
      setAuditToast({ message: 'Duplicate reporting months found.', type: 'error' })
      return
    }

    // Validate that documents explicitly marked "Yes" have physical evidence in Drive or browser staging
    const docFileMap = {
      appointment_letter: !!appointmentDoc || !!stagedAppointment?.file,
      salary_slip_1: salarySlips.length > 0 || !!salaryRows[0]?.file,
      salary_slip_2: salarySlips.length > 1 || !!salaryRows[1]?.file,
      salary_slip_3: salarySlips.length > 2 || !!salaryRows[2]?.file,
      bank_statement_1: bankStatements.length > 0 || !!bankRows[0]?.file,
      bank_statement_2: bankStatements.length > 1 || !!bankRows[1]?.file,
      bank_statement_3: bankStatements.length > 2 || !!bankRows[2]?.file,
      other_document: !!otherDoc || !!stagedOtherDoc?.file,
    }

    const checkLabels = [
      ['appointment_letter', 'Appointment / Offer Letter'],
      ['salary_slip_1', 'Salary Slip Month 1'],
      ['salary_slip_2', 'Salary Slip Month 2'],
      ['salary_slip_3', 'Salary Slip Month 3'],
      ['bank_statement_1', 'Bank Statement Month 1'],
      ['bank_statement_2', 'Bank Statement Month 2'],
      ['bank_statement_3', 'Bank Statement Month 3'],
    ]

    for (const [key, label] of checkLabels) {
      const row = documentAudit?.[key]
      if (row?.available === 'Yes' && !docFileMap[key]) {
        setError(`"${label}" is marked as "Yes" (Available), but no physical file has been uploaded to Drive or staged. Please attach the file or mark availability as "Pending" or "No".`)
        setAuditToast({ message: `Physical file missing for ${label}`, type: 'error' })
        return
      }
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
          employer_name: e.employer_name.trim(),
          months_worked: e.months_worked !== '' && e.months_worked !== null ? parseFloat(e.months_worked) : null,
          appointment_date: e.appointment_date || null,
          designation: e.designation || null,
          place_of_work: e.place_of_work || null,
          monthly_ctc: e.monthly_ctc !== '' && e.monthly_ctc !== null ? parseFloat(e.monthly_ctc) : null,
          minimum_wages: e.minimum_wages !== '' && e.minimum_wages !== null ? parseFloat(e.minimum_wages) : null,
        })),
        salary_details: salaryDetailList.map((s) => ({
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
        document_audit: documentAudit,
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


  const name = (c) => {
    if (!c) return ''
    return `${c.first_name ?? ''} ${c.last_name ?? ''}`.trim()
  }
  const safeDocs = Array.isArray(documents) ? documents : []
  const appointmentDoc = safeDocs.find((d) => d.document_type === 'APPOINTMENT_LETTER')
  const salarySlips = safeDocs.filter((d) => d.document_type === 'SALARY_SLIP')
  const bankStatements = safeDocs.filter((d) => d.document_type === 'BANK_STATEMENT')
  const otherDoc = safeDocs.find((d) => d.document_type === 'OTHER_DOCUMENT')

  // --- Staging Handlers for Appointment Letter ---
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
    const payload = {
      file,
      fileName: file.name,
      fileSize: file.size,
      month: doc.reporting_month,
      year: doc.reporting_year,
      replaceId: doc.id,
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
        return `Bank statement error for ${MONTH_NAMES[item.month - 1]} ${item.year}: ${item.error}`
      }
      const key = `${item.year}-${item.month}`
      if (stagedBankMonths.has(key)) {
        return `Duplicate reporting period selected for Bank Statements: ${MONTH_NAMES[item.month - 1]} ${item.year}.`
      }
      stagedBankMonths.add(key)
    }

    const totalFilesToSubmit =
      (stagedAppointment?.file ? 1 : 0) +
      stagedSalaryEntries.length +
      stagedBankEntries.length +
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

      // Appointment Letter
      if (stagedAppointment?.file) {
        formData.append('appointment_letter', stagedAppointment.file)
        if (stagedAppointment.replaceId) {
          formData.append('appointment_replace_id', stagedAppointment.replaceId)
        }
      }

      // Salary Slips
      const salaryMeta = []
      for (const row of salaryRows) {
        if (row.file) {
          formData.append('salary_slips', row.file)
          salaryMeta.push({
            month: Number(row.month),
            year: Number(row.year),
            replace_id: null,
          })
        }
      }
      for (const [replaceId, repl] of Object.entries(stagedSalaryReplacements)) {
        if (repl.file) {
          formData.append('salary_slips', repl.file)
          salaryMeta.push({
            month: Number(repl.month),
            year: Number(repl.year),
            replace_id: replaceId,
          })
        }
      }
      formData.append('salary_slips_meta', JSON.stringify(salaryMeta))

      // Bank Statements
      const bankMeta = []
      for (const row of bankRows) {
        if (row.file) {
          formData.append('bank_statements', row.file)
          bankMeta.push({
            month: Number(row.month),
            year: Number(row.year),
            replace_id: null,
          })
        }
      }
      for (const [replaceId, repl] of Object.entries(stagedBankReplacements)) {
        if (repl.file) {
          formData.append('bank_statements', repl.file)
          bankMeta.push({
            month: Number(repl.month),
            year: Number(repl.year),
            replace_id: replaceId,
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
      setSubmitSuccessData({
        candidateId: sel.cand,
        candidateName: `${candDetail.first_name} ${candDetail.last_name}`,
        appointmentUploaded: !!stagedAppointment?.file,
        salaryMonths: salaryMeta.map((m) => `${MONTH_NAMES[m.month - 1]} ${m.year}`),
        bankMonths: bankMeta.map((m) => `${MONTH_NAMES[m.month - 1]} ${m.year}`),
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
  const stagedBankCount = bankRows.filter((r) => r.file).length + Object.values(stagedBankReplacements).filter((r) => r.file).length
  const otherDocStagedCount = stagedOtherDoc?.file ? 1 : 0
  const totalStagedFiles = (stagedAppointment?.file ? 1 : 0) + stagedSalaryCount + stagedBankCount + otherDocStagedCount

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

      {/* --------------------------------------------------------------------
         2. Hero / Portal Banner matching Login Aesthetics
         -------------------------------------------------------------------- */}
      <section className="l1-hero-banner">
        <div className="l1-hero-content">
          <span className="l1-portal-badge">
            ✦ L1 Placement Verification Portal
          </span>
          <h1>Verify &amp; Validate, Sync &amp; Confirm.</h1>
          <p>
            Audit and stage required placement verification documents—including offer letters, salary slips, and bank statements—before syncing directly to Google Drive.
          </p>
        </div>
        <div className="l1-hero-badges">
          <div className="l1-stat-pill">
            <span className="label">Storage Mode</span>
            <span className="value">Google Drive</span>
          </div>
          <div className="l1-stat-pill">
            <span className="label">Verification</span>
            <span className="value">L1 Placement</span>
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
                        <th>Status</th>
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
                            <span
                              className={`l1-status-pill ${
                                cand.cpass_status === 'APPROVED'
                                  ? 'approved success'
                                  : cand.cpass_status === 'REJECTED'
                                  ? 'rejected danger'
                                  : cand.cpass_status === 'IN_PROGRESS'
                                  ? 'in-progress info'
                                  : cand.is_uploaded
                                  ? 'uploaded info'
                                  : 'pending warning'
                              }`}
                              style={{ fontSize: '11px', padding: '2px 8px' }}
                            >
                              {cand.cpass_status === 'APPROVED'
                                ? 'APPROVED'
                                : cand.cpass_status === 'REJECTED'
                                ? 'REJECTED'
                                : cand.cpass_status === 'IN_PROGRESS'
                                ? 'IN PROGRESS'
                                : cand.is_uploaded
                                ? 'UPLOADED'
                                : 'PENDING'}
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
                    <span className={`l1-audit-status-badge ${isAuditSubmitted ? 'submitted' : 'draft'}`}>
                      <span style={{ fontSize: '10px' }}>●</span>
                      {isAuditSubmitted ? 'SUBMITTED & FINALIZED' : 'AUDIT DRAFT IN PROGRESS'}
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
                    {/* Status Notice if Submitted */}
                    {isAuditSubmitted && (
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
                      className="l1-btn-add-slot"
                      onClick={handleAddEmployerRow}
                      style={{ width: 'auto', padding: '6px 14px', fontSize: '13px' }}
                    >
                      + Add Another Employer
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
                        {!isAuditSubmitted && employerList.length > 1 && <th style={{ width: '60px' }}>Action</th>}
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
                                onClick={() => handleRemoveEmployerRow(emp.id)}
                                title="Remove Employer"
                                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#DC2626', fontSize: '15px' }}
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
                      className="l1-btn-add-slot"
                      onClick={handleAddSalaryRow}
                      style={{ width: 'auto', padding: '6px 14px', fontSize: '13px' }}
                    >
                      + Add Salary Month
                    </button>
                  )}
                </div>

                <div className="l1-salary-records-container">
                  {salaryDetailList.map((sal, idx) => {
                    const monthObj = MONTH_NAMES[(sal.month || 1) - 1] || `Month ${sal.month}`
                    return (
                      <div key={sal.id || idx} className="l1-salary-month-card">
                        <div className="l1-salary-month-header">
                          <div className="l1-salary-month-badge-wrap">
                            <span className="l1-salary-month-badge">Month {idx + 1}</span>
                            <span className="l1-salary-month-period-title">
                              {monthObj} {sal.year || 2024}
                            </span>
                            <span className="l1-salary-month-sync-hint">
                              🔗 Synchronized to Salary Slips & Bank Statements
                            </span>
                          </div>
                          {!isAuditSubmitted && salaryDetailList.length > 3 && (
                            <button
                              type="button"
                              className="l1-btn-remove-month"
                              onClick={() => handleRemoveSalaryRow(sal.id)}
                              title="Remove Month"
                            >
                              <span>🗑️</span> Remove Month
                            </button>
                          )}
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
                              aria-label={`Month ${idx + 1} Month`}
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
                              aria-label={`Month ${idx + 1} Year`}
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
                              aria-label={`Month ${idx + 1} Work Days`}
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
                              aria-label={`Month ${idx + 1} Pay Days`}
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
                              aria-label={`Month ${idx + 1} Leave Days`}
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
                              aria-label={`Month ${idx + 1} Credit Date`}
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
                              aria-label={`Month ${idx + 1} Gross Salary`}
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
                              aria-label={`Month ${idx + 1} Deductions`}
                            />
                          </div>

                          <div className="l1-salary-col">
                            <label className="l1-salary-label">Net Salary (₹)</label>
                            <input
                              type="number"
                              className="l1-salary-control calculated-field"
                              placeholder="0"
                              min="0"
                              value={sal.net_salary ?? ''}
                              onChange={(e) => handleUpdateSalaryField(sal.id, 'net_salary', e.target.value)}
                              disabled={isAuditSubmitted}
                              aria-label={`Month ${idx + 1} Net Salary`}
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
                              aria-label={`Month ${idx + 1} Amount Credited`}
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
                              aria-label={`Month ${idx + 1} Bank Name`}
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
            <div style={{ marginTop: '8px' }}>
              <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--mut)', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block', marginBottom: '8px' }}>
                Pending / Staged Monthly Slots ({salaryRows.length})
              </span>

              {salaryRows.map((row, index) => (
                <div key={row.id} className={`l1-slot-row ${row.file ? 'staged' : ''}`}>
                  <div className="l1-slot-top">
                    <span className="l1-slot-badge">
                      <span className="l1-step-dot">{index + 1}</span>
                      Monthly Slot {index + 1}
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
              ))}

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

            {/* Persisted Bank Statements */}
            {bankStatements.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--mut)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Persisted Bank Statements ({bankStatements.length})
                </span>
                {bankStatements.map((doc) => {
                  const isReplacing = activeReplaceIds.has(doc.id)
                  const stagedRepl = stagedBankReplacements[doc.id]

                  return (
                    <div key={doc.id} className={`l1-doc-item-card persisted ${isReplacing ? 'replacing' : ''}`}>
                      <div className="l1-doc-item-row">
                        <div className="l1-file-info">
                          <div className="l1-file-icon-box">▤</div>
                          <div className="l1-file-details">
                            <span className="title">
                              {MONTH_NAMES[doc.reporting_month - 1]} {doc.reporting_year} — {doc.file_name}
                            </span>
                            <span className="meta">
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
            <div style={{ marginTop: '8px' }}>
              <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--mut)', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block', marginBottom: '8px' }}>
                Pending / Staged Monthly Slots ({bankRows.length})
              </span>

              {bankRows.map((row, index) => (
                <div key={row.id} className={`l1-slot-row ${row.file ? 'staged' : ''}`}>
                  <div className="l1-slot-top">
                    <span className="l1-slot-badge">
                      <span className="l1-step-dot">{index + 1}</span>
                      Monthly Slot {index + 1}
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
                    </div>

                    <FileUploadControl
                      file={row.file}
                      fileName={row.fileName}
                      fileSize={row.fileSize}
                      error={row.error}
                      label={`Attach Bank Statement (${MONTH_NAMES[row.month - 1]} ${row.year})`}
                      helperText="PDF, PNG, JPG (up to 10MB)"
                      stagedLabel="Staged (Pending Submit)"
                      onSelect={(file) => updateRowField('BANK', row.id, 'file', file)}
                      onRemove={() => updateRowField('BANK', row.id, 'file', null)}
                    />
                  </div>
                </div>
              ))}

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
                      {[
                        { code: 'AL / OL', label: 'Appointment / Offer Letter', key: 'appointment_letter', fileDoc: appointmentDoc, staged: stagedAppointment?.file },
                        { code: 'PS 1', label: 'Salary Pay Slip — Month 1', key: 'salary_slip_1', fileDoc: salarySlips[0], staged: salaryRows[0]?.file },
                        { code: 'PS 2', label: 'Salary Pay Slip — Month 2', key: 'salary_slip_2', fileDoc: salarySlips[1], staged: salaryRows[1]?.file },
                        { code: 'PS 3', label: 'Salary Pay Slip — Month 3', key: 'salary_slip_3', fileDoc: salarySlips[2], staged: salaryRows[2]?.file },
                        { code: 'BS 1', label: 'Bank Statement / Passbook — Month 1', key: 'bank_statement_1', fileDoc: bankStatements[0], staged: bankRows[0]?.file },
                        { code: 'BS 2', label: 'Bank Statement / Passbook — Month 2', key: 'bank_statement_2', fileDoc: bankStatements[1], staged: bankRows[1]?.file },
                        { code: 'BS 3', label: 'Bank Statement / Passbook — Month 3', key: 'bank_statement_3', fileDoc: bankStatements[2], staged: bankRows[2]?.file },
                        { code: 'OD', label: `Other Document ${otherDocTitle || otherDoc?.document_title ? `— ${otherDocTitle || otherDoc?.document_title}` : '(Optional)'}`, key: 'other_document', fileDoc: otherDoc, staged: stagedOtherDoc?.file, isOptional: true },
                      ].map((item) => {
                        const entry = (documentAudit && typeof documentAudit[item.key] === 'object' && documentAudit[item.key]) || { available: 'Pending', compliance: 'Under Verification', remarks: '' }
                        const hasDriveDoc = !!item.fileDoc
                        const hasStaged = !!item.staged
                        return (
                          <tr key={item.key}>
                            <td><strong>{item.code}</strong></td>
                            <td>{item.label}</td>
                            <td>
                              <select
                                value={entry.available || 'Pending'}
                                onChange={(e) => handleUpdateDocAudit(item.key, 'available', e.target.value)}
                                disabled={isAuditSubmitted}
                              >
                                <option value="Yes">Yes</option>
                                <option value="No">No</option>
                                <option value="Pending">Pending</option>
                              </select>
                            </td>
                            <td>
                              {hasDriveDoc ? (
                                <span className="l1-status-pill success" style={{ fontSize: '11px', padding: '2px 8px' }}>
                                  ✓ Verified in Drive
                                </span>
                              ) : hasStaged ? (
                                <span className="l1-status-pill info" style={{ fontSize: '11px', padding: '2px 8px' }}>
                                  Staged in Browser
                                </span>
                              ) : item.isOptional ? (
                                <span className="l1-status-pill secondary" style={{ fontSize: '11px', padding: '2px 8px' }}>
                                  Optional / Omitted
                                </span>
                              ) : (
                                <span className="l1-status-pill danger" style={{ fontSize: '11px', padding: '2px 8px' }}>
                                  Missing in Drive
                                </span>
                              )}
                            </td>
                            <td>
                              <input
                                type="text"
                                placeholder="Observations..."
                                value={entry.remarks || ''}
                                onChange={(e) => handleUpdateDocAudit(item.key, 'remarks', e.target.value)}
                                disabled={isAuditSubmitted}
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
                      <label className="l1-checkbox-label">
                        <input
                          type="checkbox"
                          checked={!!signoffDetails.centre_head?.recommended}
                          disabled={true}
                          readOnly
                        />
                        Recommended
                      </label>
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
                      <label className="l1-checkbox-label">
                        <input
                          type="checkbox"
                          checked={!!signoffDetails.cops_team?.verified}
                          disabled={true}
                          readOnly
                        />
                        Verified
                      </label>
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
                      <label className="l1-checkbox-label">
                        <input
                          type="checkbox"
                          checked={!!signoffDetails.business_leader?.approved}
                          disabled={true}
                          readOnly
                        />
                        Approved
                      </label>
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
                {bankRows.filter((r) => r.file).length === 0 && Object.keys(stagedBankReplacements).length === 0 ? (
                  <div style={{ fontSize: '13px', color: 'var(--mut)' }}>
                    (No new bank statements staged; retaining {bankStatements.length} existing verified months)
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {bankRows.filter((r) => r.file).map((r) => (
                      <div key={r.id} style={{ padding: '6px 12px', background: '#F0F9FF', border: '1px solid #BAE6FD', borderRadius: '8px', fontSize: '13px' }}>
                        📅 <strong>{MONTH_NAMES[r.month - 1]} {r.year}:</strong> {r.fileName} ({formatFileSize(r.fileSize)})
                      </div>
                    ))}
                    {Object.entries(stagedBankReplacements).filter(([, r]) => r.file).map(([id, r]) => (
                      <div key={id} style={{ padding: '6px 12px', background: '#FFFBEB', border: '1px solid #FDE68A', borderRadius: '8px', fontSize: '13px' }}>
                        🔄 Replacement for <strong>{MONTH_NAMES[r.month - 1]} {r.year}:</strong> {r.fileName} ({formatFileSize(r.fileSize)})
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
                {submitSuccessData.bankMonths.length > 0 && (
                  <div style={{ color: '#166534' }}>
                    ✓ Bank Statements ({submitSuccessData.bankMonths.length} months): {submitSuccessData.bankMonths.join(', ')}
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
