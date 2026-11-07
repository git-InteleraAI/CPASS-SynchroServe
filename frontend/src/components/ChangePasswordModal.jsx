import React, { useState, useEffect } from 'react'
import { api } from '../lib/api'
import './ChangePasswordModal.css'

export default function ChangePasswordModal({ isOpen, onClose }) {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showCurrent, setShowCurrent] = useState(false)
  const [showNew, setShowNew] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(false)

  const handleDiscard = () => {
    setCurrentPassword('')
    setNewPassword('')
    setConfirmPassword('')
    setShowCurrent(false)
    setShowNew(false)
    setShowConfirm(false)
    setError(null)
    setSuccess(false)
    if (onClose) onClose()
  }

  useEffect(() => {
    if (!isOpen) {
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setShowCurrent(false)
      setShowNew(false)
      setShowConfirm(false)
      setError(null)
      setSuccess(false)
    }
  }, [isOpen])

  // Close on Escape key press
  useEffect(() => {
    if (!isOpen) return
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && !saving) {
        handleDiscard()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, saving])

  // Password rules validation
  const hasMinLen = newPassword.length >= 8
  const hasUpper = /[A-Z]/.test(newPassword)
  const hasLower = /[a-z]/.test(newPassword)
  const hasNumber = /[0-9]/.test(newPassword)
  const hasSpecial = /[!@#$%^&*]/.test(newPassword)

  const passedConditions = [hasMinLen, hasUpper, hasLower, hasNumber, hasSpecial].filter(Boolean).length
  const allConditionsMet = passedConditions === 5

  let strengthLevel = 0
  let strengthClass = ''
  let strengthLabel = 'Password strength requirement:'

  if (newPassword.length > 0) {
    if (passedConditions <= 2) {
      strengthLevel = 1
      strengthClass = 'weak'
      strengthLabel = 'Weak password. Must contain;'
    } else if (passedConditions <= 4) {
      strengthLevel = 2
      strengthClass = 'medium'
      strengthLabel = 'Medium password. Must contain;'
    } else {
      strengthLevel = 3
      strengthClass = 'strong'
      strengthLabel = 'Strong password. All conditions satisfied.'
    }
  }

  // Real-time password match logic
  const showMatchFeedback = newPassword.length > 0 && confirmPassword.length > 0
  const isMatching = showMatchFeedback && newPassword === confirmPassword

  // Strict Apply Changes validation
  const canApply =
    Boolean(currentPassword.trim()) &&
    allConditionsMet &&
    passwordsMatchCondition(newPassword, confirmPassword) &&
    newPassword !== currentPassword &&
    !saving

  function passwordsMatchCondition(p1, p2) {
    return p1.length > 0 && p2.length > 0 && p1 === p2
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!currentPassword) {
      setError('Please enter your current password.')
      return
    }
    if (!newPassword) {
      setError('Please enter a new password.')
      return
    }
    if (newPassword !== confirmPassword) {
      setError('New password and confirmation do not match.')
      return
    }
    if (newPassword === currentPassword) {
      setError('New password must be different from current password.')
      return
    }
    if (!allConditionsMet) {
      setError('Password does not satisfy all security requirements.')
      return
    }

    setSaving(true)
    setError(null)
    setSuccess(false)

    try {
      await api('/auth/change-password', null, {
        method: 'POST',
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
          confirm_password: confirmPassword,
        }),
      })

      setSuccess(true)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')

      setTimeout(() => {
        setSuccess(false)
        if (onClose) onClose()
      }, 1500)
    } catch (err) {
      setError(err?.message || 'Failed to update password. Please check your current password and try again.')
    } finally {
      setSaving(false)
    }
  }

  if (!isOpen) return null

  return (
    <div
      className="cpass-cp-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="cpass-cp-title"
    >
      <div className="cpass-cp-card">
        {/* Header: Circular Lock Icon + Heading + Subtitle */}
        <div className="cpass-cp-header">
          <div className="cpass-cp-lock-circle">
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#0f172a"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <rect x="4" y="11" width="16" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
          </div>
          <div className="cpass-cp-title-wrap">
            <h2 id="cpass-cp-title" className="cpass-cp-title">
              Change Password
            </h2>
            <p className="cpass-cp-subtitle">
              Update password for enhanced account security.
            </p>
          </div>
        </div>

        <div className="cpass-cp-divider" />

        <form onSubmit={handleSubmit} className="cpass-cp-form">
          {error && (
            <div className="cpass-cp-alert error" role="alert">
              <span>⚠️</span> {error}
            </div>
          )}

          {success && (
            <div className="cpass-cp-alert success" role="status">
              <span>✓</span> Password changed successfully! You will stay logged in.
            </div>
          )}

          {/* 1. Current Password */}
          <div className="cpass-cp-field">
            <label htmlFor="cpass-cp-current" className="cpass-cp-label">
              Current Password <span className="cpass-cp-asterisk">*</span>
            </label>
            <div className="cpass-cp-input-wrap">
              <input
                id="cpass-cp-current"
                type={showCurrent ? 'text' : 'password'}
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                placeholder="••••••••••••"
                required
                disabled={saving}
                className="cpass-cp-input"
                autoComplete="current-password"
              />
              <button
                type="button"
                className="cpass-cp-eye-btn"
                onClick={() => setShowCurrent(!showCurrent)}
                title={showCurrent ? 'Hide password' : 'Show password'}
                tabIndex={-1}
              >
                <EyeIcon isVisible={showCurrent} />
              </button>
            </div>
          </div>

          {/* 2. New Password */}
          <div className="cpass-cp-field">
            <label htmlFor="cpass-cp-new" className="cpass-cp-label">
              New Password <span className="cpass-cp-asterisk">*</span>
            </label>
            <div className="cpass-cp-input-wrap">
              <input
                id="cpass-cp-new"
                type={showNew ? 'text' : 'password'}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="••••••••••••"
                required
                disabled={saving}
                className="cpass-cp-input"
                autoComplete="new-password"
              />
              <button
                type="button"
                className="cpass-cp-eye-btn"
                onClick={() => setShowNew(!showNew)}
                title={showNew ? 'Hide password' : 'Show password'}
                tabIndex={-1}
              >
                <EyeIcon isVisible={showNew} />
              </button>
            </div>
          </div>

          {/* 3. Confirm New Password with Clear action & Live Feedback */}
          <div className="cpass-cp-field">
            <div className="cpass-cp-label-row">
              <label htmlFor="cpass-cp-confirm" className="cpass-cp-label">
                Confirm New Password <span className="cpass-cp-asterisk">*</span>
              </label>
              {confirmPassword && (
                <button
                  type="button"
                  className="cpass-cp-clear-btn"
                  onClick={() => setConfirmPassword('')}
                  disabled={saving}
                >
                  Clear
                </button>
              )}
            </div>
            <div className="cpass-cp-input-wrap">
              <input
                id="cpass-cp-confirm"
                type={showConfirm ? 'text' : 'password'}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="••••••••••••"
                required
                disabled={saving}
                className="cpass-cp-input"
                autoComplete="new-password"
              />
              <button
                type="button"
                className="cpass-cp-eye-btn"
                onClick={() => setShowConfirm(!showConfirm)}
                title={showConfirm ? 'Hide password' : 'Show password'}
                tabIndex={-1}
              >
                <EyeIcon isVisible={showConfirm} />
              </button>
            </div>

            {/* Live Password Match / Mismatch Feedback Indicator */}
            {showMatchFeedback && (
              <div className={`cpass-cp-match-status ${isMatching ? 'match' : 'mismatch'}`}>
                <span className="cpass-cp-match-icon">
                  {isMatching ? (
                    <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                      <circle cx="8" cy="8" r="8" fill="#10B981" />
                      <path d="M4.5 8.2L6.8 10.5L11.5 5.8" stroke="white" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  ) : (
                    <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                      <circle cx="8" cy="8" r="8" fill="#EF4444" />
                      <path d="M8 4.5V9M8 11.5H8.01" stroke="white" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </span>
                <span className="cpass-cp-match-text">
                  {isMatching ? 'Passwords match' : 'Passwords do not match'}
                </span>
              </div>
            )}
          </div>

          {/* Real-time Password Strength Meter */}
          <div className="cpass-cp-strength-wrap">
            {/* 3-Segment Horizontal Bar */}
            <div className="cpass-cp-strength-bar">
              <div className={`cpass-cp-seg ${strengthLevel >= 1 ? strengthClass : ''}`} />
              <div className={`cpass-cp-seg ${strengthLevel >= 2 ? strengthClass : ''}`} />
              <div className={`cpass-cp-seg ${strengthLevel >= 3 ? strengthClass : ''}`} />
            </div>

            {/* Strength Status Text */}
            <p className={`cpass-cp-strength-text ${strengthClass}`}>
              {strengthLabel}
            </p>

            {/* 2-Column Grid Checklist */}
            <div className="cpass-cp-checklist-grid">
              <ChecklistItem satisfied={hasMinLen} text="At least 8 characters" />
              <ChecklistItem satisfied={hasUpper} text="At least 1 uppercase" />
              <ChecklistItem satisfied={hasLower} text="At least 1 lowercase" />
              <ChecklistItem satisfied={hasNumber} text="At least 1 number" />
              <ChecklistItem satisfied={hasSpecial} text="At least 1 special character" />
            </div>
          </div>

          {/* Action Buttons: Discard & Apply Changes */}
          <div className="cpass-cp-footer">
            <button
              type="button"
              className="cpass-cp-btn-discard"
              onClick={handleDiscard}
              disabled={saving}
            >
              Discard
            </button>
            <button
              type="submit"
              className="cpass-cp-btn-apply"
              disabled={!canApply}
            >
              {saving ? 'Applying Changes…' : 'Apply Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function EyeIcon({ isVisible }) {
  if (isVisible) {
    return (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
        <circle cx="12" cy="12" r="3" />
      </svg>
    )
  }
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

function ChecklistItem({ satisfied, text }) {
  return (
    <div className={`cpass-cp-check-item ${satisfied ? 'satisfied' : 'pending'}`}>
      <span className="cpass-cp-check-icon">
        {satisfied ? (
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <circle cx="9" cy="9" r="9" fill="#10B981" />
            <path d="M5.5 9.2L7.8 11.5L12.8 6.5" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        ) : (
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <circle cx="9" cy="9" r="9" fill="#94A3B8" />
            <path d="M6 6L12 12M12 6L6 12" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </span>
      <span className="cpass-cp-check-label">{text}</span>
    </div>
  )
}
