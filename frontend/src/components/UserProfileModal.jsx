import React, { useState, useEffect } from 'react'
import { api } from '../lib/api'
import './UserProfileModal.css'

export default function UserProfileModal({
  isOpen,
  onClose,
  profile,
  onProfileUpdated,
  onOpenChangePassword,
}) {
  const [fullName, setFullName] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    if (profile) {
      setFullName(profile.full_name || '')
      setError(null)
      setSuccess(false)
    }
  }, [profile, isOpen])

  // Close on Escape key press
  useEffect(() => {
    if (!isOpen) return
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && !saving) {
        onClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, saving, onClose])

  const roleDisplay = profile
    ? {
        L1_COORDINATOR: 'Placement Executive (L1)',
        L2_MANAGER: 'Centre Head (L2)',
        L3_COPS: 'COPS Audit Team (L3)',
        L4_LEADER: 'Business Leader (L4)',
        L5_CEO: 'Chief Executive Officer (L5)',
        ADMIN: 'System Administrator',
      }[profile.role] || profile.role
    : ''

  const initials = profile?.full_name
    ? profile.full_name
        .split(' ')
        .filter(Boolean)
        .map((n) => n[0])
        .join('')
        .slice(0, 2)
        .toUpperCase()
    : 'CP'

  const handleSave = async (e) => {
    e.preventDefault()
    const trimmed = fullName.trim()
    if (!trimmed) {
      setError('Display name cannot be empty.')
      return
    }
    if (trimmed.length < 2) {
      setError('Display name must be at least 2 characters.')
      return
    }
    if (trimmed.length > 100) {
      setError('Display name must not exceed 100 characters.')
      return
    }

    setSaving(true)
    setError(null)
    setSuccess(false)

    try {
      const updated = await api('/auth/profile', null, {
        method: 'PATCH',
        body: JSON.stringify({ full_name: trimmed }),
      })
      setSuccess(true)
      if (onProfileUpdated) {
        onProfileUpdated(updated)
      }
      setTimeout(() => {
        onClose()
      }, 900)
    } catch (err) {
      setError(err?.message || 'Failed to update display name. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  if (!isOpen || !profile) return null

  return (
    <div
      className="cpass-modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="cpass-profile-title"
    >
      <div className="cpass-profile-card">
        {/* Header with Avatar, Title and Close Button */}
        <div className="cpass-profile-header">
          <div className="cpass-profile-header-user">
            <div className="cpass-profile-avatar-large">{initials}</div>
            <div>
              <h3 id="cpass-profile-title" className="cpass-profile-title">
                User Account Profile
              </h3>
              <span className="cpass-profile-sub">
                CPASS Placement Audit System
              </span>
            </div>
          </div>
          <button
            type="button"
            className="cpass-profile-close-btn"
            onClick={onClose}
            title="Close dialog (Esc)"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSave} className="cpass-profile-body">
          {error && (
            <div className="cpass-profile-alert error" role="alert">
              <span>⚠️</span> {error}
            </div>
          )}

          {success && (
            <div className="cpass-profile-alert success" role="status">
              <span>✓</span> Display name updated successfully!
            </div>
          )}

          {/* Display Name (Editable) */}
          <div className="cpass-profile-field">
            <label htmlFor="cpass-profile-fullname">
              Display Name <span className="cpass-profile-tag-edit">(Editable)</span>
            </label>
            <input
              id="cpass-profile-fullname"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Enter your official display name"
              disabled={saving}
              required
              minLength={2}
              maxLength={100}
              className="cpass-profile-input editable"
            />
            <span className="cpass-profile-hint">
              This name appears on placement audit reviews and verification sign-offs.
            </span>
          </div>

          {/* Email Address (Read-only) */}
          <div className="cpass-profile-field">
            <label>
              Email Address <span className="cpass-profile-lock-tag">🔒 Read-only</span>
            </label>
            <input
              type="text"
              value={profile.email || 'Not configured'}
              readOnly
              disabled
              className="cpass-profile-input readonly"
            />
          </div>

          {/* Role & State Grid */}
          <div className="cpass-profile-grid">
            <div className="cpass-profile-field">
              <label>
                Assigned Role <span className="cpass-profile-lock-tag">🔒 Read-only</span>
              </label>
              <div className="cpass-profile-pill role">
                <span className="cpass-profile-pill-dot" />
                {roleDisplay}
              </div>
            </div>

            <div className="cpass-profile-field">
              <label>
                Assigned State <span className="cpass-profile-lock-tag">🔒 Read-only</span>
              </label>
              <div className="cpass-profile-pill state">
                📍 {profile.assigned_state || 'All States (Global)'}
              </div>
            </div>
          </div>

          {/* Prominent Account Security Banner (Opens Dedicated Change Password Modal) */}
          <div className="cpass-profile-security-banner">
            <div className="cpass-security-banner-info">
              <div className="cpass-security-banner-icon">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#2563eb" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="4" y="11" width="16" height="11" rx="2" ry="2" />
                  <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                </svg>
              </div>
              <div>
                <strong className="cpass-security-banner-title">Account Password & Security</strong>
                <p className="cpass-security-banner-desc">
                  Update your credentials anytime for enhanced account security.
                </p>
              </div>
            </div>
            <button
              type="button"
              className="cpass-btn-switch-password"
              onClick={onOpenChangePassword}
              title="Open Change Password dialog"
            >
              Change Password →
            </button>
          </div>

          {/* Actions */}
          <div className="cpass-profile-footer">
            <button
              type="button"
              className="cpass-profile-btn-cancel"
              onClick={onClose}
              disabled={saving}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="cpass-profile-save-btn"
              disabled={saving || fullName.trim() === (profile.full_name || '').trim()}
            >
              {saving ? 'Saving…' : 'Save Display Name'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
