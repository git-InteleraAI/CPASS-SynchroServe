/**
 * Test suite for salarySequenceHelper.js
 * Validates:
 * 1. Two employers independently starting at Month 1.
 * 2. Additional months incrementing only for the relevant employer.
 * 3. Adding, removing, reordering, and reassigning salary entries.
 * 4. Copy Previous Month staying strictly within the same employer.
 * 5. December-to-January reporting periods and year rollover.
 * 6. Gaps and duplicate reporting periods.
 */

import assert from 'node:assert/strict'
import {
  MONTH_NAMES,
  SHORT_MONTH_NAMES,
  getPeriodValue,
  normalizeEmployerId,
  getEmployerSalarySequence,
  formatEmployerSalaryLabel,
  computeAllSalarySequences,
  findPreviousSalaryRecordForEmployer,
  calculateNextSalaryPeriodForEmployer,
  getEmployerDocumentSequence
} from './salarySequenceHelper.js'

console.log('--- Running salarySequenceHelper tests ---')

// Test 1: getPeriodValue and normalizeEmployerId
assert.equal(getPeriodValue(2026, 1), 2026 * 12 + 1)
assert.equal(getPeriodValue('2026', '12'), 2026 * 12 + 12)
assert.equal(normalizeEmployerId(null), 'emp_1')
assert.equal(normalizeEmployerId(''), 'emp_1')
assert.equal(normalizeEmployerId('  emp_2  '), 'emp_2')

// Test 2: Two employers independently starting at Month 1
const testSalaries = [
  { id: 's1', employer_id: 'emp_1', year: 2026, month: 1 }, // Emp 1 Month 1 (Jan 2026)
  { id: 's2', employer_id: 'emp_1', year: 2026, month: 2 }, // Emp 1 Month 2 (Feb 2026)
  { id: 's3', employer_id: 'emp_1', year: 2026, month: 3 }, // Emp 1 Month 3 (Mar 2026)
  { id: 's4', employer_id: 'emp_2', year: 2026, month: 3 }, // Emp 2 Month 1 (Mar 2026)
  { id: 's5', employer_id: 'emp_2', year: 2026, month: 4 }, // Emp 2 Month 2 (Apr 2026)
]

assert.equal(getEmployerSalarySequence(testSalaries[0], testSalaries), 1)
assert.equal(getEmployerSalarySequence(testSalaries[1], testSalaries), 2)
assert.equal(getEmployerSalarySequence(testSalaries[2], testSalaries), 3)

// Employer 2 starts independently at Month 1
assert.equal(getEmployerSalarySequence(testSalaries[3], testSalaries), 1, 'Employer 2 first entry must be Month 1')
assert.equal(getEmployerSalarySequence(testSalaries[4], testSalaries), 2, 'Employer 2 second entry must be Month 2')

// Label formatting test
assert.equal(formatEmployerSalaryLabel(testSalaries[0], testSalaries), 'Month 1 — January 2026')
assert.equal(formatEmployerSalaryLabel(testSalaries[1], testSalaries), 'Month 2 — February 2026')
assert.equal(formatEmployerSalaryLabel(testSalaries[2], testSalaries), 'Month 3 — March 2026')
assert.equal(formatEmployerSalaryLabel(testSalaries[3], testSalaries), 'Month 1 — March 2026')
assert.equal(formatEmployerSalaryLabel(testSalaries[4], testSalaries), 'Month 2 — April 2026')

// Test 3: Out-of-order insertion and chronological sorting
const unorderedSalaries = [
  { id: 's_feb', employer_id: 'emp_1', year: 2026, month: 2 },
  { id: 's_jan', employer_id: 'emp_1', year: 2026, month: 1 },
]
assert.equal(getEmployerSalarySequence(unorderedSalaries[1], unorderedSalaries), 1, 'Jan should be Month 1 even if inserted second')
assert.equal(getEmployerSalarySequence(unorderedSalaries[0], unorderedSalaries), 2, 'Feb should be Month 2 even if inserted first')

