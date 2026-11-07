import React, { useState } from 'react'
import './UploadProgressModal.css'

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`
}

export default function UploadProgressModal({
  isOpen,
  stage = 'uploading', // 'preparing' | 'uploading' | 'processing' | 'saving_records' | 'syncing_audit' | 'completed' | 'error'
  percent = 0,
  files = [],
  activeFileName = '',
  completedCount = 0,
  totalCount = 0,
  totalBytes = 0,
  errorMessage = '',
  onRetry,
  onDone,
  onClose,
}) {
  const [showFileList, setShowFileList] = useState(false)

  if (!isOpen) return null

  const isIndeterminate =
    stage === 'preparing' ||
    stage === 'processing' ||
    stage === 'saving_records' ||
    stage === 'syncing_audit'

  // Derive human-readable stage descriptions
  let stageTitle = 'Uploading Documents'
  let stageDescription = activeFileName
    ? `Uploading ${activeFileName}…`
    : 'Transferring files to secure storage…'

  if (stage === 'preparing') {
    stageTitle = 'Preparing Upload Package'
    stageDescription = 'Validating files & preparing secure transmission…'
  } else if (stage === 'processing') {
    stageTitle = 'Preparing Storage & Folders'
    stageDescription = 'Verifying candidate Google Drive directory structure…'
  } else if (stage === 'saving_records') {
    stageTitle = 'Saving Document Records'
    stageDescription = 'Persisting verified document metadata in database…'
  } else if (stage === 'syncing_audit') {
    stageTitle = 'Synchronizing Placement Audit'
    stageDescription = 'Matching evidence and updating compliance statement…'
  } else if (stage === 'completed') {
    stageTitle = 'Submission Complete'
    stageDescription = 'All placement documents uploaded and verified.'
  } else if (stage === 'error') {
    stageTitle = 'Upload Failed'
    stageDescription = errorMessage || 'An error occurred during submission.'
  }

  const effectiveTotalCount = totalCount || files.length || 0
  const effectiveCompletedCount =
    stage === 'completed'
      ? effectiveTotalCount
      : Math.min(completedCount, effectiveTotalCount)

  const formattedTotalSize = totalBytes > 0 ? formatBytes(totalBytes) : ''

  return (
    <div
      className="cpass-upload-modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="cpass-upload-modal-title"
    >
      <div className="cpass-upload-modal-card">
        <div className="cpass-upload-content">
          {/* Top Folder / State Illustration */}
          {stage === 'completed' ? (
            <div className="cpass-upload-success-badge" aria-hidden="true">
              ✓
            </div>
          ) : stage === 'error' ? (
            <div className="cpass-upload-error-badge" aria-hidden="true">
              !
            </div>
          ) : (
            <div className="cpass-upload-folder-wrap">
              <svg
                className="cpass-upload-folder-icon"
                viewBox="0 0 48 48"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <defs>
                  <linearGradient id="folderBack" x1="4" y1="8" x2="44" y2="40" gradientUnits="userSpaceOnUse">
                    <stop stopColor="#4338CA" />
                    <stop offset="1" stopColor="#3B82F6" />
                  </linearGradient>
                  <linearGradient id="folderFront" x1="4" y1="16" x2="44" y2="42" gradientUnits="userSpaceOnUse">
                    <stop stopColor="#6366F1" />
                    <stop offset="0.5" stopColor="#4F46E5" />
                    <stop offset="1" stopColor="#2563EB" />
                  </linearGradient>
                  <linearGradient id="arrowGrad" x1="24" y1="18" x2="24" y2="34" gradientUnits="userSpaceOnUse">
                    <stop stopColor="#FFFFFF" />
                    <stop offset="1" stopColor="#E0E7FF" />
                  </linearGradient>
                </defs>
                {/* Back flap */}
                <path
                  d="M6 12C6 9.79086 7.79086 8 10 8H18.5858C19.6466 8 20.664 8.42143 21.4142 9.17157L24.8284 12.5858C25.5786 13.3359 26.596 13.7574 27.6569 13.7574H38C40.2091 13.7574 42 15.5482 42 17.7574V34C42 36.2091 40.2091 38 38 38H10C7.79086 38 6 36.2091 6 34V12Z"
                  fill="url(#folderBack)"
                  opacity="0.85"
                />
                {/* Front flap with glossy perspective */}
                <path
                  d="M4 20C4 17.7909 5.79086 16 8 16H40C42.2091 16 44 17.7909 44 20V36C44 38.2091 42.2091 40 40 40H8C5.79086 40 4 38.2091 4 36V20Z"
                  fill="url(#folderFront)"
                />
                {/* Clean upload arrow */}
                <path
                  d="M24 22L18 28H22V34H26V28H30L24 22Z"
                  fill="url(#arrowGrad)"
                />
              </svg>
            </div>
          )}

          {/* Title & Metadata Badges */}
          <h3 id="cpass-upload-modal-title" className="cpass-upload-title">
            {stage === 'completed'
              ? 'Submission Complete'
              : stage === 'error'
              ? 'Document Upload Failed'
              : 'CPASS Document Upload'}
          </h3>

          <div className="cpass-upload-subtitle-row">
            <span className="cpass-upload-badge">
              📁 {effectiveTotalCount} {effectiveTotalCount === 1 ? 'Document' : 'Documents'}
              {formattedTotalSize ? ` · ${formattedTotalSize}` : ''}
            </span>
            <span className="cpass-upload-badge destination">
              ☁️ Destination: Google Drive
            </span>
          </div>

          {/* Active Upload / Processing State */}
          {stage !== 'completed' && stage !== 'error' && (
            <div className="cpass-upload-progress-box">
              <div className="cpass-upload-status-row">
                <span className="cpass-upload-status-label">
                  <span className="cpass-mini-spinner" aria-hidden="true" />
                  {stageTitle}
                </span>
                <span className="cpass-upload-percent-text">
                  {isIndeterminate ? 'Syncing…' : `${percent}%`}
                </span>
              </div>

              {/* Real Progress Bar */}
              <div className="cpass-progress-track" role="progressbar" aria-valuenow={percent} aria-valuemin="0" aria-valuemax="100">
                <div
                  className={`cpass-progress-fill ${isIndeterminate ? 'indeterminate' : ''}`}
                  style={!isIndeterminate ? { width: `${Math.max(4, percent)}%` } : undefined}
                />
              </div>

              <div className="cpass-upload-meta-row">
                <span className="cpass-upload-current-file" title={stageDescription}>
                  {stageDescription}
                </span>
                <span className="cpass-upload-count-tag">
                  {effectiveCompletedCount} of {effectiveTotalCount} completed
                </span>
              </div>
            </div>
          )}

          {/* Expandable File Breakdown */}
          {files.length > 0 && stage !== 'completed' && stage !== 'error' && (
            <>
              <button
                type="button"
                className="cpass-file-list-toggle"
                onClick={() => setShowFileList((prev) => !prev)}
                aria-expanded={showFileList}
              >
                <span>{showFileList ? '▴ Hide Breakdown' : '▾ View Document Breakdown'}</span>
                <span>({files.length} files)</span>
              </button>

              {showFileList && (
                <div className="cpass-expandable-file-list">
                  {files.map((f, idx) => {
                    let statusIcon = '•'
                    let statusColor = '#94a3b8'
                    if (f.status === 'completed') {
                      statusIcon = '✓'
                      statusColor = '#16a34a'
                    } else if (f.status === 'uploading') {
                      statusIcon = '⟳'
                      statusColor = '#4f46e5'
                    } else if (f.status === 'failed') {
                      statusIcon = '✕'
                      statusColor = '#dc2626'
                    }

                    return (
                      <div key={f.id || idx} className="cpass-file-row">
                        <div className="cpass-file-row-left">
                          <span className="cpass-file-status-icon" style={{ color: statusColor }}>
                            {statusIcon}
                          </span>
                          <span className="cpass-file-name-span" title={f.name}>
                            {f.name}
                          </span>
                        </div>
                        {f.size ? (
                          <span className="cpass-file-size-span">{formatBytes(f.size)}</span>
                        ) : null}
                      </div>
                    )
                  })}
                </div>
              )}
            </>
          )}

          {/* Completed State */}
          {stage === 'completed' && (
            <div style={{ marginTop: '12px' }}>
              <div className="cpass-upload-success-title">All documents uploaded successfully.</div>
              <p className="cpass-upload-success-text">
                All {effectiveTotalCount} staged placement document{effectiveTotalCount === 1 ? '' : 's'} have been securely transferred to Google Drive, registered in database records, and synchronized with candidate placement audit evidence.
              </p>
              <div className="cpass-upload-modal-footer" style={{ justifyContent: 'center' }}>
                <button
                  type="button"
                  className="cpass-btn-primary"
                  onClick={onDone || onClose}
                  style={{ minWidth: '130px' }}
                >
                  ✓ Done
                </button>
              </div>
            </div>
          )}

          {/* Error State */}
          {stage === 'error' && (
            <div style={{ marginTop: '12px' }}>
              <div className="cpass-upload-error-title">Document upload could not be completed.</div>
              <div className="cpass-upload-error-text">
                <strong>Error Details:</strong>
                <div>{errorMessage || 'Network or authorization error during upload.'}</div>
                <div style={{ marginTop: '6px', fontSize: '12px', color: '#64748b' }}>
                  Staged files and entered details have been preserved. You can safely retry the upload.
                </div>
              </div>
              <div className="cpass-upload-modal-footer">
                <button
                  type="button"
                  className="cpass-btn-secondary"
                  onClick={onClose}
                >
                  Close &amp; Keep Staged
                </button>
                {onRetry && (
                  <button
                    type="button"
                    className="cpass-btn-primary"
                    onClick={onRetry}
                  >
                    🔄 Retry Upload
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

