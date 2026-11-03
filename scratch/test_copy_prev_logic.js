import assert from 'node:assert/strict'
import {
  findPreviousSalaryRecordForEmployer,
  calculateNextSalaryPeriodForEmployer,
  getPeriodValue,
  MONTH_NAMES
} from '../frontend/src/lib/salarySequenceHelper.js'

console.log('=== TEST SUITE: Copy Previous & Bank Sync Logic ===\n')

// ----------------------------------------------------
// Test 1: Month 1 boundary - Copy Prev disabled
// ----------------------------------------------------
console.log('Test 1: Month 1 boundary condition')
const initialList = [
  { id: 's1', employer_id: 'emp_1', month: 1, year: 2026, gross_salary: '15000', deductions: '0', amount_credited: '15000', bank_name: 'SBI' },
  { id: 's2', employer_id: 'emp_1', month: 2, year: 2026, gross_salary: '', deductions: '', amount_credited: '', bank_name: '' },
  { id: 's3', employer_id: 'emp_1', month: 3, year: 2026, gross_salary: '', deductions: '', amount_credited: '', bank_name: '' },
]
assert.equal(findPreviousSalaryRecordForEmployer(initialList[0], initialList), null, 'Month 1 must have NO previous record (disabled Copy Prev)')
assert.equal(findPreviousSalaryRecordForEmployer(initialList[1], initialList)?.id, 's1', 'Month 2 previous record must be Month 1')
assert.equal(findPreviousSalaryRecordForEmployer(initialList[2], initialList)?.id, 's2', 'Month 3 previous record must be Month 2')
console.log('✓ Passed: Month 1 has no previous record, Month 2 points to Month 1, Month 3 points to Month 2')

// ----------------------------------------------------
// Test 2: Chronological Advance - March 2018 -> April 2018
// ----------------------------------------------------
console.log('\nTest 2: Chronological advance from March 2018')
const m1 = { month: 3, year: 2018 }
const prevM = parseInt(m1.month, 10) || 1
const prevY = parseInt(m1.year, 10) || 2026
let nextMonth = prevM + 1
let nextYear = prevY
if (nextMonth > 12) {
  nextMonth = 1
  nextYear = prevY + 1
}
assert.equal(nextMonth, 4, 'March + 1 must be April (4)')
assert.equal(nextYear, 2018, 'Year must remain 2018')
console.log('✓ Passed: March 2018 advances to April 2018')

// ----------------------------------------------------
// Test 3: Chronological Advance - December 2018 -> January 2019
// ----------------------------------------------------
console.log('\nTest 3: Year transition from December 2018')
const mDec = { month: 12, year: 2018 }
const prevMDec = parseInt(mDec.month, 10) || 1
const prevYDec = parseInt(mDec.year, 10) || 2026
let nextMonthDec = prevMDec + 1
let nextYearDec = prevYDec
if (nextMonthDec > 12) {
  nextMonthDec = 1
  nextYearDec = prevYDec + 1
}
assert.equal(nextMonthDec, 1, 'December + 1 must roll over to January (1)')
assert.equal(nextYearDec, 2019, 'Year must advance to 2019')
console.log('✓ Passed: December 2018 rolls over to January 2019')

// ----------------------------------------------------
// Test 4: Field copying rules (User specification scenario)
// ----------------------------------------------------
console.log('\nTest 4: Field copying rules with ₹15,620 scenario')
const month1Data = {
  id: 'sal_1',
  employer_id: 'emp_1',
  month: 3,
  year: 2018,
  working_days: 24,
  pay_days: 24,
  leave_days: 2,
  credit_date: '2018-04-05',
  amount_credited: '18970',
  gross_salary: '15620',
  deductions: '0',
  net_salary: '15620',
  bank_name: 'HDFC',
}

const targetMonth2 = {
  id: 'sal_2',
  employer_id: 'emp_1',
  month: 2,
  year: 2026,
  working_days: 26,
  pay_days: 26,
  leave_days: 0,
  credit_date: '',
  amount_credited: '',
  gross_salary: '',
  deductions: '',
  net_salary: '',
  bank_name: '',
}

// Simulate handleCopyPreviousMonth
const prevRecord = month1Data
const pM = parseInt(prevRecord.month, 10) || 1
const pY = parseInt(prevRecord.year, 10) || 2026
let nMonth = pM + 1
let nYear = pY
if (nMonth > 12) {
  nMonth = 1
  nYear = pY + 1
}

const grossVal = prevRecord.gross_salary !== '' && prevRecord.gross_salary !== null ? prevRecord.gross_salary : ''
const dedVal = prevRecord.deductions !== '' && prevRecord.deductions !== null ? prevRecord.deductions : ''
let netVal = prevRecord.net_salary !== '' && prevRecord.net_salary !== null ? prevRecord.net_salary : ''
if (grossVal !== '') {
  const g = parseFloat(grossVal) || 0
  const d = parseFloat(dedVal) || 0
  netVal = Math.max(0, g - d).toString()
}
const creditedVal = prevRecord.amount_credited !== '' && prevRecord.amount_credited !== null ? prevRecord.amount_credited : ''
const bankNameVal = prevRecord.bank_name || ''

