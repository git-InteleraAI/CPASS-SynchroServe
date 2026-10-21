import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import Login from './pages/Login'
import L1Home from './pages/L1Home'
import AdminHome from './pages/AdminHome'

import logoSrc from '../assets/synchro-serve-logo-4k.png'

function Shell() {
  const { profile, loading, logout } = useAuth()
  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: 'var(--bg)', color: 'var(--mut)', font: '500 15px Inter, sans-serif' }}>
        <p>Loading application…</p>
      </div>
    )
  }
  if (!profile) return <Navigate to="/login" replace />

  const isL1 = profile.role === 'L1_COORDINATOR'
  const isAdmin = profile.role === 'ADMIN'

  const initials = profile.full_name
    ? profile.full_name
        .split(' ')
        .filter(Boolean)
        .map((n) => n[0])
        .join('')
        .slice(0, 2)
        .toUpperCase()
    : 'CP'

  const roleDisplay = {
    L1_COORDINATOR: 'Placement Coordinator (L1)',
    L2_MANAGER: 'Centre Manager (L2)',
    L3_LEADER: 'Business Leader (L3)',
    ADMIN: 'System Administrator',
  }[profile.role] || profile.role

  return (
    <div className="app-layout">
      <header className="top">
        <img className="logo" src={logoSrc} alt="SynchroServe" />
        <div className="user">
          <div className="av">{initials}</div>
          <div className="user-info">
            <b>{profile.full_name}</b>
            <small>{roleDisplay}</small>
          </div>
          <button className="link" onClick={logout} title="Sign out of CPASS">
            Sign out
          </button>
        </div>
      </header>
      <main className="content-container">
        {isL1 ? (
          <L1Home />
        ) : isAdmin ? (
          <AdminHome />
        ) : (
          <div className="panel" style={{ margin: '2rem auto', maxWidth: 600 }}>
            <h3>Upcoming Role Module</h3>
            <p className="muted">The {roleDisplay} workflow screens will be released in an upcoming phase.</p>
          </div>
        )}
      </main>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/*" element={<Shell />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
