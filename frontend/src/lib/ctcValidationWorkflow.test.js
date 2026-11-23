import assert from 'node:assert'
import {
  calculateCourseDuration,
  calculateApplicableMinimumCTC,
  validateEmployerMonthlyCTC,
  formatShortCtcNotice,
} from './courseDurationHelper.js'

/**
 * Simulates L1Home.jsx handleSubmitAuditStatement validation step.
 * Returns { allowed: boolean, modal: object | null, ctcNotice: object | null, error: string }
 */
function simulatePreviewValidation({ validEmployers, courseDurationInfo }) {
  const ctcFailures = []
  for (const emp of validEmployers) {
    const ctcVal = validateEmployerMonthlyCTC(
      emp.monthly_ctc,
      courseDurationInfo,
      emp.minimum_wages,
      emp.employer_name
    )
    if (!ctcVal.isValid) {
      ctcFailures.push({ emp, ctcVal })
    }
  }

  if (ctcFailures.length > 0) {
    const firstFailure = ctcFailures[0]
    const shortNotice = formatShortCtcNotice(ctcFailures)
    return {
      allowed: false,
      ctcNotice: shortNotice,
      error: '', // error state in L1Home remains a string, reset to empty
      modal: {
        isOpen: true,
        title: firstFailure.ctcVal.title || 'Minimum CTC Requirement Not Met',
        message: firstFailure.ctcVal.userMessage,
        employerName: firstFailure.emp.employer_name || 'Employer',
        courseDuration: courseDurationInfo?.label,
        courseMinCtc: courseDurationInfo?.minimum_ctc,
        stateMinWage: firstFailure.emp.minimum_wages,
        workState: firstFailure.emp.work_state || firstFailure.emp.place_of_work,
        applicableMinCtc: firstFailure.ctcVal.applicableMinimumCTC,
        enteredCtc: firstFailure.emp.monthly_ctc,
        deficit: (firstFailure.ctcVal.applicableMinimumCTC || 0) - (Number(firstFailure.emp.monthly_ctc) || 0),
      },
    }
  }
  return { allowed: true, modal: null, ctcNotice: null, error: '' }
}

/**
 * Simulates L1Home.jsx handleConfirmFinalSubmit validation step.
 * Returns { allowed: boolean, modal: object | null, ctcNotice: object | null, error: string }
 */
function simulateFinalSubmitValidation({ employerList, courseDurationInfo }) {
  const ctcFailures = []
  for (const emp of employerList.filter((e) => e.employer_name && e.employer_name.trim())) {
    const ctcVal = validateEmployerMonthlyCTC(
      emp.monthly_ctc,
      courseDurationInfo,
      emp.minimum_wages,
      emp.employer_name
    )
    if (!ctcVal.isValid) {
      ctcFailures.push({ emp, ctcVal })
    }
  }

  if (ctcFailures.length > 0) {
    const firstFailure = ctcFailures[0]
    const shortNotice = formatShortCtcNotice(ctcFailures)
    return {
      allowed: false,
      ctcNotice: shortNotice,
      error: '', // error state in L1Home remains a string, reset to empty
      modal: {
        isOpen: true,
        title: firstFailure.ctcVal.title || 'Minimum CTC Requirement Not Met',
        message: firstFailure.ctcVal.userMessage,
        employerName: firstFailure.emp.employer_name || 'Employer',
        courseDuration: courseDurationInfo?.label,
        courseMinCtc: courseDurationInfo?.minimum_ctc,
        stateMinWage: firstFailure.emp.minimum_wages,
        workState: firstFailure.emp.work_state || firstFailure.emp.place_of_work,
        applicableMinCtc: firstFailure.ctcVal.applicableMinimumCTC,
        enteredCtc: firstFailure.emp.monthly_ctc,
        deficit: (firstFailure.ctcVal.applicableMinimumCTC || 0) - (Number(firstFailure.emp.monthly_ctc) || 0),
      },
    }
  }
  return { allowed: true, modal: null, ctcNotice: null, error: '' }
}

