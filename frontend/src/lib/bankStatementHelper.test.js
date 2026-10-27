import assert from 'node:assert/strict'
import {
  isDocConsolidated,
  getDocCoveredMonths,
  getCanonicalEmployerId,
  matchesEmployer,
  getConsolidatedCoverage,
  getBankDocumentStatus,
  isBankSlotVisible,
} from './bankStatementHelper.js'

console.log('--- Running bankStatementHelper tests ---')

// Test 1: isDocConsolidated
assert.equal(isDocConsolidated(null), false)
assert.equal(isDocConsolidated({ document_type: 'SALARY_SLIP' }), false)
assert.equal(
  isDocConsolidated({ document_type: 'BANK_STATEMENT', is_consolidated: true }),
  true
)
assert.equal(
  isDocConsolidated({
    document_type: 'BANK_STATEMENT',
    coverage_start_month: 1,
    coverage_start_year: 2026,
    coverage_end_month: 3,
    coverage_end_year: 2026,
  }),
  true
)
// Cross-calendar year coverage: Nov 2025 to Jan 2026
assert.equal(
  isDocConsolidated({
    document_type: 'BANK_STATEMENT',
    coverage_start_month: 11,
    coverage_start_year: 2025,
    coverage_end_month: 1,
    coverage_end_year: 2026,
  }),
  true,
  'Cross-calendar year range must be recognized as consolidated'
)

// Test 2: getDocCoveredMonths
const doc3Months = {
  document_type: 'BANK_STATEMENT',
  coverage_start_month: 1,
  coverage_start_year: 2026,
  coverage_end_month: 3,
  coverage_end_year: 2026,
}
const covered3 = getDocCoveredMonths(doc3Months)
assert.deepEqual(covered3, [
  { month: 1, year: 2026 },
  { month: 2, year: 2026 },
  { month: 3, year: 2026 },
])

// Cross-calendar year covered months
const docCrossYear = {
  document_type: 'BANK_STATEMENT',
  coverage_start_month: 11,
  coverage_start_year: 2025,
  coverage_end_month: 1,
  coverage_end_year: 2026,
}
const coveredCross = getDocCoveredMonths(docCrossYear)
assert.deepEqual(coveredCross, [
  { month: 11, year: 2025 },
  { month: 12, year: 2025 },
  { month: 1, year: 2026 },
])

// Test 3: Status presentation
assert.equal(getBankDocumentStatus(null), 'Missing')
assert.equal(
  getBankDocumentStatus({ drive_file_id: 'drive_123', upload_status: 'SUCCESS' }),
  'Saved',
  'File in Drive without reviewer verification must be Saved'
)
assert.equal(
  getBankDocumentStatus({ drive_file_id: 'drive_123', reviewer_status: 'VERIFIED' }),
  'Verified',
  'Reviewer verified file must be Verified'
)
assert.equal(
  getBankDocumentStatus({ upload_status: 'FAILED' }),
  'Upload failed'
)
assert.equal(
  getBankDocumentStatus({ upload_status: 'UPLOADING' }),
  'Uploading'
)

// Test 4: Single Employer — Consolidated 3-month PDF suppresses all 3 monthly upload controls
const employersSingle = [{ id: 'emp_1', employer_name: 'Acme Corp' }]
const safeDocsConsolidated = [
  {
    id: 'doc_consol_1',
    document_type: 'BANK_STATEMENT',
    file_name: 'HDFC_Q1_2026.pdf',
    drive_file_id: 'drive_abc',
    upload_status: 'SUCCESS',
    employer_id: 'emp_1',
    coverage_start_month: 1,
    coverage_start_year: 2026,
    coverage_end_month: 3,
    coverage_end_year: 2026,
  },
]
const bankRows3 = [
  { id: 'b1', month: 1, year: 2026, employer_id: 'emp_1', file: null },
  { id: 'b2', month: 2, year: 2026, employer_id: 'emp_1', file: null },
  { id: 'b3', month: 3, year: 2026, employer_id: 'emp_1', file: null },
]
const salaries3 = [
  { id: 's1', month: 1, year: 2026, employer_id: 'emp_1' },
  { id: 's2', month: 2, year: 2026, employer_id: 'emp_1' },
  { id: 's3', month: 3, year: 2026, employer_id: 'emp_1' },
]