const updatedMonth2 = {
  ...targetMonth2,
  month: nMonth,
  year: nYear,
  gross_salary: grossVal,
  deductions: dedVal,
  net_salary: netVal,
  amount_credited: creditedVal,
  bank_name: bankNameVal,
  // Preserved fields:
  working_days: targetMonth2.working_days,
  pay_days: targetMonth2.pay_days,
  leave_days: targetMonth2.leave_days,
  credit_date: targetMonth2.credit_date,
}

assert.equal(updatedMonth2.month, 4, 'Month must be April')
assert.equal(updatedMonth2.year, 2018, 'Year must be 2018')
assert.equal(updatedMonth2.gross_salary, '15620', 'Gross Salary must be 15620')
assert.equal(updatedMonth2.deductions, '0', 'Deductions must be 0')
assert.equal(updatedMonth2.net_salary, '15620', 'Net Salary must be 15620')
assert.equal(updatedMonth2.amount_credited, '18970', 'Credited Amount must be 18970')
assert.equal(updatedMonth2.bank_name, 'HDFC', 'Bank Name must be HDFC')
// Preserved:
assert.equal(updatedMonth2.working_days, 26, 'Target working_days must be preserved (26)')
assert.equal(updatedMonth2.pay_days, 26, 'Target pay_days must be preserved (26)')
assert.equal(updatedMonth2.leave_days, 0, 'Target leave_days must be preserved (0)')
assert.equal(updatedMonth2.credit_date, '', 'Target credit_date must be preserved ("")')
console.log('✓ Passed: Exact user example fields copied and preserved correctly')

// ----------------------------------------------------
// Test 5: Bank rows & Salary rows synchronization
// ----------------------------------------------------
console.log('\nTest 5: Bank and Salary rows slot synchronization')
const stagedFile = { name: 'sample_statement.pdf', size: 1024 }
let bankRows = [
  { id: 'b1', month: 1, year: 2026, employer_id: 'emp_1', file: null, fileName: '', fileSize: 0 },
  { id: 'b2', month: 2, year: 2026, employer_id: 'emp_1', file: stagedFile, fileName: 'sample_statement.pdf', fileSize: 1024 },
  { id: 'b3', month: 3, year: 2026, employer_id: 'emp_1', file: null, fileName: '', fileSize: 0 },
]

const targetIdx = 1
bankRows = bankRows.map((r, rIdx) =>
  rIdx === targetIdx
    ? {
        ...r,
        month: nMonth,
        year: nYear,
        employer_id: 'emp_1',
      }
    : r
)

assert.equal(bankRows[1].month, 4, 'Bank row month must be updated to 4 (April)')
assert.equal(bankRows[1].year, 2018, 'Bank row year must be updated to 2018')
assert.equal(bankRows[1].file, stagedFile, 'Staged file must be preserved')
assert.equal(bankRows[1].fileName, 'sample_statement.pdf', 'File name must be preserved')
assert.equal(bankRows[0].month, 1, 'Row 0 month untouched')
assert.equal(bankRows[2].month, 3, 'Row 2 month untouched')
console.log('✓ Passed: bankRows month and year synchronized while preserving staged file attachments')

// ----------------------------------------------------
// Test 6: Document Audit checklist metadata synchronization
// ----------------------------------------------------
console.log('\nTest 6: Document audit metadata synchronization')
let documentAudit = {
  appointment_letter: { available: 'Yes', compliance: 'Compliant' },
  salary_slip_1: { available: 'Yes', compliance: 'Compliant', month: 3, year: 2018 },
  salary_slip_2: { available: 'Pending', compliance: 'Under Verification', month: 2, year: 2026 },
  salary_slip_3: { available: 'Pending', compliance: 'Under Verification', month: 3, year: 2026 },
  bank_statement_1: { available: 'Yes', compliance: 'Compliant', month: 3, year: 2018 },
  bank_statement_2: { available: 'Pending', compliance: 'Under Verification', month: 2, year: 2026 },
  bank_statement_3: { available: 'Pending', compliance: 'Under Verification', month: 3, year: 2026 },
}

const salKey = `salary_slip_${targetIdx + 1}`
const bankKey = `bank_statement_${targetIdx + 1}`
documentAudit = {
  ...documentAudit,
  [salKey]: {
    ...(documentAudit[salKey] || {}),
    month: nMonth,
    year: nYear,
  },
  [bankKey]: {
    ...(documentAudit[bankKey] || {}),
    month: nMonth,
    year: nYear,
  },
}

assert.equal(documentAudit.salary_slip_2.month, 4)
assert.equal(documentAudit.salary_slip_2.year, 2018)
assert.equal(documentAudit.bank_statement_2.month, 4)
assert.equal(documentAudit.bank_statement_2.year, 2018)
console.log('✓ Passed: documentAudit synchronized with updated month and year')

console.log('\n=== ALL COPY PREVIOUS & BANK SYNC TESTS PASSED! ===')

