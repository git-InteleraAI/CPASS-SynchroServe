import assert from 'node:assert'
import {
  calculateCourseDuration,
  calculateApplicableMinimumCTC,
  validateEmployerMonthlyCTC,
  formatShortCtcNotice,
  INDIAN_STATES_28,
  INDIAN_UTS_8,
  ALL_36_INDIAN_STATES_AND_UTS,
  SUPPORTED_13_STATES,
} from './courseDurationHelper.js'

function runTests() {
  console.log('--- Running courseDurationHelper tests ---')

  // ---------------------------------------------------------------------------
  // Category 1: Course Duration Inference Tests
  // ---------------------------------------------------------------------------

  // Scenario 1: Exact 3-month batch
  {
    const res = calculateCourseDuration('2024-01-01', '2024-03-31')
    assert.strictEqual(res.status, 'DETERMINED')
    assert.strictEqual(res.months, 3)
    assert.strictEqual(res.label, '3 Months')
    assert.strictEqual(res.minimum_ctc, 6000)
    console.log('✓ Scenario 1: Exact 3-month batch passed')
  }

  // Scenario 2: Exact 6-month batch
  {
    const res = calculateCourseDuration('2024-01-01', '2024-06-30')
    assert.strictEqual(res.status, 'DETERMINED')
    assert.strictEqual(res.months, 6)
    assert.strictEqual(res.label, '6 Months')
    assert.strictEqual(res.minimum_ctc, 8000)
    console.log('✓ Scenario 2: Exact 6-month batch passed')
  }

  // Scenario 3: Exact 9-month batch
  {
    const res = calculateCourseDuration('2024-01-01', '2024-09-30')
    assert.strictEqual(res.status, 'DETERMINED')
    assert.strictEqual(res.months, 9)
    assert.strictEqual(res.label, '9 Months')
    assert.strictEqual(res.minimum_ctc, 12000)
    console.log('✓ Scenario 3: Exact 9-month batch passed')
  }

  // Scenario 4: Exact 12-month batch (leap year)
  {
    const res = calculateCourseDuration('2024-01-01', '2024-12-31')
    assert.strictEqual(res.status, 'DETERMINED')
    assert.strictEqual(res.months, 12)
    assert.strictEqual(res.label, '12 Months')
    assert.strictEqual(res.minimum_ctc, 15000)
    console.log('✓ Scenario 4: Exact 12-month batch passed')
  }

  // Scenario 5: Batch duration slightly different from standard dates
  {
    // 97 days (approx 3.2 months) -> matches 3 Months
    const res3 = calculateCourseDuration('2024-01-10', '2024-04-15')
    assert.strictEqual(res3.months, 3)
    assert.strictEqual(res3.minimum_ctc, 6000)

    // 195 days (approx 6.4 months) -> matches 6 Months
    const res6 = calculateCourseDuration('2024-01-15', '2024-07-27')
    assert.strictEqual(res6.months, 6)
    assert.strictEqual(res6.minimum_ctc, 8000)

    // 285 days (approx 9.3 months) -> matches 9 Months
    const res9 = calculateCourseDuration('2024-01-01', '2024-10-11')
    assert.strictEqual(res9.months, 9)
    assert.strictEqual(res9.minimum_ctc, 12000)

    // 380 days (approx 12.5 months) -> matches 12 Months
    const res12 = calculateCourseDuration('2024-01-01', '2025-01-15')
    assert.strictEqual(res12.months, 12)
    assert.strictEqual(res12.minimum_ctc, 15000)
    console.log('✓ Scenario 5: Slightly different dates passed')
  }

  // Scenario 6: Missing start date
  {
    const res = calculateCourseDuration(null, '2024-06-30')
    assert.strictEqual(res.status, 'MISSING_DATES')
    assert.strictEqual(res.months, null)
    assert.strictEqual(res.minimum_ctc, null)
    assert.ok(res.message.includes('Course duration could not be reliably determined'))
    console.log('✓ Scenario 6: Missing start date passed')
  }

  // Scenario 7: Missing end date
  {
    const res = calculateCourseDuration('2024-01-01', 'Not Available')
    assert.strictEqual(res.status, 'MISSING_DATES')
    assert.strictEqual(res.months, null)
    assert.strictEqual(res.minimum_ctc, null)
    console.log('✓ Scenario 7: Missing end date passed')
  }

  // Scenario 8: Invalid dates (end < start)
  {
    const res = calculateCourseDuration('2024-06-30', '2024-01-01')
    assert.strictEqual(res.status, 'INVALID_DATES')
    assert.strictEqual(res.months, null)
    assert.strictEqual(res.minimum_ctc, null)
    console.log('✓ Scenario 8: Invalid dates passed')
  }

  // Scenario 9: Unmatched duration (e.g. 20 days or 500 days)
  {
    const resShort = calculateCourseDuration('2024-01-01', '2024-01-20')
    assert.strictEqual(resShort.status, 'UNMATCHED_DURATION')
    assert.strictEqual(resShort.months, null)
    assert.strictEqual(resShort.minimum_ctc, null)

    const resLong = calculateCourseDuration('2024-01-01', '2025-06-30')
    assert.strictEqual(resLong.status, 'UNMATCHED_DURATION')
    assert.strictEqual(resLong.months, null)
    assert.strictEqual(resLong.minimum_ctc, null)
    console.log('✓ Scenario 9: Unmatched duration passed')
  }

  // ---------------------------------------------------------------------------
  // Category 2: Minimum Wage & Higher-of-Two Tests
  // ---------------------------------------------------------------------------

  // Test 1: Course minimum higher than state minimum (6 months ₹8,000 vs State ₹7,000 -> ₹8,000)
  {
    const calc = calculateApplicableMinimumCTC(8000, 7000)
    assert.strictEqual(calc.applicable_minimum_ctc, 8000)
    assert.strictEqual(calc.governing_rule, 'COURSE_DURATION_HIGHER')
    console.log('✓ Test 1: Course minimum higher than state passed')
  }

  // Test 2: State minimum higher than course minimum (3 months ₹6,000 vs State ₹9,000 -> ₹9,000)
  {
    const calc = calculateApplicableMinimumCTC(6000, 9000)
    assert.strictEqual(calc.applicable_minimum_ctc, 9000)
    assert.strictEqual(calc.governing_rule, 'STATE_WAGE_HIGHER')
    console.log('✓ Test 2: State minimum higher than course passed')
  }

  // Test 3: Both amounts equal (₹8,000 vs ₹8,000 -> ₹8,000)
  {
    const calc = calculateApplicableMinimumCTC(8000, 8000)
    assert.strictEqual(calc.applicable_minimum_ctc, 8000)
    assert.strictEqual(calc.governing_rule, 'EQUAL_AMOUNTS')
    console.log('✓ Test 3: Both amounts equal passed')
  }

  // Test 4: Monthly CTC below applicable minimum -> blocks submission
  {
    const courseInfo = { months: 6, label: '6 Months', minimum_ctc: 8000 }
    const res = validateEmployerMonthlyCTC(7500, courseInfo, 10000, 'Acme Corp')
    assert.strictEqual(res.isValid, false)
    assert.strictEqual(res.applicableMinimumCTC, 10000)
    assert.ok(res.userMessage.includes('Course Duration: 6 Months'))
    assert.ok(res.userMessage.includes('Course Minimum CTC: ₹8,000'))
    assert.ok(res.userMessage.includes('State Minimum Wage: ₹10,000'))
    assert.ok(res.userMessage.includes('Applicable Minimum CTC: ₹10,000'))
    assert.ok(res.userMessage.includes('Entered Monthly CTC: ₹7,500'))
    console.log('✓ Test 4: Monthly CTC below applicable minimum blocks submission passed')
  }

  // Test 5: Monthly CTC exactly equal to applicable minimum -> permits submission
  {
    const courseInfo = { months: 6, label: '6 Months', minimum_ctc: 8000 }
    const res = validateEmployerMonthlyCTC(10000, courseInfo, 10000)
    assert.strictEqual(res.isValid, true)
    assert.strictEqual(res.applicableMinimumCTC, 10000)
    console.log('✓ Test 5: Monthly CTC exactly equal permits submission passed')
  }

  // Test 6: Monthly CTC above applicable minimum -> permits submission
  {
    const courseInfo = { months: 6, label: '6 Months', minimum_ctc: 8000 }
    const res = validateEmployerMonthlyCTC(15000, courseInfo, 10000)
    assert.strictEqual(res.isValid, true)
    console.log('✓ Test 6: Monthly CTC above applicable minimum permits submission passed')
  }

  // Test 7: Supported state with historical wage data (e.g. Telangana ₹16,950, Course 3m ₹6,000 -> ₹16,950)
  {
    const courseInfo = { months: 3, label: '3 Months', minimum_ctc: 6000 }
    const calc = calculateApplicableMinimumCTC(courseInfo.minimum_ctc, 16950)
    assert.strictEqual(calc.applicable_minimum_ctc, 16950)
    console.log('✓ Test 7: Supported state historical wage applied passed')
  }

  // Test 8: Unsupported state without wage data (e.g. Maharashtra null wage, Course 6m ₹8,000 -> ₹8,000)
  {
    const courseInfo = { months: 6, label: '6 Months', minimum_ctc: 8000 }
    const calc = calculateApplicableMinimumCTC(courseInfo.minimum_ctc, null)
    assert.strictEqual(calc.applicable_minimum_ctc, 8000)
    assert.strictEqual(calc.governing_rule, 'COURSE_DURATION_ONLY')

    // CTC 8,500 meets requirement -> valid
    const resPass = validateEmployerMonthlyCTC(8500, courseInfo, null)
    assert.strictEqual(resPass.isValid, true)

    // CTC 7,000 below requirement -> invalid with clear popup message
    const resFail = validateEmployerMonthlyCTC(7000, courseInfo, null)
    assert.strictEqual(resFail.isValid, false)
    assert.ok(resFail.userMessage.includes('State Minimum Wage: Unavailable'))
    console.log('✓ Test 8: Unsupported state with course minimum passed')
  }

  // Test 9: State wage data unavailable but course duration available
  {
    const courseInfo = { months: 12, label: '12 Months', minimum_ctc: 15000 }
    const res = validateEmployerMonthlyCTC(16000, courseInfo, null)
    assert.strictEqual(res.isValid, true)
    assert.strictEqual(res.applicableMinimumCTC, 15000)
    console.log('✓ Test 9: State wage unavailable but course duration available passed')
  }

  // Test 10: Both state wage and course duration unavailable -> does not block submission
  {
    const courseInfo = { months: null, label: null, minimum_ctc: null }
    const res = validateEmployerMonthlyCTC(0, courseInfo, null)
    assert.strictEqual(res.isValid, true)
    assert.strictEqual(res.applicableMinimumCTC, null)
    console.log('✓ Test 10: Both unavailable does not block submission passed')
  }

  // ---------------------------------------------------------------------------
  // Category 3: States & UTs Master List Verification
  // ---------------------------------------------------------------------------
  {
    assert.strictEqual(INDIAN_STATES_28.length, 28, 'Must contain exactly 28 states')
    assert.strictEqual(INDIAN_UTS_8.length, 8, 'Must contain exactly 8 union territories')
    assert.strictEqual(ALL_36_INDIAN_STATES_AND_UTS.length, 36, 'Must contain exactly 36 states and UTs')
    assert.strictEqual(SUPPORTED_13_STATES.size, 13, 'Must contain 13 statutory master states')
    assert.ok(INDIAN_STATES_28.includes('Maharashtra'))
    assert.ok(INDIAN_STATES_28.includes('Karnataka'))
    assert.ok(INDIAN_STATES_28.includes('Tamil Nadu'))
    assert.ok(INDIAN_UTS_8.includes('Delhi'))
    assert.ok(INDIAN_UTS_8.includes('Chandigarh'))
    console.log('✓ Category 3: 28 States and 8 UTs master list verified')
  }

  // ---------------------------------------------------------------------------
  // Category 4: Specific Integration & UI Test Cases
  // ---------------------------------------------------------------------------

  // Test Case A: ₹12,950 CTC against ₹15,850 minimum -> Below Min
  {
    const courseInfo = { months: 6, label: '6 Months', minimum_ctc: 8000 }
    const res = validateEmployerMonthlyCTC(12950, courseInfo, 15850, 'Gujarat Corp')
    assert.strictEqual(res.isValid, false, '₹12,950 should be invalid against ₹15,850')
    assert.strictEqual(res.applicableMinimumCTC, 15850)
    assert.ok(res.userMessage.includes('Applicable Minimum CTC: ₹15,850'))
    assert.ok(res.userMessage.includes('Entered Monthly CTC: ₹12,950'))
    assert.ok(!res.userMessage.includes('[object Object]'), 'No [object Object] in userMessage')
    assert.ok(!res.userMessage.includes('undefined'), 'No undefined in userMessage')
    console.log('✓ Test Case A: ₹12,950 CTC against ₹15,850 minimum -> Below Min passed')
  }

  // Test Case B: ₹15,850 CTC against ₹15,850 minimum -> Valid
  {
    const courseInfo = { months: 6, label: '6 Months', minimum_ctc: 8000 }
    const res = validateEmployerMonthlyCTC(15850, courseInfo, 15850, 'Gujarat Corp')
    assert.strictEqual(res.isValid, true, '₹15,850 should be valid against ₹15,850')
    assert.strictEqual(res.applicableMinimumCTC, 15850)
    assert.strictEqual(res.userMessage, null)
    console.log('✓ Test Case B: ₹15,850 CTC against ₹15,850 minimum -> Valid passed')
  }

  // Test Case C: ₹20,950 CTC against ₹15,850 minimum -> Valid
  {
    const courseInfo = { months: 6, label: '6 Months', minimum_ctc: 8000 }
    const res = validateEmployerMonthlyCTC(20950, courseInfo, 15850, 'Gujarat Corp')
    assert.strictEqual(res.isValid, true, '₹20,950 should be valid against ₹15,850')
    assert.strictEqual(res.applicableMinimumCTC, 15850)
    assert.strictEqual(res.userMessage, null)
    console.log('✓ Test Case C: ₹20,950 CTC against ₹15,850 minimum -> Valid passed')
  }

  // Test Case D: Dynamic state change: Gujarat (₹15,850) -> Andhra Pradesh (₹14,250)
  {
    const courseInfo = { months: 6, label: '6 Months', minimum_ctc: 8000 }
    const monthlyCTC = 15000

    // Initial state: Gujarat (wage: 15,850) -> CTC 15,000 is BELOW MIN
    const resGujarat = validateEmployerMonthlyCTC(monthlyCTC, courseInfo, 15850, 'Multi State Employer')
    assert.strictEqual(resGujarat.isValid, false)
    assert.strictEqual(resGujarat.applicableMinimumCTC, 15850)

    // User changes place of work to Andhra Pradesh (wage: 14,250) -> CTC 15,000 becomes VALID
    const resAP = validateEmployerMonthlyCTC(monthlyCTC, courseInfo, 14250, 'Multi State Employer')
    assert.strictEqual(resAP.isValid, true)
    assert.strictEqual(resAP.applicableMinimumCTC, 14250)
    console.log('✓ Test Case D: Change Gujarat to Andhra Pradesh refreshed applicable minimum and status correctly passed')
  }

  // Test Case E: Verify both preview and final submit consume isValid, userMessage, and applicableMinimumCTC
  {
    const courseInfo = { months: 6, label: '6 Months', minimum_ctc: 8000 }
    const res = validateEmployerMonthlyCTC(7000, courseInfo, 12000, 'Test Employer')
    // Check that properties used in L1Home.jsx are all present, non-undefined, and correct
    assert.strictEqual(typeof res.isValid, 'boolean')
    assert.strictEqual(res.isValid, false)
    assert.strictEqual(typeof res.userMessage, 'string')
    assert.strictEqual(typeof res.applicableMinimumCTC, 'number')
    assert.strictEqual(res.applicableMinimumCTC, 12000)
    // Verify backward compatibility aliases
    assert.strictEqual(res.valid, res.isValid)
    assert.strictEqual(res.message, res.userMessage)
    assert.strictEqual(res.applicable_min_ctc, res.applicableMinimumCTC)
    console.log('✓ Test Case E: Preview and final submission contract properties verified')
  }

  // ---------------------------------------------------------------------------
  // Category 5: Short Dashboard Notice Tests
  // ---------------------------------------------------------------------------

  // Test Case F: Single employer short notice formatting
  {
    const failures = [
      {
        emp: { employer_name: 'Acme Technologies' },
        ctcVal: { applicableMinimumCTC: 15850 }
      }
    ]
    const notice = formatShortCtcNotice(failures)
    assert.strictEqual(notice.title, 'CTC Validation Failed')
    assert.strictEqual(
      notice.message,
      'The monthly CTC for Acme Technologies is below the required minimum of ₹15,850. Please update the CTC before submitting the Candidate Dossier.'
    )
    assert.ok(!notice.message.includes('Course Duration:'), 'No course duration in dashboard notice')
    assert.ok(!notice.message.includes('State Minimum Wage:'), 'No state wage breakdown in dashboard notice')
    assert.ok(!notice.message.includes('[object Object]'), 'No [object Object] in notice')
    assert.ok(notice.toString().startsWith('CTC Validation Failed:'))
    console.log('✓ Test Case F: Single employer short notice formatting passed')
  }

  // Test Case G: 2 employers with same minimum (both names displayed)
  {
    const failures = [
      { emp: { employer_name: 'Alpha Ltd' }, ctcVal: { applicableMinimumCTC: 12000 } },
      { emp: { employer_name: 'Beta Corp' }, ctcVal: { applicableMinimumCTC: 12000 } }
    ]
    const notice = formatShortCtcNotice(failures)
    assert.strictEqual(notice.title, 'CTC Validation Failed')
    assert.strictEqual(
      notice.message,
      'The monthly CTC for Alpha Ltd and Beta Corp is below the required minimum of ₹12,000. Please update the CTC before submitting the Candidate Dossier.'
    )
    console.log('✓ Test Case G: 2 employers with same minimum short notice passed')
  }

  // Test Case H: 2 employers with differing minimums (both names displayed)
  {
    const failures = [
      { emp: { employer_name: 'Gujarat Tech' }, ctcVal: { applicableMinimumCTC: 15850 } },
      { emp: { employer_name: 'AP Infotech' }, ctcVal: { applicableMinimumCTC: 14250 } }
    ]
    const notice = formatShortCtcNotice(failures)
    assert.strictEqual(notice.title, 'CTC Validation Failed')
    assert.strictEqual(
      notice.message,
      'The monthly CTC for Gujarat Tech and AP Infotech is below the required minimum. Please update the CTC before submitting the Candidate Dossier.'
    )
    console.log('✓ Test Case H: 2 employers with differing minimums short notice passed')
  }

  // Test Case I: 3 employers (first 2 names + "+ 1 more")
  {
    const failures = [
      { emp: { employer_name: 'Company A' }, ctcVal: { applicableMinimumCTC: 10000 } },
      { emp: { employer_name: 'Company B' }, ctcVal: { applicableMinimumCTC: 10000 } },
      { emp: { employer_name: 'Company C' }, ctcVal: { applicableMinimumCTC: 10000 } }
    ]
    const notice = formatShortCtcNotice(failures)
    assert.strictEqual(notice.title, 'CTC Validation Failed')
    assert.strictEqual(
      notice.message,
      'The monthly CTC for Company A, Company B (+1 more) is below the required minimum of ₹10,000. Please update the CTC before submitting the Candidate Dossier.'
    )
    console.log('✓ Test Case I: 3 employers (first 2 + "+ 1 more") passed')
  }

  // Test Case J: 5 employers with differing minimums (first 2 names + "+ 3 more")
  {
    const failures = [
      { emp: { employer_name: 'Company A' }, ctcVal: { applicableMinimumCTC: 15000 } },
      { emp: { employer_name: 'Company B' }, ctcVal: { applicableMinimumCTC: 12000 } },
      { emp: { employer_name: 'Company C' }, ctcVal: { applicableMinimumCTC: 10000 } },
      { emp: { employer_name: 'Company D' }, ctcVal: { applicableMinimumCTC: 8000 } },
      { emp: { employer_name: 'Company E' }, ctcVal: { applicableMinimumCTC: 6000 } }
    ]
    const notice = formatShortCtcNotice(failures)
    assert.strictEqual(notice.title, 'CTC Validation Failed')
    assert.strictEqual(
      notice.message,
      'The monthly CTC for Company A, Company B (+3 more) is below the required minimum. Please update the CTC before submitting the Candidate Dossier.'
    )
    console.log('✓ Test Case J: 5 employers (first 2 + "+ 3 more") passed')
  }

  console.log('All courseDurationHelper tests passed successfully!')
}

runTests()
