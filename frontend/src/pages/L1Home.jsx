import { useEffect, useRef, useState } from 'react'
import { api, downloadDocument } from '../lib/api'
import './L1Home.css'

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
}) {
  const [isDragOver, setIsDragOver] = useState(false)
  const inputRef = useRef(null)

  const handleDragOver = (e) => {
    e.preventDefault()
    if (!disabled) setIsDragOver(true)
  }

  const handleDragLeave = (e) => {
    e.preventDefault()
    setIsDragOver(false)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setIsDragOver(false)
    if (disabled) return
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
        <button type="button" className="l1-btn-choose" tabIndex={-1}>
          Browse File
        </button>
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

  // Browser-Only Document Staging State (NEVER uploaded prematurely)
  // Appointment letter staging: { file, fileName, fileSize, replaceId } | null
  const [stagedAppointment, setStagedAppointment] = useState(null)
  const [replacingAppointment, setReplacingAppointment] = useState(false)
  const [appointmentError, setAppointmentError] = useState('')

  // Monthly document staging: Array of { id, month, year, file, fileName, fileSize, replaceId, error }
  // EXACTLY 3 rows by default
  const createDefaultRows = (defaultOffset = 0) => [
    { id: `row_${Date.now()}_1`, month: 1 + defaultOffset, year: currentYear, file: null, fileName: '', fileSize: 0, replaceId: null, error: '' },
    { id: `row_${Date.now()}_2`, month: 2 + defaultOffset, year: currentYear, file: null, fileName: '', fileSize: 0, replaceId: null, error: '' },
    { id: `row_${Date.now()}_3`, month: 3 + defaultOffset, year: currentYear, file: null, fileName: '', fileSize: 0, replaceId: null, error: '' },
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

  const fill = (key, promise) =>
    promise.then((rows) => setLists((l) => ({ ...l, [key]: rows }))).catch((e) => setError(e.message))

  useEffect(() => {
    fill('state', api('/lookups/states'))
  }, [])

  function clearStagedFiles() {
    setStagedAppointment(null)
    setReplacingAppointment(false)
    setAppointmentError('')
    setSalaryRows(createDefaultRows(0))
    setBankRows(createDefaultRows(0))
    setStagedSalaryReplacements({})
    setStagedBankReplacements({})
    setActiveReplaceIds(new Set())
    setShowReviewModal(false)
    setSubmitSuccessData(null)
  }

  function refreshDocuments(candidateId) {
    if (!candidateId) return
    setLoadingDocs(true)
    Promise.all([
      api(`/candidates/${candidateId}/documents/summary`),
      api(`/candidates/${candidateId}/documents`),
    ])
      .then(([summary, docs]) => {
        setDocSummary(summary)
        setDocuments(docs || [])
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoadingDocs(false))
  }

  function pick(level, value) {
    setError('')
    setSel((s) => ({ ...s, ...Object.fromEntries(RESET[level].map((k) => [k, ''])), [level]: value }))
    setLists((l) => ({ ...l, ...Object.fromEntries(RESET[level].map((k) => [k, []])) }))
    setCandDetail(null)
    setDocSummary(null)
    setDocuments([])
    clearStagedFiles()

    if (!value) return
    if (level === 'state') fill('tc', api('/lookups/centres', { state: value }))
    if (level === 'tc') fill('order', api('/lookups/sanction-orders', { tc_id: value }))
    if (level === 'order') fill('batch', api('/lookups/batches', { tc_id: sel.tc, sanction_order: value }))
    if (level === 'batch') fill('cand', api('/lookups/candidates', { kb_batch_id: value }))
    if (level === 'cand') {
      setLoadingDetail(true)
      api(`/lookups/candidates/${value}`)
        .then((detail) => {
          setCandDetail(detail)
          refreshDocuments(value)
        })
        .catch((e) => setError(e.message))
        .finally(() => setLoadingDetail(false))
    }
  }

  const name = (c) => `${c.first_name ?? ''} ${c.last_name ?? ''}`.trim()
  const appointmentDoc = documents.find((d) => d.document_type === 'APPOINTMENT_LETTER')
  const salarySlips = documents.filter((d) => d.document_type === 'SALARY_SLIP')
  const bankStatements = documents.filter((d) => d.document_type === 'BANK_STATEMENT')

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
    const setter = type === 'SALARY' ? setSalaryRows : setBankRows
    if (rows.length > 3) {
      setter((prev) => prev.filter((r) => r.id !== rowId))
    } else {
      updateRowField(type, rowId, 'file', null)
    }
  }

  function handleAddRow(type) {
    const rows = type === 'SALARY' ? salaryRows : bankRows
    const existingCount = type === 'SALARY' ? salarySlips.length : bankStatements.length
    const totalCount = rows.length + existingCount
    if (totalCount >= 12) {
      setError(`Maximum limit of 12 months reached for ${type === 'SALARY' ? 'Salary Slips' : 'Bank Statements'}.`)
      return
    }
    const nextMonth = ((rows.length) % 12) + 1
    const newRow = {
      id: `row_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
      month: nextMonth,
      year: currentYear,
      file: null,
      fileName: '',
      fileSize: 0,
      replaceId: null,
      error: '',
    }
    if (type === 'SALARY') {
      setSalaryRows((prev) => [...prev, newRow])
    } else {
      setBankRows((prev) => [...prev, newRow])
    }
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
    setError('')

    if (!sel.cand || !candDetail) {
      return 'Please select a candidate before submitting.'
    }

    if (candDetail.has_active_hold) {
      return `Placement submission blocked: Candidate has an active administrative hold (${candDetail.active_holds?.[0]?.hold_reason || 'Under Review'}).`
    }

    // 1. Appointment Letter check
    const hasValidAppointment = appointmentDoc || (stagedAppointment && stagedAppointment.file)
    if (!hasValidAppointment) {
      return 'An Appointment / Offer Letter is required before final submission.'
    }
    if (stagedAppointment && appointmentError) {
      return `Appointment letter validation failed: ${appointmentError}`
    }

    // 2. Salary Slips check
    const replacedSalaryIds = new Set(Object.keys(stagedSalaryReplacements))
    const retainedSalaryMonths = new Set(
      salarySlips
        .filter((d) => !replacedSalaryIds.has(d.id))
        .map((d) => `${d.reporting_year}-${d.reporting_month}`)
    )

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
      if (retainedSalaryMonths.has(key)) {
        return `A salary slip for ${MONTH_NAMES[item.month - 1]} ${item.year} already exists in records. Please select a different month or use replacement.`
      }
      stagedSalaryMonths.add(key)
    }

    const totalSalaryMonthsCount = retainedSalaryMonths.size + stagedSalaryMonths.size
    if (totalSalaryMonthsCount < 3) {
      return `At least 3 distinct reporting months of Salary Slips are required. Currently satisfied: ${totalSalaryMonthsCount}.`
    }
    if (totalSalaryMonthsCount > 12) {
      return `Maximum 12 distinct reporting months allowed for Salary Slips. Currently provided: ${totalSalaryMonthsCount}.`
    }

    // 3. Bank Statements check
    const replacedBankIds = new Set(Object.keys(stagedBankReplacements))
    const retainedBankMonths = new Set(
      bankStatements
        .filter((d) => !replacedBankIds.has(d.id))
        .map((d) => `${d.reporting_year}-${d.reporting_month}`)
    )

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
      if (retainedBankMonths.has(key)) {
        return `A bank statement for ${MONTH_NAMES[item.month - 1]} ${item.year} already exists in records. Please select a different month or use replacement.`
      }
      stagedBankMonths.add(key)
    }

    const totalBankMonthsCount = retainedBankMonths.size + stagedBankMonths.size
    if (totalBankMonthsCount < 3) {
      return `At least 3 distinct reporting months of Bank Statements are required. Currently satisfied: ${totalBankMonthsCount}.`
    }
    if (totalBankMonthsCount > 12) {
      return `Maximum 12 distinct reporting months allowed for Bank Statements. Currently provided: ${totalBankMonthsCount}.`
    }

    // Check if there are any new or replacement files to submit
    const totalFilesToSubmit = (stagedAppointment?.file ? 1 : 0) + stagedSalaryEntries.length + stagedBankEntries.length
    if (totalFilesToSubmit === 0) {
      return 'All placement requirements are already satisfied from previous submissions, and no new or replacement documents have been staged.'
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

      const res = await api(`/candidates/${sel.cand}/documents/submit`, null, {
        method: 'POST',
        body: formData,
      })

      setShowReviewModal(false)
      setSubmitSuccessData({
        candidateId: sel.cand,
        candidateName: `${candDetail.first_name} ${candDetail.last_name}`,
        appointmentUploaded: !!stagedAppointment?.file,
        salaryMonths: salaryMeta.map((m) => `${MONTH_NAMES[m.month - 1]} ${m.year}`),
        bankMonths: bankMeta.map((m) => `${MONTH_NAMES[m.month - 1]} ${m.year}`),
        totalSubmitted: res.submitted_count,
      })
    } catch (err) {
      setShowReviewModal(false)
      setError(err.message || 'Submission failed. Any created Google Drive files were safely cleaned up.')
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } finally {
      setSubmitting(false)
    }
  }

  // Workflow reset after viewing success dialog
  function handleCompleteWorkflowReset() {
    setSubmitSuccessData(null)
    clearStagedFiles()
    setSel({ state: '', tc: '', order: '', batch: '', cand: '' })
    setLists((l) => ({ ...l, tc: [], order: [], batch: [], cand: [] }))
    setCandDetail(null)
    setDocSummary(null)
    setDocuments([])
    setError('')
  }

  // Calculations for Checklist & Progress
  const stagedSalaryCount = salaryRows.filter((r) => r.file).length + Object.values(stagedSalaryReplacements).filter((r) => r.file).length
  const stagedBankCount = bankRows.filter((r) => r.file).length + Object.values(stagedBankReplacements).filter((r) => r.file).length
  const totalStagedFiles = (stagedAppointment?.file ? 1 : 0) + stagedSalaryCount + stagedBankCount

  const appointmentSatisfied = !!appointmentDoc || !!stagedAppointment?.file
  const salarySatisfied = salarySlips.length + stagedSalaryCount >= 3
  const bankSatisfied = bankStatements.length + stagedBankCount >= 3
  const allRequirementsSatisfied = appointmentSatisfied && salarySatisfied && bankSatisfied

  // Candidate initials
  const candInitials = candDetail
    ? `${candDetail.first_name?.[0] || ''}${candDetail.last_name?.[0] || ''}`.toUpperCase() || 'CP'
    : 'CP'

  return (
    <div className="l1-dashboard">
      {/* --------------------------------------------------------------------
         Hero / Portal Banner matching Login Aesthetics
         -------------------------------------------------------------------- */}
      <section className="l1-hero-banner">
        <div className="l1-hero-content">
          <span className="l1-portal-badge">
            ✦ L1 Placement Verification Portal
          </span>
          <h1>Verify & Validate, Sync & Confirm.</h1>
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
              >
                <option value="">Select State…</option>
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

      {/* --------------------------------------------------------------------
         Candidate Summary Profile Card
         -------------------------------------------------------------------- */}
      {candDetail && (
        <section className="l1-cand-summary-card">
          <div className="l1-cand-header">
            <div className="l1-cand-identity">
              <div className="l1-cand-avatar">{candInitials}</div>
              <div className="l1-cand-names">
                <h2>{candDetail.first_name} {candDetail.last_name}</h2>
                <div className="l1-cand-id-badge">
                  Candidate ID: <strong>{candDetail.candidate_id}</strong>
                </div>
              </div>
            </div>
            <div>
              <span className={`l1-status-pill ${candDetail.appointed ? 'success' : 'info'}`}>
                {candDetail.appointed ? '✓ Placed & Appointed' : '● Under Training / Pending Placement'}
              </span>
            </div>
          </div>

          <div className="l1-cand-meta-grid">
            <div className="l1-meta-item">
              <span className="l1-meta-label">Father's Name</span>
              <span className="l1-meta-val">{candDetail.father_name || '—'}</span>
            </div>
            <div className="l1-meta-item">
              <span className="l1-meta-label">Date of Birth</span>
              <span className="l1-meta-val">{candDetail.dob || '—'}</span>
            </div>
            <div className="l1-meta-item">
              <span className="l1-meta-label">Mobile Contact</span>
              <span className="l1-meta-val">{candDetail.mobile || '—'}</span>
            </div>
            <div className="l1-meta-item">
              <span className="l1-meta-label">Assigned Centre</span>
              <span className="l1-meta-val">{lists.tc.find((c) => c.tc_id === sel.tc)?.name || sel.tc}</span>
            </div>
          </div>

          {/* Informational Duplicate Warning */}
          {candDetail.has_duplicate_warning && (
            <div className="l1-banner-warning" role="status">
              <span style={{ fontSize: '16px' }}>ℹ️</span>
              <div>
                <strong>Informational Notice:</strong> Possible duplicate candidate record under administrative review. This notice does not block placement verification or file submission.
              </div>
            </div>
          )}

          {/* Blocking Submission Hold */}
          {candDetail.has_active_hold && (
            <div className="l1-banner-danger" role="alert">
              <span style={{ fontSize: '18px' }}>⚠️</span>
              <div>
                <strong>Placement Submission Blocked:</strong> Administrative hold in effect ({candDetail.active_holds?.[0]?.hold_reason || 'Under review hold placed by centre manager'}). Final document upload is locked until the hold is resolved.
              </div>
            </div>
          )}
        </section>
      )}

      {/* --------------------------------------------------------------------
         Document Workspaces & Verification Sections (When Candidate Selected)
         -------------------------------------------------------------------- */}
      {sel.cand && (
        <>
          {/* Document Completion Progress Card */}
          <section className="l1-overview-card">
            <div className="l1-overview-header">
              <h3>Document Verification Progress</h3>
              <span className={`l1-status-pill ${allRequirementsSatisfied ? 'success' : 'warning'}`}>
                {allRequirementsSatisfied ? '✓ Placement Requirements Satisfied' : 'Pending Verification Requirements'}
              </span>
            </div>

            <div className="l1-requirements-grid">
              {/* Category 1: Appointment Letter */}
              <div className={`l1-req-card ${appointmentDoc ? 'satisfied' : stagedAppointment?.file ? 'staged-only' : ''}`}>
                <div className="l1-req-card-top">
                  <div className="l1-req-title">
                    <span className="l1-req-icon">✉</span>
                    Appointment Letter
                  </div>
                  <span className={`l1-status-pill ${appointmentDoc ? 'success' : stagedAppointment?.file ? 'info' : 'danger'}`}>
                    {appointmentDoc ? 'Verified' : stagedAppointment?.file ? 'Staged' : 'Missing'}
                  </span>
                </div>
                <div className="l1-req-detail">
                  Exactly 1 signed appointment or offer letter per candidate.
                </div>
                <div className="l1-req-status-row">
                  <span>Requirement: 1 file</span>
                  <strong>{appointmentDoc ? '1 Verified' : stagedAppointment?.file ? '1 Staged' : '0 Provided'}</strong>
                </div>
              </div>

              {/* Category 2: Salary Slips */}
              <div className={`l1-req-card ${salarySlips.length >= 3 ? 'satisfied' : salarySlips.length + stagedSalaryCount >= 3 ? 'staged-only' : ''}`}>
                <div className="l1-req-card-top">
                  <div className="l1-req-title">
                    <span className="l1-req-icon">₹</span>
                    Salary Slips
                  </div>
                  <span className={`l1-status-pill ${salarySlips.length >= 3 ? 'success' : salarySlips.length + stagedSalaryCount >= 3 ? 'info' : 'warning'}`}>
                    {salarySlips.length >= 3 ? 'Satisfied' : salarySlips.length + stagedSalaryCount >= 3 ? 'Staged Satisfied' : 'Incomplete'}
                  </span>
                </div>
                <div className="l1-req-detail">
                  At least 3 distinct reporting months required (up to 12).
                </div>
                <div className="l1-req-status-row">
                  <span>Requirement: Min 3 months</span>
                  <strong>{salarySlips.length} Persisted + {stagedSalaryCount} Staged</strong>
                </div>
              </div>

              {/* Category 3: Bank Statements */}
              <div className={`l1-req-card ${bankStatements.length >= 3 ? 'satisfied' : bankStatements.length + stagedBankCount >= 3 ? 'staged-only' : ''}`}>
                <div className="l1-req-card-top">
                  <div className="l1-req-title">
                    <span className="l1-req-icon">▤</span>
                    Bank Statements
                  </div>
                  <span className={`l1-status-pill ${bankStatements.length >= 3 ? 'success' : bankStatements.length + stagedBankCount >= 3 ? 'info' : 'warning'}`}>
                    {bankStatements.length >= 3 ? 'Satisfied' : bankStatements.length + stagedBankCount >= 3 ? 'Staged Satisfied' : 'Incomplete'}
                  </span>
                </div>
                <div className="l1-req-detail">
                  At least 3 distinct reporting months required matching salary disbursement.
                </div>
                <div className="l1-req-status-row">
                  <span>Requirement: Min 3 months</span>
                  <strong>{bankStatements.length} Persisted + {stagedBankCount} Staged</strong>
                </div>
              </div>
            </div>
          </section>

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
                      onClick={() => downloadDocument(sel.cand, appointmentDoc.id, appointmentDoc.file_name)}
                    >
                      Download / Preview
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
              <span className={`l1-status-pill ${salarySlips.length + stagedSalaryCount >= 3 ? 'success' : 'warning'}`}>
                {salarySlips.length} Persisted + {stagedSalaryCount} Staged
              </span>
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
                            onClick={() => downloadDocument(sel.cand, doc.id, doc.file_name)}
                          >
                            Download / Preview
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
                    <div className="l1-period-picker">
                      <select
                        value={row.month}
                        aria-label={`Slot ${index + 1} Month`}
                        onChange={(e) => updateRowField('SALARY', row.id, 'month', parseInt(e.target.value, 10))}
                      >
                        {MONTH_NAMES.map((m, mIdx) => (
                          <option key={mIdx + 1} value={mIdx + 1}>{m}</option>
                        ))}
                      </select>
                      <select
                        value={row.year}
                        aria-label={`Slot ${index + 1} Year`}
                        onChange={(e) => updateRowField('SALARY', row.id, 'year', parseInt(e.target.value, 10))}
                      >
                        {years.map((y) => (
                          <option key={y} value={y}>{y}</option>
                        ))}
                      </select>
                    </div>

                    <FileUploadControl
                      file={row.file}
                      fileName={row.fileName}
                      fileSize={row.fileSize}
                      error={row.error}
                      label={`Attach Salary Slip (${MONTH_NAMES[row.month - 1]} ${row.year})`}
                      helperText="PDF, PNG, JPG (up to 10MB)"
                      stagedLabel="Staged (Pending Submit)"
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
                  onClick={() => handleAddRow('SALARY')}
                >
                  + Add Another Salary Slip Month
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
              <span className={`l1-status-pill ${bankStatements.length + stagedBankCount >= 3 ? 'success' : 'warning'}`}>
                {bankStatements.length} Persisted + {stagedBankCount} Staged
              </span>
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
                            onClick={() => downloadDocument(sel.cand, doc.id, doc.file_name)}
                          >
                            Download / Preview
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
                    <div className="l1-period-picker">
                      <select
                        value={row.month}
                        aria-label={`Bank Slot ${index + 1} Month`}
                        onChange={(e) => updateRowField('BANK', row.id, 'month', parseInt(e.target.value, 10))}
                      >
                        {MONTH_NAMES.map((m, mIdx) => (
                          <option key={mIdx + 1} value={mIdx + 1}>{m}</option>
                        ))}
                      </select>
                      <select
                        value={row.year}
                        aria-label={`Bank Slot ${index + 1} Year`}
                        onChange={(e) => updateRowField('BANK', row.id, 'year', parseInt(e.target.value, 10))}
                      >
                        {years.map((y) => (
                          <option key={y} value={y}>{y}</option>
                        ))}
                      </select>
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
                  onClick={() => handleAddRow('BANK')}
                >
                  + Add Another Bank Statement Month
                </button>
              )}
            </div>
          </section>

          {/* ================================================================
             STICKY BOTTOM FINAL SUBMISSION DOCK
             ================================================================ */}
          <div className="l1-submit-dock">
            <div className="l1-dock-info">
              <span className="l1-dock-title">
                {allRequirementsSatisfied ? '✓ Placement Requirements Satisfied' : 'Pending Verification Requirements'}
                <span className={`l1-status-pill ${totalStagedFiles > 0 ? 'info' : 'secondary'}`} style={{ fontSize: '12px', padding: '3px 10px' }}>
                  {totalStagedFiles} Staged {totalStagedFiles === 1 ? 'file' : 'files'}
                </span>
              </span>
              <p className="l1-dock-desc">
                Files remain staged safely in your browser. Nothing is uploaded to Google Drive until you confirm.
              </p>
            </div>
            <button
              type="button"
              className="l1-btn-primary-action"
              onClick={handleOpenReviewModal}
            >
              Review & Final Submit →
            </button>
          </div>
        </>
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
                onClick={handleCompleteWorkflowReset}
              >
                Done / Verify Next Candidate
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
