/**
 * CPASS Salary Month Sequence & Period Helper
 *
 * Provides authoritative employer-scoped salary month sequencing, label formatting,
 * and chronological predecessor calculations across all CPASS frontend components.
 *
 * Rules:
 * 1. Every employer has an independent 1-based sequence (Month 1, Month 2, Month 3...).
 * 2. Display sequence is calculated by sorting each employer's salary entries chronologically.
 * 3. Actual reporting month/year are preserved as entered (never mutated or confused with sequence).
 * 4. Copy Previous Month strictly searches the same employer's preceding reporting periods,
 *    correctly handling December-to-January year transitions.
 */

export const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
]

export const SHORT_MONTH_NAMES = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
]

/**
 * Returns the period integer (year * 12 + month) for chronological comparison.
 */
export function getPeriodValue(year, month) {
  const y = parseInt(year, 10) || 0
  const m = parseInt(month, 10) || 0
  return (y * 12) + m
}

/**
 * Normalize employer ID, falling back to 'emp_1' if null or undefined.
 */
export function normalizeEmployerId(employerId) {
  if (!employerId || typeof employerId !== 'string') return 'emp_1'
  const trimmed = employerId.trim()
  return trimmed || 'emp_1'
}

/**
 * Calculates the independent 1-based sequence number for a salary entry within its employer's records.
 *
 * @param {Object} salaryEntry - The entry whose sequence is being calculated.
 * @param {Array} allSalaries - All salary entries across all employers.
 * @returns {number} 1-based sequence number (1, 2, 3...).
 */
export function getEmployerSalarySequence(salaryEntry, allSalaries) {
  if (!salaryEntry || !Array.isArray(allSalaries) || allSalaries.length === 0) return 1

  const empId = normalizeEmployerId(salaryEntry.employer_id)

  // Filter entries for the SAME employer
  const empSalaries = allSalaries.filter((s) => normalizeEmployerId(s.employer_id) === empId)

  // Sort chronologically: earlier periods come first
  // If periods are equal or zero, preserve their relative order in allSalaries
  const sorted = [...empSalaries].sort((a, b) => {
    const periodA = getPeriodValue(a.year, a.month)
    const periodB = getPeriodValue(b.year, b.month)
    if (periodA !== periodB) return periodA - periodB
    return allSalaries.indexOf(a) - allSalaries.indexOf(b)
  })

  const seqIndex = sorted.findIndex((s) => (s.id && salaryEntry.id && s.id === salaryEntry.id) || s === salaryEntry)
  return seqIndex >= 0 ? seqIndex + 1 : 1
}

/**
 * Formats a salary entry's display label as "Month {seq} — {MonthName} {Year}".
 *
 * Example:
 * Employer A -> "Month 1 — January 2026"
 * Employer B -> "Month 1 — March 2026"
 *
 * @param {Object} salaryEntry - The salary entry object.
 * @param {Array} allSalaries - All salary entries for context.
 * @param {Object} options - Optional { employerName, shortMonth, includeEmployer }
 * @returns {string} Formatted label.
 */
export function formatEmployerSalaryLabel(salaryEntry, allSalaries, options = {}) {
  if (!salaryEntry) return 'Month 1'

  const seq = getEmployerSalarySequence(salaryEntry, allSalaries)
  const m = parseInt(salaryEntry.month, 10)
  const y = salaryEntry.year || ''

  let monthStr = ''
  if (m >= 1 && m <= 12) {
    monthStr = options.shortMonth ? SHORT_MONTH_NAMES[m - 1] : MONTH_NAMES[m - 1]
  }

  const periodText = monthStr ? `${monthStr} ${y}`.trim() : (y ? `${y}` : '')
  const baseLabel = periodText ? `Month ${seq} — ${periodText}` : `Month ${seq}`

  if (options.includeEmployer && options.employerName) {
    return `${options.employerName} • ${baseLabel}`
  }

  return baseLabel
}

/**
 * Precomputes a map of salary ID -> { sequence, label } for all salary entries.
 */
export function computeAllSalarySequences(allSalaries, employersList = []) {
  if (!Array.isArray(allSalaries)) return {}

  const empMap = new Map()
  if (Array.isArray(employersList)) {
    employersList.forEach((e) => {
      if (e && e.id) empMap.set(e.id, e.employer_name || '')
    })
  }

  const result = {}
  allSalaries.forEach((sal, idx) => {
    const key = sal.id || idx
    const seq = getEmployerSalarySequence(sal, allSalaries)
    const empId = normalizeEmployerId(sal.employer_id)
    const empName = empMap.get(empId) || ''
    const label = formatEmployerSalaryLabel(sal, allSalaries, { employerName: empName })
    result[key] = {
      sequence: seq,
      label,
      employer_id: empId,
      employer_name: empName,
    }
  })
  return result
}

