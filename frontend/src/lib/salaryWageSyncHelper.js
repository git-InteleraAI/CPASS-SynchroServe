/**
 * CPASS Salary & Employer Minimum Wage Synchronization Helper
 *
 * Provides pure, deterministic functions for:
 * 1. Associating salary rows with specific employers (multi-employer isolation).
 * 2. Immediately invalidating linked salary rows when place of work is typed/cleared.
 * 3. Synchronizing salary rows when location detection completes (IDENTIFIED, UNSUPPORTED, AMBIGUOUS, UNRESOLVED).
 * 4. Determining state and error status for an individual salary row.
 */

export function isSalaryLinkedToEmployer(salaryRow, empId, employers) {
  if (!salaryRow || !empId) return false
  if (salaryRow.employer_id === empId) return true
  // If employer_id is not set on salary row, it associates with the single employer if only 1 exists
  if (!salaryRow.employer_id && (!employers || employers.length <= 1)) return true
  return false
}

export function getImmediateInvalidatedSalaryRows(salaryRows, targetEmpId, employers, isLoading) {
  if (!Array.isArray(salaryRows)) return []
  return salaryRows.map((s) => {
    if (!isSalaryLinkedToEmployer(s, targetEmpId, employers)) return s
    return {
      ...s,
      minimum_wage: null,
      minimum_wage_state: null,
      minimum_wage_effective_month: null,
      minimum_wage_effective_year: null,
      min_wage_loading: Boolean(isLoading),
      min_wage_error: null,
    }
  })
}

export function syncSalaryRowsOnLocationDetection(salaryRows, targetEmpId, employers, detectionResult) {
  if (!Array.isArray(salaryRows)) return []
  const status = detectionResult?.status
  const detectedState = detectionResult?.detected_state || null

  return salaryRows.map((s) => {
    if (!isSalaryLinkedToEmployer(s, targetEmpId, employers)) return s

    if (status === 'UNSUPPORTED_STATE') {
      const errMsg = `${detectedState || 'State'} is not in the statutory 13-state minimum wage register.`
      return {
        ...s,
        minimum_wage: null,
        minimum_wage_state: detectedState,
        minimum_wage_effective_month: null,
        minimum_wage_effective_year: null,
        min_wage_loading: false,
        min_wage_error: errMsg,
      }
    }

    if (status === 'AMBIGUOUS') {
      return {
        ...s,
        minimum_wage: null,
        minimum_wage_state: null,
        minimum_wage_effective_month: null,
        minimum_wage_effective_year: null,
        min_wage_loading: false,
        min_wage_error: 'Location ambiguous - select state',
      }
    }

    if (status === 'IDENTIFIED' && detectedState) {
      if (!s.month || !s.year) {
        return {
          ...s,
          minimum_wage: null,
          minimum_wage_state: detectedState,
          minimum_wage_effective_month: null,
          minimum_wage_effective_year: null,
          min_wage_loading: false,
          min_wage_error: null,
        }
      }
      return {
        ...s,
        minimum_wage_state: detectedState,
        min_wage_loading: true,
        min_wage_error: null,
      }
    }

    // UNRESOLVED, cleared, or error
    return {
      ...s,
      minimum_wage: null,
      minimum_wage_state: null,
      minimum_wage_effective_month: null,
      minimum_wage_effective_year: null,
      min_wage_loading: false,
      min_wage_error: null,
    }
  })
}

export function determineSalaryRowState(salaryRow, employers, explicitState) {
  if (explicitState) {
    return { canLookup: true, targetState: explicitState, error: null, isLoading: false }
  }

  const curEmps = employers || []
  const empId = salaryRow?.employer_id
  const emp = curEmps.find((e) => e.id === empId) || (curEmps.length === 1 ? curEmps[0] : null)

  if (!emp) {
    return { canLookup: false, targetState: null, error: null, isLoading: false }
  }

  if (emp.work_state && emp.work_state_detection_status === 'IDENTIFIED') {
    return { canLookup: true, targetState: emp.work_state, error: null, isLoading: false }
  }

  if (emp.work_state_detection_status === 'UNSUPPORTED_STATE') {
    const errMsg = `${emp.work_state || 'State'} is not in the statutory 13-state minimum wage register.`
    return { canLookup: false, targetState: emp.work_state || null, error: errMsg, isLoading: false }
  }

  if (emp.work_state_detection_status === 'AMBIGUOUS') {
    return { canLookup: false, targetState: null, error: 'Location ambiguous - select state', isLoading: false }
  }

  const isEmpLoading = Boolean(emp.location_loading || emp.employer_wage_loading)
  return { canLookup: false, targetState: null, error: null, isLoading: isEmpLoading }
}

