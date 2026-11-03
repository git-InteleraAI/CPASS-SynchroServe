import sys

path = "frontend/src/pages/L1Home.jsx"
with open(path, "rb") as f:
    raw = f.read()

content = raw.decode("utf-8").replace("\r\n", "\n")

# 1. Update resetAuditForm
target_reset = """  function resetAuditForm() {
    setAuditRecord(null)
    setAuditLoadError('')
    setEmployerList([createDefaultEmployer(null)])
    setSalaryDetailList(createDefaultSalaryList(currentYear))
    setDocumentAudit(createDefaultDocAudit())
    setSignoffDetails(createDefaultSignoffs())
    setStatementModalOpen(false)
    setStatementData(null)
  }"""

rep_reset = """  function resetAuditForm() {
    if (autosaveTimerRef.current) {
      clearTimeout(autosaveTimerRef.current)
      autosaveTimerRef.current = null
    }
    isDirtyRef.current = false
    setAutosaveStatus('idle')
    setAutosaveError('')
    setAutosaveLastSavedAt(null)
    setAuditRecord(null)
    setAuditLoadError('')
    setEmployerList([createDefaultEmployer(null)])
    setSalaryDetailList(createDefaultSalaryList(currentYear))
    setDocumentAudit(createDefaultDocAudit())
    setSignoffDetails(createDefaultSignoffs())
    setStatementModalOpen(false)
    setStatementData(null)
  }"""

if target_reset in content:
    content = content.replace(target_reset, rep_reset, 1)

# 2. Update loadAudit
target_load = """          if (a.signoff_details) {
            setSignoffDetails({
              centre_head: { ...createDefaultSignoffs().centre_head, ...(a.signoff_details.centre_head || {}) },
              cops_team: { ...createDefaultSignoffs().cops_team, ...(a.signoff_details.cops_team || {}) },
              business_leader: { ...createDefaultSignoffs().business_leader, ...(a.signoff_details.business_leader || {}) },
            })
          }
        } else {
          setAuditRecord(null)
          setEmployerList([createDefaultEmployer(detail)])
          setSalaryDetailList(createDefaultSalaryList(currentYear))
          setSalaryRows(createDefaultRows(0))
          setBankRows(createDefaultRows(0))
          setDocumentAudit(createDefaultDocAudit())
          setSignoffDetails(createDefaultSignoffs())
        }
      })
      .catch((err) => {
        if (selectedCandidateIdRef.current !== candidateId) return
        console.warn('Could not load candidate audit:', err)
        setAuditLoadError(err.message || 'Could not load placement audit record.')
        setAuditRecord(null)
        setEmployerList([createDefaultEmployer(detail)])
        setSalaryDetailList(createDefaultSalaryList(currentYear))
        setSalaryRows(createDefaultRows(0))
        setBankRows(createDefaultRows(0))
        setDocumentAudit(createDefaultDocAudit())
        setSignoffDetails(createDefaultSignoffs())
      })"""

rep_load = """          if (a.signoff_details) {
            setSignoffDetails({
              centre_head: { ...createDefaultSignoffs().centre_head, ...(a.signoff_details.centre_head || {}) },
              cops_team: { ...createDefaultSignoffs().cops_team, ...(a.signoff_details.cops_team || {}) },
              business_leader: { ...createDefaultSignoffs().business_leader, ...(a.signoff_details.business_leader || {}) },
            })
          }
          setAutosaveStatus('saved')
          setAutosaveLastSavedAt(new Date(a.updated_at || Date.now()))
        } else {
          setAuditRecord(null)
          const userHasData = isDirtyRef.current || hasEnteredAuditData(employerList, salaryDetailList)
          if (!userHasData) {
            setEmployerList([createDefaultEmployer(detail)])
            setSalaryDetailList(createDefaultSalaryList(currentYear))
            setSalaryRows(createDefaultRows(0))
            setBankRows(createDefaultRows(0))
            setDocumentAudit(createDefaultDocAudit())
            setSignoffDetails(createDefaultSignoffs())
            setAutosaveStatus('idle')
          } else {
            scheduleAutosave()
          }
        }
      })
      .catch((err) => {
        if (selectedCandidateIdRef.current !== candidateId) return
        console.warn('Could not load candidate audit:', err)
        setAuditLoadError(err.message || 'Could not load placement audit record.')
        setAuditRecord(null)
        const userHasData = isDirtyRef.current || hasEnteredAuditData(employerList, salaryDetailList)
        if (!userHasData) {
          setEmployerList([createDefaultEmployer(detail)])
          setSalaryDetailList(createDefaultSalaryList(currentYear))
          setSalaryRows(createDefaultRows(0))
          setBankRows(createDefaultRows(0))
          setDocumentAudit(createDefaultDocAudit())
          setSignoffDetails(createDefaultSignoffs())
        }
      })"""

