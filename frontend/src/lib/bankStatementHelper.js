import { MONTH_NAMES } from './salarySequenceHelper.js'

/**
 * Checks if a bank statement document is consolidated across multiple months.
 * Supports cross-calendar year coverage (e.g. Nov 2025 – Jan 2026).
 */
export function isDocConsolidated(d) {
  if (!d || d.document_type !== 'BANK_STATEMENT') return false
  if (d.is_consolidated === true || d.is_consolidated === 'true' || d.is_consolidated === 1) {
    return true
  }
  const sm = Number(d.coverage_start_month)
  const sy = Number(d.coverage_start_year || d.reporting_year)
  const em = Number(d.coverage_end_month)
  const ey = Number(d.coverage_end_year || d.reporting_year)
  if (sm && em && sy && ey) {
    const startVal = sy * 12 + sm
    const endVal = ey * 12 + em
    return endVal >= startVal
  }
  return false
}

/**
 * Resolves the full list of covered months from a consolidated document.
 * Returns an array of { month: number, year: number }.
 */
export function getDocCoveredMonths(doc) {
  if (!doc) return []

  let covered = doc.covered_months
  if (typeof covered === 'string') {
    try {
      covered = JSON.parse(covered)
    } catch (_) {
      covered = []
    }
  }

  if (Array.isArray(covered) && covered.length > 0) {
    return covered
      .map((cm) => ({
        month: Number(cm.month),
        year: Number(cm.year || doc.coverage_start_year || doc.reporting_year),
      }))
      .filter((m) => m.month >= 1 && m.month <= 12 && m.year > 0)
  }

  const sm = Number(doc.coverage_start_month || doc.reporting_month)
  const sy = Number(doc.coverage_start_year || doc.reporting_year)
  const em = Number(doc.coverage_end_month || sm)
  const ey = Number(doc.coverage_end_year || sy)

  if (!sm || !sy || !em || !ey) return []

  const list = []
  let curY = sy
  let curM = sm
  while (curY < ey || (curY === ey && curM <= em)) {
    list.push({ month: curM, year: curY })
    curM++
    if (curM > 12) {
      curM = 1
      curY++
    }
  }
  return list
}

/**
 * Resolves any employer identifier to its canonical employer in employerList.
 */
export function getCanonicalEmployerId(empId, employerList = []) {
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

  // 3. If there is only one employer in the list, any identifier refers to it
  if (employerList.length <= 1 && employerList[0]) {
    return String(employerList[0].id).trim()
  }

  return s
}

/**
 * Checks whether a document's employer ID matches a target employer ID.
 */
export function matchesEmployer(docEmpId, targetEmpId, employerList = []) {
  if (!employerList || employerList.length <= 1) return true
  if (!docEmpId || !targetEmpId) return true

  const canDoc = getCanonicalEmployerId(docEmpId, employerList)
  const canTarget = getCanonicalEmployerId(targetEmpId, employerList)
  if (canDoc && canTarget) {
    return canDoc === canTarget
  }
  return String(docEmpId).trim() === String(targetEmpId).trim()
}

/**
 * Checks if a specific reporting month and year for an employer is covered
 * by a persisted or locally staged consolidated bank statement.
 */
