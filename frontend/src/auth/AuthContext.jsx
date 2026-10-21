import { createContext, useContext, useEffect, useState } from 'react'
import { api, clearToken, setToken } from '../lib/api'

const AuthContext = createContext(null)
export const useAuth = () => useContext(AuthContext)

export function AuthProvider({ children }) {
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Restore session on initial load via backend /auth/me
    api('/auth/me')
      .then((me) => setProfile(me))
      .catch(() => {
        setProfile(null)
        clearToken()
      })
      .finally(() => setLoading(false))
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

    if (data.access_token) {
      setToken(data.access_token)
    }
    setProfile(data.user)
    return data.user
  }

  async function logout() {
    try {
      await api('/auth/logout', null, { method: 'POST' })
    } catch {
      // Gracefully continue with client-side cleanup
    } finally {
      clearToken()
      setProfile(null)
    }
  }

  return (
    <AuthContext.Provider value={{ profile, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}