if target_load in content:
    content = content.replace(target_load, rep_load, 1)

# 3. Add scheduleAutosave() to employer and salary handlers
target_emp_handlers = """  function handleAddEmployerRow() {
    if (auditRecord?.audit_status === 'SUBMITTED') return
    const newRow = {
      id: `emp_${Date.now()}_${Math.random().toString(36).substr(2, 4)}`,
      employer_name: '',
      months_worked: '',
      appointment_date: '',
      designation: '',
      place_of_work: '',
      monthly_ctc: '',
      minimum_wages: '',
    }
    setEmployerList((prev) => [...prev, newRow])
  }

  function handleRemoveEmployerRow(id) {
    if (auditRecord?.audit_status === 'SUBMITTED') return
    if (employerList.length <= 1) return
    setEmployerList((prev) => prev.filter((e) => e.id !== id))
  }

  function handleUpdateEmployerField(id, field, value) {
    if (auditRecord?.audit_status === 'SUBMITTED') return
    setEmployerList((prev) =>
      prev.map((e) => (e.id === id ? { ...e, [field]: value } : e))
    )
  }"""

rep_emp_handlers = """  function handleAddEmployerRow() {
    if (auditRecord?.audit_status === 'SUBMITTED') return
    const newRow = {
      id: `emp_${Date.now()}_${Math.random().toString(36).substr(2, 4)}`,
      employer_name: '',
      months_worked: '',
      appointment_date: '',
      designation: '',
      place_of_work: '',
      monthly_ctc: '',
      minimum_wages: '',
    }
    setEmployerList((prev) => [...prev, newRow])
    scheduleAutosave()
  }

  function handleRemoveEmployerRow(id) {
    if (auditRecord?.audit_status === 'SUBMITTED') return
    if (employerList.length <= 1) return
    setEmployerList((prev) => prev.filter((e) => e.id !== id))
    scheduleAutosave()
  }

  function handleUpdateEmployerField(id, field, value) {
    if (auditRecord?.audit_status === 'SUBMITTED') return
    setEmployerList((prev) =>
      prev.map((e) => (e.id === id ? { ...e, [field]: value } : e))
    )
    scheduleAutosave()
  }"""

if target_emp_handlers not in content:
    print("Error: target_emp_handlers not found")
    sys.exit(1)
content = content.replace(target_emp_handlers, rep_emp_handlers, 1)

# 4. In handleAddSalaryRow: add scheduleAutosave()
target_add_sal = """    setBankRows((prev) => [
      ...prev,
      {
        id: `bank_${slotId}`,
        month: nextMonth,
        year: nextYear,
        employer_id: defaultEmpId,
        file: null,
        fileName: '',
        fileSize: 0,
        replaceId: null,
        error: '',
        notAvailable: false,
      },
    ])
  }"""

rep_add_sal = """    setBankRows((prev) => [
      ...prev,
      {
        id: `bank_${slotId}`,
        month: nextMonth,
        year: nextYear,
        employer_id: defaultEmpId,
        file: null,
        fileName: '',
        fileSize: 0,
        replaceId: null,
        error: '',
        notAvailable: false,
      },
    ])
    scheduleAutosave()
  }"""

if target_add_sal not in content:
    print("Error: target_add_sal not found")
    sys.exit(1)
content = content.replace(target_add_sal, rep_add_sal, 1)

