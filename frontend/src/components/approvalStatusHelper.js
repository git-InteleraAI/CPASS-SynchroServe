/**
 * CPASS Statement Approval Status Helper
 *
 * Normalizes multi-level review stages (CH - L2, COPS - L3, BL - L4) and maps them
 * to human-readable labels, preventing technical enum display and duplicate status presentation.
 */

export function getApprovalStatusDetails(statementData, currentSignoffs) {
  if (!statementData) {
    return {
      overallStatus: 'Pending Review',
      overallBadgeClass: 'pending',
      reviewStatusDetail: 'Pending Review',
      chStage: { decision: 'Pending', label: 'CH — Pending', badgeClass: 'pending', reviewer: '—', date: '—', remarks: '' },
      copsStage: { decision: 'Pending', label: 'COPS — Pending', badgeClass: 'pending', reviewer: '—', date: '—', remarks: '' },
      blStage: { decision: 'Pending', label: 'BL — Pending', badgeClass: 'pending', reviewer: '—', date: '—', remarks: '' },
    }
  }

  const audit = statementData.audit || {}
  const rawAudit = (statementData.audit_status || audit.audit_status || '').toUpperCase()
  const rawCpass = (statementData.cpass_status || audit.cpass_status || '').toUpperCase()
  const signoff = currentSignoffs || statementData.signoff_details || audit.signoff_details || {}
  const rawStages = statementData.review_stages || signoff.review_stages || audit.review_stages || {}

  // Extract raw stage objects
  const chRaw = rawStages.ch || (rawStages.ch_status ? { status: rawStages.ch_status } : null)
  const copsRaw = rawStages.cops || (rawStages.cops_status ? { status: rawStages.cops_status } : null)
  const blRaw = rawStages.bl || (rawStages.bl_status ? { status: rawStages.bl_status } : null)

  const chObj = typeof chRaw === 'object' && chRaw !== null ? { ...chRaw } : { status: typeof chRaw === 'string' ? chRaw : '' }
  const copsObj = typeof copsRaw === 'object' && copsRaw !== null ? { ...copsRaw } : { status: typeof copsRaw === 'string' ? copsRaw : '' }
  const blObj = typeof blRaw === 'object' && blRaw !== null ? { ...blRaw } : { status: typeof blRaw === 'string' ? blRaw : '' }

  const chSignoff = signoff.centre_head || {}
  const copsSignoff = signoff.cops_team || {}
  const blSignoff = signoff.business_leader || {}

  const norm = (s) => (String(s || '').trim().toLowerCase())
  const chStatusNorm = norm(chObj.status).replace(/_/g, ' ')

  // Check if candidate is currently returned to L1 (and not resubmitted)
  const isReturnedToL1 = (
    rawAudit === 'RETURNED_TO_L1' ||
    rawCpass === 'RETURNED_TO_L1' ||
    chStatusNorm === 'returned to l1' ||
    chStatusNorm === 'returned' ||
    Boolean(signoff.return_to_l1 && rawAudit !== 'SUBMITTED' && rawCpass !== 'UNDER_AUDIT' && chStatusNorm !== 'pending' && chStatusNorm !== 'approved' && chStatusNorm !== 'recommended')
  ) && (
    rawAudit !== 'SUBMITTED' &&
    rawCpass !== 'UNDER_AUDIT' &&
    chStatusNorm !== 'pending' &&
    chStatusNorm !== 'approved' &&
    chStatusNorm !== 'recommended'
  )

  // 1. Resolve CH Stage Decision
  let chDecision = 'Pending'
  if (isReturnedToL1) {
    chDecision = 'Rejected'
  } else if (chStatusNorm === 'rejected' || norm(chSignoff.status) === 'rejected' || (rawAudit === 'REJECTED' && !signoff.rejected_stage && rawCpass !== 'L3_REJECTED' && rawCpass !== 'L4_REJECTED')) {
    chDecision = 'Rejected'
  } else if (
    chStatusNorm === 'recommended' ||
    chStatusNorm === 'approved' ||
    chSignoff.confirmed ||
    chSignoff.recommended ||
    chSignoff.approved ||
    signoff.l2_approval?.approved ||
    rawCpass === 'L2_APPROVED' ||
    rawCpass === 'APPROVED' ||
    rawCpass === 'CPASS_APPROVED' ||
    rawCpass === 'VERIFIED' ||
    rawCpass === 'L3_REJECTED' ||
    rawCpass === 'L4_REJECTED' ||
    signoff.rejected_stage === 'cops' ||
    signoff.rejected_stage === 'bl'
  ) {
    chDecision = 'Approved'
  }

  // 2. Resolve COPS Stage Decision
  let copsDecision = 'Pending'
  const copsStatusNorm = norm(copsObj.status)
  if (copsStatusNorm === 'rejected' || norm(copsSignoff.status) === 'rejected' || signoff.rejected_stage === 'cops' || rawCpass === 'L3_REJECTED') {
    copsDecision = 'Rejected'
  } else if (
    copsStatusNorm === 'verified' ||
    copsStatusNorm === 'approved' ||
    copsSignoff.confirmed ||
    copsSignoff.verified ||
    copsSignoff.approved ||
    signoff.rejected_stage === 'bl' ||
    rawCpass === 'L4_REJECTED' ||
    ((rawCpass === 'APPROVED' || rawCpass === 'CPASS_APPROVED' || rawCpass === 'VERIFIED') && chDecision === 'Approved')
  ) {
    copsDecision = 'Approved'
  }

  // 3. Resolve BL Stage Decision
  let blDecision = 'Pending'
  const blStatusNorm = norm(blObj.status)
  if (blStatusNorm === 'rejected' || norm(blSignoff.status) === 'rejected' || signoff.rejected_stage === 'bl' || rawCpass === 'L4_REJECTED') {
    blDecision = 'Rejected'
  } else if (
    blStatusNorm === 'approved' ||
    blSignoff.confirmed ||
    blSignoff.approved ||
    ((rawCpass === 'APPROVED' || rawCpass === 'CPASS_APPROVED') && copsDecision === 'Approved')
  ) {
    blDecision = 'Approved'
  }

  const getBadgeClass = (dec) => {
    switch (dec) {
      case 'Approved': return 'approved'
      case 'Rejected': return 'rejected'
      case 'Returned to L1': return 'returned'
      default: return 'pending'
    }
  }

  const chStage = {
    decision: chDecision,
    label: `CH — ${chDecision}`,
    badgeClass: getBadgeClass(chDecision),
    reviewer: chObj.reviewer_name || chSignoff.name || signoff.l2_approval?.approver_name || (chDecision === 'Approved' ? 'Centre Head' : '—'),
    date: chObj.date || chSignoff.date || signoff.l2_approval?.approval_date || (chDecision === 'Approved' && statementData.finalized_at ? new Date(statementData.finalized_at).toLocaleDateString('en-IN') : '—'),
    remarks: chObj.remarks || chSignoff.remarks || signoff.l2_approval?.remarks || (chDecision === 'Approved' ? 'Dossier and physical records verified.' : (chDecision === 'Pending' ? 'Pending Centre Head verification.' : (isReturnedToL1 ? 'Returned to L1 coordinator for corrections.' : 'Dossier verification rejected.'))),
    return_reason: chObj.return_reason || chObj.reason || statementData.return_reason || audit.return_reason || signoff.return_to_l1?.return_reason || '',
    rejection_reason: chObj.rejection_reason || chObj.reason || statementData.rejection_reason || audit.rejection_reason || '',
  }

  const copsStage = {
    decision: copsDecision,
    label: `COPS — ${copsDecision}`,
    badgeClass: getBadgeClass(copsDecision),
    reviewer: copsObj.reviewer_name || copsSignoff.name || (copsDecision === 'Approved' ? 'COPS Auditor' : '—'),
    date: copsObj.date || copsSignoff.date || '—',
    remarks: copsObj.remarks || copsSignoff.remarks || (copsDecision === 'Approved' ? 'Document criteria and salary credits audited.' : (copsDecision === 'Pending' ? 'Pending COPS audit.' : 'Document audit rejected.')),
    rejection_reason: copsObj.rejection_reason || copsObj.reason || '',
  }

  const blStage = {
    decision: blDecision,
    label: `BL — ${blDecision}`,
    badgeClass: getBadgeClass(blDecision),
    reviewer: blObj.reviewer_name || blSignoff.name || (blDecision === 'Approved' ? 'Business Leader' : '—'),
    date: blObj.date || blSignoff.date || '—',
    remarks: blObj.remarks || blSignoff.remarks || (blDecision === 'Approved' ? 'Placement outcome approved for compliance.' : (blDecision === 'Pending' ? 'Pending Business Leader approval.' : 'Business approval rejected.')),
    rejection_reason: blObj.rejection_reason || blObj.reason || '',
  }

  // 4. Overall Status & Review Status detail
  let overallStatus = 'Pending CH Review'
  let overallBadgeClass = 'pending'
  let reviewStatusDetail = 'Awaiting CH Verification'

  if (rawAudit === 'DRAFT') {
    overallStatus = 'Draft'
    overallBadgeClass = 'draft'
    reviewStatusDetail = 'Draft (Not Submitted)'
  } else if (blDecision === 'Rejected') {
    overallStatus = 'BL Rejected'
    overallBadgeClass = 'rejected'
    reviewStatusDetail = blStage.rejection_reason ? `Rejected at BL Approval: ${blStage.rejection_reason}` : 'Rejected at BL Approval'
  } else if (copsDecision === 'Rejected') {
    overallStatus = 'COPS Rejected'
    overallBadgeClass = 'rejected'
    reviewStatusDetail = copsStage.rejection_reason ? `Rejected at COPS Audit: ${copsStage.rejection_reason}` : 'Rejected at COPS Audit'
  } else if (isReturnedToL1) {
    overallStatus = 'CH Rejected'
    overallBadgeClass = 'rejected'
    const returnReason = chStage.return_reason || chStage.rejection_reason
    reviewStatusDetail = returnReason ? `CH Rejected — Returned for Corrections: ${returnReason}` : 'CH Rejected — Returned for Corrections'
  } else if (chDecision === 'Rejected' || (rawAudit === 'REJECTED' && !signoff.rejected_stage)) {
    overallStatus = 'CH Rejected'
    overallBadgeClass = 'rejected'
    reviewStatusDetail = chStage.rejection_reason ? `Rejected at CH Review: ${chStage.rejection_reason}` : 'Rejected at CH Review'
  } else if (blDecision === 'Approved') {
    overallStatus = 'BL Approved'
    overallBadgeClass = 'approved'
    reviewStatusDetail = 'All Reviews Complete'
  } else if (copsDecision === 'Approved') {
    overallStatus = 'COPS Approved'
    overallBadgeClass = 'approved'
    reviewStatusDetail = 'Awaiting BL Approval'
  } else if (chDecision === 'Approved') {
    overallStatus = 'CH Approved'
    overallBadgeClass = 'approved'
    reviewStatusDetail = 'Awaiting COPS Audit'
  } else {
    overallStatus = 'Pending CH Review'
    overallBadgeClass = 'pending'
    reviewStatusDetail = 'Awaiting CH Verification'
  }

  return {
    overallStatus,
    overallBadgeClass,
    reviewStatusDetail,
    chStage,
    copsStage,
    blStage,
  }
}
