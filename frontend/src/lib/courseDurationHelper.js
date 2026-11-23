/**
 * CPASS Course Duration & Minimum Wage Validation Helper
 *
 * Infers standard DDU-GKY course duration (3, 6, 9, 12 months) from Batch Start Date
 * and Batch End Date, determines governing minimum CTC using the Higher-of-Two rule
 * between course minimum and statutory state minimum wage, and validates employer monthly CTC.
 */

export const STANDARD_COURSE_DURATIONS = {
  3: 6000,
  6: 8000,
  9: 12000,
  12: 15000,
}

export const INDIAN_STATES_28 = [
  'Andhra Pradesh',
  'Arunachal Pradesh',
  'Assam',
  'Bihar',
  'Chhattisgarh',
  'Goa',
  'Gujarat',
  'Haryana',
  'Himachal Pradesh',
  'Jharkhand',
  'Karnataka',
  'Kerala',
  'Madhya Pradesh',
  'Maharashtra',
  'Manipur',
  'Meghalaya',
  'Mizoram',
  'Nagaland',
  'Odisha',
  'Punjab',
  'Rajasthan',
  'Sikkim',
  'Tamil Nadu',
  'Telangana',
  'Tripura',
  'Uttar Pradesh',
  'Uttarakhand',
  'West Bengal',
]

export const INDIAN_UTS_8 = [
  'Andaman and Nicobar Islands',
  'Chandigarh',
  'Dadra and Nagar Haveli and Daman and Diu',
  'Delhi',
  'Jammu and Kashmir',
  'Ladakh',
  'Lakshadweep',
  'Puducherry',
]

export const ALL_36_INDIAN_STATES_AND_UTS = [...INDIAN_STATES_28, ...INDIAN_UTS_8]

export const SUPPORTED_13_STATES = new Set([
  'ANDHRA PRADESH',
  'BIHAR',
  'GUJARAT',
  'KERALA',
  'MIZORAM',
  'ODISHA',
  'PUDUCHERRY',
  'PUNJAB',
  'RAJASTHAN',
  'TAMIL NADU',
  'TELANGANA',
  'UTTAR PRADESH',
  'WEST BENGAL',
])

export function parseDateSafe(val) {
  if (!val) return null
  const s = String(val).trim()
  if (!s || ['not available', 'n/a', 'none', 'null', 'undefined', '—', '-'].includes(s.toLowerCase())) {
    return null
  }

  // Handle ISO strings with time
  let cleanStr = s
  if (cleanStr.includes('T') || cleanStr.includes('t')) {
    cleanStr = cleanStr.split(/[Tt]/)[0]
  } else if (cleanStr.includes(' ')) {
    cleanStr = cleanStr.split(' ')[0]
  }

  // Try YYYY-MM-DD
  const isoMatch = cleanStr.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/)
  if (isoMatch) {
    const y = parseInt(isoMatch[1], 10)
    const m = parseInt(isoMatch[2], 10) - 1
    const d = parseInt(isoMatch[3], 10)
    const dt = new Date(y, m, d)
    if (dt.getFullYear() === y && dt.getMonth() === m && dt.getDate() === d) {
      return dt
    }
  }

  // Try DD/MM/YYYY or DD-MM-YYYY
  const dmyMatch = cleanStr.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/)
  if (dmyMatch) {
    const d = parseInt(dmyMatch[1], 10)
    const m = parseInt(dmyMatch[2], 10) - 1
    const y = parseInt(dmyMatch[3], 10)
    const dt = new Date(y, m, d)
    if (dt.getFullYear() === y && dt.getMonth() === m && dt.getDate() === d) {
      return dt
    }
  }

  const parsed = new Date(cleanStr)
  return isNaN(parsed.getTime()) ? null : parsed
}

/**
 * Formats an appointment date into standard YYYY-MM-DD string expected by backend APIs.
 * Supports YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY, and ISO date strings.
 *
 * @param {string|Date|null} dt
 * @returns {string|null} YYYY-MM-DD or null
 */