# 5. In handleRemoveSalaryRow: add scheduleAutosave()
target_rem_sal = """    setSalaryDetailList((prev) => prev.filter((s) => s.id !== id))
    setSalaryRows((prev) => prev.filter((_, idx) => idx !== removeIdx))
    setBankRows((prev) => prev.filter((_, idx) => idx !== removeIdx))
  }"""

rep_rem_sal = """    setSalaryDetailList((prev) => prev.filter((s) => s.id !== id))
    setSalaryRows((prev) => prev.filter((_, idx) => idx !== removeIdx))
    setBankRows((prev) => prev.filter((_, idx) => idx !== removeIdx))
    scheduleAutosave()
  }"""

if target_rem_sal not in content:
    print("Error: target_rem_sal not found")
    sys.exit(1)
content = content.replace(target_rem_sal, rep_rem_sal, 1)

# 6. In handleUpdateSalaryField: add scheduleAutosave()
target_upd_sal = """      if (field === 'employer_id' && sIndex !== -1) {
        setSalaryRows((prevRows) =>
          prevRows.map((r, rIdx) => (rIdx === sIndex ? { ...r, employer_id: value } : r))
        )
        setBankRows((prevRows) =>
          prevRows.map((r, rIdx) => (rIdx === sIndex ? { ...r, employer_id: value } : r))
        )
      }

      return updatedList
    })
  }"""

rep_upd_sal = """      if (field === 'employer_id' && sIndex !== -1) {
        setSalaryRows((prevRows) =>
          prevRows.map((r, rIdx) => (rIdx === sIndex ? { ...r, employer_id: value } : r))
        )
        setBankRows((prevRows) =>
          prevRows.map((r, rIdx) => (rIdx === sIndex ? { ...r, employer_id: value } : r))
        )
      }

      return updatedList
    })
    scheduleAutosave()
  }"""

if target_upd_sal not in content:
    print("Error: target_upd_sal not found")
    sys.exit(1)
content = content.replace(target_upd_sal, rep_upd_sal, 1)

# 7. In handleCopyPreviousMonth: add scheduleAutosave()
target_copy_sal = """    setAuditToast({
      message: `✓ Reusable salary details copied from ${prevMonthName} ${prevY} to ${targetMonthName} ${nextYear}.`,
      type: 'success',
    })
  }"""

rep_copy_sal = """    setAuditToast({
      message: `✓ Reusable salary details copied from ${prevMonthName} ${prevY} to ${targetMonthName} ${nextYear}.`,
      type: 'success',
    })
    scheduleAutosave()
  }"""

if target_copy_sal not in content:
    print("Error: target_copy_sal not found")
    sys.exit(1)
content = content.replace(target_copy_sal, rep_copy_sal, 1)

# 8. In handleUpdateDocAudit: add scheduleAutosave()
target_upd_doc = """  function handleUpdateDocAudit(docKey, field, value) {
    if (auditRecord?.audit_status === 'SUBMITTED') return
    setDocumentAudit((prev) => {
      const prevDoc = prev?.[docKey] && typeof prev[docKey] === 'object' ? prev[docKey] : {}
      return {
        ...prev,
        [docKey]: {
          available: prevDoc.available || 'Pending',
          compliance: prevDoc.compliance || 'Under Verification',
          remarks: prevDoc.remarks || '',
          title: prevDoc.title || '',
          ...prevDoc,
          [field]: value,
          ...(field === 'available' ? { explicitlySet: true } : {}),
        },
      }
    })
  }"""

rep_upd_doc = """  function handleUpdateDocAudit(docKey, field, value) {
    if (auditRecord?.audit_status === 'SUBMITTED') return
    setDocumentAudit((prev) => {
      const prevDoc = prev?.[docKey] && typeof prev[docKey] === 'object' ? prev[docKey] : {}
      return {
        ...prev,
        [docKey]: {
          available: prevDoc.available || 'Pending',
          compliance: prevDoc.compliance || 'Under Verification',
          remarks: prevDoc.remarks || '',
          title: prevDoc.title || '',
          ...prevDoc,
          [field]: value,
          ...(field === 'available' ? { explicitlySet: true } : {}),
        },
      }
    })
    scheduleAutosave()
  }"""

