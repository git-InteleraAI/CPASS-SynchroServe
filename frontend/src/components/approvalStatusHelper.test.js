/**
 * Automated Test Suite for CPASS Statement Approval Status Display
 *
 * Verifies:
 * 1. CH approved and rejected
 * 2. COPS approved and rejected
 * 3. BL approved and rejected
 * 4. Pending stages
 * 5. Returned-to-L1 and resubmission
 * 6. Legacy records with missing stage details
 * 7. No duplicate technical status labels
 * 8. CEO review verification (confirming CEO review is not part of current workflow)
 */

import assert from 'node:assert'
import { getApprovalStatusDetails } from './approvalStatusHelper.js'

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
// Test Cases
// -----------------------------------------------------------------------------

runTest('1. CH Approved — displays CH Approved overall, Awaiting COPS detail, and CH — Approved stage', () => {
  const statement = {
    cpass_status: 'L2_APPROVED',
    audit_status: 'SUBMITTED',
    review_stages: {
      ch: { status: 'Recommended', reviewer_name: 'Centre Head User', date: '26/10/2026' },
      cops: { status: 'Pending' },
      bl: { status: 'Pending' },
    },
  }
  const res = getApprovalStatusDetails(statement)
  assert.strictEqual(res.overallStatus, 'CH Approved')
  assert.strictEqual(res.overallBadgeClass, 'approved')
  assert.strictEqual(res.reviewStatusDetail, 'Awaiting COPS Audit')
  assert.strictEqual(res.chStage.decision, 'Approved')
  assert.strictEqual(res.chStage.label, 'CH — Approved')
  assert.strictEqual(res.chStage.badgeClass, 'approved')
  assert.strictEqual(res.copsStage.decision, 'Pending')
  assert.strictEqual(res.copsStage.label, 'COPS — Pending')
  assert.strictEqual(res.blStage.decision, 'Pending')
  assert.strictEqual(res.blStage.label, 'BL — Pending')
})

runTest('2. CH Rejected — displays CH Rejected overall and CH — Rejected stage', () => {
  const statement = {
    audit_status: 'REJECTED',
    cpass_status: 'L2_REJECTED',
    review_stages: {
      ch: { status: 'Rejected', rejection_reason: 'Aadhaar mismatch' },
      cops: { status: 'Pending' },
      bl: { status: 'Pending' },
    },
  }
  const res = getApprovalStatusDetails(statement)
  assert.strictEqual(res.overallStatus, 'CH Rejected')
  assert.strictEqual(res.overallBadgeClass, 'rejected')
  assert.strictEqual(res.chStage.decision, 'Rejected')
  assert.strictEqual(res.chStage.label, 'CH — Rejected')
  assert.strictEqual(res.chStage.badgeClass, 'rejected')
  assert.strictEqual(res.copsStage.decision, 'Pending')
  assert.strictEqual(res.blStage.decision, 'Pending')
})

runTest('3. COPS Approved — displays COPS Approved overall, Awaiting BL detail, and COPS — Approved stage', () => {
  const statement = {
    cpass_status: 'VERIFIED',
    audit_status: 'SUBMITTED',
    review_stages: {
      ch: { status: 'Recommended', reviewer_name: 'CH User' },
      cops: { status: 'Verified', reviewer_name: 'COPS Auditor', date: '26/10/2026' },
      bl: { status: 'Pending' },
    },
  }
  const res = getApprovalStatusDetails(statement)
  assert.strictEqual(res.overallStatus, 'COPS Approved')
  assert.strictEqual(res.overallBadgeClass, 'approved')
  assert.strictEqual(res.reviewStatusDetail, 'Awaiting BL Approval')
  assert.strictEqual(res.chStage.decision, 'Approved')
  assert.strictEqual(res.copsStage.decision, 'Approved')
  assert.strictEqual(res.copsStage.label, 'COPS — Approved')
  assert.strictEqual(res.copsStage.badgeClass, 'approved')
  assert.strictEqual(res.blStage.decision, 'Pending')
})

runTest('4. COPS Rejected — displays COPS Rejected, preserves CH decision as Approved, and BL Pending', () => {
  const statement = {
    cpass_status: 'L3_REJECTED',
    audit_status: 'REJECTED',
    review_stages: {
      ch: { status: 'Recommended', reviewer_name: 'CH User' },
      cops: { status: 'Rejected', rejection_reason: 'Pay slip net salary does not match bank statement' },
      bl: { status: 'Pending' },
    },
  }
  const res = getApprovalStatusDetails(statement)
  assert.strictEqual(res.overallStatus, 'COPS Rejected')
  assert.strictEqual(res.overallBadgeClass, 'rejected')
  assert.strictEqual(res.chStage.decision, 'Approved')
  assert.strictEqual(res.chStage.label, 'CH — Approved')
  assert.strictEqual(res.copsStage.decision, 'Rejected')
  assert.strictEqual(res.copsStage.label, 'COPS — Rejected')
  assert.strictEqual(res.copsStage.badgeClass, 'rejected')
  assert.strictEqual(res.blStage.decision, 'Pending')
  assert.strictEqual(res.blStage.label, 'BL — Pending')
})

