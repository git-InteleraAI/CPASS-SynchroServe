/**
 * CPASS Statement Approval Status Helper
 *
 * Normalizes multi-level review stages (CH - L2, COPS - L3, BL - L4, CEO - L5)
 * and maps them to human-readable labels, preventing technical enum display
 * and duplicate status presentation.
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
      ceoStage: { decision: 'Pending', label: 'CEO — Pending', badgeClass: 'pending', reviewer: '—', date: '—', remarks: '' },
      activeReturn: null,
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
  const ceoRaw = rawStages.ceo || (rawStages.ceo_status ? { status: rawStages.ceo_status } : null)

  const chObj = typeof chRaw === 'object' && chRaw !== null ? { ...chRaw } : { status: typeof chRaw === 'string' ? chRaw : '' }
  const copsObj = typeof copsRaw === 'object' && copsRaw !== null ? { ...copsRaw } : { status: typeof copsRaw === 'string' ? copsRaw : '' }
  const blObj = typeof blRaw === 'object' && blRaw !== null ? { ...blRaw } : { status: typeof blRaw === 'string' ? blRaw : '' }
  const ceoObj = typeof ceoRaw === 'object' && ceoRaw !== null ? { ...ceoRaw } : { status: typeof ceoRaw === 'string' ? ceoRaw : '' }

  const chSignoff = signoff.centre_head || {}
  const copsSignoff = signoff.cops_team || {}
  const blSignoff = signoff.business_leader || {}
  const ceoSignoff = signoff.ceo || {}

  const norm = (s) => String(s || '').trim().toLowerCase()
  const chStatusNorm = norm(chObj.status).replace(/_/g, ' ')
  const copsStatusNorm = norm(copsObj.status).replace(/_/g, ' ')
  const blStatusNorm = norm(blObj.status).replace(/_/g, ' ')
  const ceoStatusNorm = norm(ceoObj.status).replace(/_/g, ' ')

  // Check active return
  const activeReturn = signoff.active_return || (rawAudit === 'RETURNED_TO_L1' || rawCpass === 'RETURNED_TO_L1' ? signoff.return_to_l1 : null)

  const isReturned = (
    rawAudit === 'RETURNED_TO_L1' ||
    rawCpass.startsWith('RETURNED_TO_') ||
    chStatusNorm === 'returned to l1' ||
    chStatusNorm === 'returned' ||
    copsStatusNorm.startsWith('returned') ||
    blStatusNorm.startsWith('returned') ||
    ceoStatusNorm.startsWith('returned') ||
    Boolean(activeReturn && rawAudit !== 'SUBMITTED' && rawCpass !== 'UNDER_AUDIT' && rawCpass !== 'BL_APPROVED' && rawCpass !== 'APPROVED')
  ) && (
    rawAudit !== 'SUBMITTED' || rawCpass.startsWith('RETURNED_TO_')
  )

  const isReturnedToL1 = rawAudit === 'RETURNED_TO_L1' || rawCpass === 'RETURNED_TO_L1' || chStatusNorm === 'returned to l1'

  // 1. Resolve CH Stage Decision
  let chDecision = 'Pending'
  if (isReturnedToL1) {
    chDecision = 'Rejected'
  } else if (chStatusNorm === 'rejected' || norm(chSignoff.status) === 'rejected' || (rawAudit === 'REJECTED' && !signoff.rejected_stage && rawCpass !== 'L3_REJECTED' && rawCpass !== 'L4_REJECTED' && rawCpass !== 'L5_REJECTED')) {
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
    rawCpass === 'BL_APPROVED' ||
    rawCpass === 'VERIFIED' ||
    rawCpass === 'L3_REJECTED' ||
    rawCpass === 'L4_REJECTED' ||
    rawCpass === 'L5_REJECTED' ||
    rawCpass === 'RETURNED_TO_L3' ||
    rawCpass === 'RETURNED_TO_L4' ||
    signoff.rejected_stage === 'cops' ||
    signoff.rejected_stage === 'bl' ||
    signoff.rejected_stage === 'ceo'
  ) {
    chDecision = chStatusNorm === 'recommended' ? 'Recommended' : 'Approved'
  }

  // 2. Resolve COPS Stage Decision
  let copsDecision = 'Pending'
  if (copsStatusNorm === 'rejected' || norm(copsSignoff.status) === 'rejected' || signoff.rejected_stage === 'cops' || rawCpass === 'L3_REJECTED') {
    copsDecision = 'Rejected'
  } else if (
    copsStatusNorm === 'verified' ||
    copsStatusNorm === 'approved' ||
    copsSignoff.confirmed ||
    copsSignoff.verified ||
    copsSignoff.approved ||
    signoff.rejected_stage === 'bl' ||
    signoff.rejected_stage === 'ceo' ||
    rawCpass === 'L4_REJECTED' ||
    rawCpass === 'L5_REJECTED' ||
    rawCpass === 'BL_APPROVED' ||
    rawCpass === 'RETURNED_TO_L4' ||
    ((rawCpass === 'APPROVED' || rawCpass === 'CPASS_APPROVED' || rawCpass === 'VERIFIED') && (chDecision === 'Approved' || chDecision === 'Recommended'))
  ) {
    copsDecision = copsStatusNorm === 'verified' ? 'Verified' : 'Approved'
  }

  // 3. Resolve BL Stage Decision
  let blDecision = 'Pending'
  if (blStatusNorm === 'rejected' || norm(blSignoff.status) === 'rejected' || signoff.rejected_stage === 'bl' || rawCpass === 'L4_REJECTED') {
    blDecision = 'Rejected'
  } else if (
    blStatusNorm === 'approved' ||
    blSignoff.confirmed ||
    blSignoff.approved ||
    signoff.rejected_stage === 'ceo' ||
    rawCpass === 'L5_REJECTED' ||
    rawCpass === 'BL_APPROVED' ||
    ((rawCpass === 'APPROVED' || rawCpass === 'CPASS_APPROVED') && (copsDecision === 'Approved' || copsDecision === 'Verified'))
  ) {
    blDecision = 'Approved'
  }

  // 4. Resolve CEO Stage Decision
  let ceoDecision = 'Pending'
  if (ceoStatusNorm === 'rejected' || norm(ceoSignoff.status) === 'rejected' || signoff.rejected_stage === 'ceo' || rawCpass === 'L5_REJECTED') {
    ceoDecision = 'Rejected'
  } else if (
    ceoStatusNorm === 'approved' ||
    ceoSignoff.confirmed ||
    ceoSignoff.approved ||
    ((rawCpass === 'APPROVED' || rawCpass === 'CPASS_APPROVED') && rawAudit === 'APPROVED' && blDecision === 'Approved')
  ) {
    ceoDecision = 'Approved'
  }

  const getBadgeClass = (dec) => {
    switch (dec) {
      case 'Approved':
      case 'Recommended':
      case 'Verified':
        return 'approved'
      case 'Rejected':
      case 'Returned to L1':
      case 'Returned to L2':
      case 'Returned to L3':
      case 'Returned to L4':
        return 'rejected'
      default:
        return 'pending'
    }
  }

  const formatStageDecision = (dec) => {
    if (!dec) return 'Pending'
    if (dec.toLowerCase().includes('return') || dec.toLowerCase().includes('reject')) return 'Rejected'
    return dec
  }

  const chDisplayDecision = formatStageDecision(chDecision)
  const copsDisplayDecision = formatStageDecision(copsDecision)
  const blDisplayDecision = formatStageDecision(blDecision)
  const ceoDisplayDecision = formatStageDecision(ceoDecision)

  const chStage = {
    decision: chDisplayDecision,
    label: `CH — ${chDisplayDecision}`,
    badgeClass: getBadgeClass(chDisplayDecision),
    reviewer: chObj.reviewer_name || chSignoff.name || signoff.l2_approval?.approver_name || (chDecision === 'Approved' || chDecision === 'Recommended' ? 'Centre Head' : '—'),
    date: chObj.date || chSignoff.date || signoff.l2_approval?.approval_date || ((chDecision === 'Approved' || chDecision === 'Recommended') && statementData.finalized_at ? new Date(statementData.finalized_at).toLocaleDateString('en-IN') : '—'),
    remarks: chObj.remarks || chSignoff.remarks || signoff.l2_approval?.remarks || (chDecision === 'Approved' || chDecision === 'Recommended' ? 'Dossier and physical records verified.' : (chDecision === 'Pending' ? 'Pending Centre Head recommendation.' : (isReturnedToL1 ? 'Returned to L1 coordinator for corrections.' : 'Dossier recommendation rejected.'))),
    return_reason: chObj.return_reason || chObj.reason || statementData.return_reason || audit.return_reason || signoff.return_to_l1?.return_reason || '',
    rejection_reason: chObj.rejection_reason || chObj.reason || statementData.rejection_reason || audit.rejection_reason || '',
  }

  const copsStage = {
    decision: copsDisplayDecision,
    label: `COPS — ${copsDisplayDecision}`,
    badgeClass: getBadgeClass(copsDisplayDecision),
    reviewer: copsObj.reviewer_name || copsSignoff.name || (copsDecision === 'Approved' || copsDecision === 'Verified' ? 'COPS Auditor' : '—'),
    date: copsObj.date || copsSignoff.date || '—',
    remarks: copsObj.remarks || copsSignoff.remarks || (copsDecision === 'Approved' || copsDecision === 'Verified' ? 'Document criteria and salary credits verified.' : (copsDecision === 'Pending' ? 'Pending COPS verification.' : 'Document audit rejected.')),
    rejection_reason: copsObj.rejection_reason || copsObj.reason || '',
  }

  const blStage = {
    decision: blDisplayDecision,
    label: `BL — ${blDisplayDecision}`,
    badgeClass: getBadgeClass(blDisplayDecision),
    reviewer: blObj.reviewer_name || blSignoff.name || (blDecision === 'Approved' ? 'Business Leader' : '—'),
    date: blObj.date || blSignoff.date || '—',
    remarks: blObj.remarks || blSignoff.remarks || (blDecision === 'Approved' ? 'Placement outcome approved for compliance.' : (blDecision === 'Pending' ? 'Pending Business Leader approval.' : 'Business approval rejected.')),
    rejection_reason: blObj.rejection_reason || blObj.reason || '',
  }

  const ceoStage = {
    decision: ceoDisplayDecision,
    label: `CEO — ${ceoDisplayDecision}`,
    badgeClass: getBadgeClass(ceoDisplayDecision),
    reviewer: ceoObj.reviewer_name || ceoSignoff.name || (ceoDecision === 'Approved' ? 'Chief Executive Officer' : '—'),
    date: ceoObj.date || ceoSignoff.date || '—',
    remarks: ceoObj.remarks || ceoSignoff.remarks || (ceoDecision === 'Approved' ? 'Sanctioned and final approval granted by CEO.' : (ceoDecision === 'Pending' ? 'Pending CEO sanction.' : 'CEO sanction rejected.')),
    rejection_reason: ceoObj.rejection_reason || ceoObj.reason || '',
  }

  // 5. Overall Status & Review Status detail
  let overallStatus = 'Pending CH Review'
  let overallBadgeClass = 'pending'
  let reviewStatusDetail = 'Awaiting CH Verification'

  if (rawAudit === 'DRAFT') {
    overallStatus = 'Draft'
    overallBadgeClass = 'draft'
    reviewStatusDetail = 'Draft (Not Submitted)'
  } else if (ceoDecision === 'Rejected') {
    overallStatus = 'Rejected'
    overallBadgeClass = 'rejected'
    reviewStatusDetail = ceoStage.rejection_reason ? `Rejected at CEO Sanction: ${ceoStage.rejection_reason}` : 'Rejected at CEO Sanction'
  } else if (blDecision === 'Rejected') {
    overallStatus = 'Rejected'
    overallBadgeClass = 'rejected'
    reviewStatusDetail = blStage.rejection_reason ? `Rejected at BL Approval: ${blStage.rejection_reason}` : 'Rejected at BL Approval'
  } else if (copsDecision === 'Rejected') {
    overallStatus = 'Rejected'
    overallBadgeClass = 'rejected'
    reviewStatusDetail = copsStage.rejection_reason ? `Rejected at COPS Audit: ${copsStage.rejection_reason}` : 'Rejected at COPS Audit'
  } else if (isReturnedToL1) {
    overallStatus = 'Rejected'
    overallBadgeClass = 'rejected'
    const returnReason = chStage.return_reason || chStage.rejection_reason
    reviewStatusDetail = returnReason ? `Rejected — Returned to L1 for Corrections: ${returnReason}` : 'Rejected — Returned to L1 for Corrections'
  } else if (isReturned && activeReturn) {
    const dest = activeReturn.destination || 'Corrections'
    overallStatus = 'Rejected'
    overallBadgeClass = 'rejected'
    const reason = activeReturn.reason || activeReturn.return_reason || ''
    reviewStatusDetail = reason ? `Rejected — Returned to ${dest} for Corrections: ${reason}` : `Rejected — Returned to ${dest} for Corrections`
  } else if (chDecision === 'Rejected' || (rawAudit === 'REJECTED' && !signoff.rejected_stage)) {
    overallStatus = 'Rejected'
    overallBadgeClass = 'rejected'
    reviewStatusDetail = chStage.rejection_reason ? `Rejected at CH Review: ${chStage.rejection_reason}` : 'Rejected at CH Review'
  } else if (ceoDecision === 'Approved') {
    overallStatus = 'All Reviews Complete'
    overallBadgeClass = 'approved'
    reviewStatusDetail = 'All Reviews Complete'
  } else if (blDecision === 'Approved') {
    overallStatus = 'BL Approved'
    overallBadgeClass = 'approved'
    reviewStatusDetail = 'Awaiting CEO Approval'
  } else if (copsDecision === 'Approved' || copsDecision === 'Verified') {
    overallStatus = 'COPS Approved'
    overallBadgeClass = 'approved'
    reviewStatusDetail = 'Awaiting BL Approval'
  } else if (chDecision === 'Approved' || chDecision === 'Recommended') {
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
    ceoStage,
    activeReturn,
  }
}