if target_upd_doc not in content:
    print("Error: target_upd_doc not found")
    sys.exit(1)
content = content.replace(target_upd_doc, rep_upd_doc, 1)

# 9. In handleFinalSubmit: flushAutosave before upload and update res.audit
target_final_submit = """  async function handleFinalSubmit() {
    setSubmitting(true)
    setError('')

    try {
      const formData = new FormData()"""

rep_final_submit = """  async function handleFinalSubmit() {
    setSubmitting(true)
    setError('')

    try {
      // Flush any pending autosave first so full employer and salary state are saved before upload
      await flushAutosave()

      const formData = new FormData()"""

if target_final_submit not in content:
    print("Error: target_final_submit not found")
    sys.exit(1)
content = content.replace(target_final_submit, rep_final_submit, 1)

target_submit_res = """      const res = await api(`/candidates/${sel.cand}/documents/submit`, null, {
        method: 'POST',
        body: formData,
      })

      setShowReviewModal(false)
      clearStagedFiles()
      await refreshDocuments(sel.cand)
      if (candDetail) {
        await loadAudit(sel.cand, candDetail)
      }"""

rep_submit_res = """      const res = await api(`/candidates/${sel.cand}/documents/submit`, null, {
        method: 'POST',
        body: formData,
      })

      setShowReviewModal(false)
      clearStagedFiles()
      if (res?.audit) {
        setAuditRecord(res.audit)
        if (res.audit.document_audit) {
          setDocumentAudit(normalizeDocAudit(res.audit.document_audit))
        }
      }
      await refreshDocuments(sel.cand)
      if (candDetail) {
        await loadAudit(sel.cand, candDetail)
      }"""

if target_submit_res not in content:
    print("Error: target_submit_res not found")
    sys.exit(1)
content = content.replace(target_submit_res, rep_submit_res, 1)

# 10. In handleOpenStatementModal: flushAutosave before statement
target_stmt_modal = """  async function handleOpenStatementModal() {
    if (!sel.cand) return
    setLoadingStatement(true)
    try {
      const res = await api(`/candidates/${sel.cand}/audit/statement`)"""

rep_stmt_modal = """  async function handleOpenStatementModal() {
    if (!sel.cand) return
    setLoadingStatement(true)
    try {
      if (isDirtyRef.current) {
        await flushAutosave()
      }
      const res = await api(`/candidates/${sel.cand}/audit/statement`)"""

if target_stmt_modal not in content:
    print("Error: target_stmt_modal not found")
    sys.exit(1)
content = content.replace(target_stmt_modal, rep_stmt_modal, 1)

# 11. Add <AutosaveIndicator /> to top audit actions bar and bottom dock
target_top_btn_group = """              <div className="l1-audit-btn-group">
                {auditRecord && ("""

rep_top_btn_group = """              <div className="l1-audit-btn-group">
                <AutosaveIndicator
                  status={autosaveStatus}
                  lastSavedAt={autosaveLastSavedAt || (auditRecord?.updated_at ? new Date(auditRecord.updated_at) : null)}
                  error={autosaveError}
                  onRetry={() => performAutosave(0)}
                />
                {auditRecord && ("""

if target_top_btn_group not in content:
    print("Error: target_top_btn_group not found")
    sys.exit(1)
content = content.replace(target_top_btn_group, rep_top_btn_group, 1)

target_dock_actions = """          <div className="l1-dock-actions" style={{ display: 'flex', gap: '10px' }}>
            {auditRecord && ("""

rep_dock_actions = """          <div className="l1-dock-actions" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <AutosaveIndicator
              status={autosaveStatus}
              lastSavedAt={autosaveLastSavedAt || (auditRecord?.updated_at ? new Date(auditRecord.updated_at) : null)}
              error={autosaveError}
              onRetry={() => performAutosave(0)}
            />
            {auditRecord && ("""

if target_dock_actions not in content:
    print("Error: target_dock_actions not found")
    sys.exit(1)
content = content.replace(target_dock_actions, rep_dock_actions, 1)

print("All handlers and UI patches applied successfully!")
with open(path, "w", encoding="utf-8") as f:
    f.write(content)
