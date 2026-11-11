import { api } from './api.js'

/**
 * Resolves the authoritative candidate hierarchy and fetches all five-level
 * dropdown option lists in coordination, ensuring that selected values and option
 * lists match perfectly without race conditions or empty selections.
 *
 * Applicable across L1, L2, L3, L4, and L5 dashboard metric dossier workflows.
 *
 * @param {Object} params
 * @param {string|number} params.candidateId - ID of candidate to select
 * @param {Object} [params.initialCandidate] - Optional candidate row from card modal
 * @param {Array<string>} [params.currentStates] - Currently loaded states in dashboard
 * @param {Function} [params.apiFetch] - API fetch function (defaults to api)
 * @returns {Promise<{ detail: Object, selection: Object, lists: Object }>}
 */
export async function resolveCandidateHierarchyPipeline({
  candidateId,
  initialCandidate = null,
  currentStates = [],
  apiFetch = api,
}) {
  if (!candidateId) {
    throw new Error('A candidate ID is required to resolve candidate hierarchy.')
  }

  const candId = parseInt(candidateId, 10) || candidateId

  // 1. Retrieve authoritative candidate details
  const detail = await apiFetch(`/lookups/candidates/${candId}`)
  if (!detail) {
    throw new Error(`Candidate ${candId} could not be retrieved.`)
  }

  // 2. Resolve target hierarchy identifiers from authoritative detail (with fallback to initialCandidate)
  const rawState = detail.state_name && detail.state_name !== 'Not Available'
    ? detail.state_name
    : (initialCandidate?.state_name && initialCandidate.state_name !== 'Not Available' ? initialCandidate.state_name : null)

  const targetTcId = detail.tc_id != null && detail.tc_id !== ''
    ? detail.tc_id
    : (initialCandidate?.tc_id != null && initialCandidate.tc_id !== '' ? initialCandidate.tc_id : null)

  const rawOrder = detail.sanction_order_number && detail.sanction_order_number !== 'Not Available' && detail.sanction_order_number !== '—'
    ? detail.sanction_order_number
    : (initialCandidate?.sanction_order_number && initialCandidate.sanction_order_number !== '—' && initialCandidate.sanction_order_number !== 'Not Available' ? initialCandidate.sanction_order_number : null)

  const targetBatchId = detail.kb_batch_id != null && detail.kb_batch_id !== ''
    ? detail.kb_batch_id
    : (initialCandidate?.kb_batch_id != null && initialCandidate.kb_batch_id !== '' ? initialCandidate.kb_batch_id : null)

  // 3. Resolve states list
  let statesList = Array.isArray(currentStates) && currentStates.length > 0 ? [...currentStates] : []
  if (statesList.length === 0) {
    try {
      const res = await apiFetch('/lookups/states')
      statesList = Array.isArray(res) ? res : []
    } catch (err) {
      console.warn('Failed to fetch states in pipeline:', err)
    }
  }

  // Match state against statesList (case-insensitive canonical match)
  let matchedState = ''
  if (rawState) {
    const foundState = statesList.find(
      (s) => String(s).trim().toUpperCase() === String(rawState).trim().toUpperCase()
    )
    if (foundState) {
      matchedState = foundState
    } else {
      matchedState = rawState
      statesList = [...statesList, rawState]
    }
  } else if (statesList.length === 1) {
    matchedState = statesList[0]
  }

  // 4. Fetch dependent option lists in parallel whenever parameters are known
  const centresPromise = matchedState
    ? apiFetch('/lookups/centres', { state: matchedState }).catch(() => [])
    : Promise.resolve([])

  const ordersPromise = targetTcId != null
    ? apiFetch('/lookups/sanction-orders', { tc_id: targetTcId }).catch(() => [])
    : Promise.resolve([])

  const batchesPromise = (targetTcId != null && rawOrder)
    ? apiFetch('/lookups/batches', { tc_id: targetTcId, sanction_order: rawOrder }).catch(() => [])
    : Promise.resolve([])

  const candsPromise = targetBatchId != null
    ? apiFetch('/lookups/candidates', { kb_batch_id: targetBatchId }).catch(() => [])
    : Promise.resolve([])

  const [centresRes, ordersRes, batchesRes, candsRes] = await Promise.all([
    centresPromise,
    ordersPromise,
    batchesPromise,
    candsPromise,
  ])

  let centresList = Array.isArray(centresRes) ? [...centresRes] : []
  let ordersList = Array.isArray(ordersRes) ? [...ordersRes] : []
  let batchesList = Array.isArray(batchesRes) ? [...batchesRes] : []
  let candidatesList = Array.isArray(candsRes) ? [...candsRes] : []

  // Resolve Training Centre
  let resolvedTcId = ''
  if (targetTcId != null) {
    const matchedCentre = centresList.find((c) => String(c.tc_id) === String(targetTcId))
    if (matchedCentre) {
      resolvedTcId = matchedCentre.tc_id
    } else {
      resolvedTcId = targetTcId
      centresList.push({
        tc_id: targetTcId,
        name: detail.tc_name || initialCandidate?.tc_name || `Centre ${targetTcId}`,
        tc_state_name: detail.tc_state_name || matchedState,
      })
    }
  } else if (centresList.length === 1) {
    resolvedTcId = centresList[0].tc_id
  }

  // If sanction orders were not fetched because targetTcId was just resolved from centresList
  if (ordersList.length === 0 && resolvedTcId) {
    try {
      const orders = await apiFetch('/lookups/sanction-orders', { tc_id: resolvedTcId })
      ordersList = Array.isArray(orders) ? orders : []
    } catch (_) {}
  }

  // Resolve Sanction Order
  let resolvedOrder = ''
  if (rawOrder) {
    const matchedOrder = ordersList.find((o) => String(o).trim() === String(rawOrder).trim())
    if (matchedOrder) {
      resolvedOrder = matchedOrder
    } else {
      resolvedOrder = rawOrder
      ordersList.push(rawOrder)
    }
  } else if (ordersList.length === 1) {
    resolvedOrder = ordersList[0]
  }

  // If batches were not fetched because resolvedOrder was just resolved
  if (batchesList.length === 0 && resolvedTcId && resolvedOrder) {
    try {
      const batches = await apiFetch('/lookups/batches', { tc_id: resolvedTcId, sanction_order: resolvedOrder })
      batchesList = Array.isArray(batches) ? batches : []
    } catch (_) {}
  }

  // Resolve Batch
  let resolvedBatchId = ''
  if (targetBatchId != null) {
    const matchedBatch = batchesList.find((b) => String(b.kb_batch_id) === String(targetBatchId))
    if (matchedBatch) {
      resolvedBatchId = matchedBatch.kb_batch_id
    } else {
      resolvedBatchId = targetBatchId
      batchesList.push({
        kb_batch_id: targetBatchId,
        batch_code: detail.batch_code || initialCandidate?.batch_code || `Batch ${targetBatchId}`,
        trade_name: detail.trade_name || null,
      })
    }
  } else if (batchesList.length === 1) {
    resolvedBatchId = batchesList[0].kb_batch_id
  }

  // If candidates were not fetched because resolvedBatchId was just resolved
  if (candidatesList.length === 0 && resolvedBatchId) {
    try {
      const cands = await apiFetch('/lookups/candidates', { kb_batch_id: resolvedBatchId })
      candidatesList = Array.isArray(cands) ? cands : []
    } catch (_) {}
  }

  // Resolve Candidate
  let resolvedCandId = candId
  const matchedCand = candidatesList.find((c) => String(c.candidate_id) === String(candId))
  if (matchedCand) {
    resolvedCandId = matchedCand.candidate_id
  } else {
    candidatesList.push({
      candidate_id: candId,
      first_name: detail.first_name || initialCandidate?.first_name || '',
      last_name: detail.last_name || initialCandidate?.last_name || '',
    })
  }

  return {
    detail,
    selection: {
      state: matchedState,
      tc: resolvedTcId,
      order: resolvedOrder,
      batch: resolvedBatchId,
      cand: resolvedCandId,
    },
    lists: {
      state: statesList,
      tc: centresList,
      order: ordersList,
      batch: batchesList,
      cand: candidatesList,
    },
  }
}
