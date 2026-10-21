import { useState, useEffect, useRef } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import logoSrc from '../../assets/synchro-serve-logo-4k.png'
import './Login.css'

const ROLE_TABS = [
  { key: 'L1', value: 'L1_COORDINATOR', title: 'Placement coordinator', small: 'L1', label: 'Coordinator' },
  { key: 'L2', value: 'L2_MANAGER', title: 'Centre manager', small: 'L2', label: 'Manager' },
  { key: 'L3', value: 'L3_LEADER', title: 'Business leader', small: 'L3', label: 'Leader' },
  { key: 'ADMIN', value: 'ADMIN', title: 'Administrator', small: 'Admin', label: 'Administrator' },
]

const CAROUSEL_TITLES = ['Offer letter', 'Salary slips', 'Bank statements', 'Verified', 'Placed']
const CAROUSEL_ICONS = ['✉', '₹', '▤', '✓', '★']
const CAROUSEL_STATUSES = ['Persisted', '3 months', '3 months', 'Checked', 'Appointed']
const CAROUSEL_GRADIENTS = [
  'linear-gradient(160deg,#1C6BEA,#0A2A7A)',
  'linear-gradient(160deg,#F4000F,#B0146A)',
  'linear-gradient(160deg,#B0146A,#0B4FB8)',
  'linear-gradient(160deg,#0B4FB8,#27B0E8)',
  'linear-gradient(160deg,#102A7A,#B0146A)',
]

const N = 10
const P = 118
const TT = N * P
const C = 320
const D = 326
const md = (a, n) => ((a % n) + n) % n

function rp(p, r) {
  let s = ''
  for (let i = 0; i < 4; i++) {
    const v = p[i]
    const a = p[(i + 3) % 4]
    const b = p[(i + 1) % 4]
    const u = (q) => {
      const dx = q[0] - v[0]
      const dy = q[1] - v[1]
      const l = Math.hypot(dx, dy) || 1
      return [v[0] + (dx / l) * r, v[1] + (dy / l) * r]
    }
    const A = u(a)
    const B = u(b)
    s += (i ? 'L' : 'M') + A[0] + ' ' + A[1] + 'Q' + v[0] + ' ' + v[1] + ' ' + B[0] + ' ' + B[1]
  }
  return s + 'Z'
}

