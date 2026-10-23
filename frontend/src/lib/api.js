const rawBase = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const BASE = rawBase.replace(/\/+$/, '')
const TOKEN_KEY = 'cpass_token'
const REFRESH_TOKEN_KEY = 'cpass_refresh_token'

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function getRefreshToken() {
  try {
    return localStorage.getItem(REFRESH_TOKEN_KEY)
  } catch {
    return null
  }
}

export function setTokens({ accessToken, refreshToken }) {
  try {
    if (accessToken) {
      localStorage.setItem(TOKEN_KEY, accessToken)
    } else {
      localStorage.removeItem(TOKEN_KEY)
    }
    if (refreshToken) {
      localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
    } else if (refreshToken === null) {
      localStorage.removeItem(REFRESH_TOKEN_KEY)
    }
  } catch {
    // LocalStorage fallback
  }
}

export function setToken(token) {
  setTokens({ accessToken: token })
}

export function clearTokens() {
  try {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
  } catch {
    // LocalStorage fallback
  }
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
      const storedRefreshToken = getRefreshToken()
      const res = await fetch(`${BASE}/auth/refresh`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          refresh_token: storedRefreshToken || null,
        }),
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
      if (data.access_token) {
        setTokens({
          accessToken: data.access_token,
          refreshToken: data.refresh_token,
        })
      }
      return data
    } finally {
      refreshPromise = null
    }
  })()

  return refreshPromise
}

export async function api(path, params, options = {}, _isRetry = false) {
  const token = getToken()
  const qs = params ? '?' + new URLSearchParams(params).toString() : ''
  const headers = {
    ...(options.headers || {}),
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
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
    // Check if we have credentials or tokens to attempt refresh
    const hasRefreshToken = !!getRefreshToken()
    const hasToken = !!token

    if (hasRefreshToken || hasToken) {
      try {
        await refreshSession()
        // Retry the request once with refreshed token
        return api(path, params, options, true)
      } catch (refreshErr) {
        // Refresh failed; clear tokens and propagate original 401
        clearTokens()
        const err = new Error(refreshErr.message || 'Session expired')
        err.status = 401
        throw err
      }
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
  const token = getToken()
  const headers = {}
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
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
  const token = getToken()
  const headers = {}
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
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

