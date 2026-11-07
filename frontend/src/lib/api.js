const rawBase = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const BASE = rawBase.replace(/\/+$/, '')

// Protected preview URL: PDF.js requests byte ranges directly with HttpOnly cookies.
export function getDocumentPreviewUrl(candidateId, documentId) {
  return `${BASE}/candidates/${candidateId}/documents/${documentId}/download`
}
// Authentication is cookie-only. These exports remain as no-op compatibility
// shims for older imports; no token is read from or written to JavaScript storage.
export function getToken() {
  return null
}

export function getRefreshToken() {
  return null
}

export function setTokens(_tokens) {
  // Intentionally disabled: auth tokens must never be persisted in localStorage.
}

export function setToken(_token) {
  // Intentionally disabled.
}

export function clearTokens() {
  // Intentionally no-op; the server clears HttpOnly cookies via /auth/logout.
}

export function clearToken() {
  clearTokens()
}

// In-flight refresh promise mutex to prevent concurrent refresh races
let refreshPromise = null

export async function refreshSession() {
  if (refreshPromise) {
    return refreshPromise
  }

  refreshPromise = (async () => {
    try {
      const res = await fetch(`${BASE}/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
      })

      if (!res.ok) {
        clearTokens()
        const errData = await res.json().catch(() => ({}))
        const err = new Error(errData.detail || 'Session expired. Please log in again.')
        err.status = res.status
        throw err
      }

      const data = await res.json()
      // The refreshed session is delivered only through HttpOnly Set-Cookie headers.
      return data
    } finally {
      refreshPromise = null
    }
  })()

  return refreshPromise
}

export async function api(path, params, options = {}, _isRetry = false) {
  const qs = params ? '?' + new URLSearchParams(params).toString() : ''
  const headers = {
    ...(options.headers || {}),
  }
  if (options.body && typeof options.body === 'string' && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json'
  }

  const res = await fetch(`${BASE}${path}${qs}`, {
    ...options,
    headers,
    credentials: 'include',
  })

  // Handle 401 with automatic token refresh if token expired and not an auth management endpoint
  const isAuthManagement =
    path === '/auth/login' ||
    path === '/auth/refresh' ||
    path === '/auth/logout'

  if (res.status === 401 && !isAuthManagement && !_isRetry) {
    try {
      await refreshSession()
      // Retry the request once with the refreshed HttpOnly cookie.
      return api(path, params, options, true)
    } catch (refreshErr) {
      const err = new Error(refreshErr.message || 'Session expired')
      err.status = 401
      throw err
    }
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    let msg
    if (Array.isArray(body.detail)) {
      msg = body.detail
        .map((d) => d.msg || (typeof d === 'string' ? d : JSON.stringify(d)))
        .join(', ')
    } else if (body.detail && typeof body.detail === 'object') {
      msg = body.detail.msg || JSON.stringify(body.detail)
    } else {
      msg = body.detail || body.message || `Request failed (${res.status})`
    }
    const err = new Error(msg)
    err.status = res.status
    err.detail = body.detail
    throw err
  }

  return res.json()
}

export async function downloadDocument(candidateId, documentId, fallbackFilename, _isRetry = false) {
  const headers = {}
  const res = await fetch(`${BASE}/candidates/${candidateId}/documents/${documentId}/download`, {
    headers,
    credentials: 'include',
  })

  if (res.status === 401 && !_isRetry) {
    try {
      await refreshSession()
      return downloadDocument(candidateId, documentId, fallbackFilename, true)
    } catch {
      clearTokens()
      throw new Error('Session expired. Please log in again to download documents.')
    }
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const err = new Error(body.detail || `Download failed (${res.status})`)
    err.status = res.status
    throw err
  }

  const blob = await res.blob()
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fallbackFilename || `document_${documentId}`
  document.body.appendChild(a)
  a.click()
  a.remove()
  // Defer revocation so browsers have sufficient time to initiate the file save dialog
  setTimeout(() => {
    window.URL.revokeObjectURL(url)
  }, 60000)
}

export async function fetchDocumentBlob(candidateId, documentId, _isRetry = false) {
  const headers = {}
  const res = await fetch(`${BASE}/candidates/${candidateId}/documents/${documentId}/download`, {
    headers,
    credentials: 'include',
  })

  if (res.status === 401 && !_isRetry) {
    try {
      await refreshSession()
      return fetchDocumentBlob(candidateId, documentId, true)
    } catch {
      clearTokens()
      throw new Error('Session expired. Please log in again to preview documents.')
    }
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const err = new Error(body.detail || `Failed to fetch document (${res.status})`)
    err.status = res.status
    throw err
  }

  return res.blob()
}

export function uploadDocumentBatchWithProgress(candidateId, formData, onProgress, _isRetry = false) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${BASE}/candidates/${candidateId}/documents/submit`)
    xhr.withCredentials = true

    if (xhr.upload && onProgress) {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && event.total > 0) {
          const percent = Math.min(99, Math.round((event.loaded / event.total) * 100))
          onProgress({
            stage: 'uploading',
            loadedBytes: event.loaded,
            totalBytes: event.total,
            percent,
          })
        }
      }

      xhr.upload.onload = () => {
        onProgress({
          stage: 'processing',
          percent: 100,
        })
      }
    }

    xhr.onload = async () => {
      if (xhr.status === 401 && !_isRetry) {
        try {
          await refreshSession()
          const retryRes = await uploadDocumentBatchWithProgress(candidateId, formData, onProgress, true)
          return resolve(retryRes)
        } catch {
          clearTokens()
          return reject(new Error('Session expired. Please log in again to upload documents.'))
        }
      }

      let body = {}
      try {
        body = JSON.parse(xhr.responseText)
      } catch {
        body = {}
      }

      if (xhr.status >= 200 && xhr.status < 300) {
        return resolve(body)
      }

      let msg = body.detail || body.message || `Upload failed (${xhr.status})`
      if (Array.isArray(body.detail)) {
        msg = body.detail.map((d) => d.msg || (typeof d === 'string' ? d : JSON.stringify(d))).join(', ')
      } else if (body.detail && typeof body.detail === 'object') {
        msg = body.detail.msg || JSON.stringify(body.detail)
      }
      const err = new Error(msg)
      err.status = xhr.status
      err.detail = body.detail
      return reject(err)
    }

    xhr.onerror = () => {
      reject(new Error('Network error occurred during document upload. Please check your connection and try again.'))
    }

    xhr.ontimeout = () => {
      reject(new Error('Document upload request timed out. Please try again.'))
    }

    xhr.send(formData)
  })
}