function runIntegrationTests() {
  console.log('--- Running CTC Validation Integration Tests (Preview & Final Submit) ---')

  const course6m = calculateCourseDuration('2024-01-01', '2024-06-30') // 6 months, min ₹8,000

  // 1. CTC below applicable minimum blocks preview and final submit (1 employer)
  {
    const employers = [
      { id: 'emp_1', employer_name: 'Gujarat Tech', place_of_work: 'Gujarat', work_state: 'GUJARAT', monthly_ctc: 12950, minimum_wages: 15850 }
    ]

    const previewRes = simulatePreviewValidation({ validEmployers: employers, courseDurationInfo: course6m })
    assert.strictEqual(previewRes.allowed, false, 'Preview should be blocked when CTC < 15,850')
    assert.strictEqual(previewRes.error, '', 'error state in L1Home must remain empty string')
    assert.strictEqual(previewRes.ctcNotice.title, 'CTC Validation Failed')
    assert.strictEqual(
      previewRes.ctcNotice.message,
      'The monthly CTC for Gujarat Tech is below the required minimum of ₹15,850. Please update the CTC before submitting the Candidate Dossier.'
    )
    assert.ok(!previewRes.ctcNotice.message.includes('Course Duration:'), 'Dashboard notice must not contain course duration breakdown')
    assert.ok(!previewRes.ctcNotice.message.includes('State Minimum Wage:'), 'Dashboard notice must not contain state wage breakdown')
    assert.strictEqual(previewRes.modal.applicableMinCtc, 15850)
    assert.strictEqual(previewRes.modal.enteredCtc, 12950)
    assert.strictEqual(previewRes.modal.deficit, 2900)
    assert.ok(!JSON.stringify(previewRes.modal).includes('[object Object]'), 'No [object Object] in modal')

    const submitRes = simulateFinalSubmitValidation({ employerList: employers, courseDurationInfo: course6m })
    assert.strictEqual(submitRes.allowed, false, 'Final submit should be blocked when CTC < 15,850')
    assert.strictEqual(submitRes.error, '', 'error state remains string')
    assert.strictEqual(submitRes.ctcNotice.title, 'CTC Validation Failed')
    assert.ok(submitRes.ctcNotice.message.includes('below the required minimum of ₹15,850'))
    console.log('✓ Test 1: CTC below applicable minimum blocks preview and final submit passed')
  }

  // 2. CTC exactly equal to minimum allows preview and final submit, clears ctcNotice
  {
    const employers = [
      { id: 'emp_1', employer_name: 'Gujarat Tech', place_of_work: 'Gujarat', work_state: 'GUJARAT', monthly_ctc: 15850, minimum_wages: 15850 }
    ]

    const previewRes = simulatePreviewValidation({ validEmployers: employers, courseDurationInfo: course6m })
    assert.strictEqual(previewRes.allowed, true, 'Preview should be allowed when CTC == 15,850')
    assert.strictEqual(previewRes.ctcNotice, null, 'ctcNotice should be cleared (null) on success')
    assert.strictEqual(previewRes.modal, null)

    const submitRes = simulateFinalSubmitValidation({ employerList: employers, courseDurationInfo: course6m })
    assert.strictEqual(submitRes.allowed, true, 'Final submit should be allowed when CTC == 15,850')
    assert.strictEqual(submitRes.ctcNotice, null, 'ctcNotice should be cleared (null) on success')
    console.log('✓ Test 2: CTC exactly equal to minimum allows preview and final submit passed')
  }

  // 3. CTC above minimum allows preview and final submit, clears ctcNotice
  {
    const employers = [
      { id: 'emp_1', employer_name: 'Gujarat Tech', place_of_work: 'Gujarat', work_state: 'GUJARAT', monthly_ctc: 20950, minimum_wages: 15850 }
    ]

    const previewRes = simulatePreviewValidation({ validEmployers: employers, courseDurationInfo: course6m })
    assert.strictEqual(previewRes.allowed, true, 'Preview should be allowed when CTC > 15,850')
    assert.strictEqual(previewRes.ctcNotice, null)

    const submitRes = simulateFinalSubmitValidation({ employerList: employers, courseDurationInfo: course6m })
    assert.strictEqual(submitRes.allowed, true, 'Final submit should be allowed when CTC > 15,850')
    assert.strictEqual(submitRes.ctcNotice, null)
    console.log('✓ Test 3: CTC above minimum allows preview and final submit passed')
  }

  // 4. Unsupported state (Karnataka) with sufficient course-based CTC allows submission
  {
    const employers = [
      { id: 'emp_1', employer_name: 'Bengaluru Tech', place_of_work: 'Karnataka', work_state: 'KARNATAKA', monthly_ctc: 9000, minimum_wages: null }
    ]

    const previewRes = simulatePreviewValidation({ validEmployers: employers, courseDurationInfo: course6m })
    assert.strictEqual(previewRes.allowed, true, 'Preview should allow unsupported state when CTC >= ₹8,000')
    assert.strictEqual(previewRes.ctcNotice, null)

    const submitRes = simulateFinalSubmitValidation({ employerList: employers, courseDurationInfo: course6m })
    assert.strictEqual(submitRes.allowed, true, 'Final submit should allow unsupported state when CTC >= ₹8,000')
    assert.strictEqual(submitRes.ctcNotice, null)
    console.log('✓ Test 4: Unsupported state with sufficient course-based CTC allows submission passed')
  }

  // 5. Multi-employer notices limiting (2 employers -> both names; 3+ employers -> first 2 + (+N more))
  {
    // 2 employers
    const twoEmployers = [
      { id: 'emp_1', employer_name: 'Alpha Ltd', place_of_work: 'Gujarat', monthly_ctc: 12000, minimum_wages: 15850 },
      { id: 'emp_2', employer_name: 'Beta Pvt', place_of_work: 'Andhra Pradesh', monthly_ctc: 11000, minimum_wages: 14250 },
    ]
    const res2 = simulatePreviewValidation({ validEmployers: twoEmployers, courseDurationInfo: course6m })
    assert.strictEqual(res2.allowed, false)
    assert.ok(res2.ctcNotice.message.includes('Alpha Ltd and Beta Pvt'))
    assert.ok(!res2.ctcNotice.message.includes('+'), '2 employers should not have + more')

    // 3 employers -> first 2 + (+1 more)
    const threeEmployers = [
      { id: 'emp_1', employer_name: 'Alpha Ltd', place_of_work: 'Gujarat', monthly_ctc: 12000, minimum_wages: 15850 },
      { id: 'emp_2', employer_name: 'Beta Pvt', place_of_work: 'Andhra Pradesh', monthly_ctc: 11000, minimum_wages: 14250 },
      { id: 'emp_3', employer_name: 'Gamma Corp', place_of_work: 'Delhi', monthly_ctc: 10000, minimum_wages: 18000 },
    ]
    const res3 = simulatePreviewValidation({ validEmployers: threeEmployers, courseDurationInfo: course6m })
    assert.strictEqual(res3.allowed, false)
    assert.ok(res3.ctcNotice.message.includes('Alpha Ltd, Beta Pvt (+1 more)'))
    assert.ok(!res3.ctcNotice.message.includes('Gamma Corp'), 'Gamma Corp should be collapsed into +1 more')

    // 5 employers -> first 2 + (+3 more)
    const fiveEmployers = [
      { id: 'e1', employer_name: 'E1', place_of_work: 'Gujarat', monthly_ctc: 12000, minimum_wages: 15850 },
      { id: 'e2', employer_name: 'E2', place_of_work: 'Gujarat', monthly_ctc: 12000, minimum_wages: 15850 },
      { id: 'e3', employer_name: 'E3', place_of_work: 'Gujarat', monthly_ctc: 12000, minimum_wages: 15850 },
      { id: 'e4', employer_name: 'E4', place_of_work: 'Gujarat', monthly_ctc: 12000, minimum_wages: 15850 },
      { id: 'e5', employer_name: 'E5', place_of_work: 'Gujarat', monthly_ctc: 12000, minimum_wages: 15850 },
    ]
    const res5 = simulatePreviewValidation({ validEmployers: fiveEmployers, courseDurationInfo: course6m })
    assert.strictEqual(res5.allowed, false)
    assert.ok(res5.ctcNotice.message.includes('E1, E2 (+3 more)'))
    console.log('✓ Test 5: Multi-employer limiting (1, 2, and 3+ employers) passed')
  }

  // 6. Dynamic field modification (monthly_ctc, place_of_work) clears ctcNotice
  {
    let currentCtcNotice = { title: 'CTC Validation Failed', message: 'The monthly CTC...' }
    function simulateFieldChange(field) {
      if (field === 'monthly_ctc' || field === 'place_of_work') {
        currentCtcNotice = null
      }
    }

    simulateFieldChange('designation')
    assert.notStrictEqual(currentCtcNotice, null, 'Updating designation should not clear ctcNotice')

    simulateFieldChange('monthly_ctc')
    assert.strictEqual(currentCtcNotice, null, 'Updating monthly_ctc must clear ctcNotice')

    currentCtcNotice = { title: 'CTC Validation Failed', message: 'The monthly CTC...' }
    simulateFieldChange('place_of_work')
    assert.strictEqual(currentCtcNotice, null, 'Updating place_of_work must clear ctcNotice')
    console.log('✓ Test 6: Field change on monthly_ctc / place_of_work clears ctcNotice passed')
  }

  // 7. Changing Gujarat to Andhra Pradesh dynamically recalculates validation status
  {
    const emp = { id: 'emp_1', employer_name: 'Southern Tech', place_of_work: 'Gujarat', work_state: 'GUJARAT', monthly_ctc: 15000, minimum_wages: 15850 }

    // In Gujarat: ₹15,000 < ₹15,850 -> BLOCKED
    const resGujarat = simulatePreviewValidation({ validEmployers: [emp], courseDurationInfo: course6m })
    assert.strictEqual(resGujarat.allowed, false)
    assert.strictEqual(resGujarat.modal.applicableMinCtc, 15850)

    // User changes to Andhra Pradesh: minimum wage becomes ₹14,250
    emp.place_of_work = 'Andhra Pradesh'
    emp.work_state = 'ANDHRA PRADESH'
    emp.minimum_wages = 14250

    // In AP: ₹15,000 >= ₹14,250 -> ALLOWED
    const resAP = simulatePreviewValidation({ validEmployers: [emp], courseDurationInfo: course6m })
    assert.strictEqual(resAP.allowed, true)
    assert.strictEqual(resAP.ctcNotice, null)
    console.log('✓ Test 7: Dynamic state switch Gujarat -> AP recalculates validation status passed')
  }

  // 8. Formatting test: ensure no [object Object] or undefined in formatted display
  {
    const calc = calculateApplicableMinimumCTC(8000, 15850)
    const appMin = calc.applicable_minimum_ctc ?? calc.applicableMinimumCTC
    const formatted = `₹${Math.round(appMin).toLocaleString('en-IN')}`
    assert.strictEqual(formatted, '₹15,850')
    assert.ok(!formatted.includes('[object Object]'))
    assert.ok(!formatted.includes('undefined'))
    console.log('✓ Test 8: Formatted minimum string is strictly readable passed')
  }

  console.log('All CTC Validation Integration Tests passed successfully!')
}

runIntegrationTests()