/**
 * Finds the immediately preceding salary record for the SAME employer.
 * Handles December-to-January year transitions (e.g. Dec 2025 -> Jan 2026).
 * Never returns a record from a different employer.
 *
 * @param {Object} targetEntry - The current salary entry being copied to.
 * @param {Array} allSalaries - The complete list of salary entries.
 * @returns {Object|null} The immediately preceding record for the same employer, or null.
 */
export function findPreviousSalaryRecordForEmployer(targetEntry, allSalaries) {
  if (!targetEntry || !Array.isArray(allSalaries) || allSalaries.length === 0) return null

  const targetEmpId = normalizeEmployerId(targetEntry.employer_id)
  const targetPeriod = getPeriodValue(targetEntry.year, targetEntry.month)

  // Filter strictly to the same employer, excluding the target itself
  const sameEmpSalaries = allSalaries.filter(
    (s) => normalizeEmployerId(s.employer_id) === targetEmpId &&
           ((targetEntry.id && s.id !== targetEntry.id) || s !== targetEntry)
  )

  if (sameEmpSalaries.length === 0) return null

  // If target has a valid period, find the record with the highest period that is strictly < targetPeriod
  if (targetPeriod > 0) {
    const preceding = sameEmpSalaries.filter((s) => {
      const p = getPeriodValue(s.year, s.month)
      return p > 0 && p < targetPeriod
    })

    if (preceding.length > 0) {
      preceding.sort((a, b) => getPeriodValue(b.year, b.month) - getPeriodValue(a.year, a.month))
      return preceding[0]
    }
  }

  // Fallback: if target has no period set or is the earliest period, find record immediately preceding in array order
  const targetIdx = allSalaries.findIndex((s) => (s.id && targetEntry.id && s.id === targetEntry.id) || s === targetEntry)
  if (targetIdx > 0) {
    for (let i = targetIdx - 1; i >= 0; i--) {
      if (normalizeEmployerId(allSalaries[i].employer_id) === targetEmpId) {
        return allSalaries[i]
      }
    }
  }

  // If none found before, return the latest existing record for this employer
  return sameEmpSalaries[sameEmpSalaries.length - 1] || null
}

/**
 * Calculates the next logical reporting period for an employer.
 * Advances month by 1, wrapping December (12) to January (1) and incrementing the year.
 *
 * @param {string} targetEmpId - The employer ID.
 * @param {Array} allSalaries - Existing salary entries.
 * @param {number} defaultYear - Fallback year if none exists.
 * @returns {{ month: number, year: number }}
 */
export function calculateNextSalaryPeriodForEmployer(targetEmpId, allSalaries, defaultYear = new Date().getFullYear()) {
  const empId = normalizeEmployerId(targetEmpId)
  const empSalaries = (allSalaries || []).filter((s) => normalizeEmployerId(s.employer_id) === empId)

  if (empSalaries.length === 0) {
    return { month: 1, year: defaultYear }
  }

  // Find the chronological latest entry for this employer
  const sorted = [...empSalaries].sort((a, b) => getPeriodValue(a.year, a.month) - getPeriodValue(b.year, b.month))
  const latest = sorted[sorted.length - 1]

  const lastMonth = parseInt(latest.month, 10) || 1
  const lastYear = parseInt(latest.year, 10) || defaultYear

  if (lastMonth === 12) {
    return { month: 1, year: lastYear + 1 }
  }
  return { month: lastMonth + 1, year: lastYear }
}

/**
 * Calculates a document's independent 1-based sequence within its employer and type.
 */
export function getEmployerDocumentSequence(doc, allDocs) {
  if (!doc || !Array.isArray(allDocs)) return 1

  const empId = normalizeEmployerId(doc.employer_id)
  const docType = doc.document_type

  const matchingDocs = allDocs.filter(
    (d) => d.document_type === docType && normalizeEmployerId(d.employer_id) === empId
  )

  const sorted = [...matchingDocs].sort((a, b) => {
    const periodA = getPeriodValue(a.reporting_year || a.coverage_start_year, a.reporting_month || a.coverage_start_month)
    const periodB = getPeriodValue(b.reporting_year || b.coverage_start_year, b.reporting_month || b.coverage_start_month)
    if (periodA !== periodB) return periodA - periodB
    return allDocs.indexOf(a) - allDocs.indexOf(b)
  })

  const idx = sorted.findIndex((d) => (d.id && doc.id && d.id === doc.id) || d === doc)
  return idx >= 0 ? idx + 1 : 1
}
