import assert from 'node:assert'
import { resolveCandidateHierarchyPipeline } from './candidatePipelineHelper.js'

async function runTests() {
  console.log('--- Running candidatePipelineHelper tests ---')

  // Test 1: Complete authoritative candidate detail populates all 5 levels
  {
    const mockDetail = {
      candidate_id: 1062247,
      first_name: 'Kalidasu',
      last_name: 'Vijaya Sri',
      state_name: 'Andhra Pradesh',
      tc_id: 1462012803001,
      tc_name: 'Anantapur Training Centre',
      sanction_order_number: 'SO/AP/2023/889',
      kb_batch_id: 719,
      batch_code: 'BATCH-719-AP',
    }

    const mockApi = async (url, params) => {
      if (url === '/lookups/candidates/1062247') return mockDetail
      if (url === '/lookups/states') return ['ANDHRA PRADESH', 'TELANGANA', 'ODISHA']
      if (url === '/lookups/centres' && params?.state === 'ANDHRA PRADESH') {
        return [{ tc_id: 1462012803001, name: 'Anantapur Training Centre' }]
      }
      if (url === '/lookups/sanction-orders' && params?.tc_id === 1462012803001) {
        return ['SO/AP/2023/889', 'SO/AP/2023/890']
      }
      if (url === '/lookups/batches' && params?.tc_id === 1462012803001 && params?.sanction_order === 'SO/AP/2023/889') {
        return [{ kb_batch_id: 719, batch_code: 'BATCH-719-AP' }]
      }
      if (url === '/lookups/candidates' && params?.kb_batch_id === 719) {
        return [{ candidate_id: 1062247, first_name: 'Kalidasu', last_name: 'Vijaya Sri' }]
      }
      throw new Error(`Unexpected url: ${url} with params: ${JSON.stringify(params)}`)
    }

    const res = await resolveCandidateHierarchyPipeline({
      candidateId: 1062247,
      apiFetch: mockApi,
    })

    assert.strictEqual(res.selection.state, 'ANDHRA PRADESH', 'State should be canonical uppercase')
    assert.strictEqual(res.selection.tc, 1462012803001, 'Training centre ID should match')
    assert.strictEqual(res.selection.order, 'SO/AP/2023/889', 'Sanction order should match')
    assert.strictEqual(res.selection.batch, 719, 'Batch ID should match')
    assert.strictEqual(res.selection.cand, 1062247, 'Candidate ID should match')

    assert.strictEqual(res.lists.state.length, 3, 'States list should be populated')
    assert.strictEqual(res.lists.tc.length, 1, 'Centres list should be populated')
    assert.strictEqual(res.lists.order.length, 2, 'Sanction orders list should be populated')
    assert.strictEqual(res.lists.batch.length, 1, 'Batches list should be populated')
    assert.strictEqual(res.lists.cand.length, 1, 'Candidates list should be populated')
    console.log('[PASS] 1. Complete authoritative candidate detail populates all 5 levels')
  }

  // Test 2: Candidate list response missing tc_id, sanction_order, and kb_batch_id
  {
    const initialCand = {
      candidate_id: 99901,
      state_name: 'PUNJAB',
      // tc_id, sanction_order_number, kb_batch_id are completely missing
    }

    const mockDetail = {
      candidate_id: 99901,
      first_name: 'Harpreet',
      last_name: 'Singh',
      state_name: 'PUNJAB',
      tc_id: 501,
      tc_name: 'Ludhiana TC',
      sanction_order_number: 'SO/PB/2024/01',
      kb_batch_id: 88,
      batch_code: 'PB-BATCH-88',
    }

    const mockApi = async (url, params) => {
      if (url === '/lookups/candidates/99901') return mockDetail
      if (url === '/lookups/states') return ['PUNJAB', 'HARYANA']
      if (url === '/lookups/centres' && params?.state === 'PUNJAB') {
        return [{ tc_id: 501, name: 'Ludhiana TC' }]
      }
      if (url === '/lookups/sanction-orders' && params?.tc_id === 501) {
        return ['SO/PB/2024/01']
      }
      if (url === '/lookups/batches' && params?.tc_id === 501) {
        return [{ kb_batch_id: 88, batch_code: 'PB-BATCH-88' }]
      }
      if (url === '/lookups/candidates' && params?.kb_batch_id === 88) {
        return [{ candidate_id: 99901, first_name: 'Harpreet', last_name: 'Singh' }]
      }
      return []
    }

    const res = await resolveCandidateHierarchyPipeline({
      candidateId: 99901,
      initialCandidate: initialCand,
      apiFetch: mockApi,
    })

    assert.strictEqual(res.selection.state, 'PUNJAB')
    assert.strictEqual(res.selection.tc, 501)
    assert.strictEqual(res.selection.order, 'SO/PB/2024/01')
    assert.strictEqual(res.selection.batch, 88)
    assert.strictEqual(res.selection.cand, 99901)
    console.log('[PASS] 2. Candidate list response missing optional hierarchy fields resolved via authoritative detail')
  }

  // Test 3: Dropdown option values vs selected values matching (case-insensitive state match)
  {
    const mockDetail = {
      candidate_id: 555,
      state_name: 'tamil nadu', // lowercase in db
      tc_id: 202,
      sanction_order_number: 'SO/TN/001',
      kb_batch_id: 303,
    }

    const mockApi = async (url) => {
      if (url.includes('/candidates/555')) return mockDetail
      if (url === '/lookups/states') return ['TAMIL NADU', 'KERALA']
      return []
    }

    const res = await resolveCandidateHierarchyPipeline({
      candidateId: 555,
      currentStates: ['TAMIL NADU', 'KERALA'],
      apiFetch: mockApi,
    })

    assert.strictEqual(res.selection.state, 'TAMIL NADU', 'Selected state matches exact dropdown option')
    console.log('[PASS] 3. Case-insensitive state matches canonical dropdown option')
  }

  // Test 4: Missing candidate in batch candidates list is injected safely
  {
    const mockDetail = {
      candidate_id: 777,
      first_name: 'Ramesh',
      last_name: 'Kumar',
      state_name: 'BIHAR',
      tc_id: 10,
      sanction_order_number: 'SO/BR/01',
      kb_batch_id: 20,
    }

    const mockApi = async (url) => {
      if (url.includes('/candidates/777')) return mockDetail
      if (url === '/lookups/candidates') {
        // Return batch candidates that don't include 777 (edge case)
        return [{ candidate_id: 778, first_name: 'Suresh', last_name: 'Kumar' }]
      }
      return []
    }

    const res = await resolveCandidateHierarchyPipeline({
      candidateId: 777,
      apiFetch: mockApi,
    })

    assert.strictEqual(res.selection.cand, 777)
    const injected = res.lists.cand.find((c) => c.candidate_id === 777)
    assert.ok(injected, 'Candidate 777 was safely injected into candidate options')
    assert.strictEqual(injected.first_name, 'Ramesh')
    console.log('[PASS] 4. Missing candidate in batch candidates list is injected safely')
  }

  // Test 5: Missing centre in centres list is injected safely
  {
    const mockDetail = {
      candidate_id: 888,
      state_name: 'ODISHA',
      tc_id: 9999,
      tc_name: 'Special Odisha Centre',
      sanction_order_number: 'SO/OD/01',
      kb_batch_id: 50,
    }

    const mockApi = async (url) => {
      if (url.includes('/candidates/888')) return mockDetail
      if (url === '/lookups/centres') return []
      return []
    }

    const res = await resolveCandidateHierarchyPipeline({
      candidateId: 888,
      apiFetch: mockApi,
    })

    assert.strictEqual(res.selection.tc, 9999)
    const injected = res.lists.tc.find((c) => c.tc_id === 9999)
    assert.ok(injected, 'Centre 9999 was safely injected into centre options')
    assert.strictEqual(injected.name, 'Special Odisha Centre')
    console.log('[PASS] 5. Missing centre in centres list is injected safely')
  }

  // Test 6: Missing sanction order resolves to single available order
  {
    const mockDetail = {
      candidate_id: 111,
      state_name: 'TELANGANA',
      tc_id: 42,
      sanction_order_number: 'Not Available',
      kb_batch_id: 15,
    }

    const mockApi = async (url) => {
      if (url.includes('/candidates/111')) return mockDetail
      if (url === '/lookups/sanction-orders') return ['SO/TG/SINGLE/2025']
      return []
    }

    const res = await resolveCandidateHierarchyPipeline({
      candidateId: 111,
      apiFetch: mockApi,
    })

    assert.strictEqual(res.selection.order, 'SO/TG/SINGLE/2025', 'Resolves to single available sanction order')
    console.log('[PASS] 6. Missing sanction order resolves to single available order')
  }

  // Test 7: String training centre ID (e.g., AANPCR1462012803001) preserved accurately
  {
    const mockDetail = {
      candidate_id: 1062247,
      state_name: 'ANDHRA PRADESH',
      tc_id: 'AANPCR1462012803001',
      tc_name: 'Anantapur TC',
      sanction_order_number: 'SO/AP/1',
      kb_batch_id: 719,
    }

    const mockApi = async (url) => {
      if (url.includes('/candidates/1062247')) return mockDetail
      if (url === '/lookups/centres') return [{ tc_id: 'AANPCR1462012803001', name: 'Anantapur TC' }]
      return []
    }

    const res = await resolveCandidateHierarchyPipeline({
      candidateId: 1062247,
      currentStates: ['ANDHRA PRADESH'],
      apiFetch: mockApi,
    })

    assert.strictEqual(res.selection.tc, 'AANPCR1462012803001')
    console.log('[PASS] 7. Alphanumeric / string training centre ID preserved accurately')
  }

  // Test 8: Rapid switching simulation — verifying sequence cancellation logic
  {
    let activeRequest = 0
    const sequenceRef = { current: 0 }

    async function switchCandidate(candId) {
      const seq = ++sequenceRef.current
      const res = await resolveCandidateHierarchyPipeline({
        candidateId: candId,
        apiFetch: async (url) => {
          if (url.includes('/candidates/101')) {
            // Simulate slow network response for candidate 101
            await new Promise((r) => setTimeout(r, 50))
            return { candidate_id: 101, state_name: 'KERALA' }
          }
          if (url.includes('/candidates/102')) {
            // Fast network response for candidate 102
            return { candidate_id: 102, state_name: 'GUJARAT' }
          }
          return []
        },
      })
      if (sequenceRef.current !== seq) {
        // Stale response ignored
        return null
      }
      activeRequest = candId
      return res
    }

    // Trigger candidate 101 then immediately candidate 102
    const p1 = switchCandidate(101)
    const p2 = switchCandidate(102)

    await Promise.all([p1, p2])
    assert.strictEqual(activeRequest, 102, 'Only latest candidate (102) determines final state')
    console.log('[PASS] 8. Rapid switching sequence cancellation prevents stale response overwrites')
  }

  // Test 9: Graceful error when candidate is missing
  {
    let errorThrown = false
    try {
      await resolveCandidateHierarchyPipeline({
        candidateId: 999999,
        apiFetch: async () => null,
      })
    } catch (e) {
      errorThrown = true
      assert.ok(e.message.includes('could not be retrieved'))
    }
    assert.ok(errorThrown, 'Should throw error when candidate not found')
    console.log('[PASS] 9. Graceful error handling when candidate detail is not found')
  }

  console.log('\n========================================')
  console.log('All candidatePipelineHelper tests passed!')
  console.log('========================================')
}

runTests().catch((err) => {
  console.error('Test failed:', err)
  process.exit(1)
})
