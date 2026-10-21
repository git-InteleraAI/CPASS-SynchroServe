import { useEffect, useState } from 'react'
import { api, downloadDocument } from '../lib/api'

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
const ALLOWED_MIME_TYPES = ['application/pdf', 'image/png', 'image/jpeg', 'image/jpg']
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

function Pick({ label, value, options, disabled, onChange }) {
  return (
    <label>
      {label}
      <select value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
        <option value="">Select…</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  )
}

function ChecklistPanel({ summary, stagedSummary }) {
  if (!summary) return null

  return (
    <div className="checklist-card">
      <div className="checklist-header">
        <h3 style={{ margin: 0, fontSize: '1.1rem' }}>L1 Placement Document Checklist</h3>
        <span className={`badge ${summary.min_requirements_met ? 'badge-success' : 'badge-warning'}`}>
          {summary.min_requirements_met ? '✓ Placement Requirements Satisfied' : 'Pending Verification Requirements'}
        </span>
      </div>

      <div className="checklist-items">
        {summary.checklist?.map((item, idx) => (
          <div key={idx} className="checklist-item">
            <div>
              <strong>{item.item}</strong>
              <div className="doc-meta">{item.detail}</div>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              {stagedSummary && stagedSummary[item.item] && (
                <span className="badge badge-staged">{stagedSummary[item.item]} staged</span>
              )}
              <span className={`badge ${item.satisfied ? 'badge-success' : 'badge-danger'}`}>
                {item.satisfied ? 'Persisted' : 'Pending'}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function L1Home() {
  const currentYear = new Date().getFullYear()
  const years = [currentYear - 2, currentYear - 1, currentYear, currentYear + 1]

  // Dropdown navigation state
  const [lists, setLists] = useState({ state: [], tc: [], order: [], batch: [], cand: [] })
  const [sel, setSel] = useState({ state: '', tc: '', order: '', batch: '', cand: '' })
  const [candDetail, setCandDetail] = useState(null)
  const [loadingDetail, setLoadingDetail] = useState(false)

  // Persisted documents from Supabase
  const [docSummary, setDocSummary] = useState(null)
  const [documents, setDocuments] = useState([])
  const [loadingDocs, setLoadingDocs] = useState(false)
  const [error, setError] = useState('')

  // PHASE 3 & 4: Browser-Only Document Staging State
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
    // Allow removing if total rows > 3, OR if it has a file, allow clearing the file
    if (rows.length > 3) {
      setter((prev) => prev.filter((r) => r.id !== rowId))
    } else {
      // Clear file in slot
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
        // Also clean up staged replacement
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
    // Collect retained persisted salary slips (not replaced)
    const replacedSalaryIds = new Set([
      ...Object.keys(stagedSalaryReplacements),
    ])
    const retainedSalaryMonths = new Set(
      salarySlips
        .filter((d) => !replacedSalaryIds.has(d.id))
        .map((d) => `${d.reporting_year}-${d.reporting_month}`)
    )

    // Collect staged salary slips
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
      return `At least 3 distinct reporting months of Salary Slips are required. Currently provided: ${totalSalaryMonthsCount}.`
    }
    if (totalSalaryMonthsCount > 12) {
      return `Maximum 12 distinct reporting months allowed for Salary Slips. Currently provided: ${totalSalaryMonthsCount}.`
    }

    // 3. Bank Statements check
    const replacedBankIds = new Set([
      ...Object.keys(stagedBankReplacements),
    ])
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
      return `At least 3 distinct reporting months of Bank Statements are required. Currently provided: ${totalBankMonthsCount}.`
    }
    if (totalBankMonthsCount > 12) {
      return `Maximum 12 distinct reporting months allowed for Bank Statements. Currently provided: ${totalBankMonthsCount}.`
    }

    // Check if there are any new files to submit
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

      // Close review modal and show success dialog
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

  // Compute staged summary badges for checklist
  const stagedSalaryCount = salaryRows.filter((r) => r.file).length + Object.values(stagedSalaryReplacements).filter((r) => r.file).length
  const stagedBankCount = bankRows.filter((r) => r.file).length + Object.values(stagedBankReplacements).filter((r) => r.file).length
  const stagedSummary = {
    'Appointment / Offer Letter': stagedAppointment?.file ? '1' : null,
    'Salary Slips': stagedSalaryCount > 0 ? `${stagedSalaryCount}` : null,
    'Bank Statements': stagedBankCount > 0 ? `${stagedBankCount}` : null,
  }

  return (
    <section className="panel">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
        <h2>L1 Candidate Placement Verification</h2>
        <span className="badge badge-info">L1 Verification Portal</span>
      </div>

      {error && (
        <div className="hold-danger" role="alert" style={{ margin: '1rem 0' }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Cascading selectors: State -> Centre -> Sanction Order -> Batch -> Candidate */}
      <div className="grid">
        <Pick
          label="State"
          value={sel.state}
          options={lists.state.map((s) => ({ value: s, label: s }))}
          onChange={(v) => pick('state', v)}
        />
        <Pick
          label="Training centre"
          value={sel.tc}
          disabled={!sel.state}
          options={lists.tc.map((c) => ({ value: c.tc_id, label: c.name }))}
          onChange={(v) => pick('tc', v)}
        />
        <Pick
          label="Sanction order"
          value={sel.order}
          disabled={!sel.tc}
          options={lists.order.map((o) => ({ value: o, label: o }))}
          onChange={(v) => pick('order', v)}
        />
        <Pick
          label="Batch"
          value={sel.batch}
          disabled={!sel.order}
          options={lists.batch.map((b) => ({ value: b.kb_batch_id, label: b.batch_code }))}
          onChange={(v) => pick('batch', v)}
        />
        <Pick
          label="Candidate"
          value={sel.cand}
          disabled={!sel.batch}
          options={lists.cand.map((c) => ({
            value: c.candidate_id,
            label: `${name(c)} (Father: ${c.father_name || '—'}) [ID: ${c.candidate_id}]`,
          }))}
          onChange={(v) => pick('cand', v)}
        />
      </div>

      {loadingDetail && <p className="muted">Loading candidate details…</p>}

      {candDetail && (
        <div className="status-box">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
            <h3 style={{ margin: 0 }}>
              {candDetail.first_name} {candDetail.last_name} (Candidate ID: {candDetail.candidate_id})
            </h3>
            <span className={`badge ${candDetail.appointed ? 'badge-success' : 'badge-info'}`}>
              {candDetail.appointed ? 'Appointed' : 'Under Training / Pending'}
            </span>
          </div>
          <p className="muted" style={{ marginTop: '0.35rem' }}>
            Father: {candDetail.father_name || '—'} · DOB: {candDetail.dob || '—'} · Mobile: {candDetail.mobile || '—'} · State: {sel.state}
          </p>

          {/* Candidate-level non-blocking duplicate warning */}
          {candDetail.has_duplicate_warning && (
            <div className="warning" role="status">
              <strong>Notice:</strong> Possible duplicate record under review. (This informational notice does not block placement submission.)
            </div>
          )}

          {/* Candidate-level blocking submission hold */}
          {candDetail.has_active_hold && (
            <div className="hold-danger" role="alert">
              <strong>Submission Hold Active:</strong> {candDetail.active_holds[0]?.hold_reason || 'Under review hold placed by manager'}. Placement submission is blocked.
            </div>
          )}
        </div>
      )}

      {/* Document Verification & Staging Workflow */}
      {sel.cand && (
        <div className="workflow-container">
          {loadingDocs && !docSummary && <p className="muted">Loading document records from Google Drive & Database…</p>}

          {/* Live checklist panel */}
          <ChecklistPanel summary={docSummary} stagedSummary={stagedSummary} />

          {/* 1. Appointment / Offer Letter Section */}
          <div className="doc-section">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
              <div>
                <h3>1. Appointment / Offer Letter</h3>
                <p className="section-desc">
                  Exactly one active appointment or offer letter per candidate. PDF, PNG, or JPG up to 10MB.
                </p>
              </div>
              <span className={`badge ${appointmentDoc || stagedAppointment?.file ? 'badge-success' : 'badge-danger'}`}>
                {appointmentDoc ? 'Verified in Drive' : stagedAppointment?.file ? 'Staged' : 'Required'}
              </span>
            </div>

            {/* Display persisted appointment letter if exists */}
            {appointmentDoc && (
              <div className={`doc-card existing ${replacingAppointment ? 'replacing' : ''}`}>
                <div className="doc-card-row">
                  <div>
                    <div style={{ fontWeight: 600 }}>{appointmentDoc.file_name}</div>
                    <div className="doc-meta">
                      Size: {formatFileSize(appointmentDoc.file_size_bytes)} · Persisted: {new Date(appointmentDoc.created_at).toLocaleDateString()}
                    </div>
                  </div>
                  <span className="badge badge-success">✓ Persisted in Drive</span>
                </div>

                <div className="doc-actions">
                  <button
                    type="button"
                    className="btn-sm btn-outline"
                    onClick={() => downloadDocument(sel.cand, appointmentDoc.id, appointmentDoc.file_name)}
                  >
                    Download / Preview
                  </button>
                  <button
                    type="button"
                    className="btn-sm btn-secondary"
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
            )}

            {/* Appointment Letter Staging Form (New or Replacement) */}
            {(!appointmentDoc || replacingAppointment) && (
              <div className={`doc-card ${stagedAppointment?.file ? 'staged' : ''}`}>
                <div className="doc-card-row">
                  <span className="doc-meta">
                    <strong>{appointmentDoc ? 'Replacement Appointment Letter:' : 'Select Appointment Letter:'}</strong> (File is staged locally until Final Submit)
                  </span>
                  {stagedAppointment?.file && (
                    <span className="badge badge-staged">
                      {stagedAppointment.replaceId ? 'Staged Replacement' : 'Staged (Pending Submit)'}
                    </span>
                  )}
                </div>

                {appointmentError && <p className="error" style={{ fontSize: '0.88rem' }}>{appointmentError}</p>}

                {stagedAppointment?.file ? (
                  <div className="doc-card-row" style={{ background: '#fff', padding: '0.6rem 0.8rem', borderRadius: '4px', border: '1px solid var(--line)' }}>
                    <div>
                      <strong style={{ fontSize: '0.92rem' }}>{stagedAppointment.fileName}</strong>
                      <span className="doc-meta" style={{ marginLeft: '0.5rem' }}>
                        ({formatFileSize(stagedAppointment.fileSize)})
                      </span>
                    </div>
                    <button
                      type="button"
                      className="btn-sm btn-danger"
                      onClick={handleRemoveStagedAppointment}
                    >
                      Remove Staged File
                    </button>
                  </div>
                ) : (
                  <div className="file-upload-box">
                    <input
                      type="file"
                      accept=".pdf,.png,.jpg,.jpeg"
                      onChange={(e) => handleSelectAppointment(e.target.files[0], !!appointmentDoc)}
                    />
                    <span className="muted" style={{ fontSize: '0.85rem' }}>
                      Selecting a file stages it locally. No upload occurs until Final Submit.
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 2. Salary Slips Section (Default 3 rows, min 3, max 12) */}
          <div className="doc-section">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
              <div>
                <h3>2. Salary Slips</h3>
                <p className="section-desc">
                  Default 3 rows. At least 3 distinct reporting months required, up to 12 months maximum.
                </p>
              </div>
              <span className={`badge ${salarySlips.length + salaryRows.filter((r) => r.file).length >= 3 ? 'badge-success' : 'badge-warning'}`}>
                {salarySlips.length} Persisted + {salaryRows.filter((r) => r.file).length + Object.values(stagedSalaryReplacements).filter((r) => r.file).length} Staged
              </span>
            </div>

            {/* Persisted Salary Slips */}
            {salarySlips.map((doc) => {
              const isReplacing = activeReplaceIds.has(doc.id)
              const stagedRepl = stagedSalaryReplacements[doc.id]

              return (
                <div key={doc.id} className={`doc-card existing ${isReplacing ? 'replacing' : ''}`}>
                  <div className="doc-card-row">
                    <div>
                      <strong style={{ fontSize: '1rem' }}>
                        {MONTH_NAMES[doc.reporting_month - 1]} {doc.reporting_year}
                      </strong>
                      <div style={{ marginTop: '0.2rem' }}>{doc.file_name}</div>
                      <div className="doc-meta">
                        Size: {formatFileSize(doc.file_size_bytes)} · Persisted: {new Date(doc.created_at).toLocaleDateString()}
                      </div>
                    </div>
                    <span className="badge badge-success">✓ Persisted in Drive</span>
                  </div>

                  <div className="doc-actions">
                    <button
                      type="button"
                      className="btn-sm btn-outline"
                      onClick={() => downloadDocument(sel.cand, doc.id, doc.file_name)}
                    >
                      Download / Preview
                    </button>
                    <button
                      type="button"
                      className="btn-sm btn-secondary"
                      onClick={() => toggleReplaceMode(doc.id)}
                    >
                      {isReplacing ? 'Cancel Replacement' : 'Replace'}
                    </button>
                  </div>

                  {isReplacing && (
                    <div style={{ marginTop: '0.5rem', paddingTop: '0.5rem', borderTop: '1px dashed var(--line)' }}>
                      <div className="doc-card-row">
                        <span className="doc-meta">
                          <strong>Staged Replacement for {MONTH_NAMES[doc.reporting_month - 1]} {doc.reporting_year}:</strong>
                        </span>
                        {stagedRepl?.file && <span className="badge badge-replacement">Staged Replacement</span>}
                      </div>

                      {stagedRepl?.error && <p className="error" style={{ fontSize: '0.85rem' }}>{stagedRepl.error}</p>}

                      {stagedRepl?.file ? (
                        <div className="doc-card-row" style={{ background: '#fff', padding: '0.5rem 0.75rem', borderRadius: '4px', border: '1px solid var(--line)', marginTop: '0.5rem' }}>
                          <div>
                            <strong>{stagedRepl.fileName}</strong> ({formatFileSize(stagedRepl.fileSize)})
                          </div>
                          <button
                            type="button"
                            className="btn-sm btn-danger"
                            onClick={() => toggleReplaceMode(doc.id)}
                          >
                            Remove Staged Replacement
                          </button>
                        </div>
                      ) : (
                        <div className="file-upload-box" style={{ marginTop: '0.5rem' }}>
                          <input
                            type="file"
                            accept=".pdf,.png,.jpg,.jpeg"
                            onChange={(e) => handleSelectReplacement(doc, e.target.files[0])}
                          />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}

            {/* Staged / Pending Salary Slip Rows (EXACTLY 3 rows by default) */}
            <div style={{ marginTop: '1rem' }}>
              <div style={{ fontWeight: 600, fontSize: '0.95rem', marginBottom: '0.5rem' }}>
                Pending / Staged Salary Slip Slots:
              </div>

              {salaryRows.map((row, index) => (
                <div key={row.id} className={`doc-card ${row.file ? 'staged' : ''}`}>
                  <div className="doc-card-row">
                    <span className="doc-meta">
                      <strong>Slot {index + 1}:</strong> Reporting Month & File
                    </span>
                    {row.file ? (
                      <span className="badge badge-staged">Staged ({formatFileSize(row.fileSize)})</span>
                    ) : (
                      <span className="muted" style={{ fontSize: '0.85rem' }}>Unstaged</span>
                    )}
                  </div>

                  {row.error && <p className="error" style={{ fontSize: '0.85rem' }}>{row.error}</p>}

                  <div className="file-upload-box">
                    <div className="period-selector">
                      <select
                        value={row.month}
                        onChange={(e) => updateRowField('SALARY', row.id, 'month', parseInt(e.target.value, 10))}
                      >
                        {MONTH_NAMES.map((m, mIdx) => (
                          <option key={mIdx + 1} value={mIdx + 1}>{m}</option>
                        ))}
                      </select>
                      <select
                        value={row.year}
                        onChange={(e) => updateRowField('SALARY', row.id, 'year', parseInt(e.target.value, 10))}
                      >
                        {years.map((y) => (
                          <option key={y} value={y}>{y}</option>
                        ))}
                      </select>
                    </div>

                    <input
                      type="file"
                      accept=".pdf,.png,.jpg,.jpeg"
                      onChange={(e) => updateRowField('SALARY', row.id, 'file', e.target.files[0] || null)}
                    />

                    {/* Remove row button: clears file if <= 3 rows, removes row if > 3 rows */}
                    <button
                      type="button"
                      className="btn-sm btn-secondary"
                      onClick={() => handleRemoveRow('SALARY', row.id)}
                    >
                      {salaryRows.length > 3 ? 'Remove Row' : row.file ? 'Clear File' : 'Reset'}
                    </button>
                  </div>
                </div>
              ))}

              {salaryRows.length + salarySlips.length < 12 && (
                <button
                  type="button"
                  className="btn-secondary btn-sm btn-add"
                  onClick={() => handleAddRow('SALARY')}
                >
                  + Add Salary Slip Row
                </button>
              )}
            </div>
          </div>

          {/* 3. Bank Statements Section (Default 3 rows, min 3, max 12) */}
          <div className="doc-section">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
              <div>
                <h3>3. Bank Statements</h3>
                <p className="section-desc">
                  Default 3 rows. At least 3 distinct reporting months required, up to 12 months maximum.
                </p>
              </div>
              <span className={`badge ${bankStatements.length + bankRows.filter((r) => r.file).length >= 3 ? 'badge-success' : 'badge-warning'}`}>
                {bankStatements.length} Persisted + {bankRows.filter((r) => r.file).length + Object.values(stagedBankReplacements).filter((r) => r.file).length} Staged
              </span>
            </div>

            {/* Persisted Bank Statements */}
            {bankStatements.map((doc) => {
              const isReplacing = activeReplaceIds.has(doc.id)
              const stagedRepl = stagedBankReplacements[doc.id]

              return (
                <div key={doc.id} className={`doc-card existing ${isReplacing ? 'replacing' : ''}`}>
                  <div className="doc-card-row">
                    <div>
                      <strong style={{ fontSize: '1rem' }}>
                        {MONTH_NAMES[doc.reporting_month - 1]} {doc.reporting_year}
                      </strong>
                      <div style={{ marginTop: '0.2rem' }}>{doc.file_name}</div>
                      <div className="doc-meta">
                        Size: {formatFileSize(doc.file_size_bytes)} · Persisted: {new Date(doc.created_at).toLocaleDateString()}
                      </div>
                    </div>
                    <span className="badge badge-success">✓ Persisted in Drive</span>
                  </div>

                  <div className="doc-actions">
                    <button
                      type="button"
                      className="btn-sm btn-outline"
                      onClick={() => downloadDocument(sel.cand, doc.id, doc.file_name)}
                    >
                      Download / Preview
                    </button>
                    <button
                      type="button"
                      className="btn-sm btn-secondary"
                      onClick={() => toggleReplaceMode(doc.id)}
                    >
                      {isReplacing ? 'Cancel Replacement' : 'Replace'}
                    </button>
                  </div>

                  {isReplacing && (
                    <div style={{ marginTop: '0.5rem', paddingTop: '0.5rem', borderTop: '1px dashed var(--line)' }}>
                      <div className="doc-card-row">
                        <span className="doc-meta">
                          <strong>Staged Replacement for {MONTH_NAMES[doc.reporting_month - 1]} {doc.reporting_year}:</strong>
                        </span>
                        {stagedRepl?.file && <span className="badge badge-replacement">Staged Replacement</span>}
                      </div>

                      {stagedRepl?.error && <p className="error" style={{ fontSize: '0.85rem' }}>{stagedRepl.error}</p>}

                      {stagedRepl?.file ? (
                        <div className="doc-card-row" style={{ background: '#fff', padding: '0.5rem 0.75rem', borderRadius: '4px', border: '1px solid var(--line)', marginTop: '0.5rem' }}>
                          <div>
                            <strong>{stagedRepl.fileName}</strong> ({formatFileSize(stagedRepl.fileSize)})
                          </div>
                          <button
                            type="button"
                            className="btn-sm btn-danger"
                            onClick={() => toggleReplaceMode(doc.id)}
                          >
                            Remove Staged Replacement
                          </button>
                        </div>
                      ) : (
                        <div className="file-upload-box" style={{ marginTop: '0.5rem' }}>
                          <input
                            type="file"
                            accept=".pdf,.png,.jpg,.jpeg"
                            onChange={(e) => handleSelectReplacement(doc, e.target.files[0])}
                          />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}

            {/* Staged / Pending Bank Statement Rows (EXACTLY 3 rows by default) */}
            <div style={{ marginTop: '1rem' }}>
              <div style={{ fontWeight: 600, fontSize: '0.95rem', marginBottom: '0.5rem' }}>
                Pending / Staged Bank Statement Slots:
              </div>

              {bankRows.map((row, index) => (
                <div key={row.id} className={`doc-card ${row.file ? 'staged' : ''}`}>
                  <div className="doc-card-row">
                    <span className="doc-meta">
                      <strong>Slot {index + 1}:</strong> Reporting Month & File
                    </span>
                    {row.file ? (
                      <span className="badge badge-staged">Staged ({formatFileSize(row.fileSize)})</span>
                    ) : (
                      <span className="muted" style={{ fontSize: '0.85rem' }}>Unstaged</span>
                    )}
                  </div>

                  {row.error && <p className="error" style={{ fontSize: '0.85rem' }}>{row.error}</p>}

                  <div className="file-upload-box">
                    <div className="period-selector">
                      <select
                        value={row.month}
                        onChange={(e) => updateRowField('BANK', row.id, 'month', parseInt(e.target.value, 10))}
                      >
                        {MONTH_NAMES.map((m, mIdx) => (
                          <option key={mIdx + 1} value={mIdx + 1}>{m}</option>
                        ))}
                      </select>
                      <select
                        value={row.year}
                        onChange={(e) => updateRowField('BANK', row.id, 'year', parseInt(e.target.value, 10))}
                      >
                        {years.map((y) => (
                          <option key={y} value={y}>{y}</option>
                        ))}
                      </select>
                    </div>

                    <input
                      type="file"
                      accept=".pdf,.png,.jpg,.jpeg"
                      onChange={(e) => updateRowField('BANK', row.id, 'file', e.target.files[0] || null)}
                    />

                    <button
                      type="button"
                      className="btn-sm btn-secondary"
                      onClick={() => handleRemoveRow('BANK', row.id)}
                    >
                      {bankRows.length > 3 ? 'Remove Row' : row.file ? 'Clear File' : 'Reset'}
                    </button>
                  </div>
                </div>
              ))}

              {bankRows.length + bankStatements.length < 12 && (
                <button
                  type="button"
                  className="btn-secondary btn-sm btn-add"
                  onClick={() => handleAddRow('BANK')}
                >
                  + Add Bank Statement Row
                </button>
              )}
            </div>
          </div>

          {/* FINAL SUBMISSION ACTION BAR */}
          <div className="submit-bar">
            <div>
              <strong style={{ fontSize: '1.05rem', color: 'var(--ink)' }}>
                Ready to Finalize Placement Submission?
              </strong>
              <p className="muted" style={{ fontSize: '0.9rem', margin: '0.2rem 0 0 0' }}>
                Staged files remain locally in your browser until you review and confirm submission.
              </p>
            </div>
            <button
              type="button"
              className="btn-submit-final"
              onClick={handleOpenReviewModal}
            >
              Review & Final Submit
            </button>
          </div>
        </div>
      )}

      {/* REVIEW & CONFIRMATION MODAL (PHASE 5) */}
      {showReviewModal && candDetail && (
        <div className="modal-backdrop">
          <div className="modal-card">
            <div className="modal-header">
              <h3 style={{ margin: 0 }}>Review Placement Document Submission</h3>
              <button
                type="button"
                className="link"
                style={{ fontSize: '1.25rem', color: 'var(--muted)' }}
                onClick={() => !submitting && setShowReviewModal(false)}
                disabled={submitting}
              >
                ✕
              </button>
            </div>

            <div className="modal-body">
              <div style={{ background: 'var(--paper)', padding: '0.75rem 1rem', borderRadius: '6px', border: '1px solid var(--line)' }}>
                <strong>Candidate:</strong> {candDetail.first_name} {candDetail.last_name} (ID: {candDetail.candidate_id})
                <br />
                <span className="muted" style={{ fontSize: '0.88rem' }}>
                  State: {sel.state} · Centre: {lists.tc.find((c) => c.tc_id === sel.tc)?.name || sel.tc} · Batch: {lists.batch.find((b) => b.kb_batch_id === sel.batch)?.batch_code || sel.batch}
                </span>
              </div>

              <div>
                <strong style={{ display: 'block', marginBottom: '0.35rem' }}>1. Appointment / Offer Letter:</strong>
                {stagedAppointment?.file ? (
                  <div style={{ padding: '0.4rem 0.75rem', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '4px', fontSize: '0.9rem' }}>
                    {stagedAppointment.replaceId ? '🔄 Replacement File: ' : '📄 New File: '}
                    <strong>{stagedAppointment.fileName}</strong> ({formatFileSize(stagedAppointment.fileSize)})
                  </div>
                ) : appointmentDoc ? (
                  <div style={{ padding: '0.4rem 0.75rem', background: '#f8fafc', border: '1px solid var(--line)', borderRadius: '4px', fontSize: '0.9rem' }}>
                    ✓ Retaining already verified file: <strong>{appointmentDoc.file_name}</strong>
                  </div>
                ) : (
                  <div style={{ padding: '0.4rem 0.75rem', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '4px', color: 'var(--danger)', fontSize: '0.9rem' }}>
                    Missing appointment letter
                  </div>
                )}
              </div>

              <div>
                <strong style={{ display: 'block', marginBottom: '0.35rem' }}>2. Salary Slips to Submit:</strong>
                {salaryRows.filter((r) => r.file).length === 0 && Object.keys(stagedSalaryReplacements).length === 0 ? (
                  <span className="muted" style={{ fontSize: '0.88rem' }}>
                    (No new salary slips staged; retaining {salarySlips.length} existing verified months)
                  </span>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                    {salaryRows.filter((r) => r.file).map((r) => (
                      <div key={r.id} style={{ padding: '0.35rem 0.6rem', background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: '4px', fontSize: '0.88rem' }}>
                        📅 <strong>{MONTH_NAMES[r.month - 1]} {r.year}:</strong> {r.fileName} ({formatFileSize(r.fileSize)})
                      </div>
                    ))}
                    {Object.entries(stagedSalaryReplacements).filter(([, r]) => r.file).map(([id, r]) => (
                      <div key={id} style={{ padding: '0.35rem 0.6rem', background: '#fffbeb', border: '1px solid #fde68a', borderRadius: '4px', fontSize: '0.88rem' }}>
                        🔄 Replacement for <strong>{MONTH_NAMES[r.month - 1]} {r.year}:</strong> {r.fileName} ({formatFileSize(r.fileSize)})
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <strong style={{ display: 'block', marginBottom: '0.35rem' }}>3. Bank Statements to Submit:</strong>
                {bankRows.filter((r) => r.file).length === 0 && Object.keys(stagedBankReplacements).length === 0 ? (
                  <span className="muted" style={{ fontSize: '0.88rem' }}>
                    (No new bank statements staged; retaining {bankStatements.length} existing verified months)
                  </span>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                    {bankRows.filter((r) => r.file).map((r) => (
                      <div key={r.id} style={{ padding: '0.35rem 0.6rem', background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: '4px', fontSize: '0.88rem' }}>
                        📅 <strong>{MONTH_NAMES[r.month - 1]} {r.year}:</strong> {r.fileName} ({formatFileSize(r.fileSize)})
                      </div>
                    ))}
                    {Object.entries(stagedBankReplacements).filter(([, r]) => r.file).map(([id, r]) => (
                      <div key={id} style={{ padding: '0.35rem 0.6rem', background: '#fffbeb', border: '1px solid #fde68a', borderRadius: '4px', fontSize: '0.88rem' }}>
                        🔄 Replacement for <strong>{MONTH_NAMES[r.month - 1]} {r.year}:</strong> {r.fileName} ({formatFileSize(r.fileSize)})
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="warning" style={{ margin: '0.5rem 0 0 0', fontSize: '0.88rem' }}>
                <strong>Submission Confirmation:</strong>
                <p style={{ margin: '0.2rem 0 0 0' }}>
                  Upon confirmation, these files will be uploaded directly to Google Drive under the candidate's folder hierarchy and recorded in the CPASS database.
                </p>
              </div>
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="btn-secondary"
                disabled={submitting}
                onClick={() => setShowReviewModal(false)}
              >
                Back to Editing
              </button>
              <button
                type="button"
                className="btn-submit-final"
                disabled={submitting}
                onClick={handleFinalSubmit}
              >
                {submitting ? 'Uploading to Drive…' : 'Confirm & Submit'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* SUCCESS POPUP & WORKFLOW RESET (PHASE 7) */}
      {submitSuccessData && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: '520px' }}>
            <div className="modal-header" style={{ background: '#f0fdf4', borderBottom: '1px solid #bbf7d0' }}>
              <h3 style={{ margin: 0, color: '#166534', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                ✓ Submission Complete!
              </h3>
            </div>

            <div className="modal-body">
              <p style={{ margin: 0, fontSize: '0.95rem' }}>
                All staged placement verification documents have been successfully uploaded to Google Drive and registered in the database for:
              </p>

              <div style={{ background: 'var(--paper)', padding: '0.8rem 1rem', borderRadius: '6px', border: '1px solid var(--line)' }}>
                <strong>{submitSuccessData.candidateName}</strong>
                <div className="muted" style={{ fontSize: '0.9rem' }}>
                  Candidate ID: <strong>{submitSuccessData.candidateId}</strong>
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', fontSize: '0.9rem' }}>
                <strong>Saved Package Summary:</strong>
                {submitSuccessData.appointmentUploaded && (
                  <div>✓ Appointment / Offer Letter registered</div>
                )}
                {submitSuccessData.salaryMonths.length > 0 && (
                  <div>
                    ✓ Salary Slips ({submitSuccessData.salaryMonths.length} months): {submitSuccessData.salaryMonths.join(', ')}
                  </div>
                )}
                {submitSuccessData.bankMonths.length > 0 && (
                  <div>
                    ✓ Bank Statements ({submitSuccessData.bankMonths.length} months): {submitSuccessData.bankMonths.join(', ')}
                  </div>
                )}
                <div className="doc-meta" style={{ marginTop: '0.5rem', color: '#166534', fontWeight: 600 }}>
                  Total files uploaded and persisted: {submitSuccessData.totalSubmitted}
                </div>
              </div>
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="btn-submit-final"
                style={{ width: '100%' }}
                onClick={handleCompleteWorkflowReset}
              >
                Done / Reset Workflow
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
