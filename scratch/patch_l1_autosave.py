import sys

path = "frontend/src/pages/L1Home.jsx"
with open(path, "rb") as f:
    raw = f.read()

content = raw.decode("utf-8").replace("\r\n", "\n")

# 1. Add AutosaveIndicator and hasEnteredAuditData before createDefaultEmployer
target_1 = "// -----------------------------------------------------------------------------\n// Placement Audit Default State Creators\n// -----------------------------------------------------------------------------"
rep_1 = """// -----------------------------------------------------------------------------
// Autosave Indicator & State Helpers
// -----------------------------------------------------------------------------
function hasEnteredAuditData(empList, salList) {
  if (Array.isArray(empList)) {
    const hasEmp = empList.some(
      (e) => (e.employer_name && e.employer_name.trim().length > 0) || e.appointment_date || e.designation || e.monthly_ctc
    )
    if (hasEmp) return true
  }
  if (Array.isArray(salList)) {
    const hasSal = salList.some(
      (s) =>
        (s.gross_salary !== '' && s.gross_salary !== null && s.gross_salary !== 0 && s.gross_salary !== '0') ||
        (s.net_salary !== '' && s.net_salary !== null && s.net_salary !== 0 && s.net_salary !== '0') ||
        (s.amount_credited !== '' && s.amount_credited !== null && s.amount_credited !== 0 && s.amount_credited !== '0') ||
        (s.bank_name && s.bank_name.trim().length > 0) ||
        (s.credit_date && s.credit_date.trim().length > 0)
    )
    if (hasSal) return true
  }
  return false
}

function AutosaveIndicator({ status, lastSavedAt, error, onRetry }) {
  if (status === 'idle') return null

  let text = 'All changes saved'
  let badgeClass = 'l1-autosave-badge saved'

  if (status === 'saving') {
    badgeClass = 'l1-autosave-badge saving'
    text = 'Saving changes...'
  } else if (status === 'retrying') {
    badgeClass = 'l1-autosave-badge retrying'
    text = 'Save failed – retrying...'
  } else if (status === 'error') {
    badgeClass = 'l1-autosave-badge error'
    text = 'Save failed'
  } else if (status === 'saved') {
    const timeStr = lastSavedAt
      ? new Date(lastSavedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
      : 'just now'
    text = `All changes saved (${timeStr})`
  }

  return (
    <div className="l1-autosave-container">
      <div className={badgeClass} title={error || text}>
        {status === 'saving' && <span className="l1-autosave-spinner" />}
        {status === 'retrying' && <span className="l1-autosave-pulse" />}
        {status === 'saved' && <span className="l1-autosave-check">✓</span>}
        {status === 'error' && <span className="l1-autosave-err-icon">⚠️</span>}
        <span className="l1-autosave-text">{text}</span>
        {status === 'error' && onRetry && (
          <button type="button" className="l1-autosave-retry-btn" onClick={onRetry}>
            Retry
          </button>
        )}
      </div>
    </div>
  )
}

// -----------------------------------------------------------------------------
// Placement Audit Default State Creators
// -----------------------------------------------------------------------------"""

if target_1 not in content:
    print("Error: target_1 not found")
    sys.exit(1)

content = content.replace(target_1, rep_1, 1)

# 2. Add autosave states and refs inside L1Home
target_2 = "  const [signoffDetails, setSignoffDetails] = useState(createDefaultSignoffs)"
rep_2 = """  const [signoffDetails, setSignoffDetails] = useState(createDefaultSignoffs)

  // Autosave State & References
  const [autosaveStatus, setAutosaveStatus] = useState('idle') // 'idle' | 'saving' | 'saved' | 'retrying' | 'error'
  const [autosaveLastSavedAt, setAutosaveLastSavedAt] = useState(null)
  const [autosaveError, setAutosaveError] = useState('')
  const isDirtyRef = useRef(false)
  const autosaveTimerRef = useRef(null)
  const inFlightSavePromiseRef = useRef(null)
  const saveSeqRef = useRef(0)
  const formStateRef = useRef({})"""

if target_2 not in content:
    print("Error: target_2 not found")
    sys.exit(1)

content = content.replace(target_2, rep_2, 1)

print("Step 1 & 2 applied successfully")
with open(path, "w", encoding="utf-8") as f:
    f.write(content)

