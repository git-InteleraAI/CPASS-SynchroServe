import sys

path = "frontend/src/pages/L1Home.jsx"
with open(path, "rb") as f:
    raw = f.read()

content = raw.decode("utf-8").replace("\r\n", "\n")

# 1. Update formStateRef synchronization useEffect and autosave logic
# Find where Autosave State & References were added
target_state_refs = """  // Autosave State & References
  const [autosaveStatus, setAutosaveStatus] = useState('idle') // 'idle' | 'saving' | 'saved' | 'retrying' | 'error'
  const [autosaveLastSavedAt, setAutosaveLastSavedAt] = useState(null)
  const [autosaveError, setAutosaveError] = useState('')
  const isDirtyRef = useRef(false)
  const autosaveTimerRef = useRef(null)
  const inFlightSavePromiseRef = useRef(null)
  const saveSeqRef = useRef(0)
  const formStateRef = useRef({})"""

rep_state_refs = """  // Autosave State & References
  const [autosaveStatus, setAutosaveStatus] = useState('idle') // 'idle' | 'saving' | 'saved' | 'retrying' | 'error'
  const [autosaveLastSavedAt, setAutosaveLastSavedAt] = useState(null)
  const [autosaveError, setAutosaveError] = useState('')
  const isDirtyRef = useRef(false)
  const autosaveTimerRef = useRef(null)
  const inFlightSavePromiseRef = useRef(null)
  const saveSeqRef = useRef(0)
  const formStateRef = useRef({})

  // Keep formStateRef current for debounce execution without stale closure
  useEffect(() => {
    formStateRef.current = {
      sel,
      candDetail,
      lists,
      employerList,
      salaryDetailList,
      documentAudit,
      signoffDetails,
      auditRecord,
      auditLoadError,
      salaryRows,
      bankRows,
    }
  }, [sel, candDetail, lists, employerList, salaryDetailList, documentAudit, signoffDetails, auditRecord, auditLoadError, salaryRows, bankRows])"""

if target_state_refs not in content:
    print("Error: target_state_refs not found")
    sys.exit(1)

content = content.replace(target_state_refs, rep_state_refs, 1)

# 2. Add buildAuditDraftPayload, performAutosave, scheduleAutosave, flushAutosave right before handleSaveDraft
target_draft_start = "  // --- Audit Draft & Submit Handlers ---\n  async function handleSaveDraft(isSilent = false) {"