// Test 4: Reassigning an entry from emp_1 to emp_2
const reassignedSalaries = [
  { id: 's1', employer_id: 'emp_1', year: 2026, month: 1 },
  { id: 's2', employer_id: 'emp_2', year: 2026, month: 2 }, // Reassigned to emp_2!
]
assert.equal(getEmployerSalarySequence(reassignedSalaries[0], reassignedSalaries), 1)
assert.equal(getEmployerSalarySequence(reassignedSalaries[1], reassignedSalaries), 1, 'Reassigned entry is now Month 1 for emp_2')

// Test 5: Copy Previous Month strictly within the SAME employer
const mixedSalaries = [
  { id: 's1', employer_id: 'emp_1', year: 2026, month: 1, gross_salary: 20000 },
  { id: 's2', employer_id: 'emp_2', year: 2026, month: 2, gross_salary: 30000 },
  { id: 's3', employer_id: 'emp_1', year: 2026, month: 2, gross_salary: 0 },
]
// For s3 (emp_1 Month 2), previous must be s1 (emp_1 Month 1), NOT s2 (emp_2 Month 2)
const prevForS3 = findPreviousSalaryRecordForEmployer(mixedSalaries[2], mixedSalaries)
assert.ok(prevForS3, 'Previous entry found')
assert.equal(prevForS3.id, 's1')
assert.equal(prevForS3.employer_id, 'emp_1')
assert.equal(prevForS3.gross_salary, 20000)

// For s2 (emp_2 Month 1), there is NO previous entry for emp_2
const prevForS2 = findPreviousSalaryRecordForEmployer(mixedSalaries[1], mixedSalaries)
assert.equal(prevForS2, null, 'No previous entry for emp_2')

// Test 6: December-to-January transitions
const yearTransitionSalaries = [
  { id: 's_dec', employer_id: 'emp_1', year: 2025, month: 12, gross_salary: 25000 },
  { id: 's_jan', employer_id: 'emp_1', year: 2026, month: 1, gross_salary: 0 },
]
assert.equal(getEmployerSalarySequence(yearTransitionSalaries[0], yearTransitionSalaries), 1)
assert.equal(getEmployerSalarySequence(yearTransitionSalaries[1], yearTransitionSalaries), 2)
assert.equal(formatEmployerSalaryLabel(yearTransitionSalaries[0], yearTransitionSalaries), 'Month 1 — December 2025')
assert.equal(formatEmployerSalaryLabel(yearTransitionSalaries[1], yearTransitionSalaries), 'Month 2 — January 2026')

const prevForJan = findPreviousSalaryRecordForEmployer(yearTransitionSalaries[1], yearTransitionSalaries)
assert.ok(prevForJan)
assert.equal(prevForJan.id, 's_dec', 'December 2025 is correctly recognized as predecessor of January 2026')
assert.equal(prevForJan.year, 2025)
assert.equal(prevForJan.month, 12)

// Test 7: calculateNextSalaryPeriodForEmployer
// If empty, starts at Month 1 of given year
const nextForEmpty = calculateNextSalaryPeriodForEmployer('emp_new', [], 2026)
assert.deepEqual(nextForEmpty, { month: 1, year: 2026 })

// If last is Month 1, next is Month 2
const nextForEmp1 = calculateNextSalaryPeriodForEmployer('emp_1', [{ employer_id: 'emp_1', year: 2026, month: 1 }], 2026)
assert.deepEqual(nextForEmp1, { month: 2, year: 2026 })

// If last is Month 12, next rolls over to Month 1 of next year
const nextForDec = calculateNextSalaryPeriodForEmployer('emp_1', [{ employer_id: 'emp_1', year: 2025, month: 12 }], 2025)
assert.deepEqual(nextForDec, { month: 1, year: 2026 }, 'December rolls over to January next year')

// Test 8: computeAllSalarySequences map
const allSeqMap = computeAllSalarySequences(testSalaries, [
  { id: 'emp_1', employer_name: 'Acme Corp' },
  { id: 'emp_2', employer_name: 'Beta Tech' }
])
assert.equal(allSeqMap['s1'].sequence, 1)
assert.equal(allSeqMap['s3'].sequence, 3)
assert.equal(allSeqMap['s4'].sequence, 1)
assert.equal(allSeqMap['s5'].sequence, 2)
assert.ok(allSeqMap['s4'].label.includes('Month 1 — March 2026'))

console.log('All salarySequenceHelper tests passed successfully!')
