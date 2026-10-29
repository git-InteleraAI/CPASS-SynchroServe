import { createContext, useContext, useEffect, useState } from 'react'
import { api, clearTokens } from '../lib/api'

const AuthContext = createContext(null)
export const useAuth = () => useContext(AuthContext)

export function AuthProvider({ children }) {
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let isCancelled = false

    async function initSession() {
      try {
        // Restore the session from HttpOnly cookies; tokens are never exposed to JavaScript.
        const me = await api('/auth/me')
        if (!isCancelled) {
          setProfile(me)
        }
      } catch {
        // Expected unauthenticated startup state (no active session) or revoked token
        if (!isCancelled) {
          setProfile(null)
          clearTokens()
        }
      } finally {
        if (!isCancelled) {
          setLoading(false)
        }
      }
    }

    initSession()

    return () => {
      isCancelled = true
    }
  }, [])

  // The role picked on the login screen is verified by the backend against the profile in Supabase.
  async function login(email, password, expectedRole) {
    const data = await api('/auth/login', null, {
      method: 'POST',
      body: JSON.stringify({
        email: email.trim(),
        password,
        expected_role: expectedRole,
      }),
    })

    // The backend sets HttpOnly cookies. Never store authentication tokens in JavaScript storage.
    setProfile(data.user)
    return data.user
  }

  async function logout() {
    try {
      await api('/auth/logout', null, { method: 'POST' })
    } catch {
      // Gracefully continue with client-side cleanup even if server is unreachable
    } finally {
      clearTokens()
      setProfile(null)
    }
  }

  async function refreshProfile() {
    try {
      const me = await api('/auth/me')
      setProfile(me)
      return me
    } catch {
      clearTokens()
      setProfile(null)
      return null
    }
  }

  return (
    <AuthContext.Provider value={{ profile, loading, login, logout, refreshProfile }}>
      {children}
    </AuthContext.Provider>
  )
}
