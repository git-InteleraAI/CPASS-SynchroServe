import assert from 'node:assert'
import {
  isSalaryLinkedToEmployer,
  getImmediateInvalidatedSalaryRows,
  syncSalaryRowsOnLocationDetection,
  determineSalaryRowState,
} from './salaryWageSyncHelper.js'

function runTests() {
  console.log('--- Running salaryWageSyncHelper tests ---')

  // Test 1: Multi-employer isolation in isSalaryLinkedToEmployer
  {
    const employers = [{ id: 'emp_1' }, { id: 'emp_2' }]
    const sal1 = { id: 's1', employer_id: 'emp_1' }
    const sal2 = { id: 's2', employer_id: 'emp_2' }
    const salUnassigned = { id: 's3', employer_id: null }

    assert.strictEqual(isSalaryLinkedToEmployer(sal1, 'emp_1', employers), true, 'sal1 should link to emp_1')
    assert.strictEqual(isSalaryLinkedToEmployer(sal1, 'emp_2', employers), false, 'sal1 should NOT link to emp_2')
    assert.strictEqual(isSalaryLinkedToEmployer(sal2, 'emp_2', employers), true, 'sal2 should link to emp_2')
    assert.strictEqual(isSalaryLinkedToEmployer(sal2, 'emp_1', employers), false, 'sal2 should NOT link to emp_1')
    assert.strictEqual(isSalaryLinkedToEmployer(salUnassigned, 'emp_1', employers), false, 'unassigned row in multi-employer should not link')

    // Single employer scenario: unassigned links to the single employer
    const singleEmpList = [{ id: 'emp_1' }]
    assert.strictEqual(isSalaryLinkedToEmployer(salUnassigned, 'emp_1', singleEmpList), true, 'unassigned row in single employer should link')
    console.log('✓ Test 1: Multi-employer linkage & isolation passed')
  }

  // Test 2: Immediate invalidation on typing (e.g. changing Hyderabad to Mumbai)
  {
    const employers = [{ id: 'emp_1' }, { id: 'emp_2' }]
    const salaryRows = [
      { id: 's1', employer_id: 'emp_1', month: 1, year: 2026, minimum_wage: 16950, min_wage_loading: false, min_wage_error: null },
      { id: 's2', employer_id: 'emp_2', month: 1, year: 2026, minimum_wage: 16000, min_wage_loading: false, min_wage_error: null },
    ]

    const result = getImmediateInvalidatedSalaryRows(salaryRows, 'emp_1', employers, true)
    
    // emp_1's salary row s1 is immediately invalidated and loading
    assert.strictEqual(result[0].minimum_wage, null, 's1 minimum_wage must be cleared to null')
    assert.strictEqual(result[0].min_wage_loading, true, 's1 min_wage_loading must be true')
    assert.strictEqual(result[0].min_wage_error, null, 's1 min_wage_error must be reset')

    // emp_2's salary row s2 remains completely untouched
    assert.strictEqual(result[1].minimum_wage, 16000, 's2 minimum_wage must remain 16000')
    assert.strictEqual(result[1].min_wage_loading, false, 's2 min_wage_loading must remain false')
    console.log('✓ Test 2: Immediate invalidation on typing passed')
  }

  // Test 3: Location cleared (<2 chars)
  {
    const employers = [{ id: 'emp_1' }]
    const salaryRows = [
      { id: 's1', employer_id: 'emp_1', month: 1, year: 2026, minimum_wage: 16950, min_wage_loading: false, min_wage_error: null },
    ]

    const result = getImmediateInvalidatedSalaryRows(salaryRows, 'emp_1', employers, false)
    assert.strictEqual(result[0].minimum_wage, null)
    assert.strictEqual(result[0].min_wage_loading, false)
    assert.strictEqual(result[0].min_wage_error, null)
    console.log('✓ Test 3: Location cleared invalidation passed')
  }

  // Test 4: Detection result is UNSUPPORTED_STATE (e.g. Mumbai -> Maharashtra)
  {
    const employers = [{ id: 'emp_1' }]
    const salaryRows = [
      { id: 's1', employer_id: 'emp_1', month: 1, year: 2026, minimum_wage: 16950, min_wage_loading: true, min_wage_error: null },
    ]

    const detRes = {
      status: 'UNSUPPORTED_STATE',
      detected_state: 'MAHARASHTRA',
      message: 'Maharashtra is not included in the current 13-state statutory minimum wage register.',
    }

    const result = syncSalaryRowsOnLocationDetection(salaryRows, 'emp_1', employers, detRes)
    assert.strictEqual(result[0].minimum_wage, null, 'must not retain previous wage')
    assert.strictEqual(result[0].min_wage_loading, false)
    assert.strictEqual(result[0].minimum_wage_state, 'MAHARASHTRA')
    assert.ok(result[0].min_wage_error.includes('MAHARASHTRA is not in the statutory 13-state minimum wage register'))
    console.log('✓ Test 4: UNSUPPORTED_STATE invalidation passed')
  }

  // Test 5: Detection result is AMBIGUOUS (e.g. Bilaspur)
  {
    const employers = [{ id: 'emp_1' }]
    const salaryRows = [
      { id: 's1', employer_id: 'emp_1', month: 1, year: 2026, minimum_wage: 16950, min_wage_loading: true },
    ]

    const detRes = {
      status: 'AMBIGUOUS',
      candidate_states: ['CHHATTISGARH', 'HIMACHAL PRADESH'],
    }

    const result = syncSalaryRowsOnLocationDetection(salaryRows, 'emp_1', employers, detRes)
    assert.strictEqual(result[0].minimum_wage, null)
    assert.strictEqual(result[0].min_wage_loading, false)
    assert.strictEqual(result[0].min_wage_error, 'Location ambiguous - select state')
    console.log('✓ Test 5: AMBIGUOUS location invalidation passed')
  }

  // Test 6: Detection result is IDENTIFIED (e.g. Hyderabad -> Telangana)
  {
    const employers = [{ id: 'emp_1' }]
    const salaryRows = [
      { id: 's1', employer_id: 'emp_1', month: 1, year: 2026, minimum_wage: null, min_wage_loading: false },
    ]

    const detRes = {
      status: 'IDENTIFIED',
      detected_state: 'TELANGANA',
    }

    const result = syncSalaryRowsOnLocationDetection(salaryRows, 'emp_1', employers, detRes)
    assert.strictEqual(result[0].minimum_wage_state, 'TELANGANA')
    assert.strictEqual(result[0].min_wage_loading, true)
    assert.strictEqual(result[0].min_wage_error, null)
    console.log('✓ Test 6: IDENTIFIED state preparation passed')
  }

  // Test 7: determineSalaryRowState prevents candidate state fallback
  {
    const employers = [
      { id: 'emp_1', place_of_work: 'Mumbai', work_state: 'MAHARASHTRA', work_state_detection_status: 'UNSUPPORTED_STATE' },
    ]
    const salaryRow = { id: 's1', employer_id: 'emp_1', month: 1, year: 2026 }

    const state = determineSalaryRowState(salaryRow, employers, undefined)
    assert.strictEqual(state.canLookup, false, 'must not allow wage lookup for unsupported state')
    assert.ok(state.error.includes('MAHARASHTRA is not in the statutory 13-state minimum wage register'))
    assert.strictEqual(state.isLoading, false)

    // Ambiguous state
    employers[0].place_of_work = 'Bilaspur'
    employers[0].work_state = null
    employers[0].work_state_detection_status = 'AMBIGUOUS'
    const stateAmb = determineSalaryRowState(salaryRow, employers, undefined)
    assert.strictEqual(stateAmb.canLookup, false)
    assert.strictEqual(stateAmb.error, 'Location ambiguous - select state')

    // Identified state
    employers[0].place_of_work = 'Hyderabad'
    employers[0].work_state = 'TELANGANA'
    employers[0].work_state_detection_status = 'IDENTIFIED'
    const stateIdent = determineSalaryRowState(salaryRow, employers, undefined)
    assert.strictEqual(stateIdent.canLookup, true)
    assert.strictEqual(stateIdent.targetState, 'TELANGANA')
    assert.strictEqual(stateIdent.error, null)
    console.log('✓ Test 7: determineSalaryRowState boundary check passed')
  }

  console.log('All salaryWageSyncHelper tests passed successfully!')
}

runTests()