rep_draft_start = """  // --- Autosave Engine & Draft Payload Builder ---
  const buildAuditDraftPayload = useCallback((customState = null) => {
    const s = customState || formStateRef.current
    const { candDetail: cDetail, sel: cSel, lists: cLists, employerList: eList, salaryDetailList: sList, signoffDetails: sDetails, auditRecord: aRec } = s
    if (!cSel?.cand || !cDetail) return null

    const payloadDocAudit = prepareDocumentAuditPayload()
    const validEmployers = (eList || [])
      .filter((e) => e.employer_name && e.employer_name.trim())
      .map((e) => ({
        id: e.id,
        employer_name: e.employer_name.trim(),
        months_worked: e.months_worked !== '' && e.months_worked !== null ? parseFloat(e.months_worked) : null,
        appointment_date: e.appointment_date || null,
        designation: e.designation || null,
        place_of_work: e.place_of_work || null,
        monthly_ctc: e.monthly_ctc !== '' && e.monthly_ctc !== null ? parseFloat(e.monthly_ctc) : null,
        minimum_wages: e.minimum_wages !== '' && e.minimum_wages !== null ? parseFloat(e.minimum_wages) : null,
      }))

    const validSalary = (sList || []).map((sal) => ({
      id: sal.id,
      employer_id: sal.employer_id || (eList?.[0]?.id || 'emp_1'),
      month: parseInt(sal.month, 10),
      year: parseInt(sal.year, 10),
      working_days: sal.working_days !== '' && sal.working_days !== null ? parseInt(sal.working_days, 10) : null,
      pay_days: sal.pay_days !== '' && sal.pay_days !== null ? parseInt(sal.pay_days, 10) : null,
      leave_days: sal.leave_days !== '' && sal.leave_days !== null ? parseInt(sal.leave_days, 10) : null,
      credit_date: sal.credit_date || null,
      amount_credited: sal.amount_credited !== '' && sal.amount_credited !== null ? parseFloat(sal.amount_credited) : null,
      gross_salary: sal.gross_salary !== '' && sal.gross_salary !== null ? parseFloat(sal.gross_salary) : null,
      deductions: sal.deductions !== '' && sal.deductions !== null ? parseFloat(sal.deductions) : null,
      net_salary: sal.net_salary !== '' && sal.net_salary !== null ? parseFloat(sal.net_salary) : null,
      bank_name: sal.bank_name || null,
    }))

    return {
      candidate_snapshot: {
        candidate_id: cDetail.candidate_id,
        first_name: cDetail.first_name,
        last_name: cDetail.last_name,
        father_name: cDetail.father_name,
        dob: cDetail.dob,
        mobile: cDetail.mobile,
        state: cSel.state,
        tc_name: cLists?.tc?.find((c) => c.tc_id === cSel.tc)?.name || cSel.tc,
        batch_code: cLists?.batch?.find((b) => b.kb_batch_id === cSel.batch)?.batch_code || cSel.batch,
        sanction_order: cSel.order,
      },
      employer_details: validEmployers,
      salary_details: validSalary,
      document_audit: payloadDocAudit,
      signoff_details: sDetails || createDefaultSignoffs(),
      remarks: aRec?.remarks || null,
    }
  }, [prepareDocumentAuditPayload])

  const performAutosave = useCallback(async (retryCount = 0) => {
    const s = formStateRef.current
    const candId = s.sel?.cand
    if (!candId || !s.candDetail || s.auditRecord?.audit_status === 'SUBMITTED' || s.auditLoadError) {
      return null
    }

    if (inFlightSavePromiseRef.current) {
      try {
        await inFlightSavePromiseRef.current
      } catch {
        // Ignore previous error, we will do a fresh save with latest state
      }
    }

    const payload = buildAuditDraftPayload(formStateRef.current)
    if (!payload) return null

    const seq = ++saveSeqRef.current
    setAutosaveStatus(retryCount > 0 ? 'retrying' : 'saving')
    setAutosaveError('')

    const savePromise = (async () => {
      try {
        const res = await api(`/candidates/${candId}/audit/draft`, null, {
          method: 'POST',
          body: JSON.stringify(payload),
        })

        if (seq === saveSeqRef.current) {
          setAuditRecord(res.audit)
          isDirtyRef.current = false
          setAutosaveStatus('saved')
          setAutosaveLastSavedAt(new Date(res.audit?.updated_at || Date.now()))
          setAutosaveError('')
        }
        return res.audit
      } catch (err) {
        if (seq !== saveSeqRef.current) return null
        console.warn(`Autosave attempt ${retryCount + 1} failed:`, err)
        if (retryCount < 3) {
          setAutosaveStatus('retrying')
          setAutosaveError(`Save failed – retrying (${retryCount + 1}/3)...`)
          const delay = (retryCount + 1) * 1500
          setTimeout(() => {
            if (isDirtyRef.current && seq === saveSeqRef.current) {
              performAutosave(retryCount + 1)
            }
          }, delay)
        } else {
          setAutosaveStatus('error')
          setAutosaveError(err.message || 'Auto-save failed. Check connection.')
        }
        throw err
      } finally {
        if (inFlightSavePromiseRef.current === savePromise) {
          inFlightSavePromiseRef.current = null
        }
      }
    })()

    inFlightSavePromiseRef.current = savePromise
    return savePromise
  }, [buildAuditDraftPayload])

  const scheduleAutosave = useCallback(() => {
    const s = formStateRef.current
    if (!s.sel?.cand || !s.candDetail || s.auditRecord?.audit_status === 'SUBMITTED' || s.auditLoadError) {
      return
    }
    isDirtyRef.current = true
    if (autosaveTimerRef.current) {
      clearTimeout(autosaveTimerRef.current)
    }
    autosaveTimerRef.current = setTimeout(() => {
      performAutosave(0)
    }, 1300) // 1.3s debounce
  }, [performAutosave])

  const flushAutosave = useCallback(async () => {
    if (autosaveTimerRef.current) {
      clearTimeout(autosaveTimerRef.current)
      autosaveTimerRef.current = null
    }
    if (isDirtyRef.current) {
      return await performAutosave(0)
    }
    if (inFlightSavePromiseRef.current) {
      return await inFlightSavePromiseRef.current
    }
    return null
  }, [performAutosave])

  // --- Audit Draft & Submit Handlers ---
  async function handleSaveDraft(isSilent = false) {"""

if target_draft_start not in content:
    print("Error: target_draft_start not found")
    sys.exit(1)

content = content.replace(target_draft_start, rep_draft_start, 1)