export function getConsolidatedCoverage(
  month,
  year,
  empId,
  { safeDocs = [], docSummary = null, stagedConsolidatedBankDocs = [], employerList = [] }
) {
  const targetM = Number(month)
  const targetY = Number(year)
  if (!targetM || !targetY) return null

  // 1. Check persisted consolidated bank statements
  const allBankDocs = [
    ...safeDocs.filter((d) => d.document_type === 'BANK_STATEMENT'),
    ...(Array.isArray(docSummary?.bank_statements) ? docSummary.bank_statements : []).filter(
      (d) => d.document_type === 'BANK_STATEMENT'
    ),
  ]

  // Deduplicate by ID
  const seenIds = new Set()
  const uniqueBankDocs = []
  for (const d of allBankDocs) {
    const key = d.id || `${d.file_name}_${d.reporting_month}_${d.reporting_year}`
    if (!seenIds.has(key)) {
      seenIds.add(key)
      uniqueBankDocs.push(d)
    }
  }

  for (const d of uniqueBankDocs) {
    if (!isDocConsolidated(d)) continue

    const statusUpper = String(d.upload_status || '').toUpperCase()
    if (statusUpper === 'FAILED') continue

    const uploadOk =
      statusUpper === 'SUCCESS' ||
      statusUpper === 'SAVED' ||
      statusUpper === 'VERIFIED' ||
      !d.upload_status ||
      Boolean(d.drive_file_id)
    if (!uploadOk) continue

    if (!matchesEmployer(d.employer_id, empId, employerList)) continue

    const coveredMonths = getDocCoveredMonths(d)
    const isCovered = coveredMonths.some((cm) => cm.month === targetM && cm.year === targetY)

    if (isCovered) {
      const startM = Number(d.coverage_start_month || d.reporting_month || 1)
      const startY = Number(d.coverage_start_year || d.reporting_year || targetY)
      const endM = Number(d.coverage_end_month || d.reporting_month || startM)
      const endY = Number(d.coverage_end_year || d.reporting_year || startY)
      return {
        persisted: true,
        doc: d,
        fileName: d.file_name,
        periodText: `${MONTH_NAMES[startM - 1]} ${startY} – ${MONTH_NAMES[endM - 1]} ${endY}`,
        coveredMonths,
      }
    }
  }

  // 2. Check locally staged consolidated bank statements
  for (const c of stagedConsolidatedBankDocs) {
    if (c.file && matchesEmployer(c.employer_id, empId, employerList)) {
      const coveredMonths = getDocCoveredMonths(c)
      const isCovered = coveredMonths.some((cm) => cm.month === targetM && cm.year === targetY)
      if (isCovered) {
        return {
          persisted: false,
          fileName: c.fileName,
          periodText: `${MONTH_NAMES[Number(c.coverage_start_month) - 1]} ${c.coverage_start_year} – ${MONTH_NAMES[Number(c.coverage_end_month) - 1]} ${c.coverage_end_year}`,
          coveredMonths,
        }
      }
    }
  }

  return null
}

/**
 * Returns concise client-ready status string for a bank statement document:
 * 'Verified' — only when reviewer status confirms it.
 * 'Saved' — file successfully persisted in storage/database.
 * 'Uploading' — upload in progress.
 * 'Upload failed' — upload failed.
 * 'Missing' — required evidence missing.
 */
export function getBankDocumentStatus(doc) {
  if (!doc) return 'Missing'

  const rev = String(doc.reviewer_status || doc.verification_status || '').toUpperCase()
  if (rev === 'VERIFIED' || rev === 'APPROVED') {
    return 'Verified'
  }

  const upl = String(doc.upload_status || '').toUpperCase()
  if (upl === 'FAILED') {
    return 'Upload failed'
  }
  if (upl === 'UPLOADING') {
    return 'Uploading'
  }

  if (doc.drive_file_id || upl === 'SUCCESS' || upl === 'SAVED' || !doc.upload_status) {
    return 'Saved'
  }

  return 'Missing'
}

/**
 * Determines whether an individual monthly slot control should be rendered.
 * Suppresses redundant empty upload controls if the month is already covered
 * by a persisted or staged consolidated bank statement, or by an individual persisted doc.
 * ALWAYS preserves slots with locally staged files.
 */
export function isBankSlotVisible(
  row,
  index,
  { bankRows = [], salaryDetailList = [], employerList = [], safeDocs = [], stagedConsolidatedBankDocs = [], docSummary = null }
) {
  // 1. Preserved locally staged files MUST ALWAYS be visible
  if (row?.file) return true

  // 2. Match corresponding salary record to get employer ID and period
  const matchedSal =
    salaryDetailList.find(
      (s) => Number(s.month) === Number(row.month) && Number(s.year) === Number(row.year)
    ) || salaryDetailList[index]

  const sEmpId = row?.employer_id || matchedSal?.employer_id || employerList[0]?.id
  const targetMonth = Number(row?.month || matchedSal?.month)
  const targetYear = Number(row?.year || matchedSal?.year)

  if (!targetMonth || !targetYear) return true

  // 3. If an individual bank statement is already persisted for this month and employer,
  // it is already displayed in the Persisted Monthly Statements card -> hide empty slot.
  const indDoc = safeDocs.find(
    (d) =>
      d.document_type === 'BANK_STATEMENT' &&
      !isDocConsolidated(d) &&
      (!d.upload_status || String(d.upload_status).toUpperCase() !== 'FAILED') &&
      Number(d.reporting_month) === targetMonth &&
      Number(d.reporting_year) === targetYear &&
      matchesEmployer(d.employer_id, sEmpId, employerList)
  )
  if (indDoc) return false

  // 4. If covered by a persisted or staged consolidated bank statement for the same employer,
  // do not render an empty monthly upload control.
  const consol = getConsolidatedCoverage(targetMonth, targetYear, sEmpId, {
    safeDocs,
    docSummary,
    stagedConsolidatedBankDocs,
    employerList,
  })
  if (consol) {
    return false
  }

  // 5. Genuinely uncovered month -> render upload control
  return true
}
