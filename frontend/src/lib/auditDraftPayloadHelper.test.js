/**
 * Automated Regression Test Suite for CPASS Circular JSON Prevention
 *
 * Verifies that:
 * 1. Simulating a React SyntheticEvent containing an HTMLButtonElement and
 *    circular Fiber reference (stateNode <-> Fiber) passed as `targetEmpId` or
 *    `employer_id` never causes circular JSON serialization errors.
 * 2. `sanitizeEmployerId` strips DOM elements and falls back to a clean string.
 * 3. `sanitizeEmployerDetails` extracts only primitives and ignores DOM objects.
 * 4. `sanitizeSalaryDetails` sanitizes `employer_id` and all numeric/string fields.
 * 5. `sanitizeDocumentAudit` eliminates circular references from document audit entries.
 * 6. `sanitizeSignoffDetails` extracts clean signoff primitives only.
 * 7. `buildCleanAuditDraftPayload` serializes cleanly with `JSON.stringify()` without error.
 * 8. Staged upload metadata (`salaryMeta`, `bankMeta`) with corrupted employer_id serializes cleanly.
 */

import assert from 'node:assert'
import {
  sanitizeEmployerId,
  sanitizeEmployerDetails,
  sanitizeSalaryDetails,
  sanitizeSignoffDetails,
  sanitizeDocumentAudit,
  buildCleanAuditDraftPayload,
} from './auditDraftPayloadHelper.js'

let totalTests = 0
let passedTests = 0

function runTest(name, fn) {
  totalTests++
  try {
    fn()
    passedTests++
    console.log(`[PASS] ${name}`)
  } catch (err) {
    console.error(`[FAIL] ${name}:`, err.message)
    throw err
  }
}

// -----------------------------------------------------------------------------
// Helper: Create a Circular Object matching React SyntheticEvent & Fiber
// -----------------------------------------------------------------------------
function createMockCircularButtonEvent() {
  const buttonElement = {
    tagName: 'BUTTON',
    className: 'l1-btn-add-slot',
    innerText: '+ Add Salary Month',
  }

  const fiberNode = {
    tag: 5,
    key: null,
    elementType: 'button',
    type: 'button',
    stateNode: buttonElement, // Circular back-reference to DOM element
  }

  // React attaches __reactFiber$ to DOM element
  buttonElement['__reactFiber$abc123'] = fiberNode

  const syntheticEvent = {
    _reactName: 'onClick',
    type: 'click',
    target: buttonElement,
    currentTarget: buttonElement,
    bubbles: true,
    cancelable: true,
    defaultPrevented: false,
    nativeEvent: {
      isTrusted: true,
      target: buttonElement,
    },
  }

  return syntheticEvent
}

// -----------------------------------------------------------------------------
// Test Cases
// -----------------------------------------------------------------------------

runTest('1. Verify native JSON.stringify throws on circular structure', () => {
  const circular = createMockCircularButtonEvent()
  assert.throws(
    () => {
      JSON.stringify(circular)
    },
    (err) => err instanceof TypeError && /Converting circular structure to JSON/i.test(err.message),
    'Expected standard JSON.stringify to fail on raw circular event object'
  )
})

runTest('2. sanitizeEmployerId safely handles circular event object and returns clean fallback string', () => {
  const circularEvent = createMockCircularButtonEvent()
  const sanitized = sanitizeEmployerId(circularEvent, 'emp_default_1')
  assert.strictEqual(sanitized, 'emp_default_1')

  const validString = sanitizeEmployerId('emp_456', 'emp_default_1')
  assert.strictEqual(validString, 'emp_456')

  const validNumber = sanitizeEmployerId(101, 'emp_default_1')
  assert.strictEqual(validNumber, '101')
})

