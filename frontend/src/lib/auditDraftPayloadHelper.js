/**
 * CPASS Placement Audit Draft & Document Upload Serialization Helpers
 *
 * Guarantees that payloads submitted for draft persistence or Google Drive
 * metadata serialization are strictly primitive and free of:
 * - DOM Elements (e.g. HTMLButtonElement, HTMLInputElement)
 * - React SyntheticEvent instances or Fiber nodes
 * - Circular references of any kind
 * - Non-serializable objects (functions, symbols, undefined)
 */

export function sanitizeEmployerId(rawEmpId, fallbackEmpId = 'emp_1') {
  if (typeof rawEmpId === 'string' && rawEmpId.trim().length > 0) {
    return rawEmpId.trim()
  }
  if (typeof rawEmpId === 'number' && !isNaN(rawEmpId)) {
    return String(rawEmpId)
  }
  if (typeof fallbackEmpId === 'string' && fallbackEmpId.trim().length > 0) {
    return fallbackEmpId.trim()
  }
  return 'emp_1'
}

export function sanitizeEmployerDetails(employerList = []) {
  if (!Array.isArray(employerList)) return []
  return employerList
    .filter((e) => e && typeof e === 'object' && typeof e.employer_name === 'string' && e.employer_name.trim())
    .map((e) => ({
      id: String(e.id || ''),
      employer_name: String(e.employer_name).trim(),
      months_worked: e.months_worked !== '' && e.months_worked !== null && !isNaN(parseFloat(e.months_worked)) ? parseFloat(e.months_worked) : null,
      appointment_date: typeof e.appointment_date === 'string' ? e.appointment_date : null,
      designation: typeof e.designation === 'string' ? e.designation : null,
      place_of_work: typeof e.place_of_work === 'string' ? e.place_of_work : null,
      monthly_ctc: e.monthly_ctc !== '' && e.monthly_ctc !== null && !isNaN(parseFloat(e.monthly_ctc)) ? parseFloat(e.monthly_ctc) : null,
      minimum_wages: e.minimum_wages !== '' && e.minimum_wages !== null && !isNaN(parseFloat(e.minimum_wages)) ? parseFloat(e.minimum_wages) : null,
    }))
}

export function sanitizeSalaryDetails(salaryDetailList = [], fallbackEmpId = 'emp_1') {
  if (!Array.isArray(salaryDetailList)) return []
  return salaryDetailList.map((sal) => {
    if (!sal || typeof sal !== 'object') return null
    const cleanEmpId = sanitizeEmployerId(sal.employer_id, fallbackEmpId)
    return {
      id: String(sal.id || ''),
      employer_id: cleanEmpId,
      month: parseInt(sal.month, 10) || 1,
      year: parseInt(sal.year, 10) || new Date().getFullYear(),
      working_days: sal.working_days !== '' && sal.working_days !== null && !isNaN(parseInt(sal.working_days, 10)) ? parseInt(sal.working_days, 10) : null,
      pay_days: sal.pay_days !== '' && sal.pay_days !== null && !isNaN(parseInt(sal.pay_days, 10)) ? parseInt(sal.pay_days, 10) : null,
      leave_days: sal.leave_days !== '' && sal.leave_days !== null && !isNaN(parseInt(sal.leave_days, 10)) ? parseInt(sal.leave_days, 10) : null,
      credit_date: typeof sal.credit_date === 'string' ? sal.credit_date : null,
      amount_credited: sal.amount_credited !== '' && sal.amount_credited !== null && !isNaN(parseFloat(sal.amount_credited)) ? parseFloat(sal.amount_credited) : null,
      gross_salary: sal.gross_salary !== '' && sal.gross_salary !== null && !isNaN(parseFloat(sal.gross_salary)) ? parseFloat(sal.gross_salary) : null,
      deductions: sal.deductions !== '' && sal.deductions !== null && !isNaN(parseFloat(sal.deductions)) ? parseFloat(sal.deductions) : null,
      net_salary: sal.net_salary !== '' && sal.net_salary !== null && !isNaN(parseFloat(sal.net_salary)) ? parseFloat(sal.net_salary) : null,
      bank_name: typeof sal.bank_name === 'string' ? sal.bank_name : null,
    }
  }).filter(Boolean)
}

export function sanitizeSignoffDetails(signoffDetails = {}) {
  const cleanSignoffs = {}
  const roles = ['centre_head', 'cops_team', 'business_leader']
  for (const role of roles) {
    const src = signoffDetails?.[role] || {}
    cleanSignoffs[role] = {
      name: typeof src.name === 'string' ? src.name : '',
      designation: typeof src.designation === 'string' ? src.designation : '',
      date: typeof src.date === 'string' ? src.date : '',
      remarks: typeof src.remarks === 'string' ? src.remarks : '',
      confirmed: Boolean(src.confirmed),
      verified: Boolean(src.verified),
      approved: Boolean(src.approved),
      recommended: Boolean(src.recommended),
    }
  }
  return cleanSignoffs
}

export function sanitizeDocumentAudit(docAudit = {}) {
  if (!docAudit || typeof docAudit !== 'object') return {}
  const sanitized = {}
  for (const [k, v] of Object.entries(docAudit)) {
    // Exclude DOM nodes, Event instances, or circular elements
    if (v && typeof v === 'object' && !(typeof Element !== 'undefined' && v instanceof Element) && !(typeof Event !== 'undefined' && v instanceof Event)) {
      sanitized[k] = {
        available: typeof v.available === 'string' ? v.available : 'Pending',
        compliance: typeof v.compliance === 'string' ? v.compliance : 'Under Verification',
        remarks: typeof v.remarks === 'string' ? v.remarks : '',
        title: typeof v.title === 'string' ? v.title : '',
        explicitlySet: Boolean(v.explicitlySet),
        ...(v.month != null && !isNaN(Number(v.month)) ? { month: Number(v.month) } : {}),
        ...(v.year != null && !isNaN(Number(v.year)) ? { year: Number(v.year) } : {}),
      }
    } else if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') {
      sanitized[k] = v
    }
  }
  return sanitized
}

export function buildCleanAuditDraftPayload({
  candDetail,
  sel,
  lists,
  employerList,
  salaryDetailList,
  signoffDetails,
  auditRecord,
  documentAuditPayload,
}) {
  if (!sel?.cand || !candDetail) return null

  const fallbackEmpId = employerList?.[0]?.id ? String(employerList[0].id) : 'emp_1'
  const validEmployers = sanitizeEmployerDetails(employerList)
  const validSalary = sanitizeSalaryDetails(salaryDetailList, fallbackEmpId)
  const sanitizedDocAudit = sanitizeDocumentAudit(documentAuditPayload)
  const cleanSignoffs = sanitizeSignoffDetails(signoffDetails)

  return {
    candidate_snapshot: {
      candidate_id: candDetail.candidate_id,
      first_name: candDetail.first_name,
      last_name: candDetail.last_name,
      father_name: candDetail.father_name,
      dob: candDetail.dob,
      mobile: candDetail.mobile,
      state: sel.state,
      tc_name: lists?.tc?.find((c) => c.tc_id === sel.tc)?.name || sel.tc,
      batch_code: lists?.batch?.find((b) => b.kb_batch_id === sel.batch)?.batch_code || sel.batch,
      sanction_order: sel.order,
    },
    employer_details: validEmployers,
    salary_details: validSalary,
    document_audit: sanitizedDocAudit,
    signoff_details: cleanSignoffs,
    remarks: typeof auditRecord?.remarks === 'string' ? auditRecord.remarks : null,
  }
}

