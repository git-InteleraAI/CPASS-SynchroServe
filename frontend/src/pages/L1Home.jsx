import { useEffect, useRef, useState } from 'react'
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
    appointment_letter_status: 'Available',
    appointment_letter_compliant: true,
    appointment_letter_remarks: 'Official appointment / offer letter with designation and compensation structure verified.',
    salary_slips_status: 'Available (3 Months)',
    salary_slips_compliant: true,
    salary_slips_remarks: '3 consecutive monthly salary slips verified against wage criteria.',
    bank_statements_status: 'Available (3 Months)',
    bank_statements_compliant: true,
    bank_statements_remarks: 'Bank credit entries match net salary disbursement amounts.',
    overall_compliance: true,
    remarks: '',
  }
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
  const [activeWorkflowTab, setActiveWorkflowTab] = useState('audit')

  // Placement Audit States
  const [auditRecord, setAuditRecord] = useState(null)
  const [loadingAudit, setLoadingAudit] = useState(false)
  const [auditLoadError, setAuditLoadError] = useState('')
  const [auditSavingDraft, setAuditSavingDraft] = useState(false)
  const [auditSubmitting, setAuditSubmitting] = useState(false)
  const [auditToast, setAuditToast] = useState(null) // { message, type }
  const [auditRemarks, setAuditRemarks] = useState('')

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

  function resetAuditForm() {
    setAuditRecord(null)
    setAuditLoadError('')
    setEmployerList([createDefaultEmployer(null)])
    setSalaryDetailList(createDefaultSalaryList(currentYear))
    setDocumentAudit(createDefaultDocAudit())
    setSignoffDetails(createDefaultSignoffs())
    setAuditRemarks('')
    setStatementModalOpen(false)
    setStatementData(null)
  }

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
    resetAuditForm()
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
            setSalaryDetailList(
              a.salary_details.map((s, idx) => ({
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
            )
          } else {
            setSalaryDetailList(createDefaultSalaryList(currentYear))
          }

          if (a.document_audit) {
            setDocumentAudit((prev) => ({ ...prev, ...a.document_audit }))
          }
          if (a.signoff_details) {
            setSignoffDetails({
              centre_head: { ...createDefaultSignoffs().centre_head, ...(a.signoff_details.centre_head || {}) },
              cops_team: { ...createDefaultSignoffs().cops_team, ...(a.signoff_details.cops_team || {}) },
              business_leader: { ...createDefaultSignoffs().business_leader, ...(a.signoff_details.business_leader || {}) },
            })
          }
          setAuditRemarks(a.remarks || '')
        } else {
          setAuditRecord(null)
          setEmployerList([createDefaultEmployer(detail)])
          setSalaryDetailList(createDefaultSalaryList(currentYear))
          setDocumentAudit(createDefaultDocAudit())
          setSignoffDetails(createDefaultSignoffs())
          setAuditRemarks('')
        }
      })
      .catch((err) => {
        console.warn('Could not load candidate audit:', err)
        setAuditLoadError(err.message || 'Could not load placement audit record.')
        setAuditRecord(null)
        setEmployerList([createDefaultEmployer(detail)])
        setSalaryDetailList(createDefaultSalaryList(currentYear))
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
    const nextMonth = ((salaryDetailList.length) % 12) + 1
    const newRow = {
      id: `sal_${Date.now()}_${Math.random().toString(36).substr(2, 4)}`,
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
  }

  function handleRemoveSalaryRow(id) {
    if (auditRecord?.audit_status === 'SUBMITTED') return
    if (salaryDetailList.length <= 3) {
      setAuditToast({ message: 'At least 3 monthly salary entries are required.', type: 'info' })
      return
    }
    setSalaryDetailList((prev) => prev.filter((s) => s.id !== id))
  }

  function handleUpdateSalaryField(id, field, value) {
    if (auditRecord?.audit_status === 'SUBMITTED') return
    setSalaryDetailList((prev) =>
      prev.map((s) => {
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
    )
  }

  function handleUpdateDocAudit(field, value) {
    if (auditRecord?.audit_status === 'SUBMITTED') return
    setDocumentAudit((prev) => ({ ...prev, [field]: value }))
  }

  function handleUpdateSignoff(official, field, value) {
    if (auditRecord?.audit_status === 'SUBMITTED') return
    setSignoffDetails((prev) => ({
      ...prev,
      [official]: { ...prev[official], [field]: value },
    }))
  }

  // --- Audit Draft & Submit Handlers ---
  async function handleSaveDraft() {
    if (!sel.cand || !candDetail) return
    if (auditLoadError) {
      setError('Cannot save draft while audit record failed to load. Please retry loading first.')
      setAuditToast({ message: 'Cannot save draft: please retry loading first.', type: 'error' })
      return
    }
    if (auditRecord?.audit_status === 'SUBMITTED') {
      setAuditToast({ message: 'This placement audit is already submitted and locked against editing.', type: 'info' })
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
        remarks: auditRemarks || null,
      }

      const res = await api(`/candidates/${sel.cand}/audit/draft`, null, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      setAuditRecord(res.audit)
      setAuditToast({ message: '✓ Draft placement audit saved successfully.', type: 'success' })
    } catch (err) {
      setError(err.message || 'Failed to save audit draft.')
      setAuditToast({ message: err.message || 'Failed to save draft.', type: 'error' })
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

    setAuditSubmitting(true)
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
        remarks: auditRemarks || null,
      }

      const res = await api(`/candidates/${sel.cand}/audit/submit`, null, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      setAuditRecord(res.audit)
      setAuditToast({ message: '✓ Placement Audit Statement submitted successfully!', type: 'success' })
      handleOpenStatementModal()
    } catch (err) {
      setError(err.message || 'Failed to submit placement audit statement.')
      setAuditToast({ message: err.message || 'Submission failed.', type: 'error' })
    } finally {
      setAuditSubmitting(false)
    }
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
          {/* Navigation Tabs: Audit Statement vs Document Upload Workspaces */}
          <div className="l1-workflow-nav-tabs l1-no-print">
            <button
              type="button"
              className={`l1-workflow-tab ${activeWorkflowTab === 'audit' ? 'active' : ''}`}
              onClick={() => setActiveWorkflowTab('audit')}
            >
              <div className="l1-tab-icon">📋</div>
              <div className="l1-tab-text">
                <strong>Placement Audit &amp; Sign-off Statement</strong>
                <small>
                  {auditRecord
                    ? `Status: ${auditRecord.audit_status} (${auditRecord.audit_status === 'SUBMITTED' ? 'Locked' : 'Draft'})`
                    : 'Employer, salary, document audit & sign-offs'}
                </small>
              </div>
            </button>

            <button
              type="button"
              className={`l1-workflow-tab ${activeWorkflowTab === 'docs' ? 'active' : ''}`}
              onClick={() => setActiveWorkflowTab('docs')}
            >
              <div className="l1-tab-icon">📁</div>
              <div className="l1-tab-text">
                <strong>Document Upload Workspaces</strong>
                <small>
                  {totalStagedFiles > 0
                    ? `${totalStagedFiles} staged ${totalStagedFiles === 1 ? 'file' : 'files'} pending upload`
                    : allRequirementsSatisfied ? 'All mandatory files verified' : 'Upload appointment letter, salary slips, bank statements'}
                </small>
              </div>
            </button>
          </div>

          {/* ================================================================
             WORKFLOW TAB 1: PLACEMENT AUDIT & SIGN-OFF STATEMENT
             ================================================================ */}
          {activeWorkflowTab === 'audit' && (
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
                        <span>📄</span> {loadingStatement ? 'Loading...' : 'View Statement'}
                      </button>
                    )}
                    {!isAuditSubmitted && (
                      <>
                        <button
                          type="button"
                          className="l1-btn-secondary"
                          onClick={handleSaveDraft}
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
                          {auditSubmitting ? 'Submitting...' : 'Submit Statement →'}
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

                    {/* Section 1: Candidate Dossier Summary Card */}
                    <div className="l1-audit-card">
                      <div className="l1-audit-card-header">
                        <div className="l1-audit-card-title">
                          <span style={{ fontSize: '20px' }}>👤</span>
                          <div>
                            <h3>1. Candidate Placement Dossier</h3>
                            <p>Verified candidate registration and batch allocation records from DDU-GKY Master</p>
                          </div>
                        </div>
                        <span className="l1-status-pill info">Read-only Master Data</span>
                      </div>

                      <div className="cpass-dossier-grid">
                        <div className="cpass-dossier-item">
                          <span className="k">Candidate Name</span>
                          <span className="v">{name(candDetail)}</span>
                        </div>
                        <div className="cpass-dossier-item">
                          <span className="k">Candidate ID</span>
                          <span className="v">{candDetail?.candidate_id || sel.cand}</span>
                        </div>
                        <div className="cpass-dossier-item">
                          <span className="k">Aadhaar (Last 4)</span>
                          <span className="v">
                            {candDetail?.aadhaar_number ? `XXXX-XXXX-${String(candDetail.aadhaar_number).slice(-4)}` : 'N/A'}
                          </span>
                        </div>
                        <div className="cpass-dossier-item">
                          <span className="k">Father's Name</span>
                          <span className="v">{candDetail?.father_name || 'N/A'}</span>
                        </div>
                        <div className="cpass-dossier-item">
                          <span className="k">Training Centre</span>
                          <span className="v">{lists.tc.find((c) => c.tc_id === sel.tc)?.name || sel.tc || 'N/A'}</span>
                        </div>
                        <div className="cpass-dossier-item">
                          <span className="k">Sanction Order</span>
                          <span className="v">{sel.order || 'N/A'}</span>
                        </div>
                        <div className="cpass-dossier-item">
                          <span className="k">Batch Code</span>
                          <span className="v">{lists.batch.find((b) => b.kb_batch_id === sel.batch)?.batch_code || sel.batch || 'N/A'}</span>
                        </div>
                        <div className="cpass-dossier-item">
                          <span className="k">Mobile Number</span>
                          <span className="v">{candDetail?.mobile || 'N/A'}</span>
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

                <div className="l1-table-responsive">
                  <table className="l1-audit-table">
                    <thead>
                      <tr>
                        <th style={{ width: '110px' }}>Month</th>
                        <th style={{ width: '90px' }}>Year</th>
                        <th style={{ width: '80px' }}>Work Days</th>
                        <th style={{ width: '80px' }}>Pay Days</th>
                        <th style={{ width: '80px' }}>Leave Days</th>
                        <th style={{ width: '130px' }}>Credit Date</th>
                        <th style={{ width: '110px' }}>Gross (₹)</th>
                        <th style={{ width: '100px' }}>Deductions (₹)</th>
                        <th style={{ width: '110px' }}>Net (₹)</th>
                        <th style={{ width: '110px' }}>Credited (₹)</th>
                        <th>Bank Name</th>
                        {!isAuditSubmitted && salaryDetailList.length > 3 && <th style={{ width: '50px' }}>Action</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {salaryDetailList.map((sal, idx) => (
                        <tr key={sal.id || idx}>
                          <td>
                            <select
                              value={sal.month || 1}
                              onChange={(e) => handleUpdateSalaryField(sal.id, 'month', parseInt(e.target.value, 10))}
                              disabled={isAuditSubmitted}
                            >
                              <option value={1}>01 - Jan</option>
                              <option value={2}>02 - Feb</option>
                              <option value={3}>03 - Mar</option>
                              <option value={4}>04 - Apr</option>
                              <option value={5}>05 - May</option>
                              <option value={6}>06 - Jun</option>
                              <option value={7}>07 - Jul</option>
                              <option value={8}>08 - Aug</option>
                              <option value={9}>09 - Sep</option>
                              <option value={10}>10 - Oct</option>
                              <option value={11}>11 - Nov</option>
                              <option value={12}>12 - Dec</option>
                            </select>
                          </td>
                          <td>
                            <input
                              type="number"
                              min="2020"
                              max="2030"
                              value={sal.year || 2024}
                              onChange={(e) => handleUpdateSalaryField(sal.id, 'year', parseInt(e.target.value, 10))}
                              disabled={isAuditSubmitted}
                            />
                          </td>
                          <td>
                            <input
                              type="number"
                              placeholder="26"
                              min="0"
                              max="31"
                              value={sal.working_days ?? ''}
                              onChange={(e) => handleUpdateSalaryField(sal.id, 'working_days', e.target.value)}
                              disabled={isAuditSubmitted}
                            />
                          </td>
                          <td>
                            <input
                              type="number"
                              placeholder="26"
                              min="0"
                              max="31"
                              value={sal.pay_days ?? ''}
                              onChange={(e) => handleUpdateSalaryField(sal.id, 'pay_days', e.target.value)}
                              disabled={isAuditSubmitted}
                            />
                          </td>
                          <td>
                            <input
                              type="number"
                              placeholder="0"
                              min="0"
                              max="31"
                              value={sal.leave_days ?? ''}
                              onChange={(e) => handleUpdateSalaryField(sal.id, 'leave_days', e.target.value)}
                              disabled={isAuditSubmitted}
                            />
                          </td>
                          <td>
                            <input
                              type="date"
                              value={sal.credit_date || ''}
                              onChange={(e) => handleUpdateSalaryField(sal.id, 'credit_date', e.target.value)}
                              disabled={isAuditSubmitted}
                            />
                          </td>
                          <td>
                            <input
                              type="number"
                              placeholder="0"
                              min="0"
                              value={sal.gross_salary ?? ''}
                              onChange={(e) => handleUpdateSalaryField(sal.id, 'gross_salary', e.target.value)}
                              disabled={isAuditSubmitted}
                            />
                          </td>
                          <td>
                            <input
                              type="number"
                              placeholder="0"
                              min="0"
                              value={sal.deductions ?? ''}
                              onChange={(e) => handleUpdateSalaryField(sal.id, 'deductions', e.target.value)}
                              disabled={isAuditSubmitted}
                            />
                          </td>
                          <td>
                            <input
                              type="number"
                              placeholder="0"
                              min="0"
                              value={sal.net_salary ?? ''}
                              onChange={(e) => handleUpdateSalaryField(sal.id, 'net_salary', e.target.value)}
                              disabled={isAuditSubmitted}
                            />
                          </td>
                          <td>
                            <input
                              type="number"
                              placeholder="0"
                              min="0"
                              value={sal.amount_credited ?? ''}
                              onChange={(e) => handleUpdateSalaryField(sal.id, 'amount_credited', e.target.value)}
                              disabled={isAuditSubmitted}
                            />
                          </td>
                          <td>
                            <input
                              type="text"
                              placeholder="e.g. SBI, HDFC"
                              value={sal.bank_name || ''}
                              onChange={(e) => handleUpdateSalaryField(sal.id, 'bank_name', e.target.value)}
                              disabled={isAuditSubmitted}
                            />
                          </td>
                          {!isAuditSubmitted && salaryDetailList.length > 3 && (
                            <td style={{ textAlign: 'center' }}>
                              <button
                                type="button"
                                onClick={() => handleRemoveSalaryRow(sal.id)}
                                title="Remove Month"
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

              {/* Section 4: Document Verification & Criteria Compliance Audit */}
              <div className="l1-audit-card">
                <div className="l1-audit-card-header">
                  <div className="l1-audit-card-title">
                    <span style={{ fontSize: '20px' }}>📑</span>
                    <div>
                      <h3>4. Document Evidence &amp; Compliance Audit</h3>
                      <p>Verification of candidate placement evidence (AL/OL, PS1-PS3, BS1-BS3) against audit criteria</p>
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
                        <th style={{ width: '170px' }}>Criteria Compliance</th>
                        <th style={{ width: '170px' }}>Repository Link</th>
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
                      ].map((item, idx) => {
                        const entry = documentAudit[item.key] || { available: 'Yes', compliance: 'Compliant', remarks: '' }
                        const hasDriveDoc = !!item.fileDoc
                        const hasStaged = !!item.staged
                        return (
                          <tr key={idx}>
                            <td><strong>{item.code}</strong></td>
                            <td>{item.label}</td>
                            <td>
                              <select
                                value={entry.available || 'Yes'}
                                onChange={(e) => handleUpdateDocAudit(item.key, 'available', e.target.value)}
                                disabled={isAuditSubmitted}
                              >
                                <option value="Yes">Yes</option>
                                <option value="No">No</option>
                                <option value="Pending">Pending</option>
                              </select>
                            </td>
                            <td>
                              <select
                                value={entry.compliance || 'Compliant'}
                                onChange={(e) => handleUpdateDocAudit(item.key, 'compliance', e.target.value)}
                                disabled={isAuditSubmitted}
                              >
                                <option value="Compliant">Compliant</option>
                                <option value="Non-Compliant">Non-Compliant</option>
                                <option value="Under Verification">Under Verification</option>
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
              <div className="l1-audit-card">
                <div className="l1-audit-card-header">
                  <div className="l1-audit-card-title">
                    <span style={{ fontSize: '20px' }}>✍️</span>
                    <div>
                      <h3>5. Authorizations &amp; Sign-off Endorsements</h3>
                      <p>Sign-offs and recommendation statements from Centre Head, COPS Team, and Business Leader</p>
                    </div>
                  </div>
                  <span className="l1-status-pill info">Corporate Endorsements</span>
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
                          onChange={(e) => handleUpdateSignoff('centre_head', 'recommended', e.target.checked)}
                          disabled={isAuditSubmitted}
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
                        onChange={(e) => handleUpdateSignoff('centre_head', 'name', e.target.value)}
                        disabled={isAuditSubmitted}
                      />
                    </div>
                    <div className="l1-field-group">
                      <label>Verification Date</label>
                      <input
                        type="date"
                        value={signoffDetails.centre_head?.date || ''}
                        onChange={(e) => handleUpdateSignoff('centre_head', 'date', e.target.value)}
                        disabled={isAuditSubmitted}
                      />
                    </div>
                    <div className="l1-field-group">
                      <label>Remarks</label>
                      <input
                        type="text"
                        placeholder="e.g. Dossier physically verified"
                        value={signoffDetails.centre_head?.remarks || ''}
                        onChange={(e) => handleUpdateSignoff('centre_head', 'remarks', e.target.value)}
                        disabled={isAuditSubmitted}
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
                          onChange={(e) => handleUpdateSignoff('cops_team', 'verified', e.target.checked)}
                          disabled={isAuditSubmitted}
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
                        onChange={(e) => handleUpdateSignoff('cops_team', 'name', e.target.value)}
                        disabled={isAuditSubmitted}
                      />
                    </div>
                    <div className="l1-field-group">
                      <label>Audit Date</label>
                      <input
                        type="date"
                        value={signoffDetails.cops_team?.date || ''}
                        onChange={(e) => handleUpdateSignoff('cops_team', 'date', e.target.value)}
                        disabled={isAuditSubmitted}
                      />
                    </div>
                    <div className="l1-field-group">
                      <label>Remarks</label>
                      <input
                        type="text"
                        placeholder="e.g. Salary credits verified"
                        value={signoffDetails.cops_team?.remarks || ''}
                        onChange={(e) => handleUpdateSignoff('cops_team', 'remarks', e.target.value)}
                        disabled={isAuditSubmitted}
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
                          onChange={(e) => handleUpdateSignoff('business_leader', 'approved', e.target.checked)}
                          disabled={isAuditSubmitted}
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
                        onChange={(e) => handleUpdateSignoff('business_leader', 'name', e.target.value)}
                        disabled={isAuditSubmitted}
                      />
                    </div>
                    <div className="l1-field-group">
                      <label>Approval Date</label>
                      <input
                        type="date"
                        value={signoffDetails.business_leader?.date || ''}
                        onChange={(e) => handleUpdateSignoff('business_leader', 'date', e.target.value)}
                        disabled={isAuditSubmitted}
                      />
                    </div>
                    <div className="l1-field-group">
                      <label>Remarks</label>
                      <input
                        type="text"
                        placeholder="e.g. Placement compliance approved"
                        value={signoffDetails.business_leader?.remarks || ''}
                        onChange={(e) => handleUpdateSignoff('business_leader', 'remarks', e.target.value)}
                        disabled={isAuditSubmitted}
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* Section 6: Overall Remarks Card */}
              <div className="l1-audit-card">
                <div className="l1-audit-card-header">
                  <div className="l1-audit-card-title">
                    <span style={{ fontSize: '20px' }}>📝</span>
                    <div>
                      <h3>6. Overall Audit Remarks &amp; Observations</h3>
                      <p>Optional compliance notes or exceptional observations for this candidate's placement audit</p>
                    </div>
                  </div>
                </div>
                <div className="l1-field-group">
                  <textarea
                    rows={3}
                    placeholder="Enter any additional audit remarks or observations..."
                    value={auditRemarks}
                    onChange={(e) => setAuditRemarks(e.target.value)}
                    disabled={isAuditSubmitted}
                  />
                </div>
              </div>
                  </>
                )}

              {/* Sticky Bottom Action Dock for Audit */}
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
                <div style={{ display: 'flex', gap: '10px' }}>
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
                        onClick={handleSaveDraft}
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
                        {auditSubmitting ? 'Submitting...' : 'Submit Placement Statement →'}
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          </ErrorBoundary>
          )}

          {/* ================================================================
             WORKFLOW TAB 2: DOCUMENT UPLOADS & STAGING WORKSPACES
             ================================================================ */}
          {activeWorkflowTab === 'docs' && (
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

      {/* ====================================================================
         C-PASS CANDIDATE PLACEMENT AUDIT & SIGN-OFF STATEMENT MODAL
         ==================================================================== */}
      {statementModalOpen && statementData && (
        <PlacementAuditStatement
          statementData={statementData}
          showModalWrapper={true}
          onClose={() => setStatementModalOpen(false)}
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
