import React, { useState, useEffect, useRef } from 'react'
import { api } from '../lib/api.js'
import './L2DocumentUploadModal.css'

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
]

export default function L2DocumentUploadModal({
  isOpen,
  onClose,
  candidateId,
  candidateName = '',
  defaultDocType = 'APPOINTMENT_LETTER',
  replaceDoc = null,
  employersList = [],
  onSuccess,
}) {
  const [docType, setDocType] = useState(defaultDocType)
  const [employerId, setEmployerId] = useState('')
  const [reportingMonth, setReportingMonth] = useState(new Date().getMonth() + 1)
  const [reportingYear, setReportingYear] = useState(new Date().getFullYear())
  const [isConsolidated, setIsConsolidated] = useState(false)
  const [covStartMonth, setCovStartMonth] = useState(1)
  const [covStartYear, setCovStartYear] = useState(new Date().getFullYear())
  const [covEndMonth, setCovEndMonth] = useState(3)
  const [covEndYear, setCovEndYear] = useState(new Date().getFullYear())
  const [documentTitle, setDocumentTitle] = useState('')
  const [remarks, setRemarks] = useState('')
  const [file, setFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState('')
  const [isDragOver, setIsDragOver] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')

  const fileInputRef = useRef(null)

  useEffect(() => {
    if (isOpen) {
      if (replaceDoc) {
        setDocType(replaceDoc.document_type || defaultDocType)
        setEmployerId(replaceDoc.employer_id || (employersList[0]?.id || ''))
        setReportingMonth(replaceDoc.reporting_month || (new Date().getMonth() + 1))
        setReportingYear(replaceDoc.reporting_year || new Date().getFullYear())
        setIsConsolidated(Boolean(replaceDoc.is_consolidated))
        setCovStartMonth(replaceDoc.coverage_start_month || 1)
        setCovStartYear(replaceDoc.coverage_start_year || new Date().getFullYear())
        setCovEndMonth(replaceDoc.coverage_end_month || 3)
        setCovEndYear(replaceDoc.coverage_end_year || new Date().getFullYear())
        setDocumentTitle(replaceDoc.document_title || '')
        setRemarks(replaceDoc.remarks || '')
      } else {
        setDocType(defaultDocType)
        setEmployerId(employersList[0]?.id || '')
        setReportingMonth(new Date().getMonth() + 1)
        setReportingYear(new Date().getFullYear())
        setIsConsolidated(false)
        setCovStartMonth(1)
        setCovStartYear(new Date().getFullYear())
        setCovEndMonth(3)
        setCovEndYear(new Date().getFullYear())
        setDocumentTitle('')
        setRemarks('')
      }
      setFile(null)
      setPreviewUrl('')
      setErrorMsg('')
      setSubmitting(false)
    }
  }, [isOpen, defaultDocType, replaceDoc, employersList])

  // Clean up object URLs
  useEffect(() => {
    return () => {
      if (previewUrl && previewUrl.startsWith('blob:')) {
        URL.revokeObjectURL(previewUrl)
      }
    }
  }, [previewUrl])

  if (!isOpen) return null

  const handleFileChange = (selectedFile) => {
    setErrorMsg('')
    if (!selectedFile) {
      setFile(null)
      setPreviewUrl('')
      return
    }

    const ext = '.' + selectedFile.name.split('.').pop().toLowerCase()
    if (!['.pdf', '.jpg', '.jpeg', '.png'].includes(ext)) {
      setErrorMsg(`Unsupported file type (${ext}). Allowed: PDF, JPG, PNG.`)
      return
    }

    if (selectedFile.size > 15 * 1024 * 1024) {
      setErrorMsg(`File size (${(selectedFile.size / (1024 * 1024)).toFixed(1)} MB) exceeds 15 MB limit.`)
      return
    }

    setFile(selectedFile)
    if (selectedFile.type.startsWith('image/')) {
      const url = URL.createObjectURL(selectedFile)
      setPreviewUrl(url)
    } else {
      setPreviewUrl('')
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setIsDragOver(false)
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileChange(e.dataTransfer.files[0])
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setErrorMsg('')

    if (!file) {
      setErrorMsg('Please select a document file to upload.')
      return
    }

    if (docType === 'OTHER_DOCUMENT' && !documentTitle.trim()) {
      setErrorMsg('Document title is required for Supporting Documents.')
      return
    }

    if (docType === 'BANK_STATEMENT' && isConsolidated) {
      const startVal = covStartYear * 12 + covStartMonth
      const endVal = covEndYear * 12 + covEndMonth
      if (endVal < startVal) {
        setErrorMsg('Consolidated coverage end period must be after the start period.')
        return
      }
    }

    try {
      setSubmitting(true)
      const formData = new FormData()
      formData.append('file', file)
      formData.append('document_type', docType)

      if (replaceDoc?.id) {
        formData.append('replace_id', replaceDoc.id)
      }

      if (employerId) {
        formData.append('employer_id', employerId)
      }

      if (docType === 'SALARY_SLIP') {
        formData.append('reporting_month', String(reportingMonth))
        formData.append('reporting_year', String(reportingYear))
      } else if (docType === 'BANK_STATEMENT') {
        if (isConsolidated) {
          formData.append('is_consolidated', 'true')
          formData.append('coverage_start_month', String(covStartMonth))
          formData.append('coverage_start_year', String(covStartYear))
          formData.append('coverage_end_month', String(covEndMonth))
          formData.append('coverage_end_year', String(covEndYear))

          // Generate covered_months json list
          const covMonths = []
          let curY = covStartYear
          let curM = covStartMonth
          while (curY < covEndYear || (curY === covEndYear && curM <= covEndMonth)) {
            covMonths.push({ month: curM, year: curY })
            curM++
            if (curM > 12) {
              curM = 1
              curY++
            }
          }
          formData.append('covered_months', JSON.stringify(covMonths))
        } else {
          formData.append('is_consolidated', 'false')
          formData.append('reporting_month', String(reportingMonth))
          formData.append('reporting_year', String(reportingYear))
        }
      } else if (docType === 'OTHER_DOCUMENT') {
        formData.append('document_title', documentTitle.trim())
      }

      if (remarks.trim()) {
        formData.append('remarks', remarks.trim())
      }

      const res = await api(`/candidates/${candidateId}/documents`, null, {
        method: 'POST',
        body: formData,
      })

      if (onSuccess) {
        onSuccess(res)
      }
      onClose()
    } catch (err) {
      setErrorMsg(err.message || 'Document upload failed. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="l2-upload-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="l2-upload-title">
      <div className="l2-upload-modal-card">
        {/* Header */}
        <div className="l2-upload-modal-header">
          <div className="l2-upload-modal-title-wrap">
            <span className="l2-upload-modal-icon">📤</span>
            <div>
              <h3 id="l2-upload-title" className="l2-upload-modal-title">
                {replaceDoc ? `Replace Document` : `Upload Missing Document (Center Head)`}
              </h3>
              <p className="l2-upload-modal-sub">
                Candidate: <strong>{candidateName}</strong> (ID: {candidateId})
              </p>
            </div>
          </div>
          <button
            type="button"
            className="l2-upload-modal-close"
            onClick={onClose}
            disabled={submitting}
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="l2-upload-modal-body">
          {errorMsg && (
            <div className="l2-upload-alert error">
              <span>⚠️</span>
              <div>{errorMsg}</div>
            </div>
          )}

          {/* Info banner explaining separation of duties and attribution */}
          <div className="l2-upload-alert info">
            <span>ℹ️</span>
            <div>
              <strong>Separation of Duties Notice:</strong> Documents uploaded by Center Head are recorded with role attribution and timestamps. They are <em>not</em> automatically verified and remain subject to statutory COPS audit verification.
            </div>
          </div>

          {/* Document Type Selection */}
          <div className="l2-upload-field">
            <label htmlFor="l2-doc-type-select" className="l2-upload-label">
              Document Category <span className="req">*</span>
            </label>
            <select
              id="l2-doc-type-select"
              className="l2-upload-select"
              value={docType}
              onChange={(e) => setDocType(e.target.value)}
              disabled={submitting || Boolean(replaceDoc)}
            >
              <option value="APPOINTMENT_LETTER">1. Appointment / Offer Letter</option>
              <option value="SALARY_SLIP">2. Monthly Salary Slip</option>
              <option value="BANK_STATEMENT">3. Bank Statement / Passbook</option>
              <option value="OTHER_DOCUMENT">4. Supporting / Other Document</option>
            </select>
          </div>

          {/* Employer Selection (if multiple employers or available) */}
          {employersList.length > 0 && docType !== 'OTHER_DOCUMENT' && (
            <div className="l2-upload-field">
              <label htmlFor="l2-emp-select" className="l2-upload-label">
                Associated Employer <span className="req">*</span>
              </label>
              <select
                id="l2-emp-select"
                className="l2-upload-select"
                value={employerId}
                onChange={(e) => setEmployerId(e.target.value)}
                disabled={submitting}
              >
                {employersList.map((emp, idx) => (
                  <option key={emp.id || idx} value={emp.id || `emp_${idx + 1}`}>
                    {emp.employer_name || `Employer #${idx + 1}`}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Conditional fields based on docType */}
          {docType === 'SALARY_SLIP' && (
            <div className="l2-upload-grid-2">
              <div className="l2-upload-field">
                <label htmlFor="l2-salary-month" className="l2-upload-label">
                  Reporting Month <span className="req">*</span>
                </label>
                <select
                  id="l2-salary-month"
                  className="l2-upload-select"
                  value={reportingMonth}
                  onChange={(e) => setReportingMonth(Number(e.target.value))}
                  disabled={submitting}
                >
                  {MONTH_NAMES.map((m, idx) => (
                    <option key={m} value={idx + 1}>
                      {idx + 1} — {m}
                    </option>
                  ))}
                </select>
              </div>
              <div className="l2-upload-field">
                <label htmlFor="l2-salary-year" className="l2-upload-label">
                  Reporting Year <span className="req">*</span>
                </label>
                <input
                  id="l2-salary-year"
                  type="number"
                  className="l2-upload-input"
                  value={reportingYear}
                  min={2015}
                  max={2035}
                  onChange={(e) => setReportingYear(Number(e.target.value))}
                  disabled={submitting}
                />
              </div>
            </div>
          )}

          {docType === 'BANK_STATEMENT' && (
            <>
              <div className="l2-upload-field">
                <label className="l2-upload-label">Statement Coverage Format</label>
                <div style={{ display: 'flex', gap: '16px', marginTop: '2px' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', cursor: 'pointer' }}>
                    <input
                      type="radio"
                      name="bank_type"
                      checked={!isConsolidated}
                      onChange={() => setIsConsolidated(false)}
                      disabled={submitting}
                    />
                    Single Month Statement
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', cursor: 'pointer' }}>
                    <input
                      type="radio"
                      name="bank_type"
                      checked={isConsolidated}
                      onChange={() => setIsConsolidated(true)}
                      disabled={submitting}
                    />
                    Consolidated Multi-Month Statement
                  </label>
                </div>
              </div>

              {!isConsolidated ? (
                <div className="l2-upload-grid-2">
                  <div className="l2-upload-field">
                    <label htmlFor="l2-bank-month" className="l2-upload-label">
                      Reporting Month <span className="req">*</span>
                    </label>
                    <select
                      id="l2-bank-month"
                      className="l2-upload-select"
                      value={reportingMonth}
                      onChange={(e) => setReportingMonth(Number(e.target.value))}
                      disabled={submitting}
                    >
                      {MONTH_NAMES.map((m, idx) => (
                        <option key={m} value={idx + 1}>
                          {idx + 1} — {m}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="l2-upload-field">
                    <label htmlFor="l2-bank-year" className="l2-upload-label">
                      Reporting Year <span className="req">*</span>
                    </label>
                    <input
                      id="l2-bank-year"
                      type="number"
                      className="l2-upload-input"
                      value={reportingYear}
                      min={2015}
                      max={2035}
                      onChange={(e) => setReportingYear(Number(e.target.value))}
                      disabled={submitting}
                    />
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div className="l2-upload-grid-2">
                    <div className="l2-upload-field">
                      <label htmlFor="l2-cov-start-month" className="l2-upload-label">Coverage Start Month</label>
                      <select
                        id="l2-cov-start-month"
                        className="l2-upload-select"
                        value={covStartMonth}
                        onChange={(e) => setCovStartMonth(Number(e.target.value))}
                        disabled={submitting}
                      >
                        {MONTH_NAMES.map((m, idx) => (
                          <option key={m} value={idx + 1}>{m}</option>
                        ))}
                      </select>
                    </div>
                    <div className="l2-upload-field">
                      <label htmlFor="l2-cov-start-year" className="l2-upload-label">Coverage Start Year</label>
                      <input
                        id="l2-cov-start-year"
                        type="number"
                        className="l2-upload-input"
                        value={covStartYear}
                        min={2015}
                        max={2035}
                        onChange={(e) => setCovStartYear(Number(e.target.value))}
                        disabled={submitting}
                      />
                    </div>
                  </div>
                  <div className="l2-upload-grid-2">
                    <div className="l2-upload-field">
                      <label htmlFor="l2-cov-end-month" className="l2-upload-label">Coverage End Month</label>
                      <select
                        id="l2-cov-end-month"
                        className="l2-upload-select"
                        value={covEndMonth}
                        onChange={(e) => setCovEndMonth(Number(e.target.value))}
                        disabled={submitting}
                      >
                        {MONTH_NAMES.map((m, idx) => (
                          <option key={m} value={idx + 1}>{m}</option>
                        ))}
                      </select>
                    </div>
                    <div className="l2-upload-field">
                      <label htmlFor="l2-cov-end-year" className="l2-upload-label">Coverage End Year</label>
                      <input
                        id="l2-cov-end-year"
                        type="number"
                        className="l2-upload-input"
                        value={covEndYear}
                        min={2015}
                        max={2035}
                        onChange={(e) => setCovEndYear(Number(e.target.value))}
                        disabled={submitting}
                      />
                    </div>
                  </div>
                </div>
              )}
            </>
          )}

          {docType === 'OTHER_DOCUMENT' && (
            <div className="l2-upload-field">
              <label htmlFor="l2-doc-title-input" className="l2-upload-label">
                Document Title / Description <span className="req">*</span>
              </label>
              <input
                id="l2-doc-title-input"
                type="text"
                className="l2-upload-input"
                placeholder="e.g. Candidate Aadhaar Card, Joining Report, PF Slip"
                value={documentTitle}
                onChange={(e) => setDocumentTitle(e.target.value)}
                required
                disabled={submitting}
              />
            </div>
          )}

          {/* File Picker / Dropzone */}
          <div className="l2-upload-field">
            <label className="l2-upload-label">
              Document File <span className="req">*</span> <span className="opt">(PDF, JPG, PNG, max 15MB)</span>
            </label>
            <div
              className={`l2-upload-dropzone ${isDragOver ? 'dragover' : ''} ${file ? 'has-file' : ''}`}
              onDragOver={(e) => {
                e.preventDefault()
                setIsDragOver(true)
              }}
              onDragLeave={() => setIsDragOver(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                type="file"
                ref={fileInputRef}
                style={{ display: 'none' }}
                accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                onChange={(e) => handleFileChange(e.target.files?.[0])}
              />
              {file ? (
                <div className="dropzone-file-info">
                  <span>📄</span>
                  <span>{file.name} ({(file.size / 1024).toFixed(1)} KB)</span>
                  <button
                    type="button"
                    className="dropzone-remove"
                    onClick={(e) => {
                      e.stopPropagation()
                      setFile(null)
                      setPreviewUrl('')
                    }}
                  >
                    Remove
                  </button>
                </div>
              ) : (
                <>
                  <span className="dropzone-icon">📎</span>
                  <span className="dropzone-title">Click to select or drag and drop file here</span>
                  <span className="dropzone-sub">Supported formats: PDF, JPG, PNG up to 15MB</span>
                </>
              )}
            </div>

            {/* Thumbnail Preview for Images */}
            {previewUrl && (
              <div style={{ marginTop: '6px', textAlign: 'center' }}>
                <img
                  src={previewUrl}
                  alt="Preview"
                  style={{ maxHeight: '120px', borderRadius: '4px', border: '1px solid #cbd5e1' }}
                />
              </div>
            )}
          </div>

          {/* Upload Remarks */}
          <div className="l2-upload-field">
            <label htmlFor="l2-remarks-input" className="l2-upload-label">
              Upload Remarks <span className="opt">(Optional note for audit record)</span>
            </label>
            <textarea
              id="l2-remarks-input"
              className="l2-upload-textarea"
              rows={2}
              placeholder="e.g. Uploaded on behalf of coordinator after receiving from candidate / employer"
              value={remarks}
              onChange={(e) => setRemarks(e.target.value)}
              disabled={submitting}
            />
          </div>

          {/* Footer */}
          <div className="l2-upload-modal-footer">
            <button
              type="button"
              className="l2-upload-btn-cancel"
              onClick={onClose}
              disabled={submitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="l2-upload-btn-submit"
              disabled={submitting || !file}
            >
              {submitting
                ? 'Uploading to Drive…'
                : replaceDoc
                ? '🔄 Upload Replacement'
                : '📤 Upload Document'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