# 3. Replace handleSaveDraft body to use flushAutosave()
# Let's inspect handleSaveDraft
target_hsd = """  async function handleSaveDraft(isSilent = false) {
    if (!sel.cand || !candDetail) return
    if (auditLoadError) {
      setError('Cannot save draft while audit record failed to load. Please retry loading first.')
      if (!isSilent) setAuditToast({ message: 'Cannot save draft: please retry loading first.', type: 'error' })
      return
    }
    if (auditRecord?.audit_status === 'SUBMITTED') {
      if (!isSilent) setAuditToast({ message: 'This placement audit is already submitted and locked against editing.', type: 'info' })
      return
    }
    setAuditSavingDraft(true)
    setError('')
    try {
      const payloadDocAudit = prepareDocumentAuditPayload()
      setDocumentAudit(payloadDocAudit)
      const payload = {
        candidate_snapshot: {
          candidate_id: candDetail.candidate_id,
          first_name: candDetail.first_name,
          last_name: candDetail.last_name,
          father_name: candDetail.father_name,
          dob: candDetail.dob,
          mobile: candDetail.mobile,
          state: sel.state,
          tc_name: lists.tc.find((c) => c.tc_id === sel.tc)?.name || sel.tc,
          batch_code: lists.batch.find((b) => b.kb_batch_id === sel.batch)?.batch_code || sel.batch,
          sanction_order: sel.order,
        },
        employer_details: employerList
          .filter((e) => e.employer_name && e.employer_name.trim())
          .map((e) => ({
            id: e.id,
            employer_name: e.employer_name.trim(),
            months_worked: e.months_worked !== '' && e.months_worked !== null ? parseFloat(e.months_worked) : null,
            appointment_date: e.appointment_date || null,
            designation: e.designation || null,
            place_of_work: e.place_of_work || null,
            monthly_ctc: e.monthly_ctc !== '' && e.monthly_ctc !== null ? parseFloat(e.monthly_ctc) : null,
            minimum_wages: e.minimum_wages !== '' && e.minimum_wages !== null ? parseFloat(e.minimum_wages) : null,
          })),
        salary_details: salaryDetailList.map((s) => ({
          id: s.id,
          employer_id: s.employer_id || (employerList[0]?.id || 'emp_1'),
          month: parseInt(s.month, 10),
          year: parseInt(s.year, 10),
          working_days: s.working_days !== '' && s.working_days !== null ? parseInt(s.working_days, 10) : null,
          pay_days: s.pay_days !== '' && s.pay_days !== null ? parseInt(s.pay_days, 10) : null,
          leave_days: s.leave_days !== '' && s.leave_days !== null ? parseInt(s.leave_days, 10) : null,
          credit_date: s.credit_date || null,
          amount_credited: s.amount_credited !== '' && s.amount_credited !== null ? parseFloat(s.amount_credited) : null,
          gross_salary: s.gross_salary !== '' && s.gross_salary !== null ? parseFloat(s.gross_salary) : null,
          deductions: s.deductions !== '' && s.deductions !== null ? parseFloat(s.deductions) : null,
          net_salary: s.net_salary !== '' && s.net_salary !== null ? parseFloat(s.net_salary) : null,
          bank_name: s.bank_name || null,
        })),
        document_audit: payloadDocAudit,
        signoff_details: signoffDetails,
        remarks: auditRecord?.remarks || null,
      }

      const res = await api(`/candidates/${sel.cand}/audit/draft`, null, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      setAuditRecord(res.audit)
      if (!isSilent) {
        setAuditToast({ message: '✓ Draft placement audit saved successfully.', type: 'success' })
      }
      return res.audit
    } catch (err) {
      setError(err.message || 'Failed to save audit draft.')
      if (!isSilent) {
        setAuditToast({ message: err.message || 'Failed to save draft.', type: 'error' })
      }
      throw err
    } finally {
      setAuditSavingDraft(false)
    }
  }"""

rep_hsd = """  async function handleSaveDraft(isSilent = false) {
    if (!sel.cand || !candDetail) return
    if (auditLoadError) {
      setError('Cannot save draft while audit record failed to load. Please retry loading first.')
      if (!isSilent) setAuditToast({ message: 'Cannot save draft: please retry loading first.', type: 'error' })
      return
    }
    if (auditRecord?.audit_status === 'SUBMITTED') {
      if (!isSilent) setAuditToast({ message: 'This placement audit is already submitted and locked against editing.', type: 'info' })
      return
    }
    setAuditSavingDraft(true)
    setError('')
    try {
      const savedAudit = await flushAutosave()
      if (!isSilent) {
        setAuditToast({ message: '✓ Draft placement audit saved successfully.', type: 'success' })
      }
      return savedAudit
    } catch (err) {
      setError(err.message || 'Failed to save audit draft.')
      if (!isSilent) {
        setAuditToast({ message: err.message || 'Failed to save draft.', type: 'error' })
      }
      throw err
    } finally {
      setAuditSavingDraft(false)
    }
  }"""

if target_hsd not in content:
    print("Error: target_hsd not found")
    sys.exit(1)

content = content.replace(target_hsd, rep_hsd, 1)

print("Step 3 applied successfully")
with open(path, "w", encoding="utf-8") as f:
    f.write(content)