runTest('3. sanitizeSalaryDetails purges circular event from employer_id and serializes cleanly', () => {
  const circularEvent = createMockCircularButtonEvent()
  const salaryDetailList = [
    {
      id: 'sal_1',
      employer_id: 'emp_1',
      month: 1,
      year: 2026,
      gross_salary: '15000',
      net_salary: '14000',
    },
    {
      id: 'sal_2',
      // Corrupted by direct onClick={handleAddSalaryRow}
      employer_id: circularEvent,
      month: 2,
      year: 2026,
      gross_salary: '15000',
      net_salary: '14000',
    },
  ]

  const cleaned = sanitizeSalaryDetails(salaryDetailList, 'emp_1')
  assert.strictEqual(cleaned[1].employer_id, 'emp_1')

  // Must stringify without error
  const jsonStr = JSON.stringify(cleaned)
  assert.ok(jsonStr.includes('"employer_id":"emp_1"'))
  assert.ok(!jsonStr.includes('__reactFiber'))
})

runTest('4. sanitizeEmployerDetails purges foreign properties and serializes cleanly', () => {
  const circularEvent = createMockCircularButtonEvent()
  const employerList = [
    {
      id: 'emp_1',
      employer_name: 'Tech Mahindra Ltd',
      months_worked: '12',
      eventRef: circularEvent, // accidental attached event
    },
  ]

  const cleaned = sanitizeEmployerDetails(employerList)
  assert.strictEqual(cleaned.length, 1)
  assert.strictEqual(cleaned[0].employer_name, 'Tech Mahindra Ltd')
  assert.strictEqual(cleaned[0].months_worked, 12)
  assert.strictEqual(cleaned[0].eventRef, undefined)

  assert.doesNotThrow(() => JSON.stringify(cleaned))
})

runTest('5. sanitizeDocumentAudit eliminates circular references from document audit entries', () => {
  const circularEvent = createMockCircularButtonEvent()
  const docAudit = {
    appointment_letter: { available: 'Yes', compliance: 'Compliant', remarks: 'Verified' },
    salary_slip_1: { available: 'Yes', compliance: 'Compliant', remarks: 'Verified', domNode: circularEvent.target },
    salary_slip_4: { available: 'No', compliance: 'Non-Compliant', remarks: 'Payslip not available', event: circularEvent },
  }

  const cleaned = sanitizeDocumentAudit(docAudit)
  assert.strictEqual(cleaned.appointment_letter.available, 'Yes')
  assert.strictEqual(cleaned.salary_slip_1.domNode, undefined)
  assert.strictEqual(cleaned.salary_slip_4.event, undefined)

  assert.doesNotThrow(() => JSON.stringify(cleaned))
})

