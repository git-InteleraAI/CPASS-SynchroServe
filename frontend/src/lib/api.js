const rawBase = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const BASE = rawBase.replace(/\/+$/, '')
const TOKEN_KEY = 'cpass_token'

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token) {
  try {
    if (token) {
      localStorage.setItem(TOKEN_KEY, token)
    } else {
      localStorage.removeItem(TOKEN_KEY)
    }
  } catch {
    // LocalStorage may be unavailable in some private browsing contexts
  }
}

export function clearToken() {
  try {
    localStorage.removeItem(TOKEN_KEY)
  } catch {
    // LocalStorage fallback
  }
}

export async function api(path, params, options = {}) {
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

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const msg = body.detail || body.message || `Request failed (${res.status})`
    const err = new Error(msg)
    err.status = res.status
    throw err
  }

  return res.json()
}

export async function downloadDocument(candidateId, documentId, fallbackFilename) {
  const token = getToken()
  const headers = {}
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const res = await fetch(`${BASE}/candidates/${candidateId}/documents/${documentId}/download`, {
    headers,
    credentials: 'include',
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Download failed (${res.status})`)
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
