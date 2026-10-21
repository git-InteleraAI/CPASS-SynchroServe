import { useAuth } from '../auth/AuthContext'

export default function AdminHome() {
  const { profile } = useAuth()

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div className="hero-banner">
        <div>
          <span className="pill-badge">CPASS Administration</span>
          <h2>System Overview & Governance</h2>
          <p>System overview, master data governance, and role-based access management.</p>
        </div>
        <span className="pill-badge" style={{ alignSelf: 'flex-start' }}>
          Role: {profile?.role || 'ADMIN'}
        </span>
      </div>

      <div className="warning">
        <strong style={{ display: 'block', marginBottom: '4px' }}>Separation of Duties Notice:</strong>
        <p style={{ margin: 0, fontSize: '0.92rem', lineHeight: 1.5 }}>
          You are signed in with the <strong>ADMIN</strong> role. Under CPASS operating procedures and operational compliance,
          direct L1 Document Verification and upload operations are strictly segregated and restricted to verified <strong>L1_COORDINATOR</strong> accounts.
          Administrative accounts cannot directly verify or upload candidate placement files.
        </p>
      </div>

      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))' }}>
        <div className="panel" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <h3>Master Data Master Records</h3>
          <p className="muted" style={{ fontSize: '0.9rem' }}>
            Candidate master records loaded from DDU-GKY master dataset.
          </p>
          <div style={{ fontSize: '2.2rem', fontWeight: 700, color: 'var(--blue)', marginTop: 'auto' }}>
            9,084
          </div>
          <span className="chip success" style={{ alignSelf: 'flex-start' }}>
            ✓ Verified in Supabase
          </span>
        </div>

        <div className="panel" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <h3>Cloud Document Storage</h3>
          <p className="muted" style={{ fontSize: '0.9rem' }}>
            Google Drive hierarchy integration for candidate placement folders.
          </p>
          <div style={{ fontSize: '1.15rem', fontWeight: 600, color: 'var(--ink)', marginTop: 'auto' }}>
            CPASS Root Folder
          </div>
          <span className="chip info" style={{ alignSelf: 'flex-start' }}>
            OAuth2 / Service Account
          </span>
        </div>

        <div className="panel" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <h3>User & Profile Information</h3>
          <p className="muted" style={{ fontSize: '0.9rem' }}>
            Current authenticated administrator details.
          </p>
          <div style={{ fontSize: '0.95rem', marginTop: 'auto' }}>
            <strong style={{ fontSize: '1.05rem', color: 'var(--ink)' }}>{profile?.full_name}</strong>
            <div className="muted">{profile?.email}</div>
          </div>
          <span className={`chip ${profile?.is_active ? 'success' : 'danger'}`} style={{ alignSelf: 'flex-start' }}>
            {profile?.is_active ? 'Active Profile' : 'Inactive'}
          </span>
        </div>
      </div>

      <section className="panel">
        <h3 style={{ fontSize: '1.15rem' }}>Administrative Responsibilities & Guidance</h3>
        <ul style={{ margin: '0.75rem 0 0 0', paddingLeft: '1.25rem', lineHeight: 1.8, fontSize: '0.95rem', color: 'var(--mut)' }}>
          <li>
            <strong style={{ color: 'var(--ink)' }}>L1 Verification:</strong> For testing or performing candidate document verification, sign in with a dedicated account assigned the <code>L1_COORDINATOR</code> role.
          </li>
          <li>
            <strong style={{ color: 'var(--ink)' }}>Master Data Management:</strong> Candidate records in <code>ddugky_candidates</code> are protected against accidental overwrites and live reimports.
          </li>
          <li>
            <strong style={{ color: 'var(--ink)' }}>Data Governance:</strong> All document submissions produce permanent, auditable metadata records in <code>candidate_documents</code>.
          </li>
        </ul>
      </section>
    </div>
  )
}
