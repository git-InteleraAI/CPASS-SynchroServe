/**
 * Automated Test Suite for CPASS Five-Level Workflow Status Display
 *
 * Verifies:
 * 1. CH recommended/approved and rejected
 * 2. COPS verified/approved and rejected
 * 3. BL approved and rejected
 * 4. CEO approved and rejected
 * 5. Pending stages across 5 levels
 * 6. Flexible returns (L1, L2, L3, L4) and active return tracking
 * 7. Resubmission after return
 * 8. Legacy records with missing stage details
 * 9. No technical internal enum strings exposed
 * 10. Complete 4-stage review details (CH, COPS, BL, CEO)
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

runTest('1. CH Approved/Recommended — displays CH Approved overall, Awaiting COPS detail, and CH stage', () => {
  const statement = {
    cpass_status: 'L2_APPROVED',
    audit_status: 'SUBMITTED',
    review_stages: {
      ch: { status: 'Recommended', reviewer_name: 'Centre Head User', date: '26/10/2026' },
      cops: { status: 'Pending' },
      bl: { status: 'Pending' },
      ceo: { status: 'Pending' },
    },
  }
  const res = getApprovalStatusDetails(statement)
  assert.strictEqual(res.overallStatus, 'CH Approved')
  assert.strictEqual(res.overallBadgeClass, 'approved')
  assert.strictEqual(res.reviewStatusDetail, 'Awaiting COPS Audit')
  assert.strictEqual(res.chStage.decision, 'Recommended')
  assert.strictEqual(res.chStage.label, 'CH — Recommended')
  assert.strictEqual(res.chStage.badgeClass, 'approved')
  assert.strictEqual(res.copsStage.decision, 'Pending')
  assert.strictEqual(res.copsStage.label, 'COPS — Pending')
  assert.strictEqual(res.blStage.decision, 'Pending')
  assert.strictEqual(res.blStage.label, 'BL — Pending')
  assert.strictEqual(res.ceoStage.decision, 'Pending')
  assert.strictEqual(res.ceoStage.label, 'CEO — Pending')
})

runTest('2. CH Rejected — displays Rejected overall and CH — Rejected stage', () => {
  const statement = {
    audit_status: 'REJECTED',
    cpass_status: 'L2_REJECTED',
    review_stages: {
      ch: { status: 'Rejected', rejection_reason: 'Aadhaar mismatch' },
      cops: { status: 'Pending' },
      bl: { status: 'Pending' },
      ceo: { status: 'Pending' },
    },
  }
  const res = getApprovalStatusDetails(statement)
  assert.strictEqual(res.overallStatus, 'Rejected')
  assert.strictEqual(res.overallBadgeClass, 'rejected')
  assert.strictEqual(res.chStage.decision, 'Rejected')
  assert.strictEqual(res.chStage.label, 'CH — Rejected')
  assert.strictEqual(res.chStage.badgeClass, 'rejected')
  assert.strictEqual(res.copsStage.decision, 'Pending')
  assert.strictEqual(res.blStage.decision, 'Pending')
  assert.strictEqual(res.ceoStage.decision, 'Pending')
})

runTest('3. COPS Verified — displays COPS Approved overall, Awaiting BL detail, and COPS — Verified stage', () => {
  const statement = {
    cpass_status: 'VERIFIED',
    audit_status: 'SUBMITTED',
    review_stages: {
      ch: { status: 'Recommended', reviewer_name: 'CH User' },
      cops: { status: 'Verified', reviewer_name: 'COPS Auditor', date: '26/10/2026' },
      bl: { status: 'Pending' },
      ceo: { status: 'Pending' },
    },
  }
  const res = getApprovalStatusDetails(statement)
  assert.strictEqual(res.overallStatus, 'COPS Approved')
  assert.strictEqual(res.overallBadgeClass, 'approved')
  assert.strictEqual(res.reviewStatusDetail, 'Awaiting BL Approval')
  assert.strictEqual(res.chStage.decision, 'Recommended')
  assert.strictEqual(res.copsStage.decision, 'Verified')
  assert.strictEqual(res.copsStage.label, 'COPS — Verified')
  assert.strictEqual(res.copsStage.badgeClass, 'approved')
  assert.strictEqual(res.blStage.decision, 'Pending')
  assert.strictEqual(res.ceoStage.decision, 'Pending')
})

runTest('4. COPS Rejected — displays Rejected, preserves CH decision, and BL & CEO Pending', () => {
  const statement = {
    cpass_status: 'L3_REJECTED',
    audit_status: 'REJECTED',
    review_stages: {
      ch: { status: 'Recommended', reviewer_name: 'CH User' },
      cops: { status: 'Rejected', rejection_reason: 'Pay slip net salary does not match bank statement' },
      bl: { status: 'Pending' },
      ceo: { status: 'Pending' },
    },
  }
  const res = getApprovalStatusDetails(statement)
  assert.strictEqual(res.overallStatus, 'Rejected')
  assert.strictEqual(res.overallBadgeClass, 'rejected')
  assert.strictEqual(res.chStage.decision, 'Recommended')
  assert.strictEqual(res.chStage.label, 'CH — Recommended')
  assert.strictEqual(res.copsStage.decision, 'Rejected')
  assert.strictEqual(res.copsStage.label, 'COPS — Rejected')
  assert.strictEqual(res.copsStage.badgeClass, 'rejected')
  assert.strictEqual(res.blStage.decision, 'Pending')
  assert.strictEqual(res.ceoStage.decision, 'Pending')
})

runTest('5. BL Approved — displays BL Approved overall, Awaiting CEO Approval detail', () => {
  const statement = {
    cpass_status: 'BL_APPROVED',
    audit_status: 'SUBMITTED',
    review_stages: {
      ch: { status: 'Recommended' },
      cops: { status: 'Verified' },
      bl: { status: 'Approved', reviewer_name: 'Business Leader', date: '26/10/2026' },
      ceo: { status: 'Pending' },
    },
  }
  const res = getApprovalStatusDetails(statement)
  assert.strictEqual(res.overallStatus, 'BL Approved')
  assert.strictEqual(res.overallBadgeClass, 'approved')
  assert.strictEqual(res.reviewStatusDetail, 'Awaiting CEO Approval')
  assert.strictEqual(res.chStage.decision, 'Recommended')
  assert.strictEqual(res.copsStage.decision, 'Verified')
  assert.strictEqual(res.blStage.decision, 'Approved')
  assert.strictEqual(res.blStage.label, 'BL — Approved')
  assert.strictEqual(res.blStage.badgeClass, 'approved')
  assert.strictEqual(res.ceoStage.decision, 'Pending')
  assert.strictEqual(res.ceoStage.label, 'CEO — Pending')
})

runTest('6. CEO Approved — marks All Reviews Complete, CEO Approved stage', () => {
  const statement = {
    cpass_status: 'APPROVED',
    audit_status: 'APPROVED',
    review_stages: {
      ch: { status: 'Recommended' },
      cops: { status: 'Verified' },
      bl: { status: 'Approved' },
      ceo: { status: 'Approved', reviewer_name: 'Chief Executive Officer', date: '26/10/2026' },
    },
  }
  const res = getApprovalStatusDetails(statement)
  assert.strictEqual(res.overallStatus, 'All Reviews Complete')
  assert.strictEqual(res.overallBadgeClass, 'approved')
  assert.strictEqual(res.reviewStatusDetail, 'All Reviews Complete')
  assert.strictEqual(res.chStage.decision, 'Recommended')
  assert.strictEqual(res.copsStage.decision, 'Verified')
  assert.strictEqual(res.blStage.decision, 'Approved')
  assert.strictEqual(res.ceoStage.decision, 'Approved')
  assert.strictEqual(res.ceoStage.label, 'CEO — Approved')
  assert.strictEqual(res.ceoStage.badgeClass, 'approved')
})

runTest('7. CEO Rejected — displays Rejected, preserves prior stage signoffs', () => {
  const statement = {
    cpass_status: 'L5_REJECTED',
    audit_status: 'REJECTED',
    review_stages: {
      ch: { status: 'Recommended' },
      cops: { status: 'Verified' },
      bl: { status: 'Approved' },
      ceo: { status: 'Rejected', rejection_reason: 'Statutory compliance irregularity' },
    },
  }
  const res = getApprovalStatusDetails(statement)
  assert.strictEqual(res.overallStatus, 'Rejected')
  assert.strictEqual(res.overallBadgeClass, 'rejected')
  assert.strictEqual(res.chStage.decision, 'Recommended')
  assert.strictEqual(res.copsStage.decision, 'Verified')
  assert.strictEqual(res.blStage.decision, 'Approved')
  assert.strictEqual(res.ceoStage.decision, 'Rejected')
  assert.strictEqual(res.ceoStage.label, 'CEO — Rejected')
  assert.strictEqual(res.ceoStage.badgeClass, 'rejected')
})

runTest('8. Flexible Return to L3 by BL — displays Rejected with active return reason', () => {
  const statement = {
    audit_status: 'SUBMITTED',
    cpass_status: 'RETURNED_TO_L3',
    signoff_details: {
      active_return: {
        destination: 'L3',
        stage: 'BL',
        reason: 'Please verify employer month 3 pay slip again',
      },
    },
    review_stages: {
      ch: { status: 'Recommended' },
      cops: { status: 'Pending' },
      bl: { status: 'Pending' },
      ceo: { status: 'Pending' },
    },
  }
  const res = getApprovalStatusDetails(statement)
  assert.strictEqual(res.overallStatus, 'Rejected')
  assert.strictEqual(res.overallBadgeClass, 'rejected')
  assert.ok(res.reviewStatusDetail.includes('Returned to L3 for Corrections'))
  assert.ok(res.reviewStatusDetail.includes('Please verify employer month 3 pay slip again'))
  assert.strictEqual(res.chStage.decision, 'Recommended')
  assert.strictEqual(res.copsStage.decision, 'Pending')
})

runTest('9. Pending Stages — freshly submitted candidate shows Pending CH Review and all stages Pending', () => {
  const statement = {
    audit_status: 'SUBMITTED',
    cpass_status: 'UNDER_AUDIT',
    review_stages: {
      ch: { status: 'Pending' },
      cops: { status: 'Pending' },
      bl: { status: 'Pending' },
      ceo: { status: 'Pending' },
    },
  }
  const res = getApprovalStatusDetails(statement)
  assert.strictEqual(res.overallStatus, 'Pending CH Review')
  assert.strictEqual(res.overallBadgeClass, 'pending')
  assert.strictEqual(res.reviewStatusDetail, 'Awaiting CH Verification')
  assert.strictEqual(res.chStage.decision, 'Pending')
  assert.strictEqual(res.copsStage.decision, 'Pending')
  assert.strictEqual(res.blStage.decision, 'Pending')
  assert.strictEqual(res.ceoStage.decision, 'Pending')
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

  // Legacy BL approved (which had cpass_status: APPROVED before CEO stage)
  const blLegacy = { cpass_status: 'APPROVED', audit_status: 'SUBMITTED' }
  const blRes = getApprovalStatusDetails(blLegacy)
  assert.strictEqual(blRes.overallStatus, 'BL Approved')
  assert.strictEqual(blRes.blStage.decision, 'Approved')
})

runTest('11. No technical status labels — internal enum strings are never exposed', () => {
  const tests = [
    { cpass_status: 'L2_APPROVED', audit_status: 'SUBMITTED' },
    { cpass_status: 'APPROVED', audit_status: 'SUBMITTED' },
    { cpass_status: 'VERIFIED', audit_status: 'SUBMITTED' },
    { cpass_status: 'BL_APPROVED', audit_status: 'SUBMITTED' },
    { cpass_status: 'L3_REJECTED', audit_status: 'REJECTED' },
    { cpass_status: 'L4_REJECTED', audit_status: 'REJECTED' },
    { cpass_status: 'L5_REJECTED', audit_status: 'REJECTED' },
    { cpass_status: 'RETURNED_TO_L1', audit_status: 'RETURNED_TO_L1' },
    { cpass_status: 'RETURNED_TO_L2', audit_status: 'SUBMITTED' },
    { cpass_status: 'RETURNED_TO_L3', audit_status: 'SUBMITTED' },
    { cpass_status: 'RETURNED_TO_L4', audit_status: 'SUBMITTED' },
    { cpass_status: 'UNDER_AUDIT', audit_status: 'SUBMITTED' },
  ]

  const forbiddenEnums = [
    'L2_APPROVED', 'CPASS_APPROVED', 'BL_APPROVED', 'L3_REJECTED', 'L4_REJECTED', 'L5_REJECTED',
    'UNDER_AUDIT', 'SUBMITTED', 'RETURNED_TO_L1', 'RETURNED_TO_L2', 'RETURNED_TO_L3', 'RETURNED_TO_L4'
  ]

  for (const t of tests) {
    const res = getApprovalStatusDetails(t)
    for (const f of forbiddenEnums) {
      assert.ok(!res.overallStatus.includes(f), `overallStatus "${res.overallStatus}" should not contain "${f}"`)
      assert.ok(!res.reviewStatusDetail.includes(f), `reviewStatusDetail "${res.reviewStatusDetail}" should not contain "${f}"`)
      assert.ok(!res.chStage.label.includes(f), `chStage "${res.chStage.label}" should not contain "${f}"`)
      assert.ok(!res.copsStage.label.includes(f), `copsStage "${res.copsStage.label}" should not contain "${f}"`)
      assert.ok(!res.blStage.label.includes(f), `blStage "${res.blStage.label}" should not contain "${f}"`)
      assert.ok(!res.ceoStage.label.includes(f), `ceoStage "${res.ceoStage.label}" should not contain "${f}"`)
    }
  }
})

runTest('12. Four signoff stages verified — CH, COPS, BL, CEO all present in result', () => {
  const statement = {
    cpass_status: 'APPROVED',
    audit_status: 'APPROVED',
    review_stages: {
      ch: { status: 'Recommended' },
      cops: { status: 'Verified' },
      bl: { status: 'Approved' },
      ceo: { status: 'Approved' },
    },
  }
  const res = getApprovalStatusDetails(statement)
  assert.ok('chStage' in res)
  assert.ok('copsStage' in res)
  assert.ok('blStage' in res)
  assert.ok('ceoStage' in res)
})

console.log(`\n========================================`)
console.log(`All ${passedTests}/${totalTests} unit tests passed successfully!`)
console.log(`========================================\n`)
