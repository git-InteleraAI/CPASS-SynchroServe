import { useMemo } from 'react'
import synchroLogo from '../../assets/SynchroServeLogoHD.png'
import './PlacementAuditStatement.css'

import { getApprovalStatusDetails } from './approvalStatusHelper.js'
export { getApprovalStatusDetails }
import {
  MONTH_NAMES,
  getEmployerSalarySequence,
  formatEmployerSalaryLabel,
  normalizeEmployerId
} from '../lib/salarySequenceHelper'

export default function PlacementAuditStatement({
  statementData,
  isEditMode = false,
  editedData = null,
  onUpdateEmployer = () => { },
  onAddEmployer = () => { },
  onRemoveEmployer = () => { },
  onUpdateSalary = () => { },
  onAddSalary = () => { },
  onRemoveSalary = () => { },
  onUpdateSignoff = () => { },
  onUpdateRemarks = () => { },
  l1OriginalData = null,
  showModalWrapper = false,
  onClose = () => { },
  extraHeaderActions = null,
  extraFooterActions = null,
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

  const statusInfo = useMemo(() => {
    return getApprovalStatusDetails(statementData, currentSignoffs)
  }, [statementData, currentSignoffs])

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

  const getCanonicalEmployerId = (empId) => {
    if (!empId) return currentEmployers[0]?.id || ''
    const s = String(empId).trim()
    const direct = currentEmployers.find((e) => String(e.id).trim() === s)
    if (direct) return String(direct.id).trim()
    const norm = s.startsWith('emp_') ? s.slice(4) : s
    const idx = parseInt(norm, 10)
    if (!isNaN(idx) && idx >= 1 && idx <= currentEmployers.length) {
      return String(currentEmployers[idx - 1]?.id).trim()
    }
    if (currentEmployers.length <= 1 && currentEmployers[0]) {
      return String(currentEmployers[0].id).trim()
    }
    return s
  }

  const matchesEmployer = (docEmpId, targetEmpId) => {
    if (currentEmployers.length <= 1) return true
    if (!docEmpId || !targetEmpId) return true
    const canDoc = getCanonicalEmployerId(docEmpId)
    const canTarget = getCanonicalEmployerId(targetEmpId)
    if (canDoc && canTarget) return canDoc === canTarget
    return String(docEmpId).trim() === String(targetEmpId).trim()
  }

  const evidenceRows = statementData.document_evidence || (currentSalaries.length > 0
    ? [
        {
          code: 'AL / OL',
          label: 'Appointment / Offer Letter',
          key: 'appointment_letter',
          fallbackDoc: docList.find(d => d.document_type === 'APPOINTMENT_LETTER' && d.upload_status === 'SUCCESS'),
        },
        ...currentSalaries.map((sal, idx) => {
          const empSeq = getEmployerSalarySequence(sal, currentSalaries)
          const empObj = currentEmployers.find(e => e.id === sal.employer_id) || currentEmployers[0]
          const empPrefix = currentEmployers.length > 1 ? `${empObj?.employer_name || 'Employer'} • ` : ''
          const mName = MONTH_NAMES[(sal.month || 1) - 1] || `Month ${sal.month}`
          return {
            code: `PS ${empSeq}`,
            label: `Salary Pay Slip — ${empPrefix}Month ${empSeq} (${mName} ${sal.year || ''})`,
            key: `salary_slip_${idx + 1}`,
            fallbackDoc: docList.find(d =>
              d.document_type === 'SALARY_SLIP' &&
              d.upload_status === 'SUCCESS' &&
              (Number(d.reporting_year) === Number(sal.year) && Number(d.reporting_month) === Number(sal.month)) &&
              matchesEmployer(d.employer_id, sal.employer_id)
            ),
          }
        }),
        ...currentSalaries.map((sal, idx) => {
          const empSeq = getEmployerSalarySequence(sal, currentSalaries)
          const empObj = currentEmployers.find(e => e.id === sal.employer_id) || currentEmployers[0]
          const empPrefix = currentEmployers.length > 1 ? `${empObj?.employer_name || 'Employer'} • ` : ''
          const mName = MONTH_NAMES[(sal.month || 1) - 1] || `Month ${sal.month}`
          const sMonth = Number(sal.month)
          const sYear = Number(sal.year)
          const bankDoc = docList.find(d => {
            if (d.document_type !== 'BANK_STATEMENT') return false
            const stUpper = String(d.upload_status || '').toUpperCase()
            if (stUpper !== 'SUCCESS' && d.upload_status && !d.drive_file_id) return false
            if (!matchesEmployer(d.employer_id, sal.employer_id)) return false
            const isConsol = Boolean(
              d.is_consolidated === true ||
              d.is_consolidated === 'true' ||
              d.is_consolidated === 1 ||
              (d.coverage_start_month && d.coverage_end_month && Number(d.coverage_end_month) >= Number(d.coverage_start_month))
            )
            if (isConsol) {
              let covList = d.covered_months
              if (typeof covList === 'string') {
                try { covList = JSON.parse(covList) } catch (_) { covList = [] }
              }
              if (Array.isArray(covList) && covList.length > 0) {
                return covList.some(cm => Number(cm.month) === sMonth && (!cm.year || Number(cm.year) === sYear))
              }
              const s = (Number(d.coverage_start_year || d.reporting_year || sYear) * 12) + Number(d.coverage_start_month || d.reporting_month || 1)
              const e = (Number(d.coverage_end_year || d.reporting_year || sYear) * 12) + Number(d.coverage_end_month || d.reporting_month || 1)
              const c = (sYear * 12) + sMonth
              return c >= s && c <= e
            }
            return Number(d.reporting_year) === sYear && Number(d.reporting_month) === sMonth
          })
          const isConsol = Boolean(
            bankDoc?.is_consolidated === true ||
            bankDoc?.is_consolidated === 'true' ||
            bankDoc?.is_consolidated === 1 ||
            (bankDoc?.coverage_start_month && bankDoc?.coverage_end_month && Number(bankDoc.coverage_end_month) >= Number(bankDoc.coverage_start_month))
          )
          const startM = Number(bankDoc?.coverage_start_month || bankDoc?.reporting_month || 1)
          const startY = Number(bankDoc?.coverage_start_year || bankDoc?.reporting_year || sYear)
          const endM = Number(bankDoc?.coverage_end_month || bankDoc?.reporting_month || startM)
          const endY = Number(bankDoc?.coverage_end_year || bankDoc?.reporting_year || startY)
          const consolSuffix = isConsol ? ' (Consolidated Statement)' : ''
          return {
            code: `BS ${empSeq}`,
            label: `Bank Statement / Passbook — ${empPrefix}Month ${empSeq} (${mName} ${sal.year || ''})${consolSuffix}`,
            key: `bank_statement_${idx + 1}`,
            fallbackDoc: bankDoc,
            isConsolidated: isConsol,
            coverageText: isConsol ? `${MONTH_NAMES[startM - 1]} ${startY} – ${MONTH_NAMES[endM - 1]} ${endY}` : '',
          }
        }),
        {
          code: 'OD',
          label: 'Other Document (Optional)',
          key: 'other_document',
          fallbackDoc: docList.find(d => d.document_type === 'OTHER_DOCUMENT' && d.upload_status === 'SUCCESS'),
        },
      ]
    : [
        {
          code: 'AL / OL',
          label: 'Appointment / Offer Letter',
          key: 'appointment_letter',
          fallbackDoc: docList.find(d => d.document_type === 'APPOINTMENT_LETTER' && d.upload_status === 'SUCCESS'),
        },
        {
          code: 'PS 1',
          label: 'Salary Pay Slip — Month 1',
          key: 'salary_slip_1',
          fallbackDoc: docList.find(d => d.document_type === 'SALARY_SLIP' && d.upload_status === 'SUCCESS' && d.reporting_month === 1),
        },
        {
          code: 'PS 2',
          label: 'Salary Pay Slip — Month 2',
          key: 'salary_slip_2',
          fallbackDoc: docList.find(d => d.document_type === 'SALARY_SLIP' && d.upload_status === 'SUCCESS' && d.reporting_month === 2),
        },
        {
          code: 'PS 3',
          label: 'Salary Pay Slip — Month 3',
          key: 'salary_slip_3',
          fallbackDoc: docList.find(d => d.document_type === 'SALARY_SLIP' && d.upload_status === 'SUCCESS' && d.reporting_month === 3),
        },
        ...[1, 2, 3].map((mIdx) => {
          const bankDoc = docList.find(d => {
            if (d.document_type !== 'BANK_STATEMENT') return false
            const stUpper = String(d.upload_status || '').toUpperCase()
            if (stUpper !== 'SUCCESS' && d.upload_status && !d.drive_file_id) return false
            const isConsol = Boolean(
              d.is_consolidated === true ||
              d.is_consolidated === 'true' ||
              d.is_consolidated === 1 ||
              (d.coverage_start_month && d.coverage_end_month && Number(d.coverage_end_month) >= Number(d.coverage_start_month))
            )
            if (isConsol) {
              let covList = d.covered_months
              if (typeof covList === 'string') {
                try { covList = JSON.parse(covList) } catch (_) { covList = [] }
              }
              if (Array.isArray(covList) && covList.length > 0) {
                return covList.some(cm => Number(cm.month) === mIdx)
              }
              const s = Number(d.coverage_start_month || d.reporting_month || 1)
              const e = Number(d.coverage_end_month || d.reporting_month || 12)
              return mIdx >= s && mIdx <= e
            }
            return Number(d.reporting_month) === mIdx
          })
          const isConsol = Boolean(
            bankDoc?.is_consolidated === true ||
            bankDoc?.is_consolidated === 'true' ||
            bankDoc?.is_consolidated === 1 ||
            (bankDoc?.coverage_start_month && bankDoc?.coverage_end_month && Number(bankDoc.coverage_end_month) >= Number(bankDoc.coverage_start_month))
          )
          return {
            code: `BS ${mIdx}`,
            label: `Bank Statement / Passbook — Month ${mIdx}${isConsol ? ' (Consolidated Statement)' : ''}`,
            key: `bank_statement_${mIdx}`,
            fallbackDoc: bankDoc,
            isConsolidated: isConsol,
          }
        }),
        {
          code: 'OD',
          label: 'Other Document (Optional)',
          key: 'other_document',
          fallbackDoc: docList.find(d => d.document_type === 'OTHER_DOCUMENT' && d.upload_status === 'SUCCESS'),
        },
      ]
  ).map(item => {
    const isConsol = item.isConsolidated
    const consolNote = isConsol ? ' (Consolidated Statement)' : ''
    return {
      code: item.code,
      key: item.key,
      label: item.fallbackDoc?.document_title ? `Other Document — ${item.fallbackDoc.document_title}` : item.label,
      available: item.fallbackDoc ? 'Yes' : 'Pending',
      compliance: item.fallbackDoc ? 'Compliant' : 'Under Verification',
      repository_status: item.fallbackDoc ? `Stored in Drive: ${item.fallbackDoc.file_name}${consolNote}` : (item.code === 'OD' ? 'Optional document not provided' : 'No verified file in database'),
      observations: item.fallbackDoc ? `Verified during placement audit${consolNote}` : (item.code === 'OD' ? 'Optional supporting document' : 'Pending upload and verification'),
    }
  })

  // Helper to check if a field was changed relative to L1 original submission
  const isChangedFromL1 = (section, idx, field, currentVal) => {
    if (!l1OriginalData) return false
    const origSection = l1OriginalData[section]
    if (!Array.isArray(origSection) || !origSection[idx]) return false
    const origVal = origSection[idx][field]
    return origVal !== undefined && String(origVal) !== String(currentVal)
  }

  const submitter = statementData.submitter || statementData.signoff_details?.submitter || null

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
          <h4>C-PASS STATEMENT</h4>
          <p>
            Deen Dayal Upadhyaya Grameen Kaushalya Yojana (DDU-GKY)<br />
            Candidate Placement Audit &amp; Sign-off Verification Record
          </p>
        </div>
        <div className="cpass-header-meta">
          <div><strong>Doc Ref:</strong> CPASS-AUD-{cand.candidate_id || cand.id || 'REF'}</div>
          <div><strong>Date:</strong> {statementData.generated_at ? new Date(statementData.generated_at).toLocaleDateString('en-IN') : new Date().toLocaleDateString('en-IN')}</div>
          {submitter && (
            <div>
              <strong>Submitted By:</strong> {submitter.name || 'Placement Executive'}
            </div>
          )}
          <div>
            <strong>Overall Status:</strong>{' '}
            <span className={`cpass-status-badge ${statusInfo.overallBadgeClass}`}>
              {statusInfo.overallStatus}
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
            <span className="k">Gender / DOB</span>
            <span className="v">{cand.gender || 'N/A'}{cand.dob && cand.dob !== 'Not Available' ? ` • ${cand.dob}` : (cand.date_of_birth && cand.date_of_birth !== 'Not Available' ? ` • ${cand.date_of_birth}` : '')}</span>
          </div>
          <div className="cpass-dossier-item">
            <span className="k">Contact / Email</span>
            <span className="v">{cand.contact_number || cand.mobile || 'N/A'}{cand.candidate_email && cand.candidate_email !== 'Not Available' ? ` • ${cand.candidate_email}` : ''}</span>
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
            <span className="k">Sanction Order</span>
            <span className="v">{cand.sanction_order || cand.sanction_order_name || 'N/A'}</span>
          </div>
          <div className="cpass-dossier-item">
            <span className="k">Batch Code &amp; Dates</span>
            <span className="v">{cand.batch_code || cand.batch_id || 'N/A'}{cand.batch_start_date && cand.batch_start_date !== 'Not Available' ? ` (${cand.batch_start_date} to ${cand.batch_end_date || '—'})` : ''}</span>
          </div>
          <div className="cpass-dossier-item">
            <span className="k">State</span>
            <span className="v">{cand.state || 'N/A'}</span>
          </div>
          <div className="cpass-dossier-item">
            <span className="k">Bank Account</span>
            <span className="v">{cand.masked_bank_account || cand.bank_account || 'Not Available'}</span>
          </div>
          <div className="cpass-dossier-item">
            <span className="k">Review Status</span>
            <span className="v">{statusInfo.reviewStatusDetail}</span>
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
        <div className="cpass-table-responsive">
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
        <div className="cpass-table-responsive">
          <table className="cpass-doc-table">
            <thead>
              <tr>
                <th style={{ width: '130px' }}>Reporting Month</th>
                {currentEmployers.length > 1 && <th style={{ width: '120px' }}>Employer</th>}
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
              {currentSalaries.map((sal, idx) => {
                const empObj = currentEmployers.find((e) => e.id === sal.employer_id) || currentEmployers[0]
                return (
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
                        {currentEmployers.length > 1 && (
                          <td>
                            <select
                              className="l1-edit-cell"
                              value={sal.employer_id || currentEmployers[0]?.id}
                              onChange={(e) => onUpdateSalary(sal.id || idx, 'employer_id', e.target.value)}
                            >
                              {currentEmployers.map((emp, eIdx) => (
                                <option key={emp.id || eIdx} value={emp.id}>
                                  {emp.employer_name || `Employer ${eIdx + 1}`}
                                </option>
                              ))}
                            </select>
                          </td>
                        )}
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
                        <td><strong>{formatEmployerSalaryLabel(sal, currentSalaries)}</strong></td>
                        {currentEmployers.length > 1 && (
                          <td>
                            <span style={{ fontSize: '11px', fontWeight: 600, color: '#334155', background: '#F1F5F9', padding: '2px 6px', borderRadius: '4px' }}>
                              {empObj?.employer_name || '—'}
                            </span>
                          </td>
                        )}
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
                )
              })}
              {currentSalaries.length === 0 && (
                <tr>
                  <td colSpan={isEditMode ? (currentEmployers.length > 1 ? 12 : 11) : (currentEmployers.length > 1 ? 11 : 10)} style={{ textAlign: 'center', color: '#6B7280', padding: '14px' }}>
                    No salary disbursement records recorded.
                  </td>
                </tr>
              )}
            </tbody>
            {currentSalaries.length > 0 && (
              <tfoot>
                <tr>
                  <td colSpan={currentEmployers.length > 1 ? 6 : 5} style={{ textAlign: 'right', fontWeight: 600 }}>
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
      </div>

      {/* Section 4: Document Evidence Audit */}
      <div>
        <h5 className="cpass-statement-section-title">4. Document Evidence Audit</h5>
        <div className="cpass-table-responsive">
          <table className="cpass-doc-table">
            <thead>
              <tr>
                <th style={{ width: '60px' }}>Doc Code</th>
                <th>Document Description</th>
                <th style={{ width: '80px' }}>Availability</th>
                <th>Repository Evidence Status</th>
                <th>Auditor Observations</th>
              </tr>
            </thead>
            <tbody>
              {evidenceRows.map((docItem, idx) => (
                <tr key={docItem.key || idx}>
                  <td><strong>{docItem.code}</strong></td>
                  <td>
                    {docItem.label}
                    {docItem.employer_name && (
                      <span style={{ marginLeft: '6px', fontSize: '10.5px', background: '#F1F5F9', color: '#334155', padding: '1px 5px', borderRadius: '3px', fontWeight: 600 }}>
                        🏢 {docItem.employer_name}
                      </span>
                    )}
                    {docItem.coverage_period && (
                      <span style={{ marginLeft: '6px', fontSize: '10.5px', background: '#E0F2FE', color: '#0369A1', padding: '1px 5px', borderRadius: '3px', fontWeight: 600 }}>
                        Coverage: {docItem.coverage_period}
                      </span>
                    )}
                  </td>
                  <td>
                    {docItem.available === 'Yes' || docItem.available === true ? (
                      <span style={{ fontWeight: 700, color: '#166534' }}>✓ Yes</span>
                    ) : docItem.available === 'Pending' ? (
                      <span style={{ fontWeight: 700, color: '#D97706' }}>⏳ Pending</span>
                    ) : (
                      <span style={{ fontWeight: 700, color: '#DC2626' }}>✕ No</span>
                    )}
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
      </div>

      {/* Section 5: Authorizations & Sign-off Endorsements */}
      <div>
        <h5 className="cpass-statement-section-title">5. Multi-Level Sign-Off &amp; Approvals</h5>
        <div className="cpass-signoff-trio">
          {/* Centre Head (CH) */}
          <div className="cpass-signoff-box">
            <div className="cpass-signoff-box-header">
              <div className="cpass-signoff-box-title">Centre Head (CH)</div>
              <span className={`cpass-status-badge ${statusInfo.chStage.badgeClass}`}>
                {statusInfo.chStage.label}
              </span>
            </div>
            <div className="cpass-signoff-details">
              <div><strong>Decision:</strong> {statusInfo.chStage.decision}</div>
              <div><strong>Reviewer:</strong> {statusInfo.chStage.reviewer}</div>
              <div><strong>Date:</strong> {statusInfo.chStage.date}</div>
              {statusInfo.chStage.return_reason && (
                <div style={{ color: '#92400E', fontSize: '10.5px', marginTop: '2px' }}>
                  <strong>Return Reason:</strong> "{statusInfo.chStage.return_reason}"
                </div>
              )}
              {statusInfo.chStage.rejection_reason && (
                <div style={{ color: '#B91C1C', fontSize: '10.5px', marginTop: '2px' }}>
                  <strong>Rejection Reason:</strong> "{statusInfo.chStage.rejection_reason}"
                </div>
              )}
              <div style={{ fontStyle: 'italic', color: '#64748B', marginTop: '4px' }}>
                "{statusInfo.chStage.remarks}"
              </div>
            </div>
            <div className="cpass-signoff-line">Signature of Centre Head</div>
          </div>

          {/* COPS Audit (COPS) */}
          <div className="cpass-signoff-box">
            <div className="cpass-signoff-box-header">
              <div className="cpass-signoff-box-title">COPS Audit (COPS)</div>
              <span className={`cpass-status-badge ${statusInfo.copsStage.badgeClass}`}>
                {statusInfo.copsStage.label}
              </span>
            </div>
            <div className="cpass-signoff-details">
              <div><strong>Decision:</strong> {statusInfo.copsStage.decision}</div>
              <div><strong>Reviewer:</strong> {statusInfo.copsStage.reviewer}</div>
              <div><strong>Date:</strong> {statusInfo.copsStage.date}</div>
              {statusInfo.copsStage.rejection_reason && (
                <div style={{ color: '#B91C1C', fontSize: '10.5px', marginTop: '2px' }}>
                  <strong>Rejection Reason:</strong> "{statusInfo.copsStage.rejection_reason}"
                </div>
              )}
              <div style={{ fontStyle: 'italic', color: '#64748B', marginTop: '4px' }}>
                "{statusInfo.copsStage.remarks}"
              </div>
            </div>
            <div className="cpass-signoff-line">Signature of COPS Auditor</div>
          </div>

          {/* Business Leader (BL) */}
          <div className="cpass-signoff-box">
            <div className="cpass-signoff-box-header">
              <div className="cpass-signoff-box-title">Business Leader (BL)</div>
              <span className={`cpass-status-badge ${statusInfo.blStage.badgeClass}`}>
                {statusInfo.blStage.label}
              </span>
            </div>
            <div className="cpass-signoff-details">
              <div><strong>Decision:</strong> {statusInfo.blStage.decision}</div>
              <div><strong>Reviewer:</strong> {statusInfo.blStage.reviewer}</div>
              <div><strong>Date:</strong> {statusInfo.blStage.date}</div>
              {statusInfo.blStage.rejection_reason && (
                <div style={{ color: '#B91C1C', fontSize: '10.5px', marginTop: '2px' }}>
                  <strong>Rejection Reason:</strong> "{statusInfo.blStage.rejection_reason}"
                </div>
              )}
              <div style={{ fontStyle: 'italic', color: '#64748B', marginTop: '4px' }}>
                "{statusInfo.blStage.remarks}"
              </div>
            </div>
            <div className="cpass-signoff-line">Signature of Business Leader</div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="cpass-statement-footer">
        <div>C-PASS Candidate Placement Audit System • SynchroServe Global Solutions Pvt Ltd</div>
        <div>
          Audit Statement ID: CPASS-AUD-{cand.candidate_id || cand.id || 'REF'} • Generated {new Date().toLocaleString('en-IN')}
          {submitter?.name ? ` • Submitter: ${submitter.name} (${submitter.role_label || 'L1 (PE)'})` : ''}
        </div>
      </div>
    </div>
  )

  if (showModalWrapper) {
    return (
      <div className="l1-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="statement-modal-title">
        <div className="l1-statement-modal-card">
          <div className="l1-statement-modal-header l1-no-print">
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span style={{ fontSize: '18px' }}>📄</span>
              <strong id="statement-modal-title" style={{ fontSize: '14.5px', color: '#0A2A7A', fontWeight: 700 }}>
                C-PASS Statement Preview
              </strong>
              <span className={`cpass-status-badge ${statusInfo.overallBadgeClass}`}>
                {statusInfo.overallStatus}
              </span>
            </div>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              {extraHeaderActions}
              <button
                type="button"
                className="l1-btn-primary-action"
                onClick={() => window.print()}
                style={{ padding: '6px 14px', fontSize: '12.5px', display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                <span>🖨️</span> Print / Save as PDF
              </button>
              <button
                type="button"
                className="l1-btn-icon-close"
                onClick={onClose}
                title="Close Statement"
                aria-label="Close"
              >
                ✕
              </button>
            </div>
          </div>

          <div className="l1-statement-modal-scroll">
            {sheetContent}
          </div>

          <div className="l1-statement-modal-footer l1-no-print">
            {extraFooterActions}
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
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
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