const visibleSingle = bankRows3.filter((r, idx) =>
  isBankSlotVisible(r, idx, {
    bankRows: bankRows3,
    salaryDetailList: salaries3,
    employerList: employersSingle,
    safeDocs: safeDocsConsolidated,
    stagedConsolidatedBankDocs: [],
  })
)
assert.equal(
  visibleSingle.length,
  0,
  'All 3 months are covered by consolidated statement; no empty monthly controls should be visible'
)

// Test 5: Partially covered range (covers Jan and Feb, March uncovered)
const safeDocsPartial = [
  {
    id: 'doc_consol_2',
    document_type: 'BANK_STATEMENT',
    file_name: 'Jan_Feb_Statement.pdf',
    drive_file_id: 'drive_def',
    upload_status: 'SUCCESS',
    employer_id: 'emp_1',
    coverage_start_month: 1,
    coverage_start_year: 2026,
    coverage_end_month: 2,
    coverage_end_year: 2026,
  },
]
const visiblePartial = bankRows3.filter((r, idx) =>
  isBankSlotVisible(r, idx, {
    bankRows: bankRows3,
    salaryDetailList: salaries3,
    employerList: employersSingle,
    safeDocs: safeDocsPartial,
    stagedConsolidatedBankDocs: [],
  })
)
assert.equal(visiblePartial.length, 1, 'Only Month 3 should be visible')
assert.equal(visiblePartial[0].month, 3)

// Test 6: Locally staged file is NEVER suppressed even if covered
const bankRowsWithStaged = [
  { id: 'b1', month: 1, year: 2026, employer_id: 'emp_1', file: null },
  { id: 'b2', month: 2, year: 2026, employer_id: 'emp_1', file: new Blob(['fake']) },
  { id: 'b3', month: 3, year: 2026, employer_id: 'emp_1', file: null },
]
const visibleStaged = bankRowsWithStaged.filter((r, idx) =>
  isBankSlotVisible(r, idx, {
    bankRows: bankRowsWithStaged,
    salaryDetailList: salaries3,
    employerList: employersSingle,
    safeDocs: safeDocsConsolidated,
    stagedConsolidatedBankDocs: [],
  })
)
assert.equal(visibleStaged.length, 1, 'Staged file for Month 2 must remain visible')
assert.equal(visibleStaged[0].month, 2)

// Test 7: Multiple Employers — Employer 1 coverage MUST NOT suppress Employer 2 upload controls
const employersMulti = [
  { id: 'emp_1', employer_name: 'Company A' },
  { id: 'emp_2', employer_name: 'Company B' },
]
const bankRowsMulti = [
  { id: 'b1', month: 1, year: 2026, employer_id: 'emp_1', file: null },
  { id: 'b2', month: 2, year: 2026, employer_id: 'emp_1', file: null },
  { id: 'b3', month: 3, year: 2026, employer_id: 'emp_2', file: null },
  { id: 'b4', month: 4, year: 2026, employer_id: 'emp_2', file: null },
]
const salariesMulti = [
  { id: 's1', month: 1, year: 2026, employer_id: 'emp_1' },
  { id: 's2', month: 2, year: 2026, employer_id: 'emp_1' },
  { id: 's3', month: 3, year: 2026, employer_id: 'emp_2' },
  { id: 's4', month: 4, year: 2026, employer_id: 'emp_2' },
]
// Consolidated doc belongs to Company A (emp_1) covering Jan–Feb 2026
const safeDocsEmp1 = [
  {
    id: 'doc_emp1',
    document_type: 'BANK_STATEMENT',
    file_name: 'CompanyA_Bank.pdf',
    drive_file_id: 'drive_111',
    upload_status: 'SUCCESS',
    employer_id: 'emp_1',
    coverage_start_month: 1,
    coverage_start_year: 2026,
    coverage_end_month: 2,
    coverage_end_year: 2026,
  },
]

const visibleMulti = bankRowsMulti.filter((r, idx) =>
  isBankSlotVisible(r, idx, {
    bankRows: bankRowsMulti,
    salaryDetailList: salariesMulti,
    employerList: employersMulti,
    safeDocs: safeDocsEmp1,
    stagedConsolidatedBankDocs: [],
  })
)
assert.equal(
  visibleMulti.length,
  2,
  'Company B slots must NOT be suppressed by Company A statement'
)
assert.equal(visibleMulti[0].id, 'b3')
assert.equal(visibleMulti[1].id, 'b4')

console.log('All bankStatementHelper tests passed successfully!')