export default function Login() {
  const { profile, login } = useAuth()
  const [selectedTab, setSelectedTab] = useState(0)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [rememberMe, setRememberMe] = useState(false)
  const [error, setError] = useState('')
  const [toastMsg, setToastMsg] = useState('')
  const [busy, setBusy] = useState(false)

  const loginRef = useRef(null)
  const stageRef = useRef(null)
  const toastTimeoutRef = useRef(null)

  const showToast = (msg) => {
    if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current)
    setToastMsg(msg)
    toastTimeoutRef.current = setTimeout(() => {
      setToastMsg('')
    }, 2600)
  }

  useEffect(() => {
    const stage = stageRef.current
    if (!stage) return

    stage.innerHTML = ''
    const cards = []
    for (let i = 0; i < N; i++) {
      const c = document.createElement('div')
      c.className = 'card'
      const k = i % 5
      c.innerHTML = `<div class="ci" style="background:${CAROUSEL_GRADIENTS[k]}"><i class="ic">${CAROUSEL_ICONS[k]}</i><b>${CAROUSEL_TITLES[k]}</b><span class="bar"></span><span class="bar s"></span><em>${CAROUSEL_STATUSES[k]}</em></div>`
      stage.appendChild(c)
      cards.push(c)
    }

    const RM = typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion:reduce)').matches
    let sc = 0
    let vel = 0
    let drag = false
    let lx = 0
    let lt = 0
    let prev = 0
    let rafId

    const clock = document.documentElement.animate([{ opacity: 1 }, { opacity: 1 }], { duration: 1e9 })

    function lay() {
      const W = stage.clientWidth || 320
      const H = stage.clientHeight || 520
      const kW = W / 640
      const kH = H / 520
      const k = Math.min(kW, Math.max(0.45, kH * 1.05))
      stage.style.setProperty('--k', String(k))
      const cy0 = H / k / 2

      cards.forEach((c, i) => {
        const t = md(i * P - sc + TT / 2, TT) - TT / 2
        const x = C + t * (1 + 0.083 * (t / D) ** 2)
        const d = Math.min(1.15, Math.abs(x - C) / D)
        const w = 96 + 28 * d * d
        if (x < -w || x > 640 + w) {
          c.style.visibility = 'hidden'
          return
        }
        c.style.visibility = ''
        const xl = x - w / 2
        const xr = x + w / 2
        const q = (e) => Math.min(1.2, Math.abs(e - C) / D)
        const hl = 170 + 56 * q(xl) ** 2.6
        const hr = 170 + 56 * q(xr) ** 2.6
        const cy = cy0 - 7 * d * d
        const m = Math.max(hl, hr)
        const r = 9
        const pts = [
          [xl, cy - hl / 2],
          [xr, cy - hr / 2],
          [xr, cy + hr / 2],
          [xl, cy + hl / 2],
        ].map((a) => [a[0] * k, a[1] * k])

        c.style.clipPath = `path('${rp(pts, r * k)}')`
        const ci = c.firstChild
        if (ci) {
          ci.style.left = xl * k + 'px'
          ci.style.width = w * k + 'px'
          ci.style.top = (cy - m / 2) * k + 'px'
          ci.style.height = m * k + 'px'
        }
      })
    }

    function frame() {
      const now = clock.currentTime || performance.now()
      const dt = Math.min(0.05, (now - prev) / 1000 || 0)
      prev = now
      if (!drag && !RM) {
        sc += (50 * 0.6 + vel) * dt
        vel *= Math.pow(0.05, dt)
      }
      lay()
      rafId = requestAnimationFrame(frame)
    }

    const K = () => (stage.clientWidth || 320) / 640

    const onPointerDown = (e) => {
      drag = true
      lx = e.clientX
      lt = performance.now()
      vel = 0
      stage.classList.add('drag')
      stage.setPointerCapture(e.pointerId)
    }

    const onPointerMove = (e) => {
      if (!drag) return
      const dx = e.clientX - lx
      const n = performance.now()
      const dt = (n - lt) / 1000 || 0.016
      sc -= dx / K()
      vel = 0.7 * vel + 0.3 * (-dx / K() / dt)
      lx = e.clientX
      lt = n
    }

    const onPointerUp = () => {
      drag = false
      stage.classList.remove('drag')
      vel = Math.max(-900, Math.min(900, vel))
    }

    stage.addEventListener('pointerdown', onPointerDown)
    stage.addEventListener('pointermove', onPointerMove)
    stage.addEventListener('pointerup', onPointerUp)
    stage.addEventListener('pointercancel', onPointerUp)

    rafId = requestAnimationFrame(frame)

    // Run entrance animations if not reduced motion
    if (!RM && loginRef.current) {
      const EZ = 'cubic-bezier(.2,.8,.2,1)'
      const KF = {
        drop: [{ opacity: 0, transform: 'translateY(-24px)' }, { opacity: 1, transform: 'none' }],
        pop: [{ opacity: 0, transform: 'scale(.6)' }, { opacity: 1, transform: 'scale(1.06)', offset: 0.7 }, { opacity: 1, transform: 'none' }],
        rise: [{ opacity: 0, transform: 'translateY(28px)', filter: 'blur(14px)' }, { opacity: 1, transform: 'none', filter: 'blur(0)' }],
        scale: [{ opacity: 0, transform: 'scale(.7)' }, { opacity: 1, transform: 'none' }],
        fade: [{ opacity: 0 }, { opacity: 1 }],
      }

      loginRef.current.querySelectorAll('[data-in]').forEach((el) => {
        const t = el.dataset.in
        const d = +el.dataset.d || 0
        if (t === 'draw') {
          el.querySelectorAll('path').forEach((p, i) => {
            p.setAttribute('pathLength', '1')
            p.style.strokeDasharray = '1'
            p.animate([{ strokeDashoffset: 1 }, { strokeDashoffset: 0 }], {
              duration: 900,
              delay: 900 + i * 300,
              easing: 'ease-out',
              fill: 'both',
            })
          })
          return
        }
        if (KF[t]) {
          el.animate(KF[t], {
            duration: t === 'rise' ? 900 : 650,
            delay: d,
            easing: EZ,
            fill: 'both',
          })
        }
      })
    }

    window.addEventListener('resize', lay)

    return () => {
      cancelAnimationFrame(rafId)
      clock.cancel()
      window.removeEventListener('resize', lay)
      stage.removeEventListener('pointerdown', onPointerDown)
      stage.removeEventListener('pointermove', onPointerMove)
      stage.removeEventListener('pointerup', onPointerUp)
      stage.removeEventListener('pointercancel', onPointerUp)
      stage.innerHTML = ''
    }
  }, [])

  if (profile) return <Navigate to="/" replace />

  async function submit(e) {
    e.preventDefault()
    setError('')

    const trimmedEmail = email.trim()
    if (!trimmedEmail || !password) {
      const msg = 'Enter your email and password to sign in.'
      setError(msg)
      showToast(msg)
      return
    }

    setBusy(true)
    try {
      const expectedRole = ROLE_TABS[selectedTab].value
      await login(trimmedEmail, password, expectedRole)
    } catch (err) {
      const msg = err.message || 'Authentication failed. Please check your credentials.'
      setError(msg)
      showToast(msg)
    } finally {
      setBusy(false)
    }
  }

  return (
    <main id="login" className="view" ref={loginRef}>
      <div className="shell">
        <section className="fside">
          <img
            className="logo"
            data-in="drop"
            data-d="0"
            src={logoSrc}
            alt="SynchroServe"
          />
          <span className="badge" data-in="pop" data-d="150">
            L1 verification portal
          </span>
          <h1>
            <span className="line" data-in="rise" data-d="280">
              Verify & Validate,
            </span>
            <span className="line" data-in="rise" data-d="400">
              Sync & Confirm.
            </span>
          </h1>
          <p className="sub" data-in="rise" data-d="540">
            Sign in to check offer letters, salary slips and bank statements for every candidate in your batch.
          </p>

          <form id="lf" data-in="rise" data-d="640" onSubmit={submit} noValidate>
            <div className="fg" role="group" aria-label="Sign in as">
              <span>Sign in as</span>
              <div className="tabs" role="tablist">
                {ROLE_TABS.map((tab, idx) => (
                  <button
                    key={tab.key}
                    type="button"
                    role="tab"
                    className={`tab ${selectedTab === idx ? 'on' : ''}`}
                    aria-selected={selectedTab === idx}
                    data-r={tab.key}
                    title={tab.title}
                    onClick={() => {
                      setSelectedTab(idx)
                      setError('')
                    }}
                  >
                    <small>{tab.small}</small>
                    {tab.label}
                  </button>
                ))}
                <i
                  className="ul"
                  style={{ transform: `translateX(${selectedTab * 100}%)` }}
                />
              </div>
              <input type="hidden" id="role" value={ROLE_TABS[selectedTab].key} />
            </div>

            <label className="f">
              Email
              <input
                className="in"
                id="em"
                type="email"
                placeholder="you@organisation.in"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>

            <label className="f">
              Password
              <span className="pw">
                <input
                  className="in"
                  id="pw"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Enter your password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button
                  type="button"
                  id="eye"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  onClick={() => setShowPassword(!showPassword)}
                >
                  {showPassword ? 'Hide' : 'Show'}
                </button>
              </span>
            </label>

            <div className="row">
              <label>
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                />{' '}
                Remember for 30 days
              </label>
              <a
                href="#forgot"
                onClick={(e) => {
                  e.preventDefault()
                  showToast('Password reset is managed by your CPASS administrator.')
                }}
              >
                Forgot password?
              </a>
            </div>

            {error && (
              <div className="auth-error-msg" role="alert">
                {error}
              </div>
            )}

            <span className="ring" data-in="scale" data-d="820" style={{ borderRadius: '99px' }}>
              <button className="btn" style={{ width: '100%' }} disabled={busy}>
                {busy ? 'Signing in…' : 'Sign in'}
              </button>
            </span>

            <p className="hint">Preview mode: any email and password opens the L1 dashboard.</p>
          </form>
        </section>

        <section className="art" id="art">
          <div id="stage" ref={stageRef} />
          <svg
            className="doodle"
            style={{ left: '7%', top: '8%' }}
            width="40"
            height="40"
            viewBox="0 0 40 40"
            data-in="draw"
          >
            <path d="M12 6 L4 34" />
            <path d="M30 6 L22 34" />
          </svg>
          <div
            className="note"
            style={{ right: '9%', top: '7%', transform: 'rotate(14deg)', textAlign: 'center' }}
            data-in="fade"
            data-d="1000"
          >
            Drag
            <br />
            the cards
          </div>
          <svg
            className="doodle"
            style={{ right: '6%', top: '22%' }}
            width="80"
            height="90"
            viewBox="0 0 80 90"
            data-in="draw"
          >
            <path d="M60 6 C 78 30, 70 60, 38 80" />
            <path d="M52 82 L38 80 L42 66" />
          </svg>
          <div
            className="note"
            style={{ left: '8%', bottom: '7%', transform: 'rotate(-8deg)' }}
            data-in="fade"
            data-d="1200"
          >
            Zero paperwork
          </div>
        </section>
      </div>

      {toastMsg && (
        <div className="toast" role="status">
          {toastMsg}
        </div>
      )}
    </main>
  )
}
