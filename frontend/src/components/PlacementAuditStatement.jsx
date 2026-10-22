import { useMemo } from 'react'
import synchroLogo from '../../assets/SynchroServeLogo.png'

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
]

export default function PlacementAuditStatement({
  statementData,
  isEditMode = false,
  editedData = null,
  onUpdateEmployer = () => {},
  onAddEmployer = () => {},
  onRemoveEmployer = () => {},
  onUpdateSalary = () => {},
  onAddSalary = () => {},
  onRemoveSalary = () => {},
  onUpdateSignoff = () => {},
  onUpdateRemarks = () => {},
  l1OriginalData = null,
  showModalWrapper = false,
  onClose = () => {},
  extraHeaderActions = null,
  hasUnsavedChanges = false,
}) {
  if (!statementData) return null

  const auditStatus = statementData.audit_status || statementData.audit?.audit_status || 'DRAFT'
  const cpassStatus = statementData.cpass_status || statementData.audit?.cpass_status || (auditStatus === 'SUBMITTED' ? 'VERIFIED' : 'Under Audit')
  const finalizedAt = statementData.finalized_at || statementData.audit?.finalized_at
  const cand = statementData.candidate || {}
  const candName = cand.candidate_name || cand.full_name || `${cand.first_name || ''} ${cand.last_name || ''}`.trim() || 'N/A'
  const aadhaarDisplay = cand.masked_aadhaar || (cand.aadhaar_last4 ? `XXXX-XXXX-${cand.aadhaar_last4}` : (cand.aadhaar_number || 'Not Available'))

  // Use edited data if in edit mode, otherwise use saved statement data
  const currentEmployers = isEditMode && editedData?.employer_details
    ? editedData.employer_details
    : (statementData.employer_details || statementData.audit?.employer_details || [])

  const currentSalaries = isEditMode && editedData?.salary_details
    ? editedData.salary_details
    : (statementData.salary_details || statementData.audit?.salary_details || [])

  const currentSignoffs = isEditMode && editedData?.signoff_details
    ? editedData.signoff_details
    : (statementData.signoff_details || statementData.audit?.signoff_details || {})

  const currentRemarks = isEditMode && editedData?.remarks !== undefined
    ? editedData.remarks
    : (statementData.remarks || statementData.audit?.remarks || '')

  // Calculate live salary summary totals
  const salarySummary = useMemo(() => {
    if (isEditMode && editedData?.salary_details) {
      const rows = editedData.salary_details
      const total_credited = rows.reduce((sum, s) => sum + (Number(s.amount_credited) || 0), 0)
      const total_gross = rows.reduce((sum, s) => sum + (Number(s.gross_salary) || 0), 0)
      const total_deductions = rows.reduce((sum, s) => sum + (Number(s.deductions) || 0), 0)
      const total_net = rows.reduce((sum, s) => sum + (Number(s.net_salary) || 0), 0)
      const avg_gross = rows.length > 0 ? total_gross / rows.length : 0
      return {
        total_credited,
        total_gross,
        total_deductions,
        total_net,
        average_gross: avg_gross,
        average_monthly_gross: avg_gross,
        month_count: rows.length,
      }
    }
    return statementData.salary_summary || {}
  }, [isEditMode, editedData, statementData])

  // Document evidence rows
  const docList = statementData.documents || statementData.uploaded_documents || []
  const evidenceRows = statementData.document_evidence || [
    {
      code: 'AL / OL',
      label: 'Appointment / Offer Letter',
      key: 'appointment_letter',
      fallbackDoc: docList.find(d => d.document_type === 'APPOINTMENT_LETTER' && d.upload_status === 'SUCCESS'),
    },
    {
      code: 'PS 1',
      label: currentSalaries[0]?.month ? `Salary Pay Slip — ${MONTH_NAMES[currentSalaries[0].month - 1]} ${currentSalaries[0].year || ''}` : 'Salary Pay Slip — Month 1',
      key: 'salary_slip_1',
      fallbackDoc: docList.find(d => d.document_type === 'SALARY_SLIP' && d.upload_status === 'SUCCESS' && (currentSalaries[0] ? (d.reporting_year === currentSalaries[0].year && d.reporting_month === currentSalaries[0].month) : d.reporting_month === 1)),
    },
    {
      code: 'PS 2',
      label: currentSalaries[1]?.month ? `Salary Pay Slip — ${MONTH_NAMES[currentSalaries[1].month - 1]} ${currentSalaries[1].year || ''}` : 'Salary Pay Slip — Month 2',
      key: 'salary_slip_2',
      fallbackDoc: docList.find(d => d.document_type === 'SALARY_SLIP' && d.upload_status === 'SUCCESS' && (currentSalaries[1] ? (d.reporting_year === currentSalaries[1].year && d.reporting_month === currentSalaries[1].month) : d.reporting_month === 2)),
    },
    {
      code: 'PS 3',
      label: currentSalaries[2]?.month ? `Salary Pay Slip — ${MONTH_NAMES[currentSalaries[2].month - 1]} ${currentSalaries[2].year || ''}` : 'Salary Pay Slip — Month 3',
      key: 'salary_slip_3',
      fallbackDoc: docList.find(d => d.document_type === 'SALARY_SLIP' && d.upload_status === 'SUCCESS' && (currentSalaries[2] ? (d.reporting_year === currentSalaries[2].year && d.reporting_month === currentSalaries[2].month) : d.reporting_month === 3)),
    },
    {
      code: 'BS 1',
      label: currentSalaries[0]?.month ? `Bank Statement / Passbook — ${MONTH_NAMES[currentSalaries[0].month - 1]} ${currentSalaries[0].year || ''}` : 'Bank Statement / Passbook — Month 1',
      key: 'bank_statement_1',
      fallbackDoc: docList.find(d => d.document_type === 'BANK_STATEMENT' && d.upload_status === 'SUCCESS' && (currentSalaries[0] ? (d.reporting_year === currentSalaries[0].year && d.reporting_month === currentSalaries[0].month) : d.reporting_month === 1)),
    },
    {
      code: 'BS 2',
      label: currentSalaries[1]?.month ? `Bank Statement / Passbook — ${MONTH_NAMES[currentSalaries[1].month - 1]} ${currentSalaries[1].year || ''}` : 'Bank Statement / Passbook — Month 2',
      key: 'bank_statement_2',
      fallbackDoc: docList.find(d => d.document_type === 'BANK_STATEMENT' && d.upload_status === 'SUCCESS' && (currentSalaries[1] ? (d.reporting_year === currentSalaries[1].year && d.reporting_month === currentSalaries[1].month) : d.reporting_month === 2)),
    },
    {
      code: 'BS 3',
      label: currentSalaries[2]?.month ? `Bank Statement / Passbook — ${MONTH_NAMES[currentSalaries[2].month - 1]} ${currentSalaries[2].year || ''}` : 'Bank Statement / Passbook — Month 3',
      key: 'bank_statement_3',
      fallbackDoc: docList.find(d => d.document_type === 'BANK_STATEMENT' && d.upload_status === 'SUCCESS' && (currentSalaries[2] ? (d.reporting_year === currentSalaries[2].year && d.reporting_month === currentSalaries[2].month) : d.reporting_month === 3)),
    },
  ].map(item => ({
    code: item.code,
    label: item.label,
    available: !!item.fallbackDoc,
    compliance: item.fallbackDoc ? 'Compliant' : 'Missing / Non-Compliant',
    repository_status: item.fallbackDoc ? `Stored in Drive: ${item.fallbackDoc.file_name}` : 'No verified file in database',
    observations: item.fallbackDoc ? 'Verified during placement audit' : 'Pending upload and verification',
  }))

  // Helper to check if a field was changed relative to L1 original submission
  const isChangedFromL1 = (section, idx, field, currentVal) => {
    if (!l1OriginalData) return false
    const origSection = l1OriginalData[section]
    if (!Array.isArray(origSection) || !origSection[idx]) return false
    const origVal = origSection[idx][field]
    return origVal !== undefined && String(origVal) !== String(currentVal)
  }

  const sheetContent = (
    <div className={`cpass-statement-sheet ${isEditMode ? 'cpass-statement-editing' : ''}`}>
      {/* Edit Mode Notice Banner */}
      {isEditMode && (
        <div className="l1-no-print" style={{ marginBottom: '14px', padding: '10px 14px', background: '#FEF3C7', border: '1px solid #F59E0B', borderRadius: '6px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '16px' }}>✏️</span>
            <span style={{ fontSize: '13px', fontWeight: 600, color: '#92400E' }}>
              Statement Edit Mode Active — Edit placement or salary data. L1 original values are preserved in history.
            </span>
          </div>
          {hasUnsavedChanges && (
            <span style={{ fontSize: '11px', background: '#DC2626', color: '#fff', padding: '2px 8px', borderRadius: '4px', fontWeight: 700 }}>
              Unsaved Changes
            </span>
          )}
        </div>
      )}

      {/* Header */}
      <div className="cpass-statement-header">
        <div className="cpass-header-logo">
          <img src={synchroLogo} alt="SynchroServe Logo" />
        </div>
        <div className="cpass-header-title">
          <h2>SYNCHROSERVE GLOBAL SOLUTIONS PRIVATE LIMITED</h2>
          <h4>C-PASS CANDIDATE PLACEMENT AUDIT &amp; SIGN-OFF STATEMENT</h4>
          <p>Deen Dayal Upadhyaya Grameen Kaushalya Yojana (DDU-GKY) Verification Record</p>
        </div>
        <div className="cpass-header-meta">
          <div><strong>Doc Ref:</strong> CPASS-AUD-{cand.candidate_id || cand.id || 'REF'}</div>
          <div><strong>Date:</strong> {statementData.generated_at ? new Date(statementData.generated_at).toLocaleDateString('en-IN') : new Date().toLocaleDateString('en-IN')}</div>
          <div>
            <strong>Status:</strong>{' '}
            <span style={{ color: cpassStatus === 'L2_APPROVED' ? '#166534' : auditStatus === 'SUBMITTED' ? '#1E40AF' : '#D97706', fontWeight: 700 }}>
              {cpassStatus === 'L2_APPROVED' ? 'L2 APPROVED' : auditStatus}
            </span>
          </div>
        </div>
      </div>

      {/* Section 1: Candidate Dossier */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h5 className="cpass-statement-section-title">1. Candidate Dossier &amp; Training Details</h5>
          {isEditMode && (
            <span style={{ fontSize: '11px', color: '#6B7280', fontStyle: 'italic' }}>
              🔒 Master Record (Read-Only)
            </span>
          )}
        </div>
        <div className="cpass-dossier-grid">
          <div className="cpass-dossier-item">
            <span className="k">Candidate Name</span>
            <span className="v">{candName}</span>
          </div>
          <div className="cpass-dossier-item">
            <span className="k">Candidate ID</span>
            <span className="v">{cand.candidate_id || cand.id || 'N/A'}</span>
          </div>
          <div className="cpass-dossier-item">
            <span className="k">Aadhaar (Last 4)</span>
            <span className="v">{aadhaarDisplay}</span>
          </div>
          <div className="cpass-dossier-item">
            <span className="k">Father's Name</span>
            <span className="v">{cand.father_name || 'N/A'}</span>
          </div>
          <div className="cpass-dossier-item">
            <span className="k">Training Centre</span>
            <span className="v">{cand.training_centre || cand.training_centre_name || cand.tc_name || 'N/A'}</span>
          </div>
          <div className="cpass-dossier-item">
            <span className="k">Trade / Course</span>
            <span className="v">{cand.trade_name || cand.trade || cand.sector_name || cand.sector || 'N/A'}</span>
          </div>
          <div className="cpass-dossier-item">
            <span className="k">Contact Number</span>
            <span className="v">{cand.contact_number || cand.mobile || 'N/A'}</span>
          </div>
          <div className="cpass-dossier-item">
            <span className="k">Sanction Order</span>
            <span className="v">{cand.sanction_order || cand.sanction_order_name || 'N/A'}</span>
          </div>
          <div className="cpass-dossier-item">
            <span className="k">Batch ID / Code</span>
            <span className="v">{cand.batch_code || cand.batch_id || 'N/A'}</span>
          </div>
          <div className="cpass-dossier-item">
            <span className="k">State</span>
            <span className="v">{cand.state || 'N/A'}</span>
          </div>
          <div className="cpass-dossier-item">
            <span className="k">CPASS Status</span>
            <span className="v" style={{ fontWeight: 700, color: cpassStatus === 'L2_APPROVED' ? '#166534' : undefined }}>
              {cpassStatus}
            </span>
          </div>
          <div className="cpass-dossier-item">
            <span className="k">Audit Finalized At</span>
            <span className="v">{finalizedAt ? new Date(finalizedAt).toLocaleDateString('en-IN') : (auditStatus === 'SUBMITTED' ? new Date().toLocaleDateString('en-IN') : 'Pending Final Submission')}</span>
          </div>
        </div>
      </div>

      {/* Section 2: Employer Details */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h5 className="cpass-statement-section-title">2. Placement &amp; Employer Information</h5>
          {isEditMode && currentEmployers.length < 5 && (
            <button
              type="button"
              className="l1-btn-add-slot l1-no-print"
              onClick={onAddEmployer}
              style={{ width: 'auto', padding: '4px 10px', fontSize: '12px' }}
            >
              + Add Employer
            </button>
          )}
        </div>
        <table className="cpass-doc-table">
          <thead>
            <tr>
              <th style={{ width: '36px' }}>#</th>
              <th>Employer Name</th>
              <th style={{ width: '100px' }}>Months Worked</th>
              <th style={{ width: '120px' }}>Appointment Date</th>
              <th>Designation</th>
              <th>Place of Work</th>
              <th style={{ width: '110px' }}>Monthly CTC (₹)</th>
              <th style={{ width: '110px' }}>Minimum Wages (₹)</th>
              {isEditMode && currentEmployers.length > 1 && <th className="l1-no-print" style={{ width: '40px' }}>Action</th>}
            </tr>
          </thead>
          <tbody>
            {currentEmployers.map((emp, idx) => (
              <tr key={emp.id || idx}>
                <td>{idx + 1}</td>
                {isEditMode ? (
                  <>
                    <td>
                      <input
                        type="text"
                        className={`l1-edit-cell ${isChangedFromL1('employer_details', idx, 'employer_name', emp.employer_name) ? 'modified-field' : ''}`}
                        placeholder="Employer Name *"
                        value={emp.employer_name || ''}
                        onChange={(e) => onUpdateEmployer(emp.id || idx, 'employer_name', e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        step="0.5"
                        min="0"
                        className={`l1-edit-cell ${isChangedFromL1('employer_details', idx, 'months_worked', emp.months_worked) ? 'modified-field' : ''}`}
                        value={emp.months_worked ?? ''}
                        onChange={(e) => onUpdateEmployer(emp.id || idx, 'months_worked', e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        type="date"
                        className={`l1-edit-cell ${isChangedFromL1('employer_details', idx, 'appointment_date', emp.appointment_date) ? 'modified-field' : ''}`}
                        value={emp.appointment_date || ''}
                        onChange={(e) => onUpdateEmployer(emp.id || idx, 'appointment_date', e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        type="text"
                        className={`l1-edit-cell ${isChangedFromL1('employer_details', idx, 'designation', emp.designation) ? 'modified-field' : ''}`}
                        placeholder="Designation"
                        value={emp.designation || ''}
                        onChange={(e) => onUpdateEmployer(emp.id || idx, 'designation', e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        type="text"
                        className={`l1-edit-cell ${isChangedFromL1('employer_details', idx, 'place_of_work', emp.place_of_work) ? 'modified-field' : ''}`}
                        placeholder="Location"
                        value={emp.place_of_work || ''}
                        onChange={(e) => onUpdateEmployer(emp.id || idx, 'place_of_work', e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        min="0"
                        className={`l1-edit-cell ${isChangedFromL1('employer_details', idx, 'monthly_ctc', emp.monthly_ctc) ? 'modified-field' : ''}`}
                        value={emp.monthly_ctc ?? ''}
                        onChange={(e) => onUpdateEmployer(emp.id || idx, 'monthly_ctc', e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        min="0"
                        className={`l1-edit-cell ${isChangedFromL1('employer_details', idx, 'minimum_wages', emp.minimum_wages) ? 'modified-field' : ''}`}
                        value={emp.minimum_wages ?? ''}
                        onChange={(e) => onUpdateEmployer(emp.id || idx, 'minimum_wages', e.target.value)}
                      />
                    </td>
                    {currentEmployers.length > 1 && (
                      <td className="l1-no-print" style={{ textAlign: 'center' }}>
                        <button
                          type="button"
                          onClick={() => onRemoveEmployer(emp.id || idx)}
                          title="Remove Employer"
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#DC2626' }}
                        >
                          🗑️
                        </button>
                      </td>
                    )}
                  </>
                ) : (
                  <>
                    <td><strong>{emp.employer_name || '—'}</strong></td>
                    <td>{emp.months_worked ?? '—'}</td>
                    <td>{emp.appointment_date || '—'}</td>
                    <td>{emp.designation || '—'}</td>
                    <td>{emp.place_of_work || '—'}</td>
                    <td>{emp.monthly_ctc ? `₹${Number(emp.monthly_ctc).toLocaleString('en-IN')}` : '—'}</td>
                    <td>{emp.minimum_wages ? `₹${Number(emp.minimum_wages).toLocaleString('en-IN')}` : '—'}</td>
                  </>
                )}
              </tr>
            ))}
            {currentEmployers.length === 0 && (
              <tr>
                <td colSpan={isEditMode ? 9 : 8} style={{ textAlign: 'center', color: '#6B7280', padding: '14px' }}>
                  No employer records recorded.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Section 3: Salary Disbursement Record */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h5 className="cpass-statement-section-title">3. Monthly Salary Disbursement Record</h5>
          {isEditMode && currentSalaries.length < 12 && (
            <button
              type="button"
              className="l1-btn-add-slot l1-no-print"
              onClick={onAddSalary}
              style={{ width: 'auto', padding: '4px 10px', fontSize: '12px' }}
            >
              + Add Month
            </button>
          )}
        </div>
        <table className="cpass-doc-table">
          <thead>
            <tr>
              <th style={{ width: '130px' }}>Reporting Month</th>
              <th style={{ width: '60px' }}>Work</th>
              <th style={{ width: '60px' }}>Pay</th>
              <th style={{ width: '60px' }}>Leave</th>
              <th style={{ width: '110px' }}>Credit Date</th>
              <th style={{ width: '90px' }}>Gross (₹)</th>
              <th style={{ width: '85px' }}>Deductions</th>
              <th style={{ width: '90px' }}>Net (₹)</th>
              <th style={{ width: '90px' }}>Credited (₹)</th>
              <th>Bank Name</th>
              {isEditMode && currentSalaries.length > 3 && <th className="l1-no-print" style={{ width: '36px' }}>Action</th>}
            </tr>
          </thead>
          <tbody>
            {currentSalaries.map((sal, idx) => (
              <tr key={sal.id || idx}>
                {isEditMode ? (
                  <>
                    <td>
                      <div style={{ display: 'flex', gap: '4px' }}>
                        <select
                          className="l1-edit-cell"
                          value={sal.month || 1}
                          onChange={(e) => onUpdateSalary(sal.id || idx, 'month', parseInt(e.target.value, 10))}
                        >
                          {MONTH_NAMES.map((m, mIdx) => (
                            <option key={mIdx + 1} value={mIdx + 1}>{m.slice(0, 3)}</option>
                          ))}
                        </select>
                        <input
                          type="number"
                          className="l1-edit-cell"
                          style={{ width: '60px' }}
                          value={sal.year || 2026}
                          onChange={(e) => onUpdateSalary(sal.id || idx, 'year', parseInt(e.target.value, 10))}
                        />
                      </div>
                    </td>
                    <td>
                      <input
                        type="number"
                        min="0"
                        max="31"
                        className="l1-edit-cell"
                        value={sal.working_days ?? ''}
                        onChange={(e) => onUpdateSalary(sal.id || idx, 'working_days', e.target.value ? parseInt(e.target.value, 10) : '')}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        min="0"
                        max="31"
                        className="l1-edit-cell"
                        value={sal.pay_days ?? ''}
                        onChange={(e) => onUpdateSalary(sal.id || idx, 'pay_days', e.target.value ? parseInt(e.target.value, 10) : '')}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        min="0"
                        max="31"
                        className="l1-edit-cell"
                        value={sal.leave_days ?? ''}
                        onChange={(e) => onUpdateSalary(sal.id || idx, 'leave_days', e.target.value ? parseInt(e.target.value, 10) : '')}
                      />
                    </td>
                    <td>
                      <input
                        type="date"
                        className="l1-edit-cell"
                        value={sal.credit_date || ''}
                        onChange={(e) => onUpdateSalary(sal.id || idx, 'credit_date', e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        min="0"
                        className="l1-edit-cell"
                        value={sal.gross_salary ?? ''}
                        onChange={(e) => onUpdateSalary(sal.id || idx, 'gross_salary', e.target.value ? parseFloat(e.target.value) : '')}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        min="0"
                        className="l1-edit-cell"
                        value={sal.deductions ?? ''}
                        onChange={(e) => onUpdateSalary(sal.id || idx, 'deductions', e.target.value ? parseFloat(e.target.value) : '')}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        min="0"
                        className="l1-edit-cell"
                        value={sal.net_salary ?? ''}
                        onChange={(e) => onUpdateSalary(sal.id || idx, 'net_salary', e.target.value ? parseFloat(e.target.value) : '')}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        min="0"
                        className="l1-edit-cell"
                        value={sal.amount_credited ?? ''}
                        onChange={(e) => onUpdateSalary(sal.id || idx, 'amount_credited', e.target.value ? parseFloat(e.target.value) : '')}
                      />
                    </td>
                    <td>
                      <input
                        type="text"
                        className="l1-edit-cell"
                        placeholder="Bank Name"
                        value={sal.bank_name || ''}
                        onChange={(e) => onUpdateSalary(sal.id || idx, 'bank_name', e.target.value)}
                      />
                    </td>
                    {currentSalaries.length > 3 && (
                      <td className="l1-no-print" style={{ textAlign: 'center' }}>
                        <button
                          type="button"
                          onClick={() => onRemoveSalary(sal.id || idx)}
                          title="Remove Month"
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#DC2626' }}
                        >
                          🗑️
                        </button>
                      </td>
                    )}
                  </>
                ) : (
                  <>
                    <td><strong>{sal.month ? `${MONTH_NAMES[sal.month - 1] || sal.month} ${sal.year || ''}` : sal.reporting_month || `Month ${idx + 1}`}</strong></td>
                    <td>{sal.working_days ?? '—'}</td>
                    <td>{sal.pay_days ?? '—'}</td>
                    <td>{sal.leave_days ?? '—'}</td>
                    <td>{sal.credit_date || '—'}</td>
                    <td>{sal.gross_salary ? `₹${Number(sal.gross_salary).toLocaleString('en-IN')}` : '₹0'}</td>
                    <td>{sal.deductions ? `₹${Number(sal.deductions).toLocaleString('en-IN')}` : '₹0'}</td>
                    <td><strong>{sal.net_salary ? `₹${Number(sal.net_salary).toLocaleString('en-IN')}` : '₹0'}</strong></td>
                    <td>{sal.amount_credited ? `₹${Number(sal.amount_credited).toLocaleString('en-IN')}` : '₹0'}</td>
                    <td>{sal.bank_name || '—'}</td>
                  </>
                )}
              </tr>
            ))}
            {currentSalaries.length === 0 && (
              <tr>
                <td colSpan={isEditMode ? 11 : 10} style={{ textAlign: 'center', color: '#6B7280', padding: '14px' }}>
                  No salary disbursement records recorded.
                </td>
              </tr>
            )}
          </tbody>
          {currentSalaries.length > 0 && (
            <tfoot>
              <tr>
                <td colSpan={5} style={{ textAlign: 'right', fontWeight: 600 }}>
                  Summary Totals ({salarySummary.month_count ?? currentSalaries.length} Months, Avg Gross: ₹{Number(salarySummary.average_gross || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}):
                </td>
                <td>₹{Number(salarySummary.total_gross || 0).toLocaleString('en-IN')}</td>
                <td>₹{Number(salarySummary.total_deductions || 0).toLocaleString('en-IN')}</td>
                <td>₹{Number(salarySummary.total_net || 0).toLocaleString('en-IN')}</td>
                <td>₹{Number(salarySummary.total_credited || 0).toLocaleString('en-IN')}</td>
                <td></td>
                {isEditMode && currentSalaries.length > 3 && <td></td>}
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      {/* Section 4: Document Evidence & Compliance Audit */}
      <div>
        <h5 className="cpass-statement-section-title">4. Document Evidence &amp; Compliance Audit</h5>
        <table className="cpass-doc-table">
          <thead>
            <tr>
              <th style={{ width: '60px' }}>Doc Code</th>
              <th>Document Description</th>
              <th style={{ width: '80px' }}>Availability</th>
              <th style={{ width: '120px' }}>Criteria Compliance</th>
              <th>Repository Evidence Status</th>
              <th>Auditor Observations</th>
            </tr>
          </thead>
          <tbody>
            {evidenceRows.map((docItem, idx) => (
              <tr key={idx}>
                <td><strong>{docItem.code}</strong></td>
                <td>{docItem.label}</td>
                <td>
                  <span style={{ fontWeight: 700, color: docItem.available ? '#166534' : '#DC2626' }}>
                    {docItem.available ? '✓ Yes' : '✕ No'}
                  </span>
                </td>
                <td>
                  <span style={{ fontWeight: 600, color: docItem.compliance === 'Compliant' ? '#166534' : '#D97706' }}>
                    {docItem.compliance}
                  </span>
                </td>
                <td style={{ fontSize: '11px', color: '#4B5563' }}>
                  {docItem.repository_status}
                </td>
                <td>{docItem.observations || 'Verified during placement audit'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Section 5: Authorizations & Sign-off Endorsements */}
      <div>
        <h5 className="cpass-statement-section-title">5. Authorizations &amp; Sign-off Endorsements</h5>
        <div className="cpass-signoff-trio">
          {/* Centre Head */}
          <div className="cpass-signoff-box">
            <div className="cpass-signoff-box-title">Centre Head Verification</div>
            <div className="cpass-signoff-details">
              <div><strong>Name:</strong> {currentSignoffs.centre_head?.name || '—'}</div>
              <div><strong>Date:</strong> {currentSignoffs.centre_head?.date || '—'}</div>
              <div>
                <strong>Status:</strong>{' '}
                <span style={{ color: (currentSignoffs.centre_head?.confirmed || currentSignoffs.centre_head?.recommended) ? '#166534' : '#6B7280', fontWeight: 600 }}>
                  {(currentSignoffs.centre_head?.confirmed || currentSignoffs.centre_head?.recommended) ? 'Recommended / Approved' : 'Pending'}
                </span>
              </div>
              <div style={{ fontStyle: 'italic', color: '#6B7280', marginTop: '4px' }}>
                "{currentSignoffs.centre_head?.remarks || 'Dossier and physical records verified.'}"
              </div>
            </div>
            <div className="cpass-signoff-line">Signature of Centre Head</div>
          </div>

          {/* COPS Team */}
          <div className="cpass-signoff-box">
            <div className="cpass-signoff-box-title">COPS Team Audit</div>
            <div className="cpass-signoff-details">
              <div><strong>Name:</strong> {currentSignoffs.cops_team?.name || '—'}</div>
              <div><strong>Date:</strong> {currentSignoffs.cops_team?.date || '—'}</div>
              <div>
                <strong>Status:</strong>{' '}
                <span style={{ color: (currentSignoffs.cops_team?.confirmed || currentSignoffs.cops_team?.verified) ? '#166534' : '#6B7280', fontWeight: 600 }}>
                  {(currentSignoffs.cops_team?.confirmed || currentSignoffs.cops_team?.verified) ? 'Verified & Validated' : 'Pending'}
                </span>
              </div>
              <div style={{ fontStyle: 'italic', color: '#6B7280', marginTop: '4px' }}>
                "{currentSignoffs.cops_team?.remarks || 'Document criteria and salary credits audited.'}"
              </div>
            </div>
            <div className="cpass-signoff-line">Signature of COPS Auditor</div>
          </div>

          {/* Business Leader */}
          <div className="cpass-signoff-box">
            <div className="cpass-signoff-box-title">Business Leader Approval</div>
            <div className="cpass-signoff-details">
              <div><strong>Name:</strong> {currentSignoffs.business_leader?.name || '—'}</div>
              <div><strong>Date:</strong> {currentSignoffs.business_leader?.date || '—'}</div>
              <div>
                <strong>Status:</strong>{' '}
                <span style={{ color: (currentSignoffs.business_leader?.confirmed || currentSignoffs.business_leader?.approved) ? '#166534' : '#6B7280', fontWeight: 600 }}>
                  {(currentSignoffs.business_leader?.confirmed || currentSignoffs.business_leader?.approved) ? 'Approved for Compliance' : 'Pending'}
                </span>
              </div>
              <div style={{ fontStyle: 'italic', color: '#6B7280', marginTop: '4px' }}>
                "{currentSignoffs.business_leader?.remarks || 'Placement outcome approved.'}"
              </div>
            </div>
            <div className="cpass-signoff-line">Signature of Business Leader</div>
          </div>
        </div>
      </div>

      {/* Section 6: Overall Remarks */}
      <div>
        <h5 className="cpass-statement-section-title">6. Auditor Remarks &amp; Compliance Notes</h5>
        {isEditMode ? (
          <textarea
            rows={3}
            className="l1-edit-cell"
            style={{ width: '100%', padding: '8px 10px', fontSize: '13px' }}
            placeholder="Enter any additional audit remarks or observations..."
            value={currentRemarks}
            onChange={(e) => onUpdateRemarks(e.target.value)}
          />
        ) : (
          <div style={{ padding: '12px 14px', background: '#F9FAFB', border: '1px solid #E5E7EB', borderRadius: '8px', fontSize: '13px', color: '#1F2937', minHeight: '44px' }}>
            {currentRemarks || 'No exceptional auditor observations recorded. Placement verified according to DDU-GKY standard guidelines.'}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="cpass-statement-footer">
        <div>C-PASS Candidate Placement Audit System • SynchroServe Global Solutions Pvt Ltd</div>
        <div>Audit Statement ID: CPASS-AUD-{cand.candidate_id || cand.id || 'REF'} • Generated {new Date().toLocaleString('en-IN')}</div>
      </div>
    </div>
  )

  if (showModalWrapper) {
    return (
      <div className="l1-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="statement-modal-title">
        <div className="l1-statement-modal-card">
          <div className="l1-modal-header l1-no-print" style={{ padding: '14px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#F8FAFC', borderBottom: '1px solid #E2E8F0' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span style={{ fontSize: '18px' }}>📄</span>
              <strong id="statement-modal-title" style={{ fontSize: '15px', color: '#0A2A7A' }}>
                C-PASS Candidate Placement Audit &amp; Sign-off Statement
              </strong>
              <span className={`l1-status-pill ${cpassStatus === 'L2_APPROVED' ? 'success' : auditStatus === 'SUBMITTED' ? 'info' : 'warning'}`}>
                {cpassStatus === 'L2_APPROVED' ? 'L2 APPROVED' : auditStatus}
              </span>
            </div>
            <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
              {extraHeaderActions}
              <button
                type="button"
                className="l1-btn-primary-action"
                onClick={() => window.print()}
                style={{ padding: '7px 16px', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                <span>🖨️</span> Print / Save as PDF
              </button>
              <button
                type="button"
                className="l1-btn-icon-close"
                onClick={onClose}
                title="Close Statement"
              >
                ✕
              </button>
            </div>
          </div>

          <div className="l1-statement-modal-scroll" style={{ overflowY: 'auto', flex: 1, padding: '16px' }}>
            {sheetContent}
          </div>

          <div className="l1-modal-footer l1-no-print" style={{ padding: '12px 20px', background: '#F8FAFC', borderTop: '1px solid #E2E8F0', display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
            <button
              type="button"
              className="l1-btn-secondary"
              onClick={onClose}
            >
              Close
            </button>
            <button
              type="button"
              className="l1-btn-primary-action"
              onClick={() => window.print()}
            >
              <span>🖨️</span> Print / Save as PDF
            </button>
          </div>
        </div>
      </div>
    )
  }

  return sheetContent
}
