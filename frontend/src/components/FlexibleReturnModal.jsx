import React, { useState, useEffect } from 'react'
import './FlexibleReturnModal.css'

const REJECTION_REASONS = [
  'Document missing',
  'Details mismatch',
  'Unclear scan',
  'Wrong document uploaded',
  'Signature missing',
  'Other',
]

// Circular Destination options for L3, L4, L5
const L3_CIRCULAR_DESTINATIONS = [
  { key: 'L1', circleText: 'L1', label: 'Placement Coordinator' },
  { key: 'L2', circleText: 'L2', label: 'Center Head' },
]

const L4_CIRCULAR_DESTINATIONS = [
  { key: 'L1', circleText: 'L1', label: 'Placement Coordinator' },
  { key: 'L2', circleText: 'L2', label: 'Center Head' },
  { key: 'L3', circleText: 'L3', label: 'COPS' },
]

const L5_CIRCULAR_DESTINATIONS = [
  { key: 'L1', circleText: 'L1', label: 'Placement Coordinator' },
  { key: 'L2', circleText: 'L2', label: 'Center Head' },
  { key: 'L3', circleText: 'L3', label: 'COPS' },
  { key: 'L4', circleText: 'L4', label: 'Business Leader' },
]

const getInitials = (name) => {
  if (!name || typeof name !== 'string' || !name.trim()) return 'CD'
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

export default function FlexibleReturnModal({
  isOpen,
  onClose,
  onSubmit,
  level = 'L2',
  currentRole = 'L2_MANAGER',
  candidateName = '',
  candidateId = '',
}) {
  // Normalize level
  const normLevel = (level || currentRole || 'L2').toUpperCase()
  const isL5 = normLevel.includes('L5') || normLevel.includes('CEO')
  const isL4 = normLevel.includes('L4') || normLevel.includes('BL') || normLevel.includes('LEADER')
  const isL3 = normLevel.includes('L3') || normLevel.includes('COPS')
  const isL2 = normLevel.includes('L2') || normLevel.includes('CH') || normLevel.includes('MANAGER')

  // Destinations based on reviewer role
  const circularDestinations = isL5
    ? L5_CIRCULAR_DESTINATIONS
    : isL4
    ? L4_CIRCULAR_DESTINATIONS
    : isL3
    ? L3_CIRCULAR_DESTINATIONS
    : [{ key: 'L1', circleText: 'L1', label: 'Coordinator' }]

  const defaultDest = isL5 ? 'L4' : isL4 ? 'L3' : 'L1'

  // Form states
  const [selectedDest, setSelectedDest] = useState(defaultDest)
  const [selectedReasons, setSelectedReasons] = useState([])
  const [instructions, setInstructions] = useState('')
  const [instructionsTouched, setInstructionsTouched] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')

  useEffect(() => {
    if (isOpen) {
      setSelectedDest(defaultDest)
      setSelectedReasons([])
      setInstructions('')
      setInstructionsTouched(false)
      setErrorMsg('')
      setSubmitting(false)
    }
  }, [isOpen, normLevel, defaultDest])

  if (!isOpen) return null

  // Escape key handler
  const handleKeyDownDialog = (e) => {
    if (e.key === 'Escape' && !submitting) {
      onClose()
    }
  }

  // Toggle reason chip
  const toggleReasonChip = (chip) => {
    if (submitting) return
    setSelectedReasons((prev) =>
      prev.includes(chip) ? prev.filter((r) => r !== chip) : [...prev, chip]
    )
    if (errorMsg) setErrorMsg('')
  }

  // Validation
  const instructionsTrimmed = instructions.trim()
  const isFormValid =
    Boolean(selectedDest) &&
    selectedReasons.length > 0 &&
    instructionsTrimmed.length >= 10 &&
    instructionsTrimmed.length <= 500

  // Common error flags
  const hasLengthError =
    instructionsTouched && instructionsTrimmed.length > 0 && instructionsTrimmed.length < 10
  const hasEmptyError = instructionsTouched && instructionsTrimmed.length === 0

  // =========================================================================
  // SUBMIT HANDLER: L2 (FIXED TO L1)
  // =========================================================================
  const handleL2Submit = async (e) => {
    e.preventDefault()
    setInstructionsTouched(true)
    setErrorMsg('')

    if (selectedReasons.length === 0) {
      setErrorMsg('Please select at least one reason for sending back.')
      return
    }

    if (instructionsTrimmed.length < 10) {
      setErrorMsg('Correction instructions must be at least 10 characters.')
      return
    }

    if (instructionsTrimmed.length > 500) {
      setErrorMsg('Correction instructions cannot exceed 500 characters.')
      return
    }

    try {
      setSubmitting(true)
      await onSubmit({
        action: 'RETURN',
        destination: 'L1',
        reason: selectedReasons.join(', '),
        remarks: instructionsTrimmed,
      })
      onClose()
    } catch (err) {
      setErrorMsg(err.message || 'Action failed. Please retry.')
    } finally {
      setSubmitting(false)
    }
  }

  // =========================================================================
  // SUBMIT HANDLER: L3, L4, L5 (CIRCULAR SELECTOR)
  // =========================================================================
  const handleMultiLevelSubmit = async (e) => {
    e.preventDefault()
    setInstructionsTouched(true)
    setErrorMsg('')

    if (!selectedDest) {
      setErrorMsg('Please select a destination stage to send back to.')
      return
    }

    if (selectedReasons.length === 0) {
      setErrorMsg('Please select at least one reason for sending back.')
      return
    }

    if (instructionsTrimmed.length < 10) {
      setErrorMsg('Correction instructions must be at least 10 characters.')
      return
    }

    if (instructionsTrimmed.length > 500) {
      setErrorMsg('Correction instructions cannot exceed 500 characters.')
      return
    }

    try {
      setSubmitting(true)
      await onSubmit({
        action: 'RETURN',
        destination: selectedDest,
        reason: selectedReasons.join(', '),
        remarks: instructionsTrimmed,
      })
      onClose()
    } catch (err) {
      setErrorMsg(err.message || 'Action failed. Please retry.')
    } finally {
      setSubmitting(false)
    }
  }

  // =========================================================================
  // RENDER: L2 CENTER HEAD REDESIGNED MODAL (UNMODIFIED PRESERVATION)
  // =========================================================================
  if (isL2) {
    return (
      <div
        className="flex-return-backdrop"
        role="dialog"
        aria-modal="true"
        aria-labelledby="l2-reject-title"
        onKeyDown={handleKeyDownDialog}
      >
        <div className="l2-reject-card">
          {/* Section A: Header */}
          <div className="l2-reject-header">
            <div className="l2-reject-header-left">
              <div className="l2-reject-icon-badge" aria-hidden="true">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="9 14 4 9 9 4" />
                  <path d="M20 20v-7a4 4 0 0 0-4-4H4" />
                </svg>
              </div>
              <div>
                <h3 id="l2-reject-title" className="l2-reject-title">
                  Reject &amp; Send Back
                </h3>
                <p className="l2-reject-subtitle">
                  Provide the correction details for the Placement Coordinator.
                </p>
              </div>
            </div>
            <button
              type="button"
              className="l2-reject-close flex-return-close-btn"
              onClick={onClose}
              disabled={submitting}
              aria-label="Close modal"
              title="Close (Esc)"
            >
              ✕
            </button>
          </div>

          <form onSubmit={handleL2Submit} className="l2-reject-form">
            <div className="l2-reject-body">
              {errorMsg && (
                <div className="l2-reject-alert error" role="alert">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="8" x2="12" y2="12" />
                    <line x1="12" y1="16" x2="12.01" y2="16" />
                  </svg>
                  <span>{errorMsg}</span>
                </div>
              )}

              {/* Section B: Candidate Information Card */}
              <div className="l2-reject-candidate-card">
                <div className="l2-candidate-avatar" aria-hidden="true">
                  {getInitials(candidateName)}
                </div>
                <div className="l2-candidate-details">
                  <div className="l2-candidate-name">{candidateName || 'Candidate Record'}</div>
                  <div className="l2-candidate-id">
                    {candidateId ? `Candidate ID: ${candidateId}` : 'ID: Not specified'}
                  </div>
                </div>
              </div>

              {/* Section C: Return Destination Card (L2 Fixed to L1) */}
              <div className="l2-reject-dest-card">
                <div className="l2-dest-top-row">
                  <span className="l2-dest-label">Sending back to</span>
                  <span className="l2-dest-badge">L1 Destination</span>
                </div>
                <div className="l2-dest-title">L1 – Placement Coordinator</div>
                <p className="l2-dest-sub">
                  The original submitter will correct the dossier and resubmit it for L2 review.
                </p>
              </div>

              {/* Section D: Rejection Reason Chips */}
              <div className="l2-reject-section">
                <label className="l2-reject-section-title">
                  <span>Reason for sending back</span>
                  <span className="l2-required-indicator">*</span>
                </label>
                <div className="l2-reason-chips-grid" role="group" aria-label="Rejection reasons">
                  {REJECTION_REASONS.map((chip) => {
                    const isSelected = selectedReasons.includes(chip)
                    return (
                      <button
                        key={chip}
                        type="button"
                        role="checkbox"
                        aria-checked={isSelected}
                        className={`l2-reason-chip ${isSelected ? 'selected' : ''}`}
                        onClick={() => toggleReasonChip(chip)}
                        disabled={submitting}
                      >
                        {isSelected && (
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <polyline points="20 6 9 17 4 12" />
                          </svg>
                        )}
                        <span>{chip}</span>
                      </button>
                    )
                  })}
                </div>
                {instructionsTouched && selectedReasons.length === 0 && (
                  <div className="l2-field-error" style={{ marginTop: '6px' }}>
                    Please select at least one reason for sending back.
                  </div>
                )}
              </div>

              {/* Section E: Correction Instructions */}
              <div className="l2-reject-section">
                <div className="l2-section-header-row">
                  <label htmlFor="correction-instructions-input" className="l2-reject-section-title">
                    <span>Correction instructions</span>
                    <span className="l2-required-indicator">*</span>
                  </label>
                  <span className="l2-field-hint">Visible to L1 Coordinator</span>
                </div>
                <textarea
                  id="correction-instructions-input"
                  name="correction_instructions"
                  className={`l2-instructions-textarea ${hasLengthError || hasEmptyError ? 'has-error' : ''}`}
                  rows={4}
                  maxLength={500}
                  placeholder="Describe exactly what is missing or needs correction..."
                  value={instructions}
                  onChange={(e) => {
                    setInstructions(e.target.value)
                    if (errorMsg) setErrorMsg('')
                  }}
                  onBlur={() => setInstructionsTouched(true)}
                  disabled={submitting}
                  required
                />
                <div className="l2-textarea-meta">
                  <div className="l2-meta-left">
                    {hasLengthError && (
                      <span className="l2-field-error">
                        Minimum 10 characters required (currently {instructionsTrimmed.length}).
                      </span>
                    )}
                    {hasEmptyError && (
                      <span className="l2-field-error">Correction instructions are required.</span>
                    )}
                    {!hasLengthError && !hasEmptyError && (
                      <span className="l2-field-sub">Provide clear details to facilitate timely resubmission.</span>
                    )}
                  </div>
                  <div className={`l2-char-counter ${instructions.length >= 490 ? 'limit' : ''}`}>
                    {instructions.length}/500
                  </div>
                </div>
              </div>
            </div>

            {/* Section F: Footer */}
            <div className="l2-reject-footer">
              <div className="l2-audit-badge">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                </svg>
                <span>Recorded in audit history.</span>
              </div>
              <div className="l2-footer-btn-group">
                <button
                  type="button"
                  className="flex-return-btn cancel l2-btn-cancel"
                  onClick={onClose}
                  disabled={submitting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="flex-return-btn submit danger l2-btn-submit-reject"
                  disabled={submitting || !isFormValid}
                >
                  {submitting ? (
                    <>
                      <span className="l2-spinner" aria-hidden="true" />
                      <span>Sending Back…</span>
                    </>
                  ) : (
                    <>
                      <span>↩</span>
                      <span>Reject &amp; Send Back</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </form>
        </div>
      </div>
    )
  }

  // =========================================================================
  // RENDER: L3, L4, L5 CIRCULAR DESTINATION SELECTOR REDESIGNED MODAL
  // =========================================================================
  return (
    <div
      className="flex-return-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="multilevel-reject-title"
      onKeyDown={handleKeyDownDialog}
    >
      <div className="l2-reject-card circular-modal-card">
        {/* Section A: Header */}
        <div className="l2-reject-header">
          <div className="l2-reject-header-left">
            <div className="l2-reject-icon-badge" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="9 14 4 9 9 4" />
                <path d="M20 20v-7a4 4 0 0 0-4-4H4" />
              </svg>
            </div>
            <div>
              <h3 id="multilevel-reject-title" className="l2-reject-title">
                Reject &amp; Send Back
              </h3>
              <p className="l2-reject-subtitle">
                Provide the correction details and select return destination.
              </p>
            </div>
          </div>
          <button
            type="button"
            className="l2-reject-close flex-return-close-btn"
            onClick={onClose}
            disabled={submitting}
            aria-label="Close modal"
            title="Close (Esc)"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleMultiLevelSubmit} className="l2-reject-form">
          <div className="l2-reject-body">
            {errorMsg && (
              <div className="l2-reject-alert error" role="alert">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
                <span>{errorMsg}</span>
              </div>
            )}

            {/* Section B: Candidate Information Card */}
            <div className="l2-reject-candidate-card">
              <div className="l2-candidate-avatar" aria-hidden="true">
                {getInitials(candidateName)}
              </div>
              <div className="l2-candidate-details">
                <div className="l2-candidate-name">{candidateName || 'Candidate Record'}</div>
                <div className="l2-candidate-id">
                  {candidateId ? `Candidate ID: ${candidateId}` : 'ID: Not specified'}
                </div>
              </div>
            </div>

            {/* Section C: Return Destination with Exact Circular Selector */}
            <div className="l2-reject-section">
              <label className="l2-reject-section-title">
                <span>Send back to</span>
                <span className="l2-required-indicator">*</span>
              </label>

              <div
                className="circular-dest-selector"
                role="radiogroup"
                aria-label="Select return destination"
              >
                {circularDestinations.map((dest) => {
                  const isSelected = selectedDest === dest.key
                  return (
                    <div
                      key={dest.key}
                      className={`circular-dest-item ${isSelected ? 'selected' : ''}`}
                      onClick={() => {
                        if (!submitting) {
                          setSelectedDest(dest.key)
                          if (errorMsg) setErrorMsg('')
                        }
                      }}
                      role="radio"
                      aria-checked={isSelected}
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if ((e.key === ' ' || e.key === 'Enter') && !submitting) {
                          e.preventDefault()
                          setSelectedDest(dest.key)
                          if (errorMsg) setErrorMsg('')
                        }
                      }}
                    >
                      <div
                        className={`circular-dest-btn ${isSelected ? 'selected' : ''}`}
                        aria-hidden="true"
                      >
                        <span className="circular-dest-level">{dest.circleText}</span>
                      </div>
                      <span className={`circular-dest-label ${isSelected ? 'selected' : ''}`}>
                        {dest.label}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Section D: Rejection Reason Chips */}
            <div className="l2-reject-section">
              <label className="l2-reject-section-title">
                <span>Reason for sending back</span>
                <span className="l2-required-indicator">*</span>
              </label>
              <div className="l2-reason-chips-grid" role="group" aria-label="Rejection reasons">
                {REJECTION_REASONS.map((chip) => {
                  const isSelected = selectedReasons.includes(chip)
                  return (
                    <button
                      key={chip}
                      type="button"
                      role="checkbox"
                      aria-checked={isSelected}
                      className={`l2-reason-chip ${isSelected ? 'selected' : ''}`}
                      onClick={() => toggleReasonChip(chip)}
                      disabled={submitting}
                    >
                      {isSelected && (
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      )}
                      <span>{chip}</span>
                    </button>
                  )
                })}
              </div>
              {instructionsTouched && selectedReasons.length === 0 && (
                <div className="l2-field-error" style={{ marginTop: '6px' }}>
                  Please select at least one reason for sending back.
                </div>
              )}
            </div>

            {/* Section E: Correction Instructions */}
            <div className="l2-reject-section">
              <div className="l2-section-header-row">
                <label htmlFor="multilevel-instructions-input" className="l2-reject-section-title">
                  <span>Correction instructions</span>
                  <span className="l2-required-indicator">*</span>
                </label>
                <span className="l2-field-hint">Visible to Reviewers &amp; Coordinator</span>
              </div>
              <textarea
                id="multilevel-instructions-input"
                name="correction_instructions"
                className={`l2-instructions-textarea ${hasLengthError || hasEmptyError ? 'has-error' : ''}`}
                rows={4}
                maxLength={500}
                placeholder="Describe exactly what is missing or needs correction..."
                value={instructions}
                onChange={(e) => {
                  setInstructions(e.target.value)
                  if (errorMsg) setErrorMsg('')
                }}
                onBlur={() => setInstructionsTouched(true)}
                disabled={submitting}
                required
              />
              <div className="l2-textarea-meta">
                <div className="l2-meta-left">
                  {hasLengthError && (
                    <span className="l2-field-error">
                      Minimum 10 characters required (currently {instructionsTrimmed.length}).
                    </span>
                  )}
                  {hasEmptyError && (
                    <span className="l2-field-error">Correction instructions are required.</span>
                  )}
                  {!hasLengthError && !hasEmptyError && (
                    <span className="l2-field-sub">Provide clear details to facilitate timely resubmission.</span>
                  )}
                </div>
                <div className={`l2-char-counter ${instructions.length >= 490 ? 'limit' : ''}`}>
                  {instructions.length}/500
                </div>
              </div>
            </div>
          </div>

          {/* Section F: Footer */}
          <div className="l2-reject-footer">
            <div className="l2-audit-badge">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
              <span>Recorded in audit history.</span>
            </div>
            <div className="l2-footer-btn-group">
              <button
                type="button"
                className="flex-return-btn cancel l2-btn-cancel"
                onClick={onClose}
                disabled={submitting}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="flex-return-btn submit danger l2-btn-submit-reject"
                disabled={submitting || !isFormValid}
              >
                {submitting ? (
                  <>
                    <span className="l2-spinner" aria-hidden="true" />
                    <span>Sending Back…</span>
                  </>
                ) : (
                  <>
                    <span>↩</span>
                    <span>Reject &amp; Send Back</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  )
}
