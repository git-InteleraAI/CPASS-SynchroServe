const rawBase = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const BASE = rawBase.replace(/\/+$/, '')
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
  window.URL.revokeObjectURL(url)
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