import React, { useState, useEffect } from 'react'
import { api } from '../lib/api'
import './UserProfileModal.css'

export default function UserProfileModal({ isOpen, onClose, profile, onProfileUpdated }) {
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

  if (!isOpen || !profile) return null

  const roleDisplay = {
    L1_COORDINATOR: 'Placement Executive (L1)',
    L2_MANAGER: 'Centre Head (L2)',
    L3_COPS: 'COPS Audit Team (L3)',
    L4_LEADER: 'Business Leader (L4)',
    L5_CEO: 'Chief Executive Officer (L5)',
    ADMIN: 'System Administrator',
  }[profile.role] || profile.role

  const initials = profile.full_name
    ? profile.full_name
        .split(' ')
        .filter(Boolean)
        .map((n) => n[0])
        .join('')
        .slice(0, 2)
        .toUpperCase()
    : 'CP'

  const hasChanged = fullName.trim() !== (profile.full_name || '').trim()

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

  return (
    <div className="cpass-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="cpass-profile-title">
      <div className="cpass-profile-card">
        {/* Modal Header */}
        <div className="cpass-profile-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div className="cpass-profile-avatar-large">{initials}</div>
            <div>
              <h3 id="cpass-profile-title" style={{ margin: 0, fontSize: '17px', color: '#0f172a', fontWeight: 600 }}>
                User Account Profile
              </h3>
              <span style={{ fontSize: '12px', color: '#64748b' }}>
                CPASS State Placement Audit System
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

        {/* Modal Body */}
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
              Display Name <span style={{ color: '#2563eb', fontSize: '11px', fontWeight: 500 }}>(Editable)</span>
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
              This name appears on placement audit review sign-offs and managerial verification records.
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

          {/* Row: Role & Assigned State (Read-only) */}
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

          {/* Account Identity Notice */}
          <div className="cpass-profile-notice">
            <span style={{ fontSize: '14px' }}>🛡️</span>
            <div>
              <strong>Administrative Access Notice</strong>
              <p>
                Email, role classification, and state ownership boundaries are strictly governed by CPASS System Administration to maintain statutory compliance and data isolation.
              </p>
            </div>
          </div>

          {/* Modal Actions */}
          <div className="cpass-profile-footer">
            <button
              type="button"
              className="l1-btn-secondary"
              onClick={onClose}
              disabled={saving}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="cpass-profile-save-btn"
              disabled={saving || !hasChanged}
            >
              {saving ? 'Saving Changes…' : 'Save Display Name'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