runTest('5. BL Approved — displays BL Approved overall, All Reviews Complete, and BL — Approved stage', () => {
  const statement = {
    cpass_status: 'APPROVED',
    audit_status: 'SUBMITTED',
    review_stages: {
      ch: { status: 'Recommended' },
      cops: { status: 'Verified' },
      bl: { status: 'Approved', reviewer_name: 'Business Leader', date: '26/10/2026' },
    },
  }
  const res = getApprovalStatusDetails(statement)
  assert.strictEqual(res.overallStatus, 'BL Approved')
  assert.strictEqual(res.overallBadgeClass, 'approved')
  assert.strictEqual(res.reviewStatusDetail, 'All Reviews Complete')
  assert.strictEqual(res.chStage.decision, 'Approved')
  assert.strictEqual(res.copsStage.decision, 'Approved')
  assert.strictEqual(res.blStage.decision, 'Approved')
  assert.strictEqual(res.blStage.label, 'BL — Approved')
  assert.strictEqual(res.blStage.badgeClass, 'approved')
})

runTest('6. BL Rejected — displays BL Rejected, preserves CH & COPS as Approved', () => {
  const statement = {
    cpass_status: 'L4_REJECTED',
    audit_status: 'REJECTED',
    review_stages: {
      ch: { status: 'Recommended' },
      cops: { status: 'Verified' },
      bl: { status: 'Rejected', rejection_reason: 'CTC below statutory minimum' },
    },
  }
  const res = getApprovalStatusDetails(statement)
  assert.strictEqual(res.overallStatus, 'BL Rejected')
  assert.strictEqual(res.overallBadgeClass, 'rejected')
  assert.strictEqual(res.chStage.decision, 'Approved')
  assert.strictEqual(res.copsStage.decision, 'Approved')
  assert.strictEqual(res.blStage.decision, 'Rejected')
  assert.strictEqual(res.blStage.label, 'BL — Rejected')
  assert.strictEqual(res.blStage.badgeClass, 'rejected')
})

runTest('7. Pending Stages — freshly submitted candidate shows Pending CH Review and all stages Pending', () => {
  const statement = {
    audit_status: 'SUBMITTED',
    cpass_status: 'UNDER_AUDIT',
    review_stages: {
      ch: { status: 'Pending' },
      cops: { status: 'Pending' },
      bl: { status: 'Pending' },
    },
  }
  const res = getApprovalStatusDetails(statement)
  assert.strictEqual(res.overallStatus, 'Pending CH Review')
  assert.strictEqual(res.overallBadgeClass, 'pending')
  assert.strictEqual(res.reviewStatusDetail, 'Awaiting CH Verification')
  assert.strictEqual(res.chStage.decision, 'Pending')
  assert.strictEqual(res.copsStage.decision, 'Pending')
  assert.strictEqual(res.blStage.decision, 'Pending')
})

runTest('8. Returned to L1 — displays CH Rejected overall and in CH stage with return reason preserved', () => {
  const statement = {
    audit_status: 'RETURNED_TO_L1',
    cpass_status: 'RETURNED_TO_L1',
    review_stages: {
      ch: { status: 'Returned to L1', return_reason: 'Please upload appointment letter' },
      cops: { status: 'Pending' },
      bl: { status: 'Pending' },
    },
  }
  const res = getApprovalStatusDetails(statement)
  assert.strictEqual(res.overallStatus, 'CH Rejected')
  assert.strictEqual(res.overallBadgeClass, 'rejected')
  assert.ok(res.reviewStatusDetail.includes('CH Rejected — Returned for Corrections'))
  assert.ok(res.reviewStatusDetail.includes('Please upload appointment letter'))
  assert.strictEqual(res.chStage.decision, 'Rejected')
  assert.strictEqual(res.chStage.label, 'CH — Rejected')
  assert.strictEqual(res.chStage.badgeClass, 'rejected')
  assert.strictEqual(res.chStage.return_reason, 'Please upload appointment letter')
  assert.strictEqual(res.copsStage.decision, 'Pending')
  assert.strictEqual(res.blStage.decision, 'Pending')
})

runTest('8b. Returned to L1 without return reason — displays CH Rejected and default readable dossier label', () => {
  const statement = {
    audit_status: 'RETURNED_TO_L1',
    cpass_status: 'RETURNED_TO_L1',
    review_stages: {
      ch: { status: 'Returned to L1' },
      cops: { status: 'Pending' },
      bl: { status: 'Pending' },
    },
  }
  const res = getApprovalStatusDetails(statement)
  assert.strictEqual(res.overallStatus, 'CH Rejected')
  assert.strictEqual(res.overallBadgeClass, 'rejected')
  assert.strictEqual(res.chStage.decision, 'Rejected')
  assert.strictEqual(res.chStage.label, 'CH — Rejected')
  assert.strictEqual(res.chStage.badgeClass, 'rejected')
  assert.strictEqual(res.reviewStatusDetail, 'CH Rejected — Returned for Corrections')
})