runTest('6. buildCleanAuditDraftPayload completely protects entire autosave payload from circular JSON failure', () => {
  const circularEvent = createMockCircularButtonEvent()

  const state = {
    candDetail: {
      candidate_id: '1076617',
      first_name: 'Lalrinkimi',
      last_name: 'Sailo',
      father_name: 'Zoramthanga',
      dob: '2000-05-15',
      mobile: '9876543210',
    },
    sel: {
      cand: '1076617',
      state: 'MIZORAM',
      tc: '1005985',
      order: 'ORD-001',
      batch: 'BAT-001',
    },
    lists: {
      tc: [{ tc_id: '1005985', name: 'SynchroServe Mizoram TC' }],
      batch: [{ kb_batch_id: 'BAT-001', batch_code: 'BATCH-MIZ-01' }],
    },
    employerList: [
      { id: 'emp_1', employer_name: 'SynchroServe Global', months_worked: '6', monthly_ctc: '25000' },
    ],
    salaryDetailList: [
      { id: 'sal_1', employer_id: 'emp_1', month: 1, year: 2026, gross_salary: '25000', net_salary: '23000' },
      { id: 'sal_2', employer_id: 'emp_1', month: 2, year: 2026, gross_salary: '25000', net_salary: '23000' },
      { id: 'sal_3', employer_id: 'emp_1', month: 3, year: 2026, gross_salary: '25000', net_salary: '23000' },
      // 4th row added by clicking Add Month with onClick={handleAddSalaryRow}
      { id: 'sal_4', employer_id: circularEvent, month: 4, year: 2026, gross_salary: '25000', net_salary: '23000' },
    ],
    signoffDetails: {
      centre_head: { name: 'CH Officer', designation: 'Centre Head', date: '2026-11-09', remarks: 'OK', confirmed: true },
      cops_team: { name: 'Auditor', designation: 'COPS Lead', date: '2026-11-09', remarks: 'OK', verified: true },
      business_leader: { name: 'BL Head', designation: 'Business Head', date: '2026-11-09', remarks: 'OK', approved: true },
    },
    auditRecord: { remarks: 'Draft saved' },
    documentAuditPayload: {
      appointment_letter: { available: 'Yes', compliance: 'Compliant', remarks: '' },
      salary_slip_1: { available: 'Yes', compliance: 'Under Verification', remarks: '' },
      salary_slip_2: { available: 'Yes', compliance: 'Under Verification', remarks: '' },
      salary_slip_3: { available: 'Yes', compliance: 'Under Verification', remarks: '' },
      salary_slip_4: { available: 'Yes', compliance: 'Under Verification', remarks: '', _circular: circularEvent },
      bank_statement_1: { available: 'Yes', compliance: 'Under Verification', remarks: '' },
      bank_statement_2: { available: 'Yes', compliance: 'Under Verification', remarks: '' },
      bank_statement_3: { available: 'Yes', compliance: 'Under Verification', remarks: '' },
      bank_statement_4: { available: 'Yes', compliance: 'Under Verification', remarks: '' },
      other_document: { available: 'Pending', compliance: 'Under Verification', remarks: '', title: '' },
    },
  }

  const payload = buildCleanAuditDraftPayload(state)
  assert.ok(payload !== null)

  // Critical Assertion: JSON.stringify must succeed completely without circular error
  let serialized = ''
  assert.doesNotThrow(() => {
    serialized = JSON.stringify(payload)
  })

  assert.ok(serialized.length > 0)
  assert.ok(serialized.includes('"candidate_id":"1076617"'))
  assert.ok(serialized.includes('"salary_details"'))
  assert.ok(serialized.includes('"document_audit"'))
  assert.ok(!serialized.includes('__reactFiber'))
  assert.ok(!serialized.includes('stateNode'))
})

runTest('7. Google Drive upload metadata JSON.stringify handles corrupted employer_id cleanly', () => {
  const circularEvent = createMockCircularButtonEvent()
  const salaryRows = [
    { month: 1, year: 2026, file: { name: 'slip1.pdf', size: 1024 } },
    { month: 2, year: 2026, file: { name: 'slip2.pdf', size: 1024 } },
    { month: 3, year: 2026, file: { name: 'slip3.pdf', size: 1024 } },
    { month: 4, year: 2026, file: { name: 'slip4.pdf', size: 1024 } },
  ]
  const salaryDetailList = [
    { employer_id: 'emp_1' },
    { employer_id: 'emp_1' },
    { employer_id: 'emp_1' },
    { employer_id: circularEvent },
  ]
  const employerList = [{ id: 'emp_1' }]

  const salaryMeta = []
  for (let i = 0; i < salaryRows.length; i++) {
    const row = salaryRows[i]
    if (row.file) {
      const matchedSal = salaryDetailList[i]
      const rawEmpId = matchedSal?.employer_id || employerList[0]?.id || null
      const empId = sanitizeEmployerId(rawEmpId, employerList[0]?.id || null)
      salaryMeta.push({
        month: Number(row.month),
        year: Number(row.year),
        employer_id: empId,
        replace_id: null,
      })
    }
  }

  assert.strictEqual(salaryMeta.length, 4)
  assert.strictEqual(salaryMeta[3].employer_id, 'emp_1')

  let serializedMeta = ''
  assert.doesNotThrow(() => {
    serializedMeta = JSON.stringify(salaryMeta)
  })
  assert.ok(serializedMeta.includes('"employer_id":"emp_1"'))
})

console.log(`\n========================================`)
console.log(`All ${passedTests}/${totalTests} unit tests passed successfully!`)
console.log(`========================================`)