export function formatApptDateForBackend(dt) {
  if (!dt) return null
  const parsed = parseDateSafe(dt)
  if (!parsed) return null
  const y = parsed.getFullYear()
  const m = String(parsed.getMonth() + 1).padStart(2, '0')
  const d = String(parsed.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export function calculateCourseDuration(batchStartDate, batchEndDate) {
  const start = parseDateSafe(batchStartDate)
  const end = parseDateSafe(batchEndDate)

  if (!start || !end) {
    return {
      months: null,
      label: null,
      minimum_ctc: null,
      total_days: null,
      status: 'MISSING_DATES',
      message: 'Course duration could not be reliably determined from the available batch dates. Course-based minimum CTC validation has been skipped. Available state minimum-wage validation will still be applied.',
    }
  }

  if (end < start) {
    return {
      months: null,
      label: null,
      minimum_ctc: null,
      total_days: null,
      status: 'INVALID_DATES',
      message: 'Batch end date precedes batch start date. Course duration could not be reliably determined. Course-based minimum CTC validation has been skipped.',
    }
  }

  // Inclusive calendar days: (end - start in ms) / 86400000 + 1
  const diffMs = end.getTime() - start.getTime()
  const totalDays = Math.round(diffMs / (1000 * 60 * 60 * 24)) + 1

  // Standard duration brackets:
  // 3 Months (~91 days): 65 to 137 days
  // 6 Months (~183 days): 138 to 228 days
  // 9 Months (~274 days): 229 to 319 days
  // 12 Months (~365 days): 320 to 425 days
  if (totalDays < 65) {
    return {
      months: null,
      label: null,
      minimum_ctc: null,
      total_days: totalDays,
      status: 'UNMATCHED_DURATION',
      message: `Batch duration (${totalDays} days) is less than the standard 3-month course threshold. Course-based minimum CTC validation has been skipped.`,
    }
  }

  let matchedMonths = null
  if (totalDays <= 137) {
    matchedMonths = 3
  } else if (totalDays <= 228) {
    matchedMonths = 6
  } else if (totalDays <= 319) {
    matchedMonths = 9
  } else if (totalDays <= 425) {
    matchedMonths = 12
  } else {
    return {
      months: null,
      label: null,
      minimum_ctc: null,
      total_days: totalDays,
      status: 'UNMATCHED_DURATION',
      message: `Batch duration (${totalDays} days) exceeds the standard 12-month course threshold. Course-based minimum CTC validation has been skipped.`,
    }
  }

  const minCTC = STANDARD_COURSE_DURATIONS[matchedMonths]
  return {
    months: matchedMonths,
    label: `${matchedMonths} Months`,
    minimum_ctc: minCTC,
    total_days: totalDays,
    status: 'DETERMINED',
    message: null,
  }
}

export function calculateApplicableMinimumCTC(courseMinCTC, stateMinWage) {
  const hasCourse = courseMinCTC != null && Number(courseMinCTC) > 0
  const hasState = stateMinWage != null && Number(stateMinWage) > 0

  const numCourse = hasCourse ? Number(courseMinCTC) : null
  const numState = hasState ? Number(stateMinWage) : null

  if (hasCourse && hasState) {
    const applicableMin = Math.max(numCourse, numState)
    let governingRule = 'HIGHER_OF_COURSE_AND_STATE'
    if (numCourse > numState) governingRule = 'COURSE_DURATION_HIGHER'
    else if (numState > numCourse) governingRule = 'STATE_WAGE_HIGHER'
    else governingRule = 'EQUAL_AMOUNTS'

    return {
      applicable_minimum_ctc: applicableMin,
      applicableMinimumCTC: applicableMin,
      course_minimum_ctc: numCourse,
      courseMinimumCTC: numCourse,
      state_minimum_wage: numState,
      stateMinimumWage: numState,
      governing_rule: governingRule,
    }
  }

  if (hasCourse) {
    return {
      applicable_minimum_ctc: numCourse,
      applicableMinimumCTC: numCourse,
      course_minimum_ctc: numCourse,
      courseMinimumCTC: numCourse,
      state_minimum_wage: null,
      stateMinimumWage: null,
      governing_rule: 'COURSE_DURATION_ONLY',
    }
  }

  if (hasState) {
    return {
      applicable_minimum_ctc: numState,
      applicableMinimumCTC: numState,
      course_minimum_ctc: null,
      courseMinimumCTC: null,
      state_minimum_wage: numState,
      stateMinimumWage: numState,
      governing_rule: 'STATE_WAGE_ONLY',
    }
  }

  return {
    applicable_minimum_ctc: null,
    applicableMinimumCTC: null,
    course_minimum_ctc: null,
    courseMinimumCTC: null,
    state_minimum_wage: null,
    stateMinimumWage: null,
    governing_rule: 'NONE_AVAILABLE',
  }
}

export function validateEmployerMonthlyCTC(monthlyCTC, courseDurationInfo, stateMinWage, employerName = '') {
  const courseMin = courseDurationInfo?.minimum_ctc
  const calc = calculateApplicableMinimumCTC(courseMin, stateMinWage)
  const applicableMin = calc.applicable_minimum_ctc ?? calc.applicableMinimumCTC

  let enteredNum = null
  if (monthlyCTC !== '' && monthlyCTC != null) {
    const parsed = Number(monthlyCTC)
    if (!isNaN(parsed)) enteredNum = parsed
  }

  // If neither course min nor state wage can be determined, do not block submission
  if (applicableMin == null) {
    return {
      isValid: true,
      valid: true,
      enteredCTC: enteredNum,
      applicableMinimumCTC: null,
      applicable_min_ctc: null,
      courseDurationInfo,
      stateMinWage,
      userMessage: null,
      message: null,
    }
  }

  // If entered CTC is below applicable minimum (or missing/0)
  if (enteredNum == null || enteredNum < applicableMin) {
    const courseLabel = courseDurationInfo?.label || 'Not Available'
    const courseMinStr = courseMin ? `₹${Math.round(courseMin).toLocaleString('en-IN')}` : 'Not Available'
    const stateWageStr = stateMinWage ? `₹${Math.round(stateMinWage).toLocaleString('en-IN')}` : 'Unavailable'
    const appMinStr = `₹${Math.round(applicableMin).toLocaleString('en-IN')}`
    const enteredStr = enteredNum != null ? `₹${Math.round(enteredNum).toLocaleString('en-IN')}` : '₹0 (Not Provided)'
    const empPrefix = employerName ? ` for employer '${employerName}'` : ''

    const message = `The entered monthly CTC${empPrefix} is below the applicable minimum requirement for this placement.\n\n` +
      `Course Duration: ${courseLabel}\n` +
      `Course Minimum CTC: ${courseMinStr}\n` +
      `State Minimum Wage: ${stateWageStr}\n` +
      `Applicable Minimum CTC: ${appMinStr}\n` +
      `Entered Monthly CTC: ${enteredStr}\n\n` +
      `Please update the Monthly CTC before submitting the Candidate Dossier.`

    return {
      isValid: false,
      valid: false,
      enteredCTC: enteredNum,
      applicableMinimumCTC: applicableMin,
      applicable_min_ctc: applicableMin,
      courseDurationInfo,
      stateMinWage,
      userMessage: message,
      message: message,
      title: 'Minimum CTC Requirement Not Met',
    }
  }

  return {
    isValid: true,
    valid: true,
    enteredCTC: enteredNum,
    applicableMinimumCTC: applicableMin,
    applicable_min_ctc: applicableMin,
    courseDurationInfo,
    stateMinWage,
    userMessage: null,
    message: null,
  }
}

/**
 * Formats a short dashboard notice for CTC validation failures.
 *
 * Title: CTC Validation Failed
 * Message: The monthly CTC for [Employer Name] is below the required minimum of [Applicable Minimum CTC].
 * Please update the CTC before submitting the Candidate Dossier.
 *
 * Handles employer name limiting:
 * - 1 employer: Display its name.
 * - 2 employers: Display both names.
 * - More than 2: Display the first two names followed by "+ N more".
 *
 * @param {Array<{ emp: object, ctcVal: object }>} ctcFailures
 * @returns {{ title: string, message: string }}
 */
export function formatShortCtcNotice(ctcFailures) {
  if (!ctcFailures || ctcFailures.length === 0) return null

  const getEmpName = (emp) =>
    (emp?.employer_name && emp.employer_name.trim()) ? emp.employer_name.trim() : 'Employer'

  const formatMin = (val) =>
    val != null ? `₹${Math.round(val).toLocaleString('en-IN')}` : 'the required minimum'

  const createNotice = (title, message) => ({
    title,
    message,
    toString() {
      return `${this.title}: ${this.message}`
    },
  })

  const totalCount = ctcFailures.length

  if (totalCount === 1) {
    const { emp, ctcVal } = ctcFailures[0]
    const empName = getEmpName(emp)
    const appMinStr = formatMin(ctcVal?.applicableMinimumCTC)

    return createNotice(
      'CTC Validation Failed',
      `The monthly CTC for ${empName} is below the required minimum of ${appMinStr}. Please update the CTC before submitting the Candidate Dossier.`
    )
  }

  // Check if all failing employers have the same applicable minimum CTC
  const allSameMin = ctcFailures.every(
    (f) => f.ctcVal?.applicableMinimumCTC === ctcFailures[0].ctcVal?.applicableMinimumCTC
  )

  let subjectStr = ''
  if (totalCount === 2) {
    const name1 = getEmpName(ctcFailures[0].emp)
    const name2 = getEmpName(ctcFailures[1].emp)
    subjectStr = `${name1} and ${name2}`
  } else {
    // More than 2: Display the first two names followed by "+ N more"
    const name1 = getEmpName(ctcFailures[0].emp)
    const name2 = getEmpName(ctcFailures[1].emp)
    const extraCount = totalCount - 2
    subjectStr = `${name1}, ${name2} (+${extraCount} more)`
  }

  if (allSameMin && ctcFailures[0].ctcVal?.applicableMinimumCTC != null) {
    const appMinStr = formatMin(ctcFailures[0].ctcVal?.applicableMinimumCTC)
    return createNotice(
      'CTC Validation Failed',
      `The monthly CTC for ${subjectStr} is below the required minimum of ${appMinStr}. Please update the CTC before submitting the Candidate Dossier.`
    )
  }

  return createNotice(
    'CTC Validation Failed',
    `The monthly CTC for ${subjectStr} is below the required minimum. Please update the CTC before submitting the Candidate Dossier.`
  )
}
