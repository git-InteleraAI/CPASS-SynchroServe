with open("frontend/src/pages/L1Home.jsx", "r", encoding="utf-8") as f:
    text = f.read()

target_effect = """  // Keep formStateRef current for debounce execution without stale closure
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

assert target_effect in text, "target_effect not found"
text = text.replace(target_effect, "")

after_target = """  const [salaryRows, setSalaryRows] = useState(() => createDefaultRows(0))
  const [bankRows, setBankRows] = useState(() => createDefaultRows(0))"""

rep_after = """  const [salaryRows, setSalaryRows] = useState(() => createDefaultRows(0))
  const [bankRows, setBankRows] = useState(() => createDefaultRows(0))

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

assert after_target in text, "after_target not found"
text = text.replace(after_target, rep_after, 1)

with open("frontend/src/pages/L1Home.jsx", "w", encoding="utf-8") as f:
    f.write(text)

print("Moved formStateRef useEffect below salaryRows and bankRows!")