runTest('9. Resubmission after return — reset to Pending CH Review without residual rejection', () => {
  const statement = {
    audit_status: 'SUBMITTED',
    cpass_status: 'UNDER_AUDIT',
    signoff_details: {
      return_to_l1: { return_reason: 'Prior return reason from history' },
    },
    review_stages: {
      ch: { status: 'Pending' },
      cops: { status: 'Pending' },
      bl: { status: 'Pending' },
    },
  }
  const res = getApprovalStatusDetails(statement)
  assert.strictEqual(res.overallStatus, 'Pending CH Review')
  assert.strictEqual(res.overallBadgeClass, 'pending')
  assert.strictEqual(res.chStage.decision, 'Pending')
  assert.strictEqual(res.chStage.label, 'CH — Pending')
  assert.strictEqual(res.chStage.badgeClass, 'pending')
  assert.strictEqual(res.reviewStatusDetail, 'Awaiting CH Verification')
  assert.strictEqual(res.copsStage.decision, 'Pending')
  assert.strictEqual(res.blStage.decision, 'Pending')
})

runTest('10. Legacy records without review_stages — maps backwards-compatibly', () => {
  // Legacy L2 approved
  const l2Legacy = { cpass_status: 'L2_APPROVED', audit_status: 'SUBMITTED' }
  const l2Res = getApprovalStatusDetails(l2Legacy)
  assert.strictEqual(l2Res.overallStatus, 'CH Approved')
  assert.strictEqual(l2Res.chStage.decision, 'Approved')
  assert.strictEqual(l2Res.copsStage.decision, 'Pending')

  // Legacy COPS verified
  const copsLegacy = { cpass_status: 'VERIFIED', audit_status: 'SUBMITTED' }
  const copsRes = getApprovalStatusDetails(copsLegacy)
  assert.strictEqual(copsRes.overallStatus, 'COPS Approved')
  assert.strictEqual(copsRes.copsStage.decision, 'Approved')
  assert.strictEqual(copsRes.blStage.decision, 'Pending')

  // Legacy BL approved
  const blLegacy = { cpass_status: 'APPROVED', audit_status: 'SUBMITTED' }
  const blRes = getApprovalStatusDetails(blLegacy)
  assert.strictEqual(blRes.overallStatus, 'BL Approved')
  assert.strictEqual(blRes.blStage.decision, 'Approved')

  // Legacy returned
  const retLegacy = { audit_status: 'RETURNED_TO_L1', cpass_status: 'RETURNED_TO_L1' }
  const retRes = getApprovalStatusDetails(retLegacy)
  assert.strictEqual(retRes.overallStatus, 'CH Rejected')
  assert.strictEqual(retRes.overallBadgeClass, 'rejected')
  assert.strictEqual(retRes.chStage.decision, 'Rejected')
  assert.strictEqual(retRes.chStage.label, 'CH — Rejected')
})

runTest('11. No technical status labels — internal enum strings are never exposed', () => {
  const tests = [
    { cpass_status: 'L2_APPROVED', audit_status: 'SUBMITTED' },
    { cpass_status: 'APPROVED', audit_status: 'SUBMITTED' },
    { cpass_status: 'VERIFIED', audit_status: 'SUBMITTED' },
    { cpass_status: 'L3_REJECTED', audit_status: 'REJECTED' },
    { cpass_status: 'RETURNED_TO_L1', audit_status: 'RETURNED_TO_L1' },
    { cpass_status: 'UNDER_AUDIT', audit_status: 'SUBMITTED' },
  ]

  const forbiddenEnums = ['L2_APPROVED', 'CPASS_APPROVED', 'L3_REJECTED', 'L4_REJECTED', 'UNDER_AUDIT', 'SUBMITTED', 'RETURNED_TO_L1']

  for (const t of tests) {
    const res = getApprovalStatusDetails(t)
    for (const f of forbiddenEnums) {
      assert.ok(!res.overallStatus.includes(f), `overallStatus "${res.overallStatus}" should not contain "${f}"`)
      assert.ok(!res.reviewStatusDetail.includes(f), `reviewStatusDetail "${res.reviewStatusDetail}" should not contain "${f}"`)
      assert.ok(!res.chStage.label.includes(f), `chStage "${res.chStage.label}" should not contain "${f}"`)
      assert.ok(!res.copsStage.label.includes(f), `copsStage "${res.copsStage.label}" should not contain "${f}"`)
      assert.ok(!res.blStage.label.includes(f), `blStage "${res.blStage.label}" should not contain "${f}"`)
    }
  }
})

runTest('12. CEO review verification — CEO is not present in review stages (only CH, COPS, BL)', () => {
  const statement = {
    cpass_status: 'APPROVED',
    review_stages: { ch: { status: 'Recommended' }, cops: { status: 'Verified' }, bl: { status: 'Approved' } },
  }
  const res = getApprovalStatusDetails(statement)
  assert.strictEqual(res.ceoStage, undefined, 'CEO review should not be defined or fabricated')
  assert.ok('chStage' in res)
  assert.ok('copsStage' in res)
  assert.ok('blStage' in res)
})

console.log(`\n========================================`)
console.log(`All ${passedTests}/${totalTests} unit tests passed successfully!`)
console.log(`========================================\n`)
